content = open('C:/Users/user/Documents/Product-Pipeline/Product-Pipeline/flask_app/static/js/app.js', encoding='utf-8').read()
assert '(d.exports && d.exports.files) || (d.product_exports && d.product_exports.files)' in content
print('app.js: nsExport fix confirmed present')

pkg = open('C:/Users/user/Documents/Product-Pipeline/Product-Pipeline/flask_app/services/packaging.py', encoding='utf-8').read()
assert 'crossword' in pkg and 'is_pdf' in pkg and 'pdf_bytes' in pkg and 'Word Search PDF' in pkg
assert 'Crossword PDF export is invalid' in pkg  # crossword block present
print('packaging.py: crossword export block confirmed present')
