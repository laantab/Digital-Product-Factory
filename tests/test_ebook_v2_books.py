"""Actual supplied-text publishing, saved state, integrity and ownership."""
import hashlib
import io
import zipfile
import fitz
import pytest
from services.ebook_v2.books import Books,Conflict,clean_spec
from services.ebook_v2.recovery import InputConflict,CorruptCheckpoint
from services.ebook_v2.publishing import export_valid
from tests.ebook_v2_fixture import spec


@pytest.fixture
def engine(tmp_path):
    books=Books(tmp_path/"studio.sqlite",tmp_path/"objects");books.initialize();return books


def reviewed(engine):
    book=engine.create("alice","fixture-request-0001",spec())
    for _ in range(20):
        book=engine.advance("alice",book["id"])
        if book["state"]=="REVIEW":return book
    pytest.fail("Supplied manuscript did not finish")


def test_real_pdf_zip_and_editable_manuscript_agree(engine):
    book=reviewed(engine)
    pdf,checksum=engine.download("alice",book["id"],"ebook.pdf",preview=True)
    package,_=engine.download("alice",book["id"],"package.zip",preview=True)
    assert hashlib.sha256(pdf).hexdigest()==checksum
    with fitz.open(stream=pdf,filetype="pdf") as document:
        assert document.page_count>=4
        text=" ".join(" ".join(page.get_text().split()) for page in document)
        assert "ACCEPTANCE FIXTURE - NOT FOR SALE" in text
        for chapter in spec()["chapters"]:
            assert chapter["title"] in text
            assert chapter["text"].split(".")[0] in text
        for page in document:
            assert page.get_text().strip()
            page.get_pixmap()
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        assert archive.testzip() is None
        assert archive.read("ebook.pdf")==pdf
        assert b"## Choose one clear working area" in archive.read("manuscript.md")
    with pytest.raises(ValueError):engine.download("alice",book["id"],"package.zip")
    book=engine.approve("alice",book["id"],book["revision"])
    assert book["state"]=="READY"
    assert engine.download("alice",book["id"],"ebook.pdf")[0]==pdf


def test_reopen_uses_completed_chapters_and_immutable_export(engine):
    book=reviewed(engine)
    ids=list(book["units"])
    engine.approve("alice",book["id"],book["revision"])
    pdf=engine.download("alice",book["id"],"ebook.pdf")[0]
    restarted=Books(engine.units.path,engine.root)
    assert restarted.get("alice",book["id"])["units"]==ids
    assert restarted.advance("alice",book["id"])["state"]=="READY"
    assert restarted.download("alice",book["id"],"ebook.pdf")[0]==pdf
    assert all(restarted.units.get("alice",key)["attempts"]==1 for key in ids)


def test_creation_idempotency_and_owner_isolation(engine):
    first=engine.create("alice","fixture-request-0001",spec())
    assert engine.create("alice","fixture-request-0001",spec())["id"]==first["id"]
    changed=spec();changed["title"]="Changed title"
    with pytest.raises(InputConflict):engine.create("alice","fixture-request-0001",changed)
    with pytest.raises(LookupError):engine.get("bob",first["id"])
    assert engine.listing("bob")==[]
    assert engine.listing("alice")[0]["title"]==spec()["title"]


def test_status_get_does_not_advance_work(engine):
    book=engine.create("alice","fixture-request-0001",spec())
    before=engine.get("alice",book["id"])
    for _ in range(3):engine.status("alice",book["id"])
    assert engine.get("alice",book["id"])==before


def test_stale_decision_cannot_approve_newer_revision(engine):
    book=reviewed(engine)
    with pytest.raises(Conflict):engine.approve("alice",book["id"],book["revision"]-1)
    with pytest.raises(Conflict):engine.approve("alice",book["id"],True)
    assert engine.get("alice",book["id"])["state"]=="REVIEW"


def test_optimistic_book_updates_preserve_newer_work(engine):
    book=engine.create("alice","fixture-request-0001",spec())
    engine.advance("alice",book["id"])
    with pytest.raises(Conflict):engine.save(book,state="READY")
    assert engine.get("alice",book["id"])["state"]=="RUNNING"


def test_corrupt_file_is_never_downloaded_or_approved(engine):
    from pathlib import Path
    book=reviewed(engine)
    result=engine.units.get("alice",book["units"][-1])["output"]
    path=Path(engine.root)/result["files"]["ebook.pdf"]["key"]
    path.write_bytes(b"damaged by deliberate failure-injection test")
    assert not export_valid(result)
    with pytest.raises(ValueError):engine.approve("alice",book["id"],book["revision"])
    assert engine.get("alice",book["id"])["state"]=="REVIEW"


def test_saved_manuscript_checksum_mismatch_stops_work(engine):
    book=engine.create("alice","fixture-request-0001",spec())
    with engine.units.transaction() as conn:
        conn.execute("UPDATE ebook_v2_books SET spec='{}' WHERE id=?",(book["id"],))
    with pytest.raises(CorruptCheckpoint):engine.advance("alice",book["id"])


@pytest.mark.parametrize("change",["short","duplicate","placeholder","wrong-theme"])
def test_bad_supplied_input_does_not_create_a_failed_book(engine,change):
    raw=spec()
    if change=="short":raw["chapters"][0]["text"]="Too short"
    if change=="duplicate":raw["chapters"][1]["title"]=raw["chapters"][0]["title"]
    if change=="placeholder":raw["chapters"][0]["text"]+="\n\n[placeholder image]"
    if change=="wrong-theme":raw["theme"]="unknown"
    with pytest.raises(ValueError):engine.create("alice","fixture-request-0001",raw)
    assert engine.listing("alice")==[]
