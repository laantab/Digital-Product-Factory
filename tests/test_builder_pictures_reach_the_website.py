"""The builder's pictures and finished files reach the website -- v1.8.4.

THE DEFECT THIS CLOSES
----------------------
Container Gardening for Beginners reached the pictures step on the live
builder and the website could show none of its nine pictures. Two gaps:

1. v1.8.1 published a picture to storage only when the picture itself
   carried "_project_id". Nothing ever set that key, so on the builder not
   one picture was published.
2. A picture's asset_path is a path on the machine that made it. The
   website -- and the next builder run, whose temporary disk starts empty --
   looked for that exact file, did not find it, and called the picture
   missing. The same was true of the finished PDF and ZIP.

The storage driver here has NO filesystem behind it, and the "website"
uses a different, empty exports folder from the "builder". A test that
passes only because both halves share a disk cannot pass here.

Zero cost: no photograph is downloaded, no paid call is made.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_builder_images_travel_through_storage import InMemoryDriver
from tests.test_ebook_visual_pipeline import _manuscript_ready, _paid_patches

import database
# v1.9.8: import every module that binds get_storage at import time BEFORE
# any test patches it. Otherwise the first import happens inside a patch and
# that module keeps the in-memory test driver for the rest of the run, which
# broke later storage tests depending on file order (seen on Windows).
import services.storage.compat  # noqa: E402,F401
import services.storage.executor  # noqa: E402,F401
from services import ebook_visual_pipeline as vp
from services.ebook_design_workspace import prepare_visuals_local
from services.ebook_visual_pipeline import (
    publishing_for_project,
    required_aids,
    validate_visual_readiness,
    visual_review_payload,
)


def _project(title="Container Gardening for Beginners"):
    p = database.create_project(title, "ebook", {"title": title})
    return int(p["id"] if isinstance(p, dict) else p)


class _StorageCase(unittest.TestCase):

    def setUp(self):
        for p in _paid_patches():
            p.start()
            self.addCleanup(p.stop)
        self.driver = InMemoryDriver()
        for target in ("services.storage.get_storage",
                       "services.storage.compat.get_storage"):
            p = patch(target, return_value=self.driver)
            p.start()
            self.addCleanup(p.stop)
        env = patch.dict(os.environ, {"FACTORY_PUBLISH_EXPORTS": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.builder_root = tempfile.mkdtemp(prefix="builder-exports-")
        self.website_root = tempfile.mkdtemp(prefix="website-exports-")
        self.addCleanup(shutil.rmtree, self.builder_root, True)
        self.addCleanup(shutil.rmtree, self.website_root, True)
        self.pid = _project()

    def _on(self, root):
        return patch.object(vp, "EXPORTS_DIR", root)

    def _build_on_builder(self):
        data = _manuscript_ready()
        data["_project_id"] = self.pid
        with self._on(self.builder_root), publishing_for_project(self.pid):
            data = prepare_visuals_local(data)
        return data


class PicturesTravelThroughStorageTests(_StorageCase):

    def test_pictures_made_inside_the_scope_are_published(self):
        data = self._build_on_builder()
        made = [a for a in required_aids(data["visual_plan"])
                if os.path.isfile(str(a.get("asset_path") or ""))]
        self.assertTrue(made, "the fixture produced no pictures at all")
        self.assertGreaterEqual(
            len(self.driver.objects), len(made),
            "pictures were made on the builder but not published -- the "
            "website can never show them (the v1.8.1 gap)")

    def test_the_website_sees_every_picture_with_no_shared_disk(self):
        data = self._build_on_builder()
        with self._on(self.builder_root):
            before = validate_visual_readiness(data)
        # The builder's temporary disk is gone when the task ends.
        shutil.rmtree(self.builder_root)
        with self._on(self.website_root):
            after = validate_visual_readiness(data)
            review = visual_review_payload(data)
        self.assertEqual(after.findings, before.findings,
                         "the website judged the pictures differently from "
                         "the builder that made them")
        self.assertFalse(any("no existing local asset" in f for f in after.findings),
                         after.findings)
        assets = review.get("assets") or []
        self.assertTrue(assets)
        self.assertTrue(all(a.get("has_file") for a in assets),
                        "the review screen reports pictures as missing")
        self.assertTrue(all(a.get("thumb_data_uri") for a in assets),
                        "the review screen has no thumbnail to show")

    def test_a_later_builder_run_finds_pictures_from_an_earlier_one(self):
        data = self._build_on_builder()
        shutil.rmtree(self.builder_root)
        fresh_run = tempfile.mkdtemp(prefix="builder-run-2-")
        self.addCleanup(shutil.rmtree, fresh_run, True)
        with self._on(fresh_run):
            moved = vp.localize_visual_plan(data, project_id=self.pid)
        self.assertGreater(moved, 0)
        for aid in required_aids(data["visual_plan"]):
            path = str(aid.get("asset_path") or "")
            if path:
                self.assertTrue(path.startswith(fresh_run), path)
                self.assertTrue(os.path.isfile(path), path)

    def test_outside_a_scope_nothing_is_published_and_nothing_breaks(self):
        data = _manuscript_ready()
        with self._on(self.builder_root):
            prepare_visuals_local(data)
        self.assertEqual(self.driver.objects, {})

    def test_a_missing_picture_storage_cannot_supply_stays_missing(self):
        aid = {"visual_id": "v_x",
               "asset_path": os.path.join(self.builder_root, "pkg", "visuals", "v_x.png")}
        with self._on(self.website_root):
            self.assertEqual(vp.local_visual_path(aid, project_id=self.pid),
                             aid["asset_path"])
            self.assertEqual(vp.localize_visual_plan(
                {"visual_plan": {"chapters": [{"chapter": "c", "aids": [aid]}]}},
                project_id=self.pid), 0)

    def test_windows_paths_map_to_the_same_storage_key(self):
        self.assertEqual(vp._visual_relpath(r"C:\x\exports\pkg-1\visuals\v1.png"),
                         "pkg-1/visuals/v1.png")
        self.assertEqual(vp._visual_relpath("/tmp/factory-exports/pkg-1/visuals/v1.png"),
                         "pkg-1/visuals/v1.png")
        self.assertEqual(vp._visual_relpath("/tmp/other/file.png"), "")


class FinishedFilesReachTheWebsiteTests(_StorageCase):

    def _package(self):
        import uuid

        pkg = f"ebook-v184-{uuid.uuid4().hex[:12]}"
        d = Path(self.builder_root) / pkg
        d.mkdir(parents=True)
        (d / "ebook.pdf").write_bytes(b"%PDF-1.4 finished book" * 50)
        (d / "package.zip").write_bytes(b"PK\x03\x04 finished zip" * 50)
        (d / "notes.txt").write_bytes(b"not a customer download")
        return pkg, {n: str(d / n) for n in ("ebook.pdf", "package.zip", "notes.txt")}

    def test_pdf_and_zip_are_published_and_nothing_else(self):
        from services.ebook_build_orchestrator import _publish_export_files

        pkg, files = self._package()
        self.assertEqual(_publish_export_files(self.pid, self.builder_root, files), 2)
        keys = sorted(self.driver.objects)
        self.assertTrue(any(k.endswith(f"{pkg}/ebook.pdf") for k in keys), keys)
        self.assertTrue(any(k.endswith(f"{pkg}/package.zip") for k in keys), keys)
        self.assertFalse(any(k.endswith("notes.txt") for k in keys), keys)

    def test_the_website_download_serves_the_published_pdf(self):
        import app as app_module
        from services.ebook_build_orchestrator import _publish_export_files

        pkg, files = self._package()
        _publish_export_files(self.pid, self.builder_root, files)
        shutil.rmtree(self.builder_root)
        with patch.object(app_module, "EXPORTS_DIR", self.website_root):
            resp = app_module.app.test_client().get(f"/download/{pkg}/ebook.pdf")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True)[:300])
        self.assertTrue(resp.get_data().startswith(b"%PDF"))

    def test_inline_mode_publishes_nothing(self):
        from services.ebook_build_orchestrator import _publish_export_files

        _, files = self._package()
        with patch.dict(os.environ, {"FACTORY_PUBLISH_EXPORTS": "0"}):
            self.assertEqual(_publish_export_files(self.pid, self.builder_root, files), 0)
        self.assertEqual(self.driver.objects, {})


class ScopeIsSetAroundTheWorkTests(unittest.TestCase):

    def test_step_by_step_actions_name_the_book(self):
        from services import ebook_workspace_actions as wa

        seen = []
        fake = lambda data, payload, pid: seen.append(vp._PUBLISH_PROJECT.get()) or data  # noqa: E731
        with patch.dict(wa._HANDLERS, {"__probe__": fake}):
            wa.perform({}, project_id=42, route="__probe__")
        self.assertEqual(seen, [42])
        self.assertEqual(vp._PUBLISH_PROJECT.get(), 0, "the scope leaked")

    def test_the_orchestrator_names_the_book_around_each_stage(self):
        src = Path(vp.__file__).resolve().parents[1] / "services" / "ebook_build_orchestrator.py"
        text = src.read_text(encoding="utf-8")
        self.assertIn("with publishing_for_project(project_id):", text)
        self.assertIn("localize_visual_plan(work, project_id=project_id)", text)


if __name__ == "__main__":
    unittest.main()
