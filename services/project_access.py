"""Request ownership for the explicit accounts rollout; private mode is unchanged.

Background workers have no HTTP identity and remain trusted server code. Only a
signed, active Flask-Login session supplies a customer identity. No request field
is an identity. Unreviewed endpoints fail closed in accounts mode.
"""
from __future__ import annotations

import os
from pathlib import Path

from flask import has_request_context, jsonify, redirect, request
from flask_login import current_user
from werkzeug.exceptions import Forbidden, Unauthorized


def accounts_mode() -> bool:
    mode = os.environ.get('FACTORY_ACCESS_MODE', 'private').strip().lower()
    if mode not in ('private', 'accounts'):
        raise RuntimeError('Factory access mode is not configured correctly.')
    return mode == 'accounts'


def request_owner() -> int | None:
    if not has_request_context() or not accounts_mode():
        return None
    if not current_user.is_authenticated or not current_user.is_active:
        raise Unauthorized('Please sign in.')
    return int(current_user.id)


def ownership_clause() -> tuple[str, tuple]:
    owner = request_owner()
    if owner is None or current_user.is_admin:
        return '', ()
    return ' AND user_id = ?', (owner,)


def require_owner_administration() -> None:
    if request_owner() is not None and not current_user.is_admin:
        raise Forbidden('Administrator access required.')


def export_directory(base: str, filename: str | None = None) -> str:
    owner = request_owner()
    if owner is None:
        return base
    directory = Path(base) / 'accounts' / str(owner)
    # Legacy standalone puzzle files stay available to the owner/admin only.
    if filename and current_user.is_admin and not (directory / filename).is_file():
        return base
    return str(directory)


PUBLIC_ENDPOINTS = frozenset({
    'auth.signin_page', 'auth.login', 'auth.register', 'auth.logout', 'auth.me',
    'static', 'invite_route', 'billing_stripe_webhook_route',
    'billing_lemon_webhook_route', 'public_plans_route',
})
# These endpoints either create state entirely on the server or use the scoped
# database reads below. Generic raw-project writes and unreviewed marketing,
# billing and rendering APIs are intentionally unavailable to customers during
# this rollout. Admin/owner access and the private Factory are preserved.
CUSTOMER_ENDPOINTS = frozenset({
    'index', 'list_projects_route', 'get_project_route',
    'list_unfinished_ebook_workspaces_route', 'create_ebook_workspace_route',
    'ebook_build_start_route', 'download_export_route',
    'publishing_templates_route', 'ebook_execution_mode_route',
    'word_search_builder.word_search_builder_page',
    'word_search_builder.word_search_builder_generate',
    'word_search_builder.word_search_builder_download',
    'crossword_builder.crossword_builder_page',
    'crossword_builder.crossword_builder_generate',
    'crossword_builder.crossword_builder_download',
})
WORKSPACE_ENDPOINTS = frozenset({
    'get_ebook_workspace_route',
    'ebook_workspace_cover_preview_route',
    'save_ebook_workspace_research_route',
    'run_ebook_workspace_research_route',
    'generate_ebook_workspace_title_options_route',
    'generate_ebook_workspace_outline_options_route',
    'approve_ebook_workspace_stage_route',
    'edit_ebook_workspace_author_route',
    'edit_ebook_workspace_title_route',
    'edit_ebook_workspace_outline_route',
    'estimate_ebook_workspace_cost_route',
    'cancel_ebook_workspace_estimate_route',
    'authorize_ebook_workspace_budget_route',
    'generate_ebook_workspace_manuscript_route',
    'correct_ebook_workspace_manuscript_route',
    'ebook_workspace_visuals_route',
    'ebook_workspace_cover_route',
    'ebook_workspace_cover_image_route',
    'ebook_workspace_cover_photo_route',
    'ebook_workspace_cover_variant_route',
    'ebook_workspace_design_route',
    'ebook_workspace_preview_route',
    'ebook_workspace_full_preview_route',
    'ebook_workspace_preview_opened_route',
    'ebook_workspace_preflight_route',
    'ebook_previous_exports_route',
    'ebook_previous_export_download',
    'ebook_release_review_estimate_route',
    'ebook_release_review_route',
    'ebook_release_review_current_route',
    'ebook_release_review_decision_route',
    'ebook_release_review_acknowledge_route',
    'ebook_approve_product_route',
    'ebook_release_review_page',
    'ebook_workspace_rewind_route',
    'ebook_generate_project_route',
    'ebook_cover_choice_route',
    'ebook_build_advance_route',
    'ebook_build_resume_route',
    'ebook_build_status_route',
    'ebook_manuscript_editor_route',
    'ebook_workspace_manuscript_route',
})
PROJECT_KEYS = frozenset({'project_id', '_project_id', 'product_project_id',
                          'research_id', 'source_project_id', 'parent_project_id'})
PACKAGE_KEYS = frozenset({'package_id', 'export_package_id'})


def _references(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in PROJECT_KEYS and item not in (None, '', 0, '0'):
                yield 'project', item
            elif key == 'project_ids' and isinstance(item, list):
                for project in item:
                    yield 'project', project
            elif key in PACKAGE_KEYS and item:
                yield 'package', item
            elif key == 'local_path' and item:
                # Operator-only import: a client-supplied server path could
                # copy another customer's image into an otherwise owned book.
                yield 'server_path', item
            if isinstance(item, (dict, list)):
                yield from _references(item)
    elif isinstance(value, list):
        for item in value:
            yield from _references(item)


def guard_request():
    try:
        enabled = accounts_mode()
    except RuntimeError:
        return jsonify(ok=False, error='Factory access is temporarily unavailable.'), 503
    if not enabled:
        return None
    # A per-process random fallback cannot support durable account sessions.
    if len(os.environ.get('SECRET_KEY', '')) < 32:
        return jsonify(ok=False, error='Account access is not ready yet.'), 503
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if not current_user.is_authenticated or not current_user.is_active:
        if (request.method == 'GET' and request.path == '/'
                and 'text/html' in request.headers.get('Accept', '')
                and request.accept_mimetypes['text/html'] > 0):
            return redirect('/plans')
        return jsonify(ok=False, error='Please sign in.'), 401
    if current_user.is_admin:
        return None
    args = request.view_args or {}
    endpoint = request.endpoint or ''
    # Project workspace routes are reviewed separately from generic project
    # mutation and operator APIs. New routes do not become public implicitly.
    workspace = endpoint in WORKSPACE_ENDPOINTS
    if not workspace and endpoint not in CUSTOMER_ENDPOINTS:
        return jsonify(ok=False, error='This action is not available for this account.'), 403
    if request.args.get('admin') == '1' or request.args.get('include_system') == '1':
        return jsonify(ok=False, error='Administrator access required.'), 403
    import database
    references = [*list(_references(args)), *list(_references(request.args.to_dict())),
                  *list(_references(request.form.to_dict())),
                  *list(_references(request.get_json(silent=True) or {}))]
    for kind, value in references:
        if kind == 'server_path':
            return jsonify(ok=False, error='Server file imports require administrator access.'), 403
        if kind == 'project':
            try:
                owner = database.get_project_owner(int(value))
            except (TypeError, ValueError):
                owner = None
            allowed = owner == int(current_user.id)
        else:
            allowed = database.find_project_by_package(str(value)) is not None
        if not allowed:
            return jsonify(ok=False, error='Project not found.'), 404
    return None
