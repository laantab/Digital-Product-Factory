"""Re-submitting a stage action must be safe and invisible to the customer.

A double click, a refresh, the Back button, or a retried POST after a slow
response used to surface "Confirmation token already used." That is internal
authorization vocabulary and, worse, it looked like a failure when the work had
usually already succeeded.

The confirmation stays single-use -- the security check is NOT removed. What
changed is what happens next: a repeat shows the customer where the project
actually is, never charges twice, and never regenerates accepted work.

No external call is made by any test here.
"""
from __future__ import annotations

import json
import pathlib

import pytest

import app as app_module
from services.ebook_project_workspace import (
    ConfirmationAlreadyUsed,
    consume_confirmation,
    empty_ledger,
    ensure_workspace,
)

APP_JS = pathlib.Path(__file__).resolve().parents[1] / "static" / "js" / "app.js"

FORBIDDEN_CUSTOMER_WORDS = [
    "confirmation token",
    "token already used",
    "token has already",
    "expired token",
    "token has expired",
    "invalid token",
    "invalid or missing confirmation",
    "nonce",
    "csrf",
    "idempotency",
]


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def _used_estimate_data() -> dict:
    """Workspace whose pending confirmation has already been spent."""
    data = ensure_workspace({"product_type": "ebook", "title": "T", "author_brand": "A"})
    ledger = data["ebook_workspace"].setdefault("paid_call_ledger", empty_ledger())
    ledger["pending_estimate"] = {
        "action": "run_research",
        "confirmation_token": "tok-123",
        "used": True,
        "created_at": "2026-09-04T00:00:00+00:00",
        "expires_at": "2099-01-01T00:00:00+00:00",
    }
    return data


# ------------------------------------------------- server keeps the guard ---


def test_single_use_confirmation_is_still_enforced():
    """The security check must not be weakened -- only its consequence changed."""
    with pytest.raises(ConfirmationAlreadyUsed):
        consume_confirmation(_used_estimate_data(), "run_research", "tok-123")


def test_already_used_is_a_distinct_typed_condition():
    """So a re-submission can be told apart from a genuine failure."""
    assert issubclass(ConfirmationAlreadyUsed, ValueError)


def test_wrong_token_is_still_rejected():
    data = _used_estimate_data()
    data["ebook_workspace"]["paid_call_ledger"]["pending_estimate"]["used"] = False
    with pytest.raises(ValueError):
        consume_confirmation(data, "run_research", "not-the-token")


def test_mismatched_action_is_still_rejected():
    data = _used_estimate_data()
    data["ebook_workspace"]["paid_call_ledger"]["pending_estimate"]["used"] = False
    with pytest.raises(ValueError):
        consume_confirmation(data, "generate_manuscript", "tok-123")


# ------------------------------------------- customer never sees the words ---


@pytest.mark.parametrize("phrase", FORBIDDEN_CUSTOMER_WORDS)
def test_token_wording_is_never_returned_to_the_customer(phrase: str):
    safe = app_module.customer_safe_message(
        ValueError("Confirmation token has already been used.")
    )
    assert phrase not in safe.lower()


@pytest.mark.parametrize("raw", [
    "Confirmation token has already been used.",
    "Confirmation token has expired. Request a new cost estimate.",
    "Invalid or missing confirmation token.",
    "Confirmation token was issued for a different artifact.",
    "Confirmation token was issued for a different revision.",
    "Confirmation token outline digest mismatch.",
    "Confirmation does not match the pending paid action.",
])
def test_every_token_error_becomes_plain_language(raw: str):
    safe = app_module.customer_safe_message(ValueError(raw))
    assert safe == "Factory AI could not start. Please try again."
    low = safe.lower()
    for word in FORBIDDEN_CUSTOMER_WORDS:
        assert word not in low


def test_token_wording_is_absent_from_the_browser_bundle():
    js = APP_JS.read_text(encoding="utf-8", errors="replace").lower()
    for phrase in ("confirmation token", "token already used", "nonce", "csrf"):
        assert phrase not in js, f"internal token wording in the UI: {phrase!r}"


# ------------------------------------------------ double submission guard ---


def test_button_is_disabled_and_relabelled_on_first_click():
    js = APP_JS.read_text(encoding="utf-8", errors="replace")
    assert 'btn.dataset.busy === "1"' in js, "repeat clicks are not ignored"
    assert '"Working…"' in js, "the button does not say what it is doing"
    assert "btn.disabled = busy" in js, "the button is not disabled while working"


def test_busy_state_is_restored_so_the_customer_is_not_stuck():
    js = APP_JS.read_text(encoding="utf-8", errors="replace")
    assert "delete btn.dataset.busy" in js
    assert "btn.dataset.idleLabel" in js, "the original label must be restored"


# ---------------------------------------------- resubmission returns state ---


def test_resubmission_helper_returns_the_current_stage_not_an_error(client, monkeypatch):
    """A repeat POST shows where the project is, as success."""
    import database

    created = database.create_project(
        "Resubmit Test", "ebook", _used_estimate_data(),
        user_saved=True, system_test=True, temporary=True,
    )
    pid = created.get("id")

    with app_module.app.test_request_context():
        resp = app_module._resubmitted_stage_action(pid, "run research")
    payload = resp.get_json() if hasattr(resp, "get_json") else resp[0].get_json()

    assert payload["ok"] is True
    assert payload["duplicate"] is True
    assert "workspace" in payload
    blob = json.dumps(payload).lower()
    for word in FORBIDDEN_CUSTOMER_WORDS:
        assert word not in blob, f"token wording leaked to the customer: {word!r}"


def test_resubmission_clears_the_spent_estimate_so_the_next_click_works(client):
    """Consumed-but-incomplete must not wedge the project."""
    import database

    created = database.create_project(
        "Resubmit Clear", "ebook", _used_estimate_data(),
        user_saved=True, system_test=True, temporary=True,
    )
    pid = created.get("id")

    with app_module.app.test_request_context():
        app_module._resubmitted_stage_action(pid, "run research")

    data = (database.get_project(pid) or {}).get("data") or {}
    pending = ((data.get("ebook_workspace") or {}).get("paid_call_ledger") or {}).get("pending_estimate")
    assert not pending, "the spent estimate should be cleared for a clean retry"


def test_resubmission_does_not_charge_again(client):
    """No second charge, no second generation."""
    import database

    data = _used_estimate_data()
    ledger = data["ebook_workspace"]["paid_call_ledger"]
    ledger["spent_usd"] = 0.5
    ledger["paid_calls"] = 2
    created = database.create_project(
        "Resubmit Charge", "ebook", data,
        user_saved=True, system_test=True, temporary=True,
    )
    pid = created.get("id")

    with app_module.app.test_request_context():
        app_module._resubmitted_stage_action(pid, "run research")

    after = (database.get_project(pid) or {}).get("data") or {}
    led = (after.get("ebook_workspace") or {}).get("paid_call_ledger") or {}
    assert float(led.get("spent_usd") or 0) == 0.5, "a repeat must not charge again"
    assert int(led.get("paid_calls") or 0) == 2, "a repeat must not count another call"


def test_resubmission_does_not_regenerate_accepted_chapters(client):
    """Accepted work is never rewritten by a repeat submission."""
    import database

    data = _used_estimate_data()
    data["ebook_workspace"]["accepted_chapters"] = [
        {"order": 1, "title": "One", "body": "kept body one"},
        {"order": 2, "title": "Two", "body": "kept body two"},
    ]
    created = database.create_project(
        "Resubmit Chapters", "ebook", data,
        user_saved=True, system_test=True, temporary=True,
    )
    pid = created.get("id")

    with app_module.app.test_request_context():
        app_module._resubmitted_stage_action(pid, "manuscript generation")

    after = (database.get_project(pid) or {}).get("data") or {}
    kept = (after.get("ebook_workspace") or {}).get("accepted_chapters") or []
    assert [c["body"] for c in kept] == ["kept body one", "kept body two"]


def test_resubmission_does_not_approve_or_lock(client):
    import database
    from services.quality.artifact_state import ArtifactState, resolve_artifact_state

    created = database.create_project(
        "Resubmit State", "ebook", _used_estimate_data(),
        user_saved=True, system_test=True, temporary=True,
    )
    pid = created.get("id")

    with app_module.app.test_request_context():
        app_module._resubmitted_stage_action(pid, "run research")

    after = (database.get_project(pid) or {}).get("data") or {}
    assert resolve_artifact_state(after) == ArtifactState.DRAFT
