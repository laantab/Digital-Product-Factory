"""Saved supplied-text books above independently recoverable work units."""
import json
from pathlib import Path
import time
import uuid
from .recovery import Store,digest,encode,InputConflict,CorruptCheckpoint
from .worker import Worker,Policy
from .publishing import (THEMES,clean_chapter,chapter_handler,chapter_valid,
                         export_handler,export_valid,verified_file)


class Conflict(ValueError):
    pass


def clean_spec(raw):
    if not isinstance(raw,dict):raise ValueError("Enter book settings")
    if raw.get("source")=="ollama":
        from .topics import clean_spec as clean_topic
        return clean_topic(raw)
    if raw.get("source") not in {None,"manuscript"}:raise ValueError("Choose an available text source")
    result={}
    if "require_photos" in raw:
        if type(raw["require_photos"]) is not bool:raise ValueError("Choose whether to include photographs")
        result["require_photos"]=raw["require_photos"]
    for key,limit in (("title",180),("author",100)):
        value=raw.get(key)
        if not isinstance(value,str) or not 1<=len(value.strip())<=limit:
            raise ValueError("Enter a valid "+key)
        if any(ord(ch)<32 for ch in value):raise ValueError("Remove control characters")
        result[key]=value.strip()
    result["theme"]=raw.get("theme","wellness")
    if result["theme"] not in THEMES:raise ValueError("Choose an available design")
    chapters=raw.get("chapters")
    if not isinstance(chapters,list) or not 2<=len(chapters)<=20:
        raise ValueError("Supply two to twenty chapters")
    result["chapters"]=[clean_chapter(ch) for ch in chapters]
    if len(encode(result).encode())>900_000:raise ValueError("Manuscript is too large")
    titles=[ch["title"].casefold() for ch in result["chapters"]]
    if len(titles)!=len(set(titles)):raise ValueError("Give each chapter a distinct title")
    return result


class Books:
    def __init__(self,database,objects,policies=None):
        self.units=Store(database);self.root=str(Path(objects).resolve())
        self.policies=policies or {
            "chapter":Policy("supplied-1",chapter_handler,chapter_valid,timeout=20),
            "export":Policy("pdf-zip-5",export_handler,export_valid,
                {"TIMEOUT":("rebuild",),"WORKER_EXITED":("rebuild",),
                 "VALIDATION_FAILED":("rebuild",)},timeout=120,retry_delay=1)}
        if policies is None:
            from .topics import policies as topic_policies
            self.policies.update(topic_policies())
        if policies is None:
            from .visuals import handler,valid
            self.policies['visuals']=Policy('stock-2',handler,valid,
                {'TIMEOUT':('rebuild',),'WORKER_EXITED':('rebuild',),'VALIDATION_FAILED':('rebuild',)},timeout=120,retry_delay=1)
        self.worker=Worker(self.units,self.policies)

    def initialize(self):
        self.units.initialize()
        with self.units.transaction() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS ebook_v2_books (
                id TEXT PRIMARY KEY,owner TEXT NOT NULL,request_key TEXT NOT NULL,
                spec TEXT NOT NULL,spec_sha TEXT NOT NULL,units TEXT NOT NULL,
                state TEXT NOT NULL,revision INTEGER NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,
                UNIQUE(owner,request_key))""")
            conn.execute("CREATE TABLE IF NOT EXISTS ebook_v2_workers (id TEXT PRIMARY KEY,seen REAL NOT NULL)")
            if "local_text" not in {r[1] for r in conn.execute("PRAGMA table_info(ebook_v2_workers)")}:
                conn.execute("ALTER TABLE ebook_v2_workers ADD COLUMN local_text INTEGER NOT NULL DEFAULT 0")
            conn.execute("CREATE TABLE IF NOT EXISTS ebook_v2_topics (book_id TEXT PRIMARY KEY REFERENCES ebook_v2_books(id),data TEXT NOT NULL,sha TEXT NOT NULL)")

            conn.execute("""CREATE TABLE IF NOT EXISTS ebook_v2_editions (
                book_id TEXT PRIMARY KEY REFERENCES ebook_v2_books(id),
                parent_id TEXT NOT NULL REFERENCES ebook_v2_books(id),
                root_id TEXT NOT NULL REFERENCES ebook_v2_books(id),
                number INTEGER NOT NULL,created REAL NOT NULL,UNIQUE(root_id,number))""")

    def record_worker(self,worker_id,local_text=False):
        with self.units.transaction() as conn:
            conn.execute("INSERT INTO ebook_v2_workers (id,seen,local_text) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET seen=excluded.seen,local_text=excluded.local_text",
                         (worker_id,time.time(),int(bool(local_text))))

    def available(self,local_text=False):
        with self.units.transaction() as conn:
            return conn.execute("SELECT 1 FROM ebook_v2_workers WHERE seen>? AND (local_text=1 OR ?=0) LIMIT 1",
                                (time.time()-20,int(bool(local_text)))).fetchone() is not None

    @staticmethod
    def checked(row):
        if row is None:raise LookupError("Book not found")
        result=dict(row);result["spec"]=json.loads(result["spec"]);result["units"]=json.loads(result["units"])
        if digest(result["spec"])!=result["spec_sha"]:
            raise CorruptCheckpoint("Saved manuscript checksum does not match")
        return result

    def get(self,owner,book_id):
        with self.units.transaction() as conn:
            return self.checked(conn.execute("SELECT * FROM ebook_v2_books WHERE id=? AND owner=?",
                                             (book_id,str(owner))).fetchone())

    def listing(self,owner):
        with self.units.transaction() as conn:
            rows=conn.execute("""SELECT b.id,b.state,b.revision,b.created,b.updated,
                coalesce(json_extract(t.data,'$.decisions.title'),json_extract(b.spec,'$.title')) AS title
                FROM ebook_v2_books b LEFT JOIN ebook_v2_topics t ON t.book_id=b.id
                WHERE b.owner=? ORDER BY b.updated DESC LIMIT 30""",(str(owner),)).fetchall()
        return [dict(row) for row in rows]

    def create(self,owner,key,raw):
        if not isinstance(key,str) or not 8<=len(key)<=100:raise ValueError("Use a valid request key")
        spec=clean_spec(raw)
        with self.units.transaction() as conn:
            prior=conn.execute("SELECT * FROM ebook_v2_books WHERE owner=? AND request_key=?",(str(owner),key)).fetchone()
            if prior:
                prior=self.checked(prior)
                if prior["spec_sha"]!=digest(spec):raise InputConflict("Request key already used with different settings")
                return prior
            book_id=uuid.uuid4().hex;now=time.time()
            conn.execute("INSERT INTO ebook_v2_books VALUES (?,?,?,?,?,?,'RUNNING',1,?,?)",
                (book_id,str(owner),key,encode(spec),digest(spec),"[]",now,now))
            if spec.get("source")=="ollama":
                initial={"units":{},"decisions":{}}
                conn.execute("INSERT INTO ebook_v2_topics VALUES (?,?,?)",(book_id,encode(initial),digest(initial)))
        # The dispatcher creates missing units after a crash here, too.
        return self.get(owner,book_id)

    def save(self,book,*,units=None,state=None):
        with self.units.transaction() as conn:
            count=conn.execute("""UPDATE ebook_v2_books SET units=?,state=?,revision=revision+1,updated=?
                WHERE owner=? AND id=? AND revision=?""",(encode(units if units is not None else book["units"]),
                state or book["state"],time.time(),book["owner"],book["id"],book["revision"])).rowcount
            if count!=1:raise Conflict("This book has newer saved changes")
        return self.get(book["owner"],book["id"])

    def pending(self):
        with self.units.transaction() as conn:
            return [dict(r) for r in conn.execute("SELECT id,owner,json_extract(spec,'$.source') AS source FROM ebook_v2_books WHERE state='RUNNING'")]

    def advance(self,owner,book_id):
        book=self.get(owner,book_id)
        if book["state"]!="RUNNING":return book
        if book["spec"].get("source")=="ollama":
            from .topics import advance
            return advance(self,book)
        expected=len(book["spec"]["chapters"])
        if len(book["units"])<expected:
            units=[]
            for index,chapter in enumerate(book["spec"]["chapters"]):
                units.append(self.units.enqueue(owner,book_id+f":chapter:{index}","chapter",
                    self.policies["chapter"].version,{"chapter":chapter}))
            return self.save(book,units=units)
        outputs=[]
        for unit_id in book["units"]:
            unit=self.units.get(owner,unit_id)
            if unit["state"]=="NEEDS_ATTENTION":return self.save(book,state="NEEDS_ATTENTION")
            if unit["state"]!="COMPLETE":
                self.worker.run_once(owner,unit_id)
                return self.get(owner,book_id)
            outputs.append(unit["output"])
        if len(outputs)==expected:
            visual=self.units.enqueue(owner,book_id+":visuals","visuals",self.policies["visuals"].version,
                {"root":self.root,"book":{**book["spec"],"chapters":[o["chapter"] for o in outputs]}},parents=book["units"])
            return self.save(book,units=book["units"]+[visual])
        if len(outputs)==expected+1:
            export=self.units.enqueue(owner,book_id+":export","export",self.policies["export"].version,
                {"root":self.root,"book":{**book["spec"],"chapters":[o["chapter"] for o in outputs[:expected]],
                    "visuals":outputs[expected]["visuals"]}},
                parents=book["units"])
            return self.save(book,units=book["units"]+[export])
        return self.save(book,state="REVIEW")

    def status(self,owner,book_id):
        book=self.get(owner,book_id)
        if book["spec"].get("source")=="ollama":
            from .topics import status
            return status(self,book)
        units=[self.units.get(owner,key) for key in book["units"]]
        total=len(book["spec"]["chapters"])
        exported=units[-1]["output"] if units and units[-1]["stage"]=="export" and units[-1]["state"]=="COMPLETE" else None
        return {"id":book_id,"title":book["spec"]["title"],"author":book["spec"]["author"],
            "state":("WAITING_SERVICE" if book["state"]=="RUNNING" and not self.available() else book["state"]),"revision":book["revision"],
            "chapters_checked":sum(unit["state"]=="COMPLETE" for unit in units[:total]),
            "chapters_total":total,"integrity":exported["integrity"] if exported else None,
            "page_quality":exported.get("page_quality") if exported else None,
            "attention":("The requested photographs could not be completed. Your chapters are saved. Continue after picture search is available."
                         if any(u.get("error")=="MISSING_PHOTOS" and u["state"]=="NEEDS_ATTENTION" for u in units) else ""),
            "review_scope":"Author-supplied text: structural checks; editorial and page review required.",
            "files":list(exported["files"]) if exported else []}

    def approve(self,owner,book_id,revision):
        book=self.get(owner,book_id)
        if type(revision) is not int or revision!=book["revision"]:raise Conflict("Reload the saved book")
        if book["state"]!="REVIEW":raise ValueError("Book is not ready for review")
        if book["spec"].get("source")=="ollama":
            from .topics import data
            export_id=data(self,book)["units"]["export"]
        else:export_id=book["units"][-1]
        output=self.units.get(owner,export_id)["output"]
        if not export_valid(output):raise ValueError("An edition file failed verification")
        return self.save(book,state="READY")

    def resume(self,owner,book_id,revision):
        book=self.get(owner,book_id)
        if type(revision) is not int or revision!=book["revision"]:raise Conflict("Reload the saved book")
        if book["state"]!="NEEDS_ATTENTION":raise ValueError("Book does not need manual recovery")
        if book["spec"].get("source")=="ollama":
            from .topics import resume
            return resume(self,book)
        replacements=[]
        for index,key in enumerate(book["units"]):
            unit=self.units.get(owner,key)
            if unit["state"]=="NEEDS_ATTENTION":
                policy=self.policies[unit["stage"]]
                payload=dict(unit["payload"])
                if unit["stage"]=="visuals" and unit["error"]=="MISSING_PHOTOS" and unit["output"]:
                    payload["retained_visuals"]=unit["output"]["visuals"]
                key=self.units.enqueue(owner,book_id+f":resume:{revision}:{index}",unit["stage"],
                    policy.version,payload,parents=replacements if unit["stage"]=="export" else ())
            replacements.append(key)
        return self.save(book,units=replacements,state="RUNNING")

    def decide(self,owner,book_id,revision,action,value):
        if self.get(owner,book_id)["spec"].get("source")!="ollama":raise ValueError("This book uses supplied text")
        from .topics import decide
        return decide(self,owner,book_id,revision,action,value)

    def download(self,owner,book_id,name,preview=False):
        book=self.get(owner,book_id)
        if book["state"]!="READY" and not (preview and book["state"]=="REVIEW"):
            raise ValueError("Review the completed book before downloading")
        if book["spec"].get("source")=="ollama":
            from .topics import data
            export_id=data(self,book)["units"].get("export")
            if not export_id:raise ValueError("Files are not ready")
        else:export_id=book["units"][-1]
        unit=self.units.get(owner,export_id)
        if unit["state"]!="COMPLETE":raise ValueError("Files are not ready")
        output=unit["output"]
        if name not in output["files"]:raise LookupError("File not found")
        if output["root"]!=self.root:raise CorruptCheckpoint("Storage location does not match")
        return verified_file(self.root,output["files"][name]),output["files"][name]["sha256"]
