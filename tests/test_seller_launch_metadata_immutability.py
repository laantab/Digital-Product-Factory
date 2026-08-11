"""Gate 7: Seller-package / launch-metadata / publishing-details cannot mutate artifacts.

Deterministic local math_worksheet fixture under FACTORY_TEST_MODE.
Seller/launch/publication metadata may be stored; the approved artifact must stay identical.
"""
from __future__ import annotations

import base64
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

from app import app  # noqa: E402
from services.quality.artifact_identity import (  # noqa: E402
    asset_manifest_digest,
    content_digest_from_pdf_bytes,
)


FIELDS = {
    "worksheet_title": "Gate7 Seller Launch Metadata Immutability",
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


class SellerLaunchMetadataImmutabilityTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self._project_ids: list[int] = []

    def tearDown(self):
        for pid in self._project_ids:
            try:
                self.client.delete(f"/projects/{pid}")
            except Exception:
                pass

    def test_seller_launch_publishing_metadata_keeps_artifact_immutable(self):
        import app as app_mod
        import services.ad as ad_mod
        import services.packaging as packaging_mod
        import services.product as product_mod
        import services.product_cover_agent as cover_mod
        import services.publishing as publishing_mod
        from services.math_worksheet import pdf_builder as mw

        gen_calls = {
            "generate_product": 0,
            "build_math": 0,
            "export": 0,
            "cover": 0,
            "publishing": 0,
            "seller_ai": 0,
            "launch_ai": 0,
        }
        forbidden_hits: list[str] = []
        orig_gen = product_mod.generate_product
        orig_build = mw.build_math_worksheet_pdf

        def gen_wrap(*a, **k):
            gen_calls["generate_product"] += 1
            return orig_gen(*a, **k)

        def build_wrap(*a, **k):
            gen_calls["build_math"] += 1
            return orig_build(*a, **k)

        def export_boom(*a, **k):
            gen_calls["export"] += 1
            raise AssertionError("must not export PDF/ZIP during seller/launch/metadata flow")

        def cover_boom(*a, **k):
            gen_calls["cover"] += 1
            raise AssertionError("must not generate cover during seller/launch/metadata flow")

        def publishing_boom(*a, **k):
            gen_calls["publishing"] += 1
            raise AssertionError("must not call publishing preview during this flow")

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

        def _guard_routes():
            from flask import request as flask_request

            path = flask_request.path or ""
            if path in {
                "/export-product",
                "/enhance-ebook",
                "/generate-publishing",
                "/save-publishing",
            }:
                forbidden_hits.append(path)
                return {"error": f"forbidden during Gate 7: {path}"}, 500
            return None

        with patch.object(product_mod, "generate_product", side_effect=gen_wrap), patch.object(
            mw, "build_math_worksheet_pdf", side_effect=build_wrap
        ), patch.object(
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
            app.before_request_funcs.setdefault(None, []).append(_guard_routes)
            try:
                # 1: Preview + save deterministic non-ebook artifact
                preview_resp = self.client.post(
                    "/generate-product",
                    json={"product_type": "math_worksheet", "fields": FIELDS},
                )
                self.assertEqual(preview_resp.status_code, 200, preview_resp.data)
                preview = preview_resp.get_json()
                self.assertEqual(preview.get("product_type"), "math_worksheet")
                self.assertNotEqual(preview.get("product_type"), "ebook")
                self.assertTrue(preview.get("content_digest"))
                self.assertTrue(preview.get("asset_manifest_digest"))
                self.assertEqual(int(preview.get("artifact_revision") or 0), 1)
                self.assertEqual(
                    preview["content_digest"],
                    content_digest_from_pdf_bytes(base64.b64decode(preview["pdf_bytes"])),
                )
                self.assertEqual(
                    preview["asset_manifest_digest"], asset_manifest_digest(preview)
                )

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
                saved_data = saved.get("data") or {}
                baseline = _identity_snapshot(project_id, saved_data)
                self.assertEqual(baseline["qa_status"], "accepted")
                gen_after_save = dict(gen_calls)

                # 2: Seller-package / launch-metadata / publishing-details save paths
                #    (no external publish; seller/launch AI mocked locally)
                seller_resp = self.client.post(
                    "/generate-seller-package",
                    json={"project_id": project_id, "platform": "etsy"},
                )
                self.assertEqual(seller_resp.status_code, 200, seller_resp.data)
                seller_body = seller_resp.get_json() or {}
                self.assertEqual(seller_body.get("platform"), "etsy")
                self.assertEqual(
                    (seller_body.get("package") or {}).get("product_title"),
                    "Local fixture listing",
                )

                launch_resp = self.client.post(
                    "/generate-launch-package",
                    json={"project_id": project_id, "promotion_goal": "sell_paid_product"},
                )
                self.assertEqual(launch_resp.status_code, 200, launch_resp.data)
                self.assertTrue((launch_resp.get_json() or {}).get("ok"))

                after_routes = self.client.get(f"/projects/{project_id}").get_json()
                route_data = after_routes.get("data") or {}
                self.assertEqual(_identity_snapshot(project_id, route_data), baseline)
                self.assertIn("etsy", route_data.get("packages") or {})
                self.assertTrue(isinstance(route_data.get("_launch_package"), dict))
                self.assertNotIn("ebook", str(route_data.get("product_type") or "").lower())

                with_meta = dict(route_data)
                with_meta["publishing"] = {
                    "details": {
                        "product_title": baseline["title"],
                        "subtitle": "Publishing details only",
                        "keywords": ["addition", "grade3"],
                    },
                    "studio_opened": True,
                    "external_publish": False,
                }
                with_meta["publication"] = {
                    "intent": "seller_launch_prep",
                    "external_publish": False,
                    "platform": None,
                }
                with_meta["launch"] = {
                    "metadata_saved": True,
                    "notes": "Next Steps publish-prep fields only",
                }
                with_meta["next_steps"] = {
                    "panel": "seller_launch",
                    "opened_at": "2026-08-10T00:00:00Z",
                }
                put_meta = self.client.put(
                    f"/projects/{project_id}",
                    json={
                        "name": saved["name"],
                        "type": "product",
                        "user_saved": True,
                        "data": with_meta,
                    },
                )
                self.assertEqual(put_meta.status_code, 200, put_meta.data)
                after_meta = put_meta.get_json().get("data") or {}

                # 3: Digests / ids / revision / content unchanged
                self.assertEqual(_identity_snapshot(project_id, after_meta), baseline)
                self.assertEqual(int(after_meta.get("artifact_revision") or 0), 1)
                self.assertEqual(after_meta.get("content_digest"), baseline["content_digest"])
                self.assertEqual(
                    after_meta.get("asset_manifest_digest"),
                    baseline["asset_manifest_digest"],
                )
                self.assertEqual(after_meta.get("qa_status"), "accepted")

                # 8: Publication/seller metadata remains separate from artifact content
                self.assertEqual(
                    (after_meta.get("packages") or {}).get("etsy", {}).get("product_title"),
                    "Local fixture listing",
                )
                self.assertEqual(
                    (after_meta.get("_launch_package") or {}).get("launch_checklist"),
                    "1. Prep listing\n2. Soft launch",
                )
                self.assertEqual(after_meta.get("publishing"), with_meta["publishing"])
                self.assertEqual(after_meta.get("publication"), with_meta["publication"])
                self.assertEqual(after_meta.get("launch"), with_meta["launch"])
                self.assertNotEqual(
                    after_meta.get("publishing"),
                    {
                        "content_digest": after_meta.get("content_digest"),
                        "problems": after_meta.get("problems"),
                    },
                )

                # 9: Repeated metadata-only save is idempotent (revision unchanged)
                put_again = self.client.put(
                    f"/projects/{project_id}",
                    json={
                        "name": saved["name"],
                        "type": "product",
                        "user_saved": True,
                        "data": after_meta,
                    },
                )
                self.assertEqual(put_again.status_code, 200, put_again.data)
                after_save2 = put_again.get_json().get("data") or {}
                self.assertEqual(_identity_snapshot(project_id, after_save2), baseline)
                self.assertEqual(int(after_save2.get("artifact_revision") or 0), 1)

                # 4: Reopen project — still identical
                reopen = self.client.get(f"/projects/{project_id}")
                self.assertEqual(reopen.status_code, 200)
                reopened = reopen.get_json()
                self.assertEqual(int(reopened["id"]), project_id)
                rdata = reopened.get("data") or {}
                self.assertEqual(_identity_snapshot(project_id, rdata), baseline)
                self.assertEqual(rdata.get("publishing"), with_meta["publishing"])
                self.assertIn("etsy", rdata.get("packages") or {})
                self.assertTrue(isinstance(rdata.get("_launch_package"), dict))

                # 6–7: No ebook substitution; no generate/enhance/cover/PDF/ZIP/publishing
                self.assertEqual(
                    gen_calls["generate_product"] - gen_after_save["generate_product"], 0
                )
                self.assertEqual(gen_calls["build_math"] - gen_after_save["build_math"], 0)
                self.assertEqual(gen_calls["export"], 0)
                self.assertEqual(gen_calls["cover"], 0)
                self.assertEqual(gen_calls["publishing"], 0)
                self.assertEqual(forbidden_hits, [])
                # Local mocks only — no real seller/launch platform/AI traffic
                self.assertEqual(gen_calls["seller_ai"], 1)
                self.assertEqual(gen_calls["launch_ai"], 1)

                enhance_probe = self.client.post(
                    "/enhance-ebook", json={"project_id": project_id}
                )
                self.assertEqual(enhance_probe.status_code, 500)
                self.assertIn("/enhance-ebook", forbidden_hits)
                export_probe = self.client.post(
                    "/export-product", json={"project_id": project_id}
                )
                self.assertEqual(export_probe.status_code, 500)
                self.assertIn("/export-product", forbidden_hits)

                # 5: Smuggle content mutation via publishing payload → blocked
                smuggled = dict(rdata)
                smuggled["publishing"] = {
                    "details": {"hack": True},
                    "stolen_problems": list(baseline["problems"]),
                }
                smuggled["problems"] = list(baseline["problems"]) + [
                    {"prompt": "SMUGGLED VIA PUBLISHING", "answer": "9"}
                ]
                smuggled["title"] = "Hijacked Via Publishing Payload"
                smuggled["content_digest"] = "0" * 64
                smuggle_resp = self.client.put(
                    f"/projects/{project_id}",
                    json={"data": smuggled},
                )
                self.assertEqual(smuggle_resp.status_code, 400, smuggle_resp.data)
                err = smuggle_resp.get_json() or {}
                self.assertIn("identity mismatch", (err.get("error") or "").lower())

                rev_smuggle = dict(rdata)
                rev_smuggle["publishing"] = {"details": {"ok": True}}
                rev_smuggle["artifact_revision"] = int(baseline["artifact_revision"]) + 1
                rev_resp = self.client.put(
                    f"/projects/{project_id}",
                    json={"data": rev_smuggle},
                )
                self.assertEqual(rev_resp.status_code, 400, rev_resp.data)
                self.assertIn(
                    "identity mismatch",
                    ((rev_resp.get_json() or {}).get("error") or "").lower(),
                )

                # After blocked mutations, reopen still matches baseline + metadata
                after_block = self.client.get(f"/projects/{project_id}").get_json()
                blocked_data = after_block.get("data") or {}
                self.assertEqual(_identity_snapshot(project_id, blocked_data), baseline)
                self.assertEqual(blocked_data.get("publishing"), with_meta["publishing"])
                self.assertEqual(
                    (blocked_data.get("packages") or {}).get("etsy", {}).get("product_title"),
                    "Local fixture listing",
                )
                self.assertEqual(int(blocked_data.get("artifact_revision") or 0), 1)
                self.assertEqual(
                    gen_calls["generate_product"] - gen_after_save["generate_product"], 0
                )
                self.assertEqual(gen_calls["export"], 0)
                self.assertEqual(gen_calls["publishing"], 0)
            finally:
                funcs = app.before_request_funcs.get(None) or []
                if _guard_routes in funcs:
                    funcs.remove(_guard_routes)


if __name__ == "__main__":
    unittest.main()
