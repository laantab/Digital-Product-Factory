import requests, json, os, sys

BASE = 'http://127.0.0.1:5000'

print('=== Word Search Final Verification ===')
print()

r = requests.post(f'{BASE}/word-search-builder/generate', json={
    'product_title': 'Summer School',
    'theme': 'Summer School',
    'creation_mode': 'topic',
    'include_answer_key': 'yes',
    'output_type': 'book',
}, timeout=120)
body = r.json()
print(f'HTTP status: {r.status_code}')
print(f'ok: {body.get("ok")}')
if body.get('errors'):
    print(f'ERRORS: {body["errors"]}')

pdf_url = body.get('download_url') or ''
pdf_path = body.get('filename') or ''
pdf_size = 0
pdf_valid = False
answer_key_in_pdf = False

if pdf_url:
    dl = requests.get(BASE + pdf_url, timeout=30)
    pdf_bytes = dl.content
    pdf_size = len(pdf_bytes)
    pdf_valid = pdf_bytes[:4] == b'%PDF'
    answer_key_in_pdf = b'ANSWER' in pdf_bytes.upper() or b'Answer Key' in pdf_bytes or b'KEY' in pdf_bytes.upper()
    print(f'PDF URL: {pdf_url}')
    print(f'PDF filename: {pdf_path}')
    print(f'PDF size: {pdf_size:,} bytes')
    print(f'PDF valid: {pdf_valid}')
    print(f'Answer key in PDF: {answer_key_in_pdf}')
    print()
    print('Note: ZIP export is only available via /export-product route, not /word-search-builder/generate')

print()
print('=== RESULT ===')
all_pass = pdf_valid and answer_key_in_pdf
print(f'Word Search final status: {"PASS" if all_pass else "FAIL"}')
sys.exit(0 if all_pass else 1)
