"""Exercise web -> queue -> independent worker -> shared file download."""
from functools import partial
import io
import shutil
import zipfile

from services.ebook_v2 import hosted_runtime
from services.ebook_v2.shared_work_files import install
from services.storage.local import LocalFilesystemDriver
from tests.test_ebook_v2_hosted_handoff import hosted


def test_configured_web_and_worker_complete_after_every_local_file_loss(hosted, monkeypatch, tmp_path):
    app, client, books, artifacts, connect, snapshot, headers, settings = hosted
    services = app.extensions.pop('ebook_v2_hosted')
    install(books, partial(LocalFilesystemDriver, tmp_path/'shared'))
    monkeypatch.setenv('FACTORY_V2_HOSTED_RECOVERY','1')
    monkeypatch.setattr(hosted_runtime,'configured_services',lambda:services)
    books.record_worker('integration-worker')
    response = client.post('/api/ebook-recovery/projects/1/snapshots',json=settings,headers=headers)
    assert response.status_code == 202, response.json
    assert app.extensions['ebook_v2_hosted'] is services
    book_id = response.json['book_id']
    for _ in range(20):
        outcomes = hosted_runtime.tick(services)
        assert outcomes
        # A replacement worker has shared checkpoints but no previous local files.
        shutil.rmtree(books.root,ignore_errors=True)
        if outcomes[0]['state'] == 'REVIEW': break
    assert outcomes[0]['state'] == 'REVIEW'
    prefix = '/api/ebook-recovery/books/'+book_id
    assert set(client.get(prefix).json['files']) == {'ebook.pdf','package.zip'}
    pdf = client.get(prefix+'/files/ebook.pdf?preview=1')
    package = client.get(prefix+'/files/package.zip?preview=1')
    assert pdf.status_code == package.status_code == 200
    with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
        assert archive.testzip() is None
        assert archive.read('ebook.pdf') == pdf.data
    assert hosted_runtime.tick(services) == []


def test_disabled_runtime_does_not_open_shared_services(hosted,monkeypatch):
    app, client, books, artifacts, connect, snapshot, headers, settings = hosted
    app.extensions.pop('ebook_v2_hosted')
    monkeypatch.delenv('FACTORY_V2_HOSTED_RECOVERY',raising=False)
    def forbidden():
        raise AssertionError('Disabled runtime must not connect')
    monkeypatch.setattr(hosted_runtime,'configured_services',forbidden)
    assert hosted_runtime.configure(app) is None
