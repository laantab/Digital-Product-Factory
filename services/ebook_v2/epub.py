"""Self-contained EPUB3 from the same approved chapters as the PDF.

No remote resources, executable content, inferred metadata or model calls.
"""
from datetime import datetime, timezone
import io
import uuid
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape


def document(title, body):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">'
        '<head><title>'+escape(title)+'</title><meta charset="utf-8"/>'
        '<link rel="stylesheet" type="text/css" href="book.css"/></head>'
        '<body>'+body+'</body></html>')


def render(book, cover):
    title,author=escape(book['title']),escape(book['author'])
    identifier='urn:uuid:'+str(uuid.uuid4())
    modified=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    resources={'book.css':('body { font-family: serif; line-height: 1.5; margin: 5%; } '
        'h1 { font-family: sans-serif; line-height: 1.2; } '
        'p { margin: 0 0 0.8em; } img { max-width: 100%; height: auto; }'),
        'cover.jpg':cover,
        'cover.xhtml':document(book['title'],'<section epub:type="cover"><h1>'+title+
            '</h1><p>'+author+'</p><img src="cover.jpg" alt="Book cover"/></section>')}
    items=['<item id="cover-image" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/>',
        '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="css" href="book.css" media-type="text/css"/>']
    spine=['<itemref idref="cover"/>','<itemref idref="nav"/>'];links=[]
    for index,chapter in enumerate(book['chapters'],1):
        name=f'chapter-{index}.xhtml';key=f'ch{index}'
        resources[name]=document(chapter['title'],'<section epub:type="chapter"><h1>'+
            escape(chapter['title'])+'</h1>'+''.join('<p>'+escape(p).replace('\n','<br/>')+'</p>'
                for p in chapter['text'].split('\n\n'))+'</section>')
        items.append(f'<item id="{key}" href="{name}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{key}"/>')
        links.append(f'<li><a href="{name}">'+escape(chapter['title'])+'</a></li>')
    resources['nav.xhtml']=document('Contents','<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>'+
        ''.join(links)+'</ol></nav>')
    resources['package.opf']=('<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="book-id">'+identifier+'</dc:identifier><dc:title>'+title+
        '</dc:title><dc:creator>'+author+'</dc:creator><dc:language>en</dc:language>'
        '<meta property="dcterms:modified">'+modified+'</meta></metadata><manifest>'+
        ''.join(items)+'</manifest><spine>'+''.join(spine)+'</spine></package>')
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:
        archive.writestr('mimetype',b'application/epub+zip',compress_type=zipfile.ZIP_STORED)
        archive.writestr('META-INF/container.xml','<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
            '<rootfiles><rootfile full-path="EPUB/package.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
            compress_type=zipfile.ZIP_DEFLATED)
        for name,value in resources.items():
            archive.writestr('EPUB/'+name,value,compress_type=zipfile.ZIP_DEFLATED)
    result=out.getvalue();inspect(result)
    return result


def inspect(data):
    """Runtime integrity checks; release acceptance additionally uses EPUBCheck."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=archive.namelist()
        if (len(names)!=len(set(names)) or names[0]!='mimetype'
                or archive.infolist()[0].compress_type!=zipfile.ZIP_STORED
                or archive.read('mimetype')!=b'application/epub+zip' or archive.testzip()):
            raise ValueError('Invalid EPUB container')
        for name in names:
            if name.endswith(('.xml','.opf','.xhtml')):ET.fromstring(archive.read(name))
        package=ET.fromstring(archive.read('EPUB/package.opf'))
        ns={'p':'http://www.idpf.org/2007/opf'}
        manifest={item.attrib['id']:item for item in package.findall('p:manifest/p:item',ns)}
        for item in manifest.values():
            href=item.attrib['href']
            if '/' in href or ':' in href or href.startswith('.') or 'EPUB/'+href not in names:
                raise ValueError('Missing or unsafe EPUB resource')
        for item in package.findall('p:spine/p:itemref',ns):
            if item.attrib['idref'] not in manifest:raise ValueError('Broken EPUB reading order')
    return True
