"""Saved manuscript controls use owned checkpoints and one explicit dispatch."""
from contextlib import closing
import json

import pytest

from services.ebook_v2.books import Conflict
from services.ebook_v2.hosted_resume import apply, queue
from services.ebook_v2.recovery_handoff import WorkerUnavailable
from services.ebook_v2.workflow_recovery import Dispatch, run_saved_book
from tests.test_ebook_v2_hosted_handoff import hosted


@pytest.fixture
def paused(hosted):
    app, client, books, artifacts, connect, snapshot, headers, settings = hosted
    dispatch = Dispatch(books, 'builder/recover_saved_ebook', lambda *a: 'initial-run')
    dispatch.initialize()
    app.extensions['ebook_v2_hosted']['dispatch'] = dispatch
    response = client.post('/api/ebook-recovery/projects/1/snapshots', json=settings, headers=headers)
    book = books.get('alice', response.json['book_id'])
    book = books.advance('alice', book['id'])  # enqueue chapters
    books.advance('alice', book['id'])  # first chapter completes
    retained = books.units.get('alice', book['units'][0])
    token = books.units.claim('alice', book['units'][1], 60)
    books.units.fail('alice', book['units'][1], token['token'], 'INJECTED_STOP')
    book = books.advance('alice', book['id'])
    assert book['state'] == 'NEEDS_ATTENTION'
    return hosted, dispatch, book, retained


def test_resume_retains_completed_chapter_and_delivers_actual_shared_files(paused):
    (app, client, books, artifacts, connect, _, _, _), dispatch, book, retained = paused
    with closing(connect()) as conn:
        original = tuple(conn.execute('SELECT * FROM projects WHERE id=1').fetchone())
    calls = []
    submit = lambda *a: calls.append(a) or 'resume-run'
    for _ in range(2):
        queue(dispatch, 'alice', book['id'], book['revision'], finished=lambda _: True, submit=submit)
    assert len(calls) == 1 and calls[0][-1] == book['revision']
    assert books.get('alice', book['id']) == book  # queued, not reset in the web request
    for _ in range(2):
        apply(books, 'alice', book['id'], book['revision'])
    resumed = books.get('alice', book['id'])
    assert resumed['revision'] == book['revision'] + 1
    assert resumed['units'][0] == book['units'][0]
    assert resumed['units'][1] != book['units'][1]
    assert run_saved_book(app.extensions['ebook_v2_hosted'], 'alice', book['id'])['state'] == 'REVIEW'
    assert books.units.get('alice', retained['id']) == retained
    url = '/api/ebook-recovery/books/' + book['id']
    pdf = client.get(url + '/files/ebook.pdf?preview=1')
    package = client.get(url + '/files/package.zip?preview=1')
    import io, zipfile
    assert pdf.status_code == package.status_code == 200
    with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
        assert archive.testzip() is None and archive.read('ebook.pdf') == pdf.data
    with closing(connect()) as conn:
        assert tuple(conn.execute('SELECT * FROM projects WHERE id=1').fetchone()) == original


@pytest.mark.parametrize('outcome', ['active', 'unavailable', 'ambiguous'])
def test_resume_never_retries_uncertain_or_active_run(paused, outcome):
    (_, _, books, *_), dispatch, book, _ = paused
    calls = []
    def finished(_):
        if outcome == 'unavailable':
            raise TimeoutError()
        return outcome != 'active'
    def submit(*args):
        calls.append(args)
        raise TimeoutError('Accepted remotely, response lost')
    for _ in range(2):
        with pytest.raises(WorkerUnavailable):
            queue(dispatch, 'alice', book['id'], book['revision'], finished=finished, submit=submit)
    assert len(calls) == (1 if outcome == 'ambiguous' else 0)
    assert books.get('alice', book['id']) == book


def test_resume_refuses_foreign_stale_topic_and_unrequested_worker_call(paused):
    (_, _, books, *_), dispatch, book, _ = paused
    from tests.test_ebook_v2_topics import topic_spec
    with pytest.raises(LookupError):
        queue(dispatch, 'bob', book['id'], book['revision'])
    with pytest.raises(Conflict):
        queue(dispatch, 'alice', book['id'], book['revision'] - 1)
    with pytest.raises(ValueError):
        apply(books, 'alice', book['id'], book['revision'])
    topic = books.create('alice', 'topic:controls-no-allowance', topic_spec())
    with pytest.raises(ValueError):
        queue(dispatch, 'alice', topic['id'], topic['revision'])


def test_http_resume_checks_csrf_exact_body_and_ownership_then_reports_pending(paused, monkeypatch):
    (app, client, books, _, _, _, headers, _), dispatch, book, _ = paused
    url = '/api/ebook-recovery/books/' + book['id']
    body = {'action': 'resume', 'revision': book['revision']}
    assert client.get(url).json['can_resume'] is True
    assert client.post(url, json=body).status_code == 403
    assert client.post(url, json={**body, 'owner': 'alice'}, headers=headers).status_code == 400
    assert client.post(url, json={**body, 'revision': True}, headers=headers).status_code == 400
    with client.session_transaction() as session:
        session['_user_id'] = 'bob'
    assert client.post(url, json=body, headers=headers).status_code == 404
    with client.session_transaction() as session:
        session['_user_id'] = 'alice'
    calls = []
    monkeypatch.setattr(dispatch, 'resume', lambda owner, key, rev: queue(dispatch, owner, key, rev,
        finished=lambda _: True, submit=lambda *a: calls.append(a) or 'resume-run'))
    for _ in range(2):
        assert client.post(url, json=body, headers=headers).status_code == 202
    assert len(calls) == 1
    status = client.get(url).json
    assert status['resume_pending'] is True and status['can_resume'] is False
    assert books.get('alice', book['id']) == book


def test_source_choices_do_not_expose_foreign_books_or_start_processing(hosted, monkeypatch):
    app, client, books, _, connect, _, _, _ = hosted
    with closing(connect()) as conn:
        conn.execute('INSERT INTO projects VALUES (2,?,?,?,?,?)',
                     ('bob', 'ebook', 'Private foreign manuscript', 1, '{}'))
        conn.commit()
    monkeypatch.setattr(books, 'create', lambda *a, **k: pytest.fail('Opening must never queue'))
    page = client.get('/api/ebook-recovery/workspace')
    assert page.status_code == 200 and b'Create a review copy' in page.data
    assert b'Private foreign manuscript' not in page.data
    assert b'value="1"' in page.data
    assert books.listing('alice') == []


@pytest.mark.parametrize('width,height', [(1280, 900), (390, 844)])
def test_browser_creates_one_saved_review_copy_then_resumes_once(hosted, width, height, tmp_path, monkeypatch):
    from threading import Thread
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    app, client, books, _, connect, _, _, settings = hosted
    books.record_worker('controls-fixture')
    with closing(connect()) as conn:
        original = tuple(conn.execute('SELECT * FROM projects WHERE id=1').fetchone())
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': width, 'height': height})
            context.add_cookies([{'name': 'session', 'value': client.get_cookie('session').value, 'url': base}])
            page = context.new_page(); errors = []; posts = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda r: posts.append(r.url) if r.method == 'POST' else None)
            page.goto(base + '/api/ebook-recovery/workspace')
            assert posts == [] and page.locator('#create').is_disabled()
            page.locator('#source').select_option('1')
            page.wait_for_function("!document.getElementById('create').disabled")
            page.locator('#copy-title').fill(settings['recovery']['title'])
            page.locator('#copy-author').fill(settings['recovery']['author'])
            page.screenshot(path=f'/tmp/factory-controls-create-{width}.png', full_page=True)
            page.locator('#create').click()
            page.wait_for_url('**/workspace?book=*')
            assert len(posts) == 1 and len(books.listing('alice')) == 1
            book = books.get('alice', books.listing('alice')[0]['id'])
            book = books.advance('alice', book['id'])
            books.advance('alice', book['id'])
            retained = books.units.get('alice', book['units'][0])
            token = books.units.claim('alice', book['units'][1], 60)
            books.units.fail('alice', book['units'][1], token['token'], 'INJECTED_STOP')
            book = books.advance('alice', book['id'])
            page.locator('#refresh').click()
            page.locator('#resume').wait_for(state='visible')
            page.locator('#resume').click()
            page.locator('#resume').wait_for(state='hidden')
            assert books.get('alice', book['id'])['state'] == 'RUNNING'
            assert books.units.get('alice', retained['id']) == retained
            assert len(posts) == 2 and not errors
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=f'/tmp/factory-controls-resumed-{width}.png', full_page=True)
            browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(3)
    with closing(connect()) as conn:
        assert tuple(conn.execute('SELECT * FROM projects WHERE id=1').fetchone()) == original
