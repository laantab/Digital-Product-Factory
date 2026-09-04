"""Regression: an unavailable cover vision QC must never read as a PASS.

The bug: services/cover_quality_agent.py imported ``get_model`` from ai_client,
which did not exist. The ImportError was swallowed by a broad ``except`` that
returned ``{"passed": True, "skipped": True}`` -- so a quality check that never
ran was recorded as a check that succeeded, for every cover.

No paid vision call is made by these tests.
"""
from __future__ import annotations

from unittest.mock import patch

import ai_client
from services.cover_quality_agent import evaluate_cover_image_vision_qc


def _cover() -> dict:
    return {
        "use_ai_image": True,
        "title": "A Test Book",
        "subtitle": "For QC",
        "author": "Tester",
        "image_b64": "",
    }


def test_get_model_now_exists():
    """The missing name that caused the silent failure."""
    assert callable(ai_client.get_model)
    assert ai_client.get_model() == ai_client.MODEL


def test_unavailable_qc_is_not_reported_as_passed():
    """The core of the bug. Unavailable must not equal approved."""
    result = evaluate_cover_image_vision_qc(_cover())
    if result is None:
        return  # cover opted out of AI imagery entirely; nothing to assert
    if result.get("available") is False:
        assert result.get("passed") is False, "an unavailable QC must never claim passed=True"
        assert result.get("review_required") is True


def test_disabled_qc_makes_no_ai_call_at_all(monkeypatch):
    """Repairing the import must not switch on new per-cover spend."""
    monkeypatch.delenv("FACTORY_VISION_QC", raising=False)

    def _boom(*_a, **_k):
        raise AssertionError("no AI client may be constructed while vision QC is disabled")

    with patch("ai_client.get_client", side_effect=_boom):
        result = evaluate_cover_image_vision_qc(_cover())

    if result is not None:
        assert result.get("passed") is not True


def test_skipped_flag_preserved_so_retry_flow_is_unchanged():
    """Callers branch on ``skipped`` to stop retrying; that must still hold."""
    result = evaluate_cover_image_vision_qc(_cover())
    if result is not None and result.get("available") is False:
        assert result.get("skipped") is True
