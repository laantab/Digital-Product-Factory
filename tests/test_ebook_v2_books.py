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


def test_epub_reading_order_text_cover_and_package_identity(engine):
    from xml.etree import ElementTree as ET
    from services.ebook_v2 import epub
    book=reviewed(engine)
    data,_=engine.download("alice",book["id"],"ebook.epub",preview=True)
    assert epub.inspect(data)
    package,_=engine.download("alice",book["id"],"package.zip",preview=True)
    cover,_=engine.download("alice",book["id"],"cover.jpg",preview=True)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        assert archive.read("ebook.epub")==data
        assert archive.read("cover.jpg")==cover
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.read("EPUB/cover.jpg")==cover
        for index,chapter in enumerate(spec()["chapters"],1):
            root=ET.fromstring(archive.read(f"EPUB/chapter-{index}.xhtml"))
            ns={"h":"http://www.w3.org/1999/xhtml"}
            assert root.find("h:body/h:section/h:h1",ns).text==chapter["title"]
            assert [p.text for p in root.findall("h:body/h:section/h:p",ns)]==chapter["text"].split("\n\n")


def test_epub_in_package_cannot_diverge_from_standalone(engine):
    from pathlib import Path
    book=reviewed(engine)
    output=engine.units.get("alice",book["units"][-1])["output"]
    path=Path(engine.root)/output["files"]["ebook.epub"]["key"]
    path.write_bytes(b"deliberate corruption")
    assert not export_valid(output)
    with pytest.raises(ValueError):engine.approve("alice",book["id"],book["revision"])


def test_word_manuscript_is_editable_and_preserves_approved_text(engine):
    from services.ebook_v2 import manuscript
    book=reviewed(engine)
    data,_=engine.download("alice",book["id"],"manuscript.docx",preview=True)
    assert manuscript.inspect(data,spec())
    package,_=engine.download("alice",book["id"],"package.zip",preview=True)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:assert archive.read("manuscript.docx")==data
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert b"pBdr" not in archive.read("word/styles.xml")


def test_edit_creates_new_reviewable_edition_and_preserves_original_downloads(engine):
    from services.ebook_v2.editions import editable,edit,history
    original=reviewed(engine);original=engine.approve("alice",original["id"],original["revision"])
    original_pdf=engine.download("alice",original["id"],"ebook.pdf")[0]
    saved=editable(engine,"alice",original["id"])
    revised=saved["spec"];revised["title"]="Revised desk organization guide"
    revised["chapters"][0]["text"]+="\n\nThis new author edit must appear only in the revised edition."
    book=edit(engine,"alice",original["id"],saved["revision"],"edit-request-0001",revised)
    assert edit(engine,"alice",original["id"],saved["revision"],"edit-request-0001",revised)["id"]==book["id"]
    assert engine.get("alice",original["id"])["spec"]==spec()
    assert engine.download("alice",original["id"],"ebook.pdf")[0]==original_pdf
    for _ in range(20):
        book=engine.advance("alice",book["id"])
        if book["state"]=="REVIEW":break
    assert book["state"]=="REVIEW"
    new_pdf=engine.download("alice",book["id"],"ebook.pdf",preview=True)[0]
    with fitz.open(stream=new_pdf,filetype="pdf") as document:
        assert "This new author edit" in " ".join(page.get_text() for page in document)
    assert new_pdf!=original_pdf
    assert [row["number"] for row in history(engine,"alice",book["id"])]==[1,2]
    with pytest.raises(LookupError):editable(engine,"bob",original["id"])
    with pytest.raises(Conflict):edit(engine,"alice",original["id"],saved["revision"],"edit-request-0002",revised)
    altered=dict(revised,title="Different payload")
    with pytest.raises(InputConflict):edit(engine,"alice",original["id"],saved["revision"],"edit-request-0001",altered)
    restarted=Books(engine.units.path,engine.root)
    assert len(history(restarted,"alice",book["id"]))==2
    assert restarted.download("alice",original["id"],"ebook.pdf")[0]==original_pdf
