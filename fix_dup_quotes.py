with open(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\services\pdf_export.py', 'rb') as f:
    content = f.read()

# Find and remove the duplicate """ on consecutive lines
# Look for pattern: """ followed by newline and """
# Replace with just one """
import re
# The issue: lines 217-218 both have """
# Fix: remove one of them
# The content should have a double-triple-quote issue
# Let's find it
idx = content.find(b'"""\r\n"""\r\n')
if idx >= 0:
    print(f"Found double triple-quote at position {idx}")
    # Replace with single """
    fixed = content[:idx+3] + b'\r\n' + content[idx+6:]
    with open(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\services\pdf_export.py', 'wb') as f:
        f.write(fixed)
    print("Fixed!")
else:
    print("Pattern not found")
    # Try another pattern
    idx = content.find(b'"""\n"""\n')
    if idx >= 0:
        print(f"Found (LF only) at {idx}")
        fixed = content[:idx+3] + b'\n' + content[idx+6:]
        with open(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\services\pdf_export.py', 'wb') as f:
            f.write(fixed)
        print("Fixed!")
    else:
        print("Still not found. Let me search for all occurrences:")
        pos = 0
        while True:
            pos = content.find(b'"""', pos)
            if pos < 0:
                break
            print(f'  At {pos}: {repr(content[pos-20:pos+25])}')
            pos += 1
