# Session Handoff — 2026-08-29 (supersedes 2026-08-28)

**Start a new session with:** "Read flask_app/SESSION_HANDOFF_2026-08-29.md and continue."

---

## PICK UP HERE — one known blocker, everything else is green and pushed

`origin/main` is at **40c78b7**. Working tree clean. Release gate **1056 passed,
0 failed, 0 paid API calls**.

### THE BLOCKER (start here)

**The Ebook Project workspace cannot be started from the UI.** Build This
Product now correctly creates a workspace (that bug is fixed), but the
workspace then sits at stage 1 with no way forward:

* workspace state is `next_action: "run_research"` with **every gate false**
  (`manuscript_enabled`, `visuals_enabled`, `export_enabled` … all `false`)
* the "Next production action" block at `static/js/app.js:6854` only renders a
  button for `generate_manuscript` or `request_correction`. For `run_research`
  it renders `""` — no control at all.
* the backend route **exists** (`POST /ebook-workspace/<id>/research`,
  `app.py:514`) and accepts findings directly:
  `save_research(data, body.get("research") or body)`
* but `static/js/app.js` **never calls it**. The only `/research` call in the
  file is the unrelated Factory Market Advantage one at line ~6004.

Gates cascade from research, so nothing downstream unlocks: no manuscript, no
cover, no export, and therefore no PDF/ZIP and no Editor-in-Chief review.

**Proposed fix (agreed direction, NOT yet implemented):** Build This Product
already *comes from* research, so the handoff should **seed the research it
already has** into the new workspace instead of asking the user to redo it.
That lands the customer at Title/Outline with gates open. Probably also wire a
visible `run_research` control for workspaces started by hand from the Ebook
Builder. The owner was asked to confirm before this was built — confirm first.

---

## What was fixed today (all pushed, all gate-verified)

### 1. Public URL infrastructure — DONE and live
`digitalproductfactorypro.com` serves the app through a Cloudflare named
tunnel (`factory`, id `22b5092a-5efe-477d-82db-1b25ddf35b1b`,
config `C:\Users\user\.cloudflared\config.yml` → `http://localhost:5055`).
Nameservers had propagated; `cloudflared tunnel login` completed; a stray
Namecheap parking A-record was overwritten with `--overwrite-dns`.

**Not durable:** the tunnel runs ad hoc in a terminal, NOT as a Windows
service. It dies on reboot. Decision deferred.

### 2. Lemon Squeezy webhook — one clean entry
The owner's dashboard edit created a *second* webhook rather than editing the
first. Ended with `130242` (correct URL + the 5 tested events); `107556`
deleted. Deleting it exposed a real bug: `_lemon_request` called `resp.json()`
unconditionally and crashed on Lemon Squeezy's `204 No Content`. Fixed with 3
regression tests (`362d4c1`).

### 3. Factory Market Advantage — degraded-mode defects (`e383d01`)
Found by running a real research with a dead OpenAI key:
* the page printed the **raw provider exception** — an OpenAI 401 echoing a
  masked-but-identifiable key — straight into the results card. Fixed at all
  four leak sites, including `/research` returning `str(exc)` as its `error`.
* the input-backed draft read as **broken mad-libs** ("budget planner for young
  families Budget Planner"; "addressing families overspend because …"). Three
  causes: `_idea_name`, `_as_need_phrase`, `_restates`.
* headings said **"Why We Recommend It"** above a "Needs Improvement" verdict.
  Headings now follow the BUILD / IMPROVE / AVOID decision.

### 4. Build This Product refused buildable types (`13186be`)
Live research names products in prose, so the router saw "Printable inventory
and meal planning workbook" and matched the incidental modifiers
"printable"/"planning" **before** the product noun "workbook" — routing a
workbook to the hidden generic planner.

**The routing is implemented twice** — `resolve_factory_builder()` (Python) and
`resolveFactoryTypeFromPlan()` (JS) — and they had drifted. The button is
driven by the JS copy, so fixing only Python left the message on screen. Both
now test the head noun first. The JS copy also had **no faith/budget planner
heuristic at all**, so a described "undated faith planner for busy moms" was
blocked too.

### 5. `.env` authority + the key saga (`13186be`)
* A revoked `TAVILY_API_KEY` left in the **Windows user environment** silently
  beat the working key in `.env` (python-dotenv leaves already-set vars alone).
  Deleted, and `load_dotenv` now passes `override=` explicitly.
* **Important carve-out:** `override=True` unconditionally BROKE the paid-call
  guard — `test_ebook_real_browser_customer_path.py` starts an isolated server
  as a **subprocess** with API keys blanked, and that subprocess runs outside
  conftest's network guard. Overriding refilled them with live credentials.
  Now `override=not FACTORY_TEST_MODE`: the harness owns the environment in
  tests, `.env` wins otherwise. The gate caught this.
* `.env` had a **BOM** (from PowerShell 5.1 `Set-Content -Encoding UTF8`) that
  corrupted the *name* of the first variable, so
  `AI_INTEGRATIONS_OPENAI_API_KEY` read as unset while looking perfect in an
  editor. Stripped; the new key scripts read utf-8-sig and write without a BOM.
* `PEXELS_API_KEY` had been overwritten with the Tavily key. Restored from the
  original value; verified via the app's own auth check (Pexels' *search*
  endpoint returns 200 even for a junk or empty key — it proves nothing).

**Key-entry tooling added:** `Set_OpenAI_Key.bat`,
`Set_OpenAI_Key_From_File.bat` (Notepad-based, for when console paste fails),
`scripts/set_openai_key.py`, `Setup_API_Keys.bat`. All verify the key with
OpenAI **before** writing, so a bad paste can never replace a working key, and
write `OPENAI_API_KEY` + `AI_INTEGRATIONS_OPENAI_API_KEY` together.

### 6. The ebook could not be saved, and was never reviewed (`40c78b7`)
The reported bug. Both symptoms were one cause: Build This Product handed the
ebook to the **legacy one-shot generator** (`services/ebook.py`: *"LEGACY …
Cannot create Export Ready workspace ebooks"*), which returns prose and
nothing else. No package → no PDF/ZIP. And because the Editor-in-Chief runs
inside `/export-product`, a book that never exports is **never reviewed**.

**The Editor-in-Chief was never missing or broken — it was never called.**
It lives in `services/editor_in_chief_ebook.py`, invoked at `app.py:2848`.

Both ebook entry points now create a workspace: `buildThisProduct()` (the FMA
button — **this is the one customers click**) and `sendToBuilder()` (saved-plan
button). Fixing only `sendToBuilder` is why the first attempt still failed in
the browser; there were three entry points.

### 7. The systemic fix the owner asked for (`40c78b7`)
`tests/test_customer_journey_every_product_type.py`, registered in
`tests/acceptance_manifest.json`. 1047 tests passed while a customer could not
save a book, because the suite tested *components* and never the *promise*.

Nine tests over the real HTTP routes. Six full journeys — `generate → save →
export → download` for word search, crossword, coloring book, math worksheet,
faith planner, budget planner — each asserting a PDF **and** a ZIP that
download, bytes matching the recorded sha256, a real PDF inside the ZIP, and a
recorded review **with the expected reviewer pinned per type**. Plus three
guards: a new sellable type can't ship without a journey, hidden types stay
refused, and every ebook entry point must reach the exportable pipeline.

Verified by restoring the old routing and watching it fail for the right
reason, then restoring the fix.

**Finding worth acting on:** review keys are inconsistent across the
catalogue — `qa_report` (puzzles/worksheets), `qa_result` (coloring book),
`editor_in_chief` (planners/ebooks). That inconsistency is part of why "is
this reviewed?" was hard to answer. Worth unifying.

---

## Standing open items

1. **The blocker above** — workspace cannot be started from the UI.
2. Make the Cloudflare tunnel durable (Windows service) or accept ad hoc.
3. Owner must finish **Lemon Squeezy's business-details form** with
   `https://digitalproductfactorypro.com`.
4. Cosmetic: `".,"` collision when an AI-generated idea name ends in a period
   (`recommended_mvp_text`).
5. Unify the three review-key names.
6. Retire `Update_API_Key_Anywhere.bat` — it writes a BOM and updates only one
   of the two OpenAI key names.
7. Long-standing: enforce plan limits in `/generate-product`; rotate Tavily +
   Pexels keys; real user accounts before live payments; 1.5 GB DB purge;
   OneDrive move; public repo visibility.

## Working notes

* `use_reloader=False` — **kill and relaunch the app after every code change.**
  Several "the fix didn't work" moments today were just a stale process.
* Hard-refresh the browser (Ctrl+F5) after editing `static/js/app.js`.
* Run `preflight_check.py` before and after every change. It caught two real
  defects today that the browser did not, and the browser caught two the gate
  did not. Both are needed.
* The owner's app runs on **port 5055** (`_run_factory_5055.py`).
