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


def test_dotenv_is_loaded_with_override_so_env_file_wins():
    """.env must beat a stale variable already in the OS environment.

    python-dotenv's default is to leave an existing environment variable
    alone. On 2026-08-29 a revoked TAVILY_API_KEY left behind in the Windows
    user environment silently shadowed the working key in .env: live research
    failed with 401 while .env looked correct and tested fine in isolation.
    Every load_dotenv() call in the app must pass override=True, or the file
    stops being the single source of truth for configuration.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("app.py", "ai_client.py"):
        lines = (root / name).read_text(encoding="utf-8").splitlines()
        # Checked per line rather than by regex: the argument list nests
        # parentheses (os.path.join(...)), which a naive pattern truncates.
        calls = [ln.strip() for ln in lines if "load_dotenv(" in ln and "import" not in ln]
        assert calls, f"{name} no longer calls load_dotenv"
        for call in calls:
            assert "override=" in call, (
                f"{name} has `{call}` with no explicit override=; python-dotenv "
                f"then defaults to override=False and a stale OS environment "
                f"variable silently beats .env"
            )


def test_dotenv_does_not_override_the_environment_in_test_mode():
    """...but under FACTORY_TEST_MODE the harness must own the environment.

    tests/test_ebook_real_browser_customer_path.py starts an isolated server as
    a subprocess with OPENAI_API_KEY and friends set to "". That subprocess runs
    outside conftest's network guard, so those blanks are the only thing keeping
    it from making real paid calls. An unconditional override=True refilled them
    from .env with live credentials.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["FACTORY_TEST_MODE"] = "1"
    env["OPENAI_API_KEY"] = ""
    env["TAVILY_API_KEY"] = ""
    env["PEXELS_API_KEY"] = ""
    # A fresh interpreter, because app.py resolves this once at import time.
    proc = subprocess.run(
        [sys.executable, "-c",
         "import app, os;"
         "print(repr(os.environ.get('OPENAI_API_KEY')),"
         " repr(os.environ.get('TAVILY_API_KEY')),"
         " repr(os.environ.get('PEXELS_API_KEY')))"],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, f"importing app failed: {proc.stderr[-800:]}"
    assert proc.stdout.strip().endswith("'' '' ''"), (
        f"blanked keys were refilled from .env in test mode: {proc.stdout.strip()}"
    )
