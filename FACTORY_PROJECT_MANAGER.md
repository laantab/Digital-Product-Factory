# Factory Project Manager — limited-pilot readiness

Updated: 2026-09-25 (Claude, chat session)

## Live
- main: a582639 (Factory 1.9.7, PR #25), deployed to website and builder 2026-09-25 07:15.

## In progress: Factory 1.9.8 (branch launch-sweep, from a582639)
| Area | Result |
|---|---|
| Container Gardening stuck at 90% | Real cause: export stage never recorded (export_ready false, only HTML listed). Needs ONE export-only run (owner authorized); blocked on a backup copy of the current PDF/ZIP first, because a new export overwrites the same storage keys. |
| Endless "Picking this back up" | Fixed: queued > 15 min shows Paused + Continue. Test fails without fix. |
| Real titles hidden ("SAT Test Prep", "QA ...", "Seed ...") | Fixed in is_customer_clutter_record. 8 of 13 new checks failed before the fix. |
| Three old test failures | All environment assumptions in tests, not product defects. Guards kept: tests never use the real DB; verify fails closed without R2; Command Center names Factory-v1.3. |
| Live security (no login) | /projects, /projects/5, downloads, build status, preview, build start, admin backup, register: all 401. |
| Mobile | Sidebar hidden below md; dropdown nav replaces it (index.html). Not screenshot-verified (browser window would not resize). |
| Protected products | 190 protected tests passed; lock checks passed. |

## Not yet done (pilot sweep)
- Container Gardening export + post-export verification (needs backup first).
- Real-photo cover inspection by Editor-in-Chief.
- Full Windows gate on 1.9.8 (via Save-and-Test .bat).

## Spending
- Container Gardening: 26 paid calls / $4.10, unchanged. No paid calls this session.
