"""Gate 6: Publish/Next Steps → Save → reopen does not mutate the artifact.

Deterministic local math_worksheet fixture under FACTORY_TEST_MODE.
Publication metadata may be stored; the approved artifact must stay identical.
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
    "worksheet_title": "Gate6 Publish Save Immutability",
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


class PublishSaveReopenImmutabilityTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self._project_ids: list[int] = []

    def tearDown(self):
        for pid in self._project_ids:
            try:
                self.client.delete(f"/projects/{pid}")
            except Exception:
                pass

    def test_publish_next_steps_save_reopen_keeps_artifact_immutable(self):
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
            raise AssertionError("must not export PDF/ZIP during publish/save/reopen")

        def cover_boom(*a, **k):
            gen_calls["cover"] += 1
            raise AssertionError("must not generate cover during publish/save/reopen")

        def publishing_boom(*a, **k):
            gen_calls["publishing"] += 1
            raise AssertionError("must not call publishing preview during this flow")

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
                return {"error": f"forbidden during Gate 6: {path}"}, 500
            return None

        with patch.object(product_mod, "generate_product", side_effect=gen_wrap), patch.object(
            mw, "build_math_worksheet_pdf", side_effect=build_wrap
        ), patch.object(
            packaging_mod, "build_product_export", side_effect=export_boom
        ), patch.object(
            cover_mod, "generate_cover", side_effect=cover_boom
        ), patch.object(
            publishing_mod, "build_publishing_preview", side_effect=publishing_boom
        ):
            app.before_request_funcs.setdefault(None, []).append(_guard_routes)
            try:
                # 1: Preview
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

                # 2: Save Project (first authoritative save)
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
                self.assertEqual(baseline["content_digest"], preview["content_digest"])
                self.assertEqual(
                    baseline["asset_manifest_digest"], preview["asset_manifest_digest"]
                )
                self.assertEqual(baseline["qa_status"], "accepted")
                gen_after_save = dict(gen_calls)

                # 3: Open Publish / Next Steps WITHOUT external publish
                with_pub = dict(saved_data)
                with_pub["publication"] = {
                    "studio_opened": True,
                    "intent": "next_steps",
                    "external_publish": False,
                    "platform": None,
                }
                with_pub["next_steps"] = {
                    "panel": "post_save",
                    "opened_at": "2026-08-10T00:00:00Z",
                }
                put_ns = self.client.put(
                    f"/projects/{project_id}",
                    json={
                        "name": saved["name"],
                        "type": "product",
                        "user_saved": True,
                        "data": with_pub,
                    },
                )
                self.assertEqual(put_ns.status_code, 200, put_ns.data)
                after_ns = put_ns.get_json().get("data") or {}
                self.assertEqual(_identity_snapshot(project_id, after_ns), baseline)
                self.assertEqual(after_ns.get("publication"), with_pub["publication"])
                self.assertEqual(after_ns.get("next_steps"), with_pub["next_steps"])
                self.assertNotIn("ebook", str(after_ns.get("product_type") or "").lower())

                # 4: Save again (idempotent — no new revision)
                put_again = self.client.put(
                    f"/projects/{project_id}",
                    json={
                        "name": saved["name"],
                        "type": "product",
                        "user_saved": True,
                        "data": after_ns,
                    },
                )
                self.assertEqual(put_again.status_code, 200, put_again.data)
                after_save2 = put_again.get_json().get("data") or {}
                self.assertEqual(_identity_snapshot(project_id, after_save2), baseline)
                self.assertEqual(int(after_save2.get("artifact_revision") or 0), 1)

                # 5: Reopen (Saved Projects / Open Product)
                reopen = self.client.get(f"/projects/{project_id}")
                self.assertEqual(reopen.status_code, 200)
                reopened = reopen.get_json()
                self.assertEqual(int(reopened["id"]), project_id)
                rdata = reopened.get("data") or {}
                self.assertEqual(_identity_snapshot(project_id, rdata), baseline)
                self.assertEqual(rdata.get("publication"), with_pub["publication"])
                self.assertEqual(rdata.get("next_steps"), with_pub["next_steps"])

                # 6–8: No regenerate / cover / PDF / ZIP / publishing during flow
                self.assertEqual(
                    gen_calls["generate_product"] - gen_after_save["generate_product"], 0
                )
                self.assertEqual(
                    gen_calls["build_math"] - gen_after_save["build_math"], 0
                )
                self.assertEqual(gen_calls["export"], 0)
                self.assertEqual(gen_calls["cover"], 0)
                self.assertEqual(gen_calls["publishing"], 0)
                self.assertEqual(forbidden_hits, [])

                # Prove enhance / export / publishing routes stay unused
                enhance_probe = self.client.post(
                    "/enhance-ebook", json={"project_id": project_id}
                )
                self.assertEqual(enhance_probe.status_code, 500)
                self.assertIn("/enhance-ebook", forbidden_hits)

                # 9: Mutation of approved artifact is blocked with a clear error
                mutated = dict(rdata)
                mutated["problems"] = list(baseline["problems"]) + [
                    {"prompt": "MUTATED", "answer": "9"}
                ]
                mut_resp = self.client.put(
                    f"/projects/{project_id}",
                    json={"data": mutated},
                )
                self.assertEqual(mut_resp.status_code, 400, mut_resp.data)
                err = mut_resp.get_json() or {}
                self.assertIn("identity mismatch", (err.get("error") or "").lower())

                digest_mut = dict(rdata)
                digest_mut["content_digest"] = "0" * 64
                dig_resp = self.client.put(
                    f"/projects/{project_id}",
                    json={"data": digest_mut},
                )
                self.assertEqual(dig_resp.status_code, 400, dig_resp.data)
                self.assertIn(
                    "identity mismatch",
                    ((dig_resp.get_json() or {}).get("error") or "").lower(),
                )

                # 10: After blocked mutation, reopen still matches baseline
                after_block = self.client.get(f"/projects/{project_id}").get_json()
                self.assertEqual(
                    _identity_snapshot(project_id, after_block.get("data") or {}),
                    baseline,
                )
                self.assertEqual(
                    (after_block.get("data") or {}).get("publication"),
                    with_pub["publication"],
                )

                # 11: Repeated Save remains idempotent (still revision 1)
                put_third = self.client.put(
                    f"/projects/{project_id}",
                    json={
                        "name": saved["name"],
                        "type": "product",
                        "data": after_block.get("data") or {},
                    },
                )
                self.assertEqual(put_third.status_code, 200, put_third.data)
                third = put_third.get_json().get("data") or {}
                self.assertEqual(_identity_snapshot(project_id, third), baseline)
                self.assertEqual(int(third.get("artifact_revision") or 0), 1)
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
