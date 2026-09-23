"""One request's paid-image authorization must not authorize another's.

The authorization that stands at the money boundary was a module-level integer,
so while a background build held it EVERY other thread in the process saw
`paid_image_generation_authorized()` as True. The app is multi-threaded by its
own design -- services/jobs/runner.py starts a daemon executor and spawns a
thread on passing traffic -- so a Save, an Export, a QA recheck or a diagnostic
probe running beside a build could reach the OpenAI Images API and spend real
money, which is exactly what that guard exists to prevent.
"""
import threading
import unittest

from services.ebook_package import (
    authorize_paid_image_generation,
    paid_image_generation_authorized,
)


class PaidImageAuthorizationIsPerThreadTests(unittest.TestCase):
    def test_nothing_is_authorized_by_default(self):
        self.assertFalse(paid_image_generation_authorized())

    def test_a_second_thread_is_not_authorized_by_the_first(self):
        holding = threading.Event()
        release = threading.Event()
        seen = {}

        def build():
            with authorize_paid_image_generation("user_approved_generation"):
                seen["inside_build"] = paid_image_generation_authorized()
                holding.set()
                release.wait(10)

        def other_request():
            holding.wait(10)
            seen["other_request"] = paid_image_generation_authorized()
            release.set()

        a = threading.Thread(target=build)
        b = threading.Thread(target=other_request)
        a.start(); b.start(); a.join(10); b.join(10)

        self.assertTrue(seen.get("inside_build"), "the approved build lost its own authorization")
        self.assertFalse(
            seen.get("other_request", True),
            "an unrelated request was authorized to spend money by someone else's build",
        )

    def test_the_holder_still_sees_it_nested_and_gives_it_back(self):
        with authorize_paid_image_generation("outer"):
            self.assertTrue(paid_image_generation_authorized())
            with authorize_paid_image_generation("inner"):
                self.assertTrue(paid_image_generation_authorized())
            self.assertTrue(paid_image_generation_authorized())
        self.assertFalse(paid_image_generation_authorized())


if __name__ == "__main__":
    unittest.main()
