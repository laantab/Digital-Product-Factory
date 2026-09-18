# v1.8.0 — the builder is its own machine

**Status: code and tests ready. The paid Render infrastructure has not been
created. Nothing in production has changed.**

---

## What went wrong

A live Resume Build for *Container Gardening for Beginners* pushed the
Render web service past its memory limit. The book was being written
inside the same process that serves pages, so one customer's build could
take the whole site down with it.

v1.7.24 already moved the build off the **browser** and onto the server —
that is why "you can leave this page" is true. v1.8.0 moves it off the
**web service**.

## What replaces it

```
CUSTOMER
   |
   v
FLASK WEB SERVICE  ── writes a durable job row, asks Render to run it,
   |                   returns immediately. Builds nothing.
   v
RENDER WORKFLOW TASK  ── own instance, own CPU and RAM, started on demand,
   |                     gone when the book is done.
   |                     manuscript → correction → Pexels visuals → cover
   |                     → design → preview → preflight → PDF/ZIP export
   v
POSTGRESQL (progress)  +  R2 (artifacts)
```

The handover is a **row**, not a message. The job table, the lease, the
checkpoints, the attempt ceilings and the orchestrator are all unchanged
from v1.7.29. The only thing that moved is which process calls `advance`.

### Why Workflows and not an always-on Background Worker

An always-on worker with enough memory to write an illustrated book is
paid for every hour of every day, including the many hours when nobody is
building anything. Product generation is bursty. A Workflows task starts
when a book starts, gets up to 1 CPU and 4 GB, and stops when the book is
done.

Verified against Render's own documentation, September 2026:

| | Always-on Background Worker | Workflows task |
| --- | --- | --- |
| Memory available | 512 MB at $7/mo; 4 GB needs the 2 CPU / 4 GB plan at **$85/mo** | up to **1 CPU and 4 GB** on `flex` |
| Billing | every hour, whether building or idle | **$0.20 per active CPU-hour + $0.05 per active GB-hour**, prorated by the second |
| Idle cost | full plan price | **nothing** |
| Queuing, scheduling, retries | our own code | managed |
| Run length | unlimited | 2 h default, **up to 24 h** |

Sources: <https://render.com/docs/workflows>,
<https://render.com/docs/workflows-limits>,
<https://render.com/docs/workflows-sdk-python>, <https://render.com/pricing>.

---

## The switch

One variable decides which machine builds books.

| `FACTORY_EXECUTION_MODE` | Behaviour |
| --- | --- |
| unset, empty, or anything unrecognised | **inline** — exactly v1.7.29. The web process ticks and builds. |
| `workflow` | The web process writes the job, triggers a Render task, and **never advances a build**. |

A typo means inline, deliberately: a misspelt variable must never silently
stop books being built.

**The rollback for the whole of v1.8.0 is deleting one environment
variable.** No redeploy of a different commit, no database change.

### What workflow mode turns off in the web service

| Path | Inline | Workflow |
| --- | --- | --- |
| Boot ticker (`runner.start`) | starts | does not start |
| Request-traffic tick (`runner.tick_soon`) | may tick | refuses |
| `POST /ebook/build/<id>/advance` | advances one stage | returns read-only status, `advanced: false` |
| `GET /ebook/build/<id>/status` | read-only | read-only |
| Saved Projects | read-only | read-only |

All four are gated by one function, `runner.executor_enabled()`, plus the
explicit check in `/advance`. A second copy of the decision somewhere else
is a second thing to forget.

**The browser script was deliberately not changed.** `_ebookBuildLoop` in
`static/js/app.js` calls `/advance` on a timer and stops when the status
says finished, failed or paused. In workflow mode that route returns
read-only status, so the same loop becomes a polite progress poller that
still ends correctly — and an old tab left open on an old version behaves
the same way. Changing the script as well would have added a second place
where the modes have to agree, for no behaviour that is missing.

---

## Environment variables

Names only. No value in this repository, and none is ever logged or
returned by a route.

**Web service**

| Name | Required | Notes |
| --- | --- | --- |
| `FACTORY_EXECUTION_MODE` | to cut over | set to `workflow` |
| `FACTORY_WORKFLOW_TASK` | in workflow mode | `<workflow-service-name>/build_ebook` |
| `RENDER_API_KEY` | in workflow mode | used only to start a task |
| `FACTORY_WORKFLOW_TASK_TIMEOUT_SECONDS` | no | default 7200 |

**Workflow service** — the same durable state as the website:
`FACTORY_DB_BACKEND=postgres`, `DATABASE_URL`, `FACTORY_STORAGE_DRIVER=r2`,
`FACTORY_R2_ACCOUNT_ID`, `FACTORY_R2_ACCESS_KEY_ID`,
`FACTORY_R2_SECRET_ACCESS_KEY`, `FACTORY_R2_BUCKET`, `SECRET_KEY`,
`OPENAI_API_KEY`, `PEXELS_API_KEY`, `TAVILY_API_KEY`, and optionally
`FACTORY_WORKFLOW_PLAN` (default `flex`).

**No `OLLAMA_*` variable is set on either hosted service.** Absent means
the cloud provider is used. Local Windows keeps its Ollama configuration
in its own `.env`, untouched by this release.

---

## Verifying a deploy without opening a shell

```
GET /ebook/execution-mode
```

```json
{
  "execution_mode": "workflow",
  "workflow_task": "digital-product-factory-builder/build_ebook",
  "render_api_key_configured": true,
  "task_timeout_seconds": 7200,
  "ready": true,
  "reason": ""
}
```

It reports whether a credential is configured, never what it is.
`ready: false` with a reason means the service would accept books and
build none of them — that is also logged at boot, so it is visible before
a customer is waiting.

---

## Safety properties, and the test that holds each one

Every one of these is covered in `tests/test_ebook_workflow_execution.py`.
No paid provider is called anywhere in that file: the orchestrator is
stubbed and the Render SDK is replaced with a recorder.

| Property | Why it matters |
| --- | --- |
| Default is inline | Merging v1.8.0 changes nothing until a variable is set |
| The job row is written **before** Render is asked for anything | Render being down costs a delay, never a book |
| A trigger failure never reaches the customer | Build still returns 200 |
| Five clicks start one task | Five instances racing one chapter, and five bills, is the failure |
| The duplicate guard is one conditional UPDATE | Two web instances share no memory, only the row |
| The cooldown expires | A task that died before claiming anything does not strand the book |
| A retried run never rebuilds a finished book | No second PDF, no second ZIP, no second bill |
| A task started for one book never touches another | A run id stays meaningful |
| Two tasks cannot both own one book | The second stops rather than fights |
| The task stops before its deadline | Ending cleanly beats being killed mid-chapter with a live lease |
| A transient error leaves the book retryable | A provider timeout must not destroy a customer's book |
| Status and Saved Projects never advance a build | Polling is read-only |
| No credential value appears in any response | |
| The entrypoint holds no build logic | `workflow_task.py` may not call `advance_build` |

---

## Creating the infrastructure — the owner's step

This costs money and has not been done.

1. In Render, create a **Workflows** service from this repository.
   - Runtime `python`, region `ohio` (same as the database and website).
   - Build `pip install -r requirements.txt`.
   - Start `python workflow_task.py`.
2. Set the workflow service's environment variables from the table above.
3. Note the workflow service's name. The task slug is
   `<that name>/build_ebook`.
4. Create a Render **API key** and set `RENDER_API_KEY` on the **web**
   service.
5. Set `FACTORY_WORKFLOW_TASK` on the web service to the slug from step 3.
6. Deploy the web service. Confirm `/ebook/execution-mode` reports
   `execution_mode: inline` and `ready: false` — nothing has changed yet.
7. **Cut over:** set `FACTORY_EXECUTION_MODE=workflow` on the web service.
   Confirm `/ebook/execution-mode` reports `ready: true`.

`render.yaml` in this repository describes the same shape and is
reviewable, but it is not applied automatically: the existing web service
was created by hand and keeps its own settings.

---

## Production acceptance plan

Run in this order. Stop at the first failure and delete
`FACTORY_EXECUTION_MODE` to roll back.

1. `/ebook/execution-mode` reports `ready: true`.
2. Web service logs at boot: `factory execution mode: workflow
   (in-process executor not started)`.
3. Start one short ebook. The Build response returns in under two seconds.
4. In Render, one task run appears for that project — **exactly one**.
5. Close the browser entirely. Wait.
6. Re-open Saved Projects: the book has progressed with no client
   involved.
7. Web service memory during the build stays flat at its idle level.
8. The book reaches export. `ebook.pdf` and `package.zip` download.
9. Click Continue on the finished book: no second task run starts, and no
   second export is produced.
10. Click Continue five times on a stalled book: exactly one new task run.

## Rollback

| Step | Effect |
| --- | --- |
| Delete `FACTORY_EXECUTION_MODE` on the web service | The web process ticks and builds again, immediately, as v1.7.29 |
| Leave the workflow service in place | It costs nothing while no task runs |

No data migration is involved either way: both modes read and write the
same job rows, the same PostgreSQL and the same R2 bucket. A book part-way
through when the switch is thrown is picked up by whichever executor is
enabled, from its last checkpoint.

The two added columns (`workflow_run_id`, `workflow_triggered_at`) are
added by `ALTER TABLE` at boot and are ignored entirely in inline mode, so
rolling back does not require removing them.
