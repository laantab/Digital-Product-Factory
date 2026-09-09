# FACTORY_BLUEPRINT.md — Digital Product Factory, permanent north star

This file is the project's permanent north star. Every Claude session must read
it **before** changing anything, together with `PROJECT_STATUS.md` (live status)
and the most recent `SESSION_HANDOFF_*.md` (narrative context). This file does
not change from task to task; status files do.

Version anchors: the app is a Flask backend (`app.py`), front end `static/js/app.js`,
entry launchers `_run_factory_5055.py` / `_run_factory_5077.py` (no reloader —
kill and relaunch after every code change). Tests live in `tests/`
(`tests/acceptance_manifest.json`, driven by `scripts/run_factory_tests.py`;
`preflight_check.py` is the single zero-paid-call release gate).

---

## 1. Mission

Build a beginner-friendly Digital Product Factory that takes an ordinary user
from:

**market opportunity → product idea → professional finished product →
downloadable sales package**

The Factory must create high-quality, commercially useful digital products that
a customer could reasonably sell on Etsy, Gumroad, Lemon Squeezy, Amazon KDP,
or their own website.

This is a guided production system — research, writing, design, editorial
review, approval, saving, reopening, and export — not merely a collection of
one-shot generators. Simple enough for a first-time user; powerful and
dependable underneath.

## 2. Primary business goal

Every feature must support at least one of:

1. Help the user find or validate a profitable opportunity.
2. Help the user create a high-quality product.
3. Prevent weak, incomplete, or incorrect products from being presented as finished.
4. Make the product easy to edit, approve, save, reopen, download, package, and sell.
5. Reduce confusion and unnecessary user decisions.

Do not add complexity merely because it is technically interesting.

## 3. Beginner-first user experience

Assume many users are not programmers, designers, marketers, or publishers. The
interface must:

* Use plain, friendly language.
* Give one clear recommendation and one obvious next action.
* Avoid overwhelming users with technical details, raw scores, logs, and large
  walls of text. Keep advanced evidence behind expandable sections.
* Explain errors in plain language and state exactly what to do next.
* Preserve the user's work on navigation, save, reopen, or error.
* Avoid unnecessary forms and repeated questions.
* Never make the user use project numbers when recognizable product names exist.
* Use consistent action labels: Create Product, Build Product, Open Product,
  Edit, Approve, Save, Download.
* Clearly distinguish DRAFT, AWAITING APPROVAL, APPROVED, and LOCKED.
* Never claim a product is ready when required stages or files are missing.

A new user must always understand: **Where am I? What is done? What needs
attention? What should I do next?**

## 4. Core production workflow

1. Find or enter an idea.
2. Research demand, competition, customer need, profit evidence, and the
   opportunity to stand out.
3. Recommend the best opportunity in simple language.
4. Build the selected product as a DRAFT.
5. Generate or assemble the written content.
6. Create a professional cover and interior design.
7. Add appropriate visuals (photos, illustrations, diagrams, charts, tables,
   checklists, or other useful graphics).
8. Run automatic Editor-in-Chief quality review.
9. Show a clear visual review and approval stage.
10. Build a complete preview.
11. Save without losing approved work.
12. Reopen the saved product reliably.
13. Export the final PDF and ZIP sales package.
14. Offer publishing and marketing help only after quality review passes.

A later stage must never silently rebuild, replace, downgrade, or erase an
approved earlier stage.

## 5. Supported products

Ebooks, workbooks, planners, coloring books, word-search books, crossword-puzzle
books, math worksheets (grades 1–12), flip books, cover designs, KDP packages,
marketing kits, video scripts, founder launch kits, and other useful digital
downloads supported by market research. Each builder may have specialized
requirements, but all share the same quality, lifecycle, saving, approval, and
export principles.

## 6. Product quality standard

Work must look intentionally designed, not raw AI text pasted into a PDF. Check
every applicable product for:

* Relevance to the promised topic and audience
* Accuracy and internal consistency
* Useful, substantial content
* Clear organization
* Natural, human-sounding writing
* Repetition, filler, contradictions, unfinished sections
* Plagiarism or excessive similarity
* Spelling, grammar, punctuation, formatting
* Suitable reading level (≈8th grade for standard nonfiction; ≈6th grade when
  simplicity matters most; technical topics may use appropriate vocabulary)
* Professional cover design
* Consistent typography, colors, spacing, and page hierarchy
* Proper margins and page breaks
* Readable tables, charts, checklists, callout boxes
* High-resolution, relevant visuals with correct placement and captions
* No missing/broken images, no distortion, clipping, unsafe title placement, or
  unreadable cover text
* Complete table of contents when appropriate
* Correct page count and answer keys when required
* Valid PDF and ZIP exports
* Commercial usefulness and reasonable customer value

Humor is welcome when natural; clarity and usefulness come first.

## 7. Editor-in-Chief requirement

The Editor-in-Chief is a **real release gate, not a decorative score**. It must
automatically review content quality, topic relevance, completeness, plagiarism
risk, factual/internal consistency, grammar and readability, cover quality,
interior design, visual quality/relevance/resolution, charts/diagrams/tables,
broken or inappropriate assets, export integrity, customer usefulness, and
whether the product honestly qualifies as sellable. If a serious issue exists,
the product must remain DRAFT / AWAITING CORRECTION, with the issue explained
and one clear next action. The system must never label weak or incomplete work
"ready", "approved", or "sellable" merely because a generation function ran.

*Repo anchors:* `services/editor_in_chief.py`, `services/editor_in_chief_ebook.py`,
`services/editor_in_chief_planner.py`, `services/quality/`,
`services/ebook_qa_validator.py`. Note: review results currently use several
key names (`qa_report`, `qa_result`, `editor_in_chief`, `quality_result`) — a
known cleanup item to unify.

## 8. Visual-content requirements

Visuals must support the content, not decorate randomly. Use the most
appropriate type: stock photography, instructional illustrations, diagrams,
data charts, comparison tables, timelines, checklists, callout boxes,
worksheets, and decorative elements only when appropriate. A placeholder, prompt,
URL, filename, or broken image does not count as a completed visual.

Stock searches use short, content-aware terms. If stock results fail editorial
review, an approved AI-image fallback may be used only within the user's
authorized budget. Users should be able to review visuals on a clear contact
sheet and approve them together or request corrections. Do not send customers
away through prominent source links that advertise competitors; keep necessary
attribution professional and non-disruptive.

*Repo anchors:* `services/ebook_pexels.py`, `services/ebook_visual_pipeline.py`,
`services/ebook_visual_qa.py`, `services/ebook_interior_visuals.py`,
`services/visual_fallback.py`.

## 9. Cover requirements

Covers must be professional, relevant, readable, and salable: correct title,
subtitle, and author; strong visual hierarchy; readable typography; safe
margins; no clipped/duplicated text; no irrelevant badges or accidental wording;
no prompt text or system instructions; a full-bleed professional appearance when
appropriate; a visual style consistent with the interior; a reliable "Use This
Cover in PDF" action; and a cover download option. An attractive image alone is
not a finished cover.

*Repo anchors:* `services/cover_agent.py`, `services/cover_quality_agent.py`,
`services/product_cover_agent.py`, `services/ebook_photo_cover.py`,
`services/ebook_cover_local.py`. Cover gate tests: `tests/test_cover_regression.py`,
`tests/test_retail_cover_quality_lock.py`, `tests/test_export_cover_eligibility_pages.py`.

## 10. Saving and lifecycle protection

Lifecycle: **DRAFT → AWAITING APPROVAL → APPROVED → LOCKED**.

* DRAFT may be edited.
* Approval must be explicit.
* APPROVED content must not be silently rebuilt or replaced.
* LOCKED content is immutable except for clearly permitted metadata changes.
* Reopening restores the actual saved product and assets.
* Saved Projects display recognizable product names and types.
* PDF and ZIP downloads use the saved approved files whenever appropriate.
* Navigation, refreshes, errors, or reopening must not erase finished work.
* No accidental duplication from double-clicks.
* Every stage preserves the identity of the same project.

*Repo anchors:* `services/quality/artifact_state.py`, `artifact_identity.py`,
`services/product.py`, `database.py`. Tests: `tests/test_artifact_lifecycle_mutation_paths.py`,
`test_artifact_state_revision_primitives.py`, `test_publish_save_reopen_immutability.py`,
`test_save_state_enforcement.py`, `test_non_put_persistence_immutability.py`,
`test_locked_project_deletion.py`, `test_seller_launch_metadata_immutability.py`,
`test_controlled_revision_transition.py`.

## 11. Export requirements

For completed products, always provide a finished **PDF** and a **ZIP** sales
package. Additional KDP/Etsy/Gumroad/Lemon Squeezy/Zazzle/paperback packages are
created only when requested or clearly selected. Before presenting a download:
verify the file exists, opens, contains required pages and assets, belongs to
the correct saved project, and was not silently rebuilt from stale data.

*Repo anchors:* `services/pdf_export.py`, `services/packaging.py`,
`services/ebook_package.py`, `services/ebook_local_package.py`, `app.py`
`export_product_route`. Tests: `tests/test_download_slug_package_id.py`,
`test_export_pointer_sync.py`, `test_preview_save_export_identity.py`,
`test_reopen_packaging_identity_pass2.py`, `test_saved_project_download_buttons.py`,
`test_customer_journey_every_product_type.py`.

## 12. Market-research experience

"Find it. Prove it. Build it." Helps users with an idea and users without one.
Summarize demand, competition, customer need, profit evidence, and ability to
stand out. Lead with one Best Opportunity, explain why it is recommended, state
what to build, and provide one **Build This Product** action. Keep detailed
evidence behind "View Full Research & Sources". Research may create a DRAFT in
the correct builder, but it must never automatically spend money.

*Repo anchors:* `services/factory_advantage.py`, `services/market_research.py`,
`services/research.py`, `app.py` `factory_market_advantage_route` /
`research_to_builder_route`. Tests: `tests/test_factory_market_advantage.py`,
`test_research_to_build_handoff.py`, `test_choose_idea_build_handoff.py`.

## 13. External services and spending safety

Do not call OpenAI, Tavily, Pexels, paid image generation, or any other
paid/external service during testing unless explicitly authorized. Before any
potentially paid action, report: which service, why it is required, maximum
number of calls, maximum authorized cost, and what will be created or changed.
Never generate a product, regenerate approved content, spend money, approve a
stage, lock a project, publish, deploy, or commit without current-instruction
authorization. Use mocks or blocked-network tests for routine verification.

*Repo anchors:* `ai_client.py`, `services/ebook_pexels.py`, and the paid-guard
tests `tests/test_paid_image_authorization_guard.py`,
`test_paid_image_budget_controls.py`. Ebook workspace spending is separately
capped by a per-project budget ledger in `services/ebook_project_workspace.py`
(DEFAULT_BUDGET_CAP_USD = 3.50, paid-call ledger, cost estimates, explicit
confirm before any paid call).

## 14. Engineering and repair rules

Existing working application — do not rewrite from scratch. Before editing:
inspect the repository and git status; identify the actual customer-facing path;
locate existing shared services before duplicating; preserve unrelated user
changes; record the test baseline; trace the root cause; make the smallest safe
reusable correction. After editing: run focused tests first, then the full
release/preflight gate once focused work is green; require zero unexpected
failures and zero unexplained skips; confirm no external/paid calls; verify the
real browser/customer path when UI is affected; check save/reopen/preview/export
when applicable; report exactly what changed and what did not. Do not hardcode a
fix for one project number, title, image, or fixture. Do not weaken tests to
make them pass.

## 15. Communication requirements

Communicate in plain language. For every task, clearly separate: actions Claude
performs in code; commands the user must paste into a Terminal; values the user
must place in `.env`; browser actions the user must perform; and decisions only
the user can make. Give one recommended next step, never several conflicting
ones. When reporting completion, state: root cause, what was fixed, what was
tested, test totals, whether any external/paid calls occurred, whether anything
was generated/approved/locked/committed/pushed/deployed, and what the user
should visually review next. Never claim success from code inspection alone.

## 16. Definition of done

The Factory is ready to launch when a beginner can reliably: find or validate
an opportunity; select the recommended product; build a complete professional
product; review and correct content and visuals; approve each necessary stage;
save and reopen without data loss; download a verified PDF and ZIP; understand
exactly what to do at every point; and complete the workflow without confusing
placeholders, broken links, missing buttons, false success messages, or
unexpected charges. Result must be comparable in polish and ease of use to
established digital-product tools, with stronger research, quality control, and
guided production.

---

## Known gaps vs. this blueprint (as of 2026-09-01 audit)

These are captured here as durable context. The live, prioritized list lives in
`PROJECT_STATUS.md`.

1. **Ebook Project workspace cannot advance past Research from the UI.**
   A fresh workspace starts at `current_stage: "research"`, `next_action:
   "run_research"`, with empty research. The UI's "Next production action"
   control (`static/js/app.js:6854`) renders buttons only for
   `generate_manuscript` / `request_correction` / `correct_manuscript`, and the
   Research/Title/Outline stage panels are read-only with no generate or approve
   buttons. The backend routes for research, title, and outline exist; the
   front end never calls them. Gates cascade, so nothing downstream unlocks.
   This is the single most important launch blocker.
2. **Build This Product discards research when it creates an ebook workspace.**
   The workspace POST (`app.py:368`) accepts topic/audience/outcome/author but
   not the research the Factory already has, so a customer who did the research
   lands at an empty Research stage instead of a pre-seeded Title/Outline.
3. **Inconsistent review-key names** across the catalogue: `qa_report`,
   `qa_result`, `editor_in_chief`, plus `quality_result` in packaging/KDP.
   Confirmed live in 2026-09-01 audit; a unification cleanup is open.
4. **Cloudflare tunnel runs ad hoc** (dies on reboot); not yet a durable
   Windows service.