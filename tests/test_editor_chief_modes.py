from services.editor_chief_modes import choose_mode, editing_policy
import pytest


def test_automatic_is_default_and_never_authorizes_spending():
    result = editing_policy()
    assert result["mode"] == "automatic"
    assert result["automatic_proofreading"]
    assert result["publishing_quality_gate_required"]
    assert result["preserve_previous_exports"]
    assert not result["paid_ai_authorized"]


def test_manual_keeps_quality_gate_and_requires_acceptance():
    result = editing_policy("manual")
    assert not result["automatic_proofreading"]
    assert result["manual_acceptance_required"]
    assert result["publishing_quality_gate_required"]


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        choose_mode("auto-pay")


def test_automatic_button_uses_existing_resume_route_without_new_paid_api():
    from pathlib import Path
    template = (Path(__file__).resolve().parents[1] / 'templates' / 'ebook_manuscript_editor.html').read_text()
    assert 'id="auto-continue"' in template
    assert "fetch('/ebook/build/{{ project_id }}/resume',{method:'POST'})" in template
    assert 'Required approvals and quality checks still apply.' in template
    assert 'https://api.' not in template


def test_editor_mode_saves_to_ebook_project_without_touching_exports(monkeypatch):
    import database
    from app import app
    from services.jobs import store
    database.init_db()
    store.init_jobs_table()
    project = database.create_project("Mode persistence test", "ebook", {"product_type": "ebook", "content": "# Draft\\n\\nText."})
    pid = project["id"]
    monkeypatch.setattr("services.jobs.store.get_for_project", lambda _pid: None)
    app.config.update(TESTING=True)
    response = app.test_client().post(
        f"/ebook-workspace/{pid}/edit-manuscript",
        json={"action": "set_mode", "mode": "manual"},
    )
    assert response.status_code == 200
    assert response.get_json()["policy"]["manual_acceptance_required"] is True
    saved = database.get_project(pid)["data"]
    assert saved["editor_chief_mode"] == "manual"
    assert "export_pdf" not in saved
    again = app.test_client().get(f"/ebook-workspace/{pid}/edit-manuscript")
    assert again.status_code == 200
    assert b'value="manual" checked' in again.data


def test_editor_mode_cannot_change_while_job_is_running(monkeypatch):
    import database
    from app import app
    project = database.create_project("Active mode test", "ebook", {"product_type": "ebook", "content": "# Draft\\n\\nText."})
    pid = project["id"]
    monkeypatch.setattr("services.jobs.store.get_for_project", lambda _pid: {"status": "RUNNING"})
    app.config.update(TESTING=True)
    result = app.test_client().post(f"/ebook-workspace/{pid}/edit-manuscript",
        json={"action": "set_mode", "mode": "manual"})
    assert result.status_code == 409
    assert database.get_project(pid)["data"].get("editor_chief_mode") is None
