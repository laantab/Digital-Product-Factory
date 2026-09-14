"""A live customer build stalled at 30% and the customer had no way forward.

ROOT CAUSE THIS GUARDS
-----------------------
A stage's attempt counter (services.ebook_build_orchestrator: rec["attempts"])
was never reset once it reached MAX_STAGE_ATTEMPTS. Once that happened, every
future /advance call re-failed the build instantly without even attempting the
stage. On top of that, static/js/app.js's openEbookBuild() only called /advance
again when the build was NOT already failed -- so the customer-facing "Try
again" button, once a build had failed, only re-fetched read-only status and
re-rendered the identical failure card. It never called /advance at all.

Together these left a paid customer staring at a dead end with their book
saved but stuck at "We couldn't finish your ebook", no matter how many times
they clicked the only button on the screen.

THE FIX
-------
An explicit "Resume Build" customer action (POST /ebook/build/<id>/resume,
services.ebook_build_orchestrator.resume_build) that clears the one stalled
stage's attempt count and hands the build back to the ordinary checkpoint
loop. It never runs a stage itself, never touches a stage that already
validated, and the manuscript stage's own resume-without-duplication design
(services.ebook_project_workspace.execute_generate_manuscript) is unchanged,
so already-accepted chapters are still never regenerated or re-billed.

No external/paid call is made by any test here.
"""
from __future__ import annotations

import pathlib
import re

import pytest

import app as app_module
import database
from services import ebook_build_orchestrator as orch

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
APP_PY = (ROOT / "app.py").read_text(encoding="utf-8")

ALL_STAGES = list(orch.STAGES)


def _rail(done_stages):
    rail = {}
    for stage in ALL_STAGES:
        rail[stage] = {"id": stage, "status": "approved" if stage in done_stages else "not_started"}
    return rail


def _project_data(done_stages, build_state=None):
    data = {
        "product_type": "ebook",
        "title": "Container Gardening for Beginners",
        "artifact_state": "DRAFT",
        "ebook_workspace": {"rail": _rail(done_stages)},
    }
    if build_state is not None:
        data["ebook_build"] = build_state
    return data


def _make(name, data):
    return database.create_project(
        name, "ebook", data, user_saved=True, system_test=False, temporary=False,
    )


def _stalled_manuscript_state():
    """A build that has genuinely exhausted its automatic attempts."""
    return {
        "build_id": "b1",
        "stages": {
            "manuscript": {
                "status": orch.FAILED_FINAL,
                "attempts": orch.MAX_STAGE_ATTEMPTS,
                "error": "internal detail the customer never sees",
                "running_since": 0,
            }
        },
        "customer_message": orch.MSG_FINAL,
        "finished": False,
        "failed": True,
    }


def _spy_runner(calls, key, result_data):
    def runner(data, pid):
        calls.append(key)
        return dict(result_data)
    return runner


# --------------------------------------------------------------- backend ---


class ResumeClearsTheStalledStageTests:
    """Grouped as a mixin so both direct-call and route tests share fixtures."""


def test_a_stalled_build_cannot_advance_on_its_own(monkeypatch):
    """Proves the bug existed: attempts never reset, so advance instantly re-fails."""
    project = _make("Stalled Book", _project_data(
        {"research", "title", "outline"}, _stalled_manuscript_state(),
    ))
    calls: list[str] = []
    monkeypatch.setitem(orch.STAGE_RUNNERS, "manuscript", _spy_runner(calls, "manuscript", {}))

    status = orch.advance_build(project["id"])

    assert status["failed"] is True
    assert status["finished"] is False
    assert calls == [], "a stage past the attempt ceiling must never be re-run automatically"


def test_resume_build_clears_the_ceiling_without_running_the_stage(monkeypatch):
    """Resume itself never generates anything -- it only clears the counter."""
    project = _make("Stalled Book", _project_data(
        {"research", "title", "outline"}, _stalled_manuscript_state(),
    ))
    calls: list[str] = []
    for stage in ALL_STAGES:
        monkeypatch.setitem(orch.STAGE_RUNNERS, stage, _spy_runner(calls, stage, {}))

    status = orch.resume_build(project["id"])

    assert status["failed"] is False, "Resume Build must clear the failed state"
    assert calls == [], "resume must never call a stage runner itself (no paid call, no regeneration)"

    row = database.get_project(project["id"])
    rec = row["data"]["ebook_build"]["stages"]["manuscript"]
    assert rec["attempts"] == 0
    assert rec["status"] == orch.NOT_STARTED


def test_resume_then_advance_actually_attempts_the_stage_again(monkeypatch):
    """The dead end is closed: Resume followed by the normal poll makes progress."""
    def succeed(data, pid):
        data = dict(data)
        ws = dict(data["ebook_workspace"])
        rail = dict(ws["rail"])
        rail["manuscript"] = {"id": "manuscript", "status": "approved"}
        ws["rail"] = rail
        data["ebook_workspace"] = ws
        return data

    project = _make("Stalled Book", _project_data(
        {"research", "title", "outline"}, _stalled_manuscript_state(),
    ))
    monkeypatch.setitem(orch.STAGE_RUNNERS, "manuscript", succeed)

    orch.resume_build(project["id"])
    status = orch.advance_build(project["id"])

    assert status["failed"] is False
    assert status["percent"] == 40, "manuscript must now count as the 4th completed stage"


def test_completed_stages_are_never_reattempted_by_advance(monkeypatch):
    """A stage the rail already marks approved must never be re-run, even mid-advance."""
    project = _make("Partly Done Book", _project_data({"research", "title", "outline"}))
    calls: list[str] = []
    for stage in ("research", "title", "outline"):
        monkeypatch.setitem(orch.STAGE_RUNNERS, stage, _spy_runner(calls, stage, {}))
    monkeypatch.setitem(orch.STAGE_RUNNERS, "manuscript", _spy_runner(calls, "manuscript", {}))

    orch.advance_build(project["id"])

    assert calls == ["manuscript"], "only the one incomplete stage may run; the approved ones must not"


def test_a_transient_failure_recovers_automatically_without_any_customer_action(monkeypatch):
    """FAILED_RECOVERABLE must not require Resume Build -- the poller alone fixes it."""
    attempts_made: list[int] = []

    def flaky(data, pid):
        attempts_made.append(1)
        if len(attempts_made) < 2:
            raise RuntimeError("a transient provider hiccup, never shown to the customer")
        data = dict(data)
        ws = dict(data["ebook_workspace"])
        rail = dict(ws["rail"])
        rail["manuscript"] = {"id": "manuscript", "status": "approved"}
        ws["rail"] = rail
        data["ebook_workspace"] = ws
        return data

    project = _make("Flaky Book", _project_data({"research", "title", "outline"}))
    monkeypatch.setitem(orch.STAGE_RUNNERS, "manuscript", flaky)

    first = orch.advance_build(project["id"])
    assert first["failed"] is False
    assert first["retrying"] is True, "one failed attempt below the ceiling must read as retrying, not failed"

    second = orch.advance_build(project["id"])
    assert second["failed"] is False
    assert second["finished"] is False
    assert second["percent"] == 40


def test_resume_after_the_book_already_finished_is_a_safe_no_op(monkeypatch):
    monkeypatch.setattr(orch, "_export_files_on_disk", lambda data: True)
    data = _project_data(set(ALL_STAGES), {
        "stages": {}, "finished": True, "failed": False, "customer_message": orch.MSG_READY,
    })
    data["export_ready"] = True
    data["exports"] = {"files": {"pdf": {"url": "/x"}, "zip": {"url": "/y"}}}
    project = _make("Already Done", data)

    status = orch.resume_build(project["id"])

    assert status["failed"] is False
    assert status["finished"] is True


def test_resume_on_an_unknown_project_reports_saved_not_a_crash():
    status = orch.resume_build(999999999)
    assert status["failed"] is True
    assert status["ok"] is False


def test_a_full_build_completes_normally_with_no_stage_run_more_than_once(monkeypatch):
    """Existing successful builds must still complete -- Resume changes nothing here."""
    calls: list[str] = []

    def make_runner(stage):
        def runner(data, pid):
            calls.append(stage)
            data = dict(data)
            if stage == "export":
                data["export_ready"] = True
                data["exports"] = {"files": {"pdf": {"url": "/x"}, "zip": {"url": "/y"}}}
                return data
            ws = dict(data.get("ebook_workspace") or {"rail": _rail(set())})
            rail = dict(ws["rail"])
            rail[stage] = {"id": stage, "status": "approved"}
            ws["rail"] = rail
            data["ebook_workspace"] = ws
            return data
        return runner

    for stage in ALL_STAGES:
        monkeypatch.setitem(orch.STAGE_RUNNERS, stage, make_runner(stage))
    monkeypatch.setattr(orch, "_export_files_on_disk", lambda data: True)

    project = _make("Clean Book", _project_data(set()))
    status = {"finished": False}
    for _ in range(len(ALL_STAGES) + 1):
        if status.get("finished"):
            break
        status = orch.advance_build(project["id"])

    assert status["finished"] is True
    assert status["failed"] is False
    assert calls == list(ALL_STAGES), "every stage must run exactly once, in order"


# ------------------------------------------------------------------ route ---


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_the_resume_route_exists_and_clears_the_stalled_stage(client, monkeypatch):
    project = _make("Route Book", _project_data(
        {"research", "title", "outline"}, _stalled_manuscript_state(),
    ))
    calls: list[str] = []
    monkeypatch.setitem(orch.STAGE_RUNNERS, "manuscript", _spy_runner(calls, "manuscript", {}))

    resp = client.post(f"/ebook/build/{project['id']}/resume")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["failed"] is False
    assert calls == []


def test_the_resume_route_exposes_no_internal_detail(client, monkeypatch):
    project = _make("Route Book", _project_data(
        {"research", "title", "outline"}, _stalled_manuscript_state(),
    ))
    resp = client.post(f"/ebook/build/{project['id']}/resume")
    body = str(resp.get_json()).lower()
    for leak in ("traceback", "openai", "ollama", "qwen", "pexels", "tavily",
                 "api key", "confirmation token", "internal detail"):
        assert leak not in body, f"resume route leaks {leak!r}"


# ------------------------------------------------------- customer wording ---


def _function_body(src: str, name: str) -> str:
    start = src.index(name)
    depth = 0
    seen = False
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
            seen = True
        elif src[i] == "}":
            depth -= 1
            if seen and depth == 0:
                return src[start : i + 1]
    raise AssertionError(f"could not bound {name}")


def _strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", line) for line in src.splitlines())


def test_the_failed_screen_never_says_try_again():
    render = _function_body(APP_JS, "function renderEbookBuild(status)")
    code = _strip_js_comments(render)
    assert "Try again" not in code
    assert "data-ebook-retry" not in code
    assert "Resume Build" in code
    assert "data-ebook-resume" in code
    assert "Make Changes" in code, "the intentional secondary action must remain"


def test_the_resume_button_calls_the_resume_route_not_a_read_only_reopen():
    fn = _function_body(APP_JS, "async function resumeEbookBuild(projectId)")
    assert '/ebook/build/${projectId}/resume' in fn
    assert '"POST"' in fn


def test_the_failed_screen_wiring_uses_resume_not_reopen():
    render = _function_body(APP_JS, "function renderEbookBuild(status)")
    assert "resumeEbookBuild(pid)" in render
    assert "openEbookBuild(pid)" not in render, (
        "reopening only reads status; wiring the button to it recreates the dead end"
    )


def test_starting_the_build_itself_no_longer_says_try_again():
    fn = _function_body(APP_JS, "async function startEbookBuild(fields)")
    assert "Try again" not in fn


def test_the_backend_final_message_matches_the_customer_contract():
    assert orch.MSG_FINAL == "Your project is safely saved. We couldn't complete this step automatically."
    for banned in ("Try again", "traceback", "exception", "API error", "provider error"):
        assert banned.lower() not in orch.MSG_FINAL.lower()


def test_the_resume_route_is_registered_in_app_py():
    assert '"/ebook/build/<int:project_id>/resume"' in APP_PY
    assert "resume_build" in APP_PY


# --------------------------------------------- saved-projects resume list ---
# A separate, pre-existing feature (the manual half-built-workspace resume
# list). This work must not have touched it.


def test_the_unrelated_saved_projects_resume_list_is_untouched():
    assert "list_unfinished_ebook_workspaces" in (ROOT / "database.py").read_text(encoding="utf-8")
    assert "loadEbookResumeList" in APP_JS
    assert "RESUME_STAGE_LABELS" in APP_JS
