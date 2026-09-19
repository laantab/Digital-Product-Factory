"""Every POST route is classified — v1.8.1.

THIS IS THE MOST IMPORTANT TEST IN THE RELEASE.

v1.8.0 moved the one-click build to the builder and left the step-by-step
screen, the visuals buttons and the cover buttons running inside the web
service. Nothing caught that, because nothing was watching. On 2026-09-18
the gap reached production: a gunicorn worker was killed at the 120-second
timeout writing chapters, the 512 MB instance ran out of memory minutes
later, and the builder was never asked to do anything all evening.

The point of this file is that the same thing cannot happen quietly again.
Add a POST route and forget to think about where it runs, and the release
gate goes red with the route's name in the failure.

The route list is read from the LIVE url_map, not by parsing app.py. Two
POST routes (`/crossword-builder/generate`, `/word-search-builder/generate`)
live in `routes/` and are invisible to anything that reads one file — which
is exactly the kind of blind spot that produced the defect.

Zero cost. No provider is called; the app is only imported and its routing
table read.
"""
from __future__ import annotations

import unittest

from app import app
from services.jobs import actions, route_registry as rr


def _live_post_paths() -> set[str]:
    return {str(rule.rule) for rule in app.url_map.iter_rules()
            if "POST" in (rule.methods or set())}


class PostRouteRegistryTests(unittest.TestCase):

    def test_every_live_post_route_is_classified(self):
        """A new POST route must be classified before it can ship.

        If this fails, open services/jobs/route_registry.py and add the
        route with `_l(...)` if it only reads or records a decision, or
        `_h(...)` if it writes chapters, touches images, builds a cover,
        renders a preview, or builds a PDF or ZIP.
        """
        missing = sorted(_live_post_paths() - rr.registered_paths())
        self.assertEqual(
            missing, [],
            "POST routes exist that nobody has classified as light or heavy. "
            "Add them to services/jobs/route_registry.py: " + repr(missing))

    def test_registry_has_no_routes_that_no_longer_exist(self):
        """A stale entry is a classification nobody is checking any more."""
        stale = sorted(rr.registered_paths() - _live_post_paths())
        self.assertEqual(
            stale, [],
            "the registry names routes the app does not serve: " + repr(stale))

    def test_every_entry_states_a_reason(self):
        """A classification that cannot be argued with is not reviewable."""
        for entry in rr.ROUTES:
            with self.subTest(route=entry["path"]):
                self.assertTrue(str(entry["why"]).strip(),
                                f"{entry['path']} has no stated reason")

    def test_every_heavy_route_declares_what_happens_in_workflow_mode(self):
        for entry in rr.ROUTES:
            if entry["weight"] != rr.HEAVY:
                continue
            with self.subTest(route=entry["path"]):
                self.assertIn(entry["handoff"], (rr.BUILDER, rr.DEFERRED))
                self.assertTrue(
                    str(entry["reason"]).strip(),
                    f"{entry['path']} is heavy but does not say why it is "
                    f"handed off or why it is deferred")

    def test_a_deferred_heavy_route_is_a_stated_decision(self):
        """Deferring is allowed. Deferring silently is what caused the defect."""
        for path in sorted(rr.heavy_paths(rr.DEFERRED)):
            with self.subTest(route=path):
                reason = str(rr.classify(path)["reason"])
                self.assertGreater(
                    len(reason), 40,
                    f"{path} is deferred without a real explanation")

    def test_every_builder_route_knows_which_stage_it_asks_for(self):
        """A step-by-step route must tell the builder where to stop.

        Handing a click to the builder without a stage would let it run the
        whole book behind the customer's back, spending a budget they
        authorised one step at a time.

        The three v1.8.0 build routes are the exception: the one-click build
        is a request to finish the book, so it names no stage deliberately.
        """
        whole_build = {
            "/ebook/build",
            "/ebook/build/<int:project_id>/advance",
            "/ebook/build/<int:project_id>/resume",
        }
        for path in sorted(rr.heavy_paths(rr.BUILDER)):
            if path in whole_build:
                self.assertEqual(actions.stage_for_route(path), "",
                                 f"{path} builds the whole book and must name "
                                 f"no stage")
                continue
            with self.subTest(route=path):
                self.assertIn(
                    actions.stage_for_route(path),
                    ("research", "title", "outline", "manuscript", "visuals",
                     "cover", "design", "preview", "preflight", "export"),
                    f"{path} is handed to the builder but does not say which "
                    f"stage it is asking for")

    def test_the_route_that_took_the_site_down_is_heavy(self):
        """A regression guard with a name on it."""
        path = "/ebook-workspace/<int:project_id>/generate-manuscript"
        self.assertTrue(rr.is_heavy(path))
        self.assertTrue(rr.hands_off_to_builder(path))


if __name__ == "__main__":
    unittest.main()
