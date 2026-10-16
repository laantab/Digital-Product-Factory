"""Opt-in AI rewriting proposals; never calls a provider or mutates books directly.

Callers must explicitly supply a provider function and authorize any billable
usage outside this module. The existing manuscript preview/apply flow remains
the only path that can commit a proposed revision.
"""
from __future__ import annotations

import hashlib
import re
from typing import Callable

MODES = frozenset(("clarity", "shorten", "expand", "professional", "friendly"))
PROTECTED_LINES = re.compile(r"(?m)^(?:#{1,6} |>|\\||```|~~~)")
LINKS = re.compile(r'!?\[[^\]]*\]\([^)]*\)|https?://\S+')


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def proposal(source: str, mode: str, *, provider: Callable[[str], str] | None = None,
             allow_provider: bool = False, allow_paid: bool = False) -> dict:
    """Produce a reversible suggestion, not a saved manuscript.

    The provider adapter is injected by an authorized caller. No API clients,
    network requests, credentials or billing are used here.
    """
    if mode not in MODES:
        raise ValueError("Unsupported rewrite mode.")
    if not isinstance(source, str) or not source.strip() or len(source) > 12000:
        raise ValueError("Select a nonempty passage of at most 12,000 characters.")
    if not allow_provider or provider is None:
        return {"status": "provider_not_authorized", "original": source,
                "proposed": source, "mode": mode, "paid_calls": 0,
                "original_sha256": _hash(source), "requires_review": True}
    if allow_paid:
        raise ValueError("Paid rewrite authorization must be managed by the Factory cost gate.")
    rewritten = provider(source)
    if not isinstance(rewritten, str) or not rewritten.strip():
        raise ValueError("Rewrite provider returned no usable text.")
    if len(rewritten) > 24000:
        raise ValueError("Rewrite exceeds the safety length limit.")
    # Protect structural material and embedded source references.
    original_lines = [line for line in source.splitlines() if PROTECTED_LINES.match(line)]
    proposed_lines = [line for line in rewritten.splitlines() if PROTECTED_LINES.match(line)]
    if original_lines != proposed_lines or LINKS.findall(source) != LINKS.findall(rewritten):
        raise ValueError("Rewrite changed protected headings, quotations, tables or links.")
    return {"status": "review_required", "original": source, "proposed": rewritten,
            "mode": mode, "original_sha256": _hash(source),
            "proposed_sha256": _hash(rewritten), "paid_calls": 0,
            "requires_review": True,
            "disclaimer": "Check factual accuracy and intended meaning before accepting."}
