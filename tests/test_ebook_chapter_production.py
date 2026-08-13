"""Pass C: chapter production pipeline and professional pagination.

All generation is mocked. Zero paid/external calls. Does not mutate project #2472.
"""
from __future__ import annotations

import hashlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app import app  # noqa: E402
import database  # noqa: E402
from services.ebook_book_layout import render_designed_ebook_html  # noqa: E402
from services.ebook_design_export import render_strong_fixture_bundle  # noqa: E402
from services.ebook_design_preflight import PREFLIGHT_PASS, run_design_preflight  # noqa: E402
from services.ebook_manuscript_engine import (  # noqa: E402
    FROZEN_2472_REMAINING_USD,
    FROZEN_2472_SHA256,
    FROZEN_2472_SPENT_USD,
    QUALITY_PASS,
    EXAMPLE_BUY_VS_RENT_VS_USED,
    assigned_research_for_chapter,
    build_book_contract,
    chapter_fn_from_full_manuscript,
    run_chapter_pipeline,
)
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript  # noqa: E402
from services.ebook_project_workspace import (  # noqa: E402
    CHAPTER_UNIT_USD,
    ONESHOT_WORKSPACE_BLOCKED,
    STATUS_AWAITING,
    STATUS_NEEDS_CORRECTION,
    estimate_paid_action,
    execute_correct_manuscript,
    execute_generate_manuscript,
    upsert_acceptance_project,
)

FIXTURE_DIR = ROOT / "exports" / "ebook_design_fixture_pass_c"


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class ChapterProductionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self._client_patch = patch("ai_client.get_client", side_effect=AssertionError("paid client"))
        self._chat_patch = patch("ai_client.chat", side_effect=AssertionError("paid chat"))
        self._json_patch = patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json"))
        self._client_patch.start()
        self._chat_patch.start()
        self._json_patch.start()
        self.project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        self.pid = self.project["id"]

    def tearDown(self):
        self._client_patch.stop()
        self._chat_patch.stop()
        self._json_patch.stop()

    def _data(self):
        return dict(database.get_project(self.pid)["data"])

    def test_01_one_chapter_per_provider_request(self):
        data = self._data()
        est = estimate_paid_action(data, "generate_manuscript")
        self.assertEqual(float(est["estimate"]["per_chapter_max_usd"]), CHAPTER_UNIT_USD)
        self.assertEqual(int(est["estimate"]["pending_chapter_count"]), 10)
        self.assertEqual(int(est["estimate"]["accepted_chapter_count"]), 0)
        self.assertAlmostEqual(float(est["estimate"]["max_total_usd"]), 1.5, places=3)
        self.assertTrue(est["estimate"]["confirmation_required"])
        seen = []

        def _fn(book, chapter):
            seen.append(chapter.order)
            return {"ebook": f"## {chapter.title}\n\nToo thin.\n"}

        out = execute_generate_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="c-one-at-a-time",
            generate_chapter_fn=_fn,
        )
        self.assertEqual(seen, [1])
        self.assertEqual(out["result"]["chapter_calls"], 1)
        self.assertEqual(out["result"]["failed_orders"], [1])
        self.assertAlmostEqual(float(out["result"]["charge_usd"]), CHAPTER_UNIT_USD, places=3)

    def test_02_contract_and_research_reach_provider_unchanged(self):
        data = self._data()
        book = build_book_contract(data)
        expected = book.chapters[0]
        expected_research = assigned_research_for_chapter(book, expected)
        seen = {}

        def _fn(book_c, chapter):
            seen["digest"] = chapter.digest()
            seen["research"] = assigned_research_for_chapter(book_c, chapter)
            seen["title"] = chapter.title
            return {"ebook": f"## {chapter.title}\n\nToo thin.\n", "assigned_research": seen["research"]}

        est = estimate_paid_action(data, "generate_manuscript")
        execute_generate_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="c-contract-unchanged",
            generate_chapter_fn=_fn,
        )
        self.assertEqual(seen["digest"], expected.digest())
        self.assertEqual(seen["research"], expected_research)
        self.assertEqual(seen["title"], expected.title)

    def test_02b_generate_one_chapter_prompt_lists_canonical_example_and_findings(self):
        from services.ebook import generate_one_chapter

        data = self._data()
        book = build_book_contract(data)
        ch3 = next(c for c in book.chapters if c.order == 3)
        ch3.unresolved_findings = [
            f"MISSING_REQUIRED_EXAMPLE: Missing required example: {EXAMPLE_BUY_VS_RENT_VS_USED}"
        ]
        ch3.prior_chapter_body = "Keep the starter-vs-event-kit table already drafted."
        captured = {}

        def _chat(*, system, user):
            captured["system"] = system
            captured["user"] = user
            return f"## {ch3.title}\n\nToo thin.\n"

        with patch("services.ebook.chat", side_effect=_chat):
            generate_one_chapter(book, ch3)
        user = captured["user"]
        self.assertIn(EXAMPLE_BUY_VS_RENT_VS_USED, user)
        self.assertIn("MANDATORY DELIVERABLE", user)
        self.assertIn("UNRESOLVED FINDINGS FROM THE PRIOR ATTEMPT", user)
        self.assertIn("MISSING_REQUIRED_EXAMPLE", user)
        self.assertIn("Keep the starter-vs-event-kit table already drafted.", user)
        self.assertIn("Do not invent current market prices", user)
        self.assertIn("AUTHORITATIVE CHAPTER CONTRACT", user)

    def test_03_04_05_accepted_preserved_failure_stops_resume_from_failed(self):
        data = self._data()
        strong = build_event_photo_strong_manuscript()
        splitter = chapter_fn_from_full_manuscript(strong)
        calls = []

        def _fail_at_three(book, chapter):
            calls.append(chapter.order)
            if chapter.order == 3:
                return {"ebook": f"## {chapter.title}\n\nToo thin to pass this chapter.\n"}
            return splitter(book, chapter)

        est = estimate_paid_action(data, "generate_manuscript")
        out = execute_generate_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="c-stop-at-3",
            generate_chapter_fn=_fail_at_three,
        )
        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(out["result"]["chapter_calls"], 3)
        self.assertEqual(out["result"]["failed_orders"], [3])
        self.assertEqual(out["result"]["manuscript_status"], STATUS_NEEDS_CORRECTION)
        accepted = out["data"]["ebook_workspace"]["accepted_chapters"]
        self.assertEqual([c["order"] for c in accepted], [1, 2])
        first_body = accepted[0]["body"]
        spent_after_fail = float(out["result"]["spent_usd"])

        data = out["data"]
        corr = estimate_paid_action(data, "correct_manuscript")
        self.assertEqual(int(corr["estimate"]["accepted_chapter_count"]), 2)
        self.assertEqual(int(corr["estimate"]["resume_from_order"]), 3)
        resume_calls = []

        def _resume(book, chapter):
            resume_calls.append(chapter.order)
            self.assertNotIn(chapter.order, (1, 2))
            if chapter.order == 3:
                self.assertTrue(chapter.unresolved_findings)
            return splitter(book, chapter)

        fixed = execute_correct_manuscript(
            data,
            confirmation_token=corr["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=corr["estimate"]["outline_digest"],
            max_authorized_usd=float(corr["estimate"]["max_authorized_usd"]),
            idempotency_key="c-resume-3",
            correct_chapter_fn=_resume,
        )
        self.assertTrue(resume_calls)
        self.assertEqual(resume_calls[0], 3)
        self.assertNotIn(1, resume_calls)
        self.assertNotIn(2, resume_calls)
        kept = [c for c in fixed["data"]["ebook_workspace"]["accepted_chapters"] if c["order"] == 1]
        self.assertEqual(kept[0]["body"], first_body)
        self.assertGreater(float(fixed["result"]["spent_usd"]), spent_after_fail)

    def test_06_idempotency_prevents_duplicate_charges(self):
        data = self._data()
        est = estimate_paid_action(data, "generate_manuscript")
        calls = {"n": 0}

        def _fn(book, chapter):
            calls["n"] += 1
            return {"ebook": f"## {chapter.title}\n\nToo thin.\n"}

        kwargs = dict(
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="c-idem-1",
            generate_chapter_fn=_fn,
        )
        first = execute_generate_manuscript(data, **kwargs)
        spent = float(first["result"]["spent_usd"])
        second = execute_generate_manuscript(first["data"], **kwargs)
        self.assertTrue(second.get("duplicate") or second["result"].get("duplicate") or second.get("ok"))
        self.assertEqual(calls["n"], 1)
        self.assertAlmostEqual(float(second["result"]["spent_usd"] or spent), spent, places=4)

    def test_07_full_manuscript_assembles_only_after_all_pass(self):
        data = self._data()
        md = build_event_photo_strong_manuscript()
        est = estimate_paid_action(data, "generate_manuscript")
        out = execute_generate_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="c-assemble-all",
            generate_chapter_fn=chapter_fn_from_full_manuscript(md),
        )
        self.assertEqual(out["result"]["manuscript_status"], STATUS_AWAITING)
        self.assertEqual(out["result"]["chapter_calls"], 10)
        self.assertEqual(out["result"].get("quality_status"), QUALITY_PASS)
        content = out["data"]["content"]
        self.assertIn("**Disclaimer**", content)
        self.assertIn("**Sources**", content)
        self.assertNotIn("## Disclaimer", content)
        self.assertNotIn("## Sources", content)
        self.assertAlmostEqual(float(out["result"]["charge_usd"]), 1.5, places=3)

    def test_08_oneshot_workspace_generation_blocked(self):
        data = self._data()
        est = estimate_paid_action(data, "generate_manuscript")
        with self.assertRaises(ValueError) as ctx:
            execute_generate_manuscript(
                data,
                confirmation_token=est["estimate"]["confirmation_token"],
                expected_artifact_id=str(data.get("artifact_id") or ""),
                expected_revision=int(data.get("artifact_revision") or 1),
                outline_digest_expected=est["estimate"]["outline_digest"],
                max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
                idempotency_key="c-oneshot-blocked",
                generate_fn=lambda *a, **k: {"ebook": build_event_photo_strong_manuscript()},
            )
        self.assertIn("One-shot", str(ctx.exception))
        self.assertIn("chapter pipeline", ONESHOT_WORKSPACE_BLOCKED.lower())
        r = self.client.post(
            "/generate-ebook",
            json={"project_id": self.pid, "source": "x", "author": "Lonnie Brown"},
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("legacy", r.get_json().get("error", "").lower())

    def test_09_10_every_chapter_starts_new_page_and_density_fails(self):
        html = render_designed_ebook_html(
            title="From First Booking to On-Site Prints",
            subtitle="A Practical Guide",
            author="Lonnie Brown",
            manuscript_md=build_event_photo_strong_manuscript(),
            design=type("D", (), {"theme_id": "studio_clean"})(),
        )
        self.assertIn("<pdf:nextpage", html)
        self.assertGreaterEqual(html.count("chapter-page"), 10)
        self.assertGreaterEqual(html.count("<pdf:nextpage"), 12)

        from tests.test_ebook_design_export import _pages_pdf
        from services.ebook_project_workspace import build_acceptance_project_data

        data = build_acceptance_project_data()
        data["content"] = build_event_photo_strong_manuscript()
        data["ebook"] = data["content"]
        packed = _pages_pdf(
            ["Cover From First Booking Lonnie Brown"]
            + ["Chapter 1Hello Chapter 2Hello Chapter 3Hello " + ("body " * 40)] * 9
        )
        report = run_design_preflight(data, pdf_bytes=packed)
        codes = {f.code for f in report.findings}
        self.assertTrue({"packed_chapters", "overcrowded_page", "too_few_pages"} & codes)
        self.assertNotEqual(report.status, PREFLIGHT_PASS)

    def test_11_preview_pdf_zip_identity_and_fixture_pages(self):
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        bundle = render_strong_fixture_bundle(FIXTURE_DIR)
        inspection = bundle["inspection"]
        self.assertGreaterEqual(inspection["page_count"], 16)
        self.assertEqual(bundle["preflight"]["status"], PREFLIGHT_PASS, bundle["preflight"]["findings"][:12])
        identity = bundle["identity"]
        self.assertEqual(identity["preview_digest"], identity["pdf_sha256"])
        self.assertTrue(identity["zip_sha256"])
        self.assertTrue(Path(inspection["contact_sheet"]).is_file())
        from pypdf import PdfReader
        import io
        import re

        reader = PdfReader(io.BytesIO(bundle["pdf_bytes"]))
        texts = [(p.extract_text() or "") for p in reader.pages]
        seen_on = {}
        for i, text in enumerate(texts):
            m = re.match(r"\s*Chapter\s+(\d+)", text or "")
            if m:
                n = int(m.group(1))
                self.assertNotIn(n, seen_on, f"Chapter {n} opener repeated")
                seen_on[n] = i
        self.assertEqual(sorted(seen_on), list(range(1, 11)))
        self.assertEqual(len(set(seen_on.values())), 10)

    def test_12_project_2472_unchanged(self):
        live = database.get_project(2472)
        self.assertIsNotNone(live)
        data = live["data"]
        md = str(data.get("content") or "")
        self.assertEqual(_sha(md), FROZEN_2472_SHA256)
        ledger = data["ebook_workspace"]["paid_call_ledger"]
        self.assertAlmostEqual(float(ledger["spent_usd"]), FROZEN_2472_SPENT_USD, places=3)
        self.assertAlmostEqual(float(ledger["remaining_usd"]), FROZEN_2472_REMAINING_USD, places=3)
        self.assertEqual(data["ebook_workspace"]["rail"]["manuscript"]["status"], "awaiting_approval")

    def test_13_pipeline_rejects_oneshot_engine_path(self):
        data = self._data()
        book = build_book_contract(data)
        with self.assertRaises(ValueError):
            run_chapter_pipeline(book, generate_fn=lambda **k: {"ebook": "nope"})

    def test_14_estimate_ui_copy(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Maximum total:", js)
        self.assertIn("Per-chapter maximum:", js)
        self.assertIn("Accepted chapters:", js)
        self.assertIn("Pending chapters:", js)
        self.assertIn("Confirmation required", js)


if __name__ == "__main__":
    unittest.main()
