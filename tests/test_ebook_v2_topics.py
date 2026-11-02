"""Local protocol fixtures prove integration, not real model generation."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
import json
import pytest
from services.ebook_v2.books import Books,Conflict
from services.ebook_v2 import local_text
from services.ebook_v2.worker import Repairable
from tests.ebook_v2_fixture import spec as supplied
from tests.test_ebook_v2_customer_path import live,worker,stop,wait_for


def topic_spec(mode="automatic"):
    return {"source":"ollama","topic":"Small desk organization for beginners",
        "audience":"Adults working at a small desk at home","outcome":"Create a usable work surface and a repeatable reset routine",
        "author":"Acceptance fixture","chapter_count":2,"min_words":450,"mode":mode,"research_acknowledged":True}


def developed_chapter(title):
    source=supplied()["chapters"][0 if title=="Choose one clear working area" else 1]
    addition='''For a practical trial, imagine preparing to answer a set of letters while a laptop and several reference folders share the desk. Put the current letter in the clear area and place the next action beside it. Keep the reference folder within reach without covering the writing space. When you need to switch tasks, return the letter and its note to a clearly identified place. The note should describe what remains to be done, rather than simply saying that the project is unfinished. When you return, begin with that action before opening another folder or moving unrelated items onto the desk.

At your next review, describe what happened in ordinary language. You might note that you found the correct folder immediately, or that a container blocked the space where you wanted to write. These observations help you adjust the arrangement without relying on a perfect memory. Keep changes small enough that you can tell which one helped. If an adjustment causes a new problem, reverse that change and keep the parts that still work. The trial is useful because it produces information about your own routine, not because it proves that one arrangement will work for every person or every kind of desk.'''
    return {"title":title,"text":source["text"]+"\n\n"+addition}


@pytest.fixture
def provider(monkeypatch):
    state={"calls":[],"cloud":False,"redirect":False,"missing":False,"incomplete":False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,data,status=200):
            body=json.dumps(data).encode();self.send_response(status)
            self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)))
            if status==302:self.send_header("Location","https://example.invalid/paid")
            self.end_headers();self.wfile.write(body)
        def do_GET(self):
            state["calls"].append((self.path,{}))
            if state["redirect"]:return self.reply({},302)
            return self.reply({"models":[] if state["missing"] else [{"name":"fixture-local:1","digest":"fixture-digest"}]})
        def do_POST(self):
            request=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["calls"].append((self.path,request))
            if self.path=="/api/show":return self.reply({"remote_host":"https://cloud.invalid"} if state["cloud"] else {})
            if state.get("capacity"):return self.reply({"error":"llama-server process has terminated: signal: killed"},500)
            schema=request["format"]
            if "titles" in schema["properties"]:result={"titles":["A Clear Desk","Room for Useful Work","The Desk Reset Guide"]}
            elif "chapters" in schema["properties"]:
                result={"chapters":[{"title":ch["title"],"purpose":"A distinct practical step for a useful desk arrangement"} for ch in supplied()["chapters"]]}
            elif "checks" in schema["properties"]:
                state["review_count"]=state.get("review_count",0)+1
                rejected=state.get("reject_first_review") and state["review_count"]==1
                result={"checks":{key:not rejected for key in local_text.CHECKS},
                    "issues":["Clarify which volunteer owns the next action."] if rejected else []}
            elif "new_paragraphs" in schema["properties"]:
                state["addition_count"]=state.get("addition_count",0)+1
                source=[p for ch in supplied()["chapters"] for p in ch["text"].split("\n\n")]
                result={"new_paragraphs":[source[state["addition_count"]%len(source)]]}
            else:
                result=developed_chapter(schema["properties"]["title"]["enum"][0])
                if state.get("short_writing"):
                    result["text"]=supplied()["chapters"][0]["text"].split("\n\n")[0]
            self.reply({"done":not state["incomplete"],"done_reason":"length" if state["incomplete"] else "stop","response":json.dumps(result)})
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setenv("FACTORY_V2_OLLAMA_URL",f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("FACTORY_V2_OLLAMA_MODEL","fixture-local:1")
    try:yield state
    finally:server.shutdown();server.server_close();thread.join(3)


@pytest.mark.parametrize("mode",["automatic","manual"])
def test_topic_pipeline_choices_and_validated_exports(provider,tmp_path,mode):
    books=Books(tmp_path/"studio.sqlite",tmp_path/"objects");books.initialize()
    books.record_worker("fixture-provider",local_text=True)
    book=books.create("alice","topic-protocol-request-001",topic_spec(mode));book_id=book["id"]
    choices=[]
    for _ in range(60):
        book=books.get("alice",book_id);view=books.status("alice",book_id)
        if book["state"]=="WAITING_TITLE":
            choices.append("title");books.decide("alice",book_id,book["revision"],"title",view["titles"][0])
        elif book["state"]=="WAITING_OUTLINE":
            choices.append("outline");books.decide("alice",book_id,book["revision"],"outline",True)
        elif book["state"]=="WAITING_COVER":
            choices.append("cover");books.decide("alice",book_id,book["revision"],"cover","editorial")
        elif book["state"]=="REVIEW":
            assert mode=="manual";books.approve("alice",book_id,book["revision"])
        elif book["state"]=="READY":break
        else:books.advance("alice",book_id)
    else:pytest.fail("Protocol-fixture topic workflow did not finish")
    assert choices==(["title","cover"] if mode=="automatic" else ["title","outline","cover"])
    pdf,_=books.download("alice",book_id,"ebook.pdf")
    assert pdf.startswith(b"%PDF-")
    assert books.status("alice",book_id)["chapters_checked"]==2
    calls=[body for path,body in provider["calls"] if path=="/api/generate"]
    assert len(calls)==6  # titles, outline, two distinct chapters and two reviews
    assert all(call["stream"] is False and call["think"] is False and isinstance(call["format"],dict) for call in calls)
    assert all(path in {"/api/tags","/api/show","/api/generate"} for path,_ in provider["calls"])
    from services.ebook_v2.editions import editable,edit
    saved=editable(books,"alice",book_id)
    saved["spec"]["title"]="Owner revised title"
    edited=edit(books,"alice",book_id,saved["revision"],"topic-edit-request-001",saved["spec"])
    before=len(provider["calls"])
    for _ in range(20):
        edited=books.advance("alice",edited["id"])
        if edited["state"]=="REVIEW":break
    assert edited["state"]=="REVIEW"
    assert len(provider["calls"])==before
    assert books.download("alice",book_id,"ebook.pdf")[0]==pdf


def test_cloud_model_metadata_is_refused_before_generation(provider):
    provider["cloud"]=True
    assert not local_text.ready()
    with pytest.raises(Repairable) as error:local_text.generate("A chapter",local_text.TITLE_SCHEMA)
    assert error.value.code=="LOCAL_CONFIGURATION"
    assert not any(path=="/api/generate" for path,_ in provider["calls"])


def test_redirect_is_not_followed(provider):
    provider["redirect"]=True
    with pytest.raises(Repairable) as error:local_text.generate("A chapter",local_text.TITLE_SCHEMA)
    assert error.value.code=="LOCAL_CONFIGURATION"
    assert [path for path,_ in provider["calls"]]==["/api/tags"]


def test_missing_model_is_a_readiness_failure_not_a_pull(provider):
    provider["missing"]=True
    assert not local_text.ready()
    with pytest.raises(Repairable) as error:local_text.generate("A chapter",local_text.TITLE_SCHEMA)
    assert error.value.code=="LOCAL_UNAVAILABLE"
    assert all(path=="/api/tags" for path,_ in provider["calls"])


def test_truncated_response_is_rejected(provider):
    provider["incomplete"]=True
    with pytest.raises(Repairable) as error:local_text.generate("A chapter",local_text.TITLE_SCHEMA)
    assert error.value.code=="INCOMPLETE_RESPONSE"


@pytest.mark.parametrize("url",["https://127.0.0.1:11434","http://example.com","http://user:password@localhost:11434",
    "http://127.0.0.1:11434/path","http://127.0.0.1:11434?redirect=1"])
def test_nonlocal_or_ambiguous_endpoint_never_receives_text(monkeypatch,url):
    monkeypatch.setenv("FACTORY_V2_OLLAMA_URL",url)
    with pytest.raises(Repairable) as error:local_text.configuration()
    assert error.value.code=="LOCAL_CONFIGURATION"


def test_negative_claims_key_ambiguity_cannot_approve_an_invented_percentage(monkeypatch):
    chapter=developed_chapter("Choose one clear working area")
    chapter["text"]+="\n\nSarah reduced her clutter by70 percent in a week."
    # Even an approving model does not override the deterministic numerical gate.
    monkeypatch.setattr(local_text,"generate",lambda *a,**kw:{"checks":{key:True for key in local_text.CHECKS},"issues":[]})
    with pytest.raises(Repairable) as error:local_text.review_handler({"chapter":chapter,"spec":topic_spec()},"")
    assert error.value.code=="EDITORIAL_FINDINGS"
    assert not local_text.review_valid(error.value.candidate)


def test_research_limitation_requires_explicit_acknowledgment():
    from services.ebook_v2.books import clean_spec
    raw=topic_spec();raw["research_acknowledged"]=False
    with pytest.raises(ValueError):clean_spec(raw)


def test_local_model_readiness_is_required_before_http_topic_attempt(live):
    books,session,base,data,app=live
    books.record_worker("supplied-text-only",local_text=False)
    response=session.post(base+"/api/books",json={"request_key":"no-model-http-0001","spec":topic_spec()})
    assert response.status_code==503
    assert books.listing("1")==[]


def test_automatic_topic_browser_only_requires_title_and_cover_choices(provider,live):
    from playwright.sync_api import sync_playwright
    import io,zipfile
    from pathlib import Path
    books,session,base,data,app=live
    process=worker(data)
    try:
        wait_for(lambda:books.available(local_text=True))
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            context=browser.new_context(accept_downloads=True)
            context.add_cookies([{"name":"ebook_v2_session","value":session.cookies.get("ebook_v2_session"),"url":base}])
            page=context.new_page();errors=[];page.on("pageerror",lambda error:errors.append(str(error)))
            page.goto(base)
            raw=topic_spec()
            page.locator('[name="source"]').select_option("ollama")
            for key in ("topic","audience","outcome","author"):page.locator(f'[name="{key}"]').fill(raw[key])
            page.locator('[name="chapter_count"]').fill("2")
            page.locator('[name="min_words"]').select_option("450")
            page.locator('[name="research_acknowledged"]').check()
            page.get_by_role("button",name="Create my book").click()
            page.get_by_role("button",name="A Clear Desk",exact=True).wait_for(state="visible",timeout=30000)
            page.get_by_role("button",name="A Clear Desk",exact=True).click()
            page.get_by_role("button",name="Warm Wellness",exact=True).wait_for(state="visible",timeout=60000)
            assert page.locator("#actions img").count()==6
            page.wait_for_function("Array.from(document.querySelectorAll('#actions img')).every(image=>image.complete&&image.naturalWidth===1800)")
            page.get_by_role("button",name="Warm Wellness",exact=True).click()
            page.get_by_role("link",name="Download PDF",exact=True).wait_for(state="visible",timeout=30000)
            assert page.get_by_role("button",name="Approve this edition").count()==0
            with page.expect_download() as download:page.get_by_role("link",name="Download PDF",exact=True).click()
            pdf=Path(download.value.path()).read_bytes()
            with page.expect_download() as download:page.get_by_role("link",name="Download complete ZIP").click()
            with zipfile.ZipFile(download.value.path()) as archive:
                assert archive.testzip() is None and archive.read("ebook.pdf")==pdf
            assert books.listing("1")[0]["title"]=="A Clear Desk"
            assert errors==[]
            context.close();browser.close()
    finally:stop(process)


def test_short_single_paragraph_is_retained_and_expanded_without_replacement(monkeypatch):
    chapter={"title":"Choose one clear working area","text":"Begin with the task you actually do at your desk. "*8}
    with pytest.raises(Repairable) as failure:local_text._require(chapter,450,chapter["title"])
    assert failure.value.code=="SHORT_CHAPTER"
    assert failure.value.candidate["chapter"]==chapter
    source=developed_chapter(chapter["title"])
    paragraphs=source["text"].split("\n\n")
    monkeypatch.setattr(local_text,"generate",lambda *a,**kw:{"new_paragraphs":paragraphs})
    expanded=local_text.expand(chapter,topic_spec(),"expand_saved_chapter")
    assert expanded["text"].startswith(chapter["text"]+"\n\n")
    assert expanded["title"]==chapter["title"]
    assert len(expanded["text"].split())>=450


def test_structured_paragraph_output_preserves_all_model_paragraphs():
    chapter=developed_chapter("Choose one clear working area")
    structured={"title":chapter["title"],"paragraphs":chapter["text"].split("\n\n")}
    assert local_text._require(structured,450,chapter["title"])==chapter
    with pytest.raises(Repairable):local_text.as_chapter({"title":"Bad","paragraphs":[None]})


def test_response_shapes_bound_paragraph_growth_and_title_tokens(provider):
    schema=local_text.chapter_schema("A realistic chapter",450)
    paragraphs=schema["properties"]["paragraphs"]
    assert paragraphs["maxItems"]==8 and paragraphs["items"]["maxLength"]==3000
    assert local_text.chapter_schema("A longer chapter",1800)["properties"]["paragraphs"]["maxItems"]>=18
    local_text.titles_handler({"spec":topic_spec()},"")
    calls=[body for path,body in provider["calls"] if path=="/api/generate"]
    assert calls[-1]["options"]["num_predict"]==500


@pytest.mark.parametrize("markup",['</think>}<tool_response>','&lt;tool_response&gt;',
                                 'example_sentence_1": "Internal field"','<|im_end|>'])
def test_model_review_cannot_approve_internal_markup(monkeypatch,markup):
    chapter=developed_chapter("Choose one clear working area")
    chapter["text"]+="\n\n"+markup
    monkeypatch.setattr(local_text,"generate",lambda *a,**kw:{"checks":{key:True for key in local_text.CHECKS},"issues":[]})
    assert not local_text.chapter_valid({"chapter":chapter,"minimum":450})
    with pytest.raises(Repairable) as error:local_text._require(chapter,450,chapter["title"])
    assert error.value.code=="MODEL_ARTIFACT"
    with pytest.raises(Repairable):local_text.review_handler({"chapter":chapter,"spec":topic_spec()},"")


def test_echoed_source_is_not_counted_as_new_expansion(monkeypatch):
    chapter=developed_chapter("Choose one clear working area")
    echoed=chapter["text"].split("\n\n")
    novel=supplied()["chapters"][1]["text"].split("\n\n")[0]
    monkeypatch.setattr(local_text,"generate",lambda *a,**kw:{"new_paragraphs":echoed+[novel]})
    expanded=local_text.expand(chapter,topic_spec(),"expand_saved_section")
    assert expanded["text"]==chapter["text"]+"\n\n"+novel


def test_partial_expansion_checkpoints_survive_restart_before_chapter_completion(provider,tmp_path):
    provider["short_writing"]=True
    books=Books(tmp_path/"studio.sqlite",tmp_path/"objects");books.initialize()
    book=books.create("alice","partial-graph-request-001",topic_spec());book_id=book["id"]
    from services.ebook_v2.topics import data as topic_data
    first_expansion=None
    for _ in range(60):
        book=books.get("alice",book_id)
        if book["state"]=="WAITING_TITLE":
            view=books.status("alice",book_id)
            books.decide("alice",book_id,book["revision"],"title",view["titles"][0])
        else:books.advance("alice",book_id)
        saved=topic_data(books,books.get("alice",book_id))
        key=saved["units"].get("expand:0:0")
        if key and books.units.get("alice",key)["state"]=="COMPLETE":first_expansion=key;break
    assert first_expansion is not None
    restarted=Books(books.units.path,books.root)
    for _ in range(60):
        restarted.advance("alice",book_id)
        saved=topic_data(restarted,restarted.get("alice",book_id))
        key=saved["units"].get("chapter:0")
        if key and restarted.units.get("alice",key)["state"]=="COMPLETE":break
    else:pytest.fail("Measured expansion did not complete the chapter")
    assert restarted.units.get("alice",first_expansion)["attempts"]==1
    assert len(restarted.units.get("alice",key)["output"]["chapter"]["text"].split())>=450


@pytest.mark.parametrize("defect",[
    "When I worked with a volunteer group, we always used a weekly task list.",
    "The next sentence contains unexpected text: This坦白,",
    "By regularly reflecting on what is working and what isn‘",
    "This structured approach to",
])
def test_independent_prose_guards_reject_model_approved_defects(monkeypatch,defect):
    chapter=developed_chapter("Choose one clear working area")
    chapter["text"]+="\n\n"+defect
    monkeypatch.setattr(local_text,"generate",lambda *a,**kw:{"checks":{key:True for key in local_text.CHECKS},"issues":[]})
    assert not local_text.review_valid({"chapter":chapter,"minimum":450,"report":{"checks":{key:True for key in local_text.CHECKS},"issues":[]}})
    with pytest.raises(Repairable):local_text._require(chapter,450,chapter["title"])


def test_sentence_repetition_across_different_paragraph_boundaries_is_rejected():
    chapter=developed_chapter("Choose one clear working area")
    sentence="For a practical trial, imagine preparing to answer a set of letters while a laptop and several reference folders share the desk."
    chapter["text"]+="\n\n"+sentence+" Add a different ending to disguise the copied paragraph."
    assert any("repeated" in issue for issue in local_text.generated_issues(chapter))
    assert not local_text.chapter_valid({"chapter":chapter,"minimum":450})


def test_design_name_and_workflow_settings_never_become_writing_subject(monkeypatch):
    source=topic_spec();source.update(theme="wellness",title="internal fallback",mode="automatic")
    captured=[]
    def generate(prompt,schema,repair="",**kwargs):
        captured.append(prompt)
        if "titles" in schema["properties"]:return {"titles":["A","B","C"]}
        return {"chapters":[{"title":"Team planning","purpose":"Coordinate concrete weekly tasks"}]*2}
    monkeypatch.setattr(local_text,"generate",generate)
    local_text.titles_handler({"spec":source},"")
    local_text.outline_handler({"spec":source,"title":"Team planning"},"")
    assert all('wellness' not in prompt and 'internal fallback' not in prompt and 'automatic' not in prompt for prompt in captured)
    assert all(source["topic"] in prompt and source["outcome"] in prompt for prompt in captured)


def test_local_memory_exhaustion_is_identified_without_blind_retries(provider):
    from services.ebook_v2.topics import policies
    provider["capacity"]=True
    with pytest.raises(Repairable) as failure:local_text.generate("Outline a useful book",local_text.PLAN_SCHEMA)
    assert failure.value.code=="LOCAL_CAPACITY"
    assert "LOCAL_CAPACITY" not in policies()["outline"].repairs


def test_copyedit_and_independent_recheck_are_separate_single_call_steps(monkeypatch):
    chapter=developed_chapter("Choose one clear working area")
    calls=[]
    def generate(prompt,schema,repair="",**kwargs):
        calls.append(prompt)
        if "checks" in schema["properties"]:return {"checks":{key:True for key in local_text.CHECKS},"issues":[]}
        return chapter
    monkeypatch.setattr(local_text,"generate",generate)
    previous={"chapter":chapter,"report":{"checks":{key:False for key in local_text.CHECKS},
        "issues":["Clarify the next action."]}}
    with pytest.raises(Repairable) as pending:
        local_text.review_handler({"chapter":chapter,"spec":topic_spec(),"_recovery":previous},"apply_editorial_feedback")
    assert len(calls)==1 and pending.value.code=="EDITORIAL_RECHECK"
    assert pending.value.candidate["awaiting_review"] is True
    reviewed=local_text.review_handler({"chapter":chapter,"spec":topic_spec(),"_recovery":pending.value.candidate},"review_saved_revision")
    assert len(calls)==2 and local_text.review_valid(reviewed)


def test_real_worker_editorial_repair_never_combines_model_operations(provider,tmp_path):
    provider["reject_first_review"]=True
    books=Books(tmp_path/"studio.sqlite",tmp_path/"objects");books.initialize()
    books.record_worker("fixture-provider",local_text=True)
    import time
    clock=[time.time()];books.units.clock=lambda:clock[0]
    book=books.create("alice","single-operation-editorial-001",topic_spec())
    for _ in range(100):
        book=books.get("alice",book["id"]);view=books.status("alice",book["id"])
        if book["state"]=="WAITING_TITLE":books.decide("alice",book["id"],book["revision"],"title",view["titles"][0])
        elif book["state"]=="WAITING_COVER":books.decide("alice",book["id"],book["revision"],"cover","editorial")
        elif book["state"]=="READY":break
        else:
            assert book["state"]=="RUNNING"
            before=len([path for path,_ in provider["calls"] if path=="/api/generate"])
            books.advance("alice",book["id"])
            clock[0]+=1  # Advance persisted retry time without slowing the protocol test.
            after=len([path for path,_ in provider["calls"] if path=="/api/generate"])
            assert after-before<=1
    else:pytest.fail("Bounded editorial correction did not finish")
    from services.ebook_v2.topics import data
    saved=data(books,books.get("alice",book["id"]))
    assert books.units.get("alice",saved["units"]["chapter:0"])["attempts"]==1
    assert books.units.get("alice",saved["units"]["review:0"])["attempts"]==3
    assert books.units.get("alice",saved["units"]["review:0"])["max_attempts"]==5


def test_incomplete_editorial_candidate_can_be_copyedited_then_rechecked(monkeypatch):
    chapter=developed_chapter('Choose one clear working area')
    broken={**chapter,'text':chapter['text']+'\n\nBy regularly reflecting on what is working and what isn‘'}
    report={'checks':{key:False for key in local_text.CHECKS},'issues':local_text.generated_issues(broken)}
    calls=[]
    def generate(*args,**kwargs):
        calls.append(args)
        return chapter
    monkeypatch.setattr(local_text,'generate',generate)
    with pytest.raises(Repairable) as result:
        local_text.review_handler({'spec':topic_spec(),'chapter':broken,'_recovery':{'chapter':broken,'report':report}},'apply_editorial_feedback')
    assert result.value.code=='EDITORIAL_RECHECK'
    assert result.value.candidate['chapter']==chapter
    assert result.value.candidate['awaiting_review'] is True
    assert len(calls)==1
