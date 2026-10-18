"""Saved list summaries carry controls and links, never nested book payloads."""
import copy
import json
import pytest
from services.saved_project_listing import compact_list_item


@pytest.mark.parametrize('kind', ['ebook', 'coloring_book', 'crossword'])
def test_nested_book_data_does_not_travel_in_list_summaries(kind):
    large = 'x' * 2_000_000
    original = {
        'id': 4249, 'name': 'Customer Book', 'type': 'ebook' if kind == 'ebook' else 'product',
        'user_saved': True, 'artifact_state': 'APPROVED', 'artifact_revision': 3,
        'data': {
            'title': 'Customer Book', 'product_type': kind, 'product_label': kind,
            'customer_keep': True, 'user_confirmed_save': True, 'stage': 'export_ready',
            'ebook_ready': True, 'export_ready': True, 'pdf_available': True,
            'release_status': 'PASS', 'package_id': 'original',
            'export_package_id': 'current', 'pdf_bytes': large, 'preview_html': large,
            'fields': {'author_brand': 'Lonnie Brown', 'research_notes': large},
            'ebook_document': {'manuscript': large},
            'ebook_workspace': {'next_action': 'approve_manuscript', 'history': [large]},
            'cover_design': {'author': 'Lonnie Brown', 'variants': [{'base64': large}]},
            'exports': {'files': {'pdf': {'name': 'ebook.pdf', 'url': '/download/current/ebook.pdf', 'bytes': large},
                                  'zip': {'name': 'package.zip', 'url': '/download/current/package.zip'}},
                        'preview_html': large},
        },
    }
    before = copy.deepcopy(original)
    summary = compact_list_item(original)
    assert len(json.dumps(summary)) < 16000
    assert summary['_list_summary'] is True
    assert summary['data']['pdf_bytes'] == summary['data']['preview_html'] == ''
    assert summary['data']['exports']['files']['pdf']['url'] == '/download/current/ebook.pdf'
    assert summary['data']['exports']['files']['zip']['url'] == '/download/current/package.zip'
    assert summary['data']['fields']['author_brand'] == 'Lonnie Brown'
    assert summary['data']['customer_keep'] is True
    assert summary['artifact_state'] == 'APPROVED' and summary['artifact_revision'] == 3
    assert summary['data']['ebook_workspace']['next_action'] == 'approve_manuscript'
    assert original == before


def test_non_product_record_is_unchanged():
    source = {'id': 1, 'type': 'research', 'data': {'report': 'existing research'}}
    assert compact_list_item(source) is source
