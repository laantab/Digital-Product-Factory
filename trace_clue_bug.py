"""Trace the exact bug: how everyday words lose their real clues."""
import sys; sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')

from services.crossword.clues import simple_clue, lookup_clue, _theme_pack_key, _load_clue_packs
from services.crossword.crossword_fallback import EVERYDAY_LIFE

# Check which everyday words are in crossword_clues.json (clues.py)
packs = _load_clue_packs()
general = packs.get("general", {})

everyday_words = ["COMB", "WAKE", "SOAP", "SINK", "FORK", "BOWL", "LAMP", "KEYS",
                  "TOOTHBRUSH", "ALARM", "TOAST", "LUNCH", "SPOON", "PLATE",
                  "SHIRT", "SOCKS", "SHOES", "PHONE", "PANTS", "DRESS",
                  "COUCH", "RADIO", "MONEY", "TRASH", "BROOM", "STORE"]

print("="*70)
print("CHECK 1: Are everyday words in crossword_clues.json?")
print("="*70)
for word in everyday_words[:10]:
    in_general = word in general
    in_other = any(word in p for k, p in packs.items() if k != "general")
    print(f"  {word}: general={in_general}, any_pack={in_other}")

print("\n" + "="*70)
print("CHECK 2: Are they in crossword_fallback.py (EVERYDAY_LIFE)?")
print("="*70)
fallback_words = {w for w, c in EVERYDAY_LIFE}
fallback_clues = {w: c for w, c in EVERYDAY_LIFE}
for word in everyday_words[:10]:
    in_fb = word in fallback_words
    clue = fallback_clues.get(word, "N/A")
    print(f"  {word}: in_fallback={in_fb}, clue={clue}")

print("\n" + "="*70)
print("CHECK 3: What does simple_clue return for these words?")
print("="*70)
for word in everyday_words[:10]:
    # Test with theme "motivation" (a pack that won't have these)
    clue_motivation = simple_clue(word, theme="motivation")
    clue_everyday = simple_clue(word, theme="everyday life")
    clue_empty = simple_clue(word, theme="")
    print(f"  {word} (motivation):    {clue_motivation}")
    print(f"  {word} (everyday life): {clue_everyday}")
    print(f"  {word} (empty):         {clue_empty}")
    print()

print("="*70)
print("CHECK 4: _theme_pack_key for various themes")
print("="*70)
themes_to_test = [
    "motivation", "wedding dance", "everyday life", "everyday activities",
    "happiness", "philosophy", "positive mindset", "just for fun"
]
for t in themes_to_test:
    key = _theme_pack_key(t)
    print(f"  _theme_pack_key('{t}'): {key}")

print("\n" + "="*70)
print("CHECK 5: What clue_topic is set in build_crossword_from_topic?")
print("="*70)
# Simulate: theme="motivation", sub_topic=""
primary_topic = ""
fallback_topic = "motivation"
combined_topic = f"{fallback_topic} {primary_topic}".strip()
clue_topic = primary_topic or fallback_topic or combined_topic
print(f"  theme='motivation', sub_topic=''")
print(f"  clue_topic = '{clue_topic}'")
print(f"  COMB with clue_topic='{clue_topic}': {simple_clue('COMB', theme=clue_topic)}")
