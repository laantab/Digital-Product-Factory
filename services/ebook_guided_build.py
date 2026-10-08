"""Automatic ebook preparation with one persisted title-and-cover decision."""
from __future__ import annotations
import copy
import uuid


def enabled(data):
    return (data.get('fields') or {}).get('guided_cover_choice') is True


def start(data):
    from services.quality.artifact_state import assert_content_mutable
    from services.ebook_build_orchestrator import build_state, clear_pause
    assert_content_mutable(data)
    data = copy.deepcopy(data)
    fields = data.setdefault('fields', {})
    fields['guided_cover_choice'] = True
    fields.setdefault('topic', data.get('topic') or data.get('source') or data.get('title') or '')
    fields.setdefault('author_brand', data.get('author_brand') or data.get('author') or '')
    state = build_state(data)
    if not state.get('build_id'):
        state['build_id'] = uuid.uuid4().hex[:16]
    clear_pause(data)
    if not state.get("awaiting_cover_choice"):
        state["awaiting_picture_approval"] = False
    return data


def public_choice(data, pid):
    from services.ebook_photo_cover import photo_cover_public_fields
    ws = data.get('ebook_workspace') or {}
    photo = photo_cover_public_fields(data, project_id=pid)
    return {
        'title_options': [{'id': str(o.get('id') or ''), 'title': str(o.get('title') or ''),
                           'subtitle': str(o.get('subtitle') or '')}
                          for o in ws.get('title_options', [])],
        'selected_title_id': str(ws.get('approved_title_id') or ''),
        'variants': [v for v in photo.get('variants', []) if v.get('quality_pass') and v.get('thumb_url')],
    }


def record_choice(data, body):
    from services.quality.artifact_state import assert_content_mutable
    from services.ebook_build_orchestrator import build_state
    assert_content_mutable(data)
    data = copy.deepcopy(data)
    state = build_state(data)
    if not enabled(data) or not state.get('awaiting_cover_choice'):
        raise ValueError('Your title and cover are not ready for selection yet.')
    ws = data.get('ebook_workspace') or {}
    if body.get('action') == 'title':
        choice = str(body.get('title_id') or '')
        if not choice or not any(str(o.get('id')) == choice for o in ws.get('title_options', [])):
            raise ValueError('Choose one of the suggested titles.')
        state['pending_title_id'] = choice
    elif body.get('action') == 'finish':
        if str(body.get('title_id') or '') != str(ws.get('approved_title_id') or ''):
            raise ValueError('Update the title first so the cover preview matches your choice.')
        layout = str(body.get('layout_id') or '')
        variant = ((data.get('cover_design') or {}).get('variants') or {}).get(layout) or {}
        if not (variant.get('quality') or {}).get('pass') or not variant.get('digest'):
            raise ValueError('Choose a cover that passed its quality check.')
        if str(body.get('digest') or '') != str(variant.get('digest')):
            raise ValueError('The cover changed. Please choose from the current previews.')
        state['pending_cover_layout'] = layout
        state['pending_cover_digest'] = str(variant['digest'])
    else:
        raise ValueError('Choose a title or finish with your selected cover.')
    state['awaiting_cover_choice'] = False
    return data


def run_cover(data, pid, prepare):
    data = copy.deepcopy(data)
    from services.ebook_build_orchestrator import build_state
    from services.ebook_project_workspace import approve_stage, set_stage_status, STATUS_AWAITING
    from services.ebook_photo_cover import _activate_source, select_layout
    from services.ebook_design_workspace import stage_photo_cover
    state = build_state(data)
    title_id = state.pop('pending_title_id', '')
    layout = state.pop('pending_cover_layout', '')
    digest = state.pop('pending_cover_digest', '')
    if layout:
        variant = ((data.get('cover_design') or {}).get('variants') or {}).get(layout) or {}
        if str(variant.get('digest') or '') != digest:
            raise ValueError('The selected cover changed before it could be applied.')
        data = select_layout(data, layout, project_id=pid)
        data = stage_photo_cover(data, project_id=pid)
        data = approve_stage(data, 'cover')
        build_state(data)['awaiting_cover_choice'] = False
        build_state(data)['cover_choice_approved'] = True
        return data
    if title_id:
        # This is a title choice after Visuals, not a manuscript edit. The
        # normal early-title sync rebuilds descriptive slots and would lose
        # the already-verified picture paths and attribution.
        preserved = {k: copy.deepcopy(data[k]) for k in (
            'visual_plan', 'ebook_visual_manifest', 'ebook_visual_manifest_digest',
            'content', 'ebook') if k in data}
        data = approve_stage(data, 'title', choice_id=title_id)
        data.update(preserved)
        from services.ebook_project_workspace import sync_document_from_workspace
        data = sync_document_from_workspace(data, sync_manuscript=False)
        source = copy.deepcopy((data.get('cover_design') or {}).get('source') or {})
        if not source:
            raise ValueError('The cover photograph is missing. Resume this project to recover it.')
        data = _activate_source(data, source, project_id=pid)
    else:
        data = prepare(data, pid)
    variants = (data.get('cover_design') or {}).get('variants') or {}
    if not any((v.get('quality') or {}).get('pass') and v.get('digest') for v in variants.values()):
        raise ValueError('No readable cover passed the quality check.')
    set_stage_status(data['ebook_workspace'], 'cover', STATUS_AWAITING)
    state = build_state(data)
    state['awaiting_cover_choice'] = True
    state['customer_message'] = 'Choose your title and cover. Then the Factory will finish your PDF and ZIP.'
    state['_no_retry_message'] = True
    return data


def approve_visuals(data):
    """Try free replacements for refused photos, then require the real gate."""
    from services.ebook_visual_pipeline import replace_photo_aid, visual_review_payload, MATCH_PASS
    from services.ebook_design_workspace import approve_visuals_local
    for _ in range(3):
        review = visual_review_payload(data)
        if review.get('approvable'):
            break
        refused = [v for v in review.get('assets', []) if v.get('replace_enabled')
                   and (not v.get('has_file') or v.get('match_status') != MATCH_PASS)]
        if not refused:
            break
        for visual in refused:
            data = replace_photo_aid(data, str(visual['visual_id']), mode='')
    return approve_visuals_local(data)
