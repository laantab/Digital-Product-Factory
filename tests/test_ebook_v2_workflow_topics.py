"""Topic task integration uses a local protocol fixture, never a paid model."""
import io
import shutil
import zipfile
from functools import partial

import pytest

from services.ebook_v2.shared_work_files import install
from services.ebook_v2.workflow_topics import TopicDispatch,run_topic_book,register
from services.ebook_v2.workflow_recovery import Dispatch
from services.ebook_v2.recovery_handoff import WorkerUnavailable
from services.storage.local import LocalFilesystemDriver
from tests.test_ebook_v2_hosted_handoff import hosted
from tests.test_ebook_v2_topics import provider,topic_spec


def test_topic_task_delivers_shared_review_bytes_and_preserves_approval(hosted,provider,tmp_path):
    app,client,books,artifacts,*_=hosted
    services=app.extensions['ebook_v2_hosted']
    install(books,partial(LocalFilesystemDriver,tmp_path/'shared'))
    book=books.create('alice','topic:worker-integration-001',topic_spec())
    def lose_local_files(_):shutil.rmtree(books.root,ignore_errors=True)
    result=run_topic_book(services,'alice',book['id'],ready=lambda:True,pause=lose_local_files)
    assert result['state']=='REVIEW'
    pdf,_=artifacts.download('alice',book['id'],'ebook.pdf',preview=True)
    package,_=artifacts.download('alice',book['id'],'package.zip',preview=True)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        assert archive.testzip() is None and archive.read('ebook.pdf')==pdf
    with pytest.raises(ValueError):artifacts.download('alice',book['id'],'ebook.pdf')
    with pytest.raises(LookupError):run_topic_book(services,'bob',book['id'])
    approved=books.approve('alice',book['id'],books.get('alice',book['id'])['revision'])
    before=len(provider['calls'])
    assert run_topic_book(services,'alice',book['id'],ready=lambda:False)['state']=='READY'
    assert len(provider['calls'])==before
    assert artifacts.download('alice',book['id'],'ebook.pdf')[0]==pdf


def test_missing_local_writer_stops_before_any_draft_or_work_unit(hosted):
    app,client,books,*_=hosted
    book=books.create('alice','topic:no-writer-001',topic_spec())
    with pytest.raises(ValueError,match='No drafting was started'):
        run_topic_book(app.extensions['ebook_v2_hosted'],'alice',book['id'],ready=lambda:False)
    from services.ebook_v2.topics import data
    assert data(books,book)['units']=={}
    assert books.get('alice',book['id'])['revision']==book['revision']


def test_topic_dispatch_reuses_claim_without_changing_saved_recovery(hosted):
    app,client,books,*_=hosted
    book=books.create('alice','topic:dispatch-001',topic_spec())
    calls=[]
    dispatch=TopicDispatch(books,'builder/create_topic_ebook',lambda *args:calls.append(args) or 'run-topic')
    dispatch.initialize();dispatch('alice',book['id']);dispatch('alice',book['id'])
    assert calls==[('builder/create_topic_ebook','alice',book['id'])]
    with pytest.raises(ValueError,match='saved manuscripts only'):
        Dispatch(books,'builder/recover_saved_ebook')('alice',book['id'])


def test_ambiguous_topic_submission_is_not_repeated(hosted):
    app,client,books,*_=hosted
    book=books.create('alice','topic:ambiguous-001',topic_spec());calls=[]
    def lost(*args):calls.append(args);raise TimeoutError()
    dispatch=TopicDispatch(books,'builder/create_topic_ebook',lost);dispatch.initialize()
    for _ in range(2):
        with pytest.raises(WorkerUnavailable):dispatch('alice',book['id'])
    assert len(calls)==1


def test_new_task_keeps_existing_compute_plan_and_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv('FACTORY_V2_TOPIC_WORKER_ENABLED',raising=False)
    calls=[]
    class App:
        def task(self,**settings):
            def decorate(fn):calls.append((settings,fn.__name__));return fn
            return decorate
    retry=object();task=register(App(),plan='flex',retry=retry)
    assert calls==[({'timeout_seconds':3600,'plan':'flex','retry':retry},'create_topic_ebook')]
    with pytest.raises(ValueError,match='no model or paid provider'):
        task(None,'alice','unused')


def test_approved_pilot_allowance_is_one_use_and_book_scoped(hosted,monkeypatch):
    from services.ebook_v2.workflow_topics import claim_pilot
    app,client,books,*_=hosted
    monkeypatch.setenv('FACTORY_V2_TOPIC_PILOT_BOOK','approved-book')
    with pytest.raises(ValueError,match='not the approved'):
        claim_pilot(books,'alice','another-book')
    claim_pilot(books,'alice','approved-book')
    with pytest.raises(ValueError,match='already used'):
        claim_pilot(books,'alice','approved-book')


def test_processing_budget_stop_is_visible_and_retains_completed_units(hosted,provider):
    from services.ebook_v2.topics import data
    app,client,books,*_=hosted
    book=books.create('alice','topic:budget-retained-001',topic_spec())
    books.advance('alice',book['id']);books.advance('alice',book['id'])
    before=data(books,books.get('alice',book['id']))['units'].copy()
    saved={key:books.units.get('alice',value) for key,value in before.items()}
    calls=len(provider['calls'])
    with pytest.raises(RuntimeError,match='saved topic checkpoints'):
        run_topic_book(app.extensions['ebook_v2_hosted'],'alice',book['id'],budget=0,ready=lambda:True)
    stopped=books.get('alice',book['id']);view=books.status('alice',book['id'])
    assert stopped['state']=='NEEDS_ATTENTION'
    assert 'processing time ended' in view['attention']
    assert data(books,stopped)['units']==before
    assert {key:books.units.get('alice',value) for key,value in before.items()}==saved
    assert len(provider['calls'])==calls
    resumed=books.resume('alice',book['id'],stopped['revision'])
    assert resumed['state']=='RUNNING' and 'stop_reason' not in data(books,resumed)
    assert data(books,resumed)['units']==before
