"""The real HTTP recovery path dispatches one job and returns shared bytes."""
from functools import partial
import io
import shutil
import zipfile

import pytest

from services.ebook_v2.shared_work_files import install
from services.ebook_v2.workflow_recovery import Dispatch, run_saved_book
from services.storage.local import LocalFilesystemDriver
from tests.test_ebook_v2_hosted_handoff import hosted


def test_on_demand_recovery_dispatches_once_and_restores_remote_files(hosted, tmp_path):
    app, client, books, artifacts, connect, snapshot, headers, settings = hosted
    calls = []
    dispatch = Dispatch(books, 'builder/recover_saved_ebook',
                        lambda *args: calls.append(args) or 'run-one')
    dispatch.initialize()
    services = app.extensions['ebook_v2_hosted']
    services['dispatch'] = dispatch
    install(books, partial(LocalFilesystemDriver, tmp_path/'shared'))
    url = '/api/ebook-recovery/projects/1/snapshots'
    response = client.post(url, json=settings, headers=headers)
    assert response.status_code == 202, response.json
    book_id = response.json['book_id']
    assert client.post(url, json=settings, headers=headers).json['book_id'] == book_id
    assert calls == [('builder/recover_saved_ebook', 'alice', book_id)]
    def replacement_worker(_):
        shutil.rmtree(books.root, ignore_errors=True)
    result = run_saved_book(services, 'alice', book_id, pause=replacement_worker)
    assert result['state'] == 'REVIEW'
    shutil.rmtree(books.root, ignore_errors=True)
    # A Render retry must reuse completed files and never render them again.
    before = [books.units.get('alice', key)['attempts'] for key in books.get('alice', book_id)['units']]
    assert run_saved_book(services, 'alice', book_id) == result
    assert [books.units.get('alice', key)['attempts'] for key in books.get('alice', book_id)['units']] == before
    prefix = '/api/ebook-recovery/books/'+book_id+'/files/'
    pdf = client.get(prefix+'ebook.pdf?preview=1')
    package = client.get(prefix+'package.zip?preview=1')
    assert pdf.status_code == package.status_code == 200
    with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
        assert archive.testzip() is None
        assert archive.read('ebook.pdf') == pdf.data
    with pytest.raises(LookupError):
        run_saved_book(services, 'bob', book_id)


def test_ambiguous_dispatch_is_preserved_without_automatic_resubmission(hosted):
    app, client, books, artifacts, connect, snapshot, headers, settings = hosted
    calls = []
    def disconnected(*args):
        calls.append(args)
        raise TimeoutError('response lost after server accepted request')
    dispatch = Dispatch(books, 'builder/recover_saved_ebook', disconnected)
    dispatch.initialize()
    app.extensions['ebook_v2_hosted']['dispatch'] = dispatch
    url = '/api/ebook-recovery/projects/1/snapshots'
    assert client.post(url, json=settings, headers=headers).status_code == 503
    assert client.post(url, json=settings, headers=headers).status_code == 503
    assert len(calls) == 1
    saved = books.listing('alice')
    assert len(saved) == 1 and saved[0]['state'] == 'RUNNING'
    with books.units.transaction() as conn:
        assert conn.execute('SELECT state FROM ebook_v2_dispatch').fetchone()['state'] == 'UNKNOWN'


def test_task_registration_preserves_legacy_task_and_uses_existing_plan(monkeypatch):
    from services.ebook_v2.workflow_recovery import register
    captured = []
    class App:
        def task(self, **settings):
            def decorate(fn):
                captured.append((settings, fn.__name__))
                return fn
            return decorate
    retry = object()
    task = register(App(), plan='flex', retry=retry)
    assert captured == [({'timeout_seconds':900, 'plan':'flex', 'retry':retry}, 'recover_saved_ebook')]
    assert task.__name__ == 'recover_saved_ebook'
