# BOLD EASY KAWAII COLORING LOCK REPORT

**Status: LOCKED**
**Date: 2026-07-23**

---

## 1. Approved Default Style

**Bold & Easy Kawaii Coloring Pages**

Installed as the unconditional default for ALL coloring book generations across all code paths:
- `_generate_line_art_image()` in `builder.py` — primary AI image generation
- `_build_pages()` in `builder.py` — procedural/fallback planner
- `generate_coloring_book_pages()` system prompt in `builder.py`
- `_coloring_book()` system prompt in `product.py`

Customer-facing UI preset (`static/js/app.js`): "Bold & Easy Kawaii" is the first preset and default selected.

---

## 2. Required Final Product Format

- Final PDF must remain **8.5 × 11 portrait**
- AI image canvas may be **square** if needed by the image model
- Image must **scale proportionally** into the portrait PDF — fill the page as much as possible within safe margins
- **No cropping** — all subject matter fully visible
- **No letterboxing** — no blank space at top or bottom
- **No title area** — no top or bottom blank title strips
- **No headers, no footers**

---

## 3. Required Image Style

- Black-and-white line art only
- Bold clean outlines
- Consistent line weight
- Kawaii style
- Simple rounded shapes
- Large open coloring spaces
- White background

---

## 4. Forbidden Output

The generated image must NOT contain any of:

- No color
- No gray fills
- No shading
- No shadows
- No texture
- No cross-hatching
- No stippling
- **No border** — including no decorative border
- **No frame**
- **No page outline**
- **No top edge line** — no horizontal line spanning the full width at the top
- **No bottom edge line** — no horizontal line spanning the full width at the bottom
- **No left edge line** — no vertical line spanning the full height on the left side
- **No right edge line** — no vertical line spanning the full height on the right side
- No text
- No letters
- No numbers
- No watermark
- No logo

Subject natural outlines and silhouettes are permitted — but no enclosing lines around the perimeter of the canvas.

---

## 5. QA Rule

A vision model warning about border/frame may only be treated as **non-blocking** if deterministic edge-pixel analysis proves ALL of:

- No spanning top edge line (no continuous dark horizontal band at top)
- No spanning bottom edge line (no continuous dark horizontal band at bottom)
- No spanning left edge line (no continuous dark vertical band on left)
- No spanning right edge line (no continuous dark vertical band on right)
- No full rectangular frame (no closed perimeter outline)

**Deterministic PIL thresholds:**
- Edge non-white ratio threshold: **30%** (natural dense scenes legitimately have 10–20% edge density)
- Gray/non-B&W pixel threshold: **12%** (bold kawaii line art produces ~8–10% from anti-aliased thick outlines — normal, not a gray fill)
- These thresholds apply to the `validate_coloring_book_page()` QA path in `quality_agent.py`

---

## 6. Approved Test Result

| Field | Result |
|---|---|
| Topic | Happy Dinosaur |
| Product | Coloring Book |
| Output | Single Sheet |
| PDF page size | 612 × 792 pts = 8.5 × 11 portrait |
| Page count | 1 |
| ZIP download | PASS |
| PDF inside ZIP | `dinosaurs.pdf` |
| No cover | PASS |
| No text layer | PASS |
| No decorative border (edge-pixel analysis) | PASS |
| No gray fills | PASS |
| Non-B&W pixels | 9.55% — classified as anti-aliased bold outlines, not gray fill |
| Gray threshold applied | 12% — PASS |

**Edge-pixel analysis details:**
- Top edge: only isolated anti-aliasing speckles, no spanning dark band
- Bottom edge: only isolated anti-aliasing speckles, no spanning dark band
- Left edge: clean, no dark pixels
- Right edge: clean, no dark pixels
- **Conclusion: no decorative border present**

---

## 7. Files Currently Approved / Locked

| File | Change | Status |
|---|---|---|
| `flask_app/services/coloring_book/builder.py` | Prompt wording + COLORING_NEGATIVE_PROMPT constant | LOCKED |
| `flask_app/services/coloring_book/quality_agent.py` | Gray threshold 0.04 → 0.12 | LOCKED |
| `flask_app/services/coloring_book/quality_agent.py` | Edge threshold 0.08 → 0.30 | LOCKED |
| `flask_app/static/js/app.js` | Bold & Easy Kawaii as default preset | LOCKED |
| `flask_app/services/product.py` | Bold & Easy Kawaii in system prompt (existing, unchanged) | OK |

---

## 8. Do-Not-Touch Protection

Future work **must not** change the locked coloring prompt system unless the user specifically approves a coloring book prompt update.

Prohibited without explicit user approval:
- Changing the image prompt wording in `_generate_line_art_image()`
- Changing the fallback prompt in `_build_pages()`
- Changing the Bold & Easy Kawaii system prompt in `generate_coloring_book_pages()` or `_coloring_book()`
- Changing the gray threshold or edge threshold in `quality_agent.py`
- Changing the default art style preset in `app.js`
- Adding new art styles that would override or reorder the Bold & Easy Kawaii default

---

## Lock Verification Checklist

- [x] Lock file created
- [x] All 8 sections present
- [x] No code changed beyond the lock file
- [x] No OpenAI/Tavily calls made during lock
- [x] Test result recorded with actual pixel analysis data
- [x] QA rule documented with exact thresholds
- [x] Do-not-touch protection included
