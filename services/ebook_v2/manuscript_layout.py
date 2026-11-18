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
    from reportlab.platypus import Paragraph, Table, TableStyle
    subhead = ParagraphStyle('manuscript-subhead', parent=body, fontName='V2Head',
                             fontSize=13, leading=17, spaceBefore=9,
                             spaceAfter=7, keepWithNext=True, textColor=accent)
    result = []
    for block in text.split('\n\n'):
        lines = block.splitlines()
        if (len(lines) >= 2 and all(line.strip().startswith('|') for line in lines)
                and '-' in lines[1] and re.fullmatch(r'[\s|:-]+', lines[1])):
            cells = [[cell.strip() for cell in line.strip().strip('|').split('|')]
                     for index, line in enumerate(lines) if index != 1]
            columns = len(cells[0])
            if columns >= 2 and all(len(row) == columns for row in cells):
                table_body = ParagraphStyle('table-body', parent=body, fontSize=9, leading=12, spaceAfter=0)
                table_head = ParagraphStyle('table-head', parent=table_body, fontName='V2Head')
                rows = [[Paragraph(inline(cell), table_head if index == 0 else table_body)
                         for cell in row] for index, row in enumerate(cells)]
                widths = [110, 238] if columns == 2 else [348 / columns] * columns
                table = Table(rows, colWidths=widths, hAlign='LEFT', repeatRows=0)
                table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
                    ('LINEBELOW',(0,0),(-1,0),.7,accent), ('BOTTOMPADDING',(0,0),(-1,-1),7),
                    ('TOPPADDING',(0,0),(-1,-1),5)]))
                result.append(table)
                continue
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
