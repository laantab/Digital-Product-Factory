"""Digital Product Factory — Flask backend."""
import os
import re

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, make_response, render_template, request, send_file, send_from_directory
import base64
from io import BytesIO

import database
from services.ad import generate_ad, generate_traffic_content, generate_seven_day_plan, generate_promotion_package, generate_launch_package, PLATFORMS, PLATFORMS_LEGACY, TRAFFIC_GOALS_LEGACY, PROMOTION_GOALS, PLATFORM_LABELS, PROMOTION_GOAL_LABELS
from services.ebook import generate_ebook
from services.market_research import discover_products, market_research
from services.product import (
    apply_crossword_cover_to_saved_data,
    apply_word_search_cover_to_saved_data,
    generate_product,
    normalize_crossword_project_data,
    normalize_word_search_project_data,
    rebuild_word_search_pdf_from_data,
)
from services.ebook_package import (
    EXPORTS_DIR,
    build_ebook_package,
    is_allowed_download,
    render_visual_image,
)
from services.product_plan import generate_product_plan
from services.packaging import (
    build_product_export,
    generate_product_ad_scripts,
    generate_sales_page,
    generate_seller_package,
    project_export_file_path,
    refresh_visual_preview_html,
)
from services.product_cover_agent import (
    cover_image_job,
    compute_cover_fingerprint,
    generate_cover,
    preview_cover,
    regenerate_cover_image_for_cover,
    save_cover,
    validate_cover_project,
)
from services.cover_quality_agent import validate_cover_for_export
from services.cover_agent import apply_cover_to_preview
from services.publishing import build_publishing_preview, template_list
from services.research import research
from services.ebook import _youtube_id
from services.youtube_support import analyze_youtube_video, search_youtube_videos

from routes.crossword_builder import crossword_builder_bp
from routes.word_search_builder import word_search_builder_bp

app = Flask(__name__)
# Coloring-book saves may include large PDF base64; allow up to 64 MB JSON bodies.
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

with app.app_context():
    database.init_db()

app.register_blueprint(word_search_builder_bp)
app.register_blueprint(crossword_builder_bp)


@app.after_request
def _no_store_static(response):
    if request.path.startswith("/static/") and os.environ.get("FLASK_ENV") != "production":
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def _error(message: str, status: int = 400):
    return jsonify({"error": message}), status


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/research")
def research_route():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(research(body.get("keyword", "")))
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("research failed")
        return _error(str(exc), 500)


@app.post("/generate-ebook")
def generate_ebook_route():
    """LEGACY non-workspace Factory ebook generation.

    Cannot create Export Ready workspace ebooks. Workspace manuscripts must
    use POST /ebook-workspace/<id>/generate-manuscript (chapter pipeline).
    """
    body = request.get_json(silent=True) or {}
    try:
        project_id = body.get("project_id")
        if project_id is not None:
            from services.ebook_project_workspace import get_workspace

            project = database.get_project(int(project_id))
            if not project:
                return _error("Project not found.", 404)
            data = dict(project.get("data") or {})
            ws = get_workspace(data)
            if ws is not None:
                return _error(
                    "Workspace ebooks must generate manuscripts through the chapter "
                    "pipeline (/ebook-workspace/<id>/generate-manuscript). "
                    "The one-shot /generate-ebook route is legacy and cannot create "
                    "Export Ready workspace ebooks.",
                    400,
                )
        brief = body.get("contract")
        contract = _brief_to_contract(brief)
        author = (body.get("author") or body.get("author_brand") or "").strip()
        research_notes = (body.get("research_notes") or "").strip()
        if not research_notes and isinstance(brief, dict):
            for key in ("research_notes", "research_summary", "findings", "sources_text"):
                val = brief.get(key)
                if isinstance(val, str) and val.strip():
                    research_notes = val.strip()
                    break
            plan = brief.get("plan") if isinstance(brief.get("plan"), dict) else {}
            if not research_notes and isinstance(plan.get("summary"), str):
                research_notes = plan.get("summary") or ""
        result = generate_ebook(
            body.get("source", ""),
            contract=contract,
            author=author,
            research_notes=research_notes,
        )
        return jsonify(result)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook generation failed")
        return _error(str(exc), 500)


def _ebook_workspace_project_or_404(project_id: int):
    project = database.get_project(project_id)
    if not project:
        return None, (_error("Project not found.", 404), 404)
    if project.get("type") != "ebook" and str((project.get("data") or {}).get("product_type") or "").lower() != "ebook":
        return None, (_error("Not an ebook project.", 400), 400)
    return project, None


@app.post("/ebook-workspace")
def create_ebook_workspace_route():
    """Start a new Ebook Project workspace at Research (no paid call)."""
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_project_workspace import (
            new_workspace,
            sync_document_from_workspace,
            workspace_public_view,
        )

        topic = str(body.get("topic") or "").strip()
        audience = str(body.get("audience") or "").strip()
        outcome = str(body.get("outcome") or "").strip()
        author = str(body.get("author") or "").strip()
        if not topic:
            return _error("Topic is required.", 400)
        name = str(body.get("name") or topic)[:200]
        data = {
            "product_type": "ebook",
            "ebook_project_workspace": True,
            "artifact_state": "DRAFT",
            "artifact_revision": 1,
            "title": topic,
            "subtitle": "",
            "author_brand": author,
            "source": topic,
            "content": "",
            "ebook": "",
            "export_ready": False,
            "ebook_workspace": new_workspace(
                topic=topic,
                audience=audience,
                outcome=outcome,
                author=author,
                budget_cap_usd=float(body.get("budget_cap_usd") or 3.5),
            ),
        }
        data = sync_document_from_workspace(data)
        project = database.create_project(
            name,
            "ebook",
            data,
            user_saved=True,
            system_test=False,
            temporary=False,
        )
        return jsonify(
            {
                "ok": True,
                "project": _enrich_project_artifact_fields(project),
                "workspace": workspace_public_view(project),
            }
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("create ebook workspace failed")
        return _error(str(exc), 500)


@app.get("/ebook-workspace/<int:project_id>")
def get_ebook_workspace_route(project_id: int):
    """Read-only workspace view — never triggers paid calls."""
    try:
        from services.ebook_project_workspace import (
            assert_no_paid_side_effects_on_read,
            ensure_workspace,
            get_workspace,
            sync_document_from_workspace,
            workspace_public_view,
        )

        assert_no_paid_side_effects_on_read()
        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        data = dict(project.get("data") or {})
        if get_workspace(data) is None and data.get("ebook_project_workspace"):
            data = ensure_workspace(data)
            data = sync_document_from_workspace(data)
            project = database.update_project(project_id, None, data) or project
        elif get_workspace(data) is None:
            return _error("This ebook is not an Ebook Project workspace.", 400)
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("get ebook workspace failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/research")
def save_ebook_workspace_research_route(project_id: int):
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_project_workspace import save_research, workspace_public_view

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        data = save_research(dict(project.get("data") or {}), body.get("research") or body)
        project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("save ebook research failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/approve")
def approve_ebook_workspace_stage_route(project_id: int):
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_project_workspace import approve_stage, workspace_public_view

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        stage = str(body.get("stage") or "").strip()
        data = approve_stage(
            dict(project.get("data") or {}),
            stage,
            choice_id=body.get("choice_id"),
        )
        project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("approve ebook stage failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/title")
def edit_ebook_workspace_title_route(project_id: int):
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_project_workspace import edit_title, workspace_public_view

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        data = edit_title(
            dict(project.get("data") or {}),
            title=str(body.get("title") or ""),
            subtitle=str(body.get("subtitle") or ""),
            options=body.get("title_options"),
        )
        project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("edit ebook title failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/outline")
def edit_ebook_workspace_outline_route(project_id: int):
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_project_workspace import edit_outline, workspace_public_view

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        chapters = body.get("chapters") or body.get("outline") or []
        data = edit_outline(
            dict(project.get("data") or {}),
            chapters=list(chapters),
            option_id=body.get("option_id") or body.get("choice_id"),
        )
        project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("edit ebook outline failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/estimate-cost")
def estimate_ebook_workspace_cost_route(project_id: int):
    """Return a cost estimate + confirmation token. Does not spend."""
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_project_workspace import estimate_paid_action, workspace_public_view

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        action = str(body.get("action") or "").strip()
        data = dict(project.get("data") or {})
        data["_project_id"] = project_id
        result = estimate_paid_action(data, action)
        # Persist pending estimate only (still zero paid spend).
        project = database.update_project(project_id, None, data) or project
        result["workspace"] = workspace_public_view(project)
        return jsonify(result)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook cost estimate failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/cancel-estimate")
def cancel_ebook_workspace_estimate_route(project_id: int):
    """Cancel a pending cost estimate without spending."""
    try:
        from services.ebook_project_workspace import cancel_paid_estimate, workspace_public_view

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        data = cancel_paid_estimate(dict(project.get("data") or {}))
        project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("cancel ebook estimate failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/generate-manuscript")
def generate_ebook_workspace_manuscript_route(project_id: int):
    """Execute confirmed manuscript generation (server-authoritative)."""
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_project_workspace import (
            execute_generate_manuscript,
            workspace_public_view,
        )

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        data = dict(project.get("data") or {})
        out = execute_generate_manuscript(
            data,
            confirmation_token=str(body.get("confirmation_token") or ""),
            expected_artifact_id=str(body.get("expected_artifact_id") or body.get("artifact_id") or ""),
            expected_revision=int(body.get("expected_revision") or body.get("artifact_revision") or 0),
            outline_digest_expected=str(body.get("outline_digest") or ""),
            max_authorized_usd=float(body.get("max_authorized_usd") or body.get("estimated_max_usd") or 0),
            idempotency_key=str(body.get("idempotency_key") or ""),
        )
        data = out["data"]
        project = database.update_project(project_id, None, data) or project
        return jsonify(
            {
                "ok": True,
                "duplicate": bool(out.get("duplicate")),
                "result": out.get("result") or {},
                "workspace": workspace_public_view(project),
            }
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook workspace manuscript generation failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/correct-manuscript")
def correct_ebook_workspace_manuscript_route(project_id: int):
    """Execute confirmed manuscript correction against the approved outline."""
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_project_workspace import (
            execute_correct_manuscript,
            workspace_public_view,
        )

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        data = dict(project.get("data") or {})
        data["_project_id"] = project_id
        out = execute_correct_manuscript(
            data,
            confirmation_token=str(body.get("confirmation_token") or ""),
            expected_artifact_id=str(body.get("expected_artifact_id") or body.get("artifact_id") or ""),
            expected_revision=int(body.get("expected_revision") or body.get("artifact_revision") or 0),
            outline_digest_expected=str(body.get("outline_digest") or ""),
            max_authorized_usd=float(body.get("max_authorized_usd") or body.get("estimated_max_usd") or 0),
            idempotency_key=str(body.get("idempotency_key") or ""),
        )
        data = out["data"]
        project = database.update_project(project_id, None, data) or project
        return jsonify(
            {
                "ok": True,
                "duplicate": bool(out.get("duplicate")),
                "result": out.get("result") or {},
                "workspace": workspace_public_view(project),
            }
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook workspace manuscript correction failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/seed-acceptance")
def seed_ebook_acceptance_workspace_route():
    """Seed approved pre-manuscript inputs into an existing empty workspace.

    Requires ``target_project_id`` and ``source_project_id``. Never upserts the
    frozen live manuscript project. Copies research/title/outline only.
    """
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_project_workspace import (
            MANUSCRIPT_AUTH_MAX_USD,
            seed_pre_manuscript_into_project,
            workspace_public_view,
        )

        target_id = body.get("target_project_id")
        source_id = body.get("source_project_id")
        if target_id is None or source_id is None:
            return _error(
                "target_project_id and source_project_id are required. "
                "Unlabeled upsert is disabled to protect the frozen live project.",
                400,
            )
        cap = body.get("budget_cap_usd")
        project = seed_pre_manuscript_into_project(
            database,
            int(target_id),
            source_project_id=int(source_id),
            budget_cap_usd=float(cap if cap is not None else MANUSCRIPT_AUTH_MAX_USD),
        )
        return jsonify(
            {
                "ok": True,
                "project": _enrich_project_artifact_fields(project),
                "workspace": workspace_public_view(project),
            }
        )
    except FileNotFoundError as exc:
        return _error(str(exc), 404)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("seed ebook acceptance failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/visuals")
def ebook_workspace_visuals_route(project_id: int):
    """Approve manuscript-derived visuals. No paid image generation."""
    try:
        from services.ebook_design_workspace import approve_visuals_local
        from services.ebook_project_workspace import workspace_public_view

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        data = approve_visuals_local(dict(project.get("data") or {}))
        project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook visuals failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/cover")
def ebook_workspace_cover_route(project_id: int):
    """Generate or reject a deterministic local cover. No paid image generation."""
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_design_workspace import generate_and_stage_cover, reject_cover
        from services.ebook_project_workspace import workspace_public_view

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        action = str(body.get("action") or "generate").strip().lower()
        data = dict(project.get("data") or {})
        if action == "reject":
            data = reject_cover(data)
        else:
            data = generate_and_stage_cover(data)
        project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook cover failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/design")
def ebook_workspace_design_route(project_id: int):
    """Select a local professional theme. No paid calls."""
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_design_workspace import select_and_stage_theme
        from services.ebook_project_workspace import workspace_public_view

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        theme_id = str(body.get("theme_id") or "").strip()
        data = select_and_stage_theme(dict(project.get("data") or {}), theme_id)
        project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook design failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/preview")
def ebook_workspace_preview_route(project_id: int):
    """Render designed preview from the approved manuscript. No paid calls."""
    try:
        from services.ebook_design_workspace import build_preview
        from services.ebook_project_workspace import workspace_public_view

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        data = build_preview(dict(project.get("data") or {}))
        project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook preview failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/preflight")
def ebook_workspace_preflight_route(project_id: int):
    """Run hard design preflight. Server status is authoritative."""
    try:
        from services.ebook_design_workspace import run_preflight_stage
        from services.ebook_project_workspace import workspace_public_view

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        data = run_preflight_stage(dict(project.get("data") or {}))
        project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook preflight failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/rewind")
def ebook_workspace_rewind_route(project_id: int):
    """Go backward without losing approved manuscript work."""
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_design_workspace import rewind_to_stage
        from services.ebook_project_workspace import workspace_public_view

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        data = rewind_to_stage(dict(project.get("data") or {}), str(body.get("stage") or ""))
        project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook rewind failed")
        return _error(str(exc), 500)


def _brief_to_contract(brief):
    """Map a research/plan brief dict (the saved project data) to an EbookContract.

    Falls back to None when no brief is supplied. Never raises — bad input
    becomes sensible defaults so the ebook service still works without a brief.
    """
    if not isinstance(brief, dict):
        return None
    plan = brief.get("plan") or {}
    op = brief.get("opportunity") or {}
    reco = brief.get("recommendation") or {}
    topic = (
        plan.get("product_title")
        or op.get("product_idea")
        or reco.get("suggested_title")
        or op.get("niche")
        or ""
    )
    audience = plan.get("target_audience") or op.get("target_audience") or ""
    reader_problem = (
        plan.get("customer_problem")
        or op.get("customer_problem")
        or ""
    )
    desired_transformation = (
        plan.get("product_promise")
        or plan.get("main_transformation")
        or reco.get("next_step")
        or ""
    )
    tone = plan.get("tone") or "professional"
    reading_level = plan.get("reading_level") or "General adult"
    # Chapter direction can be a list (preferred) or a string. EbookContract
    # stores required_chapter_angles as list[str]; we feed the prompts there.
    # The user-required framing (customer problem, product promise, sales angle)
    # is added as additional chapter angles so it reaches the model alongside
    # the planned chapter_direction.
    raw_chapters = (
        plan.get("chapter_direction")
        or reco.get("next_step")
        or op.get("why_opportunity")
        or ""
    )
    if isinstance(raw_chapters, list):
        chapter_angles = [str(x) for x in raw_chapters if str(x).strip()]
    elif isinstance(raw_chapters, str) and raw_chapters.strip():
        chapter_angles = [raw_chapters.strip()]
    else:
        chapter_angles = []
    for framing in (reader_problem, desired_transformation, plan.get("sales_angle") or op.get("sales_angle")):
        if framing and framing.strip() and framing.strip() not in chapter_angles:
            chapter_angles.append(framing.strip())

    # Build the contract via the existing factory (single source of truth),
    # then layer any brief-specific chapter angles on top — build_contract picks
    # topic-category angles automatically; the brief's own angles ride alongside.
    from services.ebook_contract import build_contract, EbookContract
    contract = build_contract(
        topic=topic or "Untitled",
        audience=audience,
        tone=tone,
        reading_level=reading_level,
        reader_problem=reader_problem,
        desired_transformation=desired_transformation,
        chapter_count=int(plan.get("chapters") or 6) if str(plan.get("chapters") or "6").isdigit() else 6,
        # Brief carries research findings — enable research-backed claims mode
        # so chapters may use those notes (still no invented studies).
        research_requested=True,
        worksheet_required=bool(plan.get("include_worksheets")),
        worksheet_expectation=(
            "Each chapter should end with a brief action-steps section containing "
            "3-5 concrete prompts the reader can complete immediately."
            if plan.get("include_worksheets") else ""
        ),
    )
    if chapter_angles:
        merged = list(contract.required_chapter_angles) + chapter_angles
        contract = EbookContract(
            topic=contract.topic,
            audience=contract.audience,
            reader_problem=contract.reader_problem or reader_problem,
            desired_transformation=contract.desired_transformation or desired_transformation,
            reading_level=contract.reading_level,
            tone=contract.tone,
            ebook_length=contract.ebook_length,
            chapter_count=contract.chapter_count,
            topic_category=contract.topic_category,
            risk_categories=contract.risk_categories,
            research_requested=contract.research_requested,
            claims_allowed=contract.claims_allowed,
            claims_forbidden=contract.claims_forbidden,
            disclaimer_required=contract.disclaimer_required,
            disclaimer_text=contract.disclaimer_text,
            required_chapter_angles=merged,
            worksheet_required=contract.worksheet_required,
            worksheet_expectation=contract.worksheet_expectation,
            marketing_claim_limits=contract.marketing_claim_limits,
        )
    return contract


@app.post("/generate-ad")
def generate_ad_route():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(generate_ad(body.get("details", "")))
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ad generation failed")
        return _error(str(exc), 500)


@app.post("/generate-traffic-content")
def generate_traffic_content_route():
    """Generate platform-specific free traffic content from a product/funnel."""
    body = request.get_json(silent=True) or {}
    try:
        result = generate_traffic_content(
            funnel_context=body.get("funnel_context", {}),
            platforms=body.get("platforms", []),
            traffic_goal=body.get("traffic_goal", ""),
            num_pieces=int(body.get("num_pieces", 5) or 5),
        )
        # Also generate the 7-day plan
        plan = generate_seven_day_plan(
            funnel_context=body.get("funnel_context", {}),
            platforms=body.get("platforms", []),
            traffic_goal=body.get("traffic_goal", ""),
        )
        result["seven_day_plan"] = plan.get("plan", {})
        return jsonify(result)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("traffic content generation failed")
        return _error(str(exc), 500)


@app.post("/save-ad-set")
def save_ad_set_route():
    """Save a generated ad set linked to a product project."""
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "Ad Set").strip()
    product_project_id = body.get("product_project_id")
    ad_content = body.get("ad_content", {})
    funnel_context = body.get("funnel_context", {})
    if not ad_content:
        return _error("No ad content to save.", 400)
    data = {
        "ad_content": ad_content,
        "funnel_context": funnel_context,
        "platforms": ad_content.get("platforms", []),
        "traffic_goal": ad_content.get("traffic_goal", ""),
        "product_project_id": product_project_id,
    }
    if product_project_id:
        # Update the linked product project to store the ad set reference
        try:
            proj = database.get_project(int(product_project_id))
            if proj:
                pdata = dict(proj.get("data") or {})
                pdata["ad_set"] = {"name": name, "platforms": data["platforms"], "traffic_goal": data["traffic_goal"]}
                _persist_product_data(proj, pdata)
        except Exception:  # noqa: BLE001
            pass  # Non-fatal: save the ad set independently
        new_proj = database.create_project(name, "ad_set", data)
    else:
        new_proj = database.create_project(name, "ad_set", data)
    return jsonify({"id": new_proj["id"], "name": name}), 201


@app.post("/generate-promotion-package")
def generate_promotion_package_route():
    """Generate a full Product Promotion Package (all sections)."""
    body = request.get_json(silent=True) or {}
    try:
        result = generate_promotion_package(
            funnel_context=body.get("funnel_context", {}),
            promotion_goal=body.get("promotion_goal", "freebie_signups"),
            include_paid_ads=bool(body.get("include_paid_ads", False)),
        )
        return jsonify(result)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("promotion package generation failed")
        return _error(str(exc), 500)


@app.post("/generate-launch-package")
def generate_launch_package_route():
    """Generate a complete MiloTree-style launch package for a saved product.

    Takes a project_id, loads the product data, and generates all 8 sections:
    freebie builder, opt-in page, sales page, thank-you/tripwire, ad package,
    email sequence, delivery checklist, and launch checklist.
    """
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    if not project_id:
        return _error("project_id is required.", 400)

    project = database.get_project(int(project_id))
    if not project:
        return _error("Project not found.", 404)

    data = project.get("data") or {}
    funnel_context = {
        "product_title": data.get("title") or project.get("name") or "Untitled Product",
        "audience": data.get("audience") or "",
        "problem": data.get("problem") or "",
        "product_promise": data.get("promise") or data.get("product_promise") or "",
        "product_description": data.get("description") or data.get("product_description") or "",
        "price": data.get("price") or "",
        "freebie_name": data.get("freebie_name") or data.get("freebie") or "",
        "landing_page_url": data.get("landing_page_url") or "",
        "paid_product_url": data.get("paid_product_url") or "",
        "tone": data.get("tone") or "empathetic and understanding",
    }

    try:
        result = generate_launch_package(
            funnel_context=funnel_context,
            promotion_goal=body.get("promotion_goal", "sell_paid_product"),
        )
        # Store the result in the project data so it can be re-downloaded.
        # Use the shared persistence boundary so approved artifacts stay immutable.
        data = dict(data)
        data["_launch_package"] = result
        _persist_product_data(project, data)
        return jsonify({"ok": True, "package": result})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("launch package generation failed")
        return _error(str(exc), 500)


@app.get("/download-launch-package/<int:project_id>")
def download_launch_package(project_id: int):
    """Download the stored launch package for a project as a ZIP."""
    project = database.get_project(project_id)
    if not project:
        return _error("Project not found.", 404)

    data = project.get("data") or {}
    pkg = data.get("_launch_package")
    if not pkg:
        return _error("No launch package found. Please generate one first.", 404)

    import base64
    from io import BytesIO
    import zipfile, json

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        def add_text(name: str, content: str) -> None:
            zf.writestr(name, content.encode("utf-8") if isinstance(content, str) else content)

        # ── 1. Freebie Builder ───────────────────────────────────────────────
        fb = pkg.get("freebie", {})
        freebie_md = (
            f"# Freebie Builder\n\n"
            f"**Freebie Name:** {fb.get('freebie_name', '[Name your freebie]')}\n"
            f"**Format:** {fb.get('freebie_format', '[Format]')}\n\n"
            f"## Description\n{fb.get('freebie_description', '')}\n\n"
            f"## Page Count / Size\n{fb.get('freebie_pages', '')}\n\n"
            f"## Why This Freebie Works\n{fb.get('why_this_freebie', '')}\n\n"
            f"## Opt-In Page Copy\n"
            f"**Headline:** {fb.get('freebie_optin_headline', '')}\n"
            f"**Subheadline:** {fb.get('freebie_optin_subheadline', '')}\n"
        )
        add_text("freebie_builder.md", freebie_md)

        # ── 2. Opt-in Page Copy ──────────────────────────────────────────────
        op = pkg.get("optin_page", {})
        optin_md = (
            f"# Opt-In Page Copy\n\n"
            f"**Headline:** {op.get('headline', '')}\n"
            f"**Subheadline:** {op.get('subheadline', '')}\n\n"
            f"## What They Get\n"
        )
        items = op.get("what_you_get") or []
        for item in items:
            optin_md += f"- {item}\n"
        optin_md += (
            f"\n**Sign-up CTA:** {op.get('signup_cta', '')}\n\n"
            f"## Trust Section\n{op.get('trust_section', '')}\n\n"
            f"## FAQ\n"
        )
        faq = op.get("faq") or []
        for i, item in enumerate(faq):
            q = item.get("q", "") if isinstance(item, dict) else ""
            a = item.get("a", "") if isinstance(item, dict) else ""
            optin_md += f"**Q: {q}**\n{a}\n\n"
        add_text("optin_page_copy.txt", optin_md)

        # ── 3. Sales Page Copy ───────────────────────────────────────────────
        sp = pkg.get("sales_page", {})
        sales_md = (
            f"# Sales Page Copy\n\n"
            f"**Headline:** {sp.get('headline', '')}\n\n"
            f"## Problem\n{sp.get('problem_section', '')}\n\n"
            f"## Promise\n{sp.get('promise_section', '')}\n\n"
            f"## What's Included\n"
        )
        included = sp.get("whats_included") or []
        for item in included:
            sales_md += f"- {item}\n"
        sales_md += (
            f"\n**Who Is This For:**\n{sp.get('who_is_this_for', '')}\n\n"
            f"**Price:** {sp.get('price_display', '')}\n\n"
            f"**CTA Button:** {sp.get('cta_button', '')}\n\n"
            f"**Guarantee:**\n{sp.get('guarantee', '')}\n\n"
            f"## FAQ\n"
        )
        sp_faq = sp.get("faq") or []
        for item in sp_faq:
            q = item.get("q", "") if isinstance(item, dict) else ""
            a = item.get("a", "") if isinstance(item, dict) else ""
            sales_md += f"**Q: {q}**\n{a}\n\n"
        add_text("sales_page_copy.txt", sales_md)

        # ── 4. Thank-You / Tripwire ──────────────────────────────────────────
        tw = pkg.get("thank_you_tripwire", {})
        tripwire_md = (
            f"# Thank-You Page / Tripwire\n\n"
            f"## Thank You Message\n{tw.get('thank_you_message', '')}\n\n"
            f"## Tripwire Offer\n"
            f"**Headline:** {tw.get('tripwire_headline', '')}\n\n"
            f"**Description:** {tw.get('tripwire_description', '')}\n\n"
            f"**Price:** {tw.get('tripwire_price', '')}\n\n"
            f"**CTA:** {tw.get('tripwire_cta', '')}\n\n"
            f"**No-thanks link:** {tw.get('no_thanks_link', '')}\n"
        )
        add_text("thank_you_page_copy.txt", tripwire_md)

        # ── 5. Ad Package (reuse existing text export) ───────────────────────
        from services.ad import _build_promotion_text  # noqa: PLC0415
        # Reconstruct funnel_context from project data for the text export
        lp_funnel = {
            "product_title": data.get("title") or project.get("name") or "Untitled Product",
            "audience": data.get("audience") or "",
            "problem": data.get("problem") or "",
            "product_promise": data.get("product_promise") or "",
            "product_description": data.get("description") or "",
            "price": data.get("price") or "",
            "freebie_name": data.get("freebie_name") or "",
            "landing_page_url": data.get("landing_page_url") or "",
            "paid_product_url": data.get("paid_product_url") or "",
            "tone": data.get("tone") or "empathetic and understanding",
        }
        ad_text = _build_promotion_text(pkg.get("ad_package", {}), lp_funnel)
        add_text("ad_package.txt", ad_text)

        # ── 6. Email Sequence ────────────────────────────────────────────────
        es = pkg.get("email_sequence", {})
        emails = es.get("emails") or []
        email_md = "# Email Follow-Up Sequence\n\n"
        for i, em in enumerate(emails):
            subj = em.get("subject", f"Email {i+1}")
            body_text = em.get("body", "")
            email_md += f"---\n## {subj}\n\n{body_text}\n\n"
        add_text("email_sequence.txt", email_md)

        # ── 7. Delivery Checklist ────────────────────────────────────────────
        add_text("delivery_checklist.txt", pkg.get("delivery_checklist", ""))

        # ── 8. Launch Checklist ───────────────────────────────────────────────
        add_text("launch_checklist.txt", pkg.get("launch_checklist", ""))

        # ── metadata.json ────────────────────────────────────────────────────
        meta = {
            "product_title": pkg.get("product_title", ""),
            "promotion_goal": pkg.get("promotion_goal", ""),
            "generated_at": project.get("updated_at", ""),
            "project_id": project_id,
        }
        add_text("metadata.json", json.dumps(meta, indent=2))

    buf.seek(0)
    filename = f"launch_package_{project['name'][:40].replace(' ', '_').replace('/', '-')}.zip"
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
    )


@app.post("/market-research")
def market_research_route():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            market_research(
                body.get("niche", ""),
                body.get("audience", ""),
                body.get("product_type", ""),
            )
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("market research failed")
        return _error(str(exc), 500)


@app.post("/generate-product")
def generate_product_route():
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    fields = body.get("fields") or {}
    # Product types that are hidden from the public picker (UI-side `hidden: true`
    # in static/js/app.js). If a caller hits them directly, return a clear "not
    # ready" error so we never silently produce a placeholder product.
    # spelling_worksheet: no end-to-end acceptance contract in acceptance_manifest
    # (code retained; public builder + /generate-product guard hide it).
    _HIDDEN_PRODUCT_TYPES = {
        "marketing_kit",
        "cover_design",
        "flip_book",
        "planner",
        "spelling_worksheet",
    }
    _requested = (body.get("product_type", "") or "").strip()
    if _requested in _HIDDEN_PRODUCT_TYPES:
        return _error("This product type is not ready yet.", 400)
    from services.quality.artifact_state import ArtifactStateError

    # Existing project: enforce write policy before any generation work.
    if project_id:
        project = database.get_project(int(project_id))
        if project:
            try:
                _require_content_mutation_allowed(
                    project.get("data") or {},
                    action="regenerate product content",
                )
            except ArtifactStateError as exc:
                return _error(str(exc), 409)
    try:
        result = generate_product(_requested, fields)
        # Stamp canonical digests + revision so Preview/Save/Export share one artifact.
        # New generation is always DRAFT — digests alone must not classify as APPROVED.
        if isinstance(result, dict) and (
            result.get("is_pdf")
            or result.get("pdf_bytes")
            or result.get("product_type")
            in {"math_worksheet", "spelling_worksheet", "word_search", "crossword", "coloring_book"}
        ):
            from services.quality.artifact_identity import stamp_artifact_identity
            from services.quality.artifact_state import ArtifactState

            stamp_artifact_identity(result)
            if not result.get("artifact_state"):
                result["artifact_state"] = ArtifactState.DRAFT.value
        # If a project_id was provided, persist pdf_bytes and package_id so export/download works
        if project_id and result.get("pdf_bytes"):
            project = database.get_project(int(project_id))
            if project:
                data = dict(project.get("data") or {})
                prior_revision = data.get("artifact_revision")
                prior_state = data.get("artifact_state")
                data["pdf_bytes"] = result["pdf_bytes"]
                data["package_id"] = result.get("package_id", "")
                data["filename"] = result.get("filename", "")
                data["product_type"] = body.get("product_type", "")
                data["title"] = result.get("title", "")
                # CRITICAL: persist fields so download/export can determine output format,
                # puzzle count, and cover eligibility rules. Without this, the download
                # pipeline agent cannot read output_format/puzzles and defaults to
                # cover_ineligible=True for crossword books, blocking all downloads.
                data["fields"] = fields
                # Also update is_book / is_pdf from result — is_pdf is the gate that
                # tells build_product_export to use the stored PDF bytes instead of
                # routing to the ebook fallback. Required for crossword, word_search,
                # math_worksheet, spelling_worksheet, coloring_book.
                if "is_book" in result:
                    data["is_book"] = result["is_book"]
                if result.get("is_pdf"):
                    data["is_pdf"] = True
                for _k in (
                    "content_digest",
                    "asset_manifest_digest",
                    "artifact_id",
                    "problems",
                    "challenge_problems",
                    "words",
                    "pages",
                ):
                    if _k in result:
                        data[_k] = result[_k]
                # Keep current draft revision; never auto-bump from Generate.
                if prior_revision is not None:
                    data["artifact_revision"] = prior_revision
                elif "artifact_revision" in result:
                    data["artifact_revision"] = result["artifact_revision"]
                # Preserve explicit DRAFT on the working revision (never auto-approve).
                from services.quality.artifact_state import ArtifactState

                if prior_state:
                    data["artifact_state"] = prior_state
                elif result.get("artifact_state"):
                    data["artifact_state"] = result["artifact_state"]
                else:
                    data["artifact_state"] = ArtifactState.DRAFT.value
                _persist_draft_content_mutation(project_id, data)
        return jsonify(result)
    except ArtifactStateError as exc:
        return _error(str(exc), 409)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("product generation failed")
        return _error(str(exc), 500)


@app.post("/enhance-ebook")
def enhance_ebook_route():
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    content = body.get("content") or ""
    fields = body.get("fields") or {}
    project_id = body.get("project_id")
    if not content.strip():
        return _error("Ebook content is required.", 400)
    from services.quality.artifact_state import ArtifactStateError

    if project_id:
        project = database.get_project(int(project_id))
        if project:
            try:
                _require_content_mutation_allowed(
                    project.get("data") or {},
                    action="enhance ebook content",
                )
            except ArtifactStateError as exc:
                return _error(str(exc), 409)
    try:
        result = build_ebook_package(title, content, fields)
        # Step-by-step quality / originality pipeline (no paid APIs)
        from services.ebook_pipeline_agents import run_ebook_quality_pipeline

        pipeline = run_ebook_quality_pipeline(
            title=title or "Ebook",
            manuscript=content,
            fields=fields,
            data={
                "research_notes": fields.get("research_notes") or body.get("research_notes"),
                "research_brief": body.get("contract") or fields.get("research_brief"),
                "source_content": body.get("source_content") or fields.get("source_content"),
                "author_brand": fields.get("author_brand") or body.get("author_brand"),
            },
            visual_plan=result.get("visual_plan"),
            cover_design=result.get("cover_design"),
            require_visuals=True,
            require_cover=True,
            block_on_originality=True,
        )
        result["pipeline"] = pipeline.to_dict()
        result["originality"] = {}
        for step in pipeline.steps:
            if step.step == "originality":
                result["originality"] = step.details
                break
        # Persist enhanced content to project so export can use it
        if project_id:
            project = database.get_project(int(project_id))
            if project:
                data = dict(project.get("data") or {})
                data["content"] = content
                data["preview_html"] = result.get("preview_html", "")
                data["visual_plan"] = result.get("visual_plan", "")
                data["product_summary"] = result.get("product_summary", "")
                data["package_id"] = result.get("package_id", "")
                data["cover_design"] = result.get("cover_design") or data.get("cover_design")
                data["quality_score"] = result.get("quality_score")
                data["quality_blocking"] = result.get("quality_blocking")
                data["pipeline"] = pipeline.to_dict()
                if fields.get("author_brand"):
                    data["author_brand"] = fields.get("author_brand")
                _persist_draft_content_mutation(int(project_id), data)
        return jsonify(result)
    except ArtifactStateError as exc:
        return _error(str(exc), 409)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook enhancement failed")
        return _error(str(exc), 500)


@app.post("/discover-products")
def discover_products_route():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            discover_products(
                body.get("interest", ""),
                body.get("audience", ""),
                body.get("product_type", ""),
                body.get("difficulty", ""),
                body.get("goal", ""),
                body.get("niche", ""),
            )
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("product discovery failed")
        return _error(str(exc), 500)


@app.post("/youtube/analyze")
def youtube_analyze_route():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            analyze_youtube_video(
                body.get("url", ""),
                body.get("ebook_topic", ""),
                body.get("chapter_topic", ""),
            )
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("youtube analyze failed")
        return _error(str(exc), 500)


@app.post("/youtube/search")
def youtube_search_route():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            search_youtube_videos(
                body.get("topic", ""),
                body.get("ebook_topic", ""),
                body.get("chapter_topic", ""),
            )
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("youtube search failed")
        return _error(str(exc), 500)


@app.post("/youtube/save-resource")
def youtube_save_resource_route():
    body = request.get_json(silent=True) or {}
    resource = body.get("resource") or {}

    def _text(key):
        value = resource.get(key, "")
        return value.strip() if isinstance(value, str) else ""

    video_url = _text("video_url")
    if not video_url:
        return _error("A video URL is required to save a resource.", 400)
    if not _youtube_id(video_url):
        return _error("Only YouTube video links can be saved as resources.", 400)
    video_title = _text("video_title")
    points = resource.get("key_teaching_points")
    if isinstance(points, str):
        points = [points] if points.strip() else []
    elif isinstance(points, list):
        points = [str(p).strip() for p in points if str(p).strip()]
    else:
        points = []
    create_qr = bool(body.get("create_qr"))
    record = {
        "video_title": video_title,
        "video_url": video_url,
        "chapter_placement": _text("chapter_placement"),
        "summary": _text("summary"),
        "key_teaching_points": points,
        "caption": _text("caption"),
        "resource_note": _text("resource_note"),
    }
    if create_qr:
        record["qr_code"] = {
            "status": "placeholder",
            "encodes": video_url,
            "label": video_title or "Video resource",
            "note": (
                "Placeholder QR record. Publishing Studio will render the QR "
                "code in the ebook."
            ),
        }
    name = video_title or "YouTube resource"
    return jsonify(database.create_project(name, "youtube_resource", record)), 201


@app.post("/generate-product-plan")
def generate_product_plan_route():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(generate_product_plan(body.get("form") or {}))
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("product plan generation failed")
        return _error(str(exc), 500)


@app.post("/save-product-plan")
def save_product_plan_route():
    body = request.get_json(silent=True) or {}
    data = body.get("data") or {}
    plan = data.get("plan") or {}
    name = (body.get("name") or plan.get("product_title") or "Untitled Product Plan").strip()
    if not plan:
        return _error("A generated product plan is required before saving.", 400)
    return jsonify(database.create_project(name, "product_plan", data)), 201


# ----- Publishing Studio -----


@app.get("/publishing/templates")
def publishing_templates_route():
    return jsonify(template_list())


@app.post("/generate-publishing")
def generate_publishing_route():
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    if not project_id:
        return _error("Select a saved Product Project to publish.", 400)
    try:
        project = database.get_project(int(project_id))
    except (TypeError, ValueError):
        return _error("Invalid project id.", 400)
    if not project:
        return _error("Project not found.", 404)

    aid_projects = []
    for aid_id in body.get("visual_aid_ids") or []:
        try:
            aid = database.get_project(int(aid_id))
        except (TypeError, ValueError):
            continue
        if aid and aid.get("type") == "youtube_resource":
            aid_projects.append(aid)

    try:
        return jsonify(
            build_publishing_preview(
                project,
                body.get("template", ""),
                body.get("details") or {},
                aid_projects,
            )
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("publishing preview failed")
        return _error(str(exc), 500)


@app.post("/save-publishing")
def save_publishing_route():
    body = request.get_json(silent=True) or {}
    data = body.get("data") or {}
    if not data.get("preview_html"):
        return _error("Generate a publishing preview before saving.", 400)
    details = data.get("details") or {}
    name = (
        body.get("name")
        or details.get("product_title")
        or data.get("source_name")
        or "Untitled Layout"
    ).strip()
    return jsonify(database.create_project(name, "publishing_layout", data)), 201


# ----- Ebook export downloads -----

# Accept uuid hex AND generation slugs (e.g. farm_friends_animals_1786212765).
# Reject dots/slashes so package_id cannot escape EXPORTS_DIR.
_PACKAGE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,127}$")


@app.get("/download/<package_id>/<filename>")
def download_export_route(package_id: str, filename: str):
    """
    Download Pipeline Agent — every file served to the user passes through here.

    Single controlled entry point for ALL downloads:
      1. DPA resolves context (project lookup, cover eligibility)
      2. DPA validates (via Final Output Gate rules)
      3. DPA records audit log entry
      4. Serve only if valid; block or repair if invalid
      5. Never serve a bad file silently
    """
    if not _PACKAGE_ID_RE.match(package_id or ""):
        return _error("Invalid download id.", 400)
    if not is_allowed_download(filename):
        return _error("Unknown export file.", 404)

    directory = os.path.join(EXPORTS_DIR, package_id)
    file_path = os.path.join(directory, filename)
    # Defense in depth: resolved path must stay under exports/
    try:
        exports_root = os.path.realpath(EXPORTS_DIR)
        real_file = os.path.realpath(file_path)
        if not real_file.startswith(exports_root + os.sep):
            return _error("Invalid download id.", 400)
    except OSError:
        return _error("Export file not found.", 404)
    if not os.path.isfile(file_path):
        return _error("Export file not found.", 404)

    # ── DOWNLOAD PIPELINE AGENT ───────────────────────────────────────────────
    from services.quality.download_pipeline_agent import pipeline_download
    context, result = pipeline_download(
        route="/download/<package_id>/<filename>",
        filename=filename,
        file_path=file_path,
        package_id=package_id,
    )

    if result.status == "blocked":
        return jsonify(result.error_response or {
            "error": "download_blocked",
            "message": result.message,
            "violations": result.violations,
        }), result.status_code or 403

    if result.status == "repaired":
        # Auto-corrected: serve the regenerated bytes
        response = make_response(result.served_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        return response

    # Passed: serve from disk
    as_attachment = not filename.startswith("img_")
    return send_from_directory(directory, filename, as_attachment=as_attachment)


@app.post("/render-visual-image")
def render_visual_image_route():
    body = request.get_json(silent=True) or {}
    package_id = (body.get("package_id") or "").strip()
    visual_id = (body.get("visual_id") or "").strip()
    prompt = (body.get("prompt") or "").strip()
    if not package_id or not visual_id:
        return _error("package_id and visual_id are required.", 400)
    try:
        url = render_visual_image(package_id, visual_id, prompt)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("visual image rendering failed")
        return _error(str(exc), 500)
    if not url:
        return jsonify({"visual_id": visual_id, "asset_url": None, "ok": False})
    return jsonify({"visual_id": visual_id, "asset_url": url, "ok": True})


# ----- Post-generation product workflow (Next Steps) -----


def _load_product_project(body):
    """Load a saved project by id. All Next Steps actions persist back into the
    SAME record so artifacts are never duplicated."""
    project_id = body.get("project_id")
    if project_id is None:
        raise ValueError("project_id is required. Save the project first.")
    project = database.get_project(int(project_id))
    if not project:
        raise ValueError("Project not found.")
    # Plans / research / ads are not exportable products. Allowing export here
    # created orphan package folders that /download then blocked (403), so the
    # Saved Projects "Download PDF" button looked broken for "the book".
    ptype = str(project.get("type") or "").strip().lower()
    if ptype not in {"product", "ebook"}:
        raise ValueError(
            "Only saved products can be downloaded. Open this plan and build "
            "the product in Product Factory first."
        )
    return project


def _enforce_save_persistence_boundary(
    existing_data, incoming_data, *, allow_revision_transition=False
):
    """Shared Save / persist policy: artifact state + identity immutability.

    Used by ``_persist_product_data`` and PUT ``update_project_route`` so
    seller/launch/Next Steps and project Save cannot bypass Gate 11 state rules.
    Does not call ``transition_artifact_revision`` or regenerate content.

    ``allow_revision_transition`` is Gate 12 only: persist a DRAFT already
    produced by ``transition_artifact_revision``. Ordinary Save never sets it.
    """
    from services.quality.artifact_identity import enforce_artifact_immutability
    from services.quality.artifact_state import enforce_save_artifact_state

    enforce_save_artifact_state(
        existing_data or {},
        incoming_data,
        allow_revision_transition=allow_revision_transition,
    )
    if not allow_revision_transition:
        enforce_artifact_immutability(existing_data or {}, incoming_data)


def _require_content_mutation_allowed(project_data, *, action: str):
    """Pass 1 write-policy gateway for Generate / Enhance / Cover mutation routes.

    Reuses ``assert_content_mutation_allowed`` (resolve_artifact_state). Does not
    call ``transition_artifact_revision`` or create a revision automatically.
    """
    from services.quality.artifact_state import assert_content_mutation_allowed

    return assert_content_mutation_allowed(project_data or {}, action=action)


def _persist_draft_content_mutation(project_id, data):
    """Persist a legitimate DRAFT content/cover change and invalidate export refs.

    Bypasses the Save immutability boundary (digests may change on draft edit)
    but never opens a revision transition. Prior approved lineage is preserved.
    """
    from services.quality.artifact_state import invalidate_draft_export_references

    if not isinstance(data, dict):
        raise ValueError("Draft content mutation requires a data mapping.")
    invalidate_draft_export_references(data)
    return database.update_project(int(project_id), None, data, None)


def _persist_product_data(project, data, *, allow_revision_transition=False):
    """Write the updated data blob back to the same project record.

    Shared Next Steps / seller / launch / export persistence boundary.
    Approved-artifact fields are enforced here so route callers cannot bypass
    the PUT-route immutability contract.
    """
    project_id = int(project["id"])
    existing = database.get_project(project_id) or project
    existing_data = existing.get("data") if isinstance(existing.get("data"), dict) else {}
    if isinstance(data, dict):
        _enforce_save_persistence_boundary(
            existing_data or {},
            data,
            allow_revision_transition=allow_revision_transition,
        )
    updated = database.update_project(project_id, None, data, None)
    if updated is not None:
        project["data"] = updated.get("data")
    else:
        project["data"] = data


# Disclaimer fingerprint markers — any of these in the manuscript means the
# model already included a real disclaimer and we MUST NOT add a second one.
_DISCLAIMER_MARKERS = (
    "required disclaimer",
    "important disclaimer",
    "medical, financial, legal, or other qualified advice",
    "not a substitute for professional",
    "consult a licensed professional",
    "consult your physician or a qualified healthcare",
    "not intended to diagnose, treat, cure, or prevent any disease",
    "educational and informational purposes only",
    "general educational and informational purposes",
)


def enforce_disclaimer_on_project_data(project):
    """Deterministic disclaimer enforcement for ebook exports.

    If the EbookContract (rebuilt from the saved brief) marks the disclaimer as
    required AND the manuscript does not already contain a disclaimer block,
    insert the contract's disclaimer_text immediately after the title and
    introduction and before Chapter 1. Mutates the project's data dict in
    place and returns True if anything was inserted. Idempotent.

    The detection is conservative: any of the standard contract disclaimer
    markers in the manuscript counts as "already present" so we never duplicate.
    """
    import re
    data = project.get("data") or {}
    product_type = data.get("product_type") or project.get("type")
    if product_type != "ebook":
        return False

    manuscript = data.get("ebook") or ""
    if not manuscript.strip():
        return False

    brief = data.get("contract")
    if not isinstance(brief, dict):
        return False

    # Build the EbookContract from the brief so we get the same auto-detected
    # disclaimer_required and disclaimer_text that the generator used.
    from services.ebook_contract import build_contract
    plan = brief.get("plan") or {}
    op = brief.get("opportunity") or {}
    topic = (plan.get("product_title")
             or op.get("product_idea")
             or plan.get("topic")
             or brief.get("topic")
             or "")
    audience = (plan.get("target_audience")
                or op.get("target_audience")
                or brief.get("audience")
                or "")
    contract = build_contract(
        topic=topic,
        audience=audience,
        tone=plan.get("tone") or "professional",
        reading_level=plan.get("reading_level") or "General adult",
        reader_problem=(plan.get("customer_problem")
                        or op.get("customer_problem")
                        or ""),
        desired_transformation=(plan.get("product_promise")
                                or plan.get("main_transformation")
                                or ""),
    )
    if not getattr(contract, "disclaimer_required", False):
        return False

    disclaimer_text = (getattr(contract, "disclaimer_text", "") or "").strip()
    if not disclaimer_text:
        return False

    manuscript_lower = manuscript.lower()
    # (a) fingerprint of the actual contract disclaimer text, or
    # (b) any of the standard contract disclaimer markers
    fingerprint = disclaimer_text[:120].lower()
    if fingerprint and fingerprint in manuscript_lower:
        return False
    for marker in _DISCLAIMER_MARKERS:
        if marker in manuscript_lower:
            return False

    # Insert the disclaimer immediately after the title/intro and before
    # Chapter 1. If no Chapter 1 marker exists, insert after the first
    # blank-line paragraph following the title, or fall back to the end.
    heading = "## Important Disclaimer"
    block = f"\n\n{heading}\n\n{disclaimer_text}\n"

    chapter_re = re.compile(r'(^|\n)(#{1,3}\s+chapter\s+1\b)', re.IGNORECASE)
    m = chapter_re.search(manuscript)
    if m:
        idx = m.start()
        if manuscript[idx] == "\n":
            idx += 1
        manuscript = manuscript[:idx] + block + "\n" + manuscript[idx:]
    else:
        title_re = re.compile(r'^#\s+.+$', re.MULTILINE)
        tm = title_re.search(manuscript)
        if tm:
            after_title = tm.end()
            blank_re = re.compile(r'\n\s*\n')
            bm = blank_re.search(manuscript, after_title)
            if bm:
                insert_at = bm.end()
                manuscript = manuscript[:insert_at] + block + "\n" + manuscript[insert_at:]
            else:
                manuscript = manuscript + "\n" + block
        else:
            manuscript = manuscript + "\n" + block

    data["ebook"] = manuscript
    project["data"] = data
    return True


@app.post("/export-product")
def export_product_route():
    body = request.get_json(silent=True) or {}
    # Import before try/except so early ValueError from _load_product_project
    # does not trip UnboundLocalError on ArtifactStateError in except clauses.
    from services.quality.artifact_identity import (
        stamp_artifact_identity,
        verify_artifact_identity,
    )
    from services.quality.artifact_state import (
        ArtifactState,
        ArtifactStateError,
        assert_packaging_allowed,
        current_revision,
        resolve_artifact_state,
    )

    try:
        project = _load_product_project(body)
        # Deterministic disclaimer enforcement: the AI model may have dropped
        # the required disclaimer; insert it before PDF/ZIP rendering so the
        # customer never gets a non-compliant export. Idempotent.
        enforce_disclaimer_on_project_data(project)

        data = project.get("data") or {}
        # Pass 2 packaging policy + identity: no silent content regeneration.
        packaging_state = assert_packaging_allowed(data)
        verify_artifact_identity(data)
        identity_before = {
            "content_digest": data.get("content_digest"),
            "asset_manifest_digest": data.get("asset_manifest_digest"),
            "artifact_id": data.get("artifact_id") or data.get("package_id"),
            "artifact_revision": current_revision(data),
            "artifact_state": resolve_artifact_state(data).value,
            "pdf_bytes": data.get("pdf_bytes"),
            "export_package_id": data.get("export_package_id"),
            "product_exports": data.get("product_exports"),
        }
        if data.get("is_pdf") or data.get("pdf_bytes"):
            stamp_artifact_identity(data)
            project["data"] = data
        result = build_product_export(project)
        data = project.get("data") or {}
        # Packaging must not rewrite content/assets/cover/state/revision.
        if packaging_state in (ArtifactState.APPROVED, ArtifactState.LOCKED) or (
            identity_before.get("content_digest")
            and identity_before.get("asset_manifest_digest")
        ):
            if data.get("pdf_bytes") != identity_before.get("pdf_bytes"):
                raise ArtifactStateError(
                    "Packaging must not modify stored PDF content."
                )
            if (
                identity_before.get("content_digest")
                and data.get("content_digest") != identity_before.get("content_digest")
            ):
                raise ArtifactStateError(
                    "Packaging must not modify content_digest."
                )
            if (
                identity_before.get("asset_manifest_digest")
                and data.get("asset_manifest_digest")
                != identity_before.get("asset_manifest_digest")
            ):
                raise ArtifactStateError(
                    "Packaging must not modify asset_manifest_digest."
                )
            if current_revision(data) != identity_before["artifact_revision"]:
                raise ArtifactStateError(
                    "Packaging must not modify artifact_revision."
                )
            if resolve_artifact_state(data).value != identity_before["artifact_state"]:
                raise ArtifactStateError(
                    "Packaging must not modify artifact_state."
                )
        # LOCKED with an existing export package: do not replace export refs.
        if (
            packaging_state is ArtifactState.LOCKED
            and identity_before.get("export_package_id")
            and result.get("package_id") == identity_before.get("export_package_id")
            and identity_before.get("product_exports")
        ):
            return jsonify(result)
        data["export_package_id"] = result["package_id"]
        data["product_exports"] = result["exports"]
        # Ebook release gate: Export Ready / customer downloads only on PASS.
        is_ebook = (
            project.get("type") == "ebook"
            or str(data.get("product_type") or "").lower() == "ebook"
            or bool(data.get("ebook"))
        )
        if is_ebook:
            release_status = str(data.get("release_status") or "").upper()
            cert = data.get("release_certificate") if isinstance(data.get("release_certificate"), dict) else None
            export_ready = (
                bool(data.get("export_ready"))
                and release_status == "PASS"
                and bool(cert)
                and str(cert.get("issued_by") or "") == "server"
                and str(cert.get("status") or "").upper() == "PASS"
            )
            data["export_ready"] = export_ready
            result["release_status"] = release_status
            result["release_certificate"] = cert
            result["export_ready"] = export_ready
            if not export_ready:
                # Keep package for inspection; do not advertise Export Ready.
                if release_status == "WARNING":
                    data["stage"] = "publishing_preview_ready"
                else:
                    data["stage"] = data.get("stage") or "product_generated"
            else:
                data["stage"] = "export_ready"
        if data.get("is_pdf") or data.get("pdf_bytes"):
            stamp_artifact_identity(data)
        _persist_product_data(project, data)
        return jsonify(result)
    except ArtifactStateError as exc:
        return _error(str(exc), 409)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("export-product failed")
        return _error(str(exc), 500)


@app.post("/ebook-release-check")
def ebook_release_check_route():
    """Server-authoritative ebook release PASS/WARNING/FAIL (no optimistic UI)."""
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_document import build_ebook_document_from_project
        from services.ebook_release_validator import (
            issue_release_certificate,
            release_identity_from_doc,
            validate_ebook_release,
        )
        from services.quality.artifact_state import current_revision

        project = None
        if body.get("project_id") is not None:
            project = _load_product_project(body)
        elif isinstance(body.get("project"), dict):
            project = body.get("project")
            if not isinstance(project.get("data"), dict):
                project["data"] = {}
            project.setdefault("type", "ebook")
        else:
            raise ValueError("project_id or project is required for ebook-release-check.")

        data = dict(project.get("data") or {})
        is_ebook = (
            project.get("type") == "ebook"
            or str(data.get("product_type") or "").lower() == "ebook"
            or bool(data.get("ebook") or data.get("content"))
        )
        if not is_ebook:
            raise ValueError("ebook-release-check is only for ebook projects.")

        # Optional draft field overlay from the Builder (not persisted unless asked).
        overlay = body.get("draft") if isinstance(body.get("draft"), dict) else {}
        if overlay:
            for key in (
                "title",
                "subtitle",
                "content",
                "ebook",
                "outline",
                "design_theme",
                "cover_design",
                "research_notes",
                "fields",
                "visual_plan",
                "author_brand",
            ):
                if key in overlay:
                    data[key] = overlay[key]
            if overlay.get("content") is not None and not overlay.get("ebook"):
                data["ebook"] = overlay.get("content")
            project = {**project, "data": data}

        doc = build_ebook_document_from_project(project, data)
        identity = release_identity_from_doc(
            doc,
            project_id=project.get("id"),
            artifact_id=str(
                data.get("artifact_id")
                or data.get("package_id")
                or doc.identity.artifact_id
                or ""
            ),
            revision=current_revision(data),
        )
        release = validate_ebook_release(doc)
        cert = issue_release_certificate(release, identity)

        # Persist server certificate on saved projects only (metadata; no manuscript rewrite).
        if project.get("id") is not None and not overlay:
            data["release_status"] = cert["status"]
            data["release_certificate"] = cert
            data["release_report"] = release.to_dict()
            data["export_ready"] = bool(cert["export_ready"] and cert["status"] == "PASS")
            data["ebook_manuscript_digest"] = identity["ebook_manuscript_digest"]
            data["ebook_asset_manifest_digest"] = identity["ebook_asset_manifest_digest"]
            _persist_product_data(project, data)

        return jsonify(
            {
                "release_status": cert["status"],
                "export_ready": cert["export_ready"],
                "release_certificate": cert,
                "blocking": cert.get("blocking") or [],
                "issues": cert.get("issues") or [],
                "identity": identity,
            }
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook-release-check failed")
        return _error(str(exc), 500)


@app.post("/generate-seller-package")
def generate_seller_package_route():
    body = request.get_json(silent=True) or {}
    platform = (body.get("platform") or "").strip()
    try:
        project = _load_product_project(body)
        if project.get("type") not in ("product", "ebook"):
            raise ValueError("Platform packages can only be created for completed products.")
        pkg = generate_seller_package(platform, project)
        data = project.get("data") or {}
        packages = data.get("packages") or {}
        packages[platform] = pkg
        data["packages"] = packages
        _persist_product_data(project, data)
        return jsonify({"platform": platform, "package": pkg})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("generate-seller-package failed")
        return _error(str(exc), 500)


@app.post("/generate-sales-page")
def generate_sales_page_route():
    body = request.get_json(silent=True) or {}
    try:
        project = _load_product_project(body)
        sales_page = generate_sales_page(project)
        data = project.get("data") or {}
        data["sales_page"] = sales_page
        _persist_product_data(project, data)
        return jsonify({"sales_page": sales_page})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("generate-sales-page failed")
        return _error(str(exc), 500)


@app.post("/generate-product-ad")
def generate_product_ad_route():
    body = request.get_json(silent=True) or {}
    try:
        project = _load_product_project(body)
        scripts = generate_product_ad_scripts(project)
        data = project.get("data") or {}
        data["ad_scripts"] = scripts
        _persist_product_data(project, data)
        return jsonify(scripts)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("generate-product-ad failed")
        return _error(str(exc), 500)


# ----- Product Projects (SQLite) -----


def _record_artifact_id(data) -> str:
    if not isinstance(data, dict):
        return ""
    return str(data.get("artifact_id") or data.get("package_id") or "").strip()


def _enrich_project_artifact_fields(
    project: dict, *, raise_on_conflict: bool = False
) -> dict:
    """Attach resolved artifact_state / id / revision for UI (no DB migration)."""
    if not isinstance(project, dict):
        return project
    data = project.get("data") if isinstance(project.get("data"), dict) else None
    if not data:
        return project
    try:
        from services.quality.artifact_state import (
            ArtifactStateError,
            current_revision,
            resolve_artifact_state,
        )

        project["artifact_state"] = resolve_artifact_state(data).value
        project["artifact_id"] = _record_artifact_id(data)
        project["artifact_revision"] = current_revision(data)
    except ArtifactStateError:
        if raise_on_conflict:
            raise
        # List view: omit fields so UI hides the control.
        pass
    except Exception:
        # Unreadable evidence: omit fields so UI hides the control.
        pass
    return project


@app.get("/projects")
def list_projects_route():
    """List projects. By default hides system/test/temporary projects.
    Pass ?include_system=1 to see everything."""
    include_system = request.args.get("include_system", "0") == "1"
    projects = database.list_projects(include_system=include_system)
    return jsonify([_enrich_project_artifact_fields(p) for p in projects])


@app.get("/projects/<int:project_id>")
def get_project_route(project_id: int):
    from services.quality.artifact_state import ArtifactStateError

    project = database.get_project(project_id)
    if not project:
        return _error("Project not found.", 404)
    try:
        return jsonify(
            _enrich_project_artifact_fields(project, raise_on_conflict=True)
        )
    except ArtifactStateError as exc:
        return _error(str(exc), 409)


@app.post("/projects")
def create_project_route():
    """Create a project. Applies backend safety guard for test/debug names."""
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    type_ = (body.get("type") or "").strip()
    if not name or not type_:
        return _error("Project name and type are required.", 400)

    # Resolve save flags — backend safety guard runs inside apply_save_flags
    explicit_save = body.get("user_saved")
    user_saved, system_test, temporary = database.apply_save_flags(
        name=name,
        explicit_user_save=bool(explicit_save) if explicit_save is not None else None,
        system_test=body.get("system_test"),
        temporary=body.get("temporary"),
    )

    # Identity/state for new PDF products is stamped on Generate
    # (artifact_state=DRAFT). POST /projects persists the client payload as-is
    # so legacy digests-without-state fixtures are not migrated.
    project = database.create_project(
        name=name,
        type_=type_,
        data=body.get("data") or {},
        user_saved=user_saved,
        system_test=system_test,
        temporary=temporary,
    )
    return jsonify(project), 201


@app.put("/projects/<int:project_id>")
def update_project_route(project_id: int):
    """Update a project. Applies backend safety guard for test/debug names."""
    body = request.get_json(silent=True) or {}
    name = body.get("name")

    # Apply safety guard if name is changing to a test pattern
    user_saved_arg = body.get("user_saved")
    system_test_arg = body.get("system_test")
    temporary_arg = body.get("temporary")

    if name:
        name = name.strip()
        user_saved, system_test, temporary = database.apply_save_flags(
            name=name,
            explicit_user_save=bool(user_saved_arg) if user_saved_arg is not None else None,
            system_test=bool(system_test_arg) if system_test_arg is not None else None,
            temporary=bool(temporary_arg) if temporary_arg is not None else None,
        )
    else:
        user_saved = bool(user_saved_arg) if user_saved_arg is not None else None
        system_test = bool(system_test_arg) if system_test_arg is not None else None
        temporary = bool(temporary_arg) if temporary_arg is not None else None

    # Publish/Next Steps → Save must not rewrite an approved/locked artifact.
    incoming_data = body.get("data")
    if isinstance(incoming_data, dict):
        existing = database.get_project(project_id)
        if existing and isinstance(existing.get("data"), dict):
            try:
                _enforce_save_persistence_boundary(
                    existing.get("data") or {}, incoming_data
                )
            except ValueError as exc:
                return _error(str(exc), 400)

    project = database.update_project(
        project_id,
        name=name,
        data=body.get("data"),
        type_=body.get("type"),
        user_saved=user_saved,
        system_test=system_test,
        temporary=temporary,
    )
    if not project:
        return _error("Project not found.", 404)
    return jsonify(project)


# Request body keys allowed on the Gate 12 controlled revision entrypoint.
# Anything else (content/assets/cover/digests/exports/data blob) is rejected.
_REVISION_REQUEST_ALLOWED_KEYS = frozenset(
    {
        "create_draft_revision",
        "reason",
        "expected_artifact_id",
        "expected_revision",
    }
)


@app.post("/projects/<int:project_id>/revisions")
def create_project_revision_route(project_id: int):
    """Gate 12: explicit APPROVED → new DRAFT revision (no generation).

    Controlled production entrypoint only. Does not call Generate Product,
    enhancement, cover, or packaging. Persists the transitioned DRAFT through
    ``_persist_product_data`` without Save bumping revision again.
    """
    from services.quality.artifact_state import (
        ArtifactState,
        ArtifactStateError,
        current_revision,
        resolve_artifact_state,
        transition_artifact_revision,
    )

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error("JSON body with create_draft_revision is required.", 400)

    unknown = sorted(set(body.keys()) - _REVISION_REQUEST_ALLOWED_KEYS)
    if unknown:
        return _error(
            "Revision request cannot include replacement content, assets, "
            "cover, digests, or export references. "
            f"Unsupported fields: {', '.join(unknown)}.",
            400,
        )

    if body.get("create_draft_revision") is not True:
        return _error(
            "Explicit create_draft_revision=true is required to open a new "
            "DRAFT revision.",
            400,
        )

    reason = str(body.get("reason") or "").strip()
    if not reason:
        return _error("A non-empty revision reason is required.", 400)

    expected_artifact_id = str(body.get("expected_artifact_id") or "").strip()
    if not expected_artifact_id:
        return _error("expected_artifact_id is required.", 400)
    if "expected_revision" not in body:
        return _error("expected_revision is required.", 400)
    try:
        expected_revision = int(body.get("expected_revision"))
    except (TypeError, ValueError):
        return _error("expected_revision must be an integer.", 400)

    project = database.get_project(project_id)
    if not project:
        return _error("Project not found.", 404)
    existing_data = project.get("data") if isinstance(project.get("data"), dict) else None
    if not existing_data:
        return _error("Project has no saved artifact data.", 404)

    try:
        state = resolve_artifact_state(existing_data)
    except ArtifactStateError as exc:
        return _error(str(exc), 409)

    saved_artifact_id = _record_artifact_id(existing_data)
    saved_revision = current_revision(existing_data)
    if (
        saved_artifact_id != expected_artifact_id
        or saved_revision != expected_revision
    ):
        return _error(
            "Artifact revision conflict: expected_artifact_id / "
            "expected_revision do not match the authoritative saved record. "
            "No storage change was made.",
            409,
        )

    if state is not ArtifactState.APPROVED:
        return _error(
            f"Revision transition accepts APPROVED only (current state: "
            f"{state.value}).",
            409,
        )

    try:
        draft = transition_artifact_revision(existing_data, reason=reason)
    except ArtifactStateError as exc:
        return _error(str(exc), 409)

    try:
        _persist_product_data(
            project, draft, allow_revision_transition=True
        )
    except (ArtifactStateError, ValueError) as exc:
        return _error(str(exc), 400)

    stored = database.get_project(project_id) or project
    stored_data = stored.get("data") if isinstance(stored.get("data"), dict) else draft
    return jsonify(
        {
            "ok": True,
            "project_id": project_id,
            "artifact_id": _record_artifact_id(stored_data),
            "artifact_revision": current_revision(stored_data),
            "artifact_state": resolve_artifact_state(stored_data).value,
            "prior_approved_revision": stored_data.get("prior_approved_revision"),
            "reason": reason,
        }
    ), 201


@app.post("/projects/<int:project_id>/kdp/preflight")
def kdp_preflight_route(project_id: int):
    """KDP Pass 2: run combined preflight; does not block ordinary PDF/ZIP."""
    from services.kdp.preflight import run_kdp_preflight
    from services.quality.artifact_state import ArtifactStateError

    body = request.get_json(silent=True) or {}
    project = database.get_project(project_id)
    if not project:
        return _error("Project not found.", 404)
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    try:
        result = run_kdp_preflight(
            data,
            print_settings=body.get("print_settings") or body.get("print"),
            metadata=body.get("metadata"),
            ai_disclosure=body.get("ai_disclosure"),
            publication_format=body.get("publication_format"),
        )
    except ArtifactStateError as exc:
        return _error(str(exc), 409)
    except ValueError as exc:
        return _error(str(exc), 400)

    # Persist preflight sidecar + optional settings (metadata-only; no content regen).
    data = dict(data)
    data["kdp_settings"] = {
        "publication_format": result.publication_format,
        "print": body.get("print_settings") or body.get("print") or data.get("kdp_print_settings") or {},
        "metadata": body.get("metadata") or data.get("kdp_metadata") or {},
        "ai_disclosure": body.get("ai_disclosure") or data.get("kdp_ai_disclosure") or {},
    }
    if body.get("print_settings") or body.get("print"):
        data["kdp_print_settings"] = body.get("print_settings") or body.get("print")
    if body.get("metadata"):
        data["kdp_metadata"] = body.get("metadata")
    if body.get("ai_disclosure"):
        data["kdp_ai_disclosure"] = body.get("ai_disclosure")
    if body.get("publication_format"):
        data["publication_format"] = body.get("publication_format")
    data["kdp_preflight"] = result.as_dict()
    try:
        _persist_product_data(project, data)
    except (ArtifactStateError, ValueError) as exc:
        # Still return preflight even if persist of sidecar is refused
        payload = result.as_dict()
        payload["persist_warning"] = str(exc)
        return jsonify(payload)
    return jsonify(result.as_dict())


@app.post("/projects/<int:project_id>/kdp/prepare-package")
def kdp_prepare_package_route(project_id: int):
    """KDP-specific export gate + manifest. Does not alter ordinary PDF/ZIP paths."""
    from services.kdp.preflight import (
        KdpPreflightError,
        assert_prepare_kdp_package_allowed,
        build_kdp_package_manifest,
    )
    from services.quality.artifact_state import ArtifactStateError

    body = request.get_json(silent=True) or {}
    project = database.get_project(project_id)
    if not project:
        return _error("Project not found.", 404)
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    token = str(body.get("preflight_token") or "").strip()
    try:
        preflight = assert_prepare_kdp_package_allowed(
            data,
            preflight_token=token,
            warning_acknowledged=bool(body.get("warning_acknowledged")),
            print_settings=body.get("print_settings") or body.get("print"),
            metadata=body.get("metadata"),
            ai_disclosure=body.get("ai_disclosure"),
            publication_format=body.get("publication_format"),
        )
    except KdpPreflightError as exc:
        return _error(str(exc), 403)
    except ArtifactStateError as exc:
        return _error(str(exc), 409)
    except ValueError as exc:
        return _error(str(exc), 400)

    settings = {
        "publication_format": preflight.publication_format,
        "print": body.get("print_settings")
        or body.get("print")
        or (data.get("kdp_settings") or {}).get("print")
        or data.get("kdp_print_settings")
        or {},
        "metadata": body.get("metadata")
        or (data.get("kdp_settings") or {}).get("metadata")
        or data.get("kdp_metadata")
        or {},
        "ai_disclosure": body.get("ai_disclosure")
        or (data.get("kdp_settings") or {}).get("ai_disclosure")
        or data.get("kdp_ai_disclosure")
        or {},
    }
    manifest = build_kdp_package_manifest(data, preflight, settings=settings)

    # Gate + manifest only — do not invent a new Amazon upload package format
    # and do not regenerate PDF/ZIP content to cure failures.
    data = dict(data)
    data["kdp_package_manifest"] = manifest
    data["kdp_preflight"] = preflight.as_dict()
    try:
        _persist_product_data(project, data)
    except (ArtifactStateError, ValueError) as exc:
        return _error(str(exc), 409)

    return jsonify(
        {
            "ok": True,
            "label": "Ready for Amazon Previewer",
            "amazon_approval_claim": None,
            "manifest": manifest,
            "preflight": preflight.as_dict(),
            "package_construction": "manifest_only",
            "note": (
                "KDP package gate approved the authoritative artifact and wrote a "
                "manifest. No new Amazon upload format was invented; ordinary "
                "PDF/ZIP downloads remain unchanged."
            ),
        }
    )


@app.delete("/projects/<int:project_id>")
def delete_project_route(project_id: int):
    if not database.delete_project(project_id):
        return _error("Project not found.", 404)
    return jsonify({"ok": True})


@app.delete("/projects")
def delete_all_projects():
    """Bulk-delete projects. Requires delete_all=1 AND user_saved_only=1.
    This prevents accidental deletion of hidden system/test records.
    Hidden records can only be deleted when the test/debug toggle is on
    and they are individually confirmed."""
    import flask
    delete_all = flask.request.args.get("delete_all")
    user_saved_only = flask.request.args.get("user_saved_only")
    if delete_all != "1" or user_saved_only != "1":
        return _error("Invalid bulk-delete request.", 400)
    conn = database.get_conn()
    cur = conn.execute(
        "DELETE FROM projects WHERE user_saved = 1 AND system_test = 0 AND temporary = 0"
    )
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return jsonify({"ok": True, "deleted": deleted})


@app.post("/admin/backup-db")
def admin_backup_db():
    """Create a timestamped backup of the projects database. Used before bulk operations."""
    import datetime, shutil, os as _os
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    src = database.DB_PATH
    bak_dir = _os.path.dirname(src)
    bak_name = f"projects_BACKUP_{ts}.db"
    bak_path = _os.path.join(bak_dir, bak_name)
    shutil.copy2(src, bak_path)
    return jsonify({"ok": True, "backup_path": bak_path, "backup_name": bak_name})


@app.delete("/admin/delete-test-projects")
def admin_delete_test_projects():
    """Delete all projects flagged as system_test or temporary. Creates a backup first."""
    import datetime, shutil, os as _os
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    src = database.DB_PATH
    bak_dir = _os.path.dirname(src)
    bak_name = f"projects_BACKUP_{ts}.db"
    bak_path = _os.path.join(bak_dir, bak_name)
    shutil.copy2(src, bak_path)
    conn = database.get_conn()
    cur = conn.execute(
        "DELETE FROM projects WHERE system_test = 1 OR temporary = 1 OR user_saved = 0"
    )
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return jsonify({"ok": True, "deleted": deleted, "backup_path": bak_path})


@app.get("/coloring-ai-status")
def coloring_ai_status():
    """Return Coloring Book image AI configuration status. Does not expose secrets."""
    # Import helpers from ai_client which handles the fallback chain
    from ai_client import _is_placeholder_key, get_key_source, get_base_url_source

    from dotenv import load_dotenv
    load_dotenv()

    model = os.environ.get("AI_INTEGRATIONS_IMAGE_MODEL", "gpt-image-1")

    # Use the same resolution logic as ai_client.py
    api_key_primary = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "")
    api_key_fallback = os.environ.get("OPENAI_API_KEY", "")
    base_url_primary = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "")
    base_url_fallback = os.environ.get("OPENAI_BASE_URL", "")

    # Resolve key
    if api_key_primary and api_key_primary.strip() and not _is_placeholder_key(api_key_primary):
        api_key_val = api_key_primary
        api_key_source = "AI_INTEGRATIONS_OPENAI_API_KEY"
    elif api_key_fallback and api_key_fallback.strip() and not _is_placeholder_key(api_key_fallback):
        api_key_val = api_key_fallback
        api_key_source = "OPENAI_API_KEY"
    else:
        api_key_val = api_key_primary or api_key_fallback
        api_key_source = "AI_INTEGRATIONS_OPENAI_API_KEY" if api_key_primary else ("OPENAI_API_KEY" if api_key_fallback else "none")

    has_key = bool(api_key_val and api_key_val.strip() and not _is_placeholder_key(api_key_val))
    is_placeholder = bool(api_key_val and api_key_val.strip() and _is_placeholder_key(api_key_val))

    # Resolve base URL
    if base_url_primary and base_url_primary.strip():
        base_url_source = "AI_INTEGRATIONS_OPENAI_BASE_URL"
        has_url = True
    elif base_url_fallback and base_url_fallback.strip():
        base_url_source = "OPENAI_BASE_URL"
        has_url = True
    else:
        base_url_source = "default"
        has_url = True  # default is always available

    ready = has_key and has_url and not is_placeholder

    missing: list[str] = []
    if not has_key and not is_placeholder:
        missing.append("AI_INTEGRATIONS_OPENAI_API_KEY or OPENAI_API_KEY")
    elif is_placeholder:
        missing.append(f"{api_key_source} (placeholder — needs real key)")
    if not has_url and not base_url_primary and not base_url_fallback:
        missing.append("AI_INTEGRATIONS_OPENAI_BASE_URL, OPENAI_BASE_URL, or default")

    if ready:
        message = "AI Image Coloring Page is ready."
    elif is_placeholder:
        message = f"AI Image Coloring Page is not ready — placeholder key detected in {api_key_source}."
    elif missing:
        message = f"AI Image Coloring Page is not ready — missing: {', '.join(missing)}"
    else:
        message = "AI Image Coloring Page is not ready."

    return jsonify({
        "ready": ready,
        "api_key_present": has_key,
        "api_key_source": api_key_source if api_key_val else "none",
        "base_url_present": has_url,
        "base_url_source": base_url_source,
        "image_model": model,
        "message": message,
        "missing": missing,
        "placeholder_detected": is_placeholder,
    })


# ----- Cover Editor page -----


@app.get("/cover-editor")
def cover_editor_page():
    """Full-page cover editor for crossword, word search, and coloring book products."""
    project_id = request.args.get("project_id", type=int)
    if not project_id:
        return "project_id is required", 400
    project = database.get_project(project_id)
    if not project:
        return "Project not found", 404
    data = dict(project.get("data") or {})
    cover_json = data.get("cover_design") or {}
    product_type = str(data.get("product_type") or "crossword")
    package_id = str(cover_json.get("package_id") or data.get("package_id") or "")
    return render_template(
        "cover_editor.html",
        project_id=project_id,
        cover_json=cover_json,
        product_type=product_type,
        package_id=package_id,
    )


# ----- Cover Editor routes -----


@app.post("/cover/preview")
def cover_preview_route():
    """Preview cover edits without saving. Reads project from DB."""
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    overrides = body.get("overrides") or {}
    if not project_id:
        return jsonify({"error": "project_id is required"}), 400
    try:
        project = database.get_project(int(project_id))
        if not project:
            return jsonify({"error": "Project not found"}), 404
        product_type = str((project.get("data") or {}).get("product_type") or "")
        if product_type == "coloring_book":
            # Never preview an author brand / top-banner title on coloring covers.
            overrides = dict(overrides or {})
            overrides["author"] = ""
            overrides.setdefault("text_position", {"x": 50.0, "y": 81.0, "align": "center"})
            overrides.setdefault("text_overlay", True)
        cover = preview_cover(dict(project), overrides=overrides)
        return jsonify(cover)
    except Exception as exc:
        app.logger.exception("cover preview failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/cover/save")
def cover_save_route():
    """Save cover edits and run quality gate. Reads/writes project from DB."""
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    existing = body.get("cover") or {}
    overrides = body.get("overrides") or {}
    if not project_id:
        return jsonify({"error": "project_id is required"}), 400
    from services.quality.artifact_state import ArtifactStateError

    try:
        package_id = str(existing.get("package_id") or "")
        project = database.get_project(int(project_id))
        if project:
            _require_content_mutation_allowed(
                project.get("data") or {},
                action="save cover changes",
            )
        product_type = str(((project or {}).get("data") or {}).get("product_type") or "")
        if product_type == "coloring_book":
            overrides = dict(overrides or {})
            overrides["author"] = ""
            overrides.setdefault("text_position", {"x": 50.0, "y": 81.0, "align": "center"})
            overrides.setdefault("text_y", 78)
            overrides.setdefault("text_overlay", True)
        saved = save_cover(existing, overrides, package_id=package_id)
        if product_type == "coloring_book":
            saved["author"] = ""
        # Persist to DB
        if project:
            data = dict(project.get("data") or {})
            data["cover_design"] = saved
            if saved.get("image_prompt"):
                data["cover_prompt"] = saved["image_prompt"]
            _persist_draft_content_mutation(project_id, data)
        return jsonify(saved)
    except ArtifactStateError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        app.logger.exception("cover save failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/cover/regenerate")
def cover_regenerate_route():
    """Regenerate AI cover artwork. Shows cost notice. Uses fingerprint to skip duplicate requests."""
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    cover = body.get("cover") or {}
    if not project_id:
        return jsonify({"error": "project_id is required"}), 400
    from services.quality.artifact_state import ArtifactStateError

    try:
        project = database.get_project(int(project_id))
        if not project:
            return jsonify({"error": "Project not found"}), 404
        data = dict(project.get("data") or {})
        _require_content_mutation_allowed(data, action="regenerate cover artwork")
        package_id = str(cover.get("package_id") or data.get("package_id") or "")
        fields = data.get("fields") or {}
        topic = str(fields.get("theme") or cover.get("topic") or "")
        title = str(cover.get("title") or data.get("title") or "")
        subtitle = str(cover.get("subtitle") or "")
        product_type = str(data.get("product_type") or "crossword")
        audience = str(fields.get("age_group") or "")
        difficulty = str(fields.get("difficulty") or "")
        style = str(cover.get("style") or fields.get("style_preference") or "")

        # Cost protection: skip if same brief already generated
        new_fingerprint = compute_cover_fingerprint(
            topic=topic,
            title=title,
            subtitle=subtitle,
            product_type=product_type,
            audience=audience,
            difficulty=difficulty,
            style=style,
        )
        stored_fingerprint = str(cover.get("cover_fingerprint") or "")
        if new_fingerprint == stored_fingerprint and cover.get("cover_asset_url"):
            app.logger.info("Cover fingerprint unchanged — skipping regeneration for project %s", project_id)
            return jsonify({
                "cover": cover,
                "asset_url": cover.get("cover_asset_url") or "",
                "skipped": True,
                "message": "Cover fingerprint unchanged — artwork already matches this brief.",
            })

        if product_type == "coloring_book":
            # Refresh prompt from theme + lock author/title layout before paid regen.
            from services.product_cover_agent import build_coloring_book_cover_brief

            brief = build_coloring_book_cover_brief(
                fields,
                title=title or str(data.get("title") or ""),
                theme=topic,
            )
            cover = dict(cover or {})
            cover["author"] = ""
            cover["title"] = brief.get("title") or title
            cover["subtitle"] = brief.get("subtitle") or subtitle
            cover["image_prompt"] = brief.get("cover_prompt") or cover.get("image_prompt")
            cover["cover_prompt"] = cover["image_prompt"]
            cover["image_direction"] = cover["image_prompt"]
            cover["text_overlay"] = True
            cover["text_position"] = {"x": 50.0, "y": 81.0, "align": "center"}
            cover["text_y"] = 78
            cover["product_type"] = "coloring_book"
            cover["package_id"] = package_id

        saved, asset_url = regenerate_cover_image_for_cover(cover, package_id)
        # Store the fingerprint alongside the new cover
        saved["cover_fingerprint"] = new_fingerprint
        if product_type == "coloring_book":
            saved["author"] = ""
            saved["text_position"] = {"x": 50.0, "y": 81.0, "align": "center"}
            saved["text_y"] = 78
        # Persist to DB
        data["cover_design"] = saved
        if saved.get("image_prompt"):
            data["cover_prompt"] = saved["image_prompt"]
        _persist_draft_content_mutation(project_id, data)
        return jsonify({"cover": saved, "asset_url": asset_url})
    except ArtifactStateError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        app.logger.exception("cover regeneration failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/cover/apply-to-pdf")
def cover_apply_to_pdf_route():
    """Apply saved cover to crossword/word search PDF and re-export.

    Validates the cover with validate_cover_for_export() before applying.
    Returns validation issues and blocks the export if critical issues are found.
    """
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    cover = body.get("cover") or {}
    if not project_id:
        return jsonify({"error": "project_id is required"}), 400
    from services.quality.artifact_state import ArtifactStateError

    try:
        project = database.get_project(int(project_id))
        if not project:
            return jsonify({"error": "Project not found"}), 404
        data = dict(project.get("data") or {})
        _require_content_mutation_allowed(data, action="apply cover to PDF")
        fields = data.get("fields") or {}
        product_type = str(data.get("product_type") or "")

        # Cover quality gate — run before touching the PDF
        issues = validate_cover_for_export(
            cover,
            expected_title=str(cover.get("title") or data.get("title") or ""),
            expected_subtitle=str(cover.get("subtitle") or ""),
            expected_topic=str(fields.get("theme") or cover.get("topic") or ""),
        )
        if issues:
            return jsonify({
                "ok": False,
                "error": "Cover validation failed",
                "validation_issues": issues,
                "message": "Please fix the following cover issues before applying to PDF: " + "; ".join(issues),
            }), 422

        # Apply cover to the saved PDF
        if product_type == "crossword":
            data = apply_crossword_cover_to_saved_data(data, cover)
        elif product_type == "word_search":
            from services.product import apply_word_search_cover_to_saved_data
            data = apply_word_search_cover_to_saved_data(data, cover)
        elif product_type == "coloring_book":
            from services.product import apply_coloring_book_cover_to_saved_data
            data = apply_coloring_book_cover_to_saved_data(data, cover)
        elif product_type == "ebook" or project.get("type") == "ebook":
            from services.product import apply_ebook_cover_to_saved_data
            data = apply_ebook_cover_to_saved_data(data, cover)

        # Re-save with the new covered PDF (invalidates stale draft export refs)
        _persist_draft_content_mutation(project_id, data)
        project = database.get_project(int(project_id)) or {**project, "data": data}

        # Re-export (build_product_export expects the project dict, not an id)
        result = build_product_export(project)
        return jsonify({"ok": True, "exports": result})
    except ArtifactStateError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        app.logger.exception("cover apply-to-pdf failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/cover/upload-image")
def cover_upload_image_route():
    """Accept a user-uploaded image to replace the AI-generated cover artwork."""
    from PIL import Image
    import io
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    image_data = body.get("image_data")  # base64 string
    if not project_id or not image_data:
        return jsonify({"error": "project_id and image_data required"}), 400
    from services.quality.artifact_state import ArtifactStateError

    try:
        project = database.get_project(int(project_id))
        if not project:
            return jsonify({"error": "Project not found"}), 404
        data = dict(project.get("data") or {})
        _require_content_mutation_allowed(data, action="upload cover image")
        package_id = str(data.get("package_id") or "")
        if not package_id:
            return jsonify({"error": "No package_id for this project"}), 400
        img_bytes = base64.b64decode(image_data)
        out_path = os.path.join(EXPORTS_DIR, package_id, "img_cover.png")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        # Verify it's a valid image
        img = Image.open(io.BytesIO(img_bytes))
        img = img.convert("RGB")
        img.save(out_path, "PNG")
        # Cover asset change invalidates current-draft export refs only.
        _persist_draft_content_mutation(project_id, data)
        return jsonify({"ok": True, "url": f"/download/{package_id}/img_cover.png"})
    except ArtifactStateError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        app.logger.exception("cover image upload failed")
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
