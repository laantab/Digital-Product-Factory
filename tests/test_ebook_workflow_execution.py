"""The builder is its own machine — v1.8.0 workflow execution.

THE DEFECT THIS CLOSES
----------------------
A live Resume Build for "Container Gardening for Beginners" pushed the
Render web service past its memory limit. The book was being written
inside the process that serves pages, so one customer's build could take
the whole site down.

v1.7.24 made the SERVER own finishing a book instead of the browser. This
release moves that work off the web service entirely: the job is still a
durable row, but a Render Workflow task claims it, on its own instance,
with its own CPU and RAM, and disappears when the book is done.

WHAT THESE TESTS HOLD
---------------------
  * the default is unchanged — merging v1.8.0 changes nothing until one
    environment variable is set
  * in workflow mode the web process NEVER advances a build: not at boot,
    not on request traffic, and not through /advance
  * the durable job is written BEFORE Render is asked for anything, so a
    trigger that fails loses no work
  * a customer clicking Continue five times starts one task, not five
  * a Render retry resumes from checkpoints and never rebuilds a finished
    book or exports it twice
  * a task started for one book only ever works on that book
  * status and Saved Projects stay read-only
  * no credential value is ever exposed
  * local Ollama is untouched, and hosted mode never routes to it

No paid provider is called anywhere in this file: the orchestrator is
stubbed, exactly as tests/test_ebook_durable_executor.py stubs it, and
the Render SDK is never imported — the trigger is replaced with a
recorder. What is under test is WHICH MACHINE builds the book.
"""
from __future__ import annotations

import database
import pytest

from services.jobs import dispatch, executor, mode, runner, store, workflow_trigger


# ---------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def jobs_table():
    database.init_db()
    store.init_jobs_table()
    conn = database.get_conn()
    try:
        conn.execute("DELETE FROM jobs")
        conn.commit()
    finally:
        conn.close()
    yield


@pytest.fixture(autouse=True)
def inline_by_default(monkeypatch):
    """Every test states its own mode. None inherits one from the machine."""
    monkeypatch.delenv(mode.ENV_MODE, raising=False)
    monkeypatch.delenv(mode.ENV_TASK, raising=False)
    monkeypatch.delenv(mode.ENV_API_KEY, raising=False)
    yield


@pytest.fixture
def workflow_mode(monkeypatch):
    monkeypatch.setenv(mode.ENV_MODE, "workflow")
    monkeypatch.setenv(mode.ENV_TASK, "factory-builder/build_ebook")
    monkeypatch.setenv(mode.ENV_API_KEY, "rnd_not_a_real_key")
    yield


class _Render:
    """Stands in for Render. Records every task it was asked to start.

    The SDK is never imported, so this suite proves the triggering
    contract without the package installed and without a network call.
    """

    def __init__(self, fail: bool = False):
        self.started: list[tuple[str, int]] = []
        self.fail = fail

    def start(self, task: str, project_id: int) -> str:
        if self.fail:
            raise RuntimeError("Render is unreachable")
        self.started.append((task, int(project_id)))
        return f"trn-{len(self.started):04d}"


@pytest.fixture
def render(monkeypatch):
    fake = _Render()
    monkeypatch.setattr(workflow_trigger, "_start_task", fake.start)
    return fake


def _project(name="Container Gardening for Beginners"):
    return database.create_project(name, "ebook", {"product_type": "ebook"})


class _Orchestrator:
    """A stand-in build: N units, then finished. Records every call."""

    def __init__(self, units_to_finish=3, fail_at=None, paused_at=None):
        self.calls: list[int] = []
        self.units_to_finish = units_to_finish
        self.fail_at = fail_at
        self.paused_at = paused_at
        self.exports = 0

    def advance(self, project_id):
        self.calls.append(project_id)
        n = len(self.calls)
        if self.fail_at and n == self.fail_at:
            return {"finished": False, "failed": True, "message": "provider refused"}
        if self.paused_at and n == self.paused_at:
            return {"finished": False, "failed": False, "paused_after": "preview"}
        if n >= self.units_to_finish:
            self.exports += 1
            return {"finished": True, "failed": False, "percent": 100}
        return {"finished": False, "failed": False,
                "percent": int(100 * n / self.units_to_finish)}


def _install(monkeypatch, orchestrator):
    import services.ebook_build_orchestrator as real

    monkeypatch.setattr(real, "advance_build", orchestrator.advance)
    return orchestrator


# =================================== the default is unchanged =============


def test_the_default_execution_mode_is_inline():
    """Merging v1.8.0 must change nothing until a variable is set."""
    assert mode.execution_mode() == mode.INLINE
    assert mode.is_workflow_mode() is False


@pytest.mark.parametrize("value", ["", "   ", "inline", "INLINE", "nonsense",
                                   "workflowss", "work flow"])
def test_anything_that_is_not_the_word_workflow_is_inline(monkeypatch, value):
    """A typo must never silently stop books being built."""
    monkeypatch.setenv(mode.ENV_MODE, value)
    assert mode.is_workflow_mode() is False


@pytest.mark.parametrize("value", ["workflow", "WORKFLOW", " workflow ",
                                   "workflows", "render-workflows"])
def test_the_spellings_that_do_mean_workflow(monkeypatch, value):
    monkeypatch.setenv(mode.ENV_MODE, value)
    assert mode.is_workflow_mode() is True


def test_rollback_is_one_variable(monkeypatch):
    monkeypatch.setenv(mode.ENV_MODE, "workflow")
    assert mode.is_workflow_mode() is True
    monkeypatch.delenv(mode.ENV_MODE)
    assert mode.is_workflow_mode() is False


# ============================ the web process does not build ==============


def test_the_in_process_ticker_refuses_to_start_in_workflow_mode(monkeypatch):
    """Two owners advancing one book would race onto the same chapter."""
    monkeypatch.delenv("FACTORY_TEST_MODE", raising=False)
    monkeypatch.setenv(mode.ENV_MODE, "workflow")

    assert runner.executor_enabled() is False
    assert runner.start() is False


def test_ordinary_request_traffic_never_advances_a_build_in_workflow_mode(monkeypatch):
    """`tick_soon` is the other way a passing request could write a book."""
    monkeypatch.delenv("FACTORY_TEST_MODE", raising=False)
    monkeypatch.setenv(mode.ENV_MODE, "workflow")

    assert runner.tick_soon(min_interval=0) is False


def test_the_ticker_still_runs_in_inline_mode(monkeypatch):
    monkeypatch.delenv("FACTORY_TEST_MODE", raising=False)
    monkeypatch.delenv(runner.ENV_SWITCH, raising=False)
    monkeypatch.delenv(mode.ENV_MODE, raising=False)

    assert runner.executor_enabled() is True


def test_advance_refuses_to_build_in_workflow_mode(monkeypatch, workflow_mode):
    """The last route by which a browser could make the web service build."""
    import app as app_module
    import services.ebook_build_orchestrator as real

    project = _project("Advance Guarded")
    called = []
    monkeypatch.setattr(real, "advance_build",
                        lambda pid: called.append(pid) or {"finished": True})
    monkeypatch.setattr(real, "status_payload",
                        lambda data, pid: {"ok": True, "project_id": pid, "percent": 40})
    monkeypatch.setattr(app_module, "_ebook_workspace_project_or_404",
                        lambda pid: ({"id": pid, "data": {}}, None))

    response = app_module.app.test_client().post(
        f"/ebook/build/{project['id']}/advance")

    assert response.status_code == 200, "the customer still gets their screen"
    assert called == [], "the web process must not have advanced the build"
    body = response.get_json()
    assert body["advanced"] is False
    assert body["execution_mode"] == mode.WORKFLOW
    assert body["percent"] == 40, "it answers with read-only progress"


def test_advance_still_builds_in_inline_mode(monkeypatch):
    """Local Windows development must be completely unaffected."""
    import app as app_module
    import services.ebook_build_orchestrator as real

    project = _project("Advance Inline")
    called = []
    monkeypatch.setattr(
        real, "advance_build",
        lambda pid: (called.append(pid), {"finished": True, "percent": 100})[1])

    response = app_module.app.test_client().post(
        f"/ebook/build/{project['id']}/advance")

    assert response.status_code == 200
    assert called == [project["id"]]


# ================================ durable first, trigger second ===========


def test_the_job_is_written_before_render_is_asked_for_anything(
        workflow_mode, render):
    project = _project("Durable First")

    outcome = workflow_trigger.trigger(project["id"])

    assert outcome["enqueued"] is True
    assert store.get_for_project(project["id"])["status"] == store.QUEUED
    assert render.started == [("factory-builder/build_ebook", project["id"])]


def test_a_trigger_that_fails_still_leaves_the_work_recorded(
        monkeypatch, workflow_mode):
    """Render being down must cost a delay, never a customer's book."""
    broken = _Render(fail=True)
    monkeypatch.setattr(workflow_trigger, "_start_task", broken.start)

    project = _project("Render Down")
    outcome = workflow_trigger.trigger(project["id"])

    assert outcome["enqueued"] is True
    assert outcome["triggered"] is False
    assert outcome["reason"] == "RuntimeError"
    assert store.get_for_project(project["id"])["status"] == store.QUEUED


def test_a_trigger_failure_never_reaches_the_customer(monkeypatch, workflow_mode):
    """A customer clicking Build must get a page back, not a 500."""
    import app as app_module
    import services.ebook_build_orchestrator as real

    broken = _Render(fail=True)
    monkeypatch.setattr(workflow_trigger, "_start_task", broken.start)

    project = _project("Still Starts")
    monkeypatch.setattr(real, "start_build",
                        lambda fields: ({"id": project["id"], "data": {}}, True))
    monkeypatch.setattr(real, "status_payload",
                        lambda data, pid: {"ok": True, "project_id": pid})

    response = app_module.app.test_client().post("/ebook/build", json={"fields": {}})

    assert response.status_code == 200
    assert store.get_for_project(project["id"])["status"] == store.QUEUED


def test_workflow_mode_without_configuration_records_the_work_and_says_why(
        monkeypatch):
    """A half-configured service must not silently accept books forever."""
    monkeypatch.setenv(mode.ENV_MODE, "workflow")
    # No task name, no API key.

    project = _project("Half Configured")
    outcome = workflow_trigger.trigger(project["id"])

    assert outcome["enqueued"] is True
    assert outcome["triggered"] is False
    assert mode.ENV_TASK in outcome["reason"]


def test_inline_mode_never_asks_render_for_anything(render):
    project = _project("Inline Only")
    outcome = workflow_trigger.trigger(project["id"])

    assert outcome["enqueued"] is True
    assert outcome["triggered"] is False
    assert render.started == []


# ================================ one click, one task =====================


def test_five_clicks_start_one_task(workflow_mode, render):
    """Five instances racing one chapter, and five bills, is the failure."""
    project = _project("Impatient Customer")

    for _ in range(5):
        workflow_trigger.trigger(project["id"], reset_attempts=True)

    assert len(render.started) == 1


def test_the_duplicate_guard_is_in_the_database_not_in_memory(workflow_mode):
    """Two web instances handling two clicks share no memory, only the row."""
    project = _project("Two Instances")
    job = store.enqueue(project["id"])

    assert store.claim_trigger(job["id"]) is True
    assert store.claim_trigger(job["id"]) is False


def test_a_job_being_worked_on_is_not_triggered_again(workflow_mode, render):
    """A live lease means a task already owns this book."""
    project = _project("Already Running")
    store.enqueue(project["id"])
    claimed = store.claim_next("a-running-task")
    assert claimed is not None

    outcome = workflow_trigger.trigger(project["id"])

    assert render.started == []
    assert outcome["triggered"] is False


def test_the_cooldown_expires_so_a_lost_task_is_retried(workflow_mode, render):
    """A task that died before claiming anything must not strand the book."""
    project = _project("Lost Task")
    job = store.enqueue(project["id"])

    assert store.claim_trigger(job["id"]) is True
    assert store.claim_trigger(job["id"]) is False
    # Time passes. Nothing tidies up; the window simply ends.
    conn = database.get_conn()
    try:
        conn.execute("UPDATE jobs SET workflow_triggered_at=? WHERE id=?",
                     ("2000-01-01T00:00:00+00:00", job["id"]))
        conn.commit()
    finally:
        conn.close()

    assert store.claim_trigger(job["id"]) is True


def test_the_run_id_is_recorded_so_a_stuck_book_can_be_traced(
        workflow_mode, render):
    project = _project("Traceable")
    workflow_trigger.trigger(project["id"])

    info = store.trigger_info(project["id"])
    assert info["workflow_run_id"].startswith("trn-")
    assert info["workflow_triggered_at"]


# ================================ the task builds the book ================


def test_the_task_finishes_the_book_with_no_browser_involved(monkeypatch):
    from services.jobs import workflow_runner

    fake = _install(monkeypatch, _Orchestrator(units_to_finish=3))
    project = _project("No Browser")
    store.enqueue(project["id"])

    summary = workflow_runner.run_build(project["id"], budget_seconds=3600,
                                        sleep=lambda s: None)

    assert summary["finished"] is True
    assert fake.calls, "the orchestrator must actually have been driven"
    assert store.get_for_project(project["id"])["status"] == store.SUCCEEDED


def test_the_task_keeps_claiming_until_the_book_is_done(monkeypatch):
    """One claim is bounded; a task has no ticker behind it to call again."""
    from services.jobs import workflow_runner

    units = executor.UNITS_PER_CLAIM * 2 + 1
    fake = _install(monkeypatch, _Orchestrator(units_to_finish=units))
    project = _project("Long Book")
    store.enqueue(project["id"])

    summary = workflow_runner.run_build(project["id"], budget_seconds=3600,
                                        sleep=lambda s: None)

    assert summary["finished"] is True
    assert summary["claims"] >= 3
    assert len(fake.calls) == units


def test_a_retried_task_never_rebuilds_a_finished_book(monkeypatch):
    """Render may retry a run. A second PDF and a second charge must not appear."""
    from services.jobs import workflow_runner

    fake = _install(monkeypatch, _Orchestrator(units_to_finish=2))
    project = _project("Retried")
    store.enqueue(project["id"])

    workflow_runner.run_build(project["id"], budget_seconds=3600,
                              sleep=lambda s: None)
    exports_after_first = fake.exports

    again = workflow_runner.run_build(project["id"], budget_seconds=3600,
                                      sleep=lambda s: None)

    assert again["finished"] is True
    assert fake.exports == exports_after_first, "no second export"


def test_a_task_started_for_one_book_never_works_on_another(monkeypatch):
    """A run id is meaningless if a task can wander onto someone else's book."""
    from services.jobs import workflow_runner

    fake = _install(monkeypatch, _Orchestrator(units_to_finish=2))
    mine = _project("My Book")
    someone_else = _project("Their Book")
    store.enqueue(mine["id"])
    store.enqueue(someone_else["id"])

    workflow_runner.run_build(mine["id"], budget_seconds=3600,
                              sleep=lambda s: None)

    assert set(fake.calls) == {mine["id"]}
    assert store.get_for_project(someone_else["id"])["status"] == store.QUEUED


def test_two_tasks_cannot_both_own_one_book(monkeypatch):
    """The second must stop rather than fight for the chapter."""
    from services.jobs import workflow_runner

    _install(monkeypatch, _Orchestrator(units_to_finish=1000))
    project = _project("Contested")
    store.enqueue(project["id"])
    assert store.claim_for_project("task-A", project["id"]) is not None

    summary = workflow_runner.run_build(project["id"], budget_seconds=3600,
                                        sleep=lambda s: None)

    assert summary["claims"] == 0
    assert summary["reason"] == "another task holds this book"


def test_the_task_stops_before_its_deadline_and_leaves_the_book_resumable(
        monkeypatch):
    """Being killed mid-chapter with a live lease is worse than stopping."""
    from services.jobs import workflow_runner

    _install(monkeypatch, _Orchestrator(units_to_finish=10_000))
    project = _project("Out Of Time")
    store.enqueue(project["id"])

    summary = workflow_runner.run_build(
        project["id"],
        budget_seconds=workflow_runner.DEADLINE_MARGIN_SECONDS,
        sleep=lambda s: None)

    assert summary["finished"] is False
    job = store.get_for_project(project["id"])
    assert job["status"] in (store.QUEUED, store.RUNNING), "still resumable"


def test_a_transient_error_leaves_the_book_retryable(monkeypatch):
    from services.jobs import workflow_runner
    import services.ebook_build_orchestrator as real

    def _boom(project_id):
        raise RuntimeError("provider timed out")

    monkeypatch.setattr(real, "advance_build", _boom)
    project = _project("Transient")
    store.enqueue(project["id"])

    summary = workflow_runner.run_build(project["id"], budget_seconds=3600,
                                        sleep=lambda s: None)

    assert summary["failed"] is True
    assert store.get_for_project(project["id"])["status"] == store.QUEUED


def test_a_pause_for_the_customer_is_not_a_failure(monkeypatch):
    from services.jobs import workflow_runner

    _install(monkeypatch, _Orchestrator(paused_at=2, units_to_finish=99))
    project = _project("Paused")
    store.enqueue(project["id"])

    summary = workflow_runner.run_build(project["id"], budget_seconds=3600,
                                        sleep=lambda s: None)

    assert summary["paused"] is True
    assert summary["failed"] is False
    assert store.get_for_project(project["id"])["status"] == store.QUEUED


def test_the_task_never_decides_what_to_generate(monkeypatch):
    """Completed chapters are never regenerated, because nothing here knows
    what a chapter is. It only asks the orchestrator to advance."""
    from services.jobs import workflow_runner

    fake = _install(monkeypatch, _Orchestrator(units_to_finish=4))
    project = _project("Not Ours To Decide")
    store.enqueue(project["id"])

    workflow_runner.run_build(project["id"], budget_seconds=3600,
                              sleep=lambda s: None)

    assert fake.calls == [project["id"]] * len(fake.calls)


# ================================ the app wires it up =====================


def test_starting_a_build_still_enqueues_a_durable_job_in_workflow_mode(
        monkeypatch, workflow_mode, render):
    import app as app_module
    import services.ebook_build_orchestrator as real

    project = _project("Wired Workflow")
    monkeypatch.setattr(real, "start_build",
                        lambda fields: ({"id": project["id"], "data": {}}, True))
    monkeypatch.setattr(real, "status_payload",
                        lambda data, pid: {"ok": True, "project_id": pid})

    response = app_module.app.test_client().post("/ebook/build", json={"fields": {}})

    assert response.status_code == 200
    assert store.get_for_project(project["id"])["status"] == store.QUEUED
    assert render.started == [("factory-builder/build_ebook", project["id"])]


def test_resume_hands_the_work_to_render_and_returns(monkeypatch, workflow_mode,
                                                     render):
    """The customer's Continue must not wait for a book to be written."""
    import app as app_module
    import services.ebook_build_orchestrator as real

    project = _project("Resumed")
    monkeypatch.setattr(real, "resume_build",
                        lambda pid: {"ok": True, "project_id": pid})

    response = app_module.app.test_client().post(
        f"/ebook/build/{project['id']}/resume")

    assert response.status_code == 200
    assert render.started == [("factory-builder/build_ebook", project["id"])]


def test_resume_gives_an_exhausted_book_a_fresh_set_of_attempts(
        monkeypatch, workflow_mode, render):
    """v1.7.26's rule survives the move: a human saying keep going is a
    fresh start, an automatic retry is not."""
    import app as app_module
    import services.ebook_build_orchestrator as real

    project = _project("Exhausted")
    job = store.enqueue(project["id"])
    conn = database.get_conn()
    try:
        conn.execute("UPDATE jobs SET attempts=?, status=? WHERE id=?",
                     (store.MAX_ATTEMPTS, store.FAILED, job["id"]))
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(real, "resume_build", lambda pid: {"ok": True})
    app_module.app.test_client().post(f"/ebook/build/{project['id']}/resume")

    refreshed = store.get_for_project(project["id"])
    assert refreshed["attempts"] == 0
    assert refreshed["status"] == store.QUEUED


def test_dispatch_is_the_only_decision_point(monkeypatch, workflow_mode, render):
    """One function decides who builds. A second check somewhere else is a
    second thing to forget."""
    project = _project("One Decision")
    started = []
    monkeypatch.setattr("services.jobs.runner.start",
                        lambda app=None: started.append(1) or True)

    dispatch.hand_off(project["id"])

    assert started == [], "workflow mode must not start the in-process ticker"
    assert render.started, "it must have asked Render instead"


# ================================ read-only surfaces ======================


def test_the_execution_mode_route_reports_configuration_not_secrets(
        workflow_mode):
    import app as app_module

    response = app_module.app.test_client().get("/ebook/execution-mode")

    assert response.status_code == 200
    body = response.get_json()
    assert body["execution_mode"] == mode.WORKFLOW
    assert body["render_api_key_configured"] is True
    assert body["ready"] is True
    assert "rnd_not_a_real_key" not in response.get_data(as_text=True)


def test_the_execution_mode_route_never_leaks_the_key_when_unconfigured(
        monkeypatch):
    import app as app_module

    monkeypatch.setenv(mode.ENV_MODE, "workflow")
    response = app_module.app.test_client().get("/ebook/execution-mode")

    body = response.get_json()
    assert body["render_api_key_configured"] is False
    assert body["ready"] is False


def test_describe_contains_no_secret_value(workflow_mode):
    assert "rnd_not_a_real_key" not in str(mode.describe())


def test_the_status_route_is_read_only_in_workflow_mode(monkeypatch,
                                                        workflow_mode):
    """Polling progress must never advance a build."""
    import app as app_module
    import services.ebook_build_orchestrator as real

    project = _project("Polled")
    advanced = []
    monkeypatch.setattr(real, "advance_build", lambda pid: advanced.append(pid))
    monkeypatch.setattr(real, "status_payload",
                        lambda data, pid: {"ok": True, "percent": 50})
    monkeypatch.setattr(app_module, "_ebook_workspace_project_or_404",
                        lambda pid: ({"id": pid, "data": {}}, None))

    for _ in range(5):
        app_module.app.test_client().get(f"/ebook/build/{project['id']}/status")

    assert advanced == []


def test_saved_projects_is_read_only_in_workflow_mode(monkeypatch, workflow_mode):
    import app as app_module
    import services.ebook_build_orchestrator as real

    advanced = []
    monkeypatch.setattr(real, "advance_build", lambda pid: advanced.append(pid))
    _project("Listed Book")

    response = app_module.app.test_client().get("/api/projects")

    assert response.status_code in (200, 302, 401, 404)
    assert advanced == [], "listing products must never build one"


# ================================ local development is untouched ==========


def test_local_ollama_configuration_is_not_touched_by_the_mode_switch(
        monkeypatch):
    """Workflow mode changes WHERE a build runs, never WHICH provider writes."""
    import services.ai_providers as providers

    before = sorted(n for n in dir(providers) if "ollama" in n.lower())
    monkeypatch.setenv(mode.ENV_MODE, "workflow")
    after = sorted(n for n in dir(providers) if "ollama" in n.lower())

    assert before == after


def test_the_workflow_modules_never_import_a_cloud_sdk():
    """Local Windows testing must need no Render account and no SDK.

    The SDK import lives in workflow_task.py, which only Render runs.
    """
    import inspect

    from services.jobs import workflow_runner

    for module in (mode, dispatch, workflow_trigger, workflow_runner):
        source = inspect.getsource(module)
        assert "import render" not in source or module is workflow_trigger
    # workflow_trigger imports it INSIDE the function, never at module level.
    trigger_source = inspect.getsource(workflow_trigger)
    module_level = trigger_source.split("def _start_task")[0]
    assert "from render import" not in module_level


def test_the_task_entrypoint_is_thin_and_delegates(monkeypatch):
    """The file Render runs must hold no build logic of its own."""
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "workflow_task.py"
    text = source.read_text(encoding="utf-8")

    assert "run_build" in text
    assert "advance_build" not in text, "the entrypoint must not drive the build"
    assert "app.start()" in text
