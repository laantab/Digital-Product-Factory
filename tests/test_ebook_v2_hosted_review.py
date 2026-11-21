"""Customer approval checks exact shared bytes without generation or local files."""
import copy
import io
import shutil
import zipfile
from contextlib import closing

import pytest

from services.ebook_v2.books import Conflict
from services.ebook_v2.hosted_review import approve
from tests.test_ebook_v2_hosted_handoff import hosted


@pytest.fixture
def review(hosted,monkeypatch):
    app,client,books,artifacts,connect,snapshot,headers,settings=hosted
    books.record_worker('review-fixture')
    response=client.post('/api/ebook-recovery/projects/1/snapshots',json=settings,headers=headers)
    book=books.get('alice',response.json['book_id'])
    for _ in range(20):
        book=books.advance('alice',book['id'])
        if book['state']=='REVIEW':break
    assert book['state']=='REVIEW'
    artifacts.publish('alice',book['id'])
    monkeypatch.setattr(books,'advance',lambda *a,**kw:pytest.fail('Review must never generate'))
    return hosted,book,'/api/ebook-recovery/books/'+book['id']


def test_signed_approval_preserves_source_units_and_actual_shared_pdf_zip_after_disk_loss(review):
    (app,client,books,artifacts,connect,_,headers,_),book,url=review
    with closing(connect()) as conn:original=tuple(conn.execute('SELECT * FROM projects WHERE id=1').fetchone())
    units=[books.units.get('alice',key) for key in book['units']]
    pdf=client.get(url+'/files/ebook.pdf?preview=1').data
    shutil.rmtree(books.root)
    result=client.post(url+'/approve',json={'revision':book['revision'],'reviewed':True},headers=headers)
    assert result.status_code==200,result.json
    assert result.json=={'book_id':book['id'],'revision':book['revision']+1,'state':'READY','generation_started':False,'publication_started':False}
    assert client.get(url+'/files/ebook.pdf').data==pdf
    package=client.get(url+'/files/package.zip')
    with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
        assert archive.testzip() is None and archive.read('ebook.pdf')==pdf
    assert [books.units.get('alice',key) for key in book['units']]==units
    with closing(connect()) as conn:assert tuple(conn.execute('SELECT * FROM projects WHERE id=1').fetchone())==original
    assert client.post(url+'/approve',json={'revision':book['revision'],'reviewed':True},headers=headers).status_code==409
    assert books.get('alice',book['id'])['revision']==book['revision']+1


@pytest.mark.parametrize('body',[{}, {'revision':True,'reviewed':True},{'revision':-1,'reviewed':True},
    {'revision':0,'reviewed':False},{'revision':0,'reviewed':True,'owner':'alice'}])
def test_approval_requires_exact_explicit_review_request_without_book_changes(review,body):
    (_,client,books,_,_,_,headers,_),book,url=review
    assert client.post(url+'/approve',json=body,headers=headers).status_code==400
    assert books.get('alice',book['id'])==book


@pytest.mark.parametrize('identity',['signed-out','foreign','transferred'])
def test_unsigned_foreign_or_transferred_book_cannot_be_approved(review,identity):
    (app,client,books,_,connect,_,headers,_),book,url=review
    if identity=='signed-out':client=app.test_client();expected=401
    elif identity=='foreign':
        with client.session_transaction() as session:session['_user_id']='bob'
        expected=404
    else:
        with closing(connect()) as conn:
            conn.execute("UPDATE projects SET user_id='bob' WHERE id=1");conn.commit()
        expected=404
    assert client.post(url+'/approve',json={'revision':book['revision'],'reviewed':True},headers=headers).status_code==expected
    assert books.get('alice',book['id'])==book


def test_missing_csrf_stale_revision_and_corrupt_file_leave_review_pending(review):
    (_,client,books,artifacts,_,_,headers,_),book,url=review
    body={'revision':book['revision'],'reviewed':True}
    assert client.post(url+'/approve',json=body).status_code==403
    assert client.post(url+'/approve',json={**body,'revision':book['revision']-1},headers=headers).status_code==409
    receipt=artifacts.publish('alice',book['id'])
    artifacts.storage.put(receipt['files']['package.zip']['key'],b'corrupt package')
    assert client.post(url+'/approve',json=body,headers=headers).status_code==409
    assert books.get('alice',book['id'])==book


def test_concurrent_revision_change_cannot_be_approved_by_old_review(review,monkeypatch):
    (_,_,books,artifacts,*_),book,_=review
    download=artifacts.download;changed=[]
    def racing(*args,**kwargs):
        value=download(*args,**kwargs)
        if not changed:changed.append(books.save(book,state='REVIEW'))
        return value
    monkeypatch.setattr(artifacts,'download',racing)
    with pytest.raises(Conflict):approve(books,artifacts,'alice',book,book['revision'])
    assert books.get('alice',book['id'])==changed[0]


def test_source_transferred_while_files_are_read_cannot_be_approved(review,monkeypatch):
    (_,client,books,artifacts,connect,_,headers,_),book,url=review
    download=artifacts.download
    def transferred(*args,**kwargs):
        value=download(*args,**kwargs)
        with closing(connect()) as conn:
            conn.execute("UPDATE projects SET user_id='bob' WHERE id=1");conn.commit()
        return value
    monkeypatch.setattr(artifacts,'download',transferred)
    assert client.post(url+'/approve',json={'revision':book['revision'],'reviewed':True},headers=headers).status_code==404
    assert books.get('alice',book['id'])==book


@pytest.mark.parametrize('width,height',[(1280,900),(390,844)])
def test_review_browser_requires_acknowledgement_then_saves_one_decision(review,width,height,tmp_path):
    from threading import Thread
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    (app,client,books,*_),book,url=review
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            context=browser.new_context(viewport={'width':width,'height':height})
            context.add_cookies([{'name':'session','value':client.get_cookie('session').value,'url':base}])
            page=context.new_page();errors=[];posts=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:posts.append(request.url) if request.method=='POST' else None)
            page.goto(base+'/api/ebook-recovery/workspace?book='+book['id'])
            page.locator('#approval').wait_for(state='visible')
            assert page.locator('#approve').is_disabled() and posts==[]
            page.locator('#reviewed').check();assert page.locator('#approve').is_enabled()
            page.screenshot(path=f'/tmp/factory-review-before-{width}.png',full_page=True)
            page.locator('#approve').click()
            page.wait_for_function("document.getElementById('state').textContent==='Reviewed edition'")
            assert page.locator('#approval').is_hidden() and page.locator('#pdf').inner_text()=='Open PDF'
            assert len(posts)==1 and posts[0].endswith(url+'/approve') and not errors
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=f'/tmp/factory-review-after-{width}.png',full_page=True)
            assert books.get('alice',book['id'])['state']=='READY'
            browser.close()
    finally:server.shutdown();server.server_close();thread.join(3)
