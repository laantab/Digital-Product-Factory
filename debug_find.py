content = open(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\static\js\app.js', encoding='utf-8').read()

# Find all occurrences of 'id: "crossword"'
pos = 0
count = 0
while True:
    pos = content.find('id: "crossword"', pos)
    if pos < 0:
        break
    count += 1
    snippet = content[pos:pos+200]
    print(f'#{count} at {pos}: {repr(snippet[:80])}')
    pos += 1

# Also find where PRODUCT_TYPES array starts
pt_pos = content.find('PRODUCT_TYPES')
print(f'\nPRODUCT_TYPES at: {pt_pos}')

# Find crossword in PRODUCT_TYPES
pt_cw = content.find('id: "crossword"', pt_pos)
print(f'crossword in PRODUCT_TYPES at: {pt_cw}')

# Show snippet around it
if pt_cw > 0:
    print(f'Around PRODUCT_TYPES crossword: {repr(content[pt_cw-20:pt_cw+300])}')
