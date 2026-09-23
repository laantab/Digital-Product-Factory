"""An unknown project id must be refused with 404, not crash into a 500.

_ebook_workspace_project_or_404 wrapped its error twice -- (_error(...), 404)
where _error already returns (response, status) -- so every caller's
`return err[0], err[1]` handed Flask a nested tuple. Flask raised TypeError and
answered 500. It stayed invisible because a 500 still looks like a refusal from
the outside, and because the test suite only sees it once some module has set
app.config["TESTING"], which makes Flask propagate the error instead of
swallowing it.

27 routes shared the helper.
"""
import os
import unittest

os.environ.setdefault("FACTORY_TEST_MODE", "1")

from app import app  # noqa: E402

# The condition that used to hide the bug. Leave it on.
app.config["TESTING"] = True

MISSING = 99999999

ROUTES = (
    ("get", f"/ebook-workspace/{MISSING}"),
)


class UnknownProjectGetsA404Tests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_an_unknown_project_is_refused_with_404(self):
        for method, path in ROUTES:
            with self.subTest(path=path):
                r = getattr(self.client, method)(path, json={})
                self.assertEqual(
                    r.status_code, 404,
                    f"{path} answered {r.status_code}; an unknown id is a 404",
                )
                self.assertEqual((r.get_json() or {}).get("error"), "Project not found.")

    def test_advance_in_workflow_mode_refuses_an_unknown_project_with_404(self):
        """The route the original failure surfaced on."""
        from unittest import mock

        from services.jobs import mode

        with mock.patch.dict(os.environ, {
            mode.ENV_MODE: "workflow",
            mode.ENV_TASK: "test-builder/build_ebook",
            mode.ENV_API_KEY: "not-a-real-key",
        }):
            r = self.client.post(f"/ebook/build/{MISSING}/advance", json={})
        self.assertEqual(r.status_code, 404, r.get_data(as_text=True)[:200])
        self.assertEqual((r.get_json() or {}).get("error"), "Project not found.")

    def test_the_helper_returns_something_flask_can_return(self):
        import app as app_module

        with app.test_request_context("/"):
            project, err = app_module._ebook_workspace_project_or_404(MISSING)
            self.assertIsNone(project)
            response, status = err          # a flat (response, status) pair
            self.assertEqual(status, 404)
            self.assertFalse(isinstance(response, tuple), "the error is wrapped twice")


if __name__ == "__main__":
    unittest.main()
