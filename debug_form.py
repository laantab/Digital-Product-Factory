import re

app_js = open(r"C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\static\js\app.js", encoding="utf-8").read()

# Find crossword section
cw_pos = app_js.find('id: "crossword"')
print(f"id: 'crossword' position: {cw_pos}")

# Find the end of the crossword section (next top-level object)
# Look for the start of the next object in the PRODUCT_TYPES array
# After crossword fields, the next item is flip_book or cover_design
next_pos = app_js.find('\n  {', cw_pos + 30)
print(f"Next top-level object position: {next_pos}")
if next_pos == -1:
    next_pos = cw_pos + 5000

cw_section = app_js[cw_pos:next_pos]
print(f"Section length: {len(cw_section)} chars")
print(f"Section starts: {repr(cw_section[:100])}")
print(f"Section ends: {repr(cw_section[-50:])}")

# Check each field
checks = {
    'creation_mode': '"name": "creation_mode"',
    'custom_words': '"name": "custom_words"',
    'include_answer_key': '"name": "include_answer_key"',
}

for name, pattern in checks.items():
    found = pattern in cw_section
    print(f"  {name}: {'FOUND' if found else 'MISSING'} ({repr(pattern)})")

# Also try without double-quote escaping
for name, pattern in checks.items():
    found = pattern in cw_section
    if not found:
        # Try single quote
        alt = pattern.replace('"', "'")
        found2 = alt in cw_section
        print(f"  {name} (single quote): {'FOUND' if found2 else 'MISSING'}")
        if not found2:
            # Check what quotes are actually used
            pos = cw_section.find('creation_mode')
            if pos >= 0:
                print(f"  Around creation_mode: {repr(cw_section[pos-10:pos+50])}")
            else:
                print(f"  'creation_mode' not found at all in section")
                # Maybe it's in a different part of the file?
                all_pos = [m.start() for m in re.finditer('creation_mode', cw_section)]
                print(f"  'creation_mode' occurrences in section: {all_pos}")
