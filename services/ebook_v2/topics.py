"""Durable topic writing: title choice, plan, individual chapters and review."""
import json
import time
from .recovery import digest,encode,CorruptCheckpoint
from .worker import Policy
from . import local_text as text


def clean_spec(raw):
    result={"source":"ollama"}
    if raw.get("research_acknowledged") is not True:
        raise ValueError("This reconstruction does not assess market demand. Confirm that limitation before topic generation.")
    result["research_acknowledged"]=True
    for key,limit in (("topic",2000),("audience",500),("outcome",1000),("author",100)):
        value=raw.get(key)
        if not isinstance(value,str) or not 3<=len(value.strip())<=limit:
            raise ValueError("Enter a valid "+key)
        if any(ord(c)<32 for c in value):raise ValueError("Remove control characters")
        result[key]=value.strip()
    for key,default,minimum,maximum in (("chapter_count",8,2,20),("min_words",650,450,1800)):
        value=raw.get(key,default)
        if type(value) is not int or not minimum<=value<=maximum:raise ValueError("Choose a valid "+key)
        result[key]=value
    result["mode"]=raw.get("mode","automatic")
    if result["mode"] not in {"automatic","manual"}:raise ValueError("Choose automatic or manual mode")
    result["title"]=result["topic"][:180];result["theme"]="wellness"
    return result


def policies():
    deadline=text.timeout()+30
    common={code:("retry",) for code in ("TIMEOUT","WORKER_EXITED","LOCAL_UNAVAILABLE")}
    common.update({"INVALID_RESPONSE":("complete_json",),"INCOMPLETE_RESPONSE":("complete_json",),
                   "REPETITION_LOOP":("vary_sampling",),"VALIDATION_FAILED":("correct_structure",)})
    chapters={**common,"CONTENT_QUALITY":("rewrite_clear_chapter",),"SHORT_CHAPTER":("expand_saved_chapter",),
              "MODEL_ARTIFACT":("rewrite_plain_prose",)}
    reviews={**common,"EDITORIAL_FINDINGS":("apply_editorial_feedback",),
        "SHORT_CHAPTER":("expand_editorial_revision",),"CONTENT_QUALITY":("apply_editorial_feedback",),
        "MODEL_ARTIFACT":("apply_editorial_feedback",)}
    return {"titles":Policy("titles-1",text.titles_handler,text.titles_valid,common,timeout=deadline,retry_delay=5),
        "outline":Policy("outline-1",text.outline_handler,text.outline_valid,common,timeout=deadline,retry_delay=5),
        "writing":Policy("writing-4",text.chapter_handler,text.chapter_valid,chapters,timeout=deadline,retry_delay=5),
        "editorial":Policy("editorial-4",text.review_handler,text.review_valid,reviews,timeout=2*deadline,retry_delay=5)}


def data(books,book):
    with books.units.transaction() as conn:
        row=conn.execute("SELECT data,sha FROM ebook_v2_topics WHERE book_id=?",(book["id"],)).fetchone()
    if row is None:raise CorruptCheckpoint("Missing topic checkpoint")
    value=json.loads(row["data"])
    if digest(value)!=row["sha"]:raise CorruptCheckpoint("Topic checkpoint checksum does not match")
    return value


def save(books,book,value,state="RUNNING"):
    from .books import Conflict
    with books.units.transaction() as conn:
        count=conn.execute("UPDATE ebook_v2_books SET state=?,revision=revision+1,updated=? WHERE id=? AND owner=? AND revision=?",
            (state,time.time(),book["id"],book["owner"],book["revision"])).rowcount
        if count!=1:raise Conflict("This book has newer saved changes")
        conn.execute("UPDATE ebook_v2_topics SET data=?,sha=? WHERE book_id=?",(encode(value),digest(value),book["id"]))
    return books.get(book["owner"],book["id"])


def advance(books,book):
    owner=book["owner"];state=data(books,book);spec=book["spec"];unit_map=state["units"]
    changed=False
    def unit(name,stage,payload,parents=()):
        nonlocal changed
        if name not in unit_map:
            unit_map[name]=books.units.enqueue(owner,book["id"]+":"+name,stage,books.policies[stage].version,payload,parents)
            changed=True
            return None
        row=books.units.get(owner,unit_map[name])
        if row["state"]=="NEEDS_ATTENTION":
            save(books,book,state,"NEEDS_ATTENTION")
            return None
        if row["state"]!="COMPLETE":
            books.worker.run_once(owner,row["id"])
            return None
        return row["output"]
    def pending():
        return save(books,book,state) if changed else books.get(owner,book["id"])
    titles=unit("titles","titles",{"spec":spec})
    if titles is None:return pending()
    if "title" not in state["decisions"]:return save(books,book,state,"WAITING_TITLE")
    plan=unit("outline","outline",{"spec":spec,"title":state["decisions"]["title"]},[unit_map["titles"]])
    if plan is None:return pending()
    if spec["mode"]=="manual" and not state["decisions"].get("outline"):
        return save(books,book,state,"WAITING_OUTLINE")
    reviewed=[]
    for index in range(spec["chapter_count"]):
        name=f"chapter:{index}";review=f"review:{index}"
        chapter=unit(name,"writing",{"spec":spec,"plan":plan,"index":index},[unit_map["outline"]])
        if chapter is None:return pending()
        checked=unit(review,"editorial",{"spec":spec,"chapter":chapter["chapter"]},[unit_map[name]])
        if checked is None:return pending()
        reviewed.append(checked["chapter"])
    if "cover" not in state["decisions"]:return save(books,book,state,"WAITING_COVER")
    exported=unit("export","export",{"root":books.root,"book":{"title":state["decisions"]["title"],
        "author":spec["author"],"theme":state["decisions"]["cover"],"chapters":reviewed,"source":"local_model"}},
        [unit_map[f"review:{index}"] for index in range(spec["chapter_count"])])
    if exported is None:return pending()
    return save(books,book,state,"READY" if spec["mode"]=="automatic" else "REVIEW")


def status(books,book):
    state=data(books,book);rows={key:books.units.get(book["owner"],value) for key,value in state["units"].items()}
    def output(name):
        row=rows.get(name)
        return row["output"] if row and row["state"]=="COMPLETE" else {}
    exported=output("export");total=book["spec"]["chapter_count"]
    return {"id":book["id"],"title":state["decisions"].get("title",book["spec"]["title"]),
        "author":book["spec"]["author"],"state":("WAITING_SERVICE" if book["state"]=="RUNNING"
            and (not books.available(local_text=True)) else book["state"]),"revision":book["revision"],
        "source":"local_model","chapters_checked":sum(output(f"review:{index}")!={} for index in range(total)),
        "chapters_total":total,"integrity":exported.get("integrity"),"files":list(exported.get("files",{})),
        "titles":output("titles").get("titles",[]),"outline":output("outline").get("chapters",[]),
        "review_scope":"Local AI editorial and structural checks. External factual and plagiarism verification were not performed."}


def decide(books,owner,book_id,revision,action,value):
    from .books import Conflict
    from .publishing import THEMES
    book=books.get(owner,book_id)
    if type(revision) is not int or revision!=book["revision"]:raise Conflict("Reload the saved book")
    state=data(books,book);view=status(books,book)
    if action=="title" and book["state"]=="WAITING_TITLE" and value in view["titles"]:
        state["decisions"]["title"]=value
    elif action=="outline" and book["state"]=="WAITING_OUTLINE" and value is True:
        state["decisions"]["outline"]=True
    elif action=="cover" and book["state"]=="WAITING_COVER" and isinstance(value,str) and value in THEMES:
        state["decisions"]["cover"]=value
    else:raise ValueError("Choose a valid action for this book step")
    return save(books,book,state)


def resume(books,book):
    state=data(books,book)
    for name,key in list(state["units"].items()):
        row=books.units.get(book["owner"],key)
        if row["state"]!="NEEDS_ATTENTION":continue
        with books.units.transaction() as conn:
            parents=[r[0] for r in conn.execute("SELECT parent_id FROM ebook_v2_dependencies WHERE unit_id=?",(key,))]
        state["units"][name]=books.units.enqueue(book["owner"],book["id"]+f":resume:{book['revision']}:{name}",
            row["stage"],books.policies[row["stage"]].version,row["payload"],parents)
        if row["output"] is not None and row["stage"] in {"writing","editorial"}:
            code,repair=row["error"],row["repair"]
            chapter=row["output"].get("chapter")
            if row["stage"]=="writing" and isinstance(chapter,dict) and isinstance(chapter.get("text"),str):
                if 0<len(chapter["text"].split())<book["spec"]["min_words"]:code,repair="SHORT_CHAPTER","expand_saved_chapter"
            if repair in books.policies[row["stage"]].repairs.get(code,()):
                books.units.seed_recovery(book["owner"],state["units"][name],key,code,repair)
    return save(books,book,state)
