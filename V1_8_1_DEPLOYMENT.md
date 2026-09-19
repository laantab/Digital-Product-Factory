# v1.8.1 — the step-by-step screen moves to the builder

**Status: code and tests ready on `fix/v1.8.1-workspace-to-builder`.
Nothing has been pushed, merged or deployed. No production setting has
been changed.**

---

## What this release is

v1.8.0 moved the one-click **Build My Ebook** button off the web service.
It left the step-by-step ebook screen, the visuals buttons and the cover
buttons running inside the web process, and nothing forced anyone to look
at them.

On 2026-09-18, after the cutover, that gap reached production:

| Time (PDT) | What happened |
|---|---|
| 8:54 PM | `POST /ebook-workspace/11/generate-manuscript` returned **500** — the gunicorn worker was killed at the 120-second limit while writing chapters |
| 9:16–9:18 PM | Retry; manuscript generated and approved |
| 9:22 PM | **"Instance failed: Ran out of memory (used over 512MB)"**, instance restarted |
| All evening | The builder showed **0 runs**. It was never asked to do anything |

v1.8.1 closes it, and adds the thing whose absence allowed it: a registry
of every POST route, and a test that fails the release gate when a new one
is added without being classified.

---

## The owner's steps, in order

Do these one at a time. Stop at the first thing that does not match.

### 1. Merge (your decision, not done)

The branch is `fix/v1.8.1-workspace-to-builder`, based on `origin/main`.
Nothing is pushed.

### 2. Point the builder at the same commit — IMPORTANT

The website deploys from **`main`**. The builder service was created from
**`feature/v1.8.0-workflows`**.

If you merge v1.8.1 to `main` and change nothing else, the website will be
running v1.8.1 and the builder will still be running v1.8.0. A v1.8.0
builder does not understand a requested action: it would claim the job,
build the book straight through, and the photograph you chose would never
appear — with nothing in any log saying why.

**In Render, open the builder service (`digital-product-factory-builder`),
go to its settings, and change its deploy branch from
`feature/v1.8.0-workflows` to `main`.** Then both services always run the
same commit.

### 3. Check the versions match

```
GET /ebook/execution-mode
```

v1.8.1 adds two fields to this read-only page:

```json
{
  "execution_mode": "workflow",
  "website_version": "1.8.1",
  "builder_version_last_seen": "1.8.1",
  "ready": true
}
```

- `website_version` is what the web service is running, now.
- `builder_version_last_seen` is the version reported by the most recent
  builder run. **Empty means no builder run has ever reported** — which is
  exactly what was true on the evening of 18 September.

If the two versions differ, stop and fix step 2 before building anything.

The builder also prints its version in the first line of every run:
`Digital Product Factory workflow service starting (VERSION 1.8.1)`.

### 4. No new environment variables are required

v1.8.1 adds no new setting you must configure. One optional variable exists
for testing only:

| Name | Default | What it does |
|---|---|---|
| `FACTORY_PUBLISH_EXPORTS` | unset | Forces image publishing on or off. Unset is correct: publishing follows the execution mode by itself. |

**Anything you do add later must be added to BOTH services.** The builder
was given a copy of the website's environment variables on 2026-09-18, and
they do not stay in step on their own.

---

## What to expect on the live site

Using the step-by-step ebook screen, on a book you are willing to pay for:

1. **Continue Building returns within a couple of seconds** and shows
   progress, instead of hanging and then failing.
2. **The builder's Runs page in Render shows a run for that book** — exactly
   one, however many times you click.
3. **The website's memory stays flat** and it does not restart.
4. **Visuals and the cover appear on the screen**, and you can replace a
   photograph.
5. **The finished PDF and ZIP download.**
6. **The build stops and waits after each step** rather than running ahead.
   Approving a step is what lets it continue.

This is a paid build. It needs your go-ahead on the day.

---

## Rollback, unchanged

Delete `FACTORY_EXECUTION_MODE` on the web service and redeploy. Everything
returns to building inside the website, exactly as before v1.8.0. No data
migration is involved either way.

The new job-row columns (`requested_action`, `requested_action_at`,
`builder_version`) are added by `ALTER TABLE` at boot and are ignored
entirely in inline mode, so rolling back does not require removing them.

---

## What v1.8.1 deliberately does NOT move

Seven heavy routes still run in the web service:

`/export-product`, `/render-visual-image`, `/retry-ebook-visual`,
`/enhance-ebook`, `/generate-ebook`, `/ebook/regenerate-cover`,
`/projects/<id>/kdp/prepare-package`

They work on a `package_id` or an older non-workspace record rather than on
a step-by-step build, and the builder's only task is `build_ebook`, which
drives a step-by-step build. There is nothing for them to join yet.

They are **registered as heavy with that reason written down** in
`services/jobs/route_registry.py`, and the release gate will not let anyone
quietly forget them. Moving them needs a second builder task, which is its
own release.

Nine further heavy routes belong to the coloring book, crossword, word
search and planner product lines, and are registered the same way for the
same reason.
