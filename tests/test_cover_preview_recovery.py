"""Cover choices remain viewable when the website has a different exports root."""
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess

import pytest
from PIL import Image
from services import ebook_photo_cover as pc
from services import ebook_guided_build as guided


def test_preview_recovers_registered_files_under_the_websites_exports_root(tmp_path, monkeypatch):
    buf = io.BytesIO()
    Image.new('RGB', (900, 1200), (34, 90, 40)).save(buf, format='PNG')
    photo = buf.getvalue()
    sha = hashlib.sha256(photo).hexdigest()
    layout = pc.LAYOUT_IDS[0]
    source_path = f'/builder/exports/pkg/cover_photo/sources/{sha}.png'
    thumb_path = f'/builder/exports/pkg/cover_photo/variants/cache/{layout}/thumb.png'
    source = {'path': source_path, 'sha256': sha, 'project_id': 20,
              'source_type': 'upload', 'license_note': 'Owner photograph', 'package_id': 'pkg'}
    data = {'package_id': 'pkg', 'cover_design': {
        'workflow': 'photo_backed', 'package_id': 'pkg', 'source': source,
        'variants': {layout: {'digest': 'cover-digest', 'source_sha256': sha,
                            'thumb_path': thumb_path}}}}
    monkeypatch.setattr(pc, 'EXPORTS_DIR', str(tmp_path / 'website-exports'))
    reads = []
    def read(pid, rel):
        reads.append((pid, rel))
        return photo if rel in (f'pkg/cover_photo/sources/{sha}.png',
                                f'pkg/cover_photo/variants/cache/{layout}/thumb.png') else None
    monkeypatch.setattr('services.storage.compat.read_export_or_legacy', read)
    result = pc.verified_variant_asset(data, project_id=20, layout=layout,
                                      digest='cover-digest', size='thumb', source_sha=sha)
    assert result['bytes'] == photo
    assert reads == [(20, f'pkg/cover_photo/sources/{sha}.png'),
                     (20, f'pkg/cover_photo/variants/cache/{layout}/thumb.png')]
    assert source['path'].startswith(str(tmp_path / 'website-exports'))


def test_refresh_queues_only_the_existing_cover_and_preserves_the_book():
    original = {'fields': {'guided_cover_choice': True},
                'ebook_build': {'awaiting_cover_choice': True},
                'ebook_workspace': {'approved_title_id': 'title-1'},
                'content': 'Accepted manuscript', 'visual_plan': {'accepted': True},
                'cover_design': {'source': {'sha256': 'existing-photo'}}}
    before = copy.deepcopy(original)
    result = guided.record_choice(original, {'action': 'refresh', 'title_id': 'title-1'})
    assert result['ebook_build']['pending_cover_refresh'] is True
    assert result['ebook_build']['awaiting_cover_choice'] is False
    assert result['content'] == original['content']
    assert result['visual_plan'] == original['visual_plan']
    assert result['cover_design'] == original['cover_design']
    assert original == before


def test_refresh_rejects_a_different_title():
    with pytest.raises(ValueError, match='title'):
        guided.record_choice({'fields': {'guided_cover_choice': True},
                              'ebook_build': {'awaiting_cover_choice': True},
                              'ebook_workspace': {'approved_title_id': 'current'}},
                             {'action': 'refresh', 'title_id': 'different'})


@pytest.mark.parametrize('path', ['/builder/exports/other/cover_photo/sources/a.png',
                                  '/builder/exports/pkg/cover_photo/../../other/a.png'])
def test_rebasing_never_adopts_a_different_package_or_traversal(path, tmp_path, monkeypatch):
    monkeypatch.setattr(pc, 'EXPORTS_DIR', str(tmp_path))
    assert pc._cover_path_on_this_machine(path, 'pkg') == path


def test_refresh_renders_the_registered_photo_without_calling_preparation(monkeypatch):
    source = {'path': '/registered/photo.png', 'sha256': 'same-photo'}
    data = {'fields': {'guided_cover_choice': True},
            'ebook_build': {'pending_cover_refresh': True}, 'ebook_workspace': {},
            'content': 'Accepted manuscript', 'visual_plan': {'accepted': True},
            'cover_design': {'source': source, 'editor': {'zoom': 1.2}}}
    seen = []
    monkeypatch.setattr(pc, 'verify_source', lambda *args, **kw: {})
    monkeypatch.setattr(pc, '_publish_cover_files', lambda *args, **kw: None)
    def render(value, *, project_id):
        seen.append((copy.deepcopy(value['cover_design']), project_id))
        value['cover_design']['variants'] = {'layout': {'quality': {'pass': True}, 'digest': 'new-render'}}
        return value
    monkeypatch.setattr(pc, 'render_photo_variants', render)
    monkeypatch.setattr('services.ebook_project_workspace.set_stage_status', lambda *a, **kw: None)
    def forbidden(*args):
        raise AssertionError('Refresh must not research or prepare another photograph')
    result = guided.run_cover(data, 20, forbidden)
    assert seen == [({'source': source, 'editor': {'zoom': 1.2}}, 20)]
    assert result['ebook_build']['awaiting_cover_choice'] is True
    assert result['content'] == data['content']
    assert result['visual_plan'] == data['visual_plan']


def test_cover_choice_controls_refresh_same_title_and_refuse_an_unloaded_image():
    text = (Path(__file__).resolve().parents[1] / 'static/js/app.js').read_text()
    function = text.split('function _renderEbookCoverChoice(', 1)[1].split('\nasync function startEbookWorkspaceFromBuilder', 1)[0]
    script = '''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const image = {complete: true, naturalWidth: 0};
const input = {value: 'layout', dataset: {digest: 'digest'}, closest: () => ({querySelector: () => image})};
const title = {value: 'current'};
const finish = {disabled: true};
const refresh = {};
const error = {classList: {remove() {}}, textContent: ''};
const root = {
 querySelector(selector) {return ({'[data-cover-title]': title, '[data-cover-error]': error,
  '[data-cover-finish]': finish, '[data-cover-update-title]': refresh,
  '[data-cover-layout]:checked': input})[selector];},
 querySelectorAll(selector) {return selector === '[data-cover-layout]' ? [input] : [title, finish, refresh, input];}
};
let submitted = [];
const context = {card: x=>x, escapeHtml: x=>x, api: async (url, request) => {
 submitted.push(JSON.parse(request.body)); return {};}, renderEbookBuild() {},
 _ebookBuildRun: 0, _ebookBuildLoop: async ()=>{}};
vm.createContext(context);
vm.runInContext(FUNCTION, context);
context._renderEbookCoverChoice(root, {cover_choice: {selected_title_id: 'current', variants: []}}, 20, 'Book');
input.onchange();
assert.equal(finish.disabled, true);
finish.onclick();
assert.equal(submitted.length, 0);
image.naturalWidth = 400;
image.onload();
assert.equal(finish.disabled, false);
image.naturalWidth = 0;
image.onerror();
assert.equal(finish.disabled, true);
(async () => {await refresh.onclick(); assert.equal(submitted[0].action, 'refresh');
 assert.equal(submitted[0].title_id, 'current');})().catch(e=>{console.error(e);process.exitCode=1;});
'''.replace('FUNCTION', json.dumps('function _renderEbookCoverChoice(' + function))
    subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)
