"""A completed, reviewed workspace follows its chosen plan, never inferred replacements."""
import copy
import hashlib

import pytest

from services.ebook_factory_pipeline import ebook_project_readiness
from services.ebook_project_workspace import new_workspace, set_stage_status, STATUS_APPROVED
from services.ebook_visual_pipeline import VisualValidation


@pytest.fixture
def reviewed_book(tmp_path, monkeypatch):
    pdf, bundle = tmp_path / 'ebook.pdf', tmp_path / 'package.zip'
    pdf.write_bytes(b'%PDF-1.4 reviewed book')
    bundle.write_bytes(b'PK\x03\x04 reviewed package')
    ws = new_workspace(topic='Home repair')
    for stage in ('visuals', 'cover', 'design', 'preview', 'preflight'):
        set_stage_status(ws, stage, STATUS_APPROVED)
    data = {
        'product_type': 'ebook', 'ebook_project_workspace': True,
        'title': 'A Home Repair Checklist', 'fields': {'topic': 'Home repair'},
        'content': ('Compare upgrade costs before choosing the next improvement. ' * 80),
        'ebook_document': {'chapters': [{'chapter_id': 'ch1'}]},
        'ebook_workspace': ws, 'release_status': 'PASS',
        'ebook_design_preflight': {'status': 'PASS'},
        'pdf_path': str(pdf), 'export_files': {'ebook.pdf': str(pdf), 'package.zip': str(bundle)},
        'cover_design': {'workflow': 'photo_backed', 'selected_layout': 'clean', 'source': {'sha256': 'registered'}},
        'visual_plan': {'chapters': [{'chapter': 'Choosing Upgrades', 'aids': [
            {'type': 'action step box', 'items': ['Compare costs', 'Choose the priority'], 'title': 'Priorities'}]}]},
        'release_review': {'status': 'Ready for approval', 'counts': {},
                           'pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
                           'zip_sha256': hashlib.sha256(bundle.read_bytes()).hexdigest()},
    }
    monkeypatch.setattr('services.ebook_visual_pipeline.validate_visual_readiness',
                        lambda *a, **k: VisualValidation(True, required_count=1, resolved_count=1))
    return data


def test_reviewed_workspace_keeps_its_approved_chart_plan(reviewed_book):
    result = ebook_project_readiness(reviewed_book)
    assert result['ebook_ready'], result['completion_blockers']
    requirement = result['chapter_visual_requirements'][0]
    assert requirement['requirement_kind'] == 'approved_workspace_plan'
    assert requirement['allowed_categories'] == ['checklist']


@pytest.mark.parametrize('change', ['pdf', 'zip', 'review', 'hard', 'visuals', 'preflight', 'legacy'])
def test_unverified_or_legacy_books_keep_inferred_requirements(reviewed_book, change):
    data = copy.deepcopy(reviewed_book)
    if change in {'pdf', 'zip'}:
        data['release_review'][change + '_sha256'] = 'stale'
    elif change == 'review':
        data['release_review']['status'] = 'Needs human review'
    elif change == 'hard':
        data['release_review']['counts']['hard'] = 1
    elif change == 'visuals':
        data['ebook_workspace']['rail']['visuals']['status'] = 'not_started'
    elif change == 'preflight':
        data['ebook_design_preflight']['status'] = 'NEEDS_CORRECTION'
    else:
        data['ebook_project_workspace'] = False
    result = ebook_project_readiness(data)
    assert not result['ebook_ready']
    assert result['chapter_visual_requirements'][0]['requirement_kind'] == 'demonstration'


def test_review_does_not_excuse_a_changed_or_missing_asset(reviewed_book, monkeypatch):
    monkeypatch.setattr('services.ebook_visual_pipeline.validate_visual_readiness',
                        lambda *a, **k: VisualValidation(False, ['Original image hash changed.']))
    result = ebook_project_readiness(reviewed_book)
    assert not result['ebook_ready']
    assert 'Original image hash changed.' in result['completion_blockers']
