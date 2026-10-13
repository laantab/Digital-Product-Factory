"""Preserve exact customer previews while bounding database save payloads."""
import json

import pytest

import database


def test_large_workspace_preview_roundtrip_persists_one_copy_and_keeps_stale_guard():
    database.init_db()
    html = '<html><body>' + 'Clear text and full-resolution pixels. ' * 40000 + '</body></html>'
    source = {'ebook_workspace': {}, 'preview_html': html, 'ebook_preview_html': html,
              'content': 'Approved manuscript', 'pdf_bytes': 'legacy PDF backup'}
    project = database.create_project('Large preview preservation', 'ebook', source)
    pid = project['id']
    with database.get_conn() as connection:
        row = connection.execute('SELECT data FROM projects WHERE id=?', (pid,)).fetchone()
    stored = json.loads(row['data'])
    assert stored['preview_html'] == html
    assert 'ebook_preview_html' not in stored
    assert len(row['data']) < len(html) + 1000
    assert source['ebook_preview_html'] == html
    first = database.get_project(pid)['data']
    stale = database.get_project(pid)['data']
    assert first['ebook_preview_html'] == first['preview_html'] == html
    assert first['pdf_bytes'] == source['pdf_bytes']
    assert '_factory_ebook_preview_alias' not in first
    first['review_note'] = 'Ready'
    updated = database.update_project(pid, None, first)
    assert updated['data']['ebook_preview_html'] == html
    with pytest.raises(database.StaleProjectWrite):
        database.update_project(pid, None, stale)


def test_different_previews_are_preserved_separately():
    data = {'ebook_workspace': {}, 'preview_html': 'a' * 1100000,
            'ebook_preview_html': 'b' * 1100000}
    assert database._decode_project_data(database._encode_project_data(data)) == data
    assert '_factory_ebook_preview_alias' not in json.loads(database._encode_project_data(data))


def test_legacy_records_keep_both_previews_unchanged():
    data = {'ebook_workspace': {}, 'preview_html': '<html>Legacy</html>',
            'ebook_preview_html': '<html>Legacy</html>', 'pdf_bytes': 'saved PDF'}
    assert database._decode_project_data(json.dumps(data)) == data


def test_other_products_are_not_compacted():
    data = {'preview_html': 'x' * 1100000, 'ebook_preview_html': 'x' * 1100000}
    assert json.loads(database._encode_project_data(data)) == data
