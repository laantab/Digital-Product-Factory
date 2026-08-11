"""Gate 8: Non-PUT persistence enforces approved-artifact immutability.

Covers `_persist_product_data` and launch/seller database-write paths.
Deterministic local math_worksheet fixture under FACTORY_TEST_MODE.
"""
from __future__ import annotations

import base64
import copy
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""

from app import app, _persist_product_data  # noqa: E402
from services.quality.artifact_identity import (  # noqa: E402
    content_digest_from_pdf_bytes,
    stamp_artifact_identity,
)


FIELDS = {
    "worksheet_title": "Gate8 Non-PUT Persistence Immutability",
    "grade": "3",
    "math_topic": "Addition",
    "difficulty": "Easy",
    "problems": "6",
    "include_answer_key": "Yes",
    "include_challenge": "No",
    "output_format": "Single Worksheet",
    "audience": "Grade 3 students",
    "goal": "Practice addition facts",
}


def _identity_snapshot(project_id: int, data: dict) -> dict:
    pdf = base64.b64decode(data["pdf_bytes"]) if data.get("pdf_bytes") else b""
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    return {
        "project_id": project_id,
        "artifact_id": data.get("artifact_id") or data.get("package_id"),
        "artifact_revision": int(data.get("artifact_revision") or 0),
        "product_type": data.get("product_type"),
        "title": data.get("title"),
        "problems": list(data.get("problems") or []),
        "pages": data.get("pages"),
        "words": data.get("words"),
        "challenge_problems": data.get("challenge_problems"),
        "image_jobs": list(data.get("image_jobs") or []),
        "cover_ref": (
            cover.get("local_image_path")
            or cover.get("asset_url")
            or cover.get("image_url")
            or data.get("cover_image")
            or ""
        ),
        "content_digest": data.get("content_digest"),
        "asset_manifest_digest": data.get("asset_manifest_digest"),
        "qa_status": data.get("qa_status"),
        "pdf_digest": content_digest_from_pdf_bytes(pdf) if pdf else None,
        "package_id": data.get("package_id"),
    }


def _mutated_artifact(data: dict) -> dict:
    mutated = copy.deepcopy(data)
    mutated["title"] = "Hijacked Via Non-PUT Persist"
    mutated["artifact_id"] = "hijacked-artifact-id"
    mutated["artifact_revision"] = int(data.get("artifact_revision") or 1) + 7
    mutated["content_digest"] = "0" * 64
    mutated["asset_manifest_digest"] = "f" * 64
    mutated["qa_status"] = "tampered"
    mutated["problems"] = list(data.get("problems") or []) + [
        {"prompt": "SMUGGLED", "answer": "9"}
    ]
    pdf = base64.b64decode(data["pdf_bytes"]) if data.get("pdf_bytes") else b"%PDF-1.4\n%%EOF\n"
    mutated["pdf_bytes"] = base64.b64encode(pdf + b"\n%mutated\n").decode("ascii")
    mutated["cover_design"] = {
        **(data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}),
        "local_image_path": "exports/tampered/img_cover.png",
    }
    return mutated


class NonPutPersistenceImmutabilityTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self._project_ids: list[int] = []

    def tearDown(self):
        for pid in self._project_ids:
            try:
                self.client.delete(f"/projects/{pid}")
            except Exception:
                pass

    def _save_stamped_fixture(self) -> tuple[int, dict, dict]:
        import services.product as product_mod
        from services.math_worksheet import pdf_builder as mw

        with patch.object(product_mod, "generate_product", wraps=product_mod.generate_product), patch.object(
            mw, "build_math_worksheet_pdf", wraps=mw.build_math_worksheet_pdf
        ):
            preview_resp = self.client.post(
                "/generate-product",
                json={"product_type": "math_worksheet", "fields": FIELDS},
            )
        self.assertEqual(preview_resp.status_code, 200, preview_resp.data)
        preview = preview_resp.get_json()
        stamp_artifact_identity(preview)
        self.assertTrue(preview.get("content_digest"))
        self.assertTrue(preview.get("asset_manifest_digest"))

        save_resp = self.client.post(
            "/projects",
            json={
                "name": preview["title"],
                "type": "product",
                "user_saved": True,
                "temporary": True,
                "system_test": True,
                "data": {
                    **preview,
                    "audience": FIELDS["audience"],
                    "goal": FIELDS["goal"],
                    "qa_status": "accepted",
                },
            },
        )
        self.assertEqual(save_resp.status_code, 201, save_resp.data)
        saved = save_resp.get_json()
        project_id = int(saved["id"])
        self._project_ids.append(project_id)
        data = saved.get("data") or {}
        return project_id, saved, _identity_snapshot(project_id, data)

    def test_persist_product_data_metadata_only_and_blocks_mutation(self):
        """Prove items 1–2, 5–6 for the shared `_persist_product_data` boundary."""
        import database

        project_id, saved, baseline = self._save_stamped_fixture()
        project = database.get_project(project_id)
        self.assertIsNotNone(project)

        meta = dict(project.get("data") or {})
        meta["publication"] = {"intent": "metadata_only", "external_publish": False}
        meta["next_steps"] = {"panel": "gate8", "opened_at": "2026-08-10T00:00:00Z"}
        meta["launch"] = {"metadata_saved": True, "notes": "persist boundary"}

        gen_hits: list[str] = []

        def _forbid(*_a, **_k):
            gen_hits.append("generate")
            raise AssertionError("must not generate during persist metadata")

        with patch("services.product.generate_product", side_effect=_forbid), patch(
            "services.packaging.build_product_export", side_effect=_forbid
        ):
            _persist_product_data(project, meta)

        after = database.get_project(project_id)
        after_data = after.get("data") or {}
        self.assertEqual(_identity_snapshot(project_id, after_data), baseline)
        self.assertEqual(after_data.get("publication"), meta["publication"])
        self.assertEqual(after_data.get("next_steps"), meta["next_steps"])
        self.assertEqual(after_data.get("launch"), meta["launch"])

        # Idempotent metadata re-save
        _persist_product_data(after, dict(after_data))
        again = database.get_project(project_id).get("data") or {}
        self.assertEqual(_identity_snapshot(project_id, again), baseline)
        self.assertEqual(int(again.get("artifact_revision") or 0), baseline["artifact_revision"])

        # Mutation attempt blocked; record unchanged
        mutated = _mutated_artifact(again)
        with self.assertRaises(ValueError) as ctx:
            _persist_product_data(database.get_project(project_id), mutated)
        self.assertIn("identity mismatch", str(ctx.exception).lower())

        blocked = database.get_project(project_id).get("data") or {}
        self.assertEqual(_identity_snapshot(project_id, blocked), baseline)
        self.assertEqual(blocked.get("publication"), meta["publication"])
        self.assertEqual(gen_hits, [])

    def test_launch_and_seller_paths_metadata_ok_mutation_blocked(self):
        """Prove items 3–6 for launch-package and seller-package DB-write paths."""
        import app as app_mod
        import services.ad as ad_mod
        import services.packaging as packaging_mod
        import services.product as product_mod
        import services.product_cover_agent as cover_mod
        import services.publishing as publishing_mod

        project_id, saved, baseline = self._save_stamped_fixture()
        gen_calls = {
            "generate_product": 0,
            "export": 0,
            "cover": 0,
            "publishing": 0,
            "seller_ai": 0,
            "launch_ai": 0,
        }

        def seller_fake(platform, project):
            gen_calls["seller_ai"] += 1
            return {
                "platform": platform,
                "platform_label": "Etsy",
                "product_title": "Local fixture listing",
                "short_description": "Deterministic seller package",
                "tags": ["math", "worksheet", "grade3"],
            }

        def launch_fake(funnel_context, promotion_goal="sell_paid_product"):
            gen_calls["launch_ai"] += 1
            return {
                "launch_checklist": "1. Prep listing\n2. Soft launch",
                "launch_email": {"subject": "Launch", "body": "Go live"},
                "freebie": {"freebie_name": "Sample", "freebie_format": "PDF"},
            }

        def export_boom(*_a, **_k):
            gen_calls["export"] += 1
            raise AssertionError("must not export during Gate 8")

        def cover_boom(*_a, **_k):
            gen_calls["cover"] += 1
            raise AssertionError("must not generate cover during Gate 8")

        def publishing_boom(*_a, **_k):
            gen_calls["publishing"] += 1
            raise AssertionError("must not call publishing during Gate 8")

        def gen_boom(*_a, **_k):
            gen_calls["generate_product"] += 1
            raise AssertionError("must not regenerate product during Gate 8")

        with patch.object(product_mod, "generate_product", side_effect=gen_boom), patch.object(
            packaging_mod, "build_product_export", side_effect=export_boom
        ), patch.object(
            cover_mod, "generate_cover", side_effect=cover_boom
        ), patch.object(
            publishing_mod, "build_publishing_preview", side_effect=publishing_boom
        ), patch.object(
            app_mod, "generate_seller_package", side_effect=seller_fake
        ), patch.object(
            app_mod, "generate_launch_package", side_effect=launch_fake
        ), patch.object(
            ad_mod, "generate_launch_package", side_effect=launch_fake
        ):
            # Metadata-only via seller + launch routes
            seller_resp = self.client.post(
                "/generate-seller-package",
                json={"project_id": project_id, "platform": "etsy"},
            )
            self.assertEqual(seller_resp.status_code, 200, seller_resp.data)

            launch_resp = self.client.post(
                "/generate-launch-package",
                json={"project_id": project_id, "promotion_goal": "sell_paid_product"},
            )
            self.assertEqual(launch_resp.status_code, 200, launch_resp.data)
            self.assertTrue((launch_resp.get_json() or {}).get("ok"))

            after = self.client.get(f"/projects/{project_id}").get_json()
            route_data = after.get("data") or {}
            self.assertEqual(_identity_snapshot(project_id, route_data), baseline)
            self.assertIn("etsy", route_data.get("packages") or {})
            self.assertTrue(isinstance(route_data.get("_launch_package"), dict))

            # Direct `_persist_product_data` seller-like metadata append (idempotent)
            import database

            project = database.get_project(project_id)
            meta = dict(project.get("data") or {})
            meta["packages"] = {
                **(meta.get("packages") or {}),
                "etsy": {
                    **((meta.get("packages") or {}).get("etsy") or {}),
                    "tags": ["math", "worksheet", "grade3", "addition"],
                },
            }
            _persist_product_data(project, meta)
            after_meta = database.get_project(project_id).get("data") or {}
            self.assertEqual(_identity_snapshot(project_id, after_meta), baseline)
            self.assertEqual(
                (after_meta.get("packages") or {}).get("etsy", {}).get("product_title"),
                "Local fixture listing",
            )

            # Block content / asset / digest / id / revision / PDF substitution
            # through the shared persist boundary used by seller + launch.
            for label, payload in (
                ("content", {"problems": list(baseline["problems"]) + [{"x": 1}]}),
                ("digest", {"content_digest": "0" * 64}),
                ("asset_digest", {"asset_manifest_digest": "a" * 64}),
                ("artifact_id", {"artifact_id": "stolen-id"}),
                ("revision", {"artifact_revision": baseline["artifact_revision"] + 1}),
                ("title", {"title": "Stolen Title"}),
                ("qa", {"qa_status": "forged"}),
            ):
                with self.subTest(mutation=label):
                    current = database.get_project(project_id)
                    attempt = dict(current.get("data") or {})
                    attempt.update(payload)
                    with self.assertRaises(ValueError) as ctx:
                        _persist_product_data(current, attempt)
                    self.assertIn("identity mismatch", str(ctx.exception).lower())
                    stored = database.get_project(project_id).get("data") or {}
                    self.assertEqual(_identity_snapshot(project_id, stored), baseline)

            # PDF substitution blocked
            current = database.get_project(project_id)
            pdf_mut = dict(current.get("data") or {})
            raw = base64.b64decode(pdf_mut["pdf_bytes"])
            pdf_mut["pdf_bytes"] = base64.b64encode(raw + b"\n%swap\n").decode("ascii")
            with self.assertRaises(ValueError):
                _persist_product_data(current, pdf_mut)
            stored = database.get_project(project_id).get("data") or {}
            self.assertEqual(_identity_snapshot(project_id, stored), baseline)

            # Launch-path persist cannot smuggle mutation alongside package metadata
            launch_mut = dict(stored)
            launch_mut["_launch_package"] = {"launch_checklist": "legit meta"}
            launch_mut.update(
                {
                    "title": "Launch Smuggle",
                    "content_digest": "1" * 64,
                    "artifact_revision": baseline["artifact_revision"] + 3,
                }
            )
            with self.assertRaises(ValueError):
                _persist_product_data(database.get_project(project_id), launch_mut)

            # Seller route path: packages metadata ok already; mutation via persist
            seller_mut = dict(database.get_project(project_id).get("data") or {})
            seller_mut["packages"] = {
                **(seller_mut.get("packages") or {}),
                "etsy": {"product_title": "ok meta"},
            }
            seller_mut["package_id"] = "substituted-zip-identity"
            seller_mut["pdf_bytes"] = base64.b64encode(
                base64.b64decode(seller_mut["pdf_bytes"]) + b"\n%zip\n"
            ).decode("ascii")
            with self.assertRaises(ValueError):
                _persist_product_data(database.get_project(project_id), seller_mut)

            final = database.get_project(project_id).get("data") or {}
            self.assertEqual(_identity_snapshot(project_id, final), baseline)
            self.assertIn("etsy", final.get("packages") or {})
            self.assertTrue(isinstance(final.get("_launch_package"), dict))
            self.assertEqual(gen_calls["generate_product"], 0)
            self.assertEqual(gen_calls["export"], 0)
            self.assertEqual(gen_calls["cover"], 0)
            self.assertEqual(gen_calls["publishing"], 0)
            self.assertEqual(gen_calls["seller_ai"], 1)
            self.assertEqual(gen_calls["launch_ai"], 1)

            # HTTP seller/launch still return 400 when persist rejects (patch
            # generate to return ok, but pre-corrupt via wrapping persist).
            import app as app_module

            original_persist = app_module._persist_product_data

            def persist_then_try_mutate(project, data):
                # First call (from route) should succeed for metadata; prove
                # wrapper still enforces by attempting a second illegal write.
                original_persist(project, data)
                bad = _mutated_artifact(data)
                original_persist(project, bad)

            with patch.object(app_module, "_persist_product_data", side_effect=persist_then_try_mutate):
                bad_seller = self.client.post(
                    "/generate-seller-package",
                    json={"project_id": project_id, "platform": "kdp"},
                )
                self.assertEqual(bad_seller.status_code, 400, bad_seller.data)
                err = (bad_seller.get_json() or {}).get("error") or ""
                self.assertIn("identity mismatch", err.lower())

            unchanged = database.get_project(project_id).get("data") or {}
            self.assertEqual(_identity_snapshot(project_id, unchanged), baseline)
            # kdp may have been written before the illegal second persist;
            # artifact identity must still match baseline regardless.
            self.assertEqual(
                unchanged.get("content_digest"),
                baseline["content_digest"],
            )
            self.assertEqual(
                int(unchanged.get("artifact_revision") or 0),
                baseline["artifact_revision"],
            )


if __name__ == "__main__":
    unittest.main()
