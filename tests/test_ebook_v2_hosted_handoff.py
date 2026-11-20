"""Signed requests queue saved text and retrieve verified shared artifacts."""
import json
import shutil
import sqlite3
from contextlib import closing

import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin

from services.ebook_v2.books import Books
from services.ebook_v2.hosted_recovery import blueprint
from services.ebook_v2.shared_artifacts import SharedArtifacts
from services.storage.local import LocalFilesystemDriver
from tests.ebook_v2_fixture import spec
from tests.test_ebook_v2_topics import provider


@pytest.fixture
def hosted(tmp_path):
    path = tmp_path / 'source.db'
    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    manuscript = spec()
    source = {'ebook_workspace': {'chapter_pipeline': {'assembled_complete': True},
              'accepted_chapters': [dict(order=i, title=c['title'], body=c['text'])
                                    for i, c in enumerate(manuscript['chapters'], 1)]}}
    with closing(connect()) as conn:
        conn.execute('CREATE TABLE projects (id INTEGER PRIMARY KEY, user_id TEXT, type TEXT, name TEXT, version INTEGER, data TEXT)')
        conn.execute('INSERT INTO projects VALUES (1,?,?,?,?,?)', ('alice','ebook','Saved',1,json.dumps(source)))
        conn.commit()
    books = Books(tmp_path/'studio.db', tmp_path/'worker'); books.initialize()
    artifacts = SharedArtifacts(books, LocalFilesystemDriver(tmp_path/'shared')); artifacts.initialize()
    app = Flask(__name__); app.secret_key = 'isolated-fixture'
    login = LoginManager(app)
    @login.user_loader
    def user(identity):
        result = UserMixin(); result.id = identity; return result
    app.extensions['ebook_v2_hosted'] = {'books': books, 'artifacts': artifacts}
    app.register_blueprint(blueprint(connect))
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = 'alice'; session['_fresh'] = True
    info = client.get('/api/ebook-recovery/projects/1').json
    headers = {'X-CSRF-Token': info['csrf_token']}
    snapshot = client.post('/api/ebook-recovery/projects/1/snapshots', json={'source_version':1}, headers=headers).json['snapshot_id']
    settings = {key:manuscript[key] for key in ('title','author','theme')}
    settings['require_photos'] = False
    return app, client, books, artifacts, connect, snapshot, headers, {'source_version':1, 'recovery':settings}


def test_signed_recovery_reaches_download_without_worker_local_files(hosted):
    app, client, books, artifacts, connect, snapshot, headers, settings = hosted
    books.record_worker('test-worker')
    path = '/api/ebook-recovery/projects/1/snapshots'
    response = client.post(path, json=settings, headers=headers)
    assert response.status_code == 202, response.json
    book_id = response.json['book_id']
    assert response.json['generation_started'] is False
    assert client.post(path,json=settings,headers=headers).json['book_id'] == book_id
    assert client.get('/api/ebook-recovery/books/'+book_id).json['files'] == []
    for _ in range(20):
        book = books.advance('alice', book_id)
        if book['state'] == 'REVIEW': break
    assert book['state'] == 'REVIEW'
    artifacts.publish('alice', book_id)
    url = '/api/ebook-recovery/books/'+book_id+'/files/ebook.pdf'
    assert client.get(url).status_code == 400
    preview = client.get(url+'?preview=1')
    assert preview.status_code == 200
    books.approve('alice',book_id,book['revision'])
    shutil.rmtree(books.root)
    downloaded = client.get(url)
    assert downloaded.status_code == 200
    assert downloaded.data == preview.data
    assert downloaded.headers['Cache-Control'] == 'no-store'
    assert client.get('/api/ebook-recovery/books/'+book_id+'/files/package.zip').status_code == 200
    with closing(connect()) as conn:
        conn.execute("UPDATE projects SET user_id='bob' WHERE id=1"); conn.commit()
    assert client.get(url).status_code == 404


def test_recovery_without_worker_or_csrf_does_not_queue(hosted):
    app, client, books, artifacts, connect, snapshot, headers, settings = hosted
    path = '/api/ebook-recovery/projects/1/snapshots'
    assert client.post(path,json=settings).status_code == 403
    assert client.post(path,json=settings,headers=headers).status_code == 503
    assert books.listing('alice') == []
    assert app.test_client().post(path,json=settings,headers=headers).status_code == 401
    app.extensions.pop('ebook_v2_hosted')
    assert client.post(path,json=settings,headers=headers).status_code == 503


def test_foreign_account_and_client_manuscript_cannot_be_imported(hosted):
    app, client, books, artifacts, connect, snapshot, headers, settings = hosted
    books.record_worker('test-worker')
    path = '/api/ebook-recovery/projects/1/snapshots'
    assert client.post(path,json={**settings,'chapters':[]},headers=headers).status_code == 400
    with client.session_transaction() as session:
        session['_user_id'] = 'bob'
    assert client.post(path,json=settings,headers=headers).status_code == 404
    assert books.listing('alice') == []


def test_retry_after_preservation_before_queue_reuses_one_snapshot_and_book(hosted, monkeypatch):
    app, client, books, artifacts, connect, snapshot, headers, settings = hosted
    books.record_worker('test-worker')
    path = '/api/ebook-recovery/projects/1/snapshots'
    with closing(connect()) as conn:
        original = tuple(conn.execute('SELECT * FROM projects WHERE id=1').fetchone())
    create = books.create
    def interrupted(*args, **kwargs):
        raise RuntimeError('Simulated interruption between preservation and queue')
    monkeypatch.setattr(books, 'create', interrupted)
    assert client.post(path, json=settings, headers=headers).status_code == 503
    assert books.listing('alice') == []
    monkeypatch.setattr(books, 'create', create)
    recovered = client.post(path, json=settings, headers=headers)
    repeated = client.post(path, json=settings, headers=headers)
    assert recovered.status_code == repeated.status_code == 202
    assert recovered.json['snapshot_id'] == snapshot
    assert repeated.json['book_id'] == recovered.json['book_id']
    assert len(books.listing('alice')) == 1
    with closing(connect()) as conn:
        assert conn.execute('SELECT count(*) FROM ebook_v2_legacy_snapshots').fetchone()[0] == 1
        assert tuple(conn.execute('SELECT * FROM projects WHERE id=1').fetchone()) == original


def test_stale_or_incomplete_source_does_not_queue(hosted):
    app, client, books, artifacts, connect, snapshot, headers, settings = hosted
    books.record_worker('test-worker')
    path = '/api/ebook-recovery/projects/1/snapshots'
    with closing(connect()) as conn:
        data = json.loads(conn.execute('SELECT data FROM projects WHERE id=1').fetchone()[0])
        data['ebook_workspace']['chapter_pipeline']['assembled_complete'] = False
        conn.execute('UPDATE projects SET data=?, version=2 WHERE id=1', (json.dumps(data),))
        conn.commit()
    assert client.post(path, json=settings, headers=headers).status_code == 409
    assert client.post(path, json={**settings,'source_version':2}, headers=headers).status_code == 400
    assert books.listing('alice') == []
    with closing(connect()) as conn:
        assert conn.execute('SELECT count(*) FROM ebook_v2_legacy_snapshots').fetchone()[0] == 1


def test_private_review_page_lists_only_owned_books_and_never_builds(hosted,monkeypatch):
    from tests.test_ebook_v2_topics import topic_spec
    app,client,books,*_=hosted
    own=books.create('alice','topic:review-page-owned',dict(topic_spec(),topic='<script>alert(1)</script>'))
    foreign=books.create('bob','topic:review-page-foreign',dict(topic_spec(),topic='Other account private title'))
    monkeypatch.setattr(books,'advance',lambda *a,**k:pytest.fail('A review page must never build'))
    response=client.get('/api/ebook-recovery/workspace?book='+own['id'])
    assert response.status_code==200 and response.headers['Cache-Control']=='no-store'
    assert b'&lt;script&gt;alert(1)&lt;/script&gt;' in response.data
    assert b'Other account private title' not in response.data
    assert client.get('/api/ebook-recovery/workspace?book='+foreign['id']).status_code==404
    assert app.test_client().get('/api/ebook-recovery/workspace').status_code==401
    assert books.get('alice',own['id'])['revision']==own['revision']


def test_topic_status_and_unfinished_files_are_private_read_only_requests(hosted,monkeypatch):
    from tests.test_ebook_v2_topics import topic_spec
    app,client,books,*_=hosted
    book=books.create('alice','topic:private-review-status',topic_spec());url='/api/ebook-recovery/books/'+book['id']
    monkeypatch.setattr(books,'advance',lambda *a,**k:pytest.fail('Status must never build'))
    assert client.get(url).status_code==200 and client.get(url).json['files']==[]
    assert client.get(url+'/files/ebook.pdf?preview=1').status_code==400
    with client.session_transaction() as session:session['_user_id']='bob'
    assert client.get(url).status_code==404
    assert client.get(url+'/files/package.zip?preview=1').status_code==404
    assert app.test_client().get(url).status_code==401


def test_topic_review_http_delivers_exact_shared_pdf_and_zip_without_regeneration(hosted,provider,monkeypatch):
    import hashlib,io,zipfile
    from tests.test_ebook_v2_topics import topic_spec
    from services.ebook_v2.workflow_topics import run_topic_book
    app,client,books,artifacts,*_=hosted
    book=books.create('alice','topic:review-http-files',topic_spec())
    assert run_topic_book(app.extensions['ebook_v2_hosted'],'alice',book['id'],ready=lambda:True)['state']=='REVIEW'
    calls=len(provider['calls']);monkeypatch.setattr(books,'advance',lambda *a,**k:pytest.fail('A review download must never build'))
    url='/api/ebook-recovery/books/'+book['id']
    assert client.get('/api/ebook-recovery/workspace?book='+book['id']).status_code==200
    assert client.get(url).json['files']==['ebook.pdf','package.zip']
    pdf=client.get(url+'/files/ebook.pdf?preview=1');package=client.get(url+'/files/package.zip?preview=1')
    assert pdf.status_code==package.status_code==200
    for response in (pdf,package):
        assert response.headers['X-Content-SHA256']==hashlib.sha256(response.data).hexdigest()
        assert response.headers['Cache-Control']=='no-store'
    with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
        assert archive.testzip() is None and archive.read('ebook.pdf')==pdf.data
    assert len(provider['calls'])==calls and books.get('alice',book['id'])['state']=='REVIEW'
