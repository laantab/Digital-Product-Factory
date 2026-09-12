# Session Handoff — 2026-09-11, end of day (supersedes the 2026-09-11 morning handoff)

**Start a new session with:** "Read CLAUDE.md and the newest handoff first. Confirm the
current Factory path, current Git branch, current commit, and that the working tree is
clean before making any changes."

---

## CLOSEOUT — Word Search v1.7.2 (2026-09-11, night) — COMPLETE, verified live

The plan below ("TOMORROW — START HERE", "The approved-in-principle fix", "Push hold")
was carried out in full this same night, approved step by step, and is now closed. This
section is the current truth; the sections below it are kept as the historical record of
the investigation and the plan, unedited except for short "RESOLVED" notes pointing here.

- **Fix implemented exactly as planned**, commit `a021385`: `_resolve_word_search_words`
  now resolves Topic-mode words from the shared topic engine (mirrors
  `_resolve_crossword_words`); the OpenAI call and the ten-word placeholder are gone from
  `services/product.py`. `_word_search_pdf_payload` now passes the real `mode`, so the
  topic-relevance QA gate actually runs. A curated `flower_parts` family was added to
  `data/topic_vocabulary_packs.json` (pure pack data) so "Flower Parts" resolves to real
  flower anatomy instead of the older, broader `plant_parts` pack.
- **A standalone Factory Command Center** (`command_center/`) was also built this session,
  commit `e35654a` — see `command_center/README.md`. It now shows this release correctly:
  no open Word Search issue, `word_search_engine` good / 1.7.2 / `a021385`.
- **Released as Factory v1.7.2.** Fast Stability Gate: 148 passed, 603 subtests. Full
  Windows release gate: 2,647 tests, 0 failures, 0 errors, 0 skipped, 0 paid API calls
  (log: `Factory Control Center/Logs/full_release_gate_v1.7.2_20260911.txt`).
- **Pushed to `origin/main`**: `0a9a713`, `e35654a`, `a021385`, `e7a15fb`, `789371b`
  (`1c86c05..789371b`). Render redeployed automatically and was confirmed live at v1.7.2.
- **Verified on the live public site**, twice, through the actual customer UI
  (`digitalproductfactorypro.com` → Word Search → Topic mode → "Flower Parts"): the real
  rendered PDF's "Words to Find" is ANTHER, CALYX, COROLLA, FILAMENT, NECTAR, OVARY,
  PETAL, PISTIL, POLLEN, RECEPTACLE, SEPAL, STAMEN, STEM, STIGMA, STYLE. None of the
  retired placeholder words (apple, banana, cherry, dragon, energy, forest, garden,
  harbor, island, jungle) appear. QA passed both times.
- **Word Search last-known-good version:** `a021385` (v1.7.2) — the first last-known-good
  version this customer route has ever had. Crossword's last-known-good is unchanged,
  `e81298e`.

**Why you saw the old words even after the fix was written:** the fix lived only in this
local, uncommitted checkout until it was pushed above. A Flower Parts test run against
`digitalproductfactorypro.com` before the push was hitting the still-deployed v1.7.0
(`origin/main` at `1c86c05`), which is unrelated to whether the local fix was correct. See
the "Runtime audit" work earlier in this session's transcript if that comes up again — the
lesson: after any fix, confirm which checkout and which deployed commit you are actually
testing before concluding a fix did or didn't work.

## Tester invite protection — CLOSED (2026-09-11, night)

Read-only audit first, then the owner turned it on and verified it live; no code was
touched.

- **Audit result:** the invite-gate code (`app.py`, added in v1.7.1/`0a9a713`) was already
  correct, tested (`tests/test_invite_gate.py`, 14/14), and deployed — it was simply never
  switched on. No bypass found (only `/static/*` and the two signature-verified billing
  webhooks are exempt; `/admin/*` is gated by design); no secret found anywhere in source,
  git history, logs, HTML, JS, or live responses; the gate re-reads the environment on
  every request, so it survives restarts/redeploys with no caching involved.
- **`FACTORY_INVITE_CODE` is now active on Render.** No code release was required — this
  was a Render dashboard/environment change only.
- **Owner verified live, manually, in Incognito:** a fresh Incognito session is blocked by
  the invite page; the real code is accepted; the Factory opens normally after; a
  brand-new Incognito session asks for the code again (the 90-day cookie is per-browser-
  profile, as designed). Owner/admin access is unaffected — the owner enters the same
  shared code like any tester, by design (no separate admin bypass).
- **Not part of this task, still genuinely open:** whether OPENAI / TAVILY / PEXELS keys
  are set on Render (unrelated, unverified); whether Render's automatic health check (if
  any) targets a path other than `/` — worth a glance now that `/` requires the code.

## Cloudflare Email Routing (support@) — CLOSED (2026-09-11, night)

A read-only DNS audit earlier this session found Email Routing **not yet enabled** for
`digitalproductfactorypro.com` (no MX/TXT records existed at all — a clean slate, no
conflict either way). That finding is now superseded: the owner completed the setup in
Cloudflare directly and verified it live. Current state:

- Cloudflare Email Routing is **enabled** for `digitalproductfactorypro.com`; the required
  DNS records are active.
- The owner's private destination inbox is added and **verified** in Cloudflare (the
  address itself is deliberately not recorded here or anywhere in this repo).
- The routing rule exists: `support@digitalproductfactorypro.com` → that verified
  destination.
- **Owner sent a real test email to `support@digitalproductfactorypro.com` and it arrived
  successfully** at the verified destination.
- No Factory code change, no Render change, and no application deploy were required or
  made — this was entirely Cloudflare-side DNS/account configuration, exactly as the audit
  predicted it could be.

## Factory Market Advantage ("Find Top Opportunities") — RESOLVED (2026-09-11, night)

Live symptom: "Find Ideas for Me" → "Find Top Opportunities" returned "We couldn't
complete the market research. Your idea and filters have been preserved. Please try
again." on the public site.

- **Read-only diagnosis (this session) confirmed the Factory Market Advantage code itself
  was intact** — nothing in `services/market_research.py`, `services/factory_advantage.py`,
  or `ai_client.py` had changed since 2026-08-28/09-03, well before v1.7.1 or v1.7.2; no
  regression from this session's own releases. `discover_top_opportunities()` calls Tavily
  first and only reaches OpenAI if that succeeds; a missing/failing Tavily key alone is
  enough to produce exactly this message without OpenAI ever being invoked.
- Confirmed which environment variable names the code actually reads: `TAVILY_API_KEY`
  for Tavily; for OpenAI, `AI_INTEGRATIONS_OPENAI_API_KEY` first, then `OPENAI_API_KEY` as
  a fallback (`ai_client.py::_get_key_and_source`).
- **Root cause, confirmed by the owner: both `TAVILY_API_KEY` and
  `AI_INTEGRATIONS_OPENAI_API_KEY` were missing from Render.** Not a code defect.
- **Fix:** added both variables on Render, preserved the existing
  `AI_INTEGRATIONS_OPENAI_BASE_URL`, redeployed. No Factory code change.
- **Verified live** through the actual public customer UI: Find Top Opportunities now
  completes successfully.
- A related but separate symptom was also investigated this session — Render logs showing
  `401` on `/discover-products` and `/projects?factory_sources=1`, traced to the invite-gate
  cookie layer (confirmed same-origin, confirmed `fetch()`'s credentials default, no code
  fix identified or made). That thread was left with a decisive test for the owner to run
  (a fresh Incognito login) and is **not itself claimed resolved here** — this entry closes
  out only the confirmed, tested Tavily/OpenAI configuration gap above. If a 401 on those
  routes recurs, pick that investigation back up rather than re-diagnosing from scratch.

## TOMORROW — START HERE

1. **Confirm the ground.** In `Factory-v1.3` run `git status` (expect a clean tree) and
   `git log --oneline -3` (expect `main` to match `origin/main`, v1.7.2).
2. **Word Search, tester invite protection, support-email routing, and the Factory Market
   Advantage Tavily/OpenAI configuration gap are all closed — do not reopen or
   re-investigate any of them.** See "CLOSEOUT", "Tester invite protection — CLOSED",
   "Cloudflare Email Routing (support@) — CLOSED", and "Factory Market Advantage
   ("Find Top Opportunities") — RESOLVED" above for the proof. If a report of bad Word
   Search vocabulary comes in again, first confirm which site/version was actually tested
   (see the runtime-audit lesson above) before assuming the code regressed.
3. **Pick the next item from "Still open" below.** Nothing is mandated — every active
   engineering/ops task from this session is closed; everything remaining is the owner's
   choice (key rotation, the v2 marketing plan, etc.).

---

## What the owner completed on 2026-09-11 (evening, reported by the owner)

1. Custom domain is live: `https://digitalproductfactorypro.com`.
2. Render custom domains verified, certificates issued.
3. Render support confirmed the site works after the Cloudflare/Render domain issue.
4. Render service upgraded from Free to the $7/month instance (0.5 CPU, 512 MB RAM).
5. 10 GB persistent disk added at `/var/data`.
6. Render environment variables added:
   - `FACTORY_DB_PATH=/var/data/projects.db`
   - `FACTORY_EXPORTS_DIR=/var/data/exports`
   - `FLASK_EXPORTS_DIR=/var/data/exports`
   (Both exports variables are read by the code: `database.py` prefers
   `FACTORY_EXPORTS_DIR` and falls back to `FLASK_EXPORTS_DIR`; the coloring-book
   modules read `FLASK_EXPORTS_DIR` directly. Setting both was correct.)
7. The Factory redeployed successfully and the live domain loads. A read-only GET of the
   home page tonight showed the footer marker **v1.7.0** and no invite prompt, so
   `FACTORY_INVITE_CODE` is not yet set on Render.
8. A separate Claude session verified locally that the database and product exports honor
   the persistent-storage paths (owner's report).

## What was done in this session (read-only audits, no code changed)

### Word Search regression: root cause (COMPLETE)

Live test on the domain: Word Search, subject "Flower Parts". Title correct, words wrong:
apple, banana, cherry, dragon, energy, forest, garden, harbor, island, jungle.

**Exact cause, three stacked defects, all in `services/product.py`:**

- `_resolve_word_search_words` (line ~556) is the function behind the Product Factory
  Word Search tile (`/generate-product`). In Topic mode it calls
  `suggest_words_from_topic` only as a yes/no pre-check and **throws the words away**,
  then asks OpenAI for a fresh list.
- When the OpenAI call raises for any reason (no key on the host, Safe Mode, network,
  quota), the `except Exception` at line ~602 substitutes the hard-coded string at
  line ~603: `"apple\nbanana\ncherry\ndragon\nenergy\nforest\ngarden\nharbor\nisland\njungle"`.
  That string is the whole source of the wrong words. It is a developer placeholder, not
  pack data, fixture data, or seeded data.
- `_word_search_pdf_payload` (line ~681) always passes `mode="custom_word_list"` to the
  PDF builder, even in Topic mode, so the topic QA check in
  `services/word_search/qa_agent.py::_check_topic_relevance` (which returns immediately
  unless `mode == "topic"`) never inspects the words. `validate_generated_product` only
  checks cover and answer key, not words.

**Reproduced locally, zero cost, under `FACTORY_TEST_MODE=1`** (outbound calls blocked):
the exact customer fields produced the ten fallback words and QA passed. The same topic
through the puzzle builder in topic mode (`build_word_search_pdf(mode="topic")`) produced
Leaf, Root, Stem, Flower, Petal, Sepal, Pollen, Seed, Stomata, Xylem from the local
`plant_parts` pack with no errors. The engine works; the route never asks it.

**Why "Flower Parts" specifically:** it matches the older per-product pack `plant_parts`
(keyword "flower") in `data/word_search_topics.json`, so the pre-check passed, the AI
call was attempted, it failed on Render, and the placeholder shipped with QA disabled.

**Why the protected tests did not catch it:**
- `tests/test_customer_journey_every_product_type.py` drives Word Search through
  `/generate-product` with topic "Ocean Animals". Under the suite's blanked API key the
  product it receives is the same ten fallback words with QA passed. The test only checks
  that a `qa_report` exists. Confirmed directly.
- `tests/factory_golden_customer_path_smoke_suite.py`, `tests/test_universal_topic_puzzle_engine.py`,
  and `tests/test_word_search_short_topic_repair.py` call the builder with `mode="topic"`
  directly, so they prove the engine, not the customer route.
- The pre-Git scripts `test_ws_topic_fix.py` and `test_phase5.py` (2026-07-10) posted to
  `/word-search-builder/generate`, the standalone page, which is not linked from the
  customer UI. They are not in the manifest.

**Why the 2026-09-09 "GREEN" verification did not catch it:** the Stability Matrix marks
Word Search green on live project 356 ("American Automobiles"). That project is in
`Factory Control Center\Backups\projects_pre_spelling_release_20260909.db`. Its words are
AMC, Acadia, Aerostar, Allante, Ambassador, Apache, Aspen, Aurora, Avalanche, Avenger.
Four of five checked appear in no local pack. The shared automobile pack begins Barracuda,
Bronco, Buick, Cadillac, which is what Crossword projects 363 and 364 contain from the same
day. Project 356's words came from OpenAI via the two real keys in the local `.env`. The
paid path worked locally, so the route looked fine. Render is the first host that ran this
route without a working OpenAI key. Same story for project 354 ("American Cars") and 335
("Farm Animals"). Note: projects 356 and 362 to 364 are not in the current `projects.db`
(113 rows) but are in that backup (126 rows).

### Version recovery audit (COMPLETE)

Nothing was lost, reverted, or overwritten.

- The shared engine (`services/factory/topic_vocabulary.py`, `data/topic_vocabulary_packs.json`)
  was created in `e81298e` (2026-09-09, v1.5.0 second commit) with alias matching and the
  BRAND_MODEL vs PART scope layer. It is **byte-identical** from `e81298e` through
  `0a9a713`. No later commit touched it, `word_entries.py`, `word_lists.py`, `book.py`,
  or either QA agent.
- Both product resolvers call the engine first: `services/word_search/word_lists.py`
  line ~225 and `services/crossword/word_entries.py` line ~148.
- Verified locally: "Automobile" and "American Automobiles" return brand/model words;
  "Car Parts" returns parts; nonsense topics fail closed in both products. The American
  Automobiles regression is protected by `tests/test_crossword_scope_answerkey_zip_repair.py`;
  the twelve golden topics and the no-AI-call rule for both products by
  `tests/test_universal_topic_puzzle_engine.py`. Both are in the fast gate.
- `_resolve_word_search_words` is identical from the Git baseline `444e88f` (2026-08-09)
  through `0a9a713`, on all four remote branches, on the rescued branch
  `onedrive-workspace-phase-a`, in the OneDrive archive `Factory_Stabilized_V2/flask_app`,
  and in the 2026-09-09 safety snapshot. The OpenAI call and the fallback predate Git.
- The Crossword customer route, `_resolve_crossword_words` (line ~1050), was already
  local, no-AI, and fail-closed at the baseline, and passes the real `mode` at line ~1209.
  It is the proven pattern the Word Search route needs.
- The engine commit `e81298e` changed `product.py` for Crossword and Spelling Worksheet
  only. Word Search's route was not part of that work.

| Factory version | Word Search route | Puzzle builder + engine | Commit | Date |
|---|---|---|---|---|
| pre-Git (Replit) | OpenAI + fallback (unproven) | Topic-pack fix v1 on the standalone builder | none | 2026-07-10 |
| baseline | same | same | `444e88f` | 2026-08-09 |
| 1.0.0 to 1.4.1 | same | same | `ef98680` to `8e724ea` | 08-24 to 09-04 |
| 1.5.0 | same | short-list repair, adaptive sizing, engine tests | `279415a` | 2026-09-09 |
| 1.5.0 (2nd) | same | **shared engine created**, scope layer, Crossword route fixed | `e81298e` | 2026-09-09 |
| 1.6.0, 1.7.0 | same | unchanged | `7759baa`, `e82d48c` | 2026-09-09 |
| 1.7.1 (local) | same | unchanged | `0a9a713` | 2026-09-11 |

- **Last known good version:** none for the tile route (never used local packs). The
  standalone builder and the Crossword route have been good since `e81298e`.
- **First bad version:** not applicable; the route was never right. v1.7.0 on Render is
  where it first became visible, because Render has no working OpenAI key.
- **Regression commit:** `444e88f` carries it in from before Git. No later commit changed it.
- **Good implementation exists in Git:** yes, on `main` today: the engine, the builder in
  topic mode, and the Crossword customer route.
- **Is production v1.7.0 missing code from an earlier release:** no.

### Two secondary scope gaps found while verifying the contract (pack data only)

- "Automobile Parts" phrase-matches the broad alias "automobile" and returns brands.
  `scope_by_alias` for PART lists "car parts", "automotive parts", "auto mechanics",
  "car maintenance" but not "automobile parts". One line in `data/topic_vocabulary_packs.json`.
- Crossword refuses "Flower Parts" (the `plant_parts` fallback pack has 12 words, below
  Crossword's minimum) while Word Search accepts it. A curated plants/flowers family in the
  shared pack file, with clues, would serve both products.

## The approved-in-principle fix — IMPLEMENTED as v1.7.2, commit `a021385` (see CLOSEOUT above)

Smallest permanent fix, no new vocabulary system, no topic special-cased. Implemented
exactly as written below, plus one addition found necessary during implementation: a
pre-existing bug in `tests/test_customer_journey_every_product_type.py`'s own Word Search
fixture (it used the field key `"topic"`, which the real form and resolver never read —
only `"theme"` — so that journey test had never really exercised topic resolution) was
fixed alongside the repair.

1. `services/product.py::_resolve_word_search_words`: in Topic mode use the words that
   `suggest_words_from_topic` already returns (it consults the shared engine first, then
   the older packs); raise the existing clear error when nothing matches; delete the
   OpenAI call and the placeholder string. Mirrors `_resolve_crossword_words`.
2. `services/product.py::_word_search_pdf_payload`: pass `mode="topic"` when the plan is
   not custom so the existing QA topic check runs. Custom lists unchanged.
3. New `tests/test_word_search_topic_scope_contract.py`: drive `/generate-product` in
   Topic mode for several ordinary topics (Flower Parts, Ocean Animals, Computer Parts,
   American Automobiles) with `ai_client.chat` patched to raise; assert every puzzle
   answer and answer-key word belongs to the resolved pack, none is on the generic
   blocklist in `services/factory/topic_intelligence.py`, `chat` is never called, an
   unknown topic returns the clear error with no PDF, and the placeholder string no
   longer exists in `services/product.py`.
4. Add the word assertion to the Word Search journey in
   `tests/test_customer_journey_every_product_type.py`.
5. Register the new test in `tests/acceptance_manifest.json`, the CLAUDE.md gate command,
   and `RUN_FACTORY_STABILITY_GATE.bat`. Bump `VERSION` to 1.7.2, add a plain-language
   `CHANGELOG.md` entry, run fast gate and full gate.

Optional follow-ups (pack data only): the "automobile parts" alias and a plants/flowers
family with clues.

## Push hold — RESOLVED, pushed (see CLOSEOUT above)

`0a9a713` (v1.7.1) was local only. It contains the invite gate, the Render first-boot DB
directory fix, and their tests. It did **not** contain the Word Search fix, and it
carried the same Word Search route as every earlier version. Owner's instruction: do not
approve that push until the regression audit is understood. The audit completed
(above), the fix was implemented as v1.7.2 on top of `0a9a713`, both gates ran green, and
the owner approved pushing both together — done, along with the Command Center commit and
two small bookkeeping commits. If another Claude session sees this note and is unsure
whether `0a9a713` is still held: it is not: `git log --oneline origin/main..HEAD` should
come back empty.

## Still open

- ~~Approve and implement the Word Search route fix (above), then release v1.7.2.~~
  **DONE** — v1.7.2, commit `a021385`. See CLOSEOUT above.
- ~~Push `0a9a713` and the fix together, only with the owner's go-ahead.~~ **DONE** —
  pushed and confirmed live. See CLOSEOUT above.
- ~~Render: set `FACTORY_INVITE_CODE` before inviting testers~~ **DONE** — see
  "Tester invite protection — CLOSED" below. Still open from this bullet: confirm
  whether OPENAI / TAVILY / PEXELS keys are set on Render (unrelated to the invite
  code, still unverified). Word Search no longer needs a key (fixed).
- ~~Verify on the live domain after deploy: create a Word Search "Flower Parts" in Topic
  mode and confirm the word list is flower-part vocabulary~~ **DONE, twice** — see
  CLOSEOUT above. Still open from this bullet: Manual Deploy → Restart still needs a
  check; confirm Saved Projects still lists prior projects and download still serves
  from `/var/data` after this deploy.
- ~~Cloudflare Email Routing for `support@digitalproductfactorypro.com`.~~ **DONE** —
  see "Cloudflare Email Routing (support@) — CLOSED" above.
- New Tavily and Pexels keys (rotation open since August). Partially addressed:
  `TAVILY_API_KEY` and `AI_INTEGRATIONS_OPENAI_API_KEY` are now confirmed present on
  Render (added to fix Factory Market Advantage, see "RESOLVED" above) — whether that
  Tavily value is the intended rotated/new key, or the same one from before, was not
  stated. Pexels key rotation is untouched and still open.
- Day 3 of the v2 plan: Founding Member product in Lemon Squeezy, first 10 messages.
- Day 4: MiniMax keys into Pin Factory Pro; 50 real pins.
- Rescued branch `onedrive-workspace-phase-a`: archive at owner's discretion.
- Plain-language manuscript panel (held by owner). Cover-editor console error (harmless).
- Per-member invite codes, real accounts, plan-limit enforcement: Month 2.

## Source of truth

Only `C:\Users\user\Documents\Product-Pipeline\Factory-v1.3` on branch `main`.
`Factory_Stabilized_V2` and the OneDrive snapshots are archives for reading only.

---

## Earlier today (morning session, kept for the record)

The Factory is on **v1.7.1** locally (private-beta invite gate + Render first-boot fix).
Full Windows release gate on this commit: **2,613 tests, 0 failures, 0 errors,
0 skipped, 0 paid API calls.** Fast Stability Gate: 139 passed, 595 subtests.

Strategy has moved from "build features" to "put the Factory in front of ten paying
Founding Members." The plan is in `Factory Control Center\Marketing\Digital Product
Factory Pro - Marketing & Launch Master Plan v2 (Execution Edition).md` (also a Google
Doc). Day 1 of that plan was executed this morning. Read Part 18 of it before marketing work.

1. **Audit (read-only)** of the whole product for the v2 plan. Key facts, all verified:
   - 8 builders live; 6 are zero-cost (planners, puzzles, worksheets).
   - Ebook: 12 real projects in the DB, 1 reached export, and it shows "Needs correction."
     Cost caps in code ≈ $2.35–3.10 per book. Founder-assisted only at beta.
   - Billing layer (Lemon Squeezy + Stripe) is built and tested but switched off;
     no user accounts exist; Free-plan cap is displayed, not enforced.
   - Pin Factory Pro v1.3.0 is on GitHub (`laantab/pin-factory-pro`), mock mode only
     (MiniMax keys empty), not wired to the Factory.
2. **Invite-code gate** (`app.py`): when `FACTORY_INVITE_CODE` is set on the host, every
   route except `/static/*`, `/billing/webhook/*` and `/invite` requires the code (cookie,
   `X-Factory-Invite` header, or `?invite=CODE` once → 90-day cookie). Unset → gate off.
   Under `FACTORY_TEST_MODE` the gate is always off; `tests/conftest.py` also blanks the
   variable so a local `.env` value can never gate the suite.
3. **Render first-boot fix** (`database.py::get_conn`): creates the DB's parent directory,
   so `FACTORY_DB_PATH=/var/data/projects.db` works on an empty disk.
4. Tests: `tests/test_invite_gate.py` (14), `tests/test_render_persistence_patch.py` (2);
   both in `acceptance_manifest.json`, the `.bat` gate and the CLAUDE.md gate command.
   `.env.example` documents `FACTORY_INVITE_CODE`.
5. **Beta Launch Kit** (no code): `Factory Control Center\Marketing\Beta Launch Kit\`
   — Founders page copy, outreach messages, beta agreement + welcome email, tester
   scorecard + bug log. All drafts; the offer is $149 one-time, 10 seats, 90 days,
   14-day build-or-refund, $29/mo Founder rate locked afterwards.
