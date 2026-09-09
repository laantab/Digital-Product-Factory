"""One authorization must finish a book — without loosening a single gate.

Lonnie: "I don't think the user should have to keep clicking a dam button to
complete a project... we should be able to do this with one click."

The workspace is ten gated stages with ten buttons. This automates the
*clicking*, never the *gates*. These tests pin both halves:

  * one call walks Research → Title → Outline → Manuscript → Visuals → Cover →
    Design → Preview → Preflight and approves each stage that passes;
  * a stage whose quality gate refuses stops the run, keeps the work, and
    reports why — it is never auto-approved (FACTORY_BLUEPRINT.md §7);
  * spending stays inside the one stated maximum and the project cap (§13);
  * an already-approved stage is skipped, never rebuilt (§10).

Zero paid/external calls: every provider-facing step is injected.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"

from app import app  # noqa: E402
import database  # noqa: E402
from services.ebook_manuscript_engine import (  # noqa: E402
    QUALITY_PASS,
    chapter_fn_from_full_manuscript,
)
from services.ebook_manuscript_fixtures import (  # noqa: E402
    build_event_photo_strong_manuscript,
)
from services.ebook_auto_build import (  # noqa: E402
    BUILD_STAGES,
    MAX_AUTO_CORRECTIONS,
    AutoBuildStop,
    plan_full_build,
    run_full_build,
)
from services.ebook_project_workspace import (  # noqa: E402
    STATUS_APPROVED,
    ensure_workspace,
    is_approved,
    new_workspace,
    set_stage_status,
    stage_status,
    upsert_acceptance_project,
)

APP_JS = ROOT / "static" / "js" / "app.js"


def _workspace(**over):
    data = {
        "title": "The Weekly Reset Guide",
        "subtitle": "Simple Systems for Busy Weeks",
        "author_brand": "A Author",
        "ebook_workspace": new_workspace(
            topic="weekly reset routines",
            audience="busy parents",
            outcome="a simple weekly system",
            author="A Author",
        ),
    }
    data.update(over)
    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    ws["research_payload"] = {"summary": "Parents want a repeatable weekly reset."}
    ws["paid_call_ledger"] = {
        "budget_cap_usd": 3.5,
        "spent_usd": 0.0,
        "remaining_usd": 3.5,
        "paid_calls": 0,
        "calls": [],
        "pending_estimate": None,
    }
    return data


def _free_stage(name):
    """Stand-in for a free stage step: mark it done the way the real one does."""

    def run(data):
        set_stage_status(data["ebook_workspace"], name, STATUS_APPROVED)
        return data

    return run


def _stage_fns(**over):
    fns = {
        "visuals_fn": _free_stage("visuals"),
        "cover_fn": _free_stage("cover"),
        "design_fn": _free_stage("design"),
        "preview_fn": _free_stage("preview"),
        "preflight_fn": _free_stage("preflight"),
    }
    fns.update(over)
    return fns


class PlanTests(unittest.TestCase):
    def test_the_plan_costs_nothing_to_ask_for(self):
        plan = plan_full_build(_workspace())
        self.assertEqual(plan["estimate_cost_usd"], 0.0)
        self.assertIn("costs $0", plan["note"])

    def test_only_writing_steps_carry_a_price(self):
        plan = plan_full_build(_workspace())
        by_stage = {s["stage"]: s for s in plan["steps"]}
        for free_stage in ("visuals", "cover", "design", "preview", "preflight"):
            with self.subTest(stage=free_stage):
                self.assertEqual(by_stage[free_stage]["max_usd"], 0.0)
                self.assertFalse(by_stage[free_stage]["paid"])
        self.assertGreater(by_stage["manuscript"]["max_usd"], 0.0)

    def test_the_maximum_never_exceeds_the_remaining_budget(self):
        data = _workspace()
        data["ebook_workspace"]["paid_call_ledger"]["remaining_usd"] = 0.25
        plan = plan_full_build(data)
        self.assertLessEqual(plan["max_total_usd"], 0.25)

    def test_approved_stages_drop_out_of_the_plan(self):
        data = _workspace()
        for stage in ("research", "title", "outline"):
            set_stage_status(data["ebook_workspace"], stage, STATUS_APPROVED)
        stages = [s["stage"] for s in plan_full_build(data)["steps"]]
        for done in ("research", "title", "outline"):
            self.assertNotIn(done, stages)


class HappyPathTests(unittest.TestCase):
    """One call, a finished book, every gate real and every stage approved.

    Uses the repository's own known-good manuscript fixture, so the quality
    engine, outline fidelity and content checks all run unpatched.
    """

    def setUp(self):
        self.project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        self.pid = self.project["id"]

    def _data(self):
        return dict(database.get_project(self.pid)["data"])

    def _good_chapter_fn(self):
        return chapter_fn_from_full_manuscript(build_event_photo_strong_manuscript())

    def test_one_call_walks_the_whole_rail(self):
        data = self._data()
        out = run_full_build(
            data,
            max_authorized_usd=3.5,
            idempotency_key="one-click-happy",
            project_id=self.pid,
            generate_chapter_fn=self._good_chapter_fn(),
            correct_chapter_fn=self._good_chapter_fn(),
            **_stage_fns(),
        )
        result = out["result"]
        ws = out["data"]["ebook_workspace"]
        self.assertTrue(result["finished"], result["stopped"])
        self.assertIsNone(result["stopped"])
        for stage in BUILD_STAGES:
            with self.subTest(stage=stage):
                self.assertTrue(
                    is_approved(ws, stage), f"{stage} reported done but is not approved"
                )
        self.assertLessEqual(result["charged_usd"], result["authorized_usd"] + 1e-9)

    def test_the_manuscript_it_approved_really_passed_quality(self):
        data = self._data()
        out = run_full_build(
            data,
            max_authorized_usd=3.5,
            idempotency_key="one-click-quality",
            project_id=self.pid,
            generate_chapter_fn=self._good_chapter_fn(),
            correct_chapter_fn=self._good_chapter_fn(),
            **_stage_fns(),
        )
        ws = out["data"]["ebook_workspace"]
        self.assertEqual(stage_status(ws, "manuscript"), STATUS_APPROVED)
        self.assertEqual((ws.get("manuscript_quality") or {}).get("status"), QUALITY_PASS)
        self.assertFalse(ws.get("manuscript_qa"))

    def test_it_skips_work_that_is_already_approved(self):
        data = self._data()
        out = run_full_build(
            data,
            max_authorized_usd=3.5,
            idempotency_key="one-click-skip",
            project_id=self.pid,
            generate_chapter_fn=self._good_chapter_fn(),
            correct_chapter_fn=self._good_chapter_fn(),
            research_fn=lambda *a, **k: self.fail("research must not re-run"),
            **_stage_fns(),
        )
        # The acceptance fixture already has research/title/outline approved.
        for done in ("research", "title", "outline"):
            self.assertNotIn(done, out["result"]["completed_stages"])


class WeakChapterDoesNotAbandonTheBookTests(unittest.TestCase):
    """The reported dead end: project 21318, 2026-09-02.

    An 8-chapter book generated only 2 chapters and stopped. Chapter 1 passed,
    chapter 2 failed PURPOSE_MISALIGN, and ``stop_on_failure`` abandoned
    chapters 3-8 (``skipped_ungenerated: [3,4,5,6,7,8]``). Correction then
    retried *only* chapter 2, failed the same way, and stopped again -- so the
    remaining six chapters could never be written. Every attempt cost $0.15 and
    the book could never complete, which is what "I had to click 5 times and
    the project still didn't build" actually was.
    """

    def setUp(self):
        self.project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        self.pid = self.project["id"]

    def test_the_one_click_build_writes_every_chapter_before_correcting(self):
        seen: list[int] = []
        good = build_event_photo_strong_manuscript()
        good_fn = chapter_fn_from_full_manuscript(good)

        def flaky(book, contract):
            seen.append(contract.order)
            if contract.order == 2:
                # Passes length but misses the approved purpose, exactly as the
                # live failure did.
                return {"ebook": f"## {contract.title}\n\n" + ("unrelated filler text. " * 400)}
            return good_fn(book, contract)

        data = dict(database.get_project(self.pid)["data"])
        run_full_build(
            data,
            max_authorized_usd=3.5,
            idempotency_key="weak-chapter",
            project_id=self.pid,
            generate_chapter_fn=flaky,
            correct_chapter_fn=flaky,
            **_stage_fns(),
        )
        # The book is no longer abandoned at the first weak chapter: chapters
        # after it are still written.
        self.assertTrue(
            [o for o in seen if o > 2],
            f"generation stopped at the weak chapter again; saw {seen}",
        )

    def test_generation_still_stops_early_for_the_step_by_step_path(self):
        """The cost guard is unchanged where the customer drives it manually."""
        engine = (ROOT / "services" / "ebook_project_workspace.py").read_text(encoding="utf-8")
        self.assertIn("stop_on_failure=not complete_all_chapters", engine)
        self.assertIn("complete_all_chapters: bool = False", engine)


class GatesStillHoldTests(unittest.TestCase):
    """The whole point: automation of clicks, not of judgement."""

    def _thin_chapter_fn(self, book, contract):
        # Deliberately too short -- the real quality gate must refuse this.
        return {"title": contract.title, "markdown": f"## {contract.title}\n\nToo short."}

    def test_a_failing_quality_gate_stops_the_run_instead_of_approving(self):
        data = _workspace()
        out = run_full_build(
            data,
            max_authorized_usd=3.5,
            idempotency_key="one-click-thin",
            generate_chapter_fn=self._thin_chapter_fn,
            correct_chapter_fn=self._thin_chapter_fn,
            **_stage_fns(),
        )
        result = out["result"]
        ws = out["data"]["ebook_workspace"]
        self.assertFalse(result["finished"])
        self.assertIsNotNone(result["stopped"])
        self.assertNotEqual(stage_status(ws, "manuscript"), STATUS_APPROVED)
        # Later stages must not have been reached at all.
        for later in ("visuals", "cover", "design", "preview", "preflight"):
            with self.subTest(stage=later):
                self.assertNotEqual(stage_status(ws, later), STATUS_APPROVED)

    def test_it_stops_with_a_sentence_a_person_can_act_on(self):
        data = _workspace()
        out = run_full_build(
            data,
            max_authorized_usd=3.5,
            idempotency_key="one-click-msg",
            generate_chapter_fn=self._thin_chapter_fn,
            correct_chapter_fn=self._thin_chapter_fn,
            **_stage_fns(),
        )
        reason = (out["result"]["stopped"] or {}).get("reason") or ""
        self.assertTrue(reason)
        # Plain language, not an engine dump.
        self.assertNotIn("Traceback", reason)
        self.assertLess(len(reason), 400)

    def test_it_corrects_at_most_once_before_asking_a_human(self):
        self.assertEqual(MAX_AUTO_CORRECTIONS, 1)
        calls = {"n": 0}

        def counting_fn(book, contract):
            calls["n"] += 1
            return {"title": contract.title, "markdown": f"## {contract.title}\n\nToo short."}

        data = _workspace()
        run_full_build(
            data,
            max_authorized_usd=3.5,
            idempotency_key="one-click-loop",
            generate_chapter_fn=counting_fn,
            correct_chapter_fn=counting_fn,
            **_stage_fns(),
        )
        # Bounded: it cannot sit in a paid retry loop.
        self.assertLess(calls["n"], 40, "auto-correction must be bounded")

    def test_a_missing_stage_function_stops_cleanly_rather_than_crashing(self):
        data = _workspace()
        for stage in ("research", "title", "outline", "manuscript"):
            set_stage_status(data["ebook_workspace"], stage, STATUS_APPROVED)
        out = run_full_build(
            data,
            max_authorized_usd=0.0,
            idempotency_key="one-click-novisuals",
            visuals_fn=None,
        )
        self.assertFalse(out["result"]["finished"])
        self.assertEqual((out["result"]["stopped"] or {}).get("stage"), "visuals")


class SpendingTests(unittest.TestCase):
    def test_an_idempotency_key_is_required(self):
        with self.assertRaises(ValueError):
            run_full_build(_workspace(), max_authorized_usd=1.0, idempotency_key="")

    def test_zero_authorization_cannot_reach_a_paid_step(self):
        data = _workspace()
        out = run_full_build(
            data,
            max_authorized_usd=0.0,
            idempotency_key="one-click-nobudget",
            generate_chapter_fn=lambda *a, **k: self.fail("must not call a provider"),
            **_stage_fns(),
        )
        self.assertEqual(out["result"]["charged_usd"], 0.0)
        self.assertFalse(out["result"]["finished"])

    def test_the_run_never_charges_more_than_authorized(self):
        data = _workspace()
        out = run_full_build(
            data,
            max_authorized_usd=0.30,
            idempotency_key="one-click-cap",
            generate_chapter_fn=lambda b, c: {
                "title": c.title,
                "markdown": f"## {c.title}\n\n" + ("word " * 800),
            },
            **_stage_fns(),
        )
        self.assertLessEqual(out["result"]["charged_usd"], 0.30 + 1e-9)


class RouteAndUiTests(unittest.TestCase):
    def test_both_routes_exist(self):
        rules = {r.rule for r in app.url_map.iter_rules()}
        self.assertIn("/ebook-workspace/<int:project_id>/estimate-full-build", rules)
        self.assertIn("/ebook-workspace/<int:project_id>/run-full-build", rules)

    def test_a_missing_project_still_gets_a_clean_404(self):
        resp = app.test_client().post(
            "/ebook-workspace/999999999/run-full-build", json={}
        )
        self.assertEqual(resp.status_code, 404)

    def test_the_build_is_one_click_with_no_confirmation_dialog(self):
        """Lonnie: "I had to click 5 times, and the project still didn't build.

        Take out the paid authorization part so the build goes through." The
        button press is the authorization; there is no second confirmation.
        """
        js = APP_JS.read_text(encoding="utf-8")
        fn = js.split("async function runFullBuild(", 1)[1].split(
            "// ---------- long-action progress ----------", 1
        )[0]
        self.assertIn("run-full-build", fn)
        # No checkbox, no confirm step, no gating of the button.
        for gate in ("data-ws-build-all-auth", "authorize_paid_call", "auth.checked", "Cancel"):
            with self.subTest(gate=gate):
                self.assertNotIn(gate, fn)
        # It still shows progress while it runs.
        self.assertIn("startWorkspaceProgress(projectId, mount)", fn)

    def test_the_cost_is_shown_on_the_card_before_the_click(self):
        js = APP_JS.read_text(encoding="utf-8")
        self.assertIn("data-ws-build-all-cost", js)
        loader = js.split("async function loadFullBuildCost(", 1)[1].split(
            "async function runFullBuild(", 1
        )[0]
        self.assertIn("estimate-full-build", loader)
        self.assertIn("Costs at most $", loader)

    def test_the_server_sets_its_own_ceiling_not_the_browser(self):
        route = (ROOT / "app.py").read_text(encoding="utf-8").split(
            "def run_ebook_full_build_route(", 1
        )[1].split("@app.get", 1)[0]
        self.assertIn("plan_full_build(dict(data))", route)
        self.assertIn("max_authorized_usd=ceiling", route)
        # The request body must not be able to raise the ceiling.
        self.assertNotIn('body.get("max_authorized_usd")', route)

    def test_the_step_by_step_path_is_still_offered(self):
        js = APP_JS.read_text(encoding="utf-8")
        self.assertIn("Or step by step:", js)


class StageOrderTests(unittest.TestCase):
    def test_the_build_order_matches_the_production_rail(self):
        self.assertEqual(
            BUILD_STAGES,
            ("research", "title", "outline", "manuscript", "visuals", "cover",
             "design", "preview", "preflight"),
        )

    def test_autobuildstop_carries_what_to_tell_the_customer(self):
        stop = AutoBuildStop("cover", "No suitable cover photo was found.", needs="human")
        self.assertEqual(stop.stage, "cover")
        self.assertEqual(stop.needs, "human")
        self.assertIn("cover photo", str(stop))


if __name__ == "__main__":
    unittest.main()
