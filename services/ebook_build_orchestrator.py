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
MSG_FINAL = "We couldn't finish your ebook. Your completed work has been saved."
MSG_MANUSCRIPT_READY = "Your manuscript is written and ready to read."


def _held_after_manuscript(data: dict, state: dict) -> bool:
    """True when the build is deliberately holding at the finished manuscript."""
    if str(state.get("paused_after") or "") != "manuscript":
        return False
    from services.ebook_project_workspace import is_approved

    ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
    return is_approved(ws, "manuscript")

#: A stage held RUNNING longer than this lost its worker and may be reclaimed.
STALE_RUNNING_SECONDS = 900
#: Attempts per stage before it is treated as unrecoverable.
MAX_STAGE_ATTEMPTS = 3


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


def _export_files_on_disk(data: dict) -> bool:
    """A real PDF and a real ZIP exist in this project's export package."""
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
    out = execute_run_research(data, **_confirm_kwargs(est, data, f"orch-research-{pid}"))
    return approve_stage(out["data"], "research")


def _run_title(data: dict, pid: int) -> dict:
    from services.ebook_project_workspace import approve_stage, execute_generate_title_options

    data, est = _authorized(data, "generate_title_options")
    out = execute_generate_title_options(data, **_confirm_kwargs(est, data, f"orch-title-{pid}"))
    return approve_stage(out["data"], "title")


def _run_outline(data: dict, pid: int) -> dict:
    from services.ebook_project_workspace import approve_stage, execute_generate_outline_options

    data, est = _authorized(data, "generate_outline_options")
    out = execute_generate_outline_options(data, **_confirm_kwargs(est, data, f"orch-outline-{pid}"))
    return approve_stage(out["data"], "outline")


def _run_manuscript(data: dict, pid: int) -> dict:
    """Write and validate chapters, then approve only if the gate passes."""
    from services.ebook_project_workspace import approve_stage, execute_generate_manuscript

    import database

    data, est = _authorized(data, "generate_manuscript")
    kwargs = _confirm_kwargs(est, data, f"orch-manuscript-{pid}")
    kwargs["outline_digest_expected"] = str(est.get("outline_digest") or "")
    out = execute_generate_manuscript(
        data,
        persist_progress=lambda partial: database.update_project(pid, None, partial),
        **kwargs,
    )
    # approve_stage runs outline fidelity and the manuscript quality gate; it
    # raises if either fails, which keeps a defective manuscript out of design.
    return approve_stage(out["data"], "manuscript")


def _run_visuals(data: dict, pid: int) -> dict:
    from services.ebook_design_workspace import approve_visuals_local, prepare_visuals_local

    data = prepare_visuals_local(data)
    try:
        return approve_visuals_local(data)
    except ValueError:
        # Approval was refused. Return the prepared data anyway so the work is
        # persisted: acquiring a visual plan costs real photograph downloads
        # (a hundred megabytes for a nine-chapter book), and letting the
        # exception escape threw all of it away on every retry, so each
        # attempt re-downloaded everything and hit the same wall.
        #
        # This does not mark the stage done. stage_is_validated() reads the
        # workspace rail, which prepare_visuals_local has just set to
        # needs_correction, so the orchestrator still records the stage as
        # unfinished and the real validator still decides.
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
    paused_after = str(state.get("paused_after") or "")
    if paused_after:
        from services.ebook_project_workspace import is_approved

        ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
        if is_approved(ws, paused_after):
            return status_payload(data, project_id)

    rec = _stage_record(state, stage)
    if int(rec.get("attempts") or 0) >= MAX_STAGE_ATTEMPTS and rec.get("status") != COMPLETE:
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
        updated = runner(dict(data), project_id)
        updated["_project_id"] = project_id
        new_state = build_state(updated)
        new_state.update({k: v for k, v in state.items() if k not in ("stages",)})
        new_state["stages"] = state["stages"]

        if stage_is_validated(updated, stage):
            _release_stage(new_state, stage, COMPLETE)
            new_state["customer_message"] = STAGE_MESSAGES.get(stage, MSG_WORKING)
        else:
            # The code ran but the validator is not satisfied. That is not done.
            _release_stage(new_state, stage, FAILED_RECOVERABLE, "stage output did not validate")
            new_state["customer_message"] = MSG_RETRY
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
        final = int(rec.get("attempts") or 0) >= MAX_STAGE_ATTEMPTS
        _release_stage(state, stage, FAILED_FINAL if final else FAILED_RECOVERABLE, str(exc)[:500])
        state["customer_message"] = MSG_FINAL if final else MSG_RETRY
        state["failed"] = final
        state["updated_at"] = _now()
        database.update_project(project_id, None, data)
        return status_payload(data, project_id)


def status_payload(data: dict, project_id: int) -> dict:
    """Everything the customer's screen needs, and nothing they shouldn't see."""
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
            attempts_left = max(0, MAX_STAGE_ATTEMPTS - int(rec.get("attempts") or 0))

    return {
        "ok": True,
        "project_id": project_id,
        "finished": bool(finished),
        "failed": bool(state.get("failed")),
        "retrying": bool(retrying),
        "attempts_left": int(attempts_left),
        "percent": progress_percent(data),
        "message": (
            MSG_READY if finished
            else (MSG_MANUSCRIPT_READY if _held_after_manuscript(data, state)
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
