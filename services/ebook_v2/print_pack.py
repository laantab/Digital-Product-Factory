"""Measured 6x9 white-paper black-and-white paperback preparation.

This implementation supports 24–150 interior pages. This is our supported
layout range, not Amazon's maximum. The owner must check KDP Previewer/proofs.
"""
import io
import json
import zipfile


def render(book,interior,cover):
    import fitz
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor
    from reportlab.lib.utils import ImageReader
    from .publishing import THEMES
    with fitz.open(stream=interior,filetype='pdf') as document:
        pages=document.page_count
        if pages<24 or pages>150:return None
        if pages%2:document.new_page(width=432,height=648)
        pages=document.page_count
        interior=document.tobytes(garbage=4,deflate=True)
    spine=pages*.002252
    width=(12+.25+spine)*72;height=9.25*72
    output=io.BytesIO()
    c=canvas.Canvas(output,pagesize=(width,height))
    accent,paper=THEMES[book['theme']]
    c.setTitle(book['title']);c.setAuthor(book['author'])
    c.setFillColor(HexColor(paper));c.rect(0,0,width,height,fill=1,stroke=0)
    # Front trim begins after the back, spine and outside bleed.
    c.drawImage(ImageReader(io.BytesIO(cover)),(6.125+spine)*72,9,432,648)
    c.setFillColor(HexColor(accent));c.setFont('V2Head',13)
    from reportlab.lib.utils import simpleSplit
    lines=simpleSplit(book['title'],'V2Head',13,342)
    y=height-72
    for line in lines:c.drawString(36,y,line);y-=18
    c.setFont('V2Body',11);c.drawString(36,y-18,book['author'])
    # Leave barcode placement clear; KDP supplies the actual barcode.
    c.setFillColorRGB(1,1,1);c.rect(279,27,144,86.4,fill=1,stroke=0)
    c.showPage();c.save()
    wrap=output.getvalue()
    report={'trim_inches':[6,9],'interior_pages':pages,'paper':'white',
        'interior':'black_and_white','bleed_inches':.125,'spine_inches':spine,
        'cover_inches':[width/72,height/72],'spine_text':False,
        'barcode_area_inches':[2,1.2],'approval':'KDP Previewer and owner proof required'}
    inspect(interior,wrap,report)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('print-interior.pdf',interior)
        archive.writestr('print-cover.pdf',wrap)
        archive.writestr('print-specification.json',json.dumps(report,indent=2))
        archive.writestr('READ-ME.txt',
            'Paperback preparation for 6 x 9 inches, white paper, black-and-white interior.\n'
            'Select no bleed for the interior. The separate full-wrap cover includes 0.125 inch outside bleed.\n'
            'No spine text or ISBN/barcode has been invented. KDP supplies its barcode in the reserved area.\n'
            'Use the measured page count and paper selection shown in print-specification.json.\n'
            'Check KDP Previewer and order a physical proof before publishing. This pack is not Amazon approval.\n')
    return out.getvalue(),report


def inspect(interior,wrap,report):
    import fitz
    pages=report['interior_pages']
    if not 24<=pages<=150 or pages%2:raise ValueError('Unsupported print page count')
    with fitz.open(stream=interior,filetype='pdf') as document:
        if len(document)!=pages:raise ValueError('Print count disagrees')
        for index,page in enumerate(document):
            if abs(page.rect.width-432)>.01 or abs(page.rect.height-648)>.01:
                raise ValueError('Incorrect interior trim')
            if not page.get_text().strip() and index!=pages-1:raise ValueError('Unexpected blank interior page')
            page.get_pixmap(matrix=fitz.Matrix(.3,.3),alpha=False)
    expected=(12.25+pages*.002252)*72
    with fitz.open(stream=wrap,filetype='pdf') as document:
        if len(document)!=1 or abs(document[0].rect.width-expected)>.01 or abs(document[0].rect.height-666)>.01:
            raise ValueError('Incorrect wrap geometry')
        document[0].get_pixmap(matrix=fitz.Matrix(.5,.5),alpha=False)
    return True


def inspect_package(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip():raise ValueError('Invalid print package')
        return inspect(archive.read('print-interior.pdf'),archive.read('print-cover.pdf'),
            json.loads(archive.read('print-specification.json')))
