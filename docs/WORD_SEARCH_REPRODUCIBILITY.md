# Word search reproducibility

**Contract (v1.9.5 onwards):** the same saved word search book, rebuilt with the
same settings, produces the same grids, the same word placements and the same
answer key.

This is the same defect Crossword had, fixed there in v1.9.2. It was written
down in `docs/CROSSWORD_REPRODUCIBILITY.md` at the time, deliberately, so it
would not be lost — this is that note being acted on.

## What was wrong

`services/product.py` built every `WordSearchPdfRequest` with an explicit
`seed=None`. `services/word_search/book.py` forwards that `None` to
`services/word_search/engine.py`, which calls `random.Random(seed)`, and
`random.Random(None)` seeds itself from the operating system.

## How to reproduce the old behaviour

Check out `390aaf8` (v1.9.2) or earlier and run:

```
python - <<'PY'
import base64, hashlib, io, os
os.environ["FACTORY_TEST_MODE"] = "1"
from pypdf import PdfReader
from services.product import _word_search_pdf_payload

FIELDS = {"title": "Garden Birds Word Search", "theme": "garden birds",
          "audience": "adults", "difficulty": "medium", "grid_size": "15",
          "output_type": "book", "worksheets": "2", "words_per_puzzle": "12",
          "include_answer_key": "yes", "word_source": "topic",
          "include_cover": "no"}

def fingerprint():
    payload = _word_search_pdf_payload(dict(FIELDS), package_id="ws_saved")
    pdf = base64.b64decode(payload["pdf_bytes"])
    text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages)
    return hashlib.sha256(text.encode()).hexdigest()[:12]

print([fingerprint() for _ in range(3)])
PY
```

On v1.9.2 this prints three different digests. Measured on 2026-09-24:
`afead480f1d2`, `3eb314f3be75`, `9d00dc852a15`. On this branch it prints the
same digest three times (`9c8bf302a4a6`).

## How to verify the fix

```
python -m pytest tests/test_word_search_rebuilds_identically.py -q
```

Eleven tests, five of which fail on `390aaf8` and pass here — including the
save/reopen/rebuild path through `rebuild_word_search_pdf_from_data`.

## How the seed is chosen

`services/word_search/seeding.py` derives it with SHA-256 from the settings
that decide the puzzles: title, theme, audience, difficulty, grid size, number
of puzzles, words per puzzle, mode, and the resolved word list. `package_id` is
excluded because `services/product.py` falls back to a fresh `uuid4()`.
Capitalisation, padding and blank lines do not move it.

An explicit `word_search_seed` field still wins, so a future "give me different
puzzles" action needs no further change here.

## Why this is a separate module from Crossword's

`services/crossword/seeding.py` does the same job with Crossword's own fields.
Crossword and Word Search are separately LOCKED functions; sharing one module
would mean unlocking both whenever either changed. The duplication is four
small normalising functions, and that is the cheaper of the two costs.

## What is *not* guaranteed

The PDF file is not byte-identical between builds — a PDF carries a creation
timestamp. The promise is the same book, not the same bytes, which is why the
tests assert on the rendered text.
