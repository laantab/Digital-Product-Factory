"""Test unknown theme behavior."""
import sys; sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')
from services.crossword.word_entries import suggest_crossword_words_from_topic
from services.crossword.crossword_fallback import _normalize_theme, get_fallback_book_vocabulary

test_themes = [
    'abstract expressionism',
    'quantum mechanics',
    'just for fun',
    'happiness',
    'motivation',
    'wedding dance',
    'urban planning',
    'philosophy',
    'aesthetic theory',
]

print("="*70)
print("UNKNOWN THEME BEHAVIOR — what happens when no pack matches")
print("="*70)

for t in test_themes:
    words, warns, errs = suggest_crossword_words_from_topic(t, max_words=5)
    pack = _normalize_theme(t)
    print(f'\nTheme: "{t}"')
    print(f'  Pack match: {warns[0] if warns else "NO LOCAL PACK MATCHED"}')
    print(f'  _normalize_theme: "{pack}"')
    print(f'  Returned words: {words[:5]}')
    if errs:
        print(f'  ERROR: {errs}')

print("\n" + "="*70)
print("FALLBACK — everyday_life vocabulary")
print("="*70)
vocab = get_fallback_book_vocabulary("no such theme exists xyz", puzzle_count=2, words_per_puzzle=10)
print("get_fallback_book_vocabulary('no such theme exists xyz'):")
for i, (wlist, cmap) in enumerate(vocab):
    print(f"  Puzzle {i+1} ({len(wlist)} words): {wlist[:6]}...")
