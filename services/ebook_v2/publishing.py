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
          "practical":("#704126","#f7efe4"),
          "modern":("#28314a","#f0f2fa"), "classic":("#593545","#f8f1ec"),
          "workbook":("#245968","#edf6f5")}


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


def render_pdf(book,print_mode=False,root=None,only_cover=False):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (BaseDocTemplate,PageTemplate,Frame,Paragraph,Spacer,PageBreak,Image,KeepTogether)
    from reportlab.platypus.tableofcontents import TableOfContents
    fonts = Path(__file__).resolve().parents[1]/"fonts"
    for name,filename in (("V2Body","LiberationSerif-Regular.ttf"),
                          ("V2Head","LiberationSans-Bold.ttf"),("V2Sans","LiberationSans-Regular.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name,str(fonts/filename)))
    accent,paper = THEMES[book["theme"]]
    accent,paper = colors.HexColor(accent),colors.HexColor(paper)
    if print_mode:accent,paper=colors.black,colors.white
    body = ParagraphStyle("body",fontName="V2Sans" if book["theme"] in ("practical","modern","workbook") else "V2Body",fontSize=11,leading=17 if book["theme"]=="workbook" else 15,spaceAfter=14 if book["theme"]=="workbook" else 9,
                          textColor=colors.black if print_mode else colors.HexColor("#24332e"))
    heading = ParagraphStyle("chapter",fontName="V2Body" if book["theme"] in ("editorial","classic") else "V2Head",fontSize=20,leading=25,
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
            if book["theme"]=="modern":
                canvas.setFillColor(accent);canvas.rect(0,0,18,648,fill=1,stroke=0)
            elif book["theme"]=="classic":
                canvas.rect(25,25,382,598,fill=0,stroke=1)
            elif book["theme"]=="workbook":
                for y in (560,550,540):canvas.line(310,y,390,y)
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
    cover_visual=next((v for v in book.get("visuals",[]) if v.get("photo")),None)
    story=[Spacer(1,35 if print_mode or cover_visual else 105),Paragraph(escape(book["title"]),title),
           Paragraph(escape(book["author"]),body)]
    if cover_visual and not print_mode:
        from .visuals import photo_bytes
        photo=cover_visual["photo"];title_height=Paragraph(escape(book["title"]),title).wrap(348,500)[1]
        height=min(220,max(70,440-title_height));width=min(348,height*photo["width"]/photo["height"])
        height=width*photo["height"]/photo["width"]
        picture=Image(io.BytesIO(photo_bytes(root,cover_visual)),width=width,height=height)
        if book["theme"]=="editorial":
            story=[Spacer(1,35),picture,Spacer(1,18),Paragraph(escape(book["title"]),title),Paragraph(escape(book["author"]),body)]
        elif book["theme"]=="practical":
            story=[story[0],story[1],Spacer(1,18),picture,Spacer(1,12),story[2]]
        else:story.extend([Spacer(1,18),picture])
    if not only_cover:
        story.extend([PageBreak(),Paragraph("Contents",ParagraphStyle("contents-title",parent=heading))])
        toc=TableOfContents();toc.levelStyles=[ParagraphStyle("toc",parent=body,spaceBefore=10)]
        story += [toc,PageBreak()]
    for index,chapter in enumerate([] if only_cover else book["chapters"]):
        if index:story.append(PageBreak())
        story.append(Paragraph(escape(chapter["title"]),heading))
        visual=book.get("visuals",[])[index] if book.get("visuals") else None
        if visual:
            from .visuals import photo_bytes,credit
            if visual.get("photo"):
                photo=visual["photo"];data=photo_bytes(root,visual)
                if print_mode:
                    from PIL import Image as PILImage
                    with PILImage.open(io.BytesIO(data)) as source:
                        gray=io.BytesIO();source.convert("L").save(gray,"JPEG",quality=92);data=gray.getvalue()
                width=348;height=min(230,width*photo["height"]/photo["width"])
                width=height*photo["width"]/photo["height"]
                story.append(KeepTogether([Image(io.BytesIO(data),width=width,height=height),
                    Spacer(1,5),Paragraph(escape(credit(photo)),small),Spacer(1,12)]))
            elif visual.get("overview"):
                story.append(Paragraph("At a glance",ParagraphStyle("overview-title",parent=small,fontName="V2Head")))
                for point in visual["overview"]:
                    story.append(Paragraph(escape(point),small,bulletText="•"))
                story.append(Spacer(1,10))
        for paragraph in chapter["text"].split("\n\n"):
            story.append(Paragraph(escape(paragraph).replace("\n","<br/>"),body))
    photos=[v["photo"] for v in book.get("visuals",[]) if v.get("photo")]
    if photos and not only_cover:
        from .visuals import credit
        story.extend([PageBreak(),Paragraph("Photo credits",heading)])
        for photo in photos:
            story.append(Paragraph(escape(credit(photo))+"<br/>"+escape(photo["source_url"]),small))
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
    from .visuals import prepare
    book={**payload["book"]}
    if "visuals" not in book:book["visuals"]=prepare(book,payload["root"])
    pdf=render_pdf(book,root=payload["root"])
    from .final_quality import inspect as inspect_pages
    page_quality=inspect_pages(pdf,book,payload["root"])
    manuscript="# "+book["title"]+"\n\n"+book["author"]+"\n\n"+"\n\n".join(
        "## "+ch["title"]+"\n\n"+ch["text"] for ch in book["chapters"])
    from . import epub
    import fitz
    with fitz.open(stream=pdf,filetype="pdf") as document:
        cover=document[0].get_pixmap(matrix=fitz.Matrix(300/72,300/72),alpha=False).tobytes("jpeg")
    electronic=epub.render(book,cover,root=payload["root"])
    from . import manuscript as word
    editable=word.render(book,root=payload["root"]);word.inspect(editable,book)
    from . import print_pack
    paperback=print_pack.render(book,render_pdf(book,print_mode=True,root=payload["root"]),cover)
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ebook.pdf",pdf);archive.writestr("manuscript.md",manuscript)
        archive.writestr("ebook.epub",electronic);archive.writestr("cover.jpg",cover)
        archive.writestr("manuscript.docx",editable)
        archive.writestr("quality-report.json",json.dumps(page_quality,indent=2))
        archive.writestr("photo-sources.json",json.dumps([{**{key:v["photo"][key] for key in ("provider","photographer","source_url","license_url","alt","width","height")},
            "image_sha256":v["photo"]["file"]["sha256"]} for v in book["visuals"] if v.get("photo")],indent=2))
        if paperback:archive.writestr("print-pack.zip",paperback[0])
        archive.writestr("edition.json",json.dumps({"title":book["title"],"author":book["author"],
            "source":book.get("source","author_supplied"),"review_scope":("local_editorial_checks" if book.get("source")=="local_model" else "structural_checks_only"),
            "pdf_sha256":hashlib.sha256(pdf).hexdigest()},indent=2))
    package=out.getvalue();integrity=inspect(pdf,package)
    root=Path(payload["root"]).resolve();folder=root/"ebook-v2"/uuid.uuid4().hex
    folder.mkdir(parents=True,exist_ok=False)
    files={}
    contents={"ebook.pdf":pdf,"package.zip":package,"manuscript.md":manuscript.encode(),
                      "ebook.epub":electronic,"cover.jpg":cover,"manuscript.docx":editable}
    if paperback:contents["print-pack.zip"]=paperback[0]
    for name,data in contents.items():
        path=folder/name
        with path.open("xb") as stream:
            stream.write(data);stream.flush()
            import os
            os.fsync(stream.fileno())
        receipt={"key":str(path.relative_to(root)),"size":len(data),"sha256":hashlib.sha256(data).hexdigest()}
        verified_file(root,receipt);files[name]=receipt
    return {"files":files,"integrity":integrity,"page_quality":page_quality,"root":str(root),
            "print_specification":paperback[1] if paperback else None,"visuals":book["visuals"]}


def export_valid(output):
    try:
        files=output["files"];root=output["root"]
        actual=inspect(verified_file(root,files["ebook.pdf"]),verified_file(root,files["package.zip"]))
        from . import epub
        with zipfile.ZipFile(io.BytesIO(verified_file(root,files["package.zip"]))) as archive:
            for name,receipt in files.items():
                if name!="package.zip" and archive.read(name)!=verified_file(root,receipt):return False
            if "page_quality" in output:
                report=output["page_quality"]
                if (json.loads(archive.read("quality-report.json"))!=report
                        or report.get("contract")!="final-pages-1"
                        or report.get("pdf_sha256")!=actual["pdf_sha256"]
                        or report.get("pages")!=actual["pages"]
                        or report.get("source_text_present") is not True
                        or report.get("text_within_page") is not True
                        or report.get("photograph_pixels_verified") is not True
                        or report.get("photographs_expected")!=sum(bool(v.get("photo")) for v in output.get("visuals",[]))
                        or report.get("photographs_placed",-1)<report["photographs_expected"]):return False
        # Older verified editions remain downloadable without being rewritten.
        if "ebook.epub" in files:epub.inspect(verified_file(root,files["ebook.epub"]))
        if "manuscript.docx" in files:
            from . import manuscript as word
            word.inspect(verified_file(root,files["manuscript.docx"]))
        if "print-pack.zip" in files:
            from . import print_pack
            print_pack.inspect_package(verified_file(root,files["print-pack.zip"]))
        for visual in output.get("visuals",[]):
            if visual.get("photo"):verified_file(root,visual["photo"]["file"])
        return actual==output["integrity"]
    except (OSError,KeyError,ValueError,TypeError,zipfile.BadZipFile):
        return False
