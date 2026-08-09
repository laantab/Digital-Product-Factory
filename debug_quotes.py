with open(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\services\pdf_export.py', 'rb') as f:
    lines = f.read().split(b'\n')
print(f'Total lines: {len(lines)}')
for i, line in enumerate(lines, 1):
    sq = line.count(b"'''")
    dq = line.count(b'"""')
    if sq or dq:
        print(i, sq, dq, repr(line[:80]))
