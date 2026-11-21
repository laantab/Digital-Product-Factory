"""Real loopback HTTP/browser + independent CLI worker. No provider mocks."""
from contextlib import contextmanager
import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Thread
import time
import zipfile
import pytest
import requests
from werkzeug.serving import make_server
from services.ebook_v2.books import Books
from services.ebook_v2.web import create_app
from tests.ebook_v2_fixture import spec

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def live(tmp_path,monkeypatch):
    import database
    monkeypatch.setattr(database,"DB_PATH",str(tmp_path/"studio.sqlite"))
    monkeypatch.setenv("FACTORY_DB_BACKEND","sqlite")
    monkeypatch.delenv("DATABASE_URL",raising=False)
    books=Books(tmp_path/"studio.sqlite",tmp_path/"objects");books.initialize()
    app=create_app(books)
    server=make_server("127.0.0.1",0,app,threaded=True)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f"http://127.0.0.1:{server.server_port}"
    session=requests.Session();session.trust_env=False
    response=session.post(base+"/auth/register",json={"email":"alice@studio.example.test","password":"Disposable-test-password"})
    assert response.status_code==201,response.text
    home=session.get(base+"/")
    token=re.search(r'<meta name="csrf" content="([^"]+)"',home.text).group(1)
    session.headers["X-CSRF-Token"]=token
    try:yield books,session,base,tmp_path,app
    finally:session.close();server.shutdown();server.server_close();thread.join(3)


def worker(data):
    return subprocess.Popen([sys.executable,"-m","services.ebook_v2.cli","worker","--data",str(data),"--interval","0.5"],
        cwd=ROOT,env=os.environ.copy(),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def stop(process):
    process.terminate()
    try:process.wait(5)
    except subprocess.TimeoutExpired:process.kill();process.wait(5)


def wait_for(check,seconds=60):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        value=check()
        if value:return value
        time.sleep(.05)
    pytest.fail("The independent worker did not reach the required checkpoint")


def test_authenticated_http_downloads_checksums_and_customer_isolation(live):
    books,session,base,data,app=live
    process=worker(data)
    try:
        wait_for(books.available)
        response=session.post(base+"/api/books",json={"request_key":"real-http-supplied-001","spec":spec()})
        assert response.status_code==202,response.text
        book_id=response.json()["id"]
        final=wait_for(lambda: (b if (b:=session.get(base+"/api/books/"+book_id).json())["state"]=="REVIEW" else None))
        assert final["integrity"]["all_pages_rendered"]
        assert session.get(base+f"/api/books/{book_id}/files/ebook.pdf").status_code==400
        response=session.post(base+f"/api/books/{book_id}/approve",json={"revision":final["revision"]})
        assert response.status_code==200,response.text
        pdf=session.get(base+f"/api/books/{book_id}/files/ebook.pdf")
        package=session.get(base+f"/api/books/{book_id}/files/package.zip")
        for actual,signature in ((pdf,b"%PDF-"),(package,b"PK")):
            assert actual.status_code==200
            assert actual.content.startswith(signature)
            assert hashlib.sha256(actual.content).hexdigest()==actual.headers["X-Content-SHA256"]
            assert actual.headers["Cache-Control"]=="no-store"
        with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
            assert archive.testzip() is None
            assert archive.read("ebook.pdf")==pdf.content
            for name,mime in (("ebook.epub","application/epub+zip"),
                    ("manuscript.docx","application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                    ("cover.jpg","image/jpeg")):
                actual=session.get(base+f"/api/books/{book_id}/files/{name}")
                assert actual.status_code==200
                assert actual.headers["Content-Type"].split(";")[0]==mime
                assert archive.read(name)==actual.content
                assert hashlib.sha256(actual.content).hexdigest()==actual.headers["X-Content-SHA256"]
        other=requests.Session();other.trust_env=False
        assert other.get(base+"/api/books").status_code==401
        assert other.post(base+"/auth/register",json={"email":"bob@studio.example.test","password":"Disposable-test-password"}).status_code==201
        assert other.get(base+"/api/books/"+book_id).status_code==404
        assert other.get(base+f"/api/books/{book_id}/files/ebook.pdf").status_code==404
        assert other.get(base+"/api/books").json()["books"]==[]
        other.close()
    finally:stop(process)


def test_csrf_and_read_only_status(live):
    books,session,base,data,app=live
    token=session.headers.pop("X-CSRF-Token")
    assert session.post(base+"/api/books",json={"request_key":"csrf-supplied-001","spec":spec()}).status_code==403
    assert books.listing("1")==[]
    session.headers["X-CSRF-Token"]=token
    books.record_worker("csrf-only-test")
    response=session.post(base+"/api/books",json={"request_key":"csrf-supplied-001","spec":spec()})
    book_id=response.json()["id"]
    first=session.get(base+"/api/books/"+book_id).json()
    assert session.get(base+"/api/books/"+book_id).json()==first
    assert first["chapters_checked"]==0 and first["files"]==[]


def test_browser_shutdown_worker_restart_and_saved_book_download(live):
    from playwright.sync_api import sync_playwright
    books,session,base,data,app=live
    process=worker(data)
    try:
        wait_for(books.available)
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            context=browser.new_context(accept_downloads=True)
            cookie=session.cookies.get("ebook_v2_session")
            context.add_cookies([{"name":"ebook_v2_session","value":cookie,"url":base}])
            page=context.new_page();errors=[];page.on("pageerror",lambda error:errors.append(str(error)))
            page.goto(base)
            source=spec()
            page.locator('[name="images"]').select_option("text")
            page.locator('[name="title"]').fill(source["title"])
            page.locator('[name="author"]').fill(source["author"])
            page.locator('[name="manuscript"]').fill("\n\n".join("## "+ch["title"]+"\n\n"+ch["text"] for ch in source["chapters"]))
            page.get_by_role("button",name="Create my book").click()
            wait_for(lambda:len(books.listing("1"))==1)
            book_id=books.listing("1")[0]["id"]
            def first_saved():
                book=books.get("1",book_id)
                return bool(book["units"]) and books.units.get("1",book["units"][0])["state"]=="COMPLETE"
            wait_for(first_saved)
            first_id=books.get("1",book_id)["units"][0]
            stop(process);page.close()
            # Restart a separate dispatcher against the same actual saved DB/files.
            process=worker(data)
            wait_for(lambda:books.get("1",book_id)["state"]=="REVIEW")
            assert books.units.get("1",first_id)["attempts"]==1
            page=context.new_page();page.on("pageerror",lambda error:errors.append(str(error)))
            page.goto(base)
            page.locator("#saved button").first.click()
            page.get_by_role("button",name="Approve this edition").click()
            link=page.get_by_role("link",name="Download PDF",exact=True)
            link.wait_for(state="visible",timeout=15000)
            with page.expect_download() as download:link.click()
            pdf=Path(download.value.path()).read_bytes()
            with page.expect_download() as download:
                page.get_by_role("link",name="Download complete ZIP").click()
            package=Path(download.value.path()).read_bytes()
            with zipfile.ZipFile(io.BytesIO(package)) as archive:
                assert archive.testzip() is None and archive.read("ebook.pdf")==pdf
            assert pdf.startswith(b"%PDF-")
            page.get_by_role("button",name="Edit manuscript and view editions").click()
            page.locator('#actions [name="title"]').fill("A revised acceptance edition")
            editor=page.locator('#actions [name="manuscript"]')
            editor.fill(editor.input_value()+"\n\nThis revised author paragraph belongs only to the new edition.")
            page.get_by_role("button",name="Save new edition",exact=True).click()
            page.get_by_role("button",name="Approve this edition",exact=True).wait_for(state="visible",timeout=30000)
            page.get_by_role("button",name="Approve this edition",exact=True).click()
            revised_link=page.get_by_role("link",name="Download PDF",exact=True)
            revised_link.wait_for(state="visible",timeout=15000)
            with page.expect_download() as download:revised_link.click()
            revised_pdf=Path(download.value.path()).read_bytes()
            assert revised_pdf!=pdf
            assert books.download("1",book_id,"ebook.pdf")[0]==pdf
            assert books.units.get("1",first_id)["attempts"]==1
            assert len(books.listing("1"))==2
            assert errors==[]
            context.close();browser.close()
    finally:stop(process)


def test_session_survives_server_recreation_and_legacy_executor_is_not_started(live,monkeypatch):
    books,session,base,data,app=live
    import services.jobs.runner as legacy
    monkeypatch.setattr(legacy,"start",lambda:pytest.fail("Legacy executor started"))
    restored=create_app(Books(books.units.path,books.root))
    assert restored.secret_key==app.secret_key
    with restored.test_client() as client:
        client.set_cookie("ebook_v2_session",session.cookies.get("ebook_v2_session"))
        assert client.get("/api/books").status_code==200


def test_no_worker_preflight_starts_no_failed_attempt(live):
    books,session,base,data,app=live
    response=session.post(base+"/api/books",json={"request_key":"no-worker-request-001","spec":spec()})
    assert response.status_code==503
    assert books.listing("1")==[]
    book=books.create("1","paused-book-request",spec())
    before=books.get("1",book["id"])
    assert session.get(base+"/api/books/"+book["id"]).json()["state"]=="WAITING_SERVICE"
    assert books.get("1",book["id"])==before


def test_photo_preflight_refuses_unavailable_search_before_creating_a_book(live,monkeypatch):
    books,session,base,data,app=live
    for key in ('PEXELS_API_KEY','UNSPLASH_ACCESS_KEY','UNSPLASH_API_KEY'):
        monkeypatch.delenv(key,raising=False)
    books.record_worker('photo-preflight-test')
    response=session.post(base+'/api/books',json={
        'request_key':'photo-preflight-refusal-001','spec':{**spec(),'require_photos':True}})
    assert response.status_code==503
    assert 'has not been started' in response.json()['error']
    assert books.listing('1')==[]
