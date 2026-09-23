"""Access control must never be off by accident -- on the live site.

_invite_code_required() returned "" when FACTORY_INVITE_CODE was unset, and
_invite_gate() then returned None immediately, so one unset or mistyped
variable silently exposed the whole Factory to the open internet with nothing
in a log to say so. FACTORY_INVITE_CODE does not appear in render.yaml, and
render.yaml states it is not the live configuration, so the live value is
hand-entered and can be lost.

The refusal applies to a hosted service only -- Render sets RENDER=true on
every service it runs. A Factory started on somebody's own machine stays open,
which is what .env.example has always promised. Turning the live site open
stays possible; it just has to be said out loud, with FACTORY_OPEN_ACCESS=1.

This module deliberately does NOT reload app.py. Reloading it rebinds the
module while other test modules still hold the original Flask app, and the
mixed pair produces failures far away from here.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("FACTORY_TEST_MODE", "1")

import app as app_module  # noqa: E402


def _env(**values):
    """Set exactly these variables, clearing any the caller passes as ''."""
    patch_env = {k: v for k, v in values.items() if v}
    remove = [k for k, v in values.items() if not v]
    cm = mock.patch.dict(os.environ, patch_env, clear=False)

    class _Ctx:
        def __enter__(self):
            cm.__enter__()
            self._removed = {k: os.environ.pop(k) for k in remove if k in os.environ}
            return self

        def __exit__(self, *exc):
            os.environ.update(self._removed)
            return cm.__exit__(*exc)

    return _Ctx()


class TheInviteGateFailsClosedTests(unittest.TestCase):
    def setUp(self):
        # _FACTORY_TEST_MODE is read once at import; patch the attribute rather
        # than re-importing the module.
        patcher = mock.patch.object(app_module, "_FACTORY_TEST_MODE", False)
        patcher.start()
        self.addCleanup(patcher.stop)
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

    def test_a_hosted_site_with_nothing_configured_refuses_every_request(self):
        with _env(RENDER="true", FACTORY_INVITE_CODE="", FACTORY_OPEN_ACCESS=""):
            self.assertTrue(app_module._access_control_is_unconfigured())
            for path in ("/", "/projects", "/admin/backup-db"):
                r = self.client.get(path)
                self.assertIn(
                    r.status_code, (401, 403, 404, 405, 503),
                    f"{path} was served with no access control configured",
                )

    def test_a_factory_on_a_laptop_is_not_refused(self):
        """RENDER unset means somebody's own machine, not the live site."""
        with _env(RENDER="", FACTORY_INVITE_CODE="", FACTORY_OPEN_ACCESS=""):
            self.assertFalse(app_module._access_control_is_unconfigured())

    def test_a_configured_invite_code_leaves_the_normal_gate_in_charge(self):
        with _env(RENDER="true", FACTORY_INVITE_CODE="letmein", FACTORY_OPEN_ACCESS=""):
            self.assertFalse(app_module._access_control_is_unconfigured())
            self.assertEqual(app_module._invite_code_required(), "letmein")

    def test_open_access_can_be_chosen_deliberately(self):
        with _env(RENDER="true", FACTORY_INVITE_CODE="", FACTORY_OPEN_ACCESS="1"):
            self.assertFalse(app_module._access_control_is_unconfigured())

    def test_static_files_are_still_served_while_closed(self):
        """A closed site must still be able to draw its own refusal page."""
        with _env(RENDER="true", FACTORY_INVITE_CODE="", FACTORY_OPEN_ACCESS=""):
            r = self.client.get("/static/js/app.js")
            self.assertNotEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
