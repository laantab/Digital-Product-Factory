"""Factory 1.9.6 -- Unsplash and Pixabay after Pexels. All HTTP mocked; zero paid calls.

What these prove:
  * Pexels stays first, and a Pexels success never touches another source.
  * Unsplash, then Pixabay, fill a picture Pexels could not.
  * Either new source is skipped when its key is absent; Pexels-only projects
    behave exactly as before.
  * Unsplash rules: photo.urls used as returned, download_location called
    once and only for the chosen picture (with its ixid), utm links, and the
    key only in a server-side header.
  * Pixabay rules: searches cached 24 hours, chosen picture stored by the
    Factory (not hotlinked), key never in an error message.
  * Paid AI is never reached while a free source can fill the picture.
  * A missing picture keeps the PDF and ZIP locked (no placeholder ships).
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["PEXELS_API_KEY"] = ""
os.environ["UNSPLASH_ACCESS_KEY"] = ""
os.environ["PIXABAY_API_KEY"] = ""

from services import image_sources  # noqa: E402
from services import ebook_factory_pipeline as pipeline  # noqa: E402
from services.ebook_visual_match import customer_safe_visual_plan  # noqa: E402

UNSPLASH_KEY = "unsplash-test-access-key-0123456789"
PIXABAY_KEY = "pixabay-test-key-0123456789"


def _jpeg(color=(60, 120, 60)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (1600, 1100), color)
    d = ImageDraw.Draw(img)
    d.rectangle((100, 100, 1400, 500), fill=(200, 170, 90))
    d.ellipse((500, 400, 1100, 1000), fill=(30, 80, 40))
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


GARDEN_ALT = "tomatoes basil and lettuce growing in pots on a sunny patio container garden"


def _unsplash_result(pid="abc123"):
    return {
        "id": pid,
        "width": 4000,
        "height": 2700,
        "alt_description": GARDEN_ALT,
        "description": "",
        "urls": {
            "full": f"https://images.unsplash.com/photo-{pid}?ixid=XYZ&fm=jpg&q=85",
            "regular": f"https://images.unsplash.com/photo-{pid}?ixid=XYZ&w=1080",
            "small": f"https://images.unsplash.com/photo-{pid}?ixid=XYZ&w=400",
        },
        "links": {
            "html": f"https://unsplash.com/photos/{pid}",
            "download": f"https://unsplash.com/photos/{pid}/download",
            "download_location": f"https://api.unsplash.com/photos/{pid}/download?ixid=XYZ",
        },
        "user": {"name": "Ada Grower", "username": "adagrower",
                 "links": {"html": "https://unsplash.com/@adagrower"}},
    }


def _pixabay_hit(pid=555):
    return {
        "id": pid,
        "pageURL": f"https://pixabay.com/photos/container-garden-tomatoes-{pid}/",
        "tags": "container garden, tomatoes, basil, pots, patio",
        "webformatURL": f"https://pixabay.com/get/abc_{pid}_640.jpg",
        "largeImageURL": f"https://pixabay.com/get/abc_{pid}_1280.jpg",
        "imageWidth": 4000,
        "imageHeight": 2600,
        "user": "Gardener",
        "user_id": 42,
    }


class _Http:
    """Records every mocked request made through image_sources._http_get."""

    def __init__(self, unsplash=None, pixabay=None):
        self.calls: list[tuple[str, dict]] = []
        self.unsplash = unsplash if unsplash is not None else [_unsplash_result()]
        self.pixabay = pixabay if pixabay is not None else [_pixabay_hit()]

    def __call__(self, url, headers, *, provider, binary=False):
        self.calls.append((url, dict(headers or {})))
        host = urlparse(url).netloc
        if binary:
            return _jpeg()
        if host == "api.unsplash.com" and "/search/" in url:
            return {"results": self.unsplash}
        if host == "api.unsplash.com" and url.endswith("ixid=XYZ") and "/download" in url:
            return {"url": "tracked"}
        if host == "pixabay.com" and "/api/" in url:
            return {"hits": self.pixabay}
        raise AssertionError(f"unexpected request {url}")

    def urls(self, needle):
        return [u for u, _ in self.calls if needle in u]


def _aid(**extra):
    aid = {
        "visual_id": extra.pop("visual_id", "v_ch1"),
        "type": "photo",
        "title": "Tomatoes and herbs in patio pots",
        "caption": "Tomatoes, basil and lettuce growing in containers on a sunny patio.",
        "chapter": "Picking Vegetables and Herbs for Containers",
        "chapter_index": 3,
        "placement": "after_opening",
        "required": True,
        "keywords": ["tomatoes", "basil", "container garden"],
    }
    aid.update(extra)
    return aid


class FreeImageSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["FACTORY_IMAGE_SOURCE_CACHE_DIR"] = self.tmp.name
        image_sources.clear_pixabay_memory_cache()
        self.env = patch.dict(os.environ, {"UNSPLASH_ACCESS_KEY": UNSPLASH_KEY,
                                           "PIXABAY_API_KEY": PIXABAY_KEY})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.pexels_queries: list[str] = []
        # No paid AI may be touched by anything here.
        for target in ("ai_client.get_client", "ai_client.chat", "ai_client.chat_json",
                       "services.ebook_package.generate_visual_image"):
            p = patch(target, side_effect=AssertionError("paid call"))
            p.start()
            self.addCleanup(p.stop)

    def _pexels(self, photos=None):
        def _search(query, **_k):
            self.pexels_queries.append(query)
            return {"photos": list(photos or [])}

        return (
            patch("services.ebook_factory_pipeline.search_pexels", side_effect=_search),
            patch("services.ebook_factory_pipeline.download_pexels_original",
                  side_effect=lambda _p: _jpeg()),
        )

    def _fill(self, **kwargs):
        return pipeline.fill_photo_aid_from_pexels(
            _aid(), package_id="v196-test-pkg", title="Container Gardening for Beginners",
            topic="container gardening", chapter="Picking Vegetables and Herbs for Containers",
            **kwargs,
        )

    # ------------------------------------------------------------ ordering
    def test_01_pexels_first_and_its_success_skips_other_sources(self):
        http = _Http()
        pex = {"photo_id": "1001", "photographer": "P", "attribution": "Photo by P on Pexels",
               "page_url": "https://www.pexels.com/photo/container-garden-tomatoes-1001/",
               "alt": GARDEN_ALT, "original_url": "https://images.pexels.com/1001.jpeg"}
        a, b = self._pexels([pex])
        with a, b, patch.object(image_sources, "_http_get", side_effect=http):
            out = self._fill()
        self.assertEqual(out.get("source"), "pexels")
        self.assertTrue(self.pexels_queries)
        self.assertEqual(http.calls, [], "no Unsplash/Pixabay call when Pexels succeeds")

    def test_02_unsplash_fills_what_pexels_could_not(self):
        http = _Http()
        a, b = self._pexels([])
        with a, b, patch.object(image_sources, "_http_get", side_effect=http):
            out = self._fill()
        self.assertTrue(self.pexels_queries, "Pexels must be tried first")
        self.assertEqual(out.get("source"), "unsplash")
        self.assertEqual(out.get("photo_id"), "unsplash:abc123")
        self.assertEqual(http.urls("pixabay.com"), [], "Pixabay not needed")
        self.assertTrue(out.get("has_file"))
        self.assertIn("Unsplash", out.get("attribution"))

    def test_03_pixabay_fills_when_pexels_and_unsplash_cannot(self):
        http = _Http(unsplash=[])
        a, b = self._pexels([])
        with a, b, patch.object(image_sources, "_http_get", side_effect=http):
            out = self._fill()
        self.assertEqual(out.get("source"), "pixabay")
        self.assertEqual(out.get("photo_id"), "pixabay:555")
        self.assertTrue(http.urls("api.unsplash.com/search"), "Unsplash tried before Pixabay")
        self.assertIn("Pixabay", out.get("attribution"))

    def test_04_missing_keys_skip_new_sources_and_keep_pexels_only_behaviour(self):
        http = _Http()
        a, b = self._pexels([])
        with patch.dict(os.environ, {"UNSPLASH_ACCESS_KEY": "", "PIXABAY_API_KEY": ""}), \
                a, b, patch.object(image_sources, "_http_get", side_effect=http):
            self.assertEqual(image_sources.configured_providers(), ())
            out = self._fill()
        self.assertEqual(http.calls, [])
        self.assertEqual(out.get("status"), "missing")
        self.assertFalse(out.get("has_file"))

    def test_05_choosing_a_source_searches_only_that_source(self):
        http = _Http()
        a, b = self._pexels([])
        with a, b, patch.object(image_sources, "_http_get", side_effect=http):
            out = self._fill(providers=("pixabay",))
        self.assertEqual(self.pexels_queries, [])
        self.assertEqual(http.urls("unsplash"), [])
        self.assertEqual(out.get("source"), "pixabay")

    # ------------------------------------------------------------ Unsplash rules
    def test_06_unsplash_download_tracked_once_only_for_the_chosen_picture(self):
        second = _unsplash_result("zzz999")
        http = _Http(unsplash=[_unsplash_result(), second])
        a, b = self._pexels([])
        with a, b, patch.object(image_sources, "_http_get", side_effect=http):
            out = self._fill()
        tracked = [u for u, _ in http.calls if "/download?" in u]
        self.assertEqual(len(tracked), 1, tracked)
        self.assertIn(out.get("provider_photo_id"), tracked[0])
        self.assertIn("ixid=XYZ", tracked[0], "download_location used with its query string")
        self.assertTrue(out.get("download_tracked"))
        # The picture itself was fetched from the API's own photo.urls address.
        fetched = [u for u, _ in http.calls if u.startswith("https://images.unsplash.com/")]
        self.assertTrue(fetched)
        for url, headers in http.calls:
            self.assertNotIn(UNSPLASH_KEY, url, "key never in a URL")
            if url.startswith("https://api.unsplash.com/"):
                self.assertEqual(headers.get("Authorization"), f"Client-ID {UNSPLASH_KEY}")
            else:
                self.assertNotIn("Authorization", headers, "key never sent to the image CDN")

    def test_07_unsplash_links_carry_utm_and_review_shows_hotlinked_url(self):
        photo = image_sources.normalize_unsplash_photo(_unsplash_result())
        for key in ("page_url", "photographer_url", "provider_home_url"):
            q = parse_qs(urlparse(photo[key]).query)
            self.assertEqual(q.get("utm_medium"), ["referral"], key)
            self.assertTrue(q.get("utm_source"), key)
        credit = image_sources.credit_for({**photo, "source": "unsplash"})
        self.assertTrue(credit["hotlink_preview_url"].startswith("https://images.unsplash.com/"))
        self.assertEqual(credit["photographer"], "Ada Grower")

    # ------------------------------------------------------------ Pixabay rules
    def test_08_pixabay_searches_are_cached_for_24_hours(self):
        http = _Http()
        with patch.object(image_sources, "_http_get", side_effect=http):
            first = image_sources.search_pixabay("container garden")
            image_sources.clear_pixabay_memory_cache()  # disk cache must still hold it
            second = image_sources.search_pixabay("container garden")
        self.assertEqual(len(http.urls("pixabay.com/api/")), 1)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        for name in os.listdir(self.tmp.name):
            self.assertNotIn(PIXABAY_KEY, (Path(self.tmp.name) / name).read_text())

    def test_09_pixabay_picture_is_stored_not_hotlinked(self):
        http = _Http(unsplash=[])
        a, b = self._pexels([])
        with a, b, patch.object(image_sources, "_http_get", side_effect=http):
            out = self._fill()
        self.assertEqual(out.get("source"), "pixabay")
        self.assertTrue(os.path.isfile(str(out.get("asset_path"))))
        self.assertFalse(out.get("preview_url"), "no Pixabay URL kept for display")
        self.assertEqual(image_sources.credit_for(out)["hotlink_preview_url"], "")

    def test_10_keys_never_appear_in_errors_or_status(self):
        err = image_sources.ImageSourceError(
            f"boom https://pixabay.com/api/?key={PIXABAY_KEY}&q=x {UNSPLASH_KEY}")
        self.assertNotIn(PIXABAY_KEY, str(err))
        self.assertNotIn(UNSPLASH_KEY, str(err))
        blob = repr(image_sources.image_sources_status())
        self.assertNotIn(PIXABAY_KEY, blob)
        self.assertNotIn(UNSPLASH_KEY, blob)

    def test_11_live_calls_blocked_in_test_mode(self):
        with self.assertRaises(image_sources.ImageSourceError) as ctx:
            image_sources.search_unsplash("garden")
        self.assertEqual(ctx.exception.code, "test_blocked")

    # ------------------------------------------------------------ safety
    def test_12_ids_from_different_sources_never_collide(self):
        hit = image_sources.normalize_pixabay_hit(_pixabay_hit(1001))
        self.assertEqual(hit["photo_id"], "pixabay:1001")
        self.assertNotEqual(hit["photo_id"], "1001")

    def test_13_customer_files_drop_links_but_keep_credit_text(self):
        plan = {"chapters": [{"aids": [{
            "attribution": "Photo by Ada Grower on Unsplash",
            "download_location": "https://api.unsplash.com/photos/x/download?ixid=1",
            "page_url": "https://unsplash.com/photos/x", "preview_url": "https://images.unsplash.com/x",
        }]}]}
        aid = customer_safe_visual_plan(plan)["chapters"][0]["aids"][0]
        self.assertEqual(aid.get("attribution"), "Photo by Ada Grower on Unsplash")
        for key in ("download_location", "page_url", "preview_url"):
            self.assertNotIn(key, aid)

    def test_14_missing_picture_keeps_pdf_and_zip_locked(self):
        data = {
            "product_type": "ebook",
            "title": "Container Gardening for Beginners",
            "content": "# Container Gardening\n\n## Soil\n\nUse potting mix.\n",
            "fields": {"topic": "container gardening"},
            "visual_plan": {"chapters": [{"chapter": "Soil", "aids": [
                {**_aid(visual_id="v_missing"), "status": "missing", "has_file": False}]}]},
            "cover_design": {"selected_layout": "cover-a", "source": {"sha256": "a" * 64}},
            "package_id": "v196-missing-pkg",
        }
        state = pipeline.ebook_project_readiness(data)
        self.assertFalse(state["ebook_ready"])
        self.assertFalse(state["pdf_enabled"])
        self.assertFalse(state["zip_enabled"])


if __name__ == "__main__":
    unittest.main()
