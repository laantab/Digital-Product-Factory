# Public Factory Menu Cleanup — LOCK

**Lock ID:** `public_factory_menu_cleanup_v1`
**Locked on:** 2026-07-28
**Scope:** Public Product Factory menu visibility + backend guard for the 4 unfinished product types.
**Status:** LOCKED

---

## What this lock protects

This lock freezes the state of the public Product Factory menu after the menu cleanup. Two source files were intentionally modified for this change; their md5s are recorded in `PUBLIC_FACTORY_MENU_CLEANUP_REGRESSION.json` (in this same directory) and must not drift without re-locking.

The cleanup itself is a market-quality, public-surface change. It does not alter generation logic, content rules, claim safety, or any product builder. The only behavioral change is: 4 unfinished product types no longer appear in the public picker, and a direct backend call to any of those 4 types returns a clear "not ready" 400 instead of producing placeholder output.

---

## What is hidden from the public picker

| Product type        | Reason for hide                                                            |
| ------------------- | -------------------------------------------------------------------------- |
| `marketing_kit`     | No working `/generate-marketing-kit` route. Builder is a placeholder/stub. |
| `cover_design`      | No recent customer-path proof. No current regression lock.                 |
| `flip_book`         | No recent customer-path proof. No QA.                                      |
| `planner`           | Generic Planner Generator is not market quality. Routes users to the locked Budget/Faith Planner V1 instead. |

Each of these 4 types carries `hidden: true` in its `PRODUCT_TYPES` entry in `flask_app/static/js/app.js`. `buildFactoryTypes()` filters with `!t.hidden` so they do not render as cards.

## What remains visible

| Product type        | Lock status                              |
| ------------------- | ---------------------------------------- |
| `ebook`             | Ebook Generator V1 LOCKED (2026-07-28)   |
| `coloring_book`     | Bold & Easy Kawaii Coloring LOCKED       |
| `word_search`       | Customer-path proof pending              |
| `crossword`         | Customer-path proof pending              |
| `math_worksheet`    | Customer-path proof pending              |
| `spelling_worksheet`| Customer-path proof pending              |

## Direct backend calls are guarded

If any caller hits `POST /generate-product` with a hidden product type, the route returns:

```
HTTP 400
{"error": "This product type is not ready yet."}
```

Guard implementation: a 4-line block at the top of `generate_product_route` in `flask_app/app.py`:

```python
_HIDDEN_PRODUCT_TYPES = {"marketing_kit", "cover_design", "flip_book", "planner"}
_requested = (body.get("product_type", "") or "").strip()
if _requested in _HIDDEN_PRODUCT_TYPES:
    return _error("This product type is not ready yet.", 400)
```

The guard runs BEFORE `generate_product()` is called, so no placeholder product is ever produced for the 4 hidden types.

---

## Locked decisions (do not change without re-locking)

1. **Marketing Kit, Cover Design, Flip Book, and generic Planner remain hidden from the public picker.** Re-enabling any of them requires a customer-path proof + a regression lock, the same bar as the other product types.
2. **Generic Planner Generator stays hidden.** The locked Budget Planner V1 and Faith Planner V1 are unaffected; users wanting a planner get those locked variants, not the generic stub.
3. **The 6 visible product types remain visible.** `ebook`, `coloring_book`, `word_search`, `crossword`, `math_worksheet`, `spelling_worksheet` are the only product types rendered as public cards.
4. **The post-save Next Steps panel on the Ebook Builder view must remain present and functional.** This is the user-facing customer flow for an ebook save.
5. **Saved Projects view must keep loading.** `isUserSavedProject` filter and `loadProjects` must continue to function.
6. **No production code is allowed to silently produce a placeholder product for any hidden type.** If a future caller bypasses the picker, the 400 guard must still fire.

---

## What is NOT affected by this lock

- **Ebook Generator V1** — Lock spec at `EBOOK_GENERATOR_V1_LOCK.md` (project root). The 2 fingerprints in that spec for `app.py` and `app.js` are EXPECTED to differ from the values in `PUBLIC_FACTORY_MENU_CLEANUP_REGRESSION.json`; that is the whole reason this separate file exists.
- **Budget Planner V1** — `BUDGET_PLANNER_V1_LOCK.md` unchanged.
- **Faith Planner V1** — `FAITH_PLANNER_V1_LOCK.md` unchanged.
- **Bold & Easy Kawaii Coloring Book** — `COLORING_BOOK_GENERATOR_LOCKED_STATE.md` unchanged.
- **Ebook Export Pipeline V2** — 10-check validator, unchanged.
- **All puzzle generators (Word Search, Crossword, Math Worksheet, Spelling Worksheet)** — unchanged.
- **The full product generation pipeline, the cover renderer, the PDF renderer, the ZIP packaging, the publishing studio, and the dashboard** — all unchanged.

---

## Allowed changes (no re-lock required)

- Adding NEW product types to the public picker (must follow the same customer-path-proof + regression-lock bar).
- Editing copy/labels on the 6 visible product cards.
- Updating the user-facing "not ready" message text in the backend guard, as long as the HTTP 400 contract is preserved.
- Editing `EBOOK_GENERATOR_V1_REGRESSION.json` to record new md5s for `app.py` and `app.js` (the Ebook Generator V1 lock has its own re-lock procedure).

## Disallowed changes (require re-lock)

- Re-enabling any of the 4 hidden product types in `PRODUCT_TYPES` without a customer-path proof.
- Removing the `_HIDDEN_PRODUCT_TYPES` guard from `app.py`.
- Weakening the 400 response to allow placeholder output for any hidden type.
- Hiding any of the 6 currently visible product types from the public picker.
- Removing the `postEbookNextSteps` panel from the Ebook Builder view.
- Breaking the `isUserSavedProject` / `loadProjects` Saved Projects view.
- Calling OpenAI, Tavily, or any LLM/provider from the hidden-type guard path.

---

## Regression fingerprint

See `PUBLIC_FACTORY_MENU_CLEANUP_REGRESSION.json` (in this same directory) for:

- `app.py` md5 after backend guard
- `app.js` md5 after hidden product filter
- Hidden / visible product type lists
- Expected backend behavior for each hidden type

**Approved post-lock fingerprint refresh** (2026-07-30 12:18 PT): `app.js` md5 was refreshed to `a4cd469cf7ce793cf33c0a892138212c` after the approved Product Planning → Product Builder handoff fix. The previous md5 (`ebea576e5138f41dfb6995bbeb04ab13`) is preserved in `previous_md5` for traceability. The handoff fix only added `resolveFactoryTypeFromPlan` + `hiddenReasonFor` and updated `sendToBuilder` and the Saved Projects row handler; it did not change the hidden-product filter, the backend guard, or any of the 6 visible product cards.

**Approved post-lock fingerprint refresh** (2026-07-30 18:25 PT): `app.js` md5 was refreshed to `7787b601e149d5c7f841d2c7e3f14348` after the approved Market Research → Factory → Downloadable Product flow upgrade. The previous md5 (`a4cd469cf7ce793cf33c0a892138212c`) is preserved in `previous_md5` for traceability. The flow upgrade added three approved UX changes inside `runProduct` and `renderProduct`: (1) auto-trigger PDF download on Generate success for the workflow case (the `wasWorkflow` branch calls `/export-product` after auto-save and fires `triggerDownload` on the PDF), (2) scroll the post-save Next Steps panel into view via a new `scrollNextStepsPanelIntoView` helper called right after `renderProduct`, and (3) a prominent "Download PDF" button on the product preview card (top-right of the title row) that reuses the same `/export-product` endpoint as the panel button. None of these changes alter the hidden-product filter, the backend 400 guard, the 6 visible product types, or any locked generator.
- Expected UI behavior for the public picker
- Confirmation that the post-save Next Steps panel and Saved Projects view remain intact
- Manual regression test steps

## Provenance

- Backup of the codebase before this change: `Product-Pipeline_BACKUP_2026-07-28_PRE_EBOOK_V1_LOCK.zip` (created during the Ebook V1 lock, unchanged by this cleanup).
- Lock files written from the live factory state on 2026-07-28.

---

**Current status: PUBLIC MENU CLEANUP LOCKED**

**Approved post-lock fingerprint refresh** (2026-07-30 19:00 PT): `app.js` md5 was refreshed to `f4e5658f1423086eb3d73d93773b2a15` after the approved **Build Product auto-fire fix**. The previous md5 (`7787b601e149d5c7f841d2c7e3f14348`) is preserved in `previous_md5` for traceability. The change is in `sendToBuilder()`'s ebook branch: after routing to the Ebook Builder view, the code now calls `runEbook()` so the user's one click on "Build Product" / "Send to Product Builder" produces the ebook without requiring a second click on "Generate Ebook". The misleading "click Generate Ebook to use it" toast was replaced with "Building your ebook from the research...". No backend changes, no locked generator behavior change, no PDF/ZIP/cover renderer change. `app.py` md5 unchanged.

**Approved post-lock fingerprint refresh** (2026-07-30 19:45 PT): `app.js` md5 was refreshed to `1bc136c7fad323277989b61a7b773acf` after the approved **Ebook Builder full-flow fix**. The previous md5 (`f4e5658f1423086eb3d73d93773b2a15`) is preserved in `previous_md5` for traceability. The change is in `renderEbook()`:
- Normalizes the data shape (d.content = d.ebook, d.title = d.source, d.product_type = 'ebook', d.fields = {}) so loadEbookEnhancements and the post-save panel can use the same field names the Product Factory path produces.
- Wires a preview-card Download PDF button (top-right of the title row) that reuses the same /export-product endpoint as the post-save panel.
- Auto-calls loadEbookEnhancements so the cover + visual plan render in the Ebook Builder view (previously only the Product Factory path did this; the Ebook Builder view showed only raw markdown with no cover).
- Auto-saves the ebook in place and renders the Post-Save Next Steps panel (Download PDF / ZIP / Open / Selling) when the ebook came in through the sendToBuilder workflow (pendingEbookBrief._project_id). One click on "Build Product" now lands the user on a saved, downloadable, cover-equipped ebook.

No backend changes, no locked generator behavior change, no PDF/ZIP/cover renderer change. `app.py` md5 unchanged.

**Approved post-lock fingerprint refresh** (2026-07-30 20:50 PT): `app.js` md5 was refreshed to `f59629484fb08e3a563a098ce8686da0` after the approved **full-pipeline fix**. The previous md5 (`1bc136c7fad323277989b61a7b773acf`) is preserved in `previous_md5` for traceability. Four approved UX changes that complete the Market Research -> Plan -> Build Product -> Downloadable Product chain:
1. `autoSaveEbookForWorkflow` now auto-fires the PDF download (with ZIP fallback) right after auto-save completes. The user always gets a downloadable file from one click on Build Product.
2. `renderEbook` now shows the Post-Save Next Steps panel directly for already-saved ebooks (skips the Save as Project bar), so reopening a saved ebook from Saved Projects lands the user on the download buttons immediately.
3. `runNextAction` (the Saved Projects 'Build Product' next-action) now auto-fires `runEbook` so a saved plan builds the ebook in one click (no second click on Generate Ebook).
4. `projectRow` now renders a direct 'Download PDF' and 'Download ZIP' button on every Saved Projects row, so the user can download any saved product without opening it first.

No backend changes, no locked generator behavior change, no PDF/ZIP/cover renderer change. `app.py` md5 unchanged.
