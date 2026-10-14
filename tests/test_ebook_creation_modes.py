"""Owner-approved automatic recommendations and custom template choices.

Provider fixtures only: no real research, paid generation or customer book.
"""
import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import database
from services import ebook_build_orchestrator as orch


def test_legacy_build_keys_are_preserved_and_new_paths_do_not_collide():
    fields = {'topic': 'Wellness', 'ebook_title': 'My Book', 'author_brand': 'Author'}
    original = {'customer': 'local', 'title': 'my book', 'topic': 'wellness', 'author': 'author'}
    expected = hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()[:32]
    assert orch.idempotency_key_for(fields) == expected
    auto = {**fields, 'ebook_creation_mode': 'ai_recommended'}
    custom = {**fields, 'ebook_creation_mode': 'custom', 'theme_id': 'bold_creator'}
    assert len({expected, orch.idempotency_key_for(auto), orch.idempotency_key_for(custom)}) == 3
    assert orch.idempotency_key_for(custom) != orch.idempotency_key_for({**custom, 'theme_id': 'warm_wellness'})
    assert orch.idempotency_key_for(auto) == orch.idempotency_key_for({**auto, 'theme_id': 'bold_creator'})


@pytest.mark.parametrize('mode,expected', [('ai_recommended', 'warm_wellness'), ('custom', 'bold_creator'), ('', 'bold_creator')])
def test_design_uses_factory_matching_only_for_the_automatic_path(mode, expected):
    data = {'title': 'Mindfulness for Beginners', 'content': 'Preserved manuscript',
            'fields': {'topic': 'mindfulness', 'theme_id': 'bold_creator', 'ebook_creation_mode': mode}}
    before = copy.deepcopy(data)
    with patch('services.ebook_design_workspace.select_and_stage_theme', side_effect=lambda d, t: d) as select, \
         patch('services.ebook_project_workspace.approve_stage', side_effect=lambda d, s: d):
        assert orch._run_design(data, 99) == before
    assert select.call_args.args[1] == expected
    assert data == before


def test_automatic_visuals_still_refuse_a_failed_quality_gate():
    data = {'fields': {'ebook_creation_mode': 'ai_recommended'}}
    with patch('services.ebook_design_workspace.prepare_visuals_local', return_value=data), \
         patch('database.update_project'), \
         patch('services.ebook_guided_build.approve_visuals', side_effect=ValueError('visual quality failed')):
        with pytest.raises(ValueError, match='visual quality failed'):
            orch._run_visuals(data, 99)
    assert not data.get('export_ready')


@pytest.mark.parametrize('mode,theme', [('ai_recommended', 'warm_wellness'), ('custom', 'bold_creator')])
def test_automatic_build_reaches_real_pdf_and_zip_without_choice_pauses(monkeypatch, mode, theme):
    monkeypatch.setenv('EBOOK_CUSTOMER_PATH_FIXTURE', '1')
    from app import app
    client = app.test_client()
    fields = {'topic': 'mindfulness for beginners', 'ebook_title': 'Mindfulness for Beginners',
              'author_brand': 'Fixture Author', 'include_images': 'Yes',
              'ebook_creation_mode': mode, 'theme_id': 'bold_creator'}
    with patch('services.jobs.dispatch.hand_off'):
        started = client.post('/ebook/build', json={'fields': fields})
        again = client.post('/ebook/build', json={'fields': fields})
    assert started.status_code == 200, started.json
    pid = started.json['project_id']
    assert again.json['project_id'] == pid
    try:
        for _ in range(100):
            status = orch.advance_build(pid)
            assert not status.get('failed'), status
            assert not status.get('awaiting_picture_approval'), status
            assert not status.get('awaiting_cover_choice'), status
            if status.get('finished'):
                break
        assert status['finished'], status
        data = database.get_project(pid)['data']
        assert data['ebook_design']['theme_id'] == theme
        pdf = client.get(status['downloads']['pdf'])
        archive = client.get(status['downloads']['zip'])
        assert pdf.status_code == 200 and pdf.data.startswith(b'%PDF')
        assert archive.status_code == 200 and archive.data.startswith(b'PK')
        with patch.dict(orch.STAGE_RUNNERS, {s: lambda *_: pytest.fail('completed book rebuilt') for s in orch.STAGES}):
            assert orch.advance_build(pid)['finished']
    finally:
        database.delete_project(pid)


def test_recommendation_button_starts_the_complete_build_and_custom_form_offers_six_styles():
    source = (Path(__file__).resolve().parents[1] / 'static/js/app.js').read_text()
    body = source.split('async function buildThisProduct()', 1)[1].split('async function runFactoryMarketAdvantage()', 1)[0]
    branch = body.split('if (factoryId === "ebook")', 1)[1].split('go("factory")', 1)[0]
    assert 'await startEbookBuild({' in branch
    assert 'ebook_creation_mode: "ai_recommended"' in branch
    assert 'openEbookWorkspace(' not in branch
    assert 'api("/ebook-workspace"' not in branch
    fields = source.split('id: "ebook"', 1)[1].split('id: "coloring_book"', 1)[0]
    for name in ('Warm Wellness', 'Modern Business', 'Bold Creator', 'Elegant Editorial', 'Bright Workbook', 'Minimal Professional'):
        assert name in fields


@pytest.fixture(scope='module')
def browser_factory():
    from tests.test_ebook_real_browser_customer_path import EbookRealBrowserCustomerPathTests as server
    server.setUpClass()
    try:
        yield server
    finally:
        server.tearDownClass()


@pytest.mark.parametrize('mode', ['custom', 'ai_recommended'])
def test_browser_one_build_click_enters_finished_product_with_the_right_mode(browser_factory, mode):
    server = browser_factory
    page = server.browser.new_page()
    sent = []
    def start(route):
        sent.append(route.request.post_data_json['fields'])
        route.fulfill(json={'ok': True, 'project_id': 900, 'finished': True, 'failed': False,
                            'percent': 100, 'title': 'Mindfulness for Beginners',
                            'downloads': {'pdf': '/download/fixture/ebook.pdf', 'zip': '/download/fixture/package.zip'}})
    page.route('**/ebook/build', start)
    try:
        page.goto(server.base)
        if mode == 'custom':
            page.locator('#nav [data-go="ebook"]').click()
            page.locator('#ebookInput').fill('mindfulness for beginners')
            page.locator('#ebookAuthor').fill('Fixture Author')
            page.get_by_label('Choose your ebook template', exact=True).select_option('bold_creator')
            page.locator('#ebookWorkspaceStartBtn').click()
        else:
            page.route('**/research-to-builder', lambda route: route.fulfill(json={
                'id': 800, 'factory_id': 'ebook', 'generated': False,
                'data': {'plan': {'product_title': 'Mindfulness for Beginners'}}}))
            fixture = {'product_type': 'Ebook', 'inputs': {'product_type': 'Ebook', 'topic': 'mindfulness', 'audience': 'beginners'},
                       'opportunities': [{'product_type': 'Ebook', 'product_idea': 'Mindfulness for Beginners', 'target_audience': 'beginners'}],
                       'recommendation': {'best_product': 'Mindfulness for Beginners', 'best_product_type': 'Ebook'}}
            page.evaluate('(d) => { go("market"); lastDiscovery = d; renderDiscovery(d); }', fixture)
            page.locator('#fmaEbookAuthor').fill('Fixture Author')
            assert page.locator('#marketOutput select').count() == 0, 'automatic path must not ask for a template'
            page.locator('#buildThisProductBtn').click()
        page.get_by_role('button', name='Download PDF', exact=True).wait_for()
        assert len(sent) == 1, sent
        assert sent[0]['ebook_creation_mode'] == mode
        if mode == 'custom':
            assert sent[0]['theme_id'] == 'bold_creator'
        else:
            assert 'theme_id' not in sent[0]
        assert page.get_by_role('button', name='Download ZIP', exact=True).is_visible()
    finally:
        page.close()
