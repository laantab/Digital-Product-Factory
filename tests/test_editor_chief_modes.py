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
