"""Copy edits are reversible, cost-free, and cannot bypass chapter contracts."""
from services.ebook_copy_editor import edit_text


def test_copy_edit_and_idempotency():
    original = "Teh reader should of checked thier seperate notes. He are ready.\n"
    report = edit_text(original)
    assert report["edited"] == "The reader should have checked their separate notes. He is ready.\n"
    assert report["original"] == original
    assert report["original_sha256"] != report["edited_sha256"]
    assert report["paid_calls"] == 0
    assert edit_text(report["edited"])["changes"] == []


def test_protected_content_numbers_and_subjunctive_survive():
    protected = ('## Teh Heading\n> teh quoted source\n'
                 '| teh | 10.5 mg |\n```python\nteh = 42\n```\n'
                 '~~~\nteh\n~~~\n'
                 '"teh" ‘thier’ \'teh\' `teh` [teh](https://x.test/teh) https://x.test/teh\n'
                 'If he were ready, the price would remain $12.50 at 8 mg.\n')
    assert edit_text(protected)["edited"] == protected


def test_advisory_findings_do_not_rewrite_meaning():
    original = " ".join(["complexity"] * 110) + "."
    report = edit_text(original, target_grade=6)
    assert report["edited"] == original
    assert {f["code"] for f in report["suggestions"]} == {"LONG_SENTENCE", "READING_LEVEL"}
    assert "comprehensive grammar" in report["not_checked"]


def test_pipeline_applies_and_checkpoints_edits_without_extra_provider_calls(monkeypatch):
    from services import ebook_manuscript_engine as engine
    from services.ebook_project_workspace import _save_editorial_revisions
    book = engine.build_book_contract({"title": "Gardening", "outline": [
        {"title": "Tools", "purpose": "tools"},
        {"title": "Seeds", "purpose": "seeds"},
        {"title": "Water", "purpose": "water"},
    ]})
    monkeypatch.setattr(engine, "validate_chapter", lambda *a, **kw: [])
    calls = []
    ws = {}
    def provider(book, chapter):
        calls.append(chapter.order)
        return {"content": "Teh gardener should of checked the the seeds.",
                "provider": "local", "billable_calls": 0}
    result = engine.run_chapter_pipeline(book, generate_chapter_fn=provider,
        on_chapter_accepted=lambda chapters: _save_editorial_revisions(ws, chapters))
    assert len(calls) == len(book.chapters)
    assert result["billable_chapter_calls"] == 0
    assert all(c.body == "The gardener should have checked the seeds." for c in result["chapters"])
    assert len(ws["editorial_revisions"]) == len(book.chapters)
    first = ws["editorial_revisions"]["1"][0]
    assert first["original"].startswith("Teh") and first["applied"]


def test_editor_rolls_back_if_it_breaks_a_contract(monkeypatch):
    from services import ebook_manuscript_engine as engine
    book = engine.build_book_contract({"title": "Gardening", "outline": [
        {"title": "Tools", "purpose": "tools"}, {"title": "Seeds", "purpose": "seeds"},
        {"title": "Water", "purpose": "water"}]})
    def validator(parsed, contract, **kwargs):
        return [] if "teh" in parsed.body else [engine.ChapterFinding(
            contract.order, contract.title, "FACT", "Required literal was removed", engine.QUALITY_FAIL)]
    monkeypatch.setattr(engine, "validate_chapter", validator)
    result = engine.run_chapter_pipeline(book, generate_chapter_fn=lambda *args: {
        "content": "Use teh as the literal example.", "provider": "local", "billable_calls": 0})
    assert all("teh" in c.body for c in result["chapters"])
    assert all(c.editorial_report["applied"] is False for c in result["chapters"])
