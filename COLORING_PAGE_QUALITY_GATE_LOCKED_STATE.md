# COLORING PAGE QUALITY GATE — LOCKED STATE
**Status:** LOCKED — 2026-07-11
**Phase:** AI image connection + sellable single-sheet polish

---

## 1. ACCEPTED BEHAVIOR

- **AI Image Coloring Page** generates a real AI image and embeds it in a clean PDF
- **Single Sheet mode** renders a pure printable coloring page: no "Page X of Y", no title header, no topic label, image fills the entire printable area
- **Basic Test Fallback** works locally with stick figures — labeled "Basic Test Fallback — Not Sellable Quality"
- **AI Image Coloring Page** mode blocks with clean error if no pre-generated image exists
- **No fake coloring pages** — quality gate is intact

---

## 2. SINGLE-SHEET LAYOUT (sellable)

When `output_type == "single_page"`:

- **No "Page X of Y"** label
- **No product title** at top
- **No topic/scene description** at top
- **No caption** (only shown if `page.caption` is set — for captions=No, nothing is printed)
- **Image fills nearly the entire printable area** (0.5" margins, image from top to bottom)
- **PDF contains zero text** — pure image page
- For `include_captions=True` with a real caption: caption appears at very bottom in small 8pt italic

---

## 3. IMAGE GENERATION

### Source
- **matrix MCP** `matrix_generate_image` tool — generates 1024×1024 professional B&W coloring page images
- Image is effectively B&W (mean RGB channel diff < 0.2, 0% color bleed)

### Image injection pattern
1. Pre-generate image using matrix MCP → save to `exports/{package_id}/coloring_p{pn:02d}.png`
2. `generate_visual_image()` checks if file exists → returns `True` (injection bypass)
3. Builder sets `page.image_path` → quality gate sees image → passes
4. Renderer embeds image in PDF
5. If no pre-generated image exists and `quality_mode == "ai_image_coloring_page"` → error result (no PDF)

---

## 4. FILES CHANGED

| File | Change |
|------|--------|
| `ebook_package.py` | `generate_visual_image()` checks if `out_path` already exists — if so, returns `True` immediately without calling AI (image injection bypass) |
| `builder.py` | `_generate_line_art_image()` catches `RuntimeError` from missing AI client and returns `False` (not propagated) |
| `renderer.py` | `_draw_coloring_page()` gains `single_sheet` parameter — removes all text headers/labels when `True`, maximizes image area; `build_coloring_book_pdf_bytes()` gains `single_sheet` param and passes to renderer |
| `pdf_builder.py` | Passes `single_sheet=(request.output_type == "single_page")` to renderer |

---

## 5. OUTPUT PATHS (Thunder Volt Man rescue scene)

| Output | Path |
|--------|------|
| Raw AI image | `flask_app/exports/thunder_volt_rescue/coloring_p01.png` (1MB, 1024×1024) |
| B&W preview | `flask_app/exports/thunder_volt_rescue/thunder_volt_man_bw_preview.png` (68 KB) |
| Final sellable PDF | `flask_app/exports/thunder_volt_rescue/thunder_volt_man_sellable_sheet.pdf` (1.27 MB, 1 page) |
| PDF preview | `flask_app/exports/thunder_volt_rescue/thunder_volt_man_sellable_preview.png` (939 KB) |

### Scene accuracy (matrix MCP inspection)
- Superhero character: YES
- Power station/electrical equipment: YES
- People being rescued/protected: YES (civilians inside energy shield)
- Lightning/electrical effects: YES
- Storm clouds: YES
- Score: **7/10** — all key elements present

### PDF verification
- Text content: **zero characters** (pure image page)
- No "Page X of Y": CONFIRMED
- No topic/title labels: CONFIRMED
- No Basic Test label: CONFIRMED
- Image embedded: CONFIRMED (PDF 1.27 MB)

---

## 6. PROTECTED BEHAVIOR

- Do not present local fallback as AI Image Coloring Page
- Do not generate AI Image Coloring Pages without a real image
- Do not silently switch AI mode to fallback
- Do not use stick figures in AI Image Coloring Page mode
- Do not use ReportLab drawings in AI Image Coloring Page mode

---

## 7. HARD CONFIRMATION

- No ebook files changed
- No Word Search files changed
- No Crossword files changed
- No planner files changed
- No dashboard rebuild
- No Tavily calls
- No unrelated products generated
