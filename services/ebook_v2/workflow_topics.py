"""Separate opt-in topic task using the existing local-only writing engine.

No runtime is installed, provider substituted or compute plan upgraded here.
Customer HTTP creation and provisioning a supported runtime are separate gates.
"""
import os
import time
import uuid
from threading import Event, Thread

from .books import Conflict
from .workflow_recovery import Dispatch


class TopicDispatch(Dispatch):
    @staticmethod
    def validate(book):
        if (book['spec'].get('source')!='ollama' or book['spec'].get('mode')!='automatic'
                or not book['request_key'].startswith('topic:')):
            raise ValueError('Choose an automatic topic request')


def run_topic_book(services, owner, book_id, *, budget=5400, clock=time.monotonic,
                   pause=time.sleep, ready=None):
    from .local_text import ready as local_ready
    from .shared_work_files import restore
    from .topics import data
    books, artifacts=services['books'],services['artifacts']
    book=books.get(owner,book_id)
    TopicDispatch.validate(book)
    # Completed retries and approved editions need no inference service.
    with books.units.transaction() as conn:
        published=conn.execute('SELECT 1 FROM ebook_v2_artifacts WHERE book_id=? AND owner=?',
                              (book_id,str(owner))).fetchone()
    if published:
        return {'book_id':book_id,'state':book['state'],'files':['ebook.pdf','package.zip']}
    if book['state'] not in {'REVIEW','READY'} and not (ready or local_ready)():
        raise ValueError('The configured free local writer is unavailable. No drafting was started.')
    stopped=Event();worker_id='topic-'+uuid.uuid4().hex
    def heartbeat():
        while not stopped.is_set():
            books.record_worker(worker_id,local_text=True)
            stopped.wait(3)
    monitor=Thread(target=heartbeat,daemon=True)
    monitor.start();deadline=clock()+budget
    try:
        while True:
            book=books.get(owner,book_id)
            if book['state'] in {'REVIEW','READY'}:
                # Automatic local Studio output still requires actual-page
                # approval in the hosted delivery path before downloads.
                if book['state']=='READY':book=books.save(book,state='REVIEW')
                export=books.units.get(owner,data(books,book)['units']['export'])
                restore(books.root,export['output'],artifacts.storage)
                artifacts.publish(owner,book_id)
                return {'book_id':book_id,'state':'REVIEW','files':['ebook.pdf','package.zip']}
            if book['state']=='NEEDS_ATTENTION':
                return {'book_id':book_id,'state':book['state'],'files':[]}
            if clock()>=deadline:
                raise RuntimeError('Continue from saved topic checkpoints; do not create a replacement book')
            try:
                if book['state']=='WAITING_TITLE':
                    view=books.status(owner,book_id)
                    books.decide(owner,book_id,book['revision'],'title',view['titles'][0])
                elif book['state']=='WAITING_COVER':
                    books.decide(owner,book_id,book['revision'],'cover','editorial')
                elif book['state']=='RUNNING':books.advance(owner,book_id)
                else:raise ValueError('Unexpected topic-book state')
            except Conflict:pass
            pause(.1)
    finally:
        stopped.set();monitor.join(4)
        with books.units.transaction() as conn:
            conn.execute('DELETE FROM ebook_v2_workers WHERE id=?',(worker_id,))


def register(app, *, plan, retry):
    @app.task(timeout_seconds=6300,plan=plan,retry=retry)
    def create_topic_ebook(ctx, owner: str, book_id: str) -> dict:
        if os.environ.get('FACTORY_V2_TOPIC_WORKER_ENABLED')!='1':
            raise ValueError('Fresh-topic processing is not enabled; no model or paid provider was started')
        from .hosted_runtime import configured_services,initialize
        services=configured_services();initialize(services)
        return run_topic_book(services,owner,book_id)
    return create_topic_ebook
