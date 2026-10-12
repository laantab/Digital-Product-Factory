"""Recover the book's photo minimum without discarding useful graphics."""
import copy
from unittest.mock import patch

from services import ebook_factory_pipeline as pipeline
from services.ebook_visual_editorial import review_visual_set


def plan():
    chapters = []
    for index, kind in enumerate(['photo', 'timeline', 'diagram', 'comparison', 'checklist', 'workflow'], 1):
        aid = {'type': kind, 'visual_id': f'v_ch{index}', 'chapter_index': index,
               'caption': f'Kitchen {index} inspection steps',
               'width': 1600, 'height': 900, 'source': 'local_render',
               'items': [f'Step {n} for room {index}' for n in range(3)],
               'required': True}
        if kind == 'comparison':
            aid['table'] = {'headers': ['Option', 'Benefit'],
                            'rows': [['Seal gaps', 'Reduce drafts'], ['Insulate', 'Retain warmth']]}
        if kind == 'photo':
            aid.update(source='pexels', match_status='pass', photo_id='original',
                       sha256='original-hash', attribution='Original photographer')
        chapters.append({'chapter': f'Kitchen {index}', 'chapter_index': index,
                         'chapter_body': f'Inspect the kitchen window in room {index}.', 'aids': [aid]})
    return {'chapters': chapters}


def photo(aid, **kwargs):
    return {**aid, 'match_status': 'pass', 'photo_id': aid['visual_id'],
            'sha256': 'hash-' + aid['visual_id'], 'width': 1600, 'height': 900,
            'attribution': 'A free stock photographer', 'status': 'resolved'}


def run(value, fill=photo):
    with patch('services.image_sources.configured_providers', return_value=('unsplash',)), \
         patch.object(pipeline, '_photo_already_stored', return_value=True), \
         patch.object(pipeline, 'fill_photo_aid_from_pexels', side_effect=fill) as stock, \
         patch.object(pipeline, 'fill_photo_aid_with_ai', side_effect=AssertionError('paid call')):
        result = pipeline.fill_missing_photograph_quota(
            value, package_id='quota-test', title='Home Makeover', topic='home improvement')
    return result, stock


def test_one_photo_and_useful_graphics_receive_two_additional_real_photos():
    value = plan()
    originals = copy.deepcopy([c['aids'][0] for c in value['chapters']])
    assert not review_visual_set(value, chapter_count=6, photography_supported=True).ok
    result, stock = run(value)
    assert stock.call_count == 2
    assert [c['aids'][0] for c in result['chapters']] == originals
    assert review_visual_set(result, chapter_count=6, photography_supported=True).ok
    for call in stock.call_args_list:
        assert 'original' in call.args[0]['rejected_photo_ids']
        assert call.args[0]['chapter_body']


def test_resume_keeps_successful_photos_and_does_not_acquire_again():
    result, _ = run(plan())
    before = copy.deepcopy(result)
    result, stock = run(result)
    assert result == before
    stock.assert_not_called()


def test_uncertain_or_duplicate_photos_cannot_satisfy_the_minimum():
    def refused(aid, **kwargs):
        return {**photo(aid), 'photo_id': 'original', 'sha256': 'original-hash'}
    value = plan()
    result, stock = run(value, refused)
    assert stock.call_count == 4
    assert sum(len(c['aids']) for c in result['chapters']) == 6
    assert not review_visual_set(result, chapter_count=6, photography_supported=True).ok
    result, _ = run(plan(), lambda a, **k: {**photo(a), 'match_status': 'needs_review'})
    assert sum(len(c['aids']) for c in result['chapters']) == 6


def test_failed_searches_rotate_chapters_on_the_next_bounded_attempt():
    value, first = run(plan(), lambda a, **k: {**a, 'match_status': 'missing'})
    _, second = run(value, lambda a, **k: {**a, 'match_status': 'missing'})
    first_ids = {c.args[0]['visual_id'] for c in first.call_args_list}
    assert second.call_args_list[0].args[0]['visual_id'] not in first_ids


def test_no_configured_source_does_not_commission_missing_slots():
    value = plan()
    before = copy.deepcopy(value)
    with patch('services.image_sources.configured_providers', return_value=()), \
         patch.object(pipeline, 'fill_photo_aid_from_pexels') as stock:
        pipeline.fill_missing_photograph_quota(value, package_id='offline')
    assert value == before
    stock.assert_not_called()
