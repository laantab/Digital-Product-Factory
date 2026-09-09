"""Run a whole Ebook Project from one authorization instead of ten clicks.

The workspace was built as ten gated stages, each with its own button, its own
estimate and its own approval. That is right for *safety* and wrong for a
first-time author, who has to click through Research → Title → Outline →
Manuscript → Visuals → Cover → Design → Preview → Preflight → Export to get one
book. Lonnie's note: "I don't think the user should have to keep clicking a
dam button to complete a project... we should be able to do this with one
click."

So this module automates the *clicking*, never the *gates*:

* Every stage still runs through the same executor and the same
  ``approve_stage`` it always did, so a stage whose quality gate fails is still
  refused — it simply stops the run and reports why, instead of quietly
  approving weak work (FACTORY_BLUEPRINT.md §7).
* Spending is authorized once, up front, with a stated maximum, and every paid
  step is still charged through the existing per-project ledger and its cap
  (§13). The run stops rather than exceeding what was authorized.
* Nothing is destructive: it only ever moves stages forward, and a stage that
  is already approved is skipped rather than rebuilt (§10).
* If a step genuinely needs a human decision, the run stops cleanly on that
  stage with a plain-language reason and everything completed so far is kept.

The result is one click for the common case, and an honest stop for the rest.
"""
from __future__ import annotations

from typing import Any, Callable

from services import progress_tracker
from services.ebook_project_workspace import (
    CHAPTER_UNIT_USD,
    DEFAULT_BUDGET_CAP_USD,
    PAID_ACTIONS,
    STATUS_APPROVED,
    STATUS_AWAITING,
    STATUS_NEEDS_CORRECTION,
    apply_draft_outline,
    approve_stage,
    chapter_pipeline_stats,
    ensure_workspace,
    estimate_paid_action,
    execute_correct_manuscript,
    execute_generate_manuscript,
    execute_run_research,
    is_approved,
    stage_status,
)

# The order the Factory produces a book in. Same rail the UI shows.
BUILD_STAGES = (
    "research",
    "title",
    "outline",
    "manuscript",
    "visuals",
    "cover",
    "design",
    "preview",
    "preflight",
)

# Plain-language names for what the customer sees while it runs.
STAGE_RUNNING_LABEL = {
    "research": "Researching your topic",
    "title": "Setting your title",
    "outline": "Planning your chapters",
    "manuscript": "Writing your chapters",
    "visuals": "Adding images to your chapters",
    "cover": "Designing your cover",
    "design": "Laying out your book",
    "preview": "Building your preview",
    "preflight": "Running final checks",
}

# One correction attempt is automatic. A second failure is a real editorial
# problem and belongs in front of a human, not in a spend loop.
MAX_AUTO_CORRECTIONS = 1


class AutoBuildStop(Exception):
    """A stage needs a person. Carries what to tell them."""

    def __init__(self, stage: str, reason: str, *, needs: str = "human"):
        super().__init__(reason)
        self.stage = stage
        self.reason = reason
        self.needs = needs


def _outline_chapter_count(data: dict) -> int:
    """How many chapters the approved outline actually has."""
    outline = data.get("outline")
    if isinstance(outline, list) and outline:
        return len(outline)
    for option in (data.get("ebook_workspace") or {}).get("outline_options") or []:
        chapters = (option or {}).get("chapters") or []
        if chapters:
            return len(chapters)
    return 0


def _pending_chapter_count(data: dict) -> int:
    try:
        return int(chapter_pipeline_stats(data).get("pending_chapter_count") or 0)
    except Exception:  # noqa: BLE001
        return 0


def plan_full_build(data: dict) -> dict[str, Any]:
    """What is left to do, and the most it can cost. Costs nothing to ask.

    Free stages contribute $0 — only the five entries in ``PAID_ACTIONS`` can
    ever charge, and the manuscript is priced per pending chapter exactly as the
    single-step estimate prices it.
    """
    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    ledger = ws.get("paid_call_ledger") or {}
    remaining_budget = round(float(ledger.get("remaining_usd") or 0), 4)
    cap = round(float(ledger.get("budget_cap_usd") or DEFAULT_BUDGET_CAP_USD), 4)

    steps: list[dict[str, Any]] = []
    total = 0.0
    for stage in BUILD_STAGES:
        if is_approved(ws, stage):
            continue
        cost = 0.0
        if stage == "research" and not (ws.get("research_payload") or {}).get("summary"):
            cost = float(PAID_ACTIONS["run_research"]["default_estimate_usd"])
        elif stage == "manuscript":
            if stage_status(ws, "manuscript") == STATUS_NEEDS_CORRECTION:
                cost = min(
                    max(_pending_chapter_count(data), 1) * CHAPTER_UNIT_USD,
                    float(PAID_ACTIONS["correct_manuscript"]["default_estimate_usd"]),
                )
            elif stage_status(ws, "manuscript") != STATUS_AWAITING:
                # `outline_options` holds outline *options*, not chapters --
                # using its length priced an 8-chapter book as one chapter.
                cost = min(
                    max(_pending_chapter_count(data) or _outline_chapter_count(data) or 8, 1)
                    * CHAPTER_UNIT_USD,
                    float(PAID_ACTIONS["generate_manuscript"]["default_estimate_usd"]),
                )
        cost = round(cost, 4)
        total += cost
        steps.append(
            {
                "stage": stage,
                "label": STAGE_RUNNING_LABEL.get(stage, stage.title()),
                "max_usd": cost,
                "paid": cost > 0,
            }
        )
    total = round(min(total, remaining_budget), 4)
    return {
        "steps": steps,
        "step_count": len(steps),
        "max_total_usd": total,
        "remaining_usd": remaining_budget,
        "budget_cap_usd": cap,
        "estimate_cost_usd": 0.0,
        "note": (
            "This estimate costs $0 and calls no provider. Only writing steps can "
            "charge; layout, preview and checks are free. Nothing is spent until "
            "you confirm, and the run stops rather than going over this maximum."
        ),
    }


def _spent(data: dict) -> float:
    ledger = (data.get("ebook_workspace") or {}).get("paid_call_ledger") or {}
    return round(float(ledger.get("spent_usd") or 0), 4)


def _run_paid_step(
    data: dict,
    action: str,
    executor: Callable[..., dict],
    *,
    budget_left: float,
    idempotency_key: str,
    **executor_kwargs: Any,
) -> dict:
    """Issue this step's own confirmation and run it inside the remaining budget.

    The single up-front authorization is turned into a per-step token here, so
    every existing guard — token binding, artifact revision, outline digest,
    ledger cap — still runs untouched.
    """
    out = estimate_paid_action(data, action)
    est = out["estimate"]
    step_max = round(float(est.get("max_authorized_usd") or est.get("estimated_max_usd") or 0), 4)
    if step_max > budget_left + 1e-9:
        raise AutoBuildStop(
            action,
            "The next writing step would go past the amount you authorized.",
            needs="budget",
        )
    return executor(
        data,
        confirmation_token=est["confirmation_token"],
        expected_artifact_id=str(est.get("artifact_id") or ""),
        expected_revision=int(est.get("artifact_revision") or 1),
        max_authorized_usd=step_max,
        idempotency_key=idempotency_key,
        **executor_kwargs,
    )


def run_full_build(
    data: dict,
    *,
    max_authorized_usd: float,
    idempotency_key: str,
    progress_key: str = "",
    project_id: int | None = None,
    research_fn=None,
    generate_chapter_fn=None,
    correct_chapter_fn=None,
    visuals_fn=None,
    cover_fn=None,
    design_fn=None,
    preview_fn=None,
    preflight_fn=None,
) -> dict[str, Any]:
    """Run every remaining stage from one authorization.

    Returns the updated ``data`` plus a report of what completed, what it cost,
    and — if it stopped early — which stage needs a person and why.
    """
    if not str(idempotency_key or "").strip():
        raise ValueError("Idempotency key is required.")

    data = ensure_workspace(data)
    if project_id is not None:
        data["_project_id"] = project_id
    authorized = round(float(max_authorized_usd or 0), 4)
    spent_at_start = _spent(data)
    completed: list[str] = []
    stopped: dict[str, Any] | None = None
    total_steps = len([s for s in BUILD_STAGES if not is_approved(data["ebook_workspace"], s)])
    done_steps = 0

    def announce(stage: str) -> None:
        if progress_key:
            progress_tracker.advance(
                progress_key,
                done=done_steps,
                total=total_steps,
                step_label=STAGE_RUNNING_LABEL.get(stage, stage.title()),
            )

    try:
        for stage in BUILD_STAGES:
            ws = data["ebook_workspace"]
            if is_approved(ws, stage):
                continue
            announce(stage)
            budget_left = round(authorized - (_spent(data) - spent_at_start), 4)

            if stage == "research":
                if not (ws.get("research_payload") or {}).get("summary"):
                    out = _run_paid_step(
                        data,
                        "run_research",
                        execute_run_research,
                        budget_left=budget_left,
                        idempotency_key=f"{idempotency_key}-research",
                        **({"research_fn": research_fn} if research_fn else {}),
                    )
                    data = out["data"]
                approve_stage(data, "research")

            elif stage == "title":
                if not str(data.get("title") or "").strip():
                    raise AutoBuildStop(
                        "title", "Your book needs a title before the chapters can be written."
                    )
                approve_stage(data, "title")

            elif stage == "outline":
                if not (data.get("outline") or data["ebook_workspace"].get("outline_options")):
                    data = apply_draft_outline(data)
                approve_stage(data, "outline")

            elif stage == "manuscript":
                data = _build_manuscript(
                    data,
                    budget_left=budget_left,
                    idempotency_key=idempotency_key,
                    generate_chapter_fn=generate_chapter_fn,
                    correct_chapter_fn=correct_chapter_fn,
                )
                approve_stage(data, "manuscript")

            elif stage == "visuals":
                data = _call_or_stop(visuals_fn, data, stage, "Images could not be prepared.")
                approve_stage(data, "visuals")

            elif stage == "cover":
                data = _call_or_stop(cover_fn, data, stage, "A cover photo could not be chosen.")
                if stage_status(data["ebook_workspace"], "cover") != STATUS_APPROVED:
                    approve_stage(data, "cover")

            elif stage == "design":
                data = _call_or_stop(design_fn, data, stage, "The layout could not be applied.")
                if stage_status(data["ebook_workspace"], "design") != STATUS_APPROVED:
                    approve_stage(data, "design")

            elif stage == "preview":
                data = _call_or_stop(preview_fn, data, stage, "The preview could not be built.")
                if stage_status(data["ebook_workspace"], "preview") != STATUS_APPROVED:
                    approve_stage(data, "preview")

            elif stage == "preflight":
                data = _call_or_stop(preflight_fn, data, stage, "Final checks could not run.")
                if stage_status(data["ebook_workspace"], "preflight") != STATUS_APPROVED:
                    approve_stage(data, "preflight")

            completed.append(stage)
            done_steps += 1

    except AutoBuildStop as stop:
        stopped = {"stage": stop.stage, "reason": stop.reason, "needs": stop.needs}
    except ValueError as exc:
        # A gate refused. That is the system working: report it, keep the work.
        stopped = {
            "stage": _current_stage(data),
            "reason": str(exc),
            "needs": "human",
        }

    charged = round(_spent(data) - spent_at_start, 4)
    if progress_key:
        progress_tracker.advance(progress_key, done=done_steps, total=total_steps)
    return {
        "ok": stopped is None,
        "data": data,
        "result": {
            "completed_stages": completed,
            "stopped": stopped,
            "charged_usd": charged,
            "authorized_usd": authorized,
            "finished": stopped is None,
        },
    }


def _current_stage(data: dict) -> str:
    return str((data.get("ebook_workspace") or {}).get("current_stage") or "")


def _call_or_stop(fn, data: dict, stage: str, failure_message: str) -> dict:
    """Run one free stage step, or stop cleanly if this deployment cannot."""
    if fn is None:
        raise AutoBuildStop(stage, failure_message)
    out = fn(data)
    if not isinstance(out, dict):
        raise AutoBuildStop(stage, failure_message)
    return out


def _build_manuscript(
    data: dict,
    *,
    budget_left: float,
    idempotency_key: str,
    generate_chapter_fn=None,
    correct_chapter_fn=None,
) -> dict:
    """Write the chapters, then auto-correct once if the quality gate objects."""
    ws = data["ebook_workspace"]
    if stage_status(ws, "manuscript") not in {STATUS_AWAITING, STATUS_NEEDS_CORRECTION}:
        out = _run_paid_step(
            data,
            "generate_manuscript",
            execute_generate_manuscript,
            budget_left=budget_left,
            idempotency_key=f"{idempotency_key}-manuscript",
            outline_digest_expected=_outline_digest(data),
            complete_all_chapters=True,
            **({"generate_chapter_fn": generate_chapter_fn} if generate_chapter_fn else {}),
        )
        data = out["data"]

    attempts = 0
    while stage_status(data["ebook_workspace"], "manuscript") == STATUS_NEEDS_CORRECTION:
        if attempts >= MAX_AUTO_CORRECTIONS:
            raise AutoBuildStop(
                "manuscript",
                "A chapter still needs an editorial fix after an automatic correction. "
                "Your draft is saved — review it and choose how to proceed.",
                needs="editorial",
            )
        budget_left = round(budget_left - 0, 4)
        out = _run_paid_step(
            data,
            "correct_manuscript",
            execute_correct_manuscript,
            budget_left=budget_left,
            idempotency_key=f"{idempotency_key}-correct-{attempts}",
            outline_digest_expected=_outline_digest(data),
            complete_all_chapters=True,
            **({"correct_chapter_fn": correct_chapter_fn} if correct_chapter_fn else {}),
        )
        data = out["data"]
        attempts += 1
    return data


def _outline_digest(data: dict) -> str:
    from services.ebook_project_workspace import outline_digest

    return outline_digest(data)
