content = open(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\static\js\app.js', encoding='utf-8').read()

# Find PRODUCT_TYPES crossword
pt_start = content.find('PRODUCT_TYPES')
pt_cw = content.find('id: "crossword"', pt_start)
section_end = content.find('\n  {', pt_cw + 20)
section = content[pt_cw:section_end]

fields_start = section.find('fields: [')
fields_end = section.find('  },', fields_start)
fields = section[fields_start:fields_end + 5]

# Check various patterns
patterns = [
    '"name": "creation_mode"',
    'name: "creation_mode"',
    "'name': 'creation_mode'",
    'name: "creation_mode"',
    '"creation_mode"',
    'creation_mode',
]
for p in patterns:
    print(f'Pattern {repr(p):40s} found: {p in fields}')

# Show first 300 chars of fields
print('\nFields block (first 400 chars):')
print(fields[:400])
