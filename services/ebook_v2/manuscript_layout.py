"""Render common saved-manuscript Markdown without changing saved text."""
import re
from xml.sax.saxutils import escape


def inline(text):
    text = re.sub(r'^\s{0,3}#{1,6}\s+', '', text)
    text = escape(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<i>\1</i>', text)
    return text


def flowables(text, body, accent):
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    subhead = ParagraphStyle('manuscript-subhead', parent=body, fontName='V2Head',
                             fontSize=13, leading=17, spaceBefore=9,
                             spaceAfter=7, keepWithNext=True, textColor=accent)
    result = []
    for block in text.split('\n\n'):
        lines = block.splitlines()
        pending = []
        def flush():
            if pending:
                result.append(Paragraph('<br/>'.join(inline(x) for x in pending), body))
                pending.clear()
        for line in lines:
            heading = re.match(r'^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$', line)
            bullet = re.match(r'^\s*[-+*]\s+(.+)$', line)
            if heading:
                flush(); result.append(Paragraph(inline(heading.group(1)), subhead))
            elif bullet:
                flush(); result.append(Paragraph(inline(bullet.group(1)), body, bulletText='•'))
            else:
                pending.append(line)
        flush()
    return result
