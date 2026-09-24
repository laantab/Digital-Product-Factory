# Crossword reproducibility

**Contract (v1.9.2 onwards):** the same saved crossword book, rebuilt with the
same settings, produces the same puzzles, the same clue numbering and the same
answer key.

## What was wrong

`services/product.py` built every `CrosswordPdfRequest` without passing `seed`.
The field defaults to `None`, `services/crossword/book.py` forwards that `None`
to `services/crossword/engine.py`, and the engine calls `random.Random(None)`,
which seeds itself from the operating system.

Every build therefore started from a different random stream. The word list was
not the problem: topic vocabulary resolution was already deterministic and
returned a byte-identical list on every run. Only the grid layout and the clue
numbering moved -- which is enough to make a proof-read book wrong, because the
answer key the customer already checked no longer describes their puzzles.

## How to reproduce the old behaviour

Check out `53a41c9` (v1.9.1) or any earlier commit and run:

```
python - <<'PY'
import hashlib, os
os.environ["FACTORY_TEST_MODE"] = "1"
from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf

def fingerprint():
    request = CrosswordPdfRequest(
        product_title="Garden Birds Crossword", theme="garden birds",
        sub_topic="garden birds", difficulty="medium", grid_size=15,
        output_type="book", number_of_puzzles=3, words_per_puzzle=10,
        include_answer_key=True, include_cover=False, mode="topic",
        package_id="repro_pkg", use_ai_words=False,
    )
    result = build_crossword_pdf(request)
    grids = "|".join(repr(getattr(p, "grid", None)) for p in result.puzzles)
    return hashlib.sha256(grids.encode()).hexdigest()[:12]

print([fingerprint() for _ in range(3)])
PY
```

On v1.9.1 this prints three different digests. Measured on 2026-09-23:
`c90d77ad9ae4`, `66e0902f1bbd`, `f16e7c991ff4`.

Passing `seed=4242` to the same request makes all three identical, which is
what identified the missing seed rather than the engine as the cause.

## How to verify the fix

```
python -m pytest tests/test_crossword_rebuilds_identically.py -q
```

Four of those tests fail on v1.9.1 and pass on v1.9.2, including the
end-to-end one that builds the same book twice through
`services.product._crossword_pdf_payload` and compares the rendered text.

## How the seed is chosen

`services/crossword/seeding.py` derives it with SHA-256 from the settings that
decide what the puzzles are: title, theme, sub-topic, difficulty, grid size,
number of puzzles, words per puzzle, mode, and the resolved word list.

* Same saved book, same settings -> same seed -> same puzzles.
* Change any of those settings -> a different seed -> puzzles that match the
  new settings.
* Cosmetic differences -- the title's capitalisation or padding, blank lines or
  stray spaces in the word list -- do not move the seed, because they do not
  change a single square of a grid.
* `package_id` is deliberately **not** in the seed: `services/product.py` falls
  back to a fresh `uuid.uuid4().hex` when none is supplied, which would put a
  random value straight back in.
* SHA-256 rather than `hash()`, because Python randomises `hash()` per process
  unless `PYTHONHASHSEED` is set.

An explicit `crossword_seed` field on the request still wins, so a future
"give me a different set of puzzles" action has a way in without changing this
path again.

## What is *not* guaranteed

The PDF **file** is not byte-identical between builds. The PDF container
carries a creation timestamp and a document id that change every time. The
promise is the same book, not the same bytes, and
`tests/test_crossword_rebuilds_identically.py` asserts on the rendered text
rather than on a file hash for that reason.

## Known sibling defect, not fixed here

`services/product.py` passes `seed=None` for **Word Search** too (in
`_word_search_pdf_payload`), so word search books have the same reproducibility
problem. It was left alone deliberately: Word Search is a separate LOCKED
function and fixing it means unlocking it, running its own protected suite, and
relocking. It is recorded here so it is not lost.
