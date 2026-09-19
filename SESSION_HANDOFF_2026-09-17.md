# Session handoff — 2026-09-17

## Start here

**v1.8.0 is written and tested. Nothing in production has changed, and
nothing will until one environment variable is set.**

The work is on branch `feature/v1.8.0-workflows`, cut from the production
commit `47393a0` (v1.7.29). The only thing left is creating the paid
Render Workflows service, which is the owner's decision.

Read `V1_8_0_WORKFLOWS_DEPLOYMENT.md` for the steps, the acceptance plan
and the rollback. Double-click `Verify_v1.8.0_Workflows.bat` on the PC to
check the branch locally; it writes a report to the Desktop and opens it.

---

## Two things that must not be misread

### 1. The old worker branch is dead

`feature/v1.8.0-background-worker` exists only on the PC. It was never
pushed, and its approach — an always-on Render Background Worker — was
abandoned. **Do not merge it.** Everything worth keeping from it has been
rewritten for Workflows on the new branch.

### 2. This release is inert until switched on

`FACTORY_EXECUTION_MODE` unset means the Factory behaves exactly as
v1.7.29 did. That is also what every local Windows checkout uses,
permanently. Merging and deploying this release changes nothing on its
own.

---

## What was wrong

A live Resume Build for "Container Gardening for Beginners" pushed the
Render web service past its memory limit. The book was being written
inside the process that serves pages, so one customer's build could take
the whole site down.

v1.7.24 moved the build off the **browser**. This moves it off the **web
service**.

## What was decided

Render **Workflows**, not an always-on Background Worker.

Product generation is bursty: a customer clicks Build, then nothing
happens for hours. An always-on worker with enough memory to write an
illustrated book costs $85 a month whether or not anyone is building one.
A Workflows task starts when a book starts, gets up to 1 CPU and 4 GB, is
billed at $0.20 per active CPU-hour plus $0.05 per active GB-hour, and
costs nothing while idle. Verified against Render's own documentation on
2026-09-17.

## What was built

| File | What it does |
| --- | --- |
| `services/jobs/mode.py` | The one switch. `inline` (default) or `workflow`. Anything unrecognised is inline, so a typo cannot stop books being built. |
| `services/jobs/dispatch.py` | The single place that decides who builds. `app.py` calls `hand_off` and knows nothing about modes. |
| `services/jobs/workflow_trigger.py` | Writes the durable job **first**, then asks Render to start a task. Never raises into a request. |
| `services/jobs/workflow_runner.py` | What a task actually does. No cloud SDK, so it is fully testable on the PC. |
| `workflow_task.py` | The Render entrypoint. Registers the task at `flex` (1 CPU / 4 GB) with three retries, and delegates. |
| `services/jobs/store.py` | Two new columns and a conditional-UPDATE duplicate guard; `claim_for_project` so a task only ever works on its own book. |
| `services/jobs/executor.py` | `run_project` alongside `run_one_job`, sharing one driver. |
| `services/jobs/runner.py` | Refuses to tick at all in workflow mode — the boot thread and `tick_soon` behind one gate. |
| `app.py` | Boot logging, `hand_off` on build and resume, `/advance` refuses to build in workflow mode, read-only `GET /ebook/execution-mode`. |

The ebook engine was not touched. Every stage, gate, attempt ceiling and
checkpoint is exactly as v1.7.29 shipped. The job row is still the durable
handover; only the process calling `advance` moved.

## What the tests hold

`tests/test_ebook_workflow_execution.py` — 50 checks, zero paid API calls.
The orchestrator is stubbed and the Render SDK is replaced by a recorder,
so nothing in it touches a network or a provider.

One real defect was caught while writing them: `run_build` re-opened a
SUCCEEDED job, so a Render retry of a run that had actually finished would
have rebuilt the whole book — a second PDF, a second ZIP and a second bill.
Fixed, and the test that caught it is
`test_a_retried_task_never_rebuilds_a_finished_book`.

---

## Open, and whose it is

| Item | Whose |
| --- | --- |
| Create the Render Workflows service and cut over | **Owner** — costs money |
| Run `Verify_v1.8.0_Workflows.bat` on the PC and commit/push from there | Owner |
| Relock `invite_protection` after `app.py` changed | Done on this branch |
| Delete or ignore `feature/v1.8.0-background-worker` on the PC | Owner |

## Nothing was pushed

The branch is committed locally in this session's checkout. Per the
standing orders, pushing is the owner's call.
