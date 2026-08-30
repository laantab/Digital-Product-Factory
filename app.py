"""Digital Product Factory — Flask backend."""
import os
import re

# Bump this by hand with each release commit/tag (see git tags for history).
APP_VERSION = "1.3.0"

from dotenv import load_dotenv
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
# In normal use .env is the single source of truth: without override=True,
# python-dotenv leaves any variable already in the process environment alone,
# so a stale Windows user-level variable silently beats the file. That cost a
# long debugging session on 2026-08-29 -- a revoked TAVILY_API_KEY left in the
# Windows user environment shadowed the working key in .env, and live research
# failed with 401 while .env looked perfectly correct and tested fine on its own.
#
# Under FACTORY_TEST_MODE the opposite must hold: the harness owns the
# environment. tests/test_ebook_real_browser_customer_path.py launches an
# isolated server as a SUBPROCESS with the API keys explicitly blanked, and
# that subprocess runs outside conftest's network guard -- those blanks are its
# only protection against real paid calls. Overriding them from .env handed it
# live credentials and hung the test.
_FACTORY_TEST_MODE = str(os.environ.get("FACTORY_TEST_MODE") or "") == "1"
load_dotenv(os.path.join(_APP_DIR, ".env"), override=not _FACTORY_TEST_MODE)

from flask import Flask, jsonify, make_response, render_template, request, send_file, send_from_directory
import base64
from io import BytesIO

import database
from services.ad import generate_ad, generate_traffic_content, generate_seven_day_plan, generate_promotion_package, generate_launch_package, PLATFORMS, PLATFORMS_LEGACY, TRAFFIC_GOALS_LEGACY, PROMOTION_GOALS, PLATFORM_LABELS, PROMOTION_GOAL_LABELS
from services.ebook import generate_ebook
from services.market_research import discover_products, discover_top_opportunities, market_research
from services.factory_advantage import draft_handoff_payload, collect_inputs, resolve_factory_builder
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
from services.coloring_book.preview_assets import (
    attach_coloring_preview_urls,
    coloring_preview_missing_message,
    is_coloring_preview_filename,
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
    from services.billing.store import init_billing_db

    init_billing_db()
    from services.ebook_pexels import pexels_status_label

    app.logger.info("%s", pexels_status_label())

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


# Shown when research dies outright. Deliberately says nothing about which
# provider failed or why -- that goes to the log, not the customer's page.
RESEARCH_FAILURE_MESSAGE = (
    "We couldn't complete the research just now. Your inputs have been kept — "
    "please try again."
)


@app.get("/pexels-status")
def pexels_status_route():
    """Safe Pexels configuration status for the running Flask process. Never returns the key."""
    from services.ebook_pexels import pexels_health, pexels_public_status

    live = str(request.args.get("live") or "").strip() in {"1", "true", "yes"}
    payload_data = pexels_health(live_auth=live) if live else pexels_public_status()
    payload = jsonify(payload_data)
    text = payload.get_data(as_text=True)
    if "PEXELS_API_KEY" in text or "sk-" in text:
        return _error("Pexels status is unavailable.", 500)
    return payload


@app.route("/")
def index():
    admin_on = os.environ.get("ADMIN_MODE", "").strip().lower() in {"1", "true", "yes"}
    return render_template("index.html", factory_admin_mode=admin_on, app_version=APP_VERSION)


# --------------------------------------------------------------------------- #
# Billing
#
# The browser holds an opaque account reference and sends it with each call.
# It is not an identity and grants nothing: every route below either returns
# public catalog data or starts a checkout the payment provider authenticates.
# Subscription state is only ever changed by a signature-verified webhook.
# --------------------------------------------------------------------------- #
def _account_ref() -> str:
    body = request.get_json(silent=True) or {}
    return str(
        body.get("account_ref")
        or request.args.get("account_ref")
        or request.headers.get("X-Factory-Account")
        or ""
    ).strip()[:64]


@app.get("/billing/plans")
def billing_plans_route():
    """Public pricing catalog, live founder-seat count, and provider status."""
    from services.billing import pricing_payload

    try:
        return jsonify(pricing_payload(_account_ref()))
    except Exception:  # noqa: BLE001
        app.logger.exception("billing plans failed")
        return _error("Pricing is temporarily unavailable.", 500)


@app.get("/billing/subscription")
def billing_subscription_route():
    from services.billing import subscription_payload, usage_payload
    from services.billing.store import get_active_subscription

    account_ref = _account_ref()
    if not account_ref:
        return _error("account_ref is required.", 400)
    try:
        payload = subscription_payload(get_active_subscription(account_ref))
        payload["usage"] = usage_payload(account_ref)
        return jsonify(payload)
    except Exception:  # noqa: BLE001
        app.logger.exception("billing subscription failed")
        return _error("Subscription status is temporarily unavailable.", 500)


@app.post("/billing/account")
def billing_account_route():
    """Mint an opaque account reference for a browser that has none yet."""
    from services.billing import new_account_ref

    return jsonify({"account_ref": new_account_ref()})


@app.post("/billing/checkout")
def billing_checkout_route():
    from services.billing import CheckoutError, start_checkout

    body = request.get_json(silent=True) or {}
    try:
        result = start_checkout(
            plan_id=str(body.get("plan_id") or ""),
            billing_period=str(body.get("billing_period") or "monthly"),
            provider=str(body.get("provider") or ""),
            account_ref=_account_ref(),
            customer_email=str(body.get("email") or "").strip()[:254],
        )
        return jsonify(result)
    except CheckoutError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        # Never leak a provider key or stack detail into a customer-facing error.
        app.logger.exception("checkout failed")
        return _error(
            "Checkout could not be started. The payment provider reported a "
            "problem; nothing has been charged.", 502)


@app.post("/billing/webhook/stripe")
def billing_stripe_webhook_route():
    from services.billing import handle_stripe_event
    from services.billing.providers import (
        BillingConfigError,
        WebhookVerificationError,
        verify_stripe_webhook,
    )

    try:
        event = verify_stripe_webhook(
            request.get_data(), request.headers.get("Stripe-Signature", ""))
    except WebhookVerificationError as exc:
        app.logger.warning("rejected stripe webhook: %s", exc)
        return _error("Signature verification failed.", 400)
    except BillingConfigError as exc:
        app.logger.error("stripe webhook not configured: %s", exc)
        return _error("Webhook endpoint is not configured.", 503)
    try:
        return jsonify(handle_stripe_event(event))
    except Exception:  # noqa: BLE001
        # A 500 makes Stripe retry, which is what we want if we failed to apply
        # a genuine event.
        app.logger.exception("stripe webhook handling failed")
        return _error("Could not process the event.", 500)


@app.post("/billing/webhook/lemonsqueezy")
def billing_lemon_webhook_route():
    from services.billing import handle_lemon_event
    from services.billing.providers import (
        BillingConfigError,
        WebhookVerificationError,
        verify_lemon_webhook,
    )

    try:
        event = verify_lemon_webhook(
            request.get_data(), request.headers.get("X-Signature", ""))
    except WebhookVerificationError as exc:
        app.logger.warning("rejected lemon squeezy webhook: %s", exc)
        return _error("Signature verification failed.", 400)
    except BillingConfigError as exc:
        app.logger.error("lemon squeezy webhook not configured: %s", exc)
        return _error("Webhook endpoint is not configured.", 503)
    try:
        return jsonify(handle_lemon_event(event))
    except Exception:  # noqa: BLE001
        app.logger.exception("lemon squeezy webhook handling failed")
        return _error("Could not process the event.", 500)


@app.post("/research")
def research_route():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            research(
                body.get("keyword", ""),
                topic=body.get("topic"),
                audience=body.get("audience"),
                customer_problem=body.get("customer_problem") or body.get("problem"),
                product_type=body.get("product_type"),
                sales_platform=body.get("sales_platform"),
                expertise=body.get("expertise"),
                target_price=body.get("target_price") or body.get("price"),
                keywords=body.get("keywords"),
                depth=body.get("depth"),
            )
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception:  # noqa: BLE001
        # The exception text is logged, never returned: this payload's "error"
        # is rendered straight into the results page, and provider exceptions
        # carry key fragments and stack detail no customer should see.
        app.logger.exception("research failed")
        return jsonify(
            {
                "error": RESEARCH_FAILURE_MESSAGE,
                "inputs": collect_inputs(body),
                "retryable": True,
            }
        ), 503


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


@app.get("/ebook-workspace/<int:project_id>/cover-preview")
def ebook_workspace_cover_preview_route(project_id: int):
    """Read-only digest-verified cover bytes. Never generates or charges."""
    from io import BytesIO

    from services.ebook_design_workspace import (
        COVER_PREVIEW_UNAVAILABLE,
        CoverPreviewUnavailable,
        verified_cover_preview_asset,
    )
    from services.ebook_project_workspace import assert_no_paid_side_effects_on_read

    try:
        assert_no_paid_side_effects_on_read()
        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        digest = str(request.args.get("digest") or "").strip()
        download = str(request.args.get("download") or "").strip().lower() in {
            "1",
            "true",
            "pdf",
        }
        asset = verified_cover_preview_asset(
            dict(project.get("data") or {}),
            project_id=project_id,
            digest=digest,
            render_png=not download,
        )
        if download:
            response = send_file(
                BytesIO(asset["pdf_bytes"]),
                mimetype="application/pdf",
                as_attachment=True,
                download_name="cover_preview.pdf",
            )
        else:
            response = send_file(
                BytesIO(asset["png_bytes"]),
                mimetype="image/png",
                as_attachment=False,
                download_name="cover_preview.png",
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Ebook-Cover-Digest"] = asset["digest"]
        return response
    except CoverPreviewUnavailable as exc:
        return _error(str(exc) or COVER_PREVIEW_UNAVAILABLE, int(exc.status_code or 404))
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook cover preview failed")
        return _error(COVER_PREVIEW_UNAVAILABLE, 404)


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
            preview_digest=body.get("preview_digest"),
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
        spent_before = float(
            ((data.get("ebook_workspace") or {}).get("paid_call_ledger") or {}).get("spent_usd")
            or 0
        )
        result = estimate_paid_action(data, action)
        spent_after = float(
            ((data.get("ebook_workspace") or {}).get("paid_call_ledger") or {}).get("spent_usd")
            or 0
        )
        if abs(spent_after - spent_before) > 1e-9:
            return _error("Estimate issuance must not charge.", 500)
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


@app.post("/ebook-workspace/<int:project_id>/authorize-budget")
def authorize_ebook_workspace_budget_route(project_id: int):
    """Raise the project cap as user authorization metadata. Does not spend."""
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_project_workspace import (
            authorize_workspace_budget_into_project,
            workspace_public_view,
        )

        if "budget_cap_usd" not in body:
            return _error("budget_cap_usd is required.", 400)
        project = authorize_workspace_budget_into_project(
            database,
            project_id,
            float(body.get("budget_cap_usd")),
            reason=str(body.get("reason") or ""),
        )
        return jsonify(
            {
                "ok": True,
                "workspace": workspace_public_view(project),
            }
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook budget authorization failed")
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
        if body.get("authorize_paid_call") is not True:
            return _error(
                "Correction requires explicit paid authorization. "
                "Request Correction is a free estimate only.",
                400,
            )
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
    """Prepare or approve content-aware visuals. No paid image generation."""
    try:
        from services.ebook_design_workspace import approve_visuals_local, prepare_visuals_local
        from services.ebook_project_workspace import workspace_public_view
        from services.quality.artifact_state import ArtifactStateError

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        body = request.get_json(silent=True) or {}
        action = str(body.get("action") or "prepare").strip().lower()
        data = dict(project.get("data") or {})
        data["_project_id"] = project_id
        try:
            _require_content_mutation_allowed(data, action="update visuals")
        except ArtifactStateError as exc:
            return _error(str(exc), 409)
        if action == "approve":
            data = approve_visuals_local(data)
            msg = "Visuals approved."
        elif action in {"replace", "replace-photo"}:
            from services.ebook_visual_pipeline import replace_photo_aid

            data = replace_photo_aid(
                data,
                str(body.get("visual_id") or ""),
                local_path=str(body.get("local_path") or ""),
                mode=str(body.get("mode") or ""),
            )
            msg = "Replacement photograph staged for review. Visuals are not approved."
        elif action in {"generate-ai", "ai-alternative"}:
            from services.ebook_visual_pipeline import replace_photo_aid

            data = replace_photo_aid(
                data,
                str(body.get("visual_id") or ""),
                mode="ai",
            )
            msg = "A custom image was prepared for review. Visuals are not approved."
        elif action in {"retry-automatic"}:
            ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
            preserve = False
            try:
                from services.ebook_project_workspace import is_approved as _is_approved

                preserve = _is_approved(ws, "cover") or _is_approved(ws, "design") or _is_approved(ws, "preview")
            except Exception:
                preserve = False
            data = prepare_visuals_local(data, preserve_downstream=preserve)
            msg = "Automatic visual retry finished. Visuals are not approved."
        elif action in {"accept-photo", "accept"}:
            from services.ebook_visual_pipeline import accept_photo_aid

            data = accept_photo_aid(data, str(body.get("visual_id") or ""))
            msg = "Photograph accepted for this brief. Visuals are not approved."
        elif action in {"view-full-size", "seen-full-size"}:
            from services.ebook_visual_pipeline import mark_photo_full_size_viewed

            data = mark_photo_full_size_viewed(data, str(body.get("visual_id") or ""))
            msg = "Full-size preview recorded."
        else:
            from services.ebook_project_workspace import is_approved as _is_approved

            ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
            preserve = _is_approved(ws, "cover") or _is_approved(ws, "design") or _is_approved(ws, "preview")
            data = prepare_visuals_local(data, preserve_downstream=preserve)
            msg = "Visuals ready for review."
        project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project), "message": msg})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook visuals failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/cover")
def ebook_workspace_cover_route(project_id: int):
    """Photo-backed cover actions. Reject remains available. Never generates a vector cover."""
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_design_workspace import reject_cover, stage_photo_cover
        from services.ebook_pexels import PexelsError, search_pexels
        from services.ebook_photo_cover import (
            PhotoCoverError,
            apply_editor,
            attach_pexels,
            clear_layout_selection,
            select_layout,
        )
        from services.ebook_project_workspace import workspace_public_view
        from services.quality.artifact_state import ArtifactStateError

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        action = str(body.get("action") or "").strip().lower()
        data = dict(project.get("data") or {})
        data["_project_id"] = project_id
        mutating = action in {"reject", "pexels-select", "editor", "select", "deselect"}
        if mutating:
            try:
                _require_content_mutation_allowed(data, action="update cover photograph")
            except ArtifactStateError as exc:
                return _error(str(exc), 409)
        if action == "reject":
            data = reject_cover(data)
        elif action == "pexels-search":
            prior_cover = data.get("cover_design")
            result = search_pexels(str(body.get("query") or ""), page=int(body.get("page") or 1))
            ws = data.setdefault("ebook_workspace", {})
            ws["pexels_cache"] = {
                "query": result.get("query"),
                "page": result.get("page"),
                "photos": result.get("photos"),
                "next_page": result.get("next_page"),
            }
            if prior_cover is not None:
                data["cover_design"] = prior_cover
        elif action == "pexels-select":
            data = attach_pexels(data, str(body.get("photo_id") or ""), project_id=project_id)
            data = stage_photo_cover(data, project_id=project_id)
        elif action == "editor":
            data = apply_editor(data, dict(body.get("editor") or {}), project_id=project_id)
            data = stage_photo_cover(data, project_id=project_id)
        elif action == "select":
            data = select_layout(data, str(body.get("layout_id") or ""), project_id=project_id)
            data = stage_photo_cover(data, project_id=project_id)
        elif action == "deselect":
            data = clear_layout_selection(data)
        elif action in {"generate", "licensed"}:
            return _error(
                "Vector covers are disabled. Search Pexels or upload your own photograph.",
                400,
            )
        else:
            return _error("Unknown cover action.", 400)
        if mutating:
            project = _persist_draft_content_mutation(project_id, data) or project
        else:
            project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ArtifactStateError as exc:
        return _error(str(exc), 409)
    except (ValueError, PhotoCoverError, PexelsError) as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook cover failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/cover-image")
def ebook_workspace_cover_image_route(project_id: int):
    """Upload a JPG/PNG cover photograph. Zero paid calls."""
    try:
        from services.ebook_design_workspace import stage_photo_cover
        from services.ebook_photo_cover import PhotoCoverError, attach_upload
        from services.ebook_project_workspace import workspace_public_view
        from services.quality.artifact_state import ArtifactStateError

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        license_note = str(request.form.get("license_note") or "").strip()
        owned = str(request.form.get("i_own_this") or "").strip().lower() in {"1", "true", "on", "yes"}
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return _error("Choose a JPG or PNG photograph.", 400)
        declared = str(upload.mimetype or "").lower()
        if declared and declared not in {"image/jpeg", "image/jpg", "image/png", "application/octet-stream"}:
            return _error("Unsupported or corrupted image. Upload a JPG or PNG.", 400)
        raw = upload.read()
        data = dict(project.get("data") or {})
        data["_project_id"] = project_id
        try:
            _require_content_mutation_allowed(data, action="upload cover photograph")
        except ArtifactStateError as exc:
            return _error(str(exc), 409)
        data = attach_upload(
            data,
            raw,
            filename=str(upload.filename or "upload.png"),
            license_note=license_note,
            project_id=project_id,
            owned=owned,
        )
        data = stage_photo_cover(data, project_id=project_id)
        project = _persist_draft_content_mutation(project_id, data) or project
        source = ((data.get("cover_design") or {}).get("source") or {})
        filename = str(source.get("filename") or upload.filename or "photograph")
        source_type = str(source.get("source_type") or "upload")
        message = f"Uploaded {filename}. Creating cover choices."
        return jsonify(
            {
                "ok": True,
                "workspace": workspace_public_view(project),
                "message": message,
                "source": {
                    "filename": filename,
                    "source_type": source_type,
                    "sha256": str(source.get("sha256") or ""),
                },
            }
        )
    except ArtifactStateError as exc:
        return _error(str(exc), 409)
    except (ValueError, PhotoCoverError) as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook cover upload failed")
        return _error(str(exc), 500)


@app.get("/ebook-workspace/<int:project_id>/cover-photo")
def ebook_workspace_cover_photo_route(project_id: int):
    """Read-only registered cover photograph. Never generates or downloads."""
    from io import BytesIO

    from services.ebook_photo_cover import PhotoCoverError, verified_source_photo_asset
    from services.ebook_project_workspace import assert_no_paid_side_effects_on_read

    try:
        assert_no_paid_side_effects_on_read()
        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        asset = verified_source_photo_asset(
            dict(project.get("data") or {}),
            project_id=project_id,
            digest=str(request.args.get("digest") or ""),
        )
        response = send_file(BytesIO(asset["bytes"]), mimetype=asset["mimetype"])
        response.headers["X-Ebook-Cover-Digest"] = asset["digest"]
        response.headers["Cache-Control"] = "no-store"
        return response
    except PhotoCoverError as exc:
        return _error(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook cover photo failed")
        return _error(str(exc), 500)


@app.get("/ebook-workspace/<int:project_id>/cover-variant")
def ebook_workspace_cover_variant_route(project_id: int):
    """Read-only photo-cover variant (full or thumbnail). Never generates."""
    from io import BytesIO

    from services.ebook_photo_cover import PhotoCoverError, verified_variant_asset
    from services.ebook_project_workspace import assert_no_paid_side_effects_on_read

    try:
        assert_no_paid_side_effects_on_read()
        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        asset = verified_variant_asset(
            dict(project.get("data") or {}),
            project_id=project_id,
            layout=str(request.args.get("layout") or ""),
            digest=str(request.args.get("digest") or ""),
            size=str(request.args.get("size") or "full"),
            source_sha=str(request.args.get("src") or ""),
        )
        response = send_file(BytesIO(asset["bytes"]), mimetype=asset["mimetype"])
        response.headers["X-Ebook-Cover-Digest"] = asset["digest"]
        response.headers["Cache-Control"] = "no-store"
        return response
    except PhotoCoverError as exc:
        return _error(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook cover variant failed")
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


@app.get("/ebook-workspace/<int:project_id>/full-preview")
def ebook_workspace_full_preview_route(project_id: int):
    """Serve the stored designed preview HTML locally. Records that it was opened."""
    try:
        from services.ebook_project_workspace import (
            assert_no_paid_side_effects_on_read,
            current_preview_digest,
            is_approved,
            record_preview_opened,
            workspace_public_view,
        )

        assert_no_paid_side_effects_on_read()
        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        data = dict(project.get("data") or {})
        html = str(data.get("ebook_preview_html") or data.get("preview_html") or "")
        if not html.strip():
            return _error("Build preview before opening it.", 400)
        current = current_preview_digest(data)
        requested = str(request.args.get("digest") or "").strip()
        if requested and current and requested != current:
            return _error("Preview has changed. Rebuild and open the current preview.", 409)
        data = record_preview_opened(data)
        project = database.update_project(project_id, None, data) or project
        data = dict(project.get("data") or data)
        from services.ebook_preview_review import wrap_preview_review_document

        view = workspace_public_view(project)
        ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
        already_approved = is_approved(ws, "preview")
        can_approve = bool((view.get("gates") or {}).get("approve_preview_enabled")) and not already_approved
        html = wrap_preview_review_document(
            html,
            title=str(data.get("title") or project.get("name") or "Ebook"),
            project_id=int(project_id),
            digest=current,
            can_approve=can_approve,
            already_approved=already_approved,
        )
        response = make_response(html)
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if current:
            response.headers["X-Ebook-Preview-Digest"] = current
        return response
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook full preview failed")
        return _error(str(exc), 500)


@app.post("/ebook-workspace/<int:project_id>/preview-opened")
def ebook_workspace_preview_opened_route(project_id: int):
    """Record that the current stored preview was opened. No paid calls."""
    try:
        from services.ebook_project_workspace import record_preview_opened, workspace_public_view

        project, err = _ebook_workspace_project_or_404(project_id)
        if err:
            return err[0], err[1]
        data = record_preview_opened(dict(project.get("data") or {}))
        project = database.update_project(project_id, None, data) or project
        return jsonify({"ok": True, "workspace": workspace_public_view(project)})
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook preview-opened failed")
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
                topic=body.get("topic"),
                customer_problem=body.get("customer_problem") or body.get("problem"),
                sales_platform=body.get("sales_platform"),
                expertise=body.get("expertise"),
                target_price=body.get("target_price") or body.get("price"),
                keywords=body.get("keywords"),
                depth=body.get("depth"),
            )
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("market research failed")
        return jsonify(
            {
                "error": str(exc),
                "inputs": collect_inputs(body),
                "retryable": True,
            }
        ), 503


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
        from services.ebook_customer_path import complete_factory_ebook

        result = complete_factory_ebook(title, content, fields)
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
        from services.ebook_factory_pipeline import READINESS_FIELDS, apply_ebook_readiness

        result["product_type"] = result.get("product_type") or "ebook"
        sanitized = str(content or "").strip() or str(result.get("content") or "")
        result["content"] = sanitized
        apply_ebook_readiness(result)
        # Persist enhanced content to project so export can use it
        if project_id:
            project = database.get_project(int(project_id))
            if project:
                data = dict(project.get("data") or {})
                data["content"] = sanitized
                data["ebook"] = sanitized
                data["preview_html"] = result.get("preview_html", "")
                data["visual_plan"] = result.get("visual_plan", "")
                data["product_summary"] = result.get("product_summary", "")
                data["package_id"] = result.get("package_id", "")
                data["cover_design"] = result.get("cover_design") or data.get("cover_design")
                data["quality_score"] = result.get("quality_score")
                data["quality_blocking"] = result.get("quality_blocking")
                data["pipeline"] = pipeline.to_dict()
                data["cover_search_query"] = result.get("cover_search_query") or ""
                data["cover_prompt"] = ""
                if fields.get("author_brand"):
                    data["author_brand"] = fields.get("author_brand")
                for key in READINESS_FIELDS:
                    if key in result:
                        data[key] = result[key]
                data["readiness"] = result.get("readiness")
                data["exports"] = result.get("exports")
                apply_ebook_readiness(data, project_type=str(project.get("type") or "ebook"))
                _persist_draft_content_mutation(int(project_id), data)
        result.pop("content", None)
        return jsonify(result)
    except ArtifactStateError as exc:
        return _error(str(exc), 409)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook enhancement failed")
        return _error(str(exc), 500)


@app.post("/ebook/save")
def ebook_save_route():
    """Transactional idempotent Save for factory ebooks. Does not regenerate."""
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_customer_path import save_factory_ebook

        data = body.get("data") if isinstance(body.get("data"), dict) else body
        name = str(body.get("name") or data.get("title") or "Ebook")
        project_id = body.get("project_id") or data.get("_project_id")
        saved = save_factory_ebook(
            data,
            name=name,
            project_id=int(project_id) if project_id not in (None, "") else None,
            user_confirmed=True,
        )
        return jsonify(saved)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook save failed")
        return _error(str(exc), 500)


@app.post("/ebook/regenerate-cover")
def ebook_regenerate_cover_route():
    """Regenerate a factory ebook cover. Keeps the current cover if the new one fails."""
    body = request.get_json(silent=True) or {}
    try:
        from services.ebook_customer_path import regenerate_factory_cover
        from services.quality.artifact_state import ArtifactStateError

        project_id = body.get("project_id")
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        if project_id not in (None, ""):
            project = database.get_project(int(project_id))
            if not project:
                return _error("Project not found.", 404)
            _require_content_mutation_allowed(project.get("data") or {}, action="regenerate cover")
            data = dict(project.get("data") or {})
            data["_project_id"] = int(project_id)
        if body.get("simulate_failure"):
            current = data.get("cover_design")
            return jsonify(
                {
                    "ok": False,
                    "cover_regenerated": False,
                    "cover": current,
                    "message": "The current cover was kept.",
                }
            )
        updated = regenerate_factory_cover(data)
        if project_id not in (None, ""):
            persist = dict(updated)
            persist.pop("_project_id", None)
            _persist_draft_content_mutation(int(project_id), persist)
        return jsonify(
            {
                "ok": bool(updated.get("cover_regenerated")),
                "cover_regenerated": bool(updated.get("cover_regenerated")),
                "cover": updated.get("cover_design"),
                "preview_html": updated.get("preview_html"),
                "message": updated.get("message") or "",
                "exports": updated.get("exports"),
                "ebook_ready": updated.get("ebook_ready"),
            }
        )
    except ArtifactStateError as exc:
        return _error(str(exc), 409)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook cover regeneration failed")
        return _error(str(exc), 500)


@app.post("/retry-ebook-visual")
def retry_ebook_visual_route():
    """Retry one missing factory stock photograph via the shared Pexels service."""
    body = request.get_json(silent=True) or {}
    package_id = str(body.get("package_id") or "").strip()
    visual_id = str(body.get("visual_id") or "").strip()
    aid = body.get("aid") if isinstance(body.get("aid"), dict) else {}
    fields = body.get("fields") if isinstance(body.get("fields"), dict) else {}
    title = str(body.get("title") or fields.get("ebook_title") or fields.get("topic") or "").strip()
    if not package_id or not visual_id:
        return _error("package_id and visual_id are required.", 400)
    aid = dict(aid)
    aid["visual_id"] = visual_id
    aid["type"] = str(aid.get("type") or "stock photo")
    try:
        from services.ebook_factory_pipeline import (
            NEXT_CHOOSE_COVER,
            NEXT_RETRY_IMAGE,
            READINESS_FIELDS,
            apply_ebook_readiness,
            ebook_project_readiness,
            fill_photo_aid_from_pexels,
            replace_visual_aid,
        )
        from services.quality.artifact_state import ArtifactStateError

        filled = fill_photo_aid_from_pexels(
            aid,
            package_id=package_id,
            title=title,
            topic=str(fields.get("topic") or title),
            audience=str(fields.get("audience") or ""),
            chapter=str(aid.get("chapter") or body.get("chapter") or ""),
        )
        ok = bool(filled.get("has_file") and filled.get("rendered"))
        filled["approved"] = False
        payload = {"ok": ok, "aid": filled, "next_action": NEXT_RETRY_IMAGE if not ok else NEXT_CHOOSE_COVER}
        project_id = body.get("project_id")
        visual_plan = body.get("visual_plan") if isinstance(body.get("visual_plan"), dict) else {"chapters": []}
        cover_design = body.get("cover_design") if isinstance(body.get("cover_design"), dict) else {}
        if project_id not in (None, ""):
            project = database.get_project(int(project_id))
            if project:
                try:
                    _require_content_mutation_allowed(
                        project.get("data") or {},
                        action="retry missing ebook photograph",
                    )
                except ArtifactStateError as exc:
                    return _error(str(exc), 409)
                data = dict(project.get("data") or {})
                manuscript = data.get("content")
                ebook_ms = data.get("ebook")
                plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else visual_plan
                data["visual_plan"] = replace_visual_aid(plan, visual_id, filled)
                data["package_id"] = str(data.get("package_id") or package_id)
                if cover_design and not data.get("cover_design"):
                    data["cover_design"] = cover_design
                apply_ebook_readiness(data, project_type=str(project.get("type") or "ebook"))
                data["content"] = manuscript
                data["ebook"] = ebook_ms
                _persist_draft_content_mutation(int(project_id), data)
                state = data.get("readiness") or ebook_project_readiness(data)
                payload["visual_plan"] = data.get("visual_plan")
                payload["next_action"] = state.get("next_action") or payload["next_action"]
                payload["readiness"] = state
                for key in READINESS_FIELDS:
                    payload[key] = state.get(key)
                return jsonify(payload)
        plan = replace_visual_aid(visual_plan, visual_id, filled)
        state = ebook_project_readiness(
            {
                "product_type": "ebook",
                "visual_plan": plan,
                "cover_design": cover_design,
                "package_id": package_id,
            }
        )
        payload["visual_plan"] = plan
        payload["next_action"] = state.get("next_action") or payload["next_action"]
        payload["readiness"] = state
        for key in READINESS_FIELDS:
            payload[key] = state.get(key)
        return jsonify(payload)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("ebook visual retry failed")
        return _error(str(exc), 500)


@app.post("/discover-products")
def discover_products_route():
    body = request.get_json(silent=True) or {}
    mode = str(body.get("mode") or body.get("fma_mode") or "").strip().lower()
    find_ideas = bool(body.get("find_ideas")) or mode in {"discover", "find", "find_ideas"}
    try:
        if find_ideas:
            result = discover_top_opportunities(
                interest=body.get("interest", "") or body.get("topic", "") or body.get("idea", ""),
                audience=body.get("audience", ""),
                product_type=body.get("product_type", ""),
                sales_platform=body.get("sales_platform") or body.get("platform") or "",
                depth=body.get("depth") or "",
                topic=body.get("topic") or body.get("idea") or body.get("interest") or "",
                customer_problem=body.get("customer_problem") or body.get("problem"),
                expertise=body.get("expertise"),
                target_price=body.get("target_price") or body.get("price"),
                keywords=body.get("keywords"),
                niche=body.get("niche", ""),
                goal=body.get("goal", ""),
                difficulty=body.get("difficulty", ""),
                carried_sources=body.get("carried_sources") or body.get("sources"),
            )
            if result.get("retryable") and not result.get("opportunities"):
                result.setdefault(
                    "error",
                    "We couldn't complete the market research. Your idea and filters have been preserved. Please try again.",
                )
                result.setdefault("inputs", collect_inputs(body))
                return jsonify(result), 503
            return jsonify(result)
        return jsonify(
            discover_products(
                body.get("interest", "") or body.get("topic", ""),
                body.get("audience", ""),
                body.get("product_type", ""),
                body.get("difficulty", ""),
                body.get("goal", ""),
                body.get("niche", ""),
                topic=body.get("topic") or body.get("idea"),
                customer_problem=body.get("customer_problem") or body.get("problem"),
                sales_platform=body.get("sales_platform"),
                expertise=body.get("expertise"),
                target_price=body.get("target_price") or body.get("price"),
                keywords=body.get("keywords"),
                depth=body.get("depth"),
                carried_sources=body.get("carried_sources") or body.get("sources"),
                prior_opportunity=body.get("prior_opportunity"),
            )
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("product discovery failed")
        return jsonify(
            {
                "error": (
                    "We couldn't complete the market research. Your idea and filters have been "
                    "preserved. Please try again."
                ),
                "inputs": collect_inputs(body),
                "retryable": True,
            }
        ), 503


@app.post("/factory-market-advantage")
def factory_market_advantage_route():
    """Primary Factory Market Advantage endpoint. Old /discover-products stays."""
    return discover_products_route()


@app.post("/research-to-builder")
def research_to_builder_route():
    """Save selected research as a DRAFT product_plan and name the correct builder.

    Never generates a finished product, cover, PDF, or ZIP.
    """
    body = request.get_json(silent=True) or {}
    opportunity = body.get("opportunity") or {}
    if not isinstance(opportunity, dict) or not (
        str(opportunity.get("product_idea") or "").strip()
        or str(opportunity.get("niche") or "").strip()
    ):
        return _error("Choose Your Advantage before building. An opportunity is required.", 400)

    research_payload = body.get("research") or {}
    if not isinstance(research_payload, dict):
        research_payload = {}
    inputs = collect_inputs(body.get("inputs") or research_payload.get("inputs") or body)
    product_type = (
        opportunity.get("product_type")
        or inputs.get("product_type")
        or research_payload.get("product_type")
        or ""
    )
    builder = resolve_factory_builder(product_type)
    if builder.get("status") != "active":
        return jsonify(
            {
                "error": (
                    "This product type is not ready in the public builder yet. "
                    "Save the research and pick an active Factory type."
                ),
                "builder": builder,
                "generated": False,
            }
        ), 409

    research_id = body.get("research_id") or body.get("project_id")
    research_payload["selected_opportunity"] = opportunity
    research_payload["stage"] = "research_saved"
    name = f"Research: {opportunity.get('product_idea') or opportunity.get('niche') or inputs.get('topic') or 'Market Advantage'}"
    try:
        if research_id:
            existing = database.get_project(int(research_id))
            if not existing:
                return _error("Research project not found.", 404)
            saved_research = database.update_project(
                int(research_id),
                name=existing.get("name") or name,
                type_="research_plan",
                data={**(existing.get("data") or {}), **research_payload, "selected_opportunity": opportunity, "stage": "research_saved"},
            )
        else:
            saved_research = database.create_project(
                name,
                "research_plan",
                {**research_payload, "selected_opportunity": opportunity, "stage": "research_saved"},
                user_saved=True,
            )
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("research save during handoff failed")
        return _error(str(exc), 500)

    draft = draft_handoff_payload(
        opportunity=opportunity,
        research={**research_payload, "id": saved_research.get("id")},
        inputs=inputs,
    )
    draft["research_id"] = saved_research.get("id")
    plan_name = (draft.get("plan") or {}).get("product_title") or name
    # Same-record handoff: research_plan becomes product_plan DRAFT (existing Factory lineage).
    saved_plan = database.update_project(
        int(saved_research["id"]),
        name=plan_name,
        type_="product_plan",
        data=draft,
        user_saved=True,
    )
    return jsonify(
        {
            "id": saved_plan["id"],
            "type": saved_plan["type"],
            "data": saved_plan["data"],
            "research_id": saved_research.get("id"),
            "builder": builder,
            "factory_id": builder.get("factory_id"),
            "product_type": draft.get("product_type"),
            "generated": False,
            "auto_generated": False,
            "artifact_state": (saved_plan.get("data") or {}).get("artifact_state"),
        }
    ), 201


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
    coloring_preview = is_coloring_preview_filename(filename)
    if not is_allowed_download(filename) and not coloring_preview:
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
        if coloring_preview:
            return _error(coloring_preview_missing_message(filename), 404)
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

    # Passed: serve from disk. Preview images must display in <img>, not download.
    as_attachment = not (
        filename.startswith("img_") or is_coloring_preview_filename(filename)
    )
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
        data = project.get("data") or {}
        if data.get("customer_keep") is True:
            from services.customer_keep_exports import reuse_existing_keep_export

            reused = reuse_existing_keep_export(project)
            # customer_keep protects an ACCEPTED artifact from being rebuilt.
            # It must not prevent building one that never existed: a keep
            # project whose package has no ebook.pdf was stuck permanently at
            # "Build PDF" because this path returned the pdf-less bundle every
            # time. With no PDF there is nothing to preserve, so fall through
            # to the normal export and create it.
            if reused is not None and not (
                (reused.get("exports") or {}).get("files", {}).get("pdf")
            ):
                reused = None
            if reused is not None:
                return jsonify(reused)
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
        # Legacy download pointers must follow the new export package. Leaving
        # pdf_path / pdf_sha256 / export_files on the previous package makes
        # row-level download buttons request a stale file, which the download
        # pipeline then blocks as a bytes-vs-authoritative mismatch.
        _new_pkg = str(result.get("package_id") or "")
        _pkg_dir = os.path.join(EXPORTS_DIR, _new_pkg) if _new_pkg else ""
        _new_pdf = os.path.join(_pkg_dir, "ebook.pdf") if _pkg_dir else ""
        # Deterministic PDF products (planners, worksheets) name their file
        # after the product rather than ebook.pdf. Fall back to whatever the
        # package actually published, or the download pointers below stay on a
        # file this package does not contain.
        if _pkg_dir and not os.path.isfile(_new_pdf):
            _pdf_url = str(
                (((result.get("exports") or {}).get("files") or {}).get("pdf") or {}).get("url") or ""
            )
            _pdf_basename = _pdf_url.rsplit("/", 1)[-1] if _pdf_url else ""
            if _pdf_basename:
                _candidate = os.path.join(_pkg_dir, _pdf_basename)
                if os.path.isfile(_candidate):
                    _new_pdf = _candidate
        if _new_pdf and os.path.isfile(_new_pdf):
            import hashlib as _hashlib

            data["pdf_path"] = _new_pdf
            data["_pdf_path"] = _new_pdf
            try:
                with open(_new_pdf, "rb") as _fh:
                    data["pdf_sha256"] = _hashlib.sha256(_fh.read()).hexdigest()
            except OSError:
                pass
            if isinstance(data.get("export_files"), dict):
                _files: dict = {"dir": _pkg_dir}
                for _name in os.listdir(_pkg_dir):
                    _fp = os.path.join(_pkg_dir, _name)
                    if os.path.isfile(_fp):
                        _files[_name] = _fp
                data["export_files"] = _files
        # Ebook release gate: Export Ready / customer downloads only on PASS.
        is_ebook = (
            project.get("type") == "ebook"
            or str(data.get("product_type") or "").lower() == "ebook"
            or bool(data.get("ebook"))
        )
        if is_ebook:
            release_status = str(data.get("release_status") or "").upper()
            cert = data.get("release_certificate") if isinstance(data.get("release_certificate"), dict) else None
            # Editor-in-Chief completion review: every ebook export receives an
            # automated editorial pass over the real rendered artifact before
            # the factory calls it ready to sell. Findings are persisted so the
            # UI can show what failed, where, why, and the next action.
            eic_ok = True
            try:
                from services.editor_in_chief import VERDICT_PASS
                from services.editor_in_chief_ebook import (
                    collect_ebook_candidate,
                    review_ebook,
                )

                if _new_pdf and os.path.isfile(_new_pdf):
                    import tempfile

                    import fitz

                    page_dir = tempfile.mkdtemp(prefix="eic_pages_")
                    page_images: list[str] = []
                    pdf_doc = fitz.open(_new_pdf)
                    for _pi, _page in enumerate(pdf_doc):
                        _img = os.path.join(page_dir, f"p{_pi + 1:03d}.png")
                        _page.get_pixmap(dpi=72).save(_img)
                        page_images.append(_img)
                    candidate = collect_ebook_candidate(
                        data, package_dir=_pkg_dir, page_images=page_images
                    )
                    report = review_ebook(candidate)
                    eic_ok = report.verdict == VERDICT_PASS
                    data["editor_in_chief"] = {
                        "verdict": report.verdict,
                        "overall": report.overall,
                        "scores": report.scores,
                        "findings": [
                            {
                                "code": fi.code,
                                "severity": fi.severity,
                                "summary": fi.summary,
                                "location": fi.location,
                            }
                            for fi in report.findings
                        ],
                        "checks_run": report.checks_run,
                        "checks_skipped": report.checks_skipped,
                    }
                    result["editor_in_chief"] = data["editor_in_chief"]
            except Exception:
                # The reviewer itself failing must not hide the export, but it
                # must be visible — an unreviewed ebook is not "ready".
                app.logger.exception("editor-in-chief review failed")
                eic_ok = False
                data["editor_in_chief"] = {
                    "verdict": "EDITOR-IN-CHIEF — REVIEW ERROR",
                    "error": "Automated review could not run; see server log.",
                }
                result["editor_in_chief"] = data["editor_in_chief"]
            export_ready = (
                bool(data.get("export_ready"))
                and release_status == "PASS"
                and bool(cert)
                and str(cert.get("issued_by") or "") == "server"
                and str(cert.get("status") or "").upper() == "PASS"
                and eic_ok
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

        # Planner release gate: the same rule as the ebook path — an automated
        # editorial pass over the real rendered PDF decides Export Ready. The
        # planner reviewer is a separate module because a planner's repeated
        # worksheet pages and typographic cover would fail the ebook rules for
        # reasons that are not defects.
        planner_type = str(data.get("product_type") or project.get("type") or "").lower()
        if planner_type in ("faith_planner", "budget_planner"):
            eic_ok = False
            try:
                from services.editor_in_chief import VERDICT_PASS
                from services.editor_in_chief_planner import (
                    collect_planner_candidate,
                    review_planner,
                )
                from services.planner import PlannerPdfRequest, build_planner_pdf

                _pf = data.get("fields") or {}
                # Rebuild the page plan from the saved fields so the reviewer
                # has the structure to measure the PDF against. The builder is
                # deterministic, so this reproduces the exported page plan.
                rebuilt = build_planner_pdf(PlannerPdfRequest(
                    planner_type=planner_type,
                    title=str(data.get("title") or ""),
                    theme=str(_pf.get("theme") or ""),
                    audience=str(_pf.get("audience") or ""),
                    author=str(_pf.get("author") or ""),
                    pages=int(data.get("declared_pages") or 60),
                    page_size=str(_pf.get("page_size") or "US Letter"),
                ))
                # Review the PDF the customer will actually receive. Only fall
                # back to the rebuilt copy when no exported file can be found —
                # reviewing a stand-in and reporting it as a verdict on the
                # shipped artifact is the failure this gate exists to prevent.
                _planner_pdf = ""
                for _cand in (data.get("pdf_path"), data.get("_pdf_path")):
                    if _cand and os.path.isfile(str(_cand)):
                        _planner_pdf = str(_cand)
                        break
                if not _planner_pdf and _pkg_dir and os.path.isdir(_pkg_dir):
                    for _name in sorted(os.listdir(_pkg_dir)):
                        if _name.lower().endswith(".pdf"):
                            _planner_pdf = os.path.join(_pkg_dir, _name)
                            break
                if not _planner_pdf:
                    _planner_pdf = rebuilt.pdf_path
                    data.setdefault("editor_in_chief_notes", []).append(
                        "Reviewed a deterministic rebuild: no exported planner "
                        "PDF was found in the package directory."
                    )
                import tempfile

                import fitz

                page_dir = tempfile.mkdtemp(prefix="eic_planner_")
                page_images: list[str] = []
                pdf_doc = fitz.open(_planner_pdf)
                for _pi, _page in enumerate(pdf_doc):
                    _img = os.path.join(page_dir, f"p{_pi + 1:03d}.png")
                    _page.get_pixmap(dpi=72).save(_img)
                    page_images.append(_img)
                pdf_doc.close()

                candidate = collect_planner_candidate(
                    rebuilt.plan, pdf_path=_planner_pdf,
                    package_dir=_pkg_dir or rebuilt.package_dir,
                    page_images=page_images,
                    author=str((data.get("fields") or {}).get("author") or ""),
                )
                report = review_planner(candidate)
                eic_ok = report.verdict == VERDICT_PASS
                data["editor_in_chief"] = {
                    "verdict": report.verdict,
                    "overall": report.overall,
                    "scores": report.scores,
                    "findings": [
                        {
                            "code": fi.code,
                            "severity": fi.severity,
                            "summary": fi.summary,
                            "location": fi.location,
                        }
                        for fi in report.findings
                    ],
                    "checks_run": report.checks_run,
                    "checks_skipped": report.checks_skipped,
                }
                result["editor_in_chief"] = data["editor_in_chief"]
            except Exception:
                # An unreviewed planner is not "ready" — same stance as ebooks.
                app.logger.exception("editor-in-chief planner review failed")
                eic_ok = False
                data["editor_in_chief"] = {
                    "verdict": "EDITOR-IN-CHIEF — REVIEW ERROR",
                    "error": "Automated review could not run; see server log.",
                }
                result["editor_in_chief"] = data["editor_in_chief"]
            data["export_ready"] = bool(eic_ok)
            result["export_ready"] = bool(eic_ok)
            data["stage"] = "export_ready" if eic_ok else (
                data.get("stage") or "product_generated"
            )

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


def _slim_workspace_list_item(project: dict) -> dict:
    """Drop the huge legacy preview_html/content blobs from list responses.

    Workspace ebooks (data.ebook_workspace is True) never render p.data
    directly from a /projects list payload -- app.js's openProject() always
    routes them to a fresh GET /ebook-workspace/<id> fetch instead (see
    openEbookWorkspace). So carrying the full rendered preview_html (seen up
    to ~480KB for one book) and raw manuscript content in every list/dashboard
    response was pure dead weight -- enough of it, across a handful of saved
    books, to make the browser tab stall while parsing/rendering the list.
    Non-workspace ebooks/products DO render data.preview_html directly from
    this same payload, so only workspace-flagged items are slimmed.
    """
    data = project.get("data") if isinstance(project.get("data"), dict) else None
    if not isinstance(data, dict) or not data.get("ebook_workspace"):
        return project
    heavy_fields = ("preview_html", "ebook_preview_html", "content")
    if not any(data.get(f) for f in heavy_fields):
        return project
    slim = dict(data)
    for f in heavy_fields:
        if slim.get(f):
            slim[f] = ""
    project = dict(project)
    project["data"] = slim
    return project


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
    from services.ebook_factory_pipeline import apply_ebook_readiness

    apply_ebook_readiness(data, project_type=str(project.get("type") or ""))
    if str(data.get("product_type") or "").strip().lower() == "coloring_book":
        from services.coloring_book.prompt_engine import stamp_coloring_author_fields

        stamp_coloring_author_fields(data)
        attach_coloring_preview_urls(data, project_id=project.get("id"))
    return project


@app.get("/projects")
def list_projects_route():
    """List projects.

    Customer default: up to 10 intentionally saved completed products.
    Dashboard uses the same filter with ?limit=3.
    Admin (?admin=1 or include_system=1) sees everything.
    Factory source dropdowns use ?factory_sources=1.
    """
    include_system = request.args.get("include_system", "0") == "1"
    admin = request.args.get("admin", "0") == "1"
    factory_sources = request.args.get("factory_sources", "0") == "1"
    if include_system or admin:
        projects = database.list_projects(include_system=True)
        return jsonify([_slim_workspace_list_item(_enrich_project_artifact_fields(p)) for p in projects])
    if factory_sources:
        projects = database.list_factory_source_projects()
        return jsonify([_slim_workspace_list_item(_enrich_project_artifact_fields(p)) for p in projects])
    try:
        limit = int(request.args.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    limit = min(max(limit, 1), 10)
    offset = max(offset, 0)
    projects, has_more = database.get_customer_saved_products(limit=limit, offset=offset)
    resp = jsonify([_slim_workspace_list_item(_enrich_project_artifact_fields(p)) for p in projects])
    resp.headers["X-Saved-Has-More"] = "1" if has_more else "0"
    return resp


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


@app.get("/projects/<int:project_id>/coloring-preview/<filename>")
def coloring_preview_route(project_id: int, filename: str):
    """Serve on-disk coloring cover/interior images for the factory preview.

    Project-scoped display URL. Does not regenerate artwork or alter PDF/ZIP.
    """
    if not is_coloring_preview_filename(filename):
        return _error("Unknown coloring preview file.", 404)
    project = database.get_project(project_id)
    if not project:
        return _error("Project not found.", 404)
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    if str(data.get("product_type") or "").strip().lower() != "coloring_book":
        return _error("Coloring preview is only available for coloring books.", 404)
    pkg = str(data.get("package_id") or data.get("export_package_id") or "").strip()
    if not pkg or not _PACKAGE_ID_RE.match(pkg):
        return _error("Coloring preview package is missing.", 404)
    directory = os.path.join(EXPORTS_DIR, pkg)
    file_path = os.path.join(directory, filename)
    try:
        exports_root = os.path.realpath(EXPORTS_DIR)
        real_file = os.path.realpath(file_path)
        if not real_file.startswith(exports_root + os.sep):
            return _error("Invalid coloring preview path.", 400)
    except OSError:
        return _error(coloring_preview_missing_message(filename), 404)
    if not os.path.isfile(file_path):
        return _error(coloring_preview_missing_message(filename), 404)
    return send_from_directory(directory, filename, as_attachment=False)


@app.post("/projects")
def create_project_route():
    """Create a project. Applies backend safety guard for test/debug names."""
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    type_ = (body.get("type") or "").strip()
    if not name or not type_:
        return _error("Project name and type are required.", 400)

    # Resolve save flags — backend safety guard runs inside apply_save_flags.
    # user_saved=true is not enough to keep an internal/test name visible.
    explicit_save = body.get("user_saved")
    confirmed = bool(body.get("user_confirmed_save"))
    user_saved, system_test, temporary = database.apply_save_flags(
        name=name,
        explicit_user_save=bool(explicit_save) if explicit_save is not None else None,
        system_test=body.get("system_test"),
        temporary=body.get("temporary"),
        type_=type_,
        data=body.get("data") if isinstance(body.get("data"), dict) else {},
        user_confirmed_save=confirmed,
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
        user_confirmed_save=confirmed,
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
    confirmed = bool(body.get("user_confirmed_save"))

    if name:
        name = name.strip()
        user_saved, system_test, temporary = database.apply_save_flags(
            name=name,
            explicit_user_save=bool(user_saved_arg) if user_saved_arg is not None else None,
            system_test=bool(system_test_arg) if system_test_arg is not None else None,
            temporary=bool(temporary_arg) if temporary_arg is not None else None,
            type_=body.get("type"),
            data=body.get("data") if isinstance(body.get("data"), dict) else {},
            user_confirmed_save=confirmed,
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
        user_confirmed_save=confirmed,
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
    from services.quality.artifact_state import ArtifactStateError

    try:
        if not database.delete_project(project_id):
            return _error("Project not found.", 404)
    except ArtifactStateError as exc:
        return _error(str(exc), 409)
    return jsonify({"ok": True})


@app.delete("/projects")
def delete_all_projects():
    """Bulk-delete projects. Requires delete_all=1 AND user_saved_only=1.
    This prevents accidental deletion of hidden system/test records.
    Hidden records can only be deleted when the test/debug toggle is on
    and they are individually confirmed. LOCKED projects are never deleted.
    """
    import flask
    delete_all = flask.request.args.get("delete_all")
    user_saved_only = flask.request.args.get("user_saved_only")
    if delete_all != "1" or user_saved_only != "1":
        return _error("Invalid bulk-delete request.", 400)
    result = database.delete_matching_projects(
        "user_saved = 1 AND system_test = 0 AND temporary = 0"
    )
    return jsonify(
        {
            "ok": True,
            "deleted": result["deleted"],
            "locked_skipped": result["locked_skipped"],
            "skipped_ids": result["skipped_ids"],
        }
    )


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
    """Delete test/debug/temporary projects. LOCKED rows are never deleted."""
    import datetime, shutil, os as _os
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    src = database.DB_PATH
    bak_dir = _os.path.dirname(src)
    bak_name = f"projects_BACKUP_{ts}.db"
    bak_path = _os.path.join(bak_dir, bak_name)
    shutil.copy2(src, bak_path)
    result = database.delete_matching_projects(
        "system_test = 1 OR temporary = 1 OR user_saved = 0"
    )
    return jsonify(
        {
            "ok": True,
            "deleted": result["deleted"],
            "locked_skipped": result["locked_skipped"],
            "skipped_ids": result["skipped_ids"],
            "backup_path": bak_path,
        }
    )


@app.get("/coloring-ai-status")
def coloring_ai_status():
    """Return Coloring Book image AI configuration status. Does not expose secrets."""
    # Import helpers from ai_client which handles the fallback chain
    from ai_client import _is_placeholder_key, get_key_source, get_base_url_source

    from dotenv import load_dotenv
    load_dotenv(override=not _FACTORY_TEST_MODE)  # see the module-level call

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
            from services.coloring_book.prompt_engine import (
                coloring_cover_draws_author,
                is_bank_rescue_theme,
            )

            overrides = dict(overrides or {})
            pdata = project.get("data") or {}
            cover = pdata.get("cover_design") if isinstance(pdata.get("cover_design"), dict) else {}
            fields = pdata.get("fields") if isinstance(pdata.get("fields"), dict) else {}
            style = str(cover.get("overlay_style") or "")
            theme = str(fields.get("theme") or pdata.get("title") or "")
            if (style and not coloring_cover_draws_author(style)) or is_bank_rescue_theme(theme):
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
            from services.coloring_book.prompt_engine import (
                coloring_cover_draws_author,
                is_bank_rescue_theme,
            )

            overrides = dict(overrides or {})
            pdata = ((project or {}).get("data") or {})
            cover = pdata.get("cover_design") if isinstance(pdata.get("cover_design"), dict) else {}
            fields = pdata.get("fields") if isinstance(pdata.get("fields"), dict) else {}
            style = str(cover.get("overlay_style") or "")
            theme = str(fields.get("theme") or pdata.get("title") or "")
            hide_author = (style and not coloring_cover_draws_author(style)) or is_bank_rescue_theme(theme)
            if hide_author:
                overrides["author"] = ""
            overrides.setdefault("text_position", {"x": 50.0, "y": 81.0, "align": "center"})
            overrides.setdefault("text_y", 78)
            overrides.setdefault("text_overlay", True)
        saved = save_cover(existing, overrides, package_id=package_id)
        if product_type == "coloring_book":
            pdata = ((project or {}).get("data") or {})
            cover = pdata.get("cover_design") if isinstance(pdata.get("cover_design"), dict) else {}
            fields = pdata.get("fields") if isinstance(pdata.get("fields"), dict) else {}
            style = str(cover.get("overlay_style") or saved.get("overlay_style") or "")
            theme = str(fields.get("theme") or pdata.get("title") or "")
            from services.coloring_book.prompt_engine import (
                coloring_cover_draws_author,
                is_bank_rescue_theme,
            )

            if (style and not coloring_cover_draws_author(style)) or is_bank_rescue_theme(theme):
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
            if str(brief.get("overlay_style") or "") == "clean_title":
                cover["author"] = ""
            else:
                from services.coloring_book.prompt_engine import resolve_coloring_book_author

                cover["author"] = resolve_coloring_book_author(
                    cover.get("author"),
                    data.get("author"),
                    data.get("author_brand"),
                    fields.get("author_brand"),
                    fields.get("author"),
                )
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
            if str(brief.get("overlay_style") or "") == "clean_title":
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
