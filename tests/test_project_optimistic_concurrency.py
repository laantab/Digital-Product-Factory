"""Phase 0B-2: a stale writer must never overwrite newer project state.

ROOT CAUSE THIS GUARDS
-----------------------
The entire per-project Factory state lives in one JSON blob
(`projects.data`), and `database.update_project()` replaced that blob
wholesale with no version check. Any caller holding a copy read before
someone else's write would silently erase that write on save.

This is not hypothetical. It is the exact mechanism behind the v1.7.9
production data loss, with only ONE writer: `advance_build()`'s failure
path persisted a `data` snapshot captured before the stage runner ran,
erasing chapters and ledger spend the runner had already saved during
that same attempt.

The Upgrade 0 architecture adds a background worker as a SECOND writer.
Without this protection, that would turn an occasional bug into a
structural guarantee of lost updates, so this lands first -- on the
existing SQLite path, before any new infrastructure.

THE CONTRACT
------------
1. `projects` carries a `version` column, incremented on every write.
2. Every read stamps the version into the returned in-memory `data` dict
   under `database.ROW_VERSION_KEY`. It is NEVER persisted into the blob.
3. A write carrying a version is a compare-and-swap: it succeeds only if
   the row is still at that version, and raises `StaleProjectWrite`
   otherwise.
4. A write carrying no version (freshly constructed `data`, never read
   from the database) is an unversioned write and is permitted, exactly
   as before -- there is no earlier read for it to be stale against.
5. On success the caller's dict is re-stamped with the new version, so a
   caller that saves the same evolving dict repeatedly (the build
   orchestrator's checkpoint pattern) stays protected on every write.
6. No automatic retry happens inside `database.py`. Retrying is the
   caller's decision, because a blind retry would reintroduce exactly
   the lost update this prevents.

No external/paid call is made by any test here.
"""
from __future__ import annotations

import json

import pytest

import database


def _make(name: str = "Concurrency Test Book", data: dict | None = None) -> int:
    project = database.create_project(
        name, "ebook", data if data is not None else {"stage": "start", "chapters": []},
        user_saved=True, system_test=False, temporary=False,
    )
    return int(project["id"])


def _raw_blob(project_id: int) -> dict:
    """Read the stored JSON directly, bypassing every helper."""
    conn = database.get_conn()
    try:
        row = conn.execute("SELECT data FROM projects WHERE id=?", (project_id,)).fetchone()
    finally:
        conn.close()
    return json.loads(row["data"] or "{}")


# =============================================== the lost-update contract ===


def test_a_two_readers_load_the_same_version():
    pid = _make()
    a = database.get_project(pid)["data"]
    b = database.get_project(pid)["data"]

    assert database.ROW_VERSION_KEY in a, "a read must carry the row version"
    assert a[database.ROW_VERSION_KEY] == b[database.ROW_VERSION_KEY], (
        "two readers of an unchanged row must see the same version"
    )


def test_b_writer_a_saves_successfully():
    pid = _make()
    a = database.get_project(pid)["data"]
    before = a[database.ROW_VERSION_KEY]

    a["chapters"] = ["ch1", "ch2"]
    database.update_project(pid, None, a)

    assert database.get_project(pid)["data"]["chapters"] == ["ch1", "ch2"]
    assert a[database.ROW_VERSION_KEY] == before + 1, (
        "a successful write must re-stamp the caller's dict with the new version"
    )


def test_c_d_e_stale_writer_is_rejected_and_cannot_overwrite():
    """The core guarantee: B loaded before A saved, so B must not win."""
    pid = _make()

    # A. both readers load the same version
    writer_a = database.get_project(pid)["data"]
    writer_b = database.get_project(pid)["data"]

    # B. writer A saves real work
    writer_a["chapters"] = ["ch1", "ch2"]
    writer_a["manuscript"] = "two real chapters"
    database.update_project(pid, None, writer_a)

    # C. writer B attempts to save its stale copy, which never saw A's work
    writer_b["chapters"] = []
    writer_b["manuscript"] = ""

    # D. writer B is rejected
    with pytest.raises(database.StaleProjectWrite):
        database.update_project(pid, None, writer_b)

    # E. A's changes survive intact
    final = database.get_project(pid)["data"]
    assert final["chapters"] == ["ch1", "ch2"], "the stale write erased newer work"
    assert final["manuscript"] == "two real chapters"


def test_the_v1_7_9_failure_shape_specifically():
    """The exact production shape: read a snapshot, work, then a failure
    path writes the PRE-work snapshot back over the saved progress."""
    pid = _make(data={"stage": "manuscript", "ebook_workspace": {"accepted_chapters": []}})

    pre_attempt_snapshot = database.get_project(pid)["data"]   # what advance_build held

    # the runner persists real progress during the attempt
    working = database.get_project(pid)["data"]
    working["ebook_workspace"]["accepted_chapters"] = [
        {"order": 1, "title": "Chapter 1", "body": "real paid work"},
        {"order": 2, "title": "Chapter 2", "body": "real paid work"},
    ]
    database.update_project(pid, None, working)

    # the failure path then tries to persist its stale pre-attempt snapshot
    with pytest.raises(database.StaleProjectWrite):
        database.update_project(pid, None, pre_attempt_snapshot)

    saved = database.get_project(pid)["data"]["ebook_workspace"]["accepted_chapters"]
    assert len(saved) == 2, "already-persisted chapters must survive a later failure write"


def test_f_normal_single_writer_saves_still_work():
    pid = _make()
    for i in range(1, 6):
        data = database.get_project(pid)["data"]
        data["counter"] = i
        database.update_project(pid, None, data)
    assert database.get_project(pid)["data"]["counter"] == 5


def test_repeated_saves_from_the_same_dict_stay_protected():
    """The build orchestrator's checkpoint pattern: one evolving dict,
    saved repeatedly. Each save must remain version-protected."""
    pid = _make()
    data = database.get_project(pid)["data"]

    for chapter in range(1, 4):
        data.setdefault("chapters", []).append(f"ch{chapter}")
        database.update_project(pid, None, data)

    assert database.get_project(pid)["data"]["chapters"] == ["ch1", "ch2", "ch3"]

    # A writer still holding the ORIGINAL version is now stale and rejected.
    stale = database.get_project(pid)["data"]
    stale[database.ROW_VERSION_KEY] = 0
    stale["chapters"] = []
    with pytest.raises(database.StaleProjectWrite):
        database.update_project(pid, None, stale)


def test_unversioned_writes_are_still_permitted():
    """Freshly constructed data was never read, so it cannot be stale."""
    pid = _make()
    database.update_project(pid, None, {"stage": "rebuilt", "chapters": ["x"]})
    assert database.get_project(pid)["data"]["stage"] == "rebuilt"


def test_the_version_key_is_never_persisted_into_the_blob():
    pid = _make()
    data = database.get_project(pid)["data"]
    data["chapters"] = ["ch1"]
    database.update_project(pid, None, data)

    assert database.ROW_VERSION_KEY not in _raw_blob(pid), (
        "the row version is in-memory bookkeeping and must never be stored; "
        "a stored version would go stale and could be trusted wrongly"
    )


def test_no_silent_retry_happens_inside_the_database_layer():
    """A rejected write must stay rejected -- never quietly reapplied."""
    pid = _make()
    winner = database.get_project(pid)["data"]
    loser = database.get_project(pid)["data"]

    winner["value"] = "kept"
    database.update_project(pid, None, winner)

    loser["value"] = "must not appear"
    with pytest.raises(database.StaleProjectWrite):
        database.update_project(pid, None, loser)

    assert database.get_project(pid)["data"]["value"] == "kept"


def test_a_missing_project_still_returns_none_not_a_stale_error():
    assert database.update_project(999_999_999, None, {"a": 1}) is None


# ============================================= lifecycle protections (G) ===


def test_g_approved_and_locked_lifecycle_protections_still_work():
    from services.quality.artifact_state import (
        ArtifactState,
        ArtifactStateError,
        assert_content_mutable,
        resolve_artifact_state,
    )

    draft = database.get_project(_make(name="Draft Book"))["data"]
    assert resolve_artifact_state(draft) == ArtifactState.DRAFT

    locked_pid = _make(name="Locked Book", data={
        "artifact_state": "LOCKED",
        "export_ready": True,
        "content": "approved manuscript",
    })
    locked = database.get_project(locked_pid)["data"]

    # The version stamp must not perturb lifecycle resolution.
    assert resolve_artifact_state(locked) == ArtifactState.LOCKED
    with pytest.raises(ArtifactStateError):
        assert_content_mutable(locked)

    approved_pid = _make(name="Approved Book", data={
        "artifact_state": "APPROVED",
        "export_ready": True,
        "content": "approved manuscript",
    })
    approved = database.get_project(approved_pid)["data"]
    assert resolve_artifact_state(approved) == ArtifactState.APPROVED
    with pytest.raises(ArtifactStateError):
        assert_content_mutable(approved)


def test_g_locked_projects_still_cannot_be_deleted():
    pid = _make(name="Locked Undeletable", data={
        "artifact_state": "LOCKED", "export_ready": True, "content": "x",
    })
    with pytest.raises(Exception):
        database.delete_project(pid)
    assert database.get_project(pid) is not None


# ==================================== admin sweep must not clobber (0B-2) ===


def test_the_admin_hide_sweep_cannot_clobber_a_concurrent_write():
    """hide_internal_records_from_customers() writes projects.data directly,
    bypassing update_project(). It must skip a row that changed underneath
    it rather than overwrite newer state."""
    result = database.hide_internal_records_from_customers()
    assert isinstance(result, dict)
    # The sweep reports what it could not safely touch instead of clobbering.
    assert "skipped_stale" in result, (
        "the direct-write admin sweep must report rows it skipped as stale"
    )


# ============================================ route compatibility (H) ===


def test_h_customer_routes_remain_compatible():
    import app as app_module

    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    pid = _make(name="Route Compatible Book")
    resp = client.get("/projects")
    assert resp.status_code == 200, resp.status_code
    assert isinstance(resp.get_json(), (list, dict))

    detail = client.get(f"/projects/{pid}")
    assert detail.status_code == 200, detail.status_code

    # A read-modify-write through the normal helper path still round-trips.
    data = database.get_project(pid)["data"]
    data["title"] = "Route Compatible Book"
    database.update_project(pid, None, data)
    assert database.get_project(pid)["data"]["title"] == "Route Compatible Book"


def test_list_reads_also_carry_a_usable_version():
    """Every read path stamps the version, not just get_project()."""
    pid = _make(name="Listed Book")
    listed = [p for p in database.list_projects(include_system=True) if p["id"] == pid]
    assert listed, "project should be listed"
    data = listed[0]["data"]
    assert database.ROW_VERSION_KEY in data
    data["from_list"] = True
    database.update_project(pid, None, data)
    assert database.get_project(pid)["data"]["from_list"] is True
