"""Independent supplied-manuscript PDF/ZIP renderer and actual-byte validator."""
import hashlib
import io
import json
from pathlib import Path
import re
import uuid
import zipfile
from xml.sax.saxutils import escape

from .worker import Repairable

THEMES = {"wellness":("#285b49","#f4f0e8"), "editorial":("#243c56","#edf1f6"),
          "practical":("#704126","#f7efe4")}


def clean_chapter(chapter):
    if not isinstance(chapter,dict) or set(chapter) != {"title","text"}:
        raise ValueError("Each chapter needs a title and text")
    title, text = chapter["title"], chapter["text"]
    if (not isinstance(title,str) or not 1 <= len(title.strip()) <= 180
            or not isinstance(text,str) or not 250 <= len(text.split()) <= 8000):
        raise ValueError("Each chapter needs a title and 250 to 8000 words")
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n",text.strip()) if part.strip()]
    if len(paragraphs) < 3 or len(set(paragraphs)) != len(paragraphs):
        raise ValueError("Use developed paragraphs without duplicates")
    if re.search(r"lorem ipsum|\[placeholder|\bTODO\b|insert (?:an? )?image",text,re.I):
        raise ValueError("Remove unfinished placeholder content")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in title+text):
        raise ValueError("Remove unsupported control characters")
    return {"title":title.strip(),"text":"\n\n".join(paragraphs)}


def chapter_handler(payload, repair):
    return {"chapter":clean_chapter(payload["chapter"]),
            "review_scope":"Author-supplied text; structural checks only"}


def chapter_valid(output):
    try:
        return output["chapter"] == clean_chapter(output["chapter"])
    except (KeyError,TypeError,ValueError):
        return False


def render_pdf(book):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (BaseDocTemplate,PageTemplate,Frame,Paragraph,Spacer,PageBreak)
    from reportlab.platypus.tableofcontents import TableOfContents
    fonts = Path(__file__).resolve().parents[1]/"fonts"
    for name,filename in (("V2Body","LiberationSerif-Regular.ttf"),
                          ("V2Head","LiberationSans-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name,str(fonts/filename)))
    accent,paper = THEMES[book["theme"]]
    accent,paper = colors.HexColor(accent),colors.HexColor(paper)
    body = ParagraphStyle("body",fontName="V2Body",fontSize=11,leading=15,spaceAfter=9,
                          textColor=colors.HexColor("#24332e"))
    heading = ParagraphStyle("chapter",fontName="V2Head",fontSize=20,leading=25,
                             textColor=accent,spaceAfter=20)
    title = ParagraphStyle("cover",parent=heading,fontSize=30,leading=35,spaceAfter=22)
    small = ParagraphStyle("small",parent=body,fontSize=9,leading=12)
    out = io.BytesIO()
    class Document(BaseDocTemplate):
        def afterFlowable(self,flowable):
            if isinstance(flowable,Paragraph) and flowable.style.name == "chapter":
                self.notify("TOCEntry",(0,flowable.getPlainText(),self.page))
    def decorate(canvas,doc):
        canvas.saveState()
        if doc.page == 1:
            canvas.setFillColor(paper);canvas.rect(0,0,432,648,fill=1,stroke=0)
            canvas.setStrokeColor(accent);canvas.setLineWidth(2);canvas.line(42,598,390,598)
        else:
            canvas.setFont("V2Body",8);canvas.setFillColor(accent)
            label=book["title"]
            while pdfmetrics.stringWidth(label,"V2Body",8) > 300:
                label=label[:-2]
            canvas.drawString(42,28,label)
            canvas.drawRightString(390,28,str(doc.page))
        canvas.restoreState()
    document=Document(out,pagesize=(432,648),leftMargin=42,rightMargin=42,topMargin=44,bottomMargin=48,
                      title=book["title"],author=book["author"])
    document.addPageTemplates(PageTemplate(id="book",frames=[Frame(42,48,348,556,
        leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=decorate))
    while Paragraph(escape(book["title"]),title).wrap(348,500)[1]>350 and title.fontSize>20:
        title.fontSize-=1;title.leading-=1
    story=[Spacer(1,105),Paragraph(escape(book["title"]),title),
           Paragraph(escape(book["author"]),body),PageBreak(),Paragraph("Contents",heading)]
    # Contents does not list itself.
    story[-1]=Paragraph("Contents",ParagraphStyle("contents-title",parent=heading))
    toc=TableOfContents();toc.levelStyles=[ParagraphStyle("toc",parent=body,spaceBefore=10)]
    story += [toc,PageBreak()]
    for index,chapter in enumerate(book["chapters"]):
        if index:story.append(PageBreak())
        story.append(Paragraph(escape(chapter["title"]),heading))
        for paragraph in chapter["text"].split("\n\n"):
            story.append(Paragraph(escape(paragraph).replace("\n","<br/>"),body))
    document.multiBuild(story)
    return out.getvalue()


def inspect(pdf,package):
    import fitz
    if not pdf.startswith(b"%PDF-") or not package.startswith(b"PK"):
        raise ValueError("Invalid document signatures")
    with fitz.open(stream=pdf,filetype="pdf") as document:
        if document.page_count < 4:raise ValueError("Incomplete book")
        for page in document:
            if not page.get_text().strip():raise ValueError("Blank page")
            page.get_pixmap(matrix=fitz.Matrix(.5,.5),alpha=False)
        pages=document.page_count
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        if archive.testzip() is not None or archive.read("ebook.pdf") != pdf:
            raise ValueError("PDF and package disagree")
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("Duplicate package entries")
    return {"pages":pages,"all_pages_rendered":True,"zip_crc_ok":True,"embedded_pdf_matches":True,
            "pdf_sha256":hashlib.sha256(pdf).hexdigest(),"zip_sha256":hashlib.sha256(package).hexdigest()}


def verified_file(root,receipt):
    root=Path(root).resolve();path=(root/receipt["key"]).resolve()
    if not path.is_relative_to(root):raise ValueError("Invalid stored file")
    data=path.read_bytes()
    if len(data)!=receipt["size"] or hashlib.sha256(data).hexdigest()!=receipt["sha256"]:
        raise ValueError("Stored file checksum does not match")
    return data


def export_handler(payload,repair):
    book=payload["book"];pdf=render_pdf(book)
    manuscript="# "+book["title"]+"\n\n"+book["author"]+"\n\n"+"\n\n".join(
        "## "+ch["title"]+"\n\n"+ch["text"] for ch in book["chapters"])
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ebook.pdf",pdf);archive.writestr("manuscript.md",manuscript)
        archive.writestr("edition.json",json.dumps({"title":book["title"],"author":book["author"],
            "source":"author_supplied","review_scope":"structural_checks_only",
            "pdf_sha256":hashlib.sha256(pdf).hexdigest()},indent=2))
    package=out.getvalue();integrity=inspect(pdf,package)
    root=Path(payload["root"]).resolve();folder=root/"ebook-v2"/uuid.uuid4().hex
    folder.mkdir(parents=True,exist_ok=False)
    files={}
    for name,data in {"ebook.pdf":pdf,"package.zip":package,"manuscript.md":manuscript.encode()}.items():
        path=folder/name
        with path.open("xb") as stream:
            stream.write(data);stream.flush()
            import os
            os.fsync(stream.fileno())
        receipt={"key":str(path.relative_to(root)),"size":len(data),"sha256":hashlib.sha256(data).hexdigest()}
        verified_file(root,receipt);files[name]=receipt
    return {"files":files,"integrity":integrity,"root":str(root)}


def export_valid(output):
    try:
        files=output["files"];root=output["root"]
        actual=inspect(verified_file(root,files["ebook.pdf"]),verified_file(root,files["package.zip"]))
        verified_file(root,files["manuscript.md"])
        return actual==output["integrity"]
    except (OSError,KeyError,ValueError,TypeError,zipfile.BadZipFile):
        return False
