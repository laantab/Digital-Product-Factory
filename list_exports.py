import os

base = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\exports'
existing = sorted(os.listdir(base))
print('Existing export folders on Windows:')
for f in existing:
    fp = os.path.join(base, f)
    if os.path.isdir(fp):
        et = os.path.join(fp, 'ebook.txt')
        content = ''
        if os.path.exists(et):
            with open(et, 'r', encoding='utf-8', errors='replace') as fh:
                content = fh.read().strip()[:80]
        files = sorted(os.listdir(fp))
        print(f'  {f}: ebook.txt="{content}"')
        print(f'    files: {files}')
    else:
        print(f'  {f}: file (not dir)')
