# COLORING BOOK — THUNDER VOLT (BANK RESCUE) — LOCKED STATE

**Status:** LOCKED  
**Locked at:** 2026-08-10T22:20:53Z  
**Package ID:** `a092b8e351174900a9082fbb46350364`  
**Product family:** coloring_book  

---

## 1. APPROVED PRODUCT

| Field | Value |
|-------|--------|
| Theme | Thunder Volt is a Black superhero. He is stopping two adult men from robbing a bank and getting away in New York City. |
| Page count | **26** (1 cover + 25 interiors) |
| Interior QA | **25/25 PASS** |
| Paid API calls | **0** |
| User visual approval | **YES** (PDF and ZIP) |
| Regenerated at lock | **NO** |

---

## 2. APPROVED OUTPUT PATHS (on disk; `exports/` is gitignored)

| Artifact | Path | Bytes | SHA-256 |
|----------|------|------:|---------|
| PDF | `exports/a092b8e351174900a9082fbb46350364/thunder_volt.pdf` | 59425947 | `59c3d7cd0e22963cad995d762b4126f593ea97df2458577f80c431672aca4bac` |
| ZIP | `exports/a092b8e351174900a9082fbb46350364/package.zip` | 47854015 | `958c208e733d2ee8cf766bf2dd985ec6fdfcdd2ed5abe0122208463c8594273f` |

### ZIP package contents (verified)

- `ebook.html`
- `ebook.txt`
- `thunder_volt.pdf` — **byte-identical** to disk PDF (same SHA-256)

---

## 3. AUTHORITATIVE ON-DISK ACCEPTANCE RECORDS

These remain under `exports/` (gitignored). Lock fields were updated at approval:

| Record | Path |
|--------|------|
| Package acceptance manifest | `exports/a092b8e351174900a9082fbb46350364/package_acceptance_manifest.json` |
| Final package build report | `exports/a092b8e351174900a9082fbb46350364/final_package_build_report.json` |

Tracked lock snapshot (committed):

| Record | Path |
|--------|------|
| Acceptance / lock JSON | `THUNDER_VOLT_COLORING_BOOK_PACKAGE_ACCEPTANCE_LOCK.json` |
| This lock document | `COLORING_BOOK_THUNDER_VOLT_LOCKED_STATE.md` |

Manifest / report lock fields set:

- `book_locked`: `true`
- `lock_status`: `LOCKED`
- `locked_at`: `2026-08-10T22:20:53Z`
- `paid_calls`: `0`
- `user_visual_approval`: approved
- `approved_outputs`: PDF/ZIP paths, sizes, SHA-256, page_count 26, interior QA 25/25
- `stopped_before`: cleared (`[]`)

---

## 4. LOCK RULES

- Do **not** regenerate cover or any interior page images for this package.
- Do **not** rebuild PDF/ZIP unless a verified corruption/missing-file proof requires it.
- Preview, Save, PDF download, and ZIP download must use these accepted artifact bytes.
- Do **not** treat a QA-blocked product as downloadable for this package.
- Generator code locks remain in `COLORING_BOOK_GENERATOR_LOCKED_STATE.md` and related coloring lock docs; this document locks the **approved Thunder Volt book package**, not the generator.

---

## 5. VERIFICATION AT LOCK

| Check | Result |
|-------|--------|
| PDF exists and readable | PASS |
| ZIP exists and opens (`testzip` clean) | PASS |
| PDF page count (pypdf) | **26** |
| ZIP contains `thunder_volt.pdf` matching disk PDF hash | PASS |
| Interior QA from package acceptance manifest | **25/25 PASS** |
| Paid calls | **0** |
| User visual approval | recorded |
| Preflight / release gate before lock | PASS (309 tests, 0 failed, 0 skipped, paid calls 0) |
