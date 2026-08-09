with open(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\services\pdf_export.py', 'rb') as f:
    lines = f.read().split(b'\n')
print(f'Total lines: {len(lines)}')
for i, line in enumerate(lines, 1):
    if 215 <= i <= 222:
        print(i, repr(line))
