"""Access control must never be off by accident.

_invite_code_required() returned "" when FACTORY_INVITE_CODE was unset, and
_invite_gate() then returned None immediately -- so one unset or mistyped
variable silently exposed the whole Factory to the open internet, with nothing
in a log to say the gate was off. FACTORY_INVITE_CODE does not appear in
render.yaml, and render.yaml states it is not the live configuration, so the
live value is hand-entered and can be lost.

Turning the gate off stays possible; it just has to be said out loud, with
FACTORY_OPEN_ACCESS=1.
"""
import importlib
import os
import unittest

os.environ.setdefault("FACTORY_TEST_MODE", "1")


def _app_with(env: dict):
    """Reload app.py under a given environment, then hand back its test client.

    The environment has to stay in place while the request runs, so it is set
    directly and put back by tearDown -- a context manager would have been
    unwound before the client was ever called.
    """
    import app as app_module

    for key, value in env.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    return app_module, app_module.app.test_client()


class TheInviteGateFailsClosedTests(unittest.TestCase):
    def tearDown(self):
        import app as app_module

        os.environ["FACTORY_TEST_MODE"] = "1"
        for key in ("FACTORY_INVITE_CODE", "FACTORY_OPEN_ACCESS"):
            os.environ.pop(key, None)
        importlib.reload(app_module)

    def test_no_invite_code_and_no_opt_out_refuses_every_request(self):
        module, client = _app_with(
            {"FACTORY_TEST_MODE": "0", "FACTORY_INVITE_CODE": "", "FACTORY_OPEN_ACCESS": ""}
        )
        for path in ("/", "/projects", "/admin/backup-db"):
            r = client.get(path)
            self.assertIn(
                r.status_code, (401, 403, 404, 405, 503),
                f"{path} was served with no access control configured",
            )

    def test_a_configured_invite_code_still_gates_normally(self):
        module, client = _app_with(
            {"FACTORY_TEST_MODE": "0", "FACTORY_INVITE_CODE": "letmein", "FACTORY_OPEN_ACCESS": ""}
        )
        self.assertEqual(module._invite_code_required(), "letmein")
        r = client.get("/", headers={"Accept": "text/html"})
        self.assertEqual(r.status_code, 401)

    def test_open_access_can_be_chosen_deliberately(self):
        module, client = _app_with(
            {"FACTORY_TEST_MODE": "0", "FACTORY_INVITE_CODE": "", "FACTORY_OPEN_ACCESS": "1"}
        )
        r = client.get("/", headers={"Accept": "text/html"})
        self.assertNotIn(r.status_code, (401, 503))

    def test_static_files_are_still_served_while_closed(self):
        """A closed gate must not make the refusal page itself unstyled."""
        module, client = _app_with(
            {"FACTORY_TEST_MODE": "0", "FACTORY_INVITE_CODE": "", "FACTORY_OPEN_ACCESS": ""}
        )
        r = client.get("/static/js/app.js")
        self.assertNotEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
