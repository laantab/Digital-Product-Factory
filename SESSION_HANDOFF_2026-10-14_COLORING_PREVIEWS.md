# Coloring preview page counts — v1.9.40

Owner explicitly requested entering a small page count to preview a coloring
book after the v1.9.39 website refused two pages. PR58:
https://github.com/laantab/Digital-Product-Factory/pull/58.

## Behavior

The shared coloring-only normalizer preserves 1–100 instead of expanding small
counts to twelve. Existing one-page Single Sheet behavior remains intact. Books
with two or more interiors retain their additional cover. The workflow validates
invalid counts before dispatch. The form explains small previews. HTTP 400
settings errors take precedence over keyword-based interrupted-build guidance.
No new service, schema, secrets, hosting configuration, or production generation.
Do not regenerate or export finished Project20 to test this release.

## Evidence

Verified production main before editing: merge06ce55c, v1.9.39. Initial local
checkout was older; fetched main and created an isolated branch without deleting
or overwriting older work. Restored pinned requirements-dev dependencies.
Baseline Fast Gate: 726 passed. After-change Fast Gate: 734 passed.
Exact two- and four-page artwork calls and real PDF/ZIP files passed. Browser
checks passed for 2, 4, and 12 interiors through validation guidance, refresh and
real PDF/ZIP downloads. No paid providers were called.

The first focused run had two stale browser expectations because wording changed
while that process was running; original report is retained. The final unchanged
browser suite passed all three cases. The first full release run caught the
new changelog entry missing required customer-facing headings. Corrected the
release note; all 40 version/registry/enforcement checks then passed. The complete second full release gate passed exactly 3087 unique cases across
221 files: zero missing/duplicate cases, failures, errors or skips. Source compile,
JS syntax and manifest/JUnit validation passed. Reports remain under
/workspace/scratch/14eabf73e52d/release-1940-preview-final-results. A photo-test
partition stopped writing progress output while receipts continued; the final
full report is PASS, and an isolated check of that photo case also passed.

Verified remote core1316a4261c11ca73a2600824302a886d3f990146 has tree
0e52ed85f26c055dbf5cfc326df9da74ff9dce86, identical to local core8b6bfbb.
Word Search, Coloring Book and Crossword are relocked at that tested source.
The coloring normalizer is now an explicit protected dependency.

## Remaining

Publish final metadata, merge PR58, verify the
website deployment and its visible v1.9.40 preview hint. Builder auto-deploys main,
but its successful deployment must be independently confirmed. Render connector returns404 for workflow deploy lookup, but list_logs accepts
its resource ID wfl-damqq8uk1f9s738jtgc0. Read-only logs verified the previous
commit06ce55c checkout, successful build and VERSION1.9.39 startup. Use those
same resource logs to verify the new commit and VERSION1.9.40 after merging;
no dashboard login or new production book is needed. Do not infer builder
version from the website alone.
