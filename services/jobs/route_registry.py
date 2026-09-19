"""Every POST route, classified — v1.8.1.

WHY THIS FILE EXISTS
--------------------
v1.8.0 moved the one-click "Build My Ebook" button off the web service and
onto the builder. It left every other route that does heavy work running
inside the web process, and nothing anywhere forced anyone to look at them.
On 2026-09-18 that gap showed up in production: a customer used the
step-by-step screen, `POST /ebook-workspace/11/generate-manuscript` was
killed at the 120-second gunicorn timeout, and a few minutes later the
512 MB instance ran out of memory and restarted. The builder showed zero
runs all evening. It was never asked to do anything.

The defect was not any single missed route. The defect was that missing a
route had no consequence. This registry is the consequence: every POST
route in `app.py` is named here and classified, and
`tests/test_post_route_registry.py` fails the release gate when a route is
added, renamed or removed without being classified.

WHAT "HEAVY" MEANS, EXACTLY
---------------------------
A route is HEAVY when, running inside the web process, it can plausibly
exceed the 120-second request timeout or the 512 MB instance limit. In
practice that means it does one or more of:

  * writes or rewrites manuscript text
  * downloads or generates an image
  * builds or re-renders a cover
  * renders a preview
  * builds a PDF
  * builds a ZIP

Everything else is LIGHT: it reads, validates, records a decision, or
edits a small amount of JSON on the project row, and returns promptly.

A route that is heavy for some request bodies and light for others is
HEAVY. `/ebook-workspace/<id>/visuals` approves in a millisecond and
replaces a photograph in thirty seconds; classifying by the worst case is
the only classification that is safe to act on.

THE TWO KINDS OF HEAVY
----------------------
`handoff="builder"` — the work belongs to a running ebook build, so in
workflow mode the route records the requested action on the durable job
row and asks the builder to do it. This is the treatment v1.8.1 ships.

`handoff="deferred"` — the route is genuinely heavy, but it is not part of
an ebook build (it belongs to the coloring book, crossword, word search or
planner product lines), and the builder's only task is `build_ebook`.
There is nothing to hand these to yet. They are recorded here, with a
reason, so that they are impossible to forget and so a later release that
adds a second builder task has the list already written. They are
UNCHANGED by v1.8.1: they behave in workflow mode exactly as they behave
today.

Deferring is a stated, reviewable decision. Silence was the defect.
"""
from __future__ import annotations

#: Classification values.
LIGHT = "light"
HEAVY = "heavy"

#: What a heavy route does in workflow mode.
BUILDER = "builder"       # hand the action to the ebook builder
DEFERRED = "deferred"     # no builder task exists for this work yet

#: Reasons, so the classification can be argued with rather than trusted.
_R_EBOOK = "part of an ebook build; the builder owns it"
_R_OTHER = ("not an ebook build; the builder's only task is build_ebook, so "
            "there is nothing to hand this to until a second task exists")


_R_LEGACY = ("the builder's only task is build_ebook(project_id), which drives the workspace build. This route works on a package_id or a legacy non-workspace record instead, so there is no build for it to join. Registered heavy so it cannot be forgotten; unchanged by v1.8.1.")


def _h(path: str, why: str, handoff: str = BUILDER, note: str = "") -> dict:
    return {"path": path, "weight": HEAVY, "handoff": handoff,
            "why": why, "reason": note or (_R_EBOOK if handoff == BUILDER else _R_OTHER)}


def _l(path: str, why: str) -> dict:
    return {"path": path, "weight": LIGHT, "handoff": "", "why": why, "reason": ""}


#: Every POST route in app.py. Order follows app.py so a reviewer can read
#: the two side by side.
ROUTES: tuple[dict, ...] = (
    _l("/invite", "checks an invite code against a stored value"),

    _h("/planner/cover-photos", "downloads photograph search results",
       DEFERRED),
    _l("/planner/cover-photo/select", "records which photograph was chosen"),

    _l("/billing/account", "reads the billing account row"),
    _l("/billing/checkout", "creates a checkout session at the payment provider"),
    _l("/billing/webhook/stripe", "records a payment event"),
    _l("/billing/webhook/lemonsqueezy", "records a payment event"),

    _l("/research", "starts a research request and returns its handle"),

    _h("/generate-ebook", "legacy non-workspace path: writes a whole ebook",
       DEFERRED, _R_LEGACY),
    _l("/ebook-workspace", "creates the workspace row"),
    _l("/ebook-workspace/<int:project_id>/research", "records research input"),
    _h("/ebook-workspace/<int:project_id>/run-research",
       "paid research provider calls inside the request"),
    _h("/ebook-workspace/<int:project_id>/title-options",
       "paid provider call inside the request"),
    _h("/ebook-workspace/<int:project_id>/outline-options",
       "paid provider call inside the request"),
    _l("/ebook-workspace/<int:project_id>/approve", "records an approval"),
    _l("/ebook-workspace/<int:project_id>/title", "stores the chosen title"),
    _l("/ebook-workspace/<int:project_id>/outline", "stores the chosen outline"),
    _l("/ebook-workspace/<int:project_id>/estimate-cost", "arithmetic on the outline"),
    _l("/ebook-workspace/<int:project_id>/cancel-estimate", "clears a stored estimate"),
    _l("/ebook-workspace/<int:project_id>/authorize-budget",
       "records the customer's spend authorisation"),

    _h("/ebook-workspace/<int:project_id>/generate-manuscript",
       "writes every chapter; this is the route that returned 500 at the "
       "120-second timeout on 2026-09-18"),
    _h("/ebook-workspace/<int:project_id>/correct-manuscript",
       "rewrites chapters against the approved outline"),
    _l("/ebook-workspace/seed-acceptance", "copies approved inputs between projects"),

    _h("/ebook-workspace/<int:project_id>/visuals",
       "prepare, replace-photo, ai-alternative and retry-automatic download "
       "or generate images; approve and accept are light, but the worst case "
       "decides"),
    _h("/ebook-workspace/<int:project_id>/cover",
       "pexels-search, pexels-select, editor, select and fixture fetch "
       "photographs and re-render cover layouts"),
    _h("/ebook-workspace/<int:project_id>/cover-image",
       "decodes an uploaded photograph and re-renders every cover layout"),
    _h("/ebook-workspace/<int:project_id>/design",
       "stages a theme, which re-renders the designed book"),
    _h("/ebook-workspace/<int:project_id>/preview",
       "renders the designed preview of the whole book"),
    _l("/ebook-workspace/<int:project_id>/preview-opened",
       "records that the preview was opened"),
    _h("/ebook-workspace/<int:project_id>/preflight",
       "runs hard design preflight across the whole book"),
    _l("/ebook-workspace/<int:project_id>/rewind", "moves the rail backward"),

    _l("/generate-ad", "assembles ad copy from stored fields"),
    _l("/generate-traffic-content", "assembles copy from stored fields"),
    _l("/save-ad-set", "stores an ad set"),
    _l("/generate-promotion-package", "assembles copy from stored fields"),
    _l("/generate-launch-package", "assembles copy from stored fields"),
    _l("/market-research", "a bounded research call, returns promptly"),

    _h("/generate-product", "builds a coloring book or puzzle book, including "
       "its images and its PDF", DEFERRED),
    _h("/enhance-ebook", "legacy path: completes an ebook and runs the quality "
       "pipeline over it", DEFERRED, _R_LEGACY),

    _l("/ebook/save", "stores edited ebook fields"),
    _h("/ebook/regenerate-cover", "re-renders the factory ebook cover",
       DEFERRED, _R_LEGACY),
    _h("/retry-ebook-visual", "downloads a replacement stock photograph",
       DEFERRED, _R_LEGACY),

    _l("/discover-products", "reads stored product ideas"),
    _l("/factory-market-advantage", "reads a stored summary"),
    _l("/research-to-builder", "copies research into builder fields"),
    _l("/youtube/analyze", "fetches a transcript and summarises it"),
    _l("/youtube/search", "a search call, returns promptly"),
    _l("/youtube/save-resource", "stores a resource row"),
    _l("/generate-product-plan", "assembles a plan from stored fields"),
    _l("/save-product-plan", "stores the plan"),
    _l("/generate-publishing", "assembles publishing copy"),
    _l("/save-publishing", "stores publishing fields"),

    _h("/render-visual-image", "generates an image", DEFERRED, _R_LEGACY),
    _h("/export-product", "builds the product PDF and ZIP", DEFERRED,
       "exports every product type, not only ebooks; " + _R_LEGACY),

    _l("/ebook-release-check", "reads stored state and reports readiness"),
    _l("/generate-seller-package", "assembles copy from stored fields"),
    _l("/generate-sales-page", "assembles copy from stored fields"),
    _l("/generate-product-ad", "assembles copy from stored fields"),

    _h("/ebook/build", "starts the whole build; handed off since v1.8.0"),
    _h("/ebook/build/<int:project_id>/advance",
       "advances one stage; refuses to build in workflow mode since v1.8.0"),
    _h("/ebook/build/<int:project_id>/resume",
       "resumes the build; handed off since v1.8.0"),

    _l("/projects", "creates a project row"),
    _l("/projects/<int:project_id>/revisions", "stores a revision row"),
    _l("/projects/<int:project_id>/kdp/preflight", "checks stored state"),
    _h("/projects/<int:project_id>/kdp/prepare-package",
       "builds the KDP package files", DEFERRED, _R_LEGACY),

    _l("/admin/backup-db", "copies the database file"),
    _h("/admin/storage-migration", "moves stored artifacts in bulk", DEFERRED,
       "an owner-operated admin action, never on a customer's request path"),

    _h("/cover/preview", "renders a cover preview image", DEFERRED),
    _l("/cover/save", "stores the chosen cover fields"),
    _h("/cover/regenerate", "generates new cover artwork", DEFERRED),
    _h("/cover/apply-to-pdf", "rebuilds the product PDF and ZIP", DEFERRED),
    _h("/cover/upload-image", "decodes and re-renders an uploaded cover image",
       DEFERRED),

    # Blueprint routes (routes/crossword_builder.py, routes/word_search_builder.py).
    # These are not in app.py at all, which is exactly why this registry is
    # built from the live url_map and not from reading one file.
    _h("/crossword-builder/generate", "builds a crossword PDF", DEFERRED),
    _h("/word-search-builder/generate", "builds a word search PDF", DEFERRED),
)

_BY_PATH = {r["path"]: r for r in ROUTES}


def classify(path: str) -> dict | None:
    """The registry entry for a route path, or None if it is not registered."""
    return _BY_PATH.get(str(path))


def is_heavy(path: str) -> bool:
    entry = classify(path)
    return bool(entry and entry["weight"] == HEAVY)


def hands_off_to_builder(path: str) -> bool:
    """True when workflow mode must give this route's work to the builder."""
    entry = classify(path)
    return bool(entry and entry["weight"] == HEAVY
                and entry["handoff"] == BUILDER)


def registered_paths() -> frozenset[str]:
    return frozenset(_BY_PATH)


def heavy_paths(handoff: str | None = None) -> frozenset[str]:
    return frozenset(r["path"] for r in ROUTES if r["weight"] == HEAVY
                     and (handoff is None or r["handoff"] == handoff))
