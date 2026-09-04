"""The ebook workspace must never show internal operating costs or providers.

A customer buys a finished product. What the Factory spends to make it, which
provider wrote a chapter, and how the internal budget is tracked are the
owner's business, not the customer's. Those must not appear in the ebook
building interface -- not in panels, buttons, progress notes, tooltips or
error text.

Server-side budget enforcement, internal spend tracking and audit logging are
deliberately NOT relaxed; only the customer-visible display is.

Scope note: these assertions target the ebook workspace renderer specifically.
Words like "remaining" and "cap" are legitimate in ordinary book content, so
this file checks the internal-cost DISPLAY, not the whole file.
"""
from __future__ import annotations

import pathlib
import re

import pytest

APP_JS = pathlib.Path(__file__).resolve().parents[1] / "static" / "js" / "app.js"


@pytest.fixture(scope="module")
def js() -> str:
    return APP_JS.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def workspace_js(js: str) -> str:
    """Only the ebook workspace renderer and its confirmation panels."""
    start = js.index("function renderEbookWorkspace") if "function renderEbookWorkspace" in js else 0
    # Everything from the workspace renderer through the estimate panels.
    end = js.index("async function estimateManuscriptInWorkspace")
    tail_end = js.index("\n}", end)
    return js[start:tail_end]


# ------------------------------------------------- forbidden cost display ---


FORBIDDEN_EXACT = [
    "Confirm paid action",
    "Confirm and Run Research",
    "Confirm and Generate Manuscript",
    "Maximum total",
    "paid calls",
    "paid call",
    "cost estimate",
    "Nothing is spent",
    "No paid calls",
]


@pytest.mark.parametrize("phrase", FORBIDDEN_EXACT)
def test_internal_cost_phrases_are_absent(js: str, phrase: str):
    assert phrase not in js, f"customer-visible internal-cost phrase still present: {phrase!r}"


def test_ledger_box_is_gone(js: str):
    """The Spend / Remaining / Cap / paid-calls box must not render."""
    assert "budget.spent_usd" not in js
    assert "budget.remaining_usd" not in js
    assert "budget.cap_usd" not in js
    assert "budget.paid_calls" not in js


def test_estimate_panels_do_not_render_money(js: str):
    """No internal ledger figure is rendered into customer-visible markup.

    Checked against the rendered template strings rather than the whole file:
    the values may still be READ from the server response (the client needs
    the confirmation token from the same payload), but none may be printed.
    """
    money_in_markup = re.findall(
        r'<p[^>]*>[^`]{0,120}\$\$\{Number\(est\.(spent_usd|remaining_usd|budget_cap_usd|'
        r'max_total_usd|estimated_max_usd|per_chapter_max_usd)',
        js,
    )
    assert not money_in_markup, f"internal cost still printed to the customer: {money_in_markup}"

    for banned in ("budget.spent_usd", "budget.remaining_usd",
                   "budget.cap_usd", "budget.paid_calls"):
        assert banned not in js, f"ledger box value still rendered: {banned}"


def test_no_ai_provider_or_model_names_in_the_ebook_workspace(workspace_js: str):
    """No AI provider, model or key language in the ebook workspace.

    Pexels is deliberately excluded from this list. It is a stock-photo
    library, not an AI provider, and its name appears only as photo
    attribution ("Free photo from Pexels" plus a link to the photo page),
    which the Pexels licence requires and which is honest sourcing for the
    customer. Stripping it would be a licensing problem, not a privacy win.
    Internal COST language about Pexels is still forbidden and is covered by
    the cost assertions above.
    """
    low = workspace_js.lower()
    for name in ("openai", "tavily", "ollama", "qwen", "gpt-", "api key", "api cost"):
        assert name not in low, f"provider/model name visible in ebook workspace: {name!r}"


def test_pexels_appears_only_as_photo_attribution(js: str):
    """Guard the exception: Pexels may be credited, never billed about."""
    for banned in ("Pexels call", "Pexels cost", "paid Pexels", "Pexels credits"):
        assert banned not in js, f"internal Pexels cost language present: {banned!r}"


def test_customer_facing_action_wording_is_plain(js: str):
    """The customer sees an ordinary next step, not an internal approval."""
    assert "Prepare My Ebook" in js or "Continue Building" in js


# --------------------------------------------- server side is NOT relaxed ---


def test_server_still_requires_a_confirmation_token():
    """Removing the panel must not remove the server-side gate."""
    ws = (pathlib.Path(__file__).resolve().parents[1]
          / "services" / "ebook_project_workspace.py").read_text(encoding="utf-8", errors="replace")
    assert "confirmation_token" in ws
    assert "RESEARCH_AUTH_MAX_USD" in ws
    assert "MANUSCRIPT_AUTH_MAX_USD" in ws


def test_internal_spend_tracking_is_preserved():
    ws = (pathlib.Path(__file__).resolve().parents[1]
          / "services" / "ebook_project_workspace.py").read_text(encoding="utf-8", errors="replace")
    for marker in ("spent_usd", "remaining_usd", "budget_cap_usd", "paid_calls"):
        assert marker in ws, f"internal cost tracking lost: {marker}"


def test_budget_enforcement_still_raises():
    """The authorization ceiling must still be enforced server side."""
    ws = (pathlib.Path(__file__).resolve().parents[1]
          / "services" / "ebook_project_workspace.py").read_text(encoding="utf-8", errors="replace")
    assert re.search(r"authorization exceeds", ws), "budget ceiling check missing"


def test_safe_mode_external_call_block_is_intact():
    ec = (pathlib.Path(__file__).resolve().parents[1]
          / "services" / "external_calls.py").read_text(encoding="utf-8", errors="replace")
    assert "ExternalCallBlocked" in ec
    assert "assert_external_call_allowed" in ec


def test_removing_the_panel_did_not_auto_approve_anything(js: str):
    """No approval or lock may be implied by the display change."""
    assert "artifact_state" not in js or "LOCKED" not in js.split("renderEbookWorkspace")[-1][:4000]


# ------------------------------------------------- other builders untouched ---


def test_coloring_book_builder_was_not_modified(js: str):
    """Reported separately; deliberately NOT changed by this correction."""
    assert "_renderColoringApprovalPanel" in js, "coloring book panel must remain"
