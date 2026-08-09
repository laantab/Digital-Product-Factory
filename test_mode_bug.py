"""Test: saved project with old 3-word custom list should not block Topic mode."""
import sys; sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')

from services.product import _resolve_crossword_words, _crossword_plan

# Simulate: saved project has 3 old custom words
old_stored_words = "APPLE\nBANANA\nCHERRY"

# Fields: user selected "Topic" mode (NOT "Custom word list")
fields_topic = {
    "title": "Garden Vegetables",
    "theme": "Garden Vegetables",
    "subtitle": "Garden Vegetables",
    "creation_mode": "Topic (AI generates words)",
    "puzzles": "10",
    "output_type": "book",
}

# Fields: user selected "Custom word list" mode
fields_custom = {
    "title": "My Words",
    "theme": "General",
    "subtitle": "",
    "creation_mode": "Custom word list",
    "custom_words": "APPLE\nBANANA\nCHERRY\nDATE",
    "puzzles": "10",
    "output_type": "book",
}

# Fields: empty fields, no creation_mode (should default to topic)
fields_empty = {
    "title": "Test",
    "theme": "Test",
    "puzzles": "10",
}

def test():
    # Test 1: Topic mode should IGNORE stored_words (3 old words)
    plan_topic = _crossword_plan(fields_topic)
    print(f"plan_topic['use_custom']: {plan_topic['use_custom']}")
    result = _resolve_crossword_words(fields_topic, plan_topic, stored_words=old_stored_words)
    lines = [l.strip() for l in result.splitlines() if l.strip()]
    print(f"\nTopic mode + 3 old stored words:")
    print(f"  Words returned: {len(lines)}")
    print(f"  Words: {lines[:5]}")
    if len(lines) >= 4:
        print("  PASS: Topic mode ignored old stored_words, generated fresh words")
    else:
        print("  FAIL: Still using old stored_words!")

    # Test 2: Custom word list mode should USE the custom_words from fields
    plan_custom = _crossword_plan(fields_custom)
    print(f"\nplan_custom['use_custom']: {plan_custom['use_custom']}")
    result2 = _resolve_crossword_words(fields_custom, plan_custom, stored_words="")
    lines2 = [l.strip() for l in result2.splitlines() if l.strip()]
    print(f"\nCustom word list mode:")
    print(f"  Words returned: {len(lines2)}")
    print(f"  Words: {lines2}")
    if len(lines2) >= 4:
        print("  PASS: Custom mode used custom_words")
    else:
        print("  FAIL: Not using custom_words!")

    # Test 3: Empty fields (default topic) should generate words
    plan_empty = _crossword_plan(fields_empty)
    print(f"\nplan_empty['use_custom']: {plan_empty['use_custom']}")
    result3 = _resolve_crossword_words(fields_empty, plan_empty, stored_words=old_stored_words)
    lines3 = [l.strip() for l in result3.splitlines() if l.strip()]
    print(f"  Words returned: {len(lines3)}")
    print(f"  Words: {lines3[:5]}")
    if len(lines3) >= 4:
        print("  PASS: Empty fields + old stored_words → generated fresh words")
    else:
        print("  FAIL: Still using old stored_words!")

test()
