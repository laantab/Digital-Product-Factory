"""Mechanical checks of final customer pages, never a designer certification."""
import io
import hashlib
import re

import fitz
from PIL import Image


def normalized(value):
    return ''.join(re.findall(r'\w+', value)).casefold()


def inspect(pdf, book, root):
    """Reject lost prose, clipped text and missing or undersized promised images.

    Compare against source chapters, not a model's own claim that it passed.
    Human judgments of relevance, usefulness and visual design remain separate.
    """
    with fitz.open(stream=pdf, filetype='pdf') as document:
        # Exclude the running footer so a paragraph continuing on the next
        # page is compared as prose, without a title/page number inserted.
        text = normalized('\n'.join(p.get_text(clip=fitz.Rect(0,0,p.rect.width,p.rect.height-42)) for p in document))
        for page in document:
            image_rects=[fitz.Rect(i['bbox']) for i in page.get_image_info()] if page.number>=2 else []
            if abs(page.rect.width-432) > .5 or abs(page.rect.height-648) > .5:
                raise ValueError('Final pages have inconsistent book dimensions')
            for block in page.get_text('dict')['blocks']:
                if block['type'] != 0:
                    continue
                for line in block['lines']:
                    for span in line['spans']:
                        if not span['text'].strip():
                            continue
                        x0, y0, x1, y1 = span['bbox']
                        if x0 < 12 or y0 < 12 or x1 > page.rect.width-12 or y1 > page.rect.height-12:
                            raise ValueError('Final pages contain clipped text or unsafe edge placement')
                        if span['size'] < 7:
                            raise ValueError('Final pages contain unreadably small text')
                        if '\ufffd' in span['text']:
                            raise ValueError('Final pages contain missing characters')
                        if any((fitz.Rect(span['bbox']) & rect).get_area()>1 for rect in image_rects):
                            raise ValueError('Final pages contain text overlapping a photograph')
        for chapter in book['chapters']:
            if normalized(chapter['title']) not in text:
                raise ValueError('Final pages are missing a chapter title')
            for paragraph in chapter['text'].split('\n\n'):
                if normalized(paragraph) not in text:
                    raise ValueError('Final pages are missing manuscript text')
        # Count actual placed raster images on chapter pages, excluding both
        # cover and contents. A resource present but never drawn does not count.
        placed = []
        for page in list(document)[2:]:
            placed.extend(page.get_image_info(hashes=True))
        expected = [v['photo'] for v in book.get('visuals', []) if v.get('photo')]
        if book.get('require_photos') and len({p['file']['sha256'] for p in expected}) < min(4, len(book['chapters'])):
            raise ValueError('The requested distinct photographs are not complete')
        if len(placed) < len(expected):
            raise ValueError('Final chapter pages are missing promised photographs')
        # Compare decoded pixels; JPEG compression metadata is not a picture's
        # identity, and identical photos reused in chapters still count per use.
        remaining = list(placed)
        for photo in expected:
            from .publishing import verified_file
            data = verified_file(root, photo['file'])
            with Image.open(io.BytesIO(data)) as image:
                if image.width < 1500 or image.height < 900:
                    raise ValueError('A chapter photograph has insufficient resolution')
            pix = fitz.Pixmap(data)
            match = next((i for i, actual in enumerate(remaining) if actual['digest'] == pix.digest), None)
            if match is None:
                raise ValueError('Final chapter pages contain a different photograph')
            actual = remaining.pop(match)
            rect = fitz.Rect(actual['bbox'])
            if rect.x0 < 24 or rect.y0 < 24 or rect.x1 > 408 or rect.y1 > 612:
                raise ValueError('A chapter photograph extends outside the page margins')
            if rect.width <= 0 or rect.height <= 0 or min(actual['width']/(rect.width/72), actual['height']/(rect.height/72)) < 300:
                raise ValueError('A chapter photograph is too low resolution at its placed size')
        return {'contract': 'final-pages-1', 'pdf_sha256': hashlib.sha256(pdf).hexdigest(), 'pages': len(document),
                'source_text_present': True, 'text_within_page': True,
                'photographs_expected': len(expected), 'photographs_placed': len(placed),
                'photograph_pixels_verified': True,
                'designer_review': 'not_certified_by_mechanical_checks'}
