"""Editable Word manuscript with native paragraph and heading styles."""
import io


def render(book,root=None):
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.oxml.ns import qn
    document=Document()
    section=document.sections[0]
    section.page_width=Inches(6);section.page_height=Inches(9)
    section.top_margin=section.bottom_margin=Inches(.65)
    section.left_margin=section.right_margin=Inches(.65)
    for name,size,font in [('Normal',11,'Liberation Serif'),('Title',28,'Liberation Sans'),
                           ('Heading 1',20,'Liberation Sans')]:
        style=document.styles[name]
        style.font.name=font;style.font.size=Pt(size);style.font.color.rgb=RGBColor(0,0,0)
        style.paragraph_format.space_after=Pt(10)
        for border in list(style.element.iter(qn('w:pBdr'))):border.getparent().remove(border)
    normal=document.styles['Normal'].paragraph_format
    normal.line_spacing=1.25;normal.widow_control=True
    document.styles['Heading 1'].paragraph_format.keep_with_next=True
    for style in document.styles:
        for border in list(style.element.iter(qn('w:pBdr'))):border.getparent().remove(border)
    document.core_properties.title=book['title']
    document.core_properties.author=book['author']
    document.core_properties.last_modified_by=''
    document.add_paragraph(book['title'],'Title')
    document.add_paragraph(book['author'])
    document.add_page_break()
    caption=document.styles['Caption'];caption.font.color.rgb=RGBColor(0,0,0)
    caption.font.name='Liberation Serif';caption.font.size=Pt(9);caption.font.bold=False;caption.font.italic=False
    caption.paragraph_format.line_spacing=1.1;caption.paragraph_format.space_after=Pt(8)
    for index,chapter in enumerate(book['chapters']):
        if index:document.add_page_break()
        document.add_paragraph(chapter['title'],'Heading 1')
        visual=book.get('visuals',[])[index] if book.get('visuals') else None
        if visual and visual.get('photo'):
            from .visuals import photo_bytes,credit
            picture=document.add_picture(io.BytesIO(photo_bytes(root,visual)),width=Inches(4.7))
            picture._inline.docPr.set('descr',visual['photo']['alt'])
            document.add_paragraph(credit(visual['photo'])+' — '+visual['photo']['source_url'],'Caption')
        for paragraph in chapter['text'].split('\n\n'):document.add_paragraph(paragraph)
    out=io.BytesIO();document.save(out)
    return out.getvalue()


def inspect(data,book=None):
    from docx import Document
    document=Document(io.BytesIO(data))
    paragraphs=[p for p in document.paragraphs if p.text and p.style.name!='Caption']
    if not paragraphs or paragraphs[0].style.name!='Title':raise ValueError('Missing manuscript title')
    if book:
        expected=[book['title'],book['author']]
        for chapter in book['chapters']:
            expected.extend([chapter['title'],*chapter['text'].split('\n\n')])
        if [p.text for p in paragraphs]!=expected:raise ValueError('Manuscript content changed')
        headings=[p.text for p in paragraphs if p.style.name=='Heading 1']
        if headings!=[c['title'] for c in book['chapters']]:raise ValueError('Missing editable chapter headings')
    return True
