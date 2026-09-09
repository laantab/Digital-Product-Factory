"""Long actions must show the customer they are moving, not look hung.

Generating an 8-chapter manuscript is one HTTP request that makes eight
sequential provider calls and can run for minutes. Until now the page showed a
busy button and nothing else, which is indistinguishable from a frozen app —
on a paid action, where the customer's instinct is to click again.

Covered here:
  * the progress tracker itself (thread-safe, self-pruning, never raises);
  * the chapter pipeline emitting one start/done event per chapter;
  * the read-only polling route;
  * progress never charging, never touching the ledger, and never being able to
    break the generation it reports on.

Zero paid/external calls. FACTORY_TEST_MODE via conftest.
"""
from __future__ import annotations

import os
import sys
import threading
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"

from app import app  # noqa: E402
from services import progress_tracker  # noqa: E402
from services.ebook_manuscript_engine import (  # noqa: E402
    BookContract,
    ChapterContract,
    run_chapter_pipeline,
)
from services.ebook_project_workspace import chapter_progress_reporter  # noqa: E402

APP_JS = ROOT / "static" / "js" / "app.js"


def _book(n: int = 3) -> BookContract:
    chapters = [
        ChapterContract(
            order=i + 1,
            title=f"Chapter {i + 1}",
            purpose="Explain one part of the method.",
            min_useful_words=1,
        )
        for i in range(n)
    ]
    return BookContract(
        title="Test Book",
        subtitle="A Subtitle",
        author="An Author",
        audience="testers",
        primary_outcome="a working routine",
        approved_outline=[{"order": c.order, "title": c.title} for c in chapters],
        research_brief="brief",
        citations=[],
        editorial_rules=[],
        chapters=chapters,
    )


class ProgressTrackerTests(unittest.TestCase):
    def setUp(self):
        self.key = progress_tracker.job_key("test", id(self))
        self.addCleanup(progress_tracker.clear, self.key)

    def test_an_unknown_key_reads_as_idle_rather_than_failing(self):
        row = progress_tracker.read("test:never-started")
        self.assertFalse(row["active"])
        self.assertEqual(row["status"], "idle")

    def test_a_job_reports_percent_and_elapsed(self):
        progress_tracker.start(self.key, action="generate_manuscript", total=8)
        progress_tracker.advance(self.key, done=2, step_label="Writing chapter 3 of 8")
        row = progress_tracker.read(self.key)
        self.assertTrue(row["active"])
        self.assertEqual(row["done"], 2)
        self.assertEqual(row["total"], 8)
        self.assertEqual(row["percent"], 25)
        self.assertEqual(row["step_label"], "Writing chapter 3 of 8")
        self.assertGreaterEqual(row["elapsed_seconds"], 0)

    def test_percent_is_absent_when_the_total_is_unknown(self):
        progress_tracker.start(self.key, action="run_research", total=0)
        self.assertIsNone(progress_tracker.read(self.key)["percent"])

    def test_percent_never_exceeds_one_hundred(self):
        progress_tracker.start(self.key, total=4)
        progress_tracker.advance(self.key, done=99)
        self.assertEqual(progress_tracker.read(self.key)["percent"], 100)

    def test_finishing_marks_the_job_inactive_but_still_readable(self):
        progress_tracker.start(self.key, total=2)
        progress_tracker.finish(self.key, status="done", message="Manuscript complete.")
        row = progress_tracker.read(self.key)
        self.assertFalse(row["active"])
        self.assertEqual(row["status"], "done")
        self.assertEqual(row["message"], "Manuscript complete.")

    def test_advancing_an_unknown_job_is_silently_ignored(self):
        progress_tracker.advance("test:missing", done=3)
        progress_tracker.finish("test:missing")
        self.assertEqual(progress_tracker.read("test:missing")["status"], "idle")

    def test_concurrent_updates_do_not_corrupt_the_record(self):
        progress_tracker.start(self.key, total=100)

        def worker(start: int) -> None:
            for i in range(start, start + 20):
                progress_tracker.advance(self.key, done=i)

        threads = [threading.Thread(target=worker, args=(n * 20,)) for n in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        row = progress_tracker.read(self.key)
        self.assertIsInstance(row["done"], int)
        self.assertTrue(row["active"])

    def test_a_finished_job_is_pruned_once_it_ages_out(self):
        progress_tracker.start(self.key, total=1)
        with mock.patch.object(progress_tracker, "RETENTION_SECONDS", -1):
            self.assertEqual(progress_tracker.read(self.key)["status"], "idle")


class ChapterPipelineProgressTests(unittest.TestCase):
    """The pipeline must report each chapter, and must not need progress to run."""

    def _chapter_fn(self, book, contract):
        body = " ".join(["useful sentence about the topic."] * 200)
        return {"title": contract.title, "markdown": f"## {contract.title}\n\n{body}"}

    def test_the_pipeline_still_runs_with_no_progress_callback(self):
        out = run_chapter_pipeline(
            _book(2), generate_chapter_fn=self._chapter_fn, stop_on_failure=False
        )
        self.assertEqual(out["chapter_calls"], 2)

    def test_each_chapter_reports_a_start_and_a_done_event(self):
        events: list[dict] = []
        run_chapter_pipeline(
            _book(3),
            generate_chapter_fn=self._chapter_fn,
            on_progress=events.append,
            stop_on_failure=False,
        )
        starts = [e for e in events if e["phase"] == "chapter_start"]
        dones = [e for e in events if e["phase"] == "chapter_done"]
        self.assertEqual([e["order"] for e in starts], [1, 2, 3])
        self.assertEqual([e["order"] for e in dones], [1, 2, 3])
        for event in starts:
            self.assertEqual(event["total"], 3)
            self.assertTrue(event["title"])
        # `done` counts finished chapters, so a chapter is never reported
        # complete while its provider call is still running.
        self.assertEqual([e["done"] for e in starts], [0, 1, 2])

    def test_a_failing_progress_callback_cannot_break_generation(self):
        def boom(_event):
            raise RuntimeError("progress backend exploded")

        out = run_chapter_pipeline(
            _book(2),
            generate_chapter_fn=self._chapter_fn,
            on_progress=boom,
            stop_on_failure=False,
        )
        self.assertEqual(out["chapter_calls"], 2)
        self.assertTrue(out["manuscript_md"])

    def test_the_reporter_publishes_readable_chapter_labels(self):
        key = progress_tracker.job_key("test", "reporter")
        self.addCleanup(progress_tracker.clear, key)
        progress_tracker.start(key, action="generate_manuscript")
        report = chapter_progress_reporter(key, "Generate Manuscript")
        run_chapter_pipeline(
            _book(3),
            generate_chapter_fn=self._chapter_fn,
            on_progress=report,
            stop_on_failure=False,
        )
        row = progress_tracker.read(key)
        self.assertEqual(row["total"], 3)
        self.assertEqual(row["done"], 3)
        self.assertEqual(row["percent"], 100)

    def test_no_reporter_is_built_without_a_key(self):
        self.assertIsNone(chapter_progress_reporter("", "Generate Manuscript"))


class ProgressRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_the_route_is_a_get_and_reads_idle_for_a_quiet_project(self):
        rules = {
            r.rule: r.methods
            for r in app.url_map.iter_rules()
            if r.rule == "/ebook-workspace/<int:project_id>/progress"
        }
        self.assertTrue(rules)
        self.assertIn("GET", list(rules.values())[0])
        body = self.client.get("/ebook-workspace/999999999/progress").get_json()
        self.assertFalse(body["active"])
        self.assertEqual(body["status"], "idle")

    def test_the_route_reports_a_running_job(self):
        key = progress_tracker.job_key("ebook", 424242)
        self.addCleanup(progress_tracker.clear, key)
        progress_tracker.start(key, action="generate_manuscript", total=8)
        progress_tracker.advance(key, done=3, step_label="Writing chapter 4 of 8")
        body = self.client.get("/ebook-workspace/424242/progress").get_json()
        self.assertTrue(body["active"])
        self.assertEqual(body["percent"], 38)  # 3/8 rounds to 38
        self.assertEqual(body["step_label"], "Writing chapter 4 of 8")

    def test_polling_progress_never_reports_a_charge(self):
        key = progress_tracker.job_key("ebook", 424243)
        self.addCleanup(progress_tracker.clear, key)
        progress_tracker.start(key, action="generate_manuscript", total=4)
        body = self.client.get("/ebook-workspace/424243/progress").get_json()
        blob = str(body).lower()
        for money in ("spent_usd", "charge", "paid_call", "budget"):
            self.assertNotIn(money, blob)


class ProgressUiTests(unittest.TestCase):
    def _js(self) -> str:
        return APP_JS.read_text(encoding="utf-8")

    def test_every_long_paid_action_shows_progress(self):
        js = self._js()
        # Count call sites, not one exact argument spelling: the four long
        # actions are manuscript, correction, research and the one-click build.
        calls = js.count("startWorkspaceProgress(") - js.count("function startWorkspaceProgress(")
        self.assertEqual(
            calls,
            4,
            "manuscript, correction, research and the one-click full build "
            "must each show progress",
        )

    def test_progress_is_always_stopped_on_success_and_on_failure(self):
        js = self._js()
        self.assertGreaterEqual(js.count("progress.stop("), 6)

    def test_the_indicator_shows_movement_a_count_and_elapsed_time(self):
        helper = self._js().split("function startWorkspaceProgress(", 1)[1].split(
            "// Free re-check of a manuscript", 1)[0]
        self.assertIn("animate-spin", self._js())
        self.assertIn("data-ws-progress-bar", helper)
        self.assertIn("data-ws-progress-elapsed", helper)
        self.assertIn("clearInterval", helper)
        # Without server data the bar must still creep, so it never looks frozen.
        self.assertIn("creep", helper)

    def test_a_polling_failure_is_swallowed_not_shown_to_the_customer(self):
        helper = self._js().split("const poll = async () =>", 1)[1].split(
            "const clockId", 1)[0]
        self.assertIn("catch", helper)
        self.assertNotIn("toast(", helper)


if __name__ == "__main__":
    unittest.main()
