"""Contract-driven Ebook manuscript quality engine.

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
from services.ebook_manuscript_engine import (  # noqa: E402
    FROZEN_2472_REMAINING_USD,
    FROZEN_2472_SHA256,
    FROZEN_2472_SPENT_USD,
    QUALITY_FAIL,
    QUALITY_NEEDS_CORRECTION,
    QUALITY_PASS,
    EXAMPLE_BUY_VS_RENT_VS_USED,
    build_book_contract,
    canonical_example_id,
    chapter_contract_prompt,
    chapter_fn_from_full_manuscript,
    remap_outline_purposes,
    run_chapter_pipeline,
    split_front_chapters_back,
    validate_chapter,
    validate_manuscript_quality,
    word_count,
)
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript  # noqa: E402
from services.ebook_outline_fidelity import normalize_chapter_title  # noqa: E402
from services.ebook_project_workspace import (  # noqa: E402
    REVISED_ACCEPTANCE_OUTLINE_TITLES,
    STATUS_AWAITING,
    STATUS_NEEDS_CORRECTION,
    approve_stage,
    edit_outline,
    estimate_paid_action,
    execute_correct_manuscript,
    execute_generate_manuscript,
    outline_digest,
    stage_status,
    upsert_acceptance_project,
    workspace_public_view,
)


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _thin_ms() -> str:
    parts = ["# From First Booking to On-Site Prints\n"]
    for t in REVISED_ACCEPTANCE_OUTLINE_TITLES:
        parts.append(f"## {t}\n\nShort practical paragraph about {t.lower()}.\n")
    parts.append("\n**Disclaimer** Educational only.\n\n**Sources** notes only.\n")
    return "\n".join(parts)


def _padded_ms() -> str:
    pad = ("This is generic filler without tables or workflows. " * 80) + "Consistency is key. "
    parts = ["# From First Booking to On-Site Prints\n"]
    for t in REVISED_ACCEPTANCE_OUTLINE_TITLES:
        parts.append(f"## {t}\n\n{pad}\n{pad}\n")
    parts.append("\n**Disclaimer** Educational only.\n\n**Sources** notes only.\n")
    return "\n".join(parts)


class ManuscriptQualityEngineTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self.project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        self.pid = self.project["id"]

    def _data(self):
        return dict(database.get_project(self.pid)["data"])

    def test_revised_titles_do_not_keep_earlier_purposes(self):
        previous = [
            {"order": 1, "title": "What This Business Actually Looks Like", "purpose": "niches"},
            {"order": 2, "title": "Packages Clients Can Understand", "purpose": "hours and deliverables"},
        ]
        new = [
            {"order": 1, "title": "What This Business Actually Looks Like", "purpose": "hours and deliverables"},
            {"order": 2, "title": "Finding Clients and Turning Inquiries into Signed Bookings", "purpose": "hours and deliverables"},
        ]
        out = remap_outline_purposes(new, previous_outline=previous)
        self.assertNotEqual(out[1]["purpose"], "hours and deliverables")
        self.assertIn("inquiry", out[1]["purpose"].lower())

    def test_edit_outline_remaps_purpose_when_title_changes(self):
        data = self._data()
        old_purpose = data["outline"][3]["purpose"]
        chapters = list(data["outline"])
        chapters[3] = {
            "order": 4,
            "title": "A Brand New Client Chapter",
            "purpose": old_purpose,
        }
        edited = edit_outline(data, chapters=chapters)
        self.assertNotEqual(edited["outline"][3]["purpose"], old_purpose)

    def test_generation_binds_and_uses_chapter_contract(self):
        data = self._data()
        est = estimate_paid_action(data, "generate_manuscript")
        self.assertTrue(est["estimate"].get("book_contract_digest"))
        self.assertEqual(len(est["estimate"].get("chapter_contract_digests") or []), 10)
        seen = []

        def _chapter_fn(book, chapter):
            seen.append(chapter.title)
            self.assertEqual(chapter.title, REVISED_ACCEPTANCE_OUTLINE_TITLES[chapter.order - 1])
            self.assertTrue(chapter.purpose)
            return {"ebook": f"## {chapter.title}\n\nToo thin to pass.\n"}

        out = execute_generate_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="ch-contract-1",
            generate_chapter_fn=_chapter_fn,
        )
        self.assertEqual(seen, [REVISED_ACCEPTANCE_OUTLINE_TITLES[0]])
        self.assertEqual(out["result"]["manuscript_status"], STATUS_NEEDS_CORRECTION)
        self.assertEqual(out["data"]["ebook_workspace"]["chapter_pipeline"]["chapter_calls"], 1)
        self.assertEqual(out["result"]["failed_orders"], [1])

    def test_chapters_validated_independently_and_preserved_on_repair(self):
        data = self._data()
        book = build_book_contract(data)
        strong = build_event_photo_strong_manuscript()
        quality = validate_manuscript_quality(data, manuscript_md=strong, book_contract=book)
        self.assertEqual(quality.status, QUALITY_PASS, quality.finding_messages[:8])

        from services.ebook_manuscript_engine import split_front_chapters_back

        _f, chapters, back = split_front_chapters_back(strong)
        thin = chapters[3]
        thin.body = "Too thin. inquiry contract deposit follow-up only."
        chapters[3] = thin
        preserved_body = chapters[0].body

        def _fix_real(book_c, chapter):
            orig = [c for c in split_front_chapters_back(strong)[1] if c.order == chapter.order][0]
            return {"ebook": f"## {chapter.title}\n\n{orig.body}"}

        pipe = run_chapter_pipeline(
            book,
            generate_chapter_fn=_fix_real,
            accepted_chapters=[c for c in chapters if c.order != 4],
            repair_orders=[4],
            back_matter=back,
        )
        self.assertEqual(pipe["chapter_calls"], 1)
        kept = [c for c in pipe["chapters"] if c.order == 1][0]
        self.assertEqual(kept.body, preserved_body)
        self.assertEqual(pipe["quality"].status, QUALITY_PASS)

    def test_missing_reordered_renamed_extra_fail(self):
        data = self._data()
        book = build_book_contract(data)
        strong = build_event_photo_strong_manuscript()
        titles = list(REVISED_ACCEPTANCE_OUTLINE_TITLES)
        missing = strong.replace(f"## {titles[-1]}", "## Bonus Extra Chapter")
        q = validate_manuscript_quality(data, manuscript_md=missing, book_contract=book)
        self.assertEqual(q.status, QUALITY_FAIL)
        extra = strong.replace(
            f"## {titles[0]}",
            f"## {titles[0]}\n\nHi.\n\n## Sneaky Extra\n\nNope.\n\n## {titles[0]}-dup",
        )
        # simpler extra: append H2
        extra = strong + "\n\n## Bonus Chapter\n\nExtra.\n"
        q2 = validate_manuscript_quality(data, manuscript_md=extra, book_contract=book)
        self.assertEqual(q2.status, QUALITY_FAIL)

    def test_thin_matching_titles_need_correction(self):
        data = self._data()
        q = validate_manuscript_quality(data, manuscript_md=_thin_ms())
        self.assertEqual(q.status, QUALITY_NEEDS_CORRECTION)
        self.assertTrue(any(f.code == "THIN_CHAPTER" for f in q.findings))
        self.assertTrue(q.outline_ok)

    def test_padding_without_substance_fails(self):
        data = self._data()
        q = validate_manuscript_quality(data, manuscript_md=_padded_ms())
        self.assertNotEqual(q.status, QUALITY_PASS)
        codes = {f.code for f in q.findings}
        self.assertTrue(
            {"MISSING_REQUIRED_TABLE", "PADDING_WITHOUT_SUBSTANCE", "GENERIC_FILLER"} & codes
        )

    def test_missing_required_deliverables_fail_chapter(self):
        data = self._data()
        md = build_event_photo_strong_manuscript()
        md = md.replace("| DS-RX1HS |", "| PrinterA |")
        md = md.replace("DS-RX1HS", "PrinterA")
        q = validate_manuscript_quality(data, manuscript_md=md)
        self.assertNotEqual(q.status, QUALITY_PASS)
        self.assertTrue(
            any("dye-sub" in (f.message or "").lower() or f.code == "MISSING_REQUIRED_TABLE" or f.code == "MISSING_REQUIRED_FACT" for f in q.findings)
        )

    def test_repeated_generic_and_unsupported_claims(self):
        data = self._data()
        body = (
            "You can do it. Believe in yourself. Guaranteed earnings of $10,000. "
            "Studies show you will earn $500 a day.\n\n"
        )
        md = _thin_ms().replace("Short practical", body + "Short practical")
        q = validate_manuscript_quality(data, manuscript_md=md)
        codes = {f.code for f in q.findings}
        self.assertTrue({"GENERIC_FILLER", "UNSUPPORTED_CLAIM"} & codes)

    def test_disclaimer_sources_unnumbered(self):
        data = self._data()
        strong = build_event_photo_strong_manuscript()
        q = validate_manuscript_quality(data, manuscript_md=strong)
        self.assertEqual(q.status, QUALITY_PASS, q.finding_messages[:12])
        numbered = strong + "\n\n## Sources\n\nhttps://example.com\n"
        q2 = validate_manuscript_quality(data, manuscript_md=numbered)
        self.assertEqual(q2.status, QUALITY_FAIL)

    def test_strong_fixture_passes_and_is_not_live_export(self):
        data = self._data()
        md = build_event_photo_strong_manuscript()
        self.assertGreater(word_count(md), 4000)
        q = validate_manuscript_quality(data, manuscript_md=md)
        self.assertEqual(q.status, QUALITY_PASS, q.finding_messages[:15])
        self.assertIn("**Disclaimer**", md)
        self.assertIn("**Sources**", md)
        self.assertNotIn("## Disclaimer", md)
        self.assertNotIn("## Sources", md)

    def test_strong_fixture_generation_enables_approve(self):
        data = self._data()
        est = estimate_paid_action(data, "generate_manuscript")
        md = build_event_photo_strong_manuscript()
        out = execute_generate_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="strong-pass-1",
            generate_chapter_fn=chapter_fn_from_full_manuscript(md),
        )
        self.assertEqual(out["result"]["manuscript_status"], STATUS_AWAITING)
        self.assertEqual(out["result"].get("quality_status"), QUALITY_PASS)
        view = workspace_public_view({"id": self.pid, "data": out["data"]})
        self.assertTrue(view["manuscript"]["can_approve"])
        self.assertTrue(view["gates"]["approve_manuscript_enabled"])
        approved = approve_stage(out["data"], "manuscript")
        self.assertEqual(stage_status(approved["ebook_workspace"], "manuscript"), "approved")

    def test_approve_hidden_unless_pass(self):
        data = self._data()
        est = estimate_paid_action(data, "generate_manuscript")
        out = execute_generate_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="thin-no-approve",
            generate_chapter_fn=chapter_fn_from_full_manuscript(_thin_ms()),
        )
        view = workspace_public_view({"id": self.pid, "data": out["data"]})
        self.assertFalse(view["manuscript"]["can_approve"])
        self.assertFalse(view["gates"]["approve_manuscript_enabled"])
        with self.assertRaises(ValueError):
            approve_stage(out["data"], "manuscript")

    def test_frozen_2472_rejected_and_unchanged(self):
        live = database.get_project(2472)
        self.assertIsNotNone(live)
        data = live["data"]
        md = str(data.get("content") or "")
        self.assertEqual(_sha(md), FROZEN_2472_SHA256)
        ws = data["ebook_workspace"]
        ledger = ws["paid_call_ledger"]
        self.assertAlmostEqual(float(ledger["spent_usd"]), FROZEN_2472_SPENT_USD, places=3)
        self.assertAlmostEqual(float(ledger["remaining_usd"]), FROZEN_2472_REMAINING_USD, places=3)
        self.assertEqual(ws["rail"]["manuscript"]["status"], "awaiting_approval")
        q = validate_manuscript_quality(data, manuscript_md=md)
        self.assertNotEqual(q.status, QUALITY_PASS)
        codes = {f.code for f in q.findings}
        self.assertTrue({"THIN_CHAPTER", "MISSING_REQUIRED_TABLE"} & codes)
        view = workspace_public_view(live)
        self.assertFalse(view["manuscript"]["can_approve"])
        after = database.get_project(2472)
        self.assertEqual(_sha(after["data"].get("content") or ""), FROZEN_2472_SHA256)
        self.assertEqual(after["data"]["ebook_workspace"]["rail"]["manuscript"]["status"], "awaiting_approval")
        self.assertAlmostEqual(
            float(after["data"]["ebook_workspace"]["paid_call_ledger"]["spent_usd"]),
            FROZEN_2472_SPENT_USD,
            places=3,
        )

    def test_other_paid_actions_and_zero_provider_calls(self):
        data = self._data()
        with patch("ai_client.chat") as chat:
            with patch("ai_client.chat_json") as chat_json:
                with patch("ai_client.get_client") as get_client:
                    est = estimate_paid_action(data, "generate_manuscript")
                    execute_generate_manuscript(
                        data,
                        confirmation_token=est["estimate"]["confirmation_token"],
                        expected_artifact_id=str(data.get("artifact_id") or ""),
                        expected_revision=int(data.get("artifact_revision") or 1),
                        outline_digest_expected=est["estimate"]["outline_digest"],
                        max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
                        idempotency_key="zero-calls",
                        generate_chapter_fn=chapter_fn_from_full_manuscript(_thin_ms()),
                    )
                    chat.assert_not_called()
                    chat_json.assert_not_called()
                    get_client.assert_not_called()
        # Research/title estimates still exist
        from services.ebook_project_workspace import PAID_ACTIONS

        self.assertIn("run_research", PAID_ACTIONS)
        self.assertIn("generate_title_options", PAID_ACTIONS)
        self.assertIn("generate_outline_options", PAID_ACTIONS)
        self.assertIn("correct_manuscript", PAID_ACTIONS)

    def test_ui_requires_quality_pass_for_approve_button(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('m.quality_status === "PASS"', js)
        self.assertIn("chapter_findings", js)
        self.assertIn("Chapter-level / QA findings", js)


class Chapter3RequiredExampleContractTests(unittest.TestCase):
    """Canonical BUY_VS_RENT_VS_USED must be in the prompt and the validator."""

    def setUp(self):
        app.config["TESTING"] = True
        self.project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        self.pid = self.project["id"]
        self._client_patch = patch("ai_client.get_client", side_effect=AssertionError("paid client"))
        self._chat_patch = patch("ai_client.chat", side_effect=AssertionError("paid chat"))
        self._json_patch = patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json"))
        self._client_patch.start()
        self._chat_patch.start()
        self._json_patch.start()

    def tearDown(self):
        self._client_patch.stop()
        self._chat_patch.stop()
        self._json_patch.stop()

    def _data(self):
        return dict(database.get_project(self.pid)["data"])

    def _book_and_ch3(self):
        book = build_book_contract(self._data())
        ch3 = next(c for c in book.chapters if c.order == 3)
        return book, ch3

    def _strong_ch3(self):
        strong = build_event_photo_strong_manuscript()
        _front, chapters, back = split_front_chapters_back(strong)
        ch3 = next(c for c in chapters if c.order == 3)
        return strong, chapters, back, ch3

    def _mention_only_body(self, good_body: str) -> str:
        marker = "**Hypothetical planning example: Buy vs. Rent vs. Used**"
        idx = good_body.find(marker)
        self.assertGreaterEqual(idx, 0)
        return (
            good_body[:idx]
            + "You might buy a camera or rent a lens. Used gear exists. "
            + "For example, some photographers buy a second body.\n"
        )

    def test_canonical_id_aliases_and_chapter_3_contract(self):
        self.assertEqual(canonical_example_id("used vs rent vs buy"), EXAMPLE_BUY_VS_RENT_VS_USED)
        self.assertEqual(canonical_example_id("Buy vs. Rent vs. Used"), EXAMPLE_BUY_VS_RENT_VS_USED)
        _book, ch3 = self._book_and_ch3()
        self.assertEqual(ch3.required_examples, [EXAMPLE_BUY_VS_RENT_VS_USED])

    def test_first_and_correction_prompts_require_labeled_three_way(self):
        book, ch3 = self._book_and_ch3()
        prompt = chapter_contract_prompt(book, ch3)
        self.assertIn(EXAMPLE_BUY_VS_RENT_VS_USED, prompt)
        self.assertIn("MANDATORY DELIVERABLE", prompt)
        self.assertIn("Buy vs. Rent vs. Used", prompt)
        self.assertIn("all three choices", prompt)
        self.assertIn("hypothetical", prompt.lower())
        self.assertIn("decision criteria", prompt.lower())
        self.assertIn("Do not invent current market prices", prompt)
        self.assertNotIn("UNRESOLVED FINDINGS FROM THE PRIOR ATTEMPT", prompt)

        ch3.unresolved_findings = [
            f"MISSING_REQUIRED_EXAMPLE: Missing required example: {EXAMPLE_BUY_VS_RENT_VS_USED}"
        ]
        ch3.prior_chapter_body = "Valid 24-70 and 70-200 kit material already drafted."
        corr = chapter_contract_prompt(book, ch3)
        self.assertIn("UNRESOLVED FINDINGS FROM THE PRIOR ATTEMPT", corr)
        self.assertIn("MISSING_REQUIRED_EXAMPLE", corr)
        self.assertIn(EXAMPLE_BUY_VS_RENT_VS_USED, corr)
        self.assertIn("Preserve all valid material", corr)
        self.assertIn("Valid 24-70 and 70-200 kit material already drafted.", corr)

    def test_mention_of_buying_or_renting_still_fails(self):
        book, contract = self._book_and_ch3()
        _strong, _chapters, _back, good = self._strong_ch3()
        mention = self._mention_only_body(good.body)
        good.body = mention
        findings = validate_chapter(good, contract, book=book)
        example_findings = [f for f in findings if f.code == "MISSING_REQUIRED_EXAMPLE"]
        self.assertTrue(example_findings, [f.code + ": " + f.message for f in findings])
        self.assertTrue(
            any(EXAMPLE_BUY_VS_RENT_VS_USED in f.message for f in example_findings)
        )

    def test_strong_three_way_example_is_accepted(self):
        book, contract = self._book_and_ch3()
        _strong, _chapters, _back, good = self._strong_ch3()
        findings = validate_chapter(good, contract, book=book)
        self.assertFalse(
            [f for f in findings if f.code == "MISSING_REQUIRED_EXAMPLE"],
            [f.code + ": " + f.message for f in findings],
        )

    def test_mocked_provider_following_correction_prompt_is_accepted(self):
        data = self._data()
        book = build_book_contract(data)
        strong, chapters, back, good_ch3 = self._strong_ch3()
        mention_body = self._mention_only_body(good_ch3.body)
        prior_md = strong.replace(good_ch3.body, mention_body, 1)
        accepted = [c for c in chapters if c.order in (1, 2)]
        for ch in accepted:
            ch.accepted = True
        seen_orders = []

        def _provider(book_c, chapter):
            seen_orders.append(chapter.order)
            prompt = chapter_contract_prompt(book_c, chapter)
            self.assertNotIn(chapter.order, (1, 2))
            self.assertIn(EXAMPLE_BUY_VS_RENT_VS_USED, prompt)
            self.assertTrue(chapter.unresolved_findings)
            self.assertTrue(
                any("MISSING_REQUIRED_EXAMPLE" in f for f in chapter.unresolved_findings)
            )
            self.assertIn("PRIOR CHAPTER DRAFT TO PRESERVE AND REPAIR", prompt)
            self.assertIn(chapter.prior_chapter_body[:80], prompt)
            if EXAMPLE_BUY_VS_RENT_VS_USED in prompt and chapter.unresolved_findings:
                return {"ebook": f"## {chapter.title}\n\n{good_ch3.body}"}
            return {"ebook": f"## {chapter.title}\n\nYou might buy or rent.\n"}

        pipe = run_chapter_pipeline(
            book,
            generate_chapter_fn=_provider,
            accepted_chapters=accepted,
            repair_orders=[3],
            stop_on_failure=True,
            max_chapter_calls=1,
            prior_manuscript_md=prior_md,
            findings_by_order={
                3: [
                    f"MISSING_REQUIRED_EXAMPLE: Missing required example: {EXAMPLE_BUY_VS_RENT_VS_USED}"
                ]
            },
            back_matter=back,
        )
        self.assertEqual(seen_orders, [3])
        self.assertEqual(pipe["chapter_calls"], 1)
        self.assertEqual(pipe["failed_orders"], [])
        accepted_orders = [c.order for c in pipe["accepted_chapters"]]
        self.assertIn(3, accepted_orders)
        ch3_out = next(c for c in pipe["accepted_chapters"] if c.order == 3)
        findings = validate_chapter(
            ch3_out,
            next(c for c in book.chapters if c.order == 3),
            book=book,
        )
        self.assertFalse(
            [f for f in findings if f.code == "MISSING_REQUIRED_EXAMPLE"],
            [f.code + ": " + f.message for f in findings],
        )
        kept = [c for c in pipe["accepted_chapters"] if c.order == 1]
        self.assertEqual(kept[0].body, chapters[0].body)

    def test_workspace_correction_does_not_regenerate_accepted_chapters(self):
        data = self._data()
        strong = build_event_photo_strong_manuscript()
        splitter = chapter_fn_from_full_manuscript(strong)
        calls = []

        def _fail_at_three(book, chapter):
            calls.append(chapter.order)
            if chapter.order == 3:
                _front, chapters, _back = split_front_chapters_back(strong)
                ch3 = next(c for c in chapters if c.order == 3)
                mention = self._mention_only_body(ch3.body)
                return {"ebook": f"## {chapter.title}\n\n{mention}"}
            return splitter(book, chapter)

        est = estimate_paid_action(data, "generate_manuscript")
        out = execute_generate_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="ch3-example-stop",
            generate_chapter_fn=_fail_at_three,
        )
        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(out["result"]["failed_orders"], [3])
        first_body = out["data"]["ebook_workspace"]["accepted_chapters"][0]["body"]
        second_body = out["data"]["ebook_workspace"]["accepted_chapters"][1]["body"]
        qa = " ".join(out["data"]["ebook_workspace"].get("manuscript_qa") or [])
        self.assertIn("MISSING_REQUIRED_EXAMPLE", qa)
        self.assertIn(EXAMPLE_BUY_VS_RENT_VS_USED, qa)

        resume_calls = []

        def _resume(book, chapter):
            resume_calls.append(chapter.order)
            self.assertNotIn(chapter.order, (1, 2))
            if chapter.order == 3:
                prompt = chapter_contract_prompt(book, chapter)
                self.assertIn(EXAMPLE_BUY_VS_RENT_VS_USED, prompt)
                self.assertTrue(chapter.unresolved_findings)
                self.assertTrue(
                    any("MISSING_REQUIRED_EXAMPLE" in f for f in chapter.unresolved_findings)
                )
            return splitter(book, chapter)

        corr = estimate_paid_action(out["data"], "correct_manuscript")
        fixed = execute_correct_manuscript(
            out["data"],
            confirmation_token=corr["estimate"]["confirmation_token"],
            expected_artifact_id=str(out["data"].get("artifact_id") or ""),
            expected_revision=int(out["data"].get("artifact_revision") or 1),
            outline_digest_expected=corr["estimate"]["outline_digest"],
            max_authorized_usd=float(corr["estimate"]["max_authorized_usd"]),
            idempotency_key="ch3-example-resume",
            correct_chapter_fn=_resume,
        )
        self.assertEqual(resume_calls[0], 3)
        self.assertNotIn(1, resume_calls)
        self.assertNotIn(2, resume_calls)
        kept = {
            c["order"]: c["body"]
            for c in fixed["data"]["ebook_workspace"]["accepted_chapters"]
            if c["order"] in (1, 2)
        }
        self.assertEqual(kept[1], first_body)
        self.assertEqual(kept[2], second_body)


if __name__ == "__main__":
    unittest.main()
