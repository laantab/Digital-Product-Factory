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
