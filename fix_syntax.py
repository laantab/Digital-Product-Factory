with open(r"C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\static\js\app.js", encoding="utf-8") as f:
    lines = f.readlines()

# Find all occurrences of "})); }" and fix them
fixed = 0
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    # Check if this line ends with "})); }\n" (extra ) before final })
    stripped = line.rstrip('\n\r')
    if stripped == '    })); }':
        # Look at previous line to understand context
        if i > 0:
            prev = lines[i-1].rstrip()
            # If prev ends with '});' or just '}' - forEach was already closed
            if prev.rstrip().endswith('});') or prev.rstrip().endswith('}'):
                # This is an extra ) in closing })); }
                # Fix: change to });
                new_lines.append('    }); }\n')
                fixed += 1
                i += 1
                print(f"Fixed line {i}: {repr(lines[i-1].rstrip()[:60])}")
                continue
    new_lines.append(line)
    i += 1

print(f"Total fixed: {fixed}")

with open(r"C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\static\js\app.js", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
