"""One-click ebook build: a durable, resumable orchestration engine.

WHY
---
The Factory could already do every step of an ebook, but the customer had to
drive them: ten stages, each with its own button, its own confirmation, and its
own way of getting stuck. A beginner should press one button and receive a
finished product. The stages remain -- they are how the work is validated,
persisted and recovered -- but the Factory operates them, not the customer.

DESIGN
------
This is a state machine with persisted checkpoints, NOT a long HTTP request.
The browser starts (or attaches to) a build and polls for status; each poll
advances at most one stage and saves the result. That means a refresh, a closed
tab, a server restart, a slow model or a crashed stage all resume from the last
completed checkpoint instead of starting over.

GUARANTEES
----------
* Exactly one project per request -- an idempotency key makes a second click
  attach to the running build rather than create a duplicate.
* A stage is COMPLETE only when its real validator passed. No stage is marked
  done because code ran without raising.
* Completed work is never regenerated while the project is DRAFT and its
  inputs are unchanged.
* A stale RUNNING stage (crashed worker) is detected by age and reclaimed.
* Two workers cannot run the same stage at once.
* The customer never sees a token, a provider, a cost, or a traceback; the
  technical cause is logged privately with project, build, stage and attempt.
* The Factory never approves or locks the project. That stays the customer's.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# State model
# --------------------------------------------------------------------------

NOT_STARTED = "NOT_STARTED"
RUNNING = "RUNNING"
REPAIRING = "REPAIRING"
COMPLETE = "COMPLETE"
BLOCKED = "BLOCKED"
FAILED_RECOVERABLE = "FAILED_RECOVERABLE"
FAILED_FINAL = "FAILED_FINAL"
#: v1.9.6: a stage whose work is done and is waiting for the customer.
PENDING_CUSTOMER = "WAITING_FOR_CUSTOMER"

#: Ordered build stages. These mirror the workspace rail, which remains the
#: source of truth for what has actually been validated.
STAGES = (
    "research",
    "title",
    "outline",
    "manuscript",
    "visuals",
    "cover",
    "design",
    "preview",
    "preflight",
    "export",
)

#: Plain language only. The customer sees these, so no stage jargon, no
#: provider names, no internal codes.
STAGE_MESSAGES = {
    "research": "Researching your topic",
    "title": "Planning your ebook",
    "outline": "Planning your ebook",
    "manuscript": "Writing your chapters",
    "visuals": "Preparing professional visuals",
    "cover": "Designing your cover",
    "design": "Preparing your design",
    "preview": "Building your preview",
    "preflight": "Checking quality",
    "export": "Building your final files",
}

MSG_WORKING = "Preparing your ebook"
MSG_READY = "Your ebook is ready"
MSG_RESUMED = "We're continuing from your last completed step."
MSG_RETRY = "We couldn't complete this step yet. The Factory saved your progress and will try again."
MSG_FINAL = "Your project is safely saved. We couldn't complete this step automatically."
MSG_MANUSCRIPT_READY = "Your manuscript is written and ready to read."


#: Plain-language "this stage is done, come and look" messages. The customer
#: reads these while the build waits for them, so they say what is ready
#: rather than naming a stage.
STAGE_READY_MESSAGES = {
    "research": "Your research is ready to read.",
    "title": "Your title choices are ready.",
    "outline": "Your outline is ready to read.",
    "manuscript": MSG_MANUSCRIPT_READY,
    "visuals": "Your visuals are ready to look at.",
    "cover": "Your cover is ready to look at.",
    "design": "Your design is ready to look at.",
    "preview": "Your preview is ready to read.",
    "preflight": "Your quality check is finished.",
    "export": "Your final files are ready.",
}


def pause_after(data: dict, stage: str) -> dict:
    """Hold the build once `stage` is complete, so the customer can look at it.

    v1.8.1. The step-by-step screen approves every stage, not only the
    manuscript, so the hold has to work for every stage. Setting it is all
    this does: the decision to STOP is made in advance_build, which already
    reads `paused_after`, and nothing about the stage's own work changes.
    """
    state = build_state(data)
    stage = str(stage or "").strip()
    if stage and stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    state["paused_after"] = stage
    state["updated_at"] = _now()
    return data


def clear_pause(data: dict) -> dict:
    """Release the hold so the build may run the next stage.

    This is what the customer's approval means. Until v1.8.1 nothing ever
    cleared `paused_after`, which is why the hold was never used: a build
    that stopped would have stopped for good.
    """
    state = build_state(data)
    state["paused_after"] = ""
    state["updated_at"] = _now()
    return data


def held_after(data: dict, state: dict | None = None) -> str:
    """The stage this build is deliberately holding at, or "".

    A hold only takes effect once the stage it names has actually completed.
    Before that the build is simply working, and reporting it as "waiting for
    you" would be a lie the customer cannot act on.
    """
    state = state if isinstance(state, dict) else build_state(data)
    stage = str(state.get("paused_after") or "")
    if not stage:
        return ""
    from services.ebook_project_workspace import is_approved

    ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
    return stage if is_approved(ws, stage) else ""


def _held_after_manuscript(data: dict, state: dict) -> bool:
    """True when the build is deliberately holding at the finished manuscript.

    Kept as a named helper because the manuscript hold has its own customer
    message and its own tests. It is now one case of the general rule above.
    """
    return held_after(data, state) == "manuscript"

#: A stage held RUNNING longer than this lost its worker and may be reclaimed.
STALE_RUNNING_SECONDS = 900
#: Attempts per stage before it is treated as unrecoverable.
MAX_STAGE_ATTEMPTS = 3
#: Manuscript now does bounded, incremental chapter-by-chapter work -- one
#: chapter (or one repair) per /advance call -- instead of writing an entire
#: book inside one request (see MANUSCRIPT_CHAPTERS_PER_ADVANCE). A real
#: book legitimately needs many /advance calls to finish this way, and none
#: of that incremental progress is a failure, so this stage alone gets a
#: much higher ceiling. Every other stage keeps MAX_STAGE_ATTEMPTS unchanged.
STAGE_MAX_ATTEMPTS: dict[str, int] = {"manuscript": 60}


def _max_attempts(stage: str) -> int:
    return STAGE_MAX_ATTEMPTS.get(stage, MAX_STAGE_ATTEMPTS)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ts() -> float:
    return datetime.now(timezone.utc).timestamp()


# --------------------------------------------------------------------------
# Build record
# --------------------------------------------------------------------------


def build_state(data: dict) -> dict:
    """The persisted build record, created on first use."""
    state = data.get("ebook_build")
    if not isinstance(state, dict):
        state = {
            "build_id": "",
            "started_at": "",
            "updated_at": "",
            "current_stage": "",
            "stages": {},
            "customer_message": MSG_WORKING,
            "finished": False,
            "failed": False,
        }
        data["ebook_build"] = state
    state.setdefault("stages", {})
    return state


def _stage_record(state: dict, stage: str) -> dict:
    rec = state["stages"].get(stage)
    if not isinstance(rec, dict):
        rec = {"status": NOT_STARTED, "attempts": 0, "updated_at": "", "error": ""}
        state["stages"][stage] = rec
    return rec


def idempotency_key_for(fields: dict, customer: str = "local") -> str:
    """Stable key for a build request, so a repeat click attaches rather than duplicates."""
    payload = {
        "customer": customer,
        "title": str((fields or {}).get("ebook_title") or "").strip().lower(),
        "topic": str((fields or {}).get("topic") or "").strip().lower(),
        "author": str((fields or {}).get("author_brand") or "").strip().lower(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:32]


# --------------------------------------------------------------------------
# Stage completion is read from the rail, never from our own optimism
# --------------------------------------------------------------------------


def _rail(data: dict) -> dict:
    ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
    rail = ws.get("rail")
    return rail if isinstance(rail, dict) else {}


def _verified_export_by_path(package_id: str, name: str) -> bytes | None:
    """Verified stored bytes for exports/<package_id>/<name>, or None. Never raises."""
    try:
        import database

        if not database.list_assets_exist():
            return None
        record = database.find_asset_by_export_path(package_id, name)
        if not record or not record.get("approved"):
            return None
        from services.storage.compat import verified_asset_bytes

        return verified_asset_bytes(record["storage_key"])
    except Exception:                                  # noqa: BLE001
        return None


def _recover_export_files(data: dict, pkg_dir: str) -> None:
    """Bring this project's finished PDF and ZIP back to THIS machine.

    v1.8.14. The files are built on the builder and published to storage;
    the website, which never had them, then reported a finished book as
    unfinished. /download already serves the stored copy, so the bytes are
    there -- fetch them so every reader agrees the book is done. Only bytes
    that really are a PDF and a ZIP are written. Never raises.
    """
    try:
        pid = int(data.get("_project_id") or 0)
    except (TypeError, ValueError):
        pid = 0
    if pid <= 0:
        return
    package_id = os.path.basename(pkg_dir)
    try:
        from services.storage.compat import read_export_or_legacy

        for name, magic in (("ebook.pdf", b"%PDF"), ("package.zip", b"PK\x03\x04")):
            path = os.path.join(pkg_dir, name)
            if os.path.isfile(path):
                continue
            payload = read_export_or_legacy(pid, f"{package_id}/{name}")
            if not payload:
                # v1.9.7: the same lookup /download uses -- the stored asset
                # record for this export folder -- so the status screen and
                # the download button can never disagree about a finished book.
                payload = _verified_export_by_path(package_id, name)
            if not payload or not payload.startswith(magic):
                continue
            os.makedirs(pkg_dir, exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(payload)
            os.replace(tmp, path)
    except Exception:                                  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception("could not fetch the finished files")


def _export_files_on_disk(data: dict) -> bool:
    """A real PDF and a real ZIP exist for this project, here or in storage."""
    from services.packaging import EXPORTS_DIR

    package_id = str(data.get("export_package_id") or data.get("package_id") or "").strip()
    # Same rule the download route enforces: no dots or separators, so the id
    # cannot escape EXPORTS_DIR. Package ids are hex or slugs like
    # "ebook-visuals-local", so hyphens and underscores are legitimate.
    if not package_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", package_id):
        return False
    pkg_dir = os.path.join(EXPORTS_DIR, package_id)
    pdf_path = os.path.join(pkg_dir, "ebook.pdf")
    zip_path = os.path.join(pkg_dir, "package.zip")
    if not (os.path.isfile(pdf_path) and os.path.isfile(zip_path)):
        _recover_export_files(data, pkg_dir)
    try:
        if not (os.path.isfile(pdf_path) and os.path.isfile(zip_path)):
            return False
        with open(pdf_path, "rb") as fh:
            if not fh.read(5).startswith(b"%PDF"):
                return False
        with open(zip_path, "rb") as fh:
            if not fh.read(4) == b"PK\x03\x04":
                return False
    except OSError:
        return False
    return True


def stage_is_validated(data: dict, stage: str) -> bool:
    """True only when the workspace itself says the stage is approved.

    The rail is updated by the real validators. Asking it -- rather than
    trusting a flag we set ourselves -- is what stops a stage being marked
    done because the code merely ran.
    """
    if stage == "export":
        # Export is a download, not an approval stage, so the rail never marks
        # it approved. Validate the artifact itself: the release gate says
        # ready, and a real PDF and ZIP exist on disk under this package.
        if not data.get("export_ready"):
            return False
        exports = data.get("exports") if isinstance(data.get("exports"), dict) else {}
        files = exports.get("files") if isinstance(exports.get("files"), dict) else {}
        if not files.get("pdf") or not files.get("zip"):
            return False
        return _export_files_on_disk(data)
    entry = _rail(data).get(stage)
    if isinstance(entry, dict):
        return str(entry.get("status") or "") == "approved"
    return False


def next_incomplete_stage(data: dict) -> str | None:
    for stage in STAGES:
        if not stage_is_validated(data, stage):
            return stage
    return None


def progress_percent(data: dict) -> int:
    done = sum(1 for s in STAGES if stage_is_validated(data, s))
    return int(round(100.0 * done / len(STAGES)))


# --------------------------------------------------------------------------
# Locking
# --------------------------------------------------------------------------


def _claim_stage(state: dict, stage: str) -> bool:
    """Claim a stage for this worker. False when another worker holds it."""
    rec = _stage_record(state, stage)
    if rec.get("status") == RUNNING:
        started = float(rec.get("running_since") or 0)
        if started and (_ts() - started) < STALE_RUNNING_SECONDS:
            return False
        # The previous worker died. Reclaim rather than stranding the build.
        log.warning("reclaiming stale RUNNING stage %s", stage)
    rec["status"] = RUNNING
    rec["running_since"] = _ts()
    rec["attempts"] = int(rec.get("attempts") or 0) + 1
    rec["updated_at"] = _now()
    return True


def _release_stage(state: dict, stage: str, status: str, error: str = "") -> None:
    rec = _stage_record(state, stage)
    rec["status"] = status
    rec["running_since"] = 0
    rec["updated_at"] = _now()
    rec["error"] = error or ""


# --------------------------------------------------------------------------
# Internal authorization: the customer never sees or approves this
# --------------------------------------------------------------------------


def _authorized(data: dict, action: str) -> tuple[dict, dict]:
    """Issue a fresh internal confirmation for a paid stage action.

    A spent or expired confirmation is replaced automatically. This is an
    internal spend control, not something to ask a customer about; the
    server-side budget ceiling still applies and still refuses when exceeded.
    """
    from services.ebook_project_workspace import clear_pending_estimate, estimate_paid_action

    data = clear_pending_estimate(data)
    out = estimate_paid_action(data, action)
    return out.get("data", data), (out.get("estimate") or {})


def _attempt_idempotency_key(data: dict, stage: str, pid: int, *, suffix: str = "") -> str:
    """One idempotency key per ATTEMPT, not one per project for all time.

    An idempotency key exists so the SAME logical paid call, delivered
    twice — two executors racing, a retried request — is charged once. A
    key that is constant for the life of the project does something else
    entirely: the workspace records it on the first call, and every later
    call carrying it returns the original result as a duplicate replay,
    doing no work and persisting nothing.

    That is what stranded a finished book. "Container Gardening for
    Beginners" wrote nine good chapters and needed one correction pass. It
    got exactly one, ever: attempt 1 corrected what it could and left a
    single finding, attempts 2 to 60 replayed instantly and re-raised on
    that same stale finding. Sixty attempts in about a minute, then
    FAILED_FINAL — and no Continue could help, because resume clears the
    attempt count while the replay still short-circuits.

    `_claim_stage` increments the stage's attempt counter before the runner
    runs, so that counter is exactly the right identity: the same attempt
    replays safely, a real retry is a new logical call (v1.7.26).
    """
    try:
        rec = _stage_record(build_state(data), stage)
        attempt = int(rec.get("attempts") or 0)
    except Exception:                                      # noqa: BLE001
        # A key must never be the reason a build cannot run.
        attempt = 0
    tail = f"-{suffix}" if suffix else ""
    return f"orch-{stage}{tail}-{pid}-a{attempt}"


def _confirm_kwargs(est: dict, data: dict, key: str) -> dict:
    return {
        "confirmation_token": str(est.get("confirmation_token") or ""),
        "expected_artifact_id": str(est.get("artifact_id") or data.get("artifact_id") or ""),
        "expected_revision": int(est.get("artifact_revision") or data.get("artifact_revision") or 0),
        "max_authorized_usd": float(
            est.get("max_total_usd") or est.get("estimated_max_usd") or 0
        ),
        "idempotency_key": key,
    }


# --------------------------------------------------------------------------
# Stage runners -- each drives the EXISTING service, then approves via the
# real validator. Nothing here bypasses a quality gate.
# --------------------------------------------------------------------------


def _run_research(data: dict, pid: int) -> dict:
    from services.ebook_project_workspace import approve_stage, execute_run_research

    data, est = _authorized(data, "run_research")
    out = execute_run_research(data, **_confirm_kwargs(est, data, _attempt_idempotency_key(data, "research", pid)))
    return approve_stage(out["data"], "research")


def _run_title(data: dict, pid: int) -> dict:
    from services.ebook_project_workspace import approve_stage, execute_generate_title_options

    data, est = _authorized(data, "generate_title_options")
    out = execute_generate_title_options(data, **_confirm_kwargs(est, data, _attempt_idempotency_key(data, "title", pid)))
    return approve_stage(out["data"], "title")


def _run_outline(data: dict, pid: int) -> dict:
    from services.ebook_project_workspace import approve_stage, execute_generate_outline_options

    data, est = _authorized(data, "generate_outline_options")
    out = execute_generate_outline_options(data, **_confirm_kwargs(est, data, _attempt_idempotency_key(data, "outline", pid)))
    return approve_stage(out["data"], "outline")


#: A manuscript used to be written entirely inside one /advance request --
#: for a real book, potentially minutes of one blocking HTTP call, long
#: enough to trip a production web server's request timeout and kill the
#: worker mid-write. Bounding each call to one chapter keeps every single
#: /advance request roughly "one chapter's writing time" long, no matter how
#: long the book is, reusing the existing checkpoint/resume loop to cover the
#: rest -- the same contract every other stage already follows.
MANUSCRIPT_CHAPTERS_PER_ADVANCE = 1


def _mark_stage_still_working(data: dict, result: dict, *, verb: str) -> None:
    """Keep the plain-language progress message when a stage reports 'not
    finished yet, nothing wrong' -- not the generic retry wording, which is
    for when something actually needed a second attempt. Sets a marker
    advance_build checks (and clears) so this stays scoped to exactly this
    call; it is never persisted or shown to the customer directly.
    """
    state = data.setdefault("ebook_build", {})
    done = result.get("chapters_done")
    total = result.get("chapters_total")
    if isinstance(done, int) and isinstance(total, int) and total > 0:
        state["customer_message"] = f"{verb} your chapters ({done} of {total})"
    else:
        state["customer_message"] = f"{verb} your chapters"
    state["_no_retry_message"] = True


def _run_manuscript(data: dict, pid: int) -> dict:
    """Write and validate chapters, auto-correct if needed, then approve.

    Bounded, incremental work: this call writes or repairs at most
    MANUSCRIPT_CHAPTERS_PER_ADVANCE chapters, then returns. If chapters
    remain, the manuscript stage is left IN_PROGRESS (not a failure) and the
    browser's ordinary polling loop calls /advance again to continue -- the
    same resumable checkpoint pattern every other stage already uses.
    Already-accepted chapters are read back from persistence and skipped,
    never regenerated or re-billed (services.ebook_project_workspace.
    execute_generate_manuscript / execute_correct_manuscript).

    A manuscript with real structural/content findings, once fully written,
    is not a customer-facing dead end either: this runs the Factory's
    existing correction pass -- the same system a human triggers via
    "Request Correction" in the guided workspace,
    services.ebook_project_workspace.execute_correct_manuscript --
    automatically before giving up. Only a manuscript that still fails after
    that correction stops the build; the customer is never asked to resolve
    internal QA findings themselves.
    """
    from services.ebook_project_workspace import (
        STATUS_NEEDS_CORRECTION,
        approve_stage,
        execute_correct_manuscript,
        execute_generate_manuscript,
        stage_status,
    )

    import database

    ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
    # A resumed attempt on a project already left needing correction (by a
    # prior attempt of this same stage) must go straight to correction.
    # execute_generate_manuscript refuses to run again over an existing
    # NEEDS_CORRECTION draft by design -- calling it here would either raise
    # that refusal or, without the guard, silently regenerate a manuscript
    # that a customer's earlier attempt already partly paid to produce.
    already_needs_correction = stage_status(ws, "manuscript") == STATUS_NEEDS_CORRECTION and bool(
        data.get("content") or data.get("ebook")
    )

    if not already_needs_correction:
        data, est = _authorized(data, "generate_manuscript")
        kwargs = _confirm_kwargs(est, data, _attempt_idempotency_key(data, "manuscript", pid))
        kwargs["outline_digest_expected"] = str(est.get("outline_digest") or "")
        out = execute_generate_manuscript(
            data,
            persist_progress=lambda partial: database.update_project(pid, None, partial),
            max_chapters_per_call=MANUSCRIPT_CHAPTERS_PER_ADVANCE,
            **kwargs,
        )
        data = out["data"]
        # Persist the assembled manuscript, QA findings and stage status now,
        # before approve_stage runs. A real structural/content finding makes
        # approve_stage raise by design (see its docstring), and that must
        # never turn into losing the work this step already produced --
        # persist_progress above only covers chapter-by-chapter progress
        # during generation, not this final assembly step.
        database.update_project(pid, None, data)
        if out.get("in_progress"):
            # More chapters remain, nothing failed -- report progress and
            # let the next /advance call continue. Never call approve_stage
            # against a manuscript that is deliberately still incomplete.
            _mark_stage_still_working(data, out.get("result") or {}, verb="Writing")
            return data
        ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}

    if stage_status(ws, "manuscript") == STATUS_NEEDS_CORRECTION:
        data, cest = _authorized(data, "correct_manuscript")
        ckwargs = _confirm_kwargs(cest, data,
                                  _attempt_idempotency_key(data, "manuscript", pid,
                                                           suffix="correct"))
        ckwargs["outline_digest_expected"] = str(cest.get("outline_digest") or "")
        cout = execute_correct_manuscript(
            data,
            persist_progress=lambda partial: database.update_project(pid, None, partial),
            max_chapters_per_call=MANUSCRIPT_CHAPTERS_PER_ADVANCE,
            **ckwargs,
        )
        data = cout["data"]
        # Same reasoning as above: persist the corrected assembly before
        # approve_stage gets a chance to reject it.
        database.update_project(pid, None, data)
        if cout.get("in_progress"):
            _mark_stage_still_working(data, cout.get("result") or {}, verb="Correcting")
            return data

    # approve_stage runs outline fidelity and the manuscript quality gate; it
    # raises if either still fails after the correction attempt above, which
    # keeps a genuinely defective manuscript out of design.
    return approve_stage(data, "manuscript")


#: v1.9.6. The one-click build stops once, after the pictures are chosen,
#: so the customer can look at every picture on one sheet, replace any, and
#: press Approve All Visuals. Their approval is what lets the build carry on
#: to the cover, the PDF and the ZIP. Nothing is approved on their behalf.
MSG_PICTURES_READY = (
    "Your pictures are ready. Look them over, change any you like, "
    "then press Approve All Visuals."
)


def awaiting_picture_approval(data: dict, state: dict | None = None) -> bool:
    """True while the build is waiting for the customer to approve the pictures.

    Only true when the pictures have been prepared and the customer has not
    approved them yet. Once the rail says visuals are approved the wait is
    over, whatever the flag still says.
    """
    from services.ebook_project_workspace import is_approved

    state = state if isinstance(state, dict) else build_state(data)
    if not state.get("awaiting_picture_approval"):
        return False
    ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
    if is_approved(ws, "visuals"):
        return False
    return isinstance(data.get("visual_plan"), dict)


def _run_visuals(data: dict, pid: int) -> dict:
    from services.ebook_design_workspace import prepare_visuals_local

    data = prepare_visuals_local(data)
    # v1.9.6: never approve here. Hold for the customer's one approval.
    state = build_state(data)
    state["awaiting_picture_approval"] = True
    state["customer_message"] = MSG_PICTURES_READY
    state["_no_retry_message"] = True
    return data


def _run_cover(data: dict, pid: int) -> dict:
    from services.ebook_customer_path import _first_passing_layout, _fixture_jpeg
    from services.ebook_design_workspace import stage_photo_cover
    from services.ebook_photo_cover import (
        PhotoCoverError,
        _activate_source,
        _store_source_bytes,
        select_layout,
    )
    from services.ebook_project_workspace import approve_stage
    from services.external_calls import ebook_fixture_mode

    data.setdefault("_project_id", pid)
    if ebook_fixture_mode():
        raw = _fixture_jpeg((36, 92, 48), seed=f"cover-{pid}")
        source = _store_source_bytes(
            data, raw, source_type="local_licensed", filename="cover-fixture.jpg",
            license_note="Deterministic local fixture photograph. Not for sale.",
            project_id=pid,
        )
        data = _activate_source(data, source, project_id=pid)
        layout = _first_passing_layout(data.get("cover_design"))
        if not layout:
            raise PhotoCoverError("No safe cover layout passed quality checks.")
        data = select_layout(data, layout, project_id=pid)
        data = stage_photo_cover(data, project_id=pid)
        return approve_stage(data, "cover")

    from services.ebook_customer_path import complete_photo_cover

    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    package_id = str(data.get("package_id") or data.get("artifact_id") or "")
    try:
        # complete_photo_cover takes keyword-only arguments. Calling it with a
        # bare dict raised TypeError on every attempt, so the cover stage could
        # never run outside fixture mode.
        data = complete_photo_cover(
            data,
            title=str(data.get("title") or ""),
            subtitle=str(data.get("subtitle") or ""),
            author=str(data.get("author_brand") or data.get("author") or ""),
            fields=fields,
            package_id=package_id,
        )
    except Exception as exc:  # noqa: BLE001
        log.info("cover: stock search raised (%s); using an approved interior photo", exc)

    # complete_photo_cover keeps the previous cover on failure rather than
    # raising, so a blocked or empty stock search returns the data unchanged
    # and approval then fails with "Select a cover before approving". Judge it
    # by its result, not by whether it threw.
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    if not str(cover.get("selected_layout") or "").strip():
        # Rather than stall the build or reach for a paid generator, use a
        # photograph this book has already approved for one of its own
        # chapters: it is on disk, it cost nothing, and it is demonstrably
        # about this subject.
        data = _cover_from_approved_interior_photo(data, pid)
    return approve_stage(data, "cover")


def _cover_from_approved_interior_photo(data: dict, pid: int) -> dict:
    """Promote an already-approved interior photograph to the cover.

    Free, offline, and honest: the image is one the visual validator has
    already accepted for this book. Raises when the book has no such
    photograph, because an unrelated stock filler would be worse than an
    honest failure.
    """
    from services.ebook_photo_cover import (
        PhotoCoverError, _activate_source, _store_source_bytes, select_layout,
    )
    from services.ebook_customer_path import _first_passing_layout
    from services.ebook_design_workspace import stage_photo_cover

    plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {}
    candidates: list[dict] = []
    for chapter in (plan.get("chapters") or []):
        for aid in (chapter.get("aids") or []):
            if str(aid.get("type") or "").lower() not in {"photo", "stock photo"}:
                continue
            # v1.9.6: interior pictures from Unsplash or Pixabay are never
            # promoted to the cover. Their API rules differ from Pexels (for
            # example Unsplash forbids selling unaltered photos on products)
            # and the cover record only understands Pexels provenance.
            if str(aid.get("source") or "").lower() in {"unsplash", "pixabay"}:
                continue
            path = str(aid.get("asset_path") or "")
            if path and os.path.isfile(path) and str(aid.get("match_status") or "") == "pass":
                candidates.append(aid)
    if not candidates:
        raise PhotoCoverError(
            "No approved photograph is available for the cover."
        )

    last_error = ""
    for aid in candidates:
        path = str(aid.get("asset_path") or "")
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
            # Provenance travels with the picture. A cover sourced from Pexels
            # must carry the photo id and photographer, or the cover validator
            # rightly refuses it as an incomplete record.
            rec = aid.get("pexels") if isinstance(aid.get("pexels"), dict) else {}
            photo_id = str(rec.get("photo_id") or aid.get("photo_id") or "").strip()
            photographer = str(rec.get("photographer") or aid.get("photographer") or "").strip()
            source_type = str(aid.get("source") or "local_licensed")
            if source_type == "pexels" and not (photo_id and photographer):
                last_error = "interior photograph has an incomplete Pexels record"
                continue
            source = _store_source_bytes(
                data, raw,
                source_type=source_type,
                # Keep the real extension: _store_source_bytes cross-checks the
                # sniffed image type against it and refuses a mismatch.
                filename=os.path.basename(path),
                license_note=str(aid.get("license_note") or "Pexels License: free to use."),
                project_id=pid,
            )
            if photographer:
                source["photographer"] = photographer
            if source_type == "pexels":
                source["pexels"] = {
                    "photo_id": photo_id,
                    "photographer": photographer,
                    "page_url": str(rec.get("page_url") or aid.get("page_url") or ""),
                    "sha256": source.get("sha256"),
                    "artifact_id": str(data.get("package_id") or ""),
                    "project_id": pid,
                    "query": str(rec.get("query") or aid.get("pexels_query") or ""),
                }
            data = _activate_source(data, source, project_id=pid)
            layout = _first_passing_layout(data.get("cover_design"))
            if not layout:
                last_error = "no cover layout passed quality checks for this photograph"
                continue
            data = select_layout(data, layout, project_id=pid)
            return stage_photo_cover(data, project_id=pid)
        except PhotoCoverError as exc:
            last_error = str(exc)
            continue
    raise PhotoCoverError(last_error or "No safe cover layout passed quality checks.")


def _run_design(data: dict, pid: int) -> dict:
    from services.ebook_design_workspace import select_and_stage_theme
    from services.ebook_project_workspace import approve_stage

    theme = str((data.get("fields") or {}).get("theme_id") or "studio_clean")
    data = select_and_stage_theme(data, theme)
    return approve_stage(data, "design")


def _run_preview(data: dict, pid: int) -> dict:
    from services.ebook_design_workspace import build_preview
    from services.ebook_project_workspace import approve_stage, record_preview_opened

    data = build_preview(data)
    # Preview approval requires proof the full preview was actually opened.
    # The orchestrator builds and renders it on the customer's behalf, so it
    # records that here rather than demanding a separate click.
    data = record_preview_opened(data)
    return approve_stage(data, "preview")


def _run_preflight(data: dict, pid: int) -> dict:
    from services.ebook_design_workspace import run_preflight_stage
    from services.ebook_project_workspace import approve_stage

    data = run_preflight_stage(data)
    return approve_stage(data, "preflight")


_EXPORT_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _publish_export_files(pid: int, exports_root: str, files: dict) -> int:
    """v1.8.4. Put the finished book's files where the website can serve them.

    On the builder the PDF and ZIP land on a temporary disk the website
    cannot read, and that disk is gone when the task ends. /download already
    serves a verified stored copy when there is no file on its own disk, so
    publishing here is all the website needs. Inline mode does not publish
    (publishing_enabled is off), so local Windows development is unchanged.
    Never raises; returns how many files were published.
    """
    published = 0
    try:
        from services.ebook_package import is_allowed_download
        from services.storage.publish import publish_file, publishing_enabled

        if not publishing_enabled():
            return 0
        for name, full in sorted((files or {}).items()):
            if not is_allowed_download(str(name)):
                continue
            ext = os.path.splitext(str(name))[1].lower()
            ctype = _EXPORT_CONTENT_TYPES.get(ext, "application/octet-stream")
            kind = "export_pdf" if ext == ".pdf" else ("export_zip" if ext == ".zip" else "export_file")
            if publish_file(int(pid), exports_root, full, kind=kind, content_type=ctype):
                published += 1
            else:
                log.error("export %s for project %s was not published", name, pid)
    except Exception:                                  # noqa: BLE001
        log.exception("could not publish the finished files for project %s", pid)
    return published


def _run_export(data: dict, pid: int) -> dict:
    """Build the customer's PDF and ZIP. Does not approve or lock anything.

    Packaging only. ``build_ebook_package`` was the wrong function here: it is
    the *generation* pipeline (visual plan, photograph retrieval, cover
    staging) and would have re-run acquisition over an already-approved
    artifact. ``build_product_export`` is the same renderer the Export button
    uses, so the one-click build and the manual rail produce the identical
    PDF/ZIP from the identical approved artifact.
    """
    from services.packaging import build_product_export

    project = {"id": pid, "type": "ebook", "data": data}
    result = build_product_export(project)
    if isinstance(project.get("data"), dict):
        data = project["data"]
    if isinstance(result, dict):
        if result.get("package_id"):
            data["export_package_id"] = result["package_id"]
            data["package_id"] = result["package_id"]
        if isinstance(result.get("exports"), dict):
            data["product_exports"] = result["exports"]
            data["exports"] = result["exports"]

    # Record the package's files on disk. ebook_project_readiness() looks up
    # data["export_files"]["package.zip"] to confirm the bundle exists, and the
    # workspace export branch of build_product_export returns before writing
    # it. Without this map the readiness check reported "Correct failed
    # preflight item" for a book whose ZIP was sitting in the package folder,
    # which blocked the customer's Approve Product save.
    from services.packaging import EXPORTS_DIR

    package_id = str(data.get("export_package_id") or data.get("package_id") or "").strip()
    if package_id and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", package_id):
        pkg_dir = os.path.join(EXPORTS_DIR, package_id)
        if os.path.isdir(pkg_dir):
            files_on_disk: dict[str, str] = {}
            for name in os.listdir(pkg_dir):
                full = os.path.join(pkg_dir, name)
                if os.path.isfile(full):
                    files_on_disk[name] = full
            if files_on_disk:
                data["export_files"] = files_on_disk
                _publish_export_files(pid, EXPORTS_DIR, files_on_disk)
            pdf_on_disk = os.path.join(pkg_dir, "ebook.pdf")
            if os.path.isfile(pdf_on_disk):
                data["pdf_path"] = pdf_on_disk
                data["pdf_available"] = True
            if os.path.isfile(os.path.join(pkg_dir, "package.zip")):
                data["zip_available"] = True

    # The workspace export branch of build_product_export returns a *new*
    # project dict, so the release state it computed never reaches this caller.
    # Re-derive it from the authoritative validator rather than carrying a
    # stale value: reaching this line at all proves design preflight PASSed and
    # the exported bytes verified, because apply_workspace_design_to_export
    # raises otherwise. This is the same rule render_designed_bundle applies --
    # it is read from the preflight record, never invented.
    pre = data.get("ebook_design_preflight")
    pre_status = str((pre or {}).get("status") or "").upper() if isinstance(pre, dict) else ""
    if pre_status == "PASS":
        data["export_ready"] = True
        data["release_status"] = "PASS"
    else:
        data["export_ready"] = False
        data["release_status"] = pre_status

    # This is the moment a workspace-built ebook becomes a finished product the
    # customer can download, so it is the moment it must become findable in
    # Saved Projects. The workspace pipeline never recorded the customer
    # lifecycle tokens the saved-products filter reads, so every ebook it built
    # stayed invisible however complete it was. Judged on stored evidence, not
    # on having reached this line: see ebook_is_customer_complete. Does not
    # touch artifact_state (v1.4.1).
    from services.ebook_customer_path import mark_ebook_customer_saved

    data = mark_ebook_customer_saved(data)

    # The identity block is stamped by design preflight; the files a customer
    # downloads are written here, later. Leaving the two unreconciled showed
    # hashes from an earlier revision beside this one's approved stages. Read
    # the bytes just written and record those (v1.5.0).
    from services.ebook_revision_identity import stamp_current_revision

    stamp_current_revision(data)
    return data


STAGE_RUNNERS: dict[str, Callable[[dict, int], dict]] = {
    "research": _run_research,
    "title": _run_title,
    "outline": _run_outline,
    "manuscript": _run_manuscript,
    "visuals": _run_visuals,
    "cover": _run_cover,
    "design": _run_design,
    "preview": _run_preview,
    "preflight": _run_preflight,
    "export": _run_export,
}


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def find_existing_build(idem_key: str):
    """An in-flight build for the same request, so a repeat click attaches."""
    import database

    if not idem_key:
        return None
    for project in database.list_projects():
        data = project.get("data") if isinstance(project.get("data"), dict) else {}
        state = data.get("ebook_build") if isinstance(data.get("ebook_build"), dict) else {}
        if state.get("idempotency_key") == idem_key:
            return project
    return None


def start_build(fields: dict, *, customer: str = "local"):
    """Create exactly one DRAFT project, or attach to the existing build."""
    import database
    from services.ebook_project_workspace import new_workspace, sync_document_from_workspace

    fields = dict(fields or {})
    idem = idempotency_key_for(fields, customer)

    existing = find_existing_build(idem)
    if existing:
        log.info("attaching to existing build for idempotency key %s", idem)
        return existing, False

    from services.ebook_contamination import normalize_author, normalize_book_title

    def _f(k: str) -> str:
        return str(fields.get(k) or "").strip()

    # The customer's raw entry can carry a leading colon or a stray byline.
    # Normalise once, here, or the defect is stored in the project and printed
    # on the cover and in the PDF.
    title = normalize_book_title(_f("ebook_title") or _f("topic"))
    topic = _f("topic") or title
    author = normalize_author(_f("author_brand"))

    data = {
        "product_type": "ebook",
        "ebook_project_workspace": True,
        "artifact_state": "DRAFT",
        "artifact_revision": 1,
        "title": title,
        "subtitle": "",
        "author_brand": author,
        "source": topic,
        "topic": topic,
        "audience": _f("audience"),
        "content": "",
        "ebook": "",
        "export_ready": False,
        # Canonical shape. automatic_visuals_requested() reads include_images
        # here, so the customer's own choice decides whether photographs are
        # fetched -- and "No" is respected.
        "fields": fields,
        "include_images": _f("include_images") or "Yes",
        "suggested_price": _f("price") or _f("suggested_price"),
        "ebook_workspace": new_workspace(
            topic=topic, audience=_f("audience"), outcome=_f("outcome"),
            author=author, budget_cap_usd=3.5,
        ),
    }
    state = build_state(data)
    state["build_id"] = hashlib.sha256(f"{idem}{_now()}".encode()).hexdigest()[:16]
    state["idempotency_key"] = idem
    state["started_at"] = _now()
    state["customer_message"] = MSG_WORKING

    data = sync_document_from_workspace(data)
    project = database.create_project(
        (title or "Untitled Ebook")[:200], "ebook", data,
        user_saved=True, system_test=False, temporary=False,
    )
    return project, True


def advance_build(project_id: int) -> dict:
    """Run at most one stage, persist, and report customer-safe status.

    Called repeatedly by the browser's poller. Each call is a checkpoint, so
    an interruption at any point loses at most the stage in flight.
    """
    import database

    project = database.get_project(project_id)
    if not project:
        return {"ok": False, "message": MSG_FINAL, "finished": False, "failed": True}

    data = dict(project.get("data") or {})
    data["_project_id"] = project_id
    state = build_state(data)

    stage = next_incomplete_stage(data)
    if stage is None:
        state["finished"] = True
        state["customer_message"] = MSG_READY
        state["updated_at"] = _now()
        database.update_project(project_id, None, data)
        return status_payload(data, project_id)

    # A build can be deliberately held after a stage so the customer can read
    # what has been produced before more work runs. Reporting progress is
    # always allowed; running the next stage is not.
    # v1.8.1: this works for every stage, not only the manuscript. The
    # step-by-step customer approves each one, so the builder has to be able
    # to stop after any of them and wait. `held_after` returns the stage only
    # once that stage has actually completed, so a hold never masks work in
    # progress.
    if held_after(data, state):
        return status_payload(data, project_id)

    # v1.9.6: waiting for the customer to approve the pictures. Nothing runs,
    # and no attempt is spent, until they do.
    if stage == "visuals" and awaiting_picture_approval(data, state):
        return status_payload(data, project_id)
    if state.get("awaiting_picture_approval") and stage != "visuals":
        # Approved: the wait is over. Clear the flag and carry on.
        state["awaiting_picture_approval"] = False

    rec = _stage_record(state, stage)
    if int(rec.get("attempts") or 0) >= _max_attempts(stage) and rec.get("status") != COMPLETE:
        _release_stage(state, stage, FAILED_FINAL, rec.get("error") or "attempt ceiling reached")
        state["failed"] = True
        state["customer_message"] = MSG_FINAL
        database.update_project(project_id, None, data)
        log.error("build %s stage %s exhausted attempts", project_id, stage)
        return status_payload(data, project_id)

    if not _claim_stage(state, stage):
        # Another worker holds it. Report progress; do not run it twice.
        return status_payload(data, project_id)

    state["current_stage"] = stage
    state["customer_message"] = STAGE_MESSAGES.get(stage, MSG_WORKING)
    state["updated_at"] = _now()
    database.update_project(project_id, None, data)

    runner = STAGE_RUNNERS.get(stage)
    try:
        # v1.8.4. Every picture made by this stage is published under this
        # book. See services.ebook_visual_pipeline.publishing_for_project.
        from services.ebook_visual_pipeline import localize_visual_plan, publishing_for_project

        work = dict(data)
        localize_visual_plan(work, project_id=project_id)
        with publishing_for_project(project_id):
            updated = runner(work, project_id)
        updated["_project_id"] = project_id
        new_state = build_state(updated)
        # A runner (currently only _run_manuscript) can mark a normal, no-error
        # return as "still working, not a retry" -- captured here before the
        # update() below overwrites customer_message with the claim-time
        # default, and popped so it is never persisted or shown as-is.
        still_working = bool(new_state.pop("_no_retry_message", False))
        still_working_message = str(new_state.get("customer_message") or "")
        runner_awaits = bool(new_state.get("awaiting_picture_approval"))
        new_state.update({k: v for k, v in state.items() if k not in ("stages",)})
        if runner_awaits:
            # Set by _run_visuals just now; the claim-time copy must not erase it.
            new_state["awaiting_picture_approval"] = True
        new_state["stages"] = state["stages"]

        if stage_is_validated(updated, stage):
            _release_stage(new_state, stage, COMPLETE)
            new_state["customer_message"] = STAGE_MESSAGES.get(stage, MSG_WORKING)
        elif stage == "visuals" and awaiting_picture_approval(updated, new_state):
            # Prepared and waiting for the customer: not a failure, and it
            # must not count against the stage's attempts.
            _release_stage(new_state, stage, PENDING_CUSTOMER)
            _stage_record(new_state, stage)["attempts"] = 0
            new_state["customer_message"] = MSG_PICTURES_READY
        else:
            # The code ran but the validator is not satisfied. That is not done.
            _release_stage(new_state, stage, FAILED_RECOVERABLE, "stage output did not validate")
            new_state["customer_message"] = still_working_message if still_working else MSG_RETRY
        new_state["updated_at"] = _now()
        database.update_project(project_id, None, updated)
        return status_payload(updated, project_id)

    except Exception as exc:  # noqa: BLE001
        # Private diagnosis; neutral message for the customer.
        log.error(
            "build project=%s build=%s stage=%s attempt=%s failed: %s\n%s",
            project_id, state.get("build_id"), stage, rec.get("attempts"),
            exc, traceback.format_exc(),
        )
        # The runner may have already persisted real progress through its own
        # persist_progress callback before raising -- chapters accepted and
        # saved one at a time, or a full manuscript assembled and quality-
        # checked before a later approval step rejected it. `data` here is
        # the snapshot from BEFORE the runner ran; persisting it now would
        # silently erase whatever the runner already saved during this same
        # attempt, forcing a full, re-billed do-over on every retry. Re-read
        # the database's current state first, so recording this failure only
        # adds the failure -- it never subtracts real, already-saved work.
        fresh_project = database.get_project(project_id)
        fresh_data = dict(fresh_project.get("data") or {}) if fresh_project else data
        fresh_data["_project_id"] = project_id
        fresh_state = build_state(fresh_data)
        fresh_rec = _stage_record(fresh_state, stage)
        final = int(fresh_rec.get("attempts") or 0) >= _max_attempts(stage)
        _release_stage(fresh_state, stage, FAILED_FINAL if final else FAILED_RECOVERABLE, str(exc)[:500])
        fresh_state["customer_message"] = MSG_FINAL if final else MSG_RETRY
        fresh_state["failed"] = final
        fresh_state["updated_at"] = _now()
        database.update_project(project_id, None, fresh_data)
        return status_payload(fresh_data, project_id)


def resume_build(project_id: int) -> dict:
    """The customer's explicit "Resume Build" action.

    This is distinct from the poller's automatic per-checkpoint retries: those
    stop on their own once a stage exhausts MAX_STAGE_ATTEMPTS and the build
    reports failed, which used to leave the customer at a dead end with no way
    forward. Resume clears that one stalled stage's attempt count and hands the
    build straight back to advance_build's normal checkpoint loop -- it never
    runs a stage itself.

    Nothing here touches a stage that already validated, so no completed work
    is redone: research/title/outline stay approved, and inside the manuscript
    stage specifically, already-accepted chapters are never regenerated or
    re-billed (services.ebook_project_workspace.execute_generate_manuscript
    reloads and skips them). Resume only ever gives the one stalled stage a
    fresh set of attempts.
    """
    import database

    project = database.get_project(project_id)
    if not project:
        return {"ok": False, "message": MSG_FINAL, "finished": False, "failed": True}

    data = dict(project.get("data") or {})
    data["_project_id"] = project_id
    state = build_state(data)

    stage = next_incomplete_stage(data)
    if stage is None:
        # Finished by the time the customer clicked Resume; nothing to do.
        state["failed"] = False
        state["updated_at"] = _now()
        database.update_project(project_id, None, data)
        return status_payload(data, project_id)

    rec = _stage_record(state, stage)
    if rec.get("status") != COMPLETE:
        rec["status"] = NOT_STARTED
        rec["attempts"] = 0
        rec["running_since"] = 0
        rec["error"] = ""
    state["failed"] = False
    state["customer_message"] = MSG_RESUMED
    state["updated_at"] = _now()
    database.update_project(project_id, None, data)
    log.info("build %s stage %s resumed by customer action", project_id, stage)
    return status_payload(data, project_id)


# --------------------------------------------------------------------------
# Activity — is anything ACTUALLY happening right now?
#
# The customer saw "Writing your chapters (5 of 9)" with a moving-looking
# screen while nothing at all was running. An indicator that always
# animates is not reassurance, it is the bug: it cannot tell "working"
# apart from "abandoned", which is the single thing the customer needs to
# know.
#
# So this reports the truth, derived from two real signals:
#   * how long ago the build last actually persisted progress, and
#   * whether a durable job holds a live lease (someone owns the work).
#
# Either driver counts. A customer watching the screen advances the build
# from the browser, and the server executor advances it when they are
# away; recent progress proves the first, a live lease proves the second.
# When neither is true, the honest answer is "stalled" -- and the screen
# says so and offers Continue, instead of spinning forever.
# --------------------------------------------------------------------------

ACTIVITY_WORKING = "working"
ACTIVITY_QUEUED = "queued"
ACTIVITY_RETRYING = "retrying"
ACTIVITY_STALLED = "stalled"
ACTIVITY_DONE = "done"
ACTIVITY_FAILED = "failed"

#: Progress more recent than this means something is genuinely running.
#: Comfortably longer than one chapter, so a slow chapter is not mistaken
#: for a stall.
ACTIVE_WITHIN_SECONDS = 90


def _seconds_since(timestamp: str) -> float | None:
    from datetime import datetime, timezone

    text = str(timestamp or "").strip()
    if not text:
        return None
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - when).total_seconds())


def activity_for(project_id: int, data: dict, *, retrying: bool = False) -> dict:
    """What the progress screen should honestly say is happening."""
    state = build_state(data)
    idle_for = _seconds_since(state.get("updated_at"))

    # Derived, not just the persisted flag. status_payload decides "finished"
    # from the rail (next_incomplete_stage is None) and the two must agree: the
    # flag is only written by advance_build, so a build whose LAST stage
    # completed inside an executor drain still had finished=False persisted.
    # The screen then showed a 100% bar reading "Your ebook is ready" beside an
    # indicator saying "Paused" -- the same contradiction between the message
    # and the indicator that v1.7.25 existed to remove (v1.7.27).
    done = bool(state.get("finished"))
    if not done:
        try:
            done = next_incomplete_stage(data) is None
        except Exception:                               # noqa: BLE001
            done = False
    if done:
        return {"state": ACTIVITY_DONE, "spinning": False,
                "label": "Finished", "idle_seconds": idle_for}
    if state.get("failed"):
        return {"state": ACTIVITY_FAILED, "spinning": False,
                "label": "Stopped", "idle_seconds": idle_for}

    job = None
    try:
        from services.jobs.store import QUEUED, RUNNING, get_for_project

        job = get_for_project(int(project_id))
    except Exception:                                   # noqa: BLE001
        job = None                                      # no jobs table yet

    lease_live = False
    queued = False
    if job:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        lease_live = (job.get("status") == "RUNNING"
                      and str(job.get("lease_expires_at") or "") > now)
        queued = job.get("status") == "QUEUED"

    recently_moved = idle_for is not None and idle_for <= ACTIVE_WITHIN_SECONDS

    if retrying and (lease_live or recently_moved):
        return {"state": ACTIVITY_RETRYING, "spinning": True,
                "label": "Retrying a step", "idle_seconds": idle_for}
    if lease_live or recently_moved:
        return {"state": ACTIVITY_WORKING, "spinning": True,
                "label": "Working", "idle_seconds": idle_for}
    if queued:
        return {"state": ACTIVITY_QUEUED, "spinning": True,
                "label": "Picking this back up", "idle_seconds": idle_for}
    return {"state": ACTIVITY_STALLED, "spinning": False,
            "label": "Paused", "idle_seconds": idle_for}


def status_payload(data: dict, project_id: int) -> dict:
    """Everything the customer's screen needs, and nothing they shouldn't see."""
    # v1.9.7: the route hands over the stored project data, which need not
    # carry its own id. Without it the finished PDF and ZIP could not be
    # fetched back from storage, so a finished book (Container Gardening for
    # Beginners) sat at 90% "Picking this back up" for days while its files
    # downloaded fine. The route's id is authoritative.
    if isinstance(data, dict) and int(project_id or 0) > 0:
        try:
            has_id = int(data.get("_project_id") or 0) > 0
        except (TypeError, ValueError):
            has_id = False
        if not has_id:
            data["_project_id"] = int(project_id)
    state = build_state(data)
    stage = next_incomplete_stage(data)
    finished = stage is None
    files = (data.get("exports") or {}).get("files") if isinstance(data.get("exports"), dict) else {}
    files = files if isinstance(files, dict) else {}

    # A recoverable wait is not progress and not failure. The browser needs to
    # tell them apart so it can pause before trying again instead of hammering
    # the stage, and so the customer is told we are retrying rather than
    # watching a progress bar that appears frozen.
    retrying = False
    attempts_left = 0
    if stage and not finished:
        rec = (state.get("stages") or {}).get(stage)
        if isinstance(rec, dict):
            retrying = str(rec.get("status") or "") == FAILED_RECOVERABLE
            attempts_left = max(0, _max_attempts(stage) - int(rec.get("attempts") or 0))

    return {
        "ok": True,
        "project_id": project_id,
        "finished": bool(finished),
        "failed": bool(state.get("failed")),
        "retrying": bool(retrying),
        "activity": activity_for(project_id, data, retrying=bool(retrying)),
        "attempts_left": int(attempts_left),
        "percent": progress_percent(data),
        "message": (
            MSG_READY if finished
            else (STAGE_READY_MESSAGES.get(held_after(data, state), MSG_WORKING)
                  if held_after(data, state)
                  else (state.get("customer_message") or MSG_WORKING))
        ),
        "artifact_state": str(data.get("artifact_state") or "DRAFT"),
        "downloads": {
            "pdf": (files.get("pdf") or {}).get("url") if isinstance(files.get("pdf"), dict) else None,
            "zip": (files.get("zip") or {}).get("url") if isinstance(files.get("zip"), dict) else None,
        },
        # Where "Open Product" points. Served locally; opening it does not
        # generate anything and makes no paid call.
        "preview_url": (
            f"/ebook-workspace/{project_id}/full-preview"
            if str(data.get("ebook_preview_html") or data.get("preview_html") or "").strip()
            else None
        ),
        "title": str(data.get("title") or ""),
        "subtitle": str(data.get("subtitle") or ""),
        # The manuscript is the book. It exists, and is worth showing, long
        # before the PDF does -- so report it as its own milestone rather than
        # leaving the customer with only a percentage.
        "manuscript": _manuscript_milestone(data, project_id),
        # A build may be deliberately held after a stage so the customer can
        # read what has been produced before more work runs.
        "paused_after": str(state.get("paused_after") or ""),
        # The hold, but only once it is actually in effect. The screen shows
        # "waiting for you" from this, never from paused_after alone, which
        # is set while the stage is still being worked on.
        "held_after": held_after(data, state),
        # v1.9.6: the one-click build is waiting for Approve All Visuals.
        "awaiting_picture_approval": bool(stage == "visuals" and awaiting_picture_approval(data, state)),
        "picture_review": (
            _picture_review(data)
            if stage == "visuals" and awaiting_picture_approval(data, state) else None
        ),
    }


def _picture_review(data: dict) -> dict:
    """One sheet: every chosen picture with its chapter and source. Read-only."""
    try:
        from services.ebook_visual_pipeline import visual_review_payload

        review = visual_review_payload(json.loads(json.dumps(data, default=str)))
    except Exception:                                  # noqa: BLE001
        log.exception("could not build the picture review sheet")
        return {"items": [], "approvable": False, "image_sources": []}
    items = []
    for a in review.get("assets") or []:
        credit = a.get("credit") or {}
        items.append({
            "visual_id": a.get("visual_id"),
            "chapter": a.get("chapter"),
            "chapter_index": a.get("chapter_index"),
            "type": a.get("type"),
            "source_label": credit.get("provider_label") or a.get("source_label"),
            "credit": credit,
            "thumb": credit.get("hotlink_preview_url") or a.get("thumb_data_uri") or "",
            "ready": bool(a.get("has_file")) and a.get("match_status") != "reject",
            "replaceable": bool(a.get("replace_enabled")),
        })
    return {
        "items": items,
        "approvable": bool(review.get("approvable")),
        "findings": list(review.get("findings") or [])[:3],
        "image_sources": review.get("image_sources") or [],
    }


def _manuscript_milestone(data: dict, project_id: int) -> dict:
    """Chapter count, word count and a link, once the manuscript is approved."""
    from services.ebook_project_workspace import is_approved

    ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
    text = str(data.get("content") or data.get("ebook") or "")
    ready = bool(text.strip()) and is_approved(ws, "manuscript")
    return {
        "ready": ready,
        "chapters": len(re.findall(r"^##\s+", text, flags=re.M)) if text else 0,
        "words": len(text.split()) if text else 0,
        "url": f"/ebook-workspace/{project_id}/manuscript" if ready else None,
    }


# --------------------------------------------------------------------------
# Unfinished builds — the route back to a stranded book
#
# WHY THIS EXISTS
#
# The build is driven entirely by a browser loop: `_ebookBuildLoop` in
# static/js/app.js calls /advance once per bounded unit (one chapter,
# since v1.7.10). There is no server-side executor. So when the customer
# closes the tab, the loop stops and nothing advances the book again.
#
# That alone would be survivable -- every finished chapter is persisted,
# and reopening the build restarts the loop from the first incomplete
# stage. The problem was that there was no way BACK:
#
#   * the browser remembered the build in sessionStorage, which the
#     browser destroys when the tab closes, and
#   * a half-built ebook has no PDF yet, so
#     database._has_usable_customer_output() is False and it does not
#     appear in Saved Projects at all.
#
# Between them, a book stopped at "Writing your chapters (5 of 9)" had no
# route back on any screen -- which is exactly the live failure this
# function exists to end. The server remembers instead of the browser.
#
# This is a deliberate pre-0B-5 recovery mechanism, not a substitute for
# it. It does not make the build survive a closed tab; it makes the build
# FINDABLE and resumable afterwards. Only a background worker (0B-5) can
# make "you can leave this page" true without the customer returning.
# --------------------------------------------------------------------------

def build_is_unfinished(data: dict) -> bool:
    """True when a build was started, is not finished, and has not failed."""
    state = data.get("ebook_build") if isinstance(data, dict) else None
    if not isinstance(state, dict):
        return False
    if not (state.get("stages") or state.get("build_id") or state.get("started_at")):
        return False
    return not bool(state.get("finished")) and not bool(state.get("failed"))


def unfinished_builds(limit: int = 10) -> list[dict]:
    """Every started-but-unfinished ebook build, newest first. Read-only.

    Deliberately independent of Saved Projects: that list is for finished
    products and requires a real PDF or ZIP on disk, which an unfinished
    book does not have yet.
    """
    import database

    out: list[dict] = []
    try:
        projects = database.list_projects(include_system=False)
    except Exception:
        return out

    for project in projects or []:
        data = project.get("data") if isinstance(project.get("data"), dict) else {}
        if not build_is_unfinished(data):
            continue
        if project.get("system_test") or data.get("system_test"):
            continue
        if project.get("temporary") or data.get("temporary"):
            continue
        state = data.get("ebook_build") or {}
        stage = str(state.get("current_stage") or "")
        out.append({
            "project_id": project.get("id"),
            "name": project.get("name") or data.get("title") or "Your ebook",
            "percent": progress_percent(data),
            "current_stage": stage,
            "message": str(state.get("customer_message") or MSG_WORKING),
            "updated_at": str(state.get("updated_at") or project.get("updated_at") or ""),
            # Nothing is running server-side between requests, so a build
            # the customer is not watching is paused, not working. Saying
            # otherwise is the animated-spinner-forever defect.
            "paused": True,
        })

    out.sort(key=lambda entry: str(entry.get("updated_at") or ""), reverse=True)
    return out[:max(1, int(limit or 10))]
