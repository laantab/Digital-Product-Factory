# COLORING BOOK SINGLE SHEET USER-PATH LOCKED STATE

**Date locked:** 2026-07-12
**Status:** LOCKED — do not modify Single Sheet enforcement logic

---

## 1. ACCEPTED BEHAVIOR

- Coloring Book Single Sheet through `POST /generate-product` produces **exactly 1 PDF page**
- Single Sheet **never includes a cover page**
- Single Sheet does not include title page, header, footer, page number, or caption when captions = No
- Single Sheet uses the **actual coloring page image only**
- ZIP/export contains the **corrected 1-page PDF**
- **Digital Book behavior is preserved** — cover + multi-page interior unchanged

---

## 2. FRESH VERIFIED TEST

### Input
```json
{
  "product_type": "coloring_book",
  "fields": {
    "coloring_title": "Farm House",
    "theme": "Farm House",
    "output_format": "Single Sheet",
    "pages": "1",
    "quality_mode": "AI Image Coloring Page",
    "age_group": "12-adult",
    "art_style": "realistic",
    "include_captions": "No",
    "page_size": "US Letter"
  }
}
```

### Verified Output
| Field | Value |
|---|---|
| Route used | `POST /generate-product` |
| Fresh export folder | `exports/c9302717b2cb4b21ad7408cd167ff874/` |
| Final PDF | `flask_app/exports/c9302717b2cb4b21ad7408cd167ff874/farm_house.pdf` |
| PNG preview | `flask_app/exports/fresh_farm_house_test/farm_house_preview.png` |
| ZIP | `flask_app/exports/cbadb09da5df46f499c8e92f9353cd2d/package.zip` |
| Page count | **1** |
| Extracted text length | **0** |
| Local fallback used | **No** |
| AI image generated | **Yes** (2,043,341 bytes, 1024×1024 B&W) |
| Cover present | **No** |
| Visual result | **PASS** |

---

## 3. FILES CHANGED

### `services/product.py` — `_coloring_book_pdf_payload()`

```python
# ── SINGLE SHEET ENFORCEMENT ────────────────────────────────────────────
if output_type == "single_page":
    pages = 1
    plan = dict(plan, include_cover=False)  # override without mutating original
# ────────────────────────────────────────────────────────────────────────
```
- Forces `page_count = 1` for Single Sheet
- Forces `include_cover = False` for Single Sheet
- Preserves Digital Book behavior (book output_type unchanged)

### `static/js/app.js` — `selectFactoryType()` + `openProject()` + new `_coloringBookSetupForm()`

```javascript
function _coloringBookSetupForm() {
  // Locks pages = 1, readOnly when "Single Sheet" selected
  // Restores pages = 12 when "Digital Book" selected
  // Re-enforces after saved-project field restore
}
```
- Client-side enforcement: pages locked to 1 for Single Sheet
- Re-enforces rules when reopening saved coloring book projects

---

## 4. PROTECTED BEHAVIOR

- **Do not allow** Single Sheet to route through book/cover assembly
- **Do not allow** Single Sheet to generate 12-page or 13-page output
- **Do not allow** Single Sheet to reuse stale old exports
- **Do not add** headers/page numbers when captions = No
- **Do not use** Basic Test Fallback in AI Image Coloring Page mode
- **Do not weaken** the image quality gate

---

## 5. HARD CONFIRMATIONS

- [x] No ebook files changed
- [x] No Word Search files changed
- [x] No Crossword files changed
- [x] No planner files changed
- [x] No Budget Planner changes
- [x] No Faith Planner changes
- [x] No Tavily calls made
- [x] No OpenAI calls made
- [x] No unrelated products generated
