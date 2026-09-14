# Upgrade 0 — Production Architecture Blueprint

Started 2026-09-14. This is the Factory's foundational reliability work —
deliberately numbered *before* the feature-upgrade roadmap
(`command_center/roadmap.json`, Upgrades 1–6), because none of that feature
work is safe to build on top of a production path that cannot be trusted
to finish what it starts.

## Why this exists

Between v1.7.6 and v1.7.10, four separate live-production defects surfaced
in the ebook one-click build, one after another, each only visible on a
real live build — the Full Release Gate was green (2800+ tests) before,
during, and after every one of them:

1. **v1.7.6** — a stalled build's "Try again" button never called `/advance`
   again once failed; a stage's attempt ceiling was never reset. Fix:
   an explicit "Resume Build" action.
2. **v1.7.7 → v1.7.8** — the manuscript stage silently routed chapter
   generation to the owner's local Ollama instance on the hosted server.
   A first fix (detect the hosting platform, refuse local routing) did not
   hold on the next live build — the detection signal was never verified
   against the real runtime. The durable fix flipped the *default*: local
   generation is opt-in only; missing/wrong configuration means the paid
   cloud provider, on any hosting platform, with nothing left to detect.
3. **v1.7.9** — a manuscript with real, fixable QA findings was treated as
   a dead end instead of using the Factory's own existing correction
   system, and a failure-recording code path was overwriting the database
   with a stale pre-attempt snapshot, silently erasing chapters and spend
   already recorded.
4. **v1.7.10** — the manuscript stage wrote an entire book inside one
   synchronous HTTP request. A production web server's own request
   timeout does not know a multi-minute manuscript write is legitimate;
   it kills the worker mid-write. Fixed by bounding every request to one
   chapter's worth of work, reusing the existing checkpoint/resume loop.

None of these were caught by tests because tests do not exercise a real
hosting platform, a real request-timeout boundary, or a real multi-attempt
customer session. **A green gate is necessary but not sufficient proof that
the live path works.** This blueprint exists so the *next* new product
type, integration, or feature is designed against these lessons from the
start, instead of rediscovering each one live, one at a time.

## Immediate priority (unchanged by anything below)

**Production Reliability Architecture → Ebook pilot → 3 successful live
ebook builds in a row.**

Nothing in this document — including the Pin Factory Pro section below —
changes this. No other upgrade, and no downstream-distribution work, is
safe to start until the ebook one-click build has completed, end to end,
on the live site, three times in a row without a code change in between.
Current count toward that milestone: **0** — v1.7.10 is deployed and
awaiting the owner's next live retest.

## Durable architectural principles (from this sprint, apply everywhere)

- **Fail closed to the safe path by default.** A feature that is only safe
  in one environment (a developer's own machine, a specific host) must
  require an explicit, opt-in signal to activate — never activate by
  default and require an opt-out. An unset variable is the *normal* state
  for a hosted deployment, not a rare edge case.
- **Every long-running stage is checkpointed and resumable, and no stage
  writes an unbounded amount of work inside one request.** A production web
  server's request timeout is real and will kill a request regardless of
  whether the work behind it is legitimate. Bound the unit of work per
  request; let the existing poll/advance loop carry the rest.
- **Recording a failure may only add information — it can never erase
  progress already saved during the same attempt.** Re-read persisted
  state before writing a failure record; never write a snapshot captured
  before the work ran.
- **An existing repair/correction system must be automatically reachable**
  by the automated path, not stranded behind a manual-only trigger that the
  automatic build never calls.
- **Proof order for anything touching the live customer path:** targeted
  tests → broader protected tests → Fast Gate → Full Gate → commit/push/
  deploy → a real live retest. Do not call a live-production defect fixed
  until the live retest confirms it, no matter how green the gate is.

## Open items

- Live retest of v1.7.10 (bounded incremental manuscript generation) —
  pending the owner.
- The exact Render Start Command / Gunicorn `--timeout` value has never
  been confirmed (it lives only in Render's dashboard, not in this repo).
  Confirming it, and considering a modest increase as additional margin,
  remains a reasonable follow-up — v1.7.10 no longer depends on that
  number for correctness, but it's still worth knowing.

---

## Future Distribution Layer — Pin Factory Pro

**DESIGN NOW — IMPLEMENT AFTER THE CORE FACTORY IS PRODUCTION-STABLE.**

Do not migrate, merge, or implement Pin Factory Pro during Upgrade 0. Do
not change Pin Factory Pro code. Do not change Pinterest configuration. Do
not start Pinterest approval work. Do not add new infrastructure solely
for Pin Factory Pro during Upgrade 0.

Pin Factory Pro is intended to eventually join the Digital Product Factory
Pro ecosystem, but it is a **downstream distribution/marketing system**,
not part of the critical product-generation path. The point of designing
this now is narrow: so the production architecture above does not have to
be redesigned later just to make room for it. Nothing in this section is
built during Upgrade 0.

### Target future flow

```
IDEA → PRODUCT CREATION → QA → APPROVAL → EXPORT → READY-TO-SELL PACKAGE
     → MARKETING PACKAGE → PIN FACTORY PRO → PINTEREST DISTRIBUTION
```

**The product must remain complete and downloadable even if Pin Factory
Pro or Pinterest is unavailable.** Everything below exists to guarantee
that, structurally, once this is ever built.

### 1. Integration boundary

Pin Factory Pro sits entirely *after* export, consuming a finished product
the same way a customer's own download does — it never reaches back into
generation, QA, approval, or export. The boundary is one-directional and
one-way-triggered: Digital Product Factory Pro emits an event/record when
a product reaches COMPLETE/APPROVED; Pin Factory Pro reads that record on
its own schedule. Digital Product Factory Pro never calls into Pin Factory
Pro synchronously as part of the product-generation path, and never blocks
on its response.

### 2. Standard completed-product payload

A stable, versioned package Pin Factory Pro (or any future downstream
consumer) could read once a product is COMPLETE/APPROVED:

- `product_id`, `product_type`
- `title`, `subtitle`, `description`
- `approved_cover` (URL/reference to the final, approved cover asset —
  never a working/draft copy)
- `approved_marketing_images` (list; same approved-only rule as the cover)
- `keywords`
- `product_url` (where the customer's finished product/listing lives)
- `listing_copy`
- `metadata` (open, versioned bag for anything a specific channel needs
  later — e.g. Pinterest board hints, Etsy category — without forcing a
  payload-schema change per channel)

This payload is a **read-only projection** of already-approved data. It
never carries draft content, in-progress QA state, or anything not yet
approved — there is no version of this payload for a product that hasn't
reached COMPLETE/APPROVED.

### 3. Downstream job type

A future job type — `CREATE_MARKETING_ASSETS` or `SEND_TO_PIN_FACTORY` (name
TBD when actually built) — that may only be enqueued *after* the
underlying product's status is COMPLETE/APPROVED. Enqueuing it is not part
of the export transaction; it is a separate, best-effort follow-on action
triggered by the product reaching that status, using the same durable,
checkpointed job pattern this blueprint already establishes above (bounded
unit of work, resumable, failure never erases prior progress).

### 4. Failure isolation

A Pinterest/Pin Factory failure must **never**:

- invalidate the finished product
- block product download
- force product regeneration
- alter the approved PDF
- alter the approved cover

The downstream job is additive only. Any failure in it is logged and
retried on its own terms, entirely outside the customer's product-delivery
path. The customer's product is never touched again once it reaches
COMPLETE/APPROVED, regardless of what happens downstream of it.

### 5. Separate credentials and provider configuration

Product generation, Pinterest/Pin Factory, and any other future
distribution system each hold their own, independently-scoped credentials
and configuration. None of them share a variable, a client, or a failure
mode with another — the same principle this sprint already applied inside
product generation itself (each provider's configuration is explicit and
independently fails closed) extends outward to each distribution channel.
A Pinterest outage or misconfiguration can never touch product-generation
credentials or behavior, and vice versa.

### 6. Idempotency

The same durable, key-based idempotency pattern already used for
manuscript generation and correction extends to distribution: a repeated
`CREATE_MARKETING_ASSETS`/`SEND_TO_PIN_FACTORY` job for the same product
must be safe to run twice — keyed so a retry, a duplicate enqueue, or a
crash-and-resume can never create duplicate Pinterest posts or duplicate
marketing jobs for the same approved product.

### 7. Future customer-facing surface

Eventually, Pin Factory Pro should be able to appear *inside* Digital
Product Factory Pro as a customer-facing module (e.g., "Promote this
product" alongside the existing download actions) while remaining
operationally separate underneath — its own service, its own credentials,
its own failure domain, reached only through the read-only payload and the
downstream job type above. The customer-facing surface is a thin
presentation layer over that boundary, not a merging of the two systems.

### 8. Future integration points (hooks only, not built)

The same completed-product payload and downstream-job pattern should
generalize to other future distribution channels without redesign:

- Pinterest (via Pin Factory Pro)
- Etsy listing assistance
- KDP marketing
- other future distribution channels

**Do not over-engineer these now.** The architectural hook — a stable
completed-product payload, a downstream job type gated on
COMPLETE/APPROVED, isolated credentials, isolated failure domains, and
idempotent jobs — is what's needed. Nothing channel-specific is designed
or built until each channel is actually taken up as its own piece of work.
