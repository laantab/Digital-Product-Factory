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
    return app, client, books, artifacts, connect, snapshot, headers, settings


def test_signed_recovery_reaches_download_without_worker_local_files(hosted):
    app, client, books, artifacts, connect, snapshot, headers, settings = hosted
    books.record_worker('test-worker')
    path = '/api/ebook-recovery/snapshots/'+snapshot+'/books'
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
    path = '/api/ebook-recovery/snapshots/'+snapshot+'/books'
    assert client.post(path,json=settings).status_code == 403
    assert client.post(path,json=settings,headers=headers).status_code == 503
    assert books.listing('alice') == []
    assert app.test_client().post(path,json=settings,headers=headers).status_code == 401
    app.extensions.pop('ebook_v2_hosted')
    assert client.post(path,json=settings,headers=headers).status_code == 503


def test_foreign_account_and_client_manuscript_cannot_be_imported(hosted):
    app, client, books, artifacts, connect, snapshot, headers, settings = hosted
    books.record_worker('test-worker')
    path = '/api/ebook-recovery/snapshots/'+snapshot+'/books'
    assert client.post(path,json={**settings,'chapters':[]},headers=headers).status_code == 400
    with client.session_transaction() as session:
        session['_user_id'] = 'bob'
    assert client.post(path,json=settings,headers=headers).status_code == 404
    assert books.listing('alice') == []
