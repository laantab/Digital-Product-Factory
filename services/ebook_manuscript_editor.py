"""Free, reversible editing of preserved manuscripts. No provider imports."""
from __future__ import annotations

import copy
import difflib
import hashlib
from collections import Counter


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def current_text(data: dict) -> str:
    return str(data.get('content') or data.get('ebook') or '')


def preview(data: dict, proposed: str | None = None) -> dict:
    from services.ebook_copy_editor import edit_text
    from services.ebook_manuscript_engine import validate_manuscript_quality
    original = current_text(data)
    if not original.strip():
        raise ValueError('This project has no manuscript to edit.')
    report = edit_text(original)
    edited = report['edited'] if proposed is None else proposed
    if not isinstance(edited, str) or not edited.strip():
        raise ValueError('The manuscript cannot be empty.')
    if len(edited.encode('utf-8')) > 2_000_000:
        raise ValueError('The edited manuscript is too large.')
    before = validate_manuscript_quality(data, manuscript_md=original)
    after = validate_manuscript_quality(data, manuscript_md=edited)
    def findings(quality):
        return Counter(quality.finding_messages)
    new_findings = list((findings(after) - findings(before)).elements())
    return {
        'original': original, 'edited': edited,
        'original_sha256': digest(original), 'edited_sha256': digest(edited),
        'diff': ''.join(difflib.unified_diff(original.splitlines(True), edited.splitlines(True),
                                           fromfile='Original', tofile='Edited')),
        'copy_review': report, 'quality': after.as_dict(),
        'new_findings': new_findings, 'can_apply': not new_findings,
        'paid_calls': 0,
    }


def apply_edit(data: dict, proposed: str, expected_digest: str, *, undo: bool = False) -> dict:
    from services.ebook_manuscript_engine import (
        QUALITY_PASS, apply_quality_to_workspace, split_front_chapters_back,
        validate_manuscript_quality,
    )
    from services.ebook_project_workspace import (
        ensure_workspace, invalidate_after, set_stage_status, sync_document_from_workspace,
        STATUS_AWAITING, STATUS_NEEDS_CORRECTION, _append_history,
    )
    from services.ebook_release_validator import invalidate_release_on_data
    original = current_text(data)
    if not expected_digest or digest(original) != expected_digest:
        raise ValueError('The manuscript changed. Reload it before applying edits.')
    result = copy.deepcopy(data)
    result = ensure_workspace(result)
    ws = result['ebook_workspace']
    build = result.get('ebook_build') or {}
    if any(r.get('status') == 'RUNNING' for r in (build.get('stages') or {}).values()):
        raise ValueError('Wait for the current build step to finish before editing.')
    if undo:
        revisions = ws.get('manuscript_edit_history') or []
        if not revisions or revisions[-1]['edited_sha256'] != digest(original):
            raise ValueError('There is no current edit to undo.')
        proposed = revisions[-1]['original']
    review = preview(result, proposed)
    # Undo restores exact prior bytes, including pre-existing findings; it
    # still reruns QA and never restores a release certificate.
    if not undo and not review['can_apply']:
        raise ValueError('These edits introduce new manuscript findings: ' + '; '.join(review['new_findings'][:5]))
    if proposed == original:
        return result
    if undo:
        ws['manuscript_edit_history'].pop()
    else:
        ws.setdefault('manuscript_edit_history', []).append({
            'original': original, 'edited': proposed,
            'original_sha256': digest(original), 'edited_sha256': digest(proposed),
        })
    result['content'] = result['ebook'] = proposed
    quality = validate_manuscript_quality(result, manuscript_md=proposed)
    apply_quality_to_workspace(result, quality)
    _, chapters, _ = split_front_chapters_back(proposed)
    passing = {int(c['order']) for c in quality.chapter_results if c.get('status') == QUALITY_PASS}
    ws['accepted_chapters'] = [
        {'order': c.order, 'title': c.title, 'body': c.body}
        for c in chapters if c.order in passing
    ]
    invalidate_after(ws, 'manuscript', reason='Manuscript edited; review the new revision')
    set_stage_status(ws, 'manuscript', STATUS_AWAITING if quality.status == QUALITY_PASS else STATUS_NEEDS_CORRECTION)
    result['artifact_revision'] = int(result.get('artifact_revision') or 1) + 1
    result['revision'] = int(result.get('revision') or 1) + 1
    invalidate_release_on_data(result)
    ws.get('paid_call_ledger', {}).update(pending_estimate=None)
    # Keep old files for recovery. Their approvals must not certify new text.
    for key in ('ebook_preview_html', 'preview_html', 'ebook_design_preflight', 'release_review'):
        result.pop(key, None)
    build['finished'] = False
    build['paused_after'] = 'manuscript'
    for stage in ('manuscript', 'visuals', 'cover', 'design', 'preview', 'preflight', 'export'):
        (build.get('stages') or {}).pop(stage, None)
    _append_history(ws, 'undo_manuscript_edit' if undo else 'edit_manuscript',
                    original_sha256=digest(original), edited_sha256=digest(proposed), paid_calls=0)
    document = result.get('ebook_document')
    if isinstance(document, dict):
        document['release_status'] = ''
        document['release_messages'] = []
    # Document generation normalizes whitespace for rendering. Preserve the
    # reviewed source bytes so the saved draft and undo hashes stay exact.
    result = sync_document_from_workspace(result, sync_manuscript=False)
    return invalidate_release_on_data(result)
