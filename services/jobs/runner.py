"""The in-process ticker that keeps builds moving — Phase 0B-5 slice.

WHY A THREAD IS ACCEPTABLE HERE, AND WHERE IT IS NOT ENOUGH
-----------------------------------------------------------
The rule is that a Render restart must not LOSE work. It does not: the
job is a row with a lease (services/jobs/store.py), and the orchestrator
checkpoints after every chapter. Kill this process mid-chapter and
nothing is lost — the lease expires and the next executor reclaims the
job and continues from the last checkpoint. No shutdown hook has to run.

So the thread is not where durability lives. Durability lives in the
table. The thread is only a heartbeat that says "is there anything to
do?", and it is disposable by design.

THE HONEST LIMIT
----------------
A thread inside the web service only ticks while that service is running.
If Render idles or stops the service entirely, nothing ticks until it is
woken — the work is safe and resumes, but it pauses. A separate Render
Background Worker removes that last gap, and it is the remaining step of
0B-5. This closes the defect that stranded a customer's book; it does not
yet make the Factory immune to an idle web service.

Every request also gets a chance to tick (see `tick_soon`), so a service
that is awake at all keeps books moving even if the thread is lost.
"""
from __future__ import annotations

import logging
import os
import threading
import time

log = logging.getLogger(__name__)

#: Seconds between ticks. Frequent enough that a book moves along briskly,
#: slow enough that an idle Factory costs nothing.
TICK_SECONDS = 20

#: Kill switch. Set FACTORY_EXECUTOR=off to return to browser-driven
#: builds -- the rollback for this change is one environment variable.
ENV_SWITCH = "FACTORY_EXECUTOR"

_started = False
_stop = threading.Event()
_lock = threading.Lock()


def executor_enabled() -> bool:
    """On by default; off under the test suite, when switched off, and in
    workflow mode.

    The test suite must never start a background thread: a suite that
    silently runs builds underneath itself is unreadable when it fails.

    WORKFLOW MODE TURNS THIS OFF, AND THAT IS THE POINT (v1.8.0)
    ------------------------------------------------------------
    In workflow mode the builder is a separate Render service. If the web
    process still ticked, it would keep writing books in the process that
    serves pages — the exact memory failure this release exists to close —
    and two owners would race each other onto the same chapter.

    One gate for both the boot thread and `tick_soon`, deliberately: a
    second check somewhere else is a second thing to forget.
    """
    if str(os.environ.get("FACTORY_TEST_MODE") or "").strip().lower() in ("1", "true", "yes"):
        return False
    try:
        from services.jobs import mode

        if mode.is_workflow_mode():
            return False
    except Exception:                                  # noqa: BLE001
        # An unreadable mode must not silently stop books being built.
        pass
    return str(os.environ.get(ENV_SWITCH) or "on").strip().lower() not in (
        "off", "0", "false", "no")


def _tick_once() -> None:
    from services.jobs.executor import drain

    try:
        drain(max_jobs=5)
    except Exception:                                  # noqa: BLE001
        # A tick must never take the web service down with it.
        log.exception("ebook executor tick failed")


def _loop() -> None:
    while not _stop.wait(TICK_SECONDS):
        _tick_once()


def start(app=None) -> bool:
    """Start the ticker once per process. Safe to call repeatedly."""
    global _started
    if not executor_enabled():
        return False
    with _lock:
        if _started:
            return True
        try:
            from services.jobs.store import init_jobs_table

            init_jobs_table()
        except Exception:                              # noqa: BLE001
            log.exception("could not prepare the jobs table")
            return False
        thread = threading.Thread(
            target=_loop, name="factory-ebook-executor", daemon=True)
        thread.start()
        _started = True
        log.info("ebook executor started (tick %ss)", TICK_SECONDS)
        return True


def stop() -> None:
    """Ask the ticker to stop. In-flight work is not abandoned unsafely:
    whatever it was doing is checkpointed and leased, so another executor
    resumes it."""
    _stop.set()


_last_request_tick = 0.0


def tick_soon(min_interval: float = TICK_SECONDS) -> bool:
    """Give a passing request the chance to advance a build.

    Belt and braces for the thread: any live traffic keeps books moving
    even if the ticker was never started or has died. Rate-limited so it
    cannot turn every request into a build step.
    """
    global _last_request_tick
    if not executor_enabled():
        return False
    now = time.monotonic()
    if now - _last_request_tick < float(min_interval):
        return False
    _last_request_tick = now
    threading.Thread(target=_tick_once, name="factory-ebook-tick",
                     daemon=True).start()
    return True
