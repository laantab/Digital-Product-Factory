"""The Editor-in-Chief blocks clear manuscript defects before PDF rendering."""
from __future__ import annotations

from pathlib import Path

from services.ebook_pre_export_review import review_before_pdf


def test_review_catches_duplicate_opening_sentence_and_production_visual_copy():
    sentence = "Many parents picture connected spaces as part of everyday family life."
    data = {
        "content": f"## Chapter 1\n\n{sentence}\n\n{sentence}\n",
        "visual_plan": {"chapters": [{"aids": [{
            "type": "workflow", "visual_id": "plan-1",
            "title": "Family plan", "caption": "Workflow graphic for Family Plan. Follow the chapter steps in order.",
        }]}]},
    }
    html = f"<html><body><p>{sentence}</p><p>{sentence}</p></body></html>"

    report = review_before_pdf(data, rendered_html=html)

    assert report["status"] == "NEEDS_CORRECTION"
    codes = {finding["code"] for finding in report["findings"]}
    assert "REPEATED_SENTENCE" in codes
    assert "PRODUCTION_COPY_LEAK" in codes
    assert report["paid_calls"] == 0
    assert report["reviewed_before_pdf"] is True


def test_review_flags_a_paragraph_cut_off_at_a_function_word_but_does_not_invent_copy():
    data = {"content": "A child needs trusted adults who will listen and"}
    report = review_before_pdf(data)

    finding = next(f for f in report["findings"] if f["code"] == "INCOMPLETE_PARAGRAPH")
    assert report["status"] == "NEEDS_CORRECTION"
    assert "will not invent" in finding["action"]


def test_complete_prose_and_finished_visual_caption_pass():
    data = {
        "content": "Parents can review the plan together each month and update it as children grow.",
        "visual_plan": {"chapters": [{"aids": [{
            "type": "workflow", "visual_id": "plan-1", "title": "Family plan",
            "caption": "A step-by-step plan for the family.",
        }]}]},
    }
    report = review_before_pdf(data, rendered_html="<html><body><p>Clear finished prose.</p></body></html>")
    assert report["status"] == "PASS"
    assert report["findings"] == []


def test_new_workflow_visual_uses_reader_facing_copy():
    from services.ebook_visual_pipeline import _choose_aid

    aid = _choose_aid(0, "Create a Family Plan", (
        "#### 1. Agree on goals\nChoose shared goals.\n"
        "#### 2. Set the rules\nWrite down clear expectations.\n"
        "#### 3. Review together\nRevisit the plan regularly."
    ))
    assert aid["type"] == "workflow"
    assert "graphic for" not in aid["caption"].lower()
    assert "follow the chapter steps" not in aid["caption"].lower()


def test_designed_renderer_runs_pre_export_review_before_pdf_conversion():
    import pytest
    import services.ebook_design_export as export
    from services.ebook_pre_export_review import PreExportReviewBlocked

    source = (Path(__file__).resolve().parents[1] / "services" / "ebook_design_export.py").read_text()
    start = source.index("def render_designed_bundle")
    body = source[start:source.index("\ndef ", start + 10)]
    review = body.index("review_before_pdf(data, rendered_html=html_doc)")
    conversion = body.index("pdf_bytes = _merge(html_doc)")
    assert review < conversion

    class Design:
        theme_id = "test"
        digest = "test"

    sentence = "Many parents picture connected spaces as part of everyday family life."
    data = {"title": "Test", "content": f"{sentence}\n\n{sentence}"}
    monkeypatch = pytest.MonkeyPatch()
    pdf_calls = []
    try:
        monkeypatch.setattr(export, "require_quality_pass", lambda _data: None)
        monkeypatch.setattr(export, "EbookDesign", type("Factory", (), {
            "from_dict": staticmethod(lambda _value: Design())
        }))
        monkeypatch.setattr(export, "design_is_stale", lambda *_args, **_kwargs: False)
        monkeypatch.setattr(export, "render_designed_ebook_html", lambda **_kwargs: (
            f"<html><body><p>{sentence}</p><p>{sentence}</p></body></html>"
        ))
        monkeypatch.setattr(export, "_html_to_pdf", lambda *_args, **_kwargs: pdf_calls.append(True))
        with pytest.raises(PreExportReviewBlocked):
            export.render_designed_bundle(data)
        assert pdf_calls == []
        assert data["editor_in_chief_pre_export"]["status"] == "NEEDS_CORRECTION"
    finally:
        monkeypatch.undo()


def test_blocked_report_is_exposed_by_the_build_status_payload():
    from services.ebook_build_orchestrator import status_payload

    report = {
        "status": "NEEDS_CORRECTION",
        "findings": [{"code": "REPEATED_SENTENCE", "action": "Remove the duplicate."}],
    }
    payload = status_payload({"editor_in_chief_pre_export": report}, 37)
    assert payload["editor_in_chief_pre_export"] == report
