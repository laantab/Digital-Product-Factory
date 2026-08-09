from types import SimpleNamespace
from unittest import mock


class _Page:
    page_number = 1
    topic = "Thunder Volt"
    image_path = ""
    line_art_prompt = ""

    def as_dict(self):
        return {
            "page_number": 1,
            "topic": self.topic,
            "quality_pass": False,
        }


@mock.patch("services.coloring_book.pdf_builder.validate_theme_adherence", return_value=(True, []))
@mock.patch("services.coloring_book.pdf_builder.build_coloring_book")
def test_full_coloring_book_qa_failure_returns_no_pdf(mock_build, _mock_theme):
    from services.coloring_book.pdf_builder import (
        ColoringBookPdfRequest,
        build_coloring_book_pdf,
    )

    mock_build.return_value = SimpleNamespace(
        errors=[],
        warnings=[],
        pages=[_Page()],
        quality_result={
            "all_passed": False,
            "blocked_export": True,
            "total_failed": 1,
            "pages": [_Page().as_dict()],
        },
        character_bible={},
        cover_prompt="",
        consistency_notes=[],
        product_title="Thunder Volt",
        subtitle="",
    )

    result = build_coloring_book_pdf(
        ColoringBookPdfRequest(
            product_title="Thunder Volt",
            theme="Black superhero stopping a bank robbery in New York City",
            quality_mode="basic_test",
            generation_stage="full",
        )
    )

    assert result.pdf_bytes == b""
    assert result.errors
    assert "QA blocked" in result.errors[0]
    assert result.qa_result["blocked_export"] is True


def test_release_manifests_and_cursor_rule_exist():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert (root / "requirements.txt").is_file()
    assert (root / "requirements-dev.txt").is_file()
    assert (root / ".cursor" / "rules" / "factory-stability.mdc").is_file()
    assert (root / "tests" / "acceptance_manifest.json").is_file()
