"""Durable topic writing: title choice, plan, individual chapters and review."""
import json
import time
from .recovery import digest,encode,CorruptCheckpoint
from .worker import Policy
from . import local_text as text


def clean_spec(raw):
    result={"source":"ollama"}
    if raw.get("research_acknowledged") is not True:
        raise ValueError("Confirm that market demand has not been assessed before starting.")
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
        "MODEL_ARTIFACT":("apply_editorial_feedback",),"EDITORIAL_RECHECK":("review_saved_revision",)}
    drafts={**chapters,"SHORT_DRAFT":("develop_saved_draft",),"SHORT_ADDITION":("expand_saved_section",)}
    return {"titles":Policy("titles-2",text.titles_handler,text.titles_valid,common,timeout=deadline,retry_delay=5),
        "outline":Policy("outline-2",text.outline_handler,text.outline_valid,common,timeout=deadline,retry_delay=5),
        "writing":Policy("writing-6",text.chapter_handler,text.chapter_valid,chapters,timeout=deadline,retry_delay=5),
        "editorial":Policy("editorial-9",text.review_handler,text.review_valid,reviews,timeout=deadline,retry_delay=5),
        "draft":Policy("draft-4",text.draft_handler,text.partial_valid,drafts,timeout=deadline,retry_delay=5),
        "expand":Policy("expand-4",text.expansion_handler,text.expansion_valid,drafts,timeout=deadline,retry_delay=5),
        "assemble":Policy("assemble-2",text.assembly_handler,text.chapter_valid,{},timeout=20,retry_delay=0)}


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
            policy=books.policies[stage].version
            fingerprint=digest({"stage":stage,"policy":policy,"payload":payload,"parents":parents})[:16]
            # Nine attempts cover two bounded review/correction/recheck cycles,
            # including retained short corrections that each need expansion.
            unit_map[name]=books.units.enqueue(owner,book["id"]+":"+name+":"+fingerprint,stage,policy,payload,parents,max_attempts=9 if stage=="editorial" else 3)
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
        existing=books.units.get(owner,unit_map[name]) if name in unit_map else None
        if existing and existing["state"]=="COMPLETE":
            chapter=existing["output"]
        else:
            draft_name=f"draft:{index}";payload={"spec":spec,"plan":plan,"index":index}
            seed_id=state.get("seeds",{}).get(name)
            if seed_id:
                saved=books.units.get(owner,seed_id)["output"] or {}
                if text.partial_valid({"chapter":saved.get("chapter")}):payload["seed"]=saved["chapter"]
            draft=unit(draft_name,"draft",payload,[unit_map["outline"]])
            if draft is None:return pending()
            parent=unit_map[draft_name]
            maximum_steps=min(32,max(6,(spec["min_words"]+59)//60))
            for step in range(maximum_steps):
                if len(draft["chapter"]["text"].split())>=spec["min_words"]:break
                expansion_name=f"expand:{index}:{step}"
                draft=unit(expansion_name,"expand",{"spec":spec,"chapter":draft["chapter"]},[parent])
                if draft is None:return pending()
                parent=unit_map[expansion_name]
            chapter=unit(name,"assemble",{"chapter":draft["chapter"],"minimum":spec["min_words"],
                         "title":plan["chapters"][index]["title"]},[parent])
        if chapter is None:return pending()
        checked=unit(review,"editorial",{"spec":spec,"chapter":chapter["chapter"]},[unit_map[name]])
        if checked is None:return pending()
        reviewed.append(checked["chapter"])
    visuals=unit("visuals","visuals",{"root":books.root,"book":{"title":state["decisions"]["title"],
        "author":spec["author"],"topic":spec["topic"],"chapters":reviewed}},[unit_map[f"review:{index}"] for index in range(spec["chapter_count"])])
    if visuals is None:return pending()
    if "cover" not in state["decisions"]:return save(books,book,state,"WAITING_COVER")
    exported=unit("export","export",{"root":books.root,"book":{"title":state["decisions"]["title"],
        "author":spec["author"],"theme":state["decisions"]["cover"],"chapters":reviewed,"source":"local_model","visuals":visuals["visuals"]}},
        [unit_map["visuals"]])
    if exported is None:return pending()
    return save(books,book,state,"READY" if spec["mode"]=="automatic" else "REVIEW")


def status(books,book):
    state=data(books,book);snapshot=books.units.outputs(book["owner"],state["units"].values())
    rows={key:snapshot[value] for key,value in state["units"].items()}
    def output(name):
        row=rows.get(name)
        return row["output"] if row and row["state"]=="COMPLETE" else {}
    exported=output("export");total=book["spec"]["chapter_count"]
    saved_words={}
    for name,row in rows.items():
        if row["state"]!="COMPLETE" or not isinstance(row["output"],dict):continue
        chapter=row["output"].get("chapter")
        if chapter and name.startswith(("draft:","expand:","chapter:","review:")):
            index=int(name.split(":")[1]);saved_words[index]=max(saved_words.get(index,0),len(chapter["text"].split()))
    labels={"titles":"Preparing title choices","outline":"Planning chapters","draft":"Drafting chapter",
        "expand":"Developing chapter","assemble":"Saving chapter","writing":"Writing chapter",
        "editorial":"Reviewing chapter","visuals":"Preparing images and cover previews","export":"Formatting files"}
    activity="Saved work is up to date"
    for name,row in rows.items():
        if row["state"] in {"RUNNING","QUEUED"}:
            activity=labels.get(row["stage"],"Preparing your book")
            if ":" in name and name.split(":")[1].isdigit():activity+=" "+str(int(name.split(":")[1])+1)
            break
    attention=""
    for row in rows.values():
        if row["state"]=="NEEDS_ATTENTION":
            if row.get("error")=="LOCAL_CAPACITY":
                attention="The local model needs more available memory. Close other heavy applications, then continue your saved work."
                activity="Waiting for local model capacity"
            else:attention="This step needs a correction. Completed chapters and drafts are preserved."
            break
    return {"attention":attention,"id":book["id"],"title":state["decisions"].get("title",book["spec"]["title"]),
        "author":book["spec"]["author"],"state":("WAITING_SERVICE" if book["state"]=="RUNNING"
            and (not books.available(local_text=True)) else book["state"]),"revision":book["revision"],
        "source":"local_model","chapters_checked":sum(output(f"review:{index}")!={} for index in range(total)),
        "chapters_total":total,"words_saved":sum(saved_words.values()),"activity":activity,
        "integrity":exported.get("integrity"),"files":list(exported.get("files",{})),
        "cover_previews":list(output("visuals").get("covers",{})),
        "photo_credits":[v["photo"] for v in output("visuals").get("visuals",[]) if v.get("photo")],
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
        if row["stage"]=="writing":
            state.setdefault("seeds",{})[name]=key
            del state["units"][name]
            continue
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
