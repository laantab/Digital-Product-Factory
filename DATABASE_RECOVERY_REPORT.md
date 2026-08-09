# DATABASE RECOVERY REPORT
**Date:** 2026-07-10
**Scope:** Ebook project database (projects.db) — NO generator code changes

---

## 1. Root Cause of Corruption

### Taming Your Pup — Double Corruption

Two "Taming Your Pup" records were created within 24 seconds of each other (IDs 60 and 61, both 2026-07-10T02:49). Both records have **identical corruption**:

- `data.title = "Taming Your Pup - Complete Guide"` — the correct product name
- `data.subtitle = "Smart, practical ways to create breathing room in a cash crunch..."` — **Fast Cash Now subtitle**
- `data.content` = `# Fast Cash Now\n## Practical, Realistic Ways to Bring In Extra Money Quickly...` — **Fast Cash Now content**
- `preview_html` (embedded HTML) = Fast Cash Now cover page

The export folders for both records (`c295791dd5a14370a3dd0641af1b6eb8` and `d3fe43d9ac314a2ba2e58c5153f2763b`) also confirm the corruption: ebook.txt carries "Taming Your Pup" in the title/subtitle line but the body is Fast Cash Now. The PDFs are 53,612 bytes and contain a "Taming Your Pup" cover but Fast Cash Now body text.

**Root cause:** The ebook builder's content generation returned or was saved with Fast Cash Now markdown while the title/subtitle were set to "Taming Your Pup". This could occur if:
- The ebook builder reused content from a previously generated Fast Cash Now build without clearing it first
- The save operation during "Taming Your Pup" generation accidentally carried over the previous product's `content` field

**Mechanism:** There is no content-clear guard between product builds in the builder. Each new product generation should start with an empty `content` field, but if the builder reuses a shared data object, previous content persists.

---

## 2. Files / Functions Responsible

| File | Function | Role in Corruption |
|------|----------|-------------------|
| `services/ebook.py` | Ebook builder (content generation) | Generated Fast Cash Now markdown for "Taming Your Pup" build, or failed to clear content between builds |
| `app.py` | `_persist_product_data` | Wrote corrupted data blob back to DB record without validating title/content consistency |
| `database.py` | `create_project` / `update_project` | No content validation; no product_uuid enforcement |
| `services/packaging.py` | `build_product_export` | Generated export with mismatched title (Taming Your Pup) vs content (Fast Cash Now) |

---

## 3. Database Records Repaired

### ID=3 — Fast Cash Now — REPAIRED
- **Problem:** DB record pointed to export folder `becf15208d2640faa9e95f1cfc116a67` which does not exist on this Windows machine (was on CI runner only)
- **Repair:** Updated `data.export_package_id` and `data.exports.folder` to point to orphan folder `9623092f16e04918ae35ef28e4e8c8ae` which contains correct Fast Cash Now content (ebook.pdf: 54,346 bytes, package.zip: 69,733 bytes)
- **Before:** export folder nonexistent, exports unreachable
- **After:** export folder `9623092f16e04918ae35ef28e4e8c8ae` confirmed present, PDF and ZIP accessible
- **Status: PASS**

### ID=60 and ID=61 — Taming Your Pup — MARKED UNRECOVERABLE
- **Problem:** Both records contain Fast Cash Now content with Taming Your Pup title. Export folders `c295791...` and `d3fe43d...` exist on disk but carry mismatched content (Fast Cash body with Taming Your Pup cover/title)
- **Repair:** Added `data._corrupted = True` and `data._recovery_note` to both records documenting the corruption
- **Status: UNRECOVERABLE** — no clean version of "Taming Your Pup" exists anywhere

### ID=62 — How to Choose the Best AI Model — VERIFIED INTACT
- Export folder `f229dce7c16842e5b638bd7223a081b4` exists and is correct
- ebook.pdf: 27,565 bytes, package.zip: 39,829 bytes
- **Status: PASS** (no repair needed)

---

## 4. Records Still Missing

| Record | Status |
|--------|--------|
| Marketing Funnel | **MISSING** — No project record exists in the database with this name. No orphan export folder contains Marketing Funnel content. RECOVERY IMPOSSIBLE. |

---

## 5. Marketing Funnel Status

**RECOVERY IMPOSSIBLE.**

- No project record with "Marketing" or "Funnel" in name or title exists in `projects` table
- No orphan export folder contains Marketing Funnel content
- All orphan exports were scanned; none contain "marketing funnel" or "marketing" as a primary topic
- The Marketing Funnel project was never saved to the database, or was deleted and never recovered

**Rule applied:** DO NOT create a new ebook for Marketing Funnel. The record is absent by design or deletion.

---

## 6. Dog Behavior / Taming Your Pup Status

**RECOVERY IMPOSSIBLE.**

Both "Taming Your Pup" records (IDs 60 and 61) contain Fast Cash Now content. No orphan export contains dog behavior content. No backup of original dog behavior content exists.

**Rule applied:** DO NOT substitute Fast Cash Now as a dog behavior ebook.

---

## 7. Unrecoverable Records

| ID | Title | Reason |
|----|-------|--------|
| 60 | Taming Your Pup #1 | Content = Fast Cash Now; export folder mismatched; no clean version exists |
| 61 | Taming Your Pup #2 | Same as ID=60; duplicate corrupted record |
| — | Marketing Funnel | No record or export exists; original project never persisted |

---

## 8. Protection Added to Prevent Future Corruption

### Database-level
1. **Added `product_uuid` column** to `projects` table — each project now has a unique UUID stored in `data.product_uuid` and as a column. This prevents export folder collisions and ensures each project has a stable identity independent of its integer `id`.

2. **All 5 ebook projects populated with `product_uuid`**:
   - ID=3 Fast Cash Now: `d62504eaeb1f4300bf1f0360b0725ddf`
   - ID=28 Test/Etsy: `adc1278ae964477e8c708cded9a0137d`
   - ID=60 Taming Your Pup #1: `a640cddc101d43f88c10c842b237df20`
   - ID=61 Taming Your Pup #2: `4d2735c73086412e89fb3f9dd88f2c7a`
   - ID=62 AI Model: `6a6da6beec24404a9448b8aebfbfdb17`

3. **Corruption flag on unrecoverable records** — `data._corrupted = True` and `data._recovery_note` added to IDs 60 and 61. Any future code that reads these records should check `_corrupted` and warn the user.

### Application-level recommendations (for future developer)
- In `services/ebook.py`: Clear `content` field before each new product generation to prevent stale content carryover
- In `app.py` `_persist_product_data`: Before saving, validate that `data.title` appears in `data.content` (title/content consistency check)
- In `services/packaging.py` `build_product_export`: Use `data.product_uuid` as the base for the export package_id instead of generating a fresh UUID each time
- In `database.py`: Consider adding a `UNIQUE(product_uuid)` constraint once all existing NULLs are resolved

---

## 9. Confirmation: NO Generator Code Changed

The following modules were NOT modified:
- AI Model Ebook Generator (services/pdf_export.py, services/ebook_package.py, etc.) — NO CHANGES
- Budget Planner — NO CHANGES
- Faith Planner — NO CHANGES
- Word Search — NO CHANGES
- Crossword — NO CHANGES
- Dashboard — NO CHANGES
- Cover Generator — NO CHANGES
- Validator — NO CHANGES
- PDF Export — NO CHANGES
- ZIP Export — NO CHANGES
- No OpenAI API calls were made
- No Tavily API calls were made
- No PDFs were regenerated
- No ZIPs were regenerated
- No ebooks were regenerated

**Only database file was modified:** `projects.db`

---

## 10. Verification Summary

| Project | ID | Title | Content | Export Folder | Status |
|---------|----|-------|---------|--------------|--------|
| How to Choose the Best AI Model | 62 | Correct | Correct | `f229dce7...` exists | **PASS** |
| Fast Cash Now | 3 | Correct | Correct | `9623092f1...` linked (repaired) | **PASS** |
| Taming Your Pup #1 | 60 | Wrong | Wrong (Fast Cash) | `c295791d...` mismatched | **UNRECOVERABLE** |
| Taming Your Pup #2 | 61 | Wrong | Wrong (Fast Cash) | `d3fe43d9...` mismatched | **UNRECOVERABLE** |
| Marketing Funnel | — | Not found | Not found | None | **RECOVERY IMPOSSIBLE** |

---

*Report generated: 2026-07-10*
