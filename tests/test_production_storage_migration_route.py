"""Phase 0B-3E — the token-gated production migration route.

This route exists because the production Factory runs on a Render
persistent disk no other machine can reach, on a plan with no Shell. It is
the only way to run the proven migration executor against production data.

Because it is an admin route on a public host, the tests that matter most
are the ones about what it REFUSES to do:

  * invisible (404) unless FACTORY_MIGRATION_TOKEN is set on the host
  * 404 on a wrong or missing token -- never 401/403, which would confirm
    the route exists
  * never deletes or rewrites pdf_bytes
  * never rewrites a project data blob or bumps a project version
  * migration requires an explicit confirm flag and is bounded
  * no credential ever appears in a response
"""
from __future__ import annotations

import base64
import io
import json
import os

import pytest

import database

TOKEN = "test-migration-token-abc123"
ROUTE = "/admin/storage-migration"


def _pdf(marker="prod"):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle(marker)
    c.drawString(72, 720, marker)
    c.showPage()
    c.save()
    return buf.getvalue()


PDF = _pdf()


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("FACTORY_STORAGE_DIR", str(tmp_path / "assets"))
    monkeypatch.delenv("FACTORY_STORAGE_DRIVER", raising=False)
    monkeypatch.delenv("FACTORY_MIGRATION_TOKEN", raising=False)
    from services.storage import reset_storage

    reset_storage()
    database.init_db()
    import app as app_module

    yield app_module.app.test_client()
    reset_storage()


def _project(pdf=PDF):
    data = {"product_type": "faith_planner", "is_pdf": True, "title": "Prod",
            "pdf_bytes": base64.b64encode(pdf).decode("ascii"), "fields": {}}
    return database.create_project("Prod Product", "product", data)


def _post(client, body=None, token=TOKEN):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Factory-Migration-Token"] = token
    return client.post(ROUTE, data=json.dumps(body or {}), headers=headers)


# ============================================================ refusals ======


def test_route_is_invisible_when_no_token_is_configured(client):
    """On a host that never uses this, the route must not exist at all."""
    assert "FACTORY_MIGRATION_TOKEN" not in os.environ
    assert _post(client).status_code == 404


def test_wrong_token_is_404_not_403(client, monkeypatch):
    """A 401/403 would confirm the route exists. It must stay a 404."""
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    assert _post(client, token="wrong-token").status_code == 404


def test_missing_token_header_is_404(client, monkeypatch):
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    assert _post(client, token=None).status_code == 404


def test_empty_token_env_does_not_admit_an_empty_header(client, monkeypatch):
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", "   ")
    assert _post(client, token="").status_code == 404
    assert _post(client, token="   ").status_code == 404


def test_migration_requires_an_explicit_confirm_flag(client, monkeypatch):
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    _project()
    response = _post(client, {"action": "migrate", "limit": 1})
    assert response.status_code == 400
    assert b"confirm" in response.data.lower()


def test_unknown_action_is_refused(client, monkeypatch):
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    assert _post(client, {"action": "delete_everything"}).status_code == 400


def test_no_credential_value_appears_in_any_response(client, monkeypatch):
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    monkeypatch.setenv("FACTORY_R2_SECRET_ACCESS_KEY", "super-secret-value-xyz")
    monkeypatch.setenv("FACTORY_R2_ACCESS_KEY_ID", "AKIA-SECRET-ID-xyz")
    _project()
    for body in ({"action": "inventory"}, {"action": "migrate"},
                 {"action": "nonsense"}):
        data = _post(client, body).data
        assert b"super-secret-value-xyz" not in data
        assert b"AKIA-SECRET-ID-xyz" not in data
        assert TOKEN.encode() not in data


# ======================================================== read-only work ====


def test_inventory_is_read_only_and_reports_eligibility(client, monkeypatch):
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    project = _project()
    before = database.get_project(project["id"])

    response = _post(client, {"action": "inventory"})
    assert response.status_code == 200
    result = response.get_json()["result"]

    assert result["projects_scanned"] >= 1
    assert result["projects_with_pdf_bytes"] >= 1
    assert result["pending_migration"] >= 1
    assert any(p["project_id"] == project["id"] for p in result["pending"])

    after = database.get_project(project["id"])
    assert after["data"]["pdf_bytes"] == before["data"]["pdf_bytes"]
    assert after["data"]["_row_version"] == before["data"]["_row_version"]
    assert database.list_assets(project["id"]) == []


def test_inventory_reports_malformed_records_rather_than_repairing_them(
    client, monkeypatch
):
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    broken = database.create_project(
        "Broken", "product",
        {"product_type": "faith_planner", "is_pdf": True, "pdf_bytes": "%%%not-base64%%%"},
    )
    result = _post(client, {"action": "inventory"}).get_json()["result"]
    problems = {p["project_id"] for p in result["problems"]}
    assert broken["id"] in problems
    # and it is NOT offered for migration
    assert all(p["project_id"] != broken["id"] for p in result["pending"])
    # and the record was left exactly as it was
    assert database.get_project(broken["id"])["data"]["pdf_bytes"] == "%%%not-base64%%%"


def test_a_project_without_pdf_bytes_is_not_eligible(client, monkeypatch):
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    plain = database.create_project("No PDF", "product", {"product_type": "ebook"})
    result = _post(client, {"action": "inventory"}).get_json()["result"]
    assert all(p["project_id"] != plain["id"] for p in result["pending"])


# ============================================================== backup ======


def test_backup_is_byte_identical_and_never_overwrites(client, monkeypatch):
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    _project()
    result = _post(client, {"action": "backup"}).get_json()["result"]
    assert result["ok"] is True
    assert result["identical"] is True
    assert result["source_sha256"] == result["backup_sha256"]
    assert result["source_bytes"] == result["backup_bytes"]
    assert os.path.exists(result["backup_path"])
    assert result["backup_path"] != result["source_path"]


# ========================================== migration safety (mocked R2) ====


def test_migration_keeps_pdf_bytes_and_does_not_touch_the_project(
    client, monkeypatch, tmp_path
):
    """The whole contract, end to end, with storage mocked to local."""
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    project = _project()
    before = database.get_project(project["id"])

    from services.storage.local import LocalFilesystemDriver
    import services.storage.production_migration as pm

    class FakeR2(LocalFilesystemDriver):
        name = "r2"

    monkeypatch.setattr("services.storage.r2.R2Driver",
                        lambda *a, **k: FakeR2(root=tmp_path / "fake_r2"))

    # Target this project explicitly: the suite shares one database, so
    # other tests' eligible projects must not decide what gets migrated.
    response = _post(client, {"action": "migrate", "limit": 5, "confirm": True,
                              "project_ids": [project["id"]]})
    assert response.status_code == 200, response.data[:300]
    result = response.get_json()["result"]
    assert project["id"] in result["migrated"]
    assert result["failed"] == []

    after = database.get_project(project["id"])
    assert after["data"]["pdf_bytes"] == before["data"]["pdf_bytes"], "pdf_bytes changed"
    assert base64.b64decode(after["data"]["pdf_bytes"]) == PDF
    assert after["data"]["_row_version"] == before["data"]["_row_version"], "version bumped"
    assert after["data"].get("artifact_state") == before["data"].get("artifact_state")

    rows = database.list_assets(project["id"])
    assert len(rows) == 1 and rows[0]["approved"] is True


def test_migration_is_idempotent_across_requests(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    project = _project()
    from services.storage.local import LocalFilesystemDriver

    class FakeR2(LocalFilesystemDriver):
        name = "r2"

    monkeypatch.setattr("services.storage.r2.R2Driver",
                        lambda *a, **k: FakeR2(root=tmp_path / "fake_r2"))

    body = {"action": "migrate", "limit": 5, "confirm": True,
            "project_ids": [project["id"]]}
    first = _post(client, body).get_json()
    second = _post(client, body).get_json()

    assert project["id"] in first["result"]["migrated"]
    # Second pass finds nothing pending -- the inventory excludes it now.
    assert project["id"] not in second["result"]["migrated"]
    assert len(database.list_assets(project["id"])) == 1


def test_migrate_is_bounded_per_request(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    for _ in range(4):
        _project()
    from services.storage.local import LocalFilesystemDriver

    class FakeR2(LocalFilesystemDriver):
        name = "r2"

    monkeypatch.setattr("services.storage.r2.R2Driver",
                        lambda *a, **k: FakeR2(root=tmp_path / "fake_r2"))

    result = _post(client, {"action": "migrate", "limit": 2, "confirm": True}).get_json()["result"]
    assert result["migrated_count"] <= 2, "limit not honoured"


def test_cli_default_action_is_read_only(client, monkeypatch, capsys):
    """`python pmig.py` with no arguments must only ever read.

    It is typed straight into a production shell, so the default has to be
    the harmless one -- never a migration.
    """
    import services.storage.production_migration as pm

    project = _project()
    before = database.get_project(project["id"])

    assert pm.main([]) == 0
    printed = json.loads(capsys.readouterr().out)

    assert "projects_scanned" in printed
    assert "pending_migration" in printed
    assert "on_persistent_disk" in printed
    assert "pending" not in printed, "the full list must not be dumped to a shell"

    after = database.get_project(project["id"])
    assert after["data"]["pdf_bytes"] == before["data"]["pdf_bytes"]
    assert after["data"]["_row_version"] == before["data"]["_row_version"]
    assert database.list_assets(project["id"]) == []


def test_cli_rejects_an_unknown_action_without_doing_anything(client, capsys):
    import services.storage.production_migration as pm

    project = _project()
    assert pm.main(["destroy"]) == 2
    assert "unknown action" in capsys.readouterr().out
    assert database.list_assets(project["id"]) == []


def test_cli_verify_does_not_migrate(client, capsys):
    import services.storage.production_migration as pm

    project = _project()
    assert pm.main(["verify"]) == 0
    assert database.list_assets(project["id"]) == [], "verify must never migrate"


def test_migration_is_not_limited_by_the_inventory_display_cap(client, monkeypatch):
    """A migration must reach projects beyond the response's 200-row cap.

    `inventory()` trims its pending list so an HTTP response stays sane.
    If `migrate()` worked from that trimmed list, a database with more
    eligible projects than the cap would leave the tail permanently
    unmigrated -- silently.
    """
    import services.storage.production_migration as pm

    full = pm._scan()
    shown = pm.inventory()
    assert shown["pending_migration"] == full["pending_migration"], (
        "the totals must describe every eligible project, not the shown page"
    )
    assert len(shown["pending"]) <= 200
    assert len(full["pending"]) == full["pending_migration"], (
        "the internal scan must return the complete list"
    )


def test_verify_reports_a_mismatch_rather_than_hiding_it(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    project = _project()
    from services.storage.local import LocalFilesystemDriver

    root = tmp_path / "fake_r2"

    class FakeR2(LocalFilesystemDriver):
        name = "r2"

    monkeypatch.setattr("services.storage.r2.R2Driver", lambda *a, **k: FakeR2(root=root))
    _post(client, {"action": "migrate", "limit": 5, "confirm": True,
                   "project_ids": [project["id"]]})

    # Scoped to THIS project: the suite shares one database, so assets left
    # by other tests (pointing at their own temp roots) must not decide it.
    def failures_for(pid):
        # Verify only this project. A whole-database verify truncates its
        # failure list, so another suite's leftovers could crowd this one out.
        result = _post(client, {"action": "verify",
                                "project_ids": [pid]}).get_json()["result"]
        assert result["verified"] == 1, "the check must target exactly this project"
        return result["failures"]

    assert failures_for(project["id"]) == [], "a freshly migrated asset must verify"

    # Corrupt the stored object behind the recorded checksum.
    from services.storage.keys import KIND_PDF, embedded_key

    FakeR2(root=root).put(embedded_key(project["id"], "pdf_bytes", KIND_PDF), b"corrupt")
    assert failures_for(project["id"]), "a corrupt object must be reported, not hidden"
    # the legacy copy is still fine
    assert base64.b64decode(database.get_project(project["id"])["data"]["pdf_bytes"]) == PDF


# =========================================== the gate itself is unchanged ===


def test_the_route_is_exempt_from_the_invite_gate(client, monkeypatch):
    """It carries a stronger credential; the invite cookie adds nothing.

    The gate is off under FACTORY_TEST_MODE, so it is switched on the way
    its own suite does it -- by patching _invite_code_required.
    """
    import app as app_module

    assert ROUTE in app_module._INVITE_EXEMPT_PATHS
    monkeypatch.setattr(app_module, "_invite_code_required", lambda: "some-invite-code")
    monkeypatch.setenv("FACTORY_MIGRATION_TOKEN", TOKEN)
    # No invite cookie supplied, yet the migration token alone admits it.
    assert _post(client, {"action": "inventory"}).status_code == 200
    # …and a wrong migration token is still refused.
    assert _post(client, {"action": "inventory"}, token="nope").status_code == 404


def test_other_routes_remain_gated_when_an_invite_code_is_set(client, monkeypatch):
    """Exempting one route must not weaken the gate anywhere else."""
    import app as app_module

    monkeypatch.setattr(app_module, "_invite_code_required", lambda: "some-invite-code")
    assert client.get("/projects").status_code == 401
    assert client.get("/admin/delete-test-projects").status_code in (401, 405)
