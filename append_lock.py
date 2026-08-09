append = """

**Approved post-lock fingerprint refresh** (2026-08-04 08:30 PT): `app.js` md5 refreshed to `e5d8798be79ef4cd8cce7e9a920be165` after fixing three crossword regressions. Previous md5 `f59629484fb08e3a563a098ce8686da0` preserved in `previous_md5` for traceability. Changes:

1. Added `creation_mode` and `custom_words` fields to the crossword factory form (was missing; word search had them).
2. Added `default: "Yes"` to `include_answer_key` field (was defaulting to "No" — answer keys never worked by default).
3. Fixed `services/product.py:_crossword_plan` to check `creation_mode == "Custom word list"` instead of `use_custom_words` field (which was never set by the form).

**Approved post-lock fingerprint refresh** (2026-08-04): `services/product.py` md5 refreshed to `1e8eb8b96a7817f14e0d528bf55fa197` for the `creation_mode` fix. Previous md5 preserved in file.
"""

with open(r"C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\PUZZLE_GENERATORS_V1_LOCK.md", "a", encoding="utf-8") as f:
    f.write(append)
print("Done")
