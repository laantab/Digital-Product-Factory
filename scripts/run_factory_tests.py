"""Reproducible Factory release gate. It never starts Flask or calls paid APIs."""
from __future__ import annotations

import compileall
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "acceptance_manifest.json"
RESULT_DIR = ROOT / "test-results"
JUNIT = RESULT_DIR / "factory-junit.xml"

IMPORTS = {
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "fitz": "PyMuPDF",
    "flask": "Flask",
    "markdown": "Markdown",
    "openai": "openai",
    "PIL": "Pillow",
    "pypdf": "pypdf",
    "reportlab": "reportlab",
    "requests": "requests",
    "svglib": "svglib",
    "tavily": "tavily-python",
    "xhtml2pdf": "xhtml2pdf",
    "youtube_transcript_api": "youtube-transcript-api",
    "pytest": "requirements-dev.txt",
}


def fail(message: str) -> int:
    print(f"\nFAIL: {message}")
    return 1


def check_dependencies() -> list[str]:
    missing: list[str] = []
    for module, package in IMPORTS.items():
        try:
            importlib.import_module(module)
        except Exception:
            missing.append(package)
    return missing


def run(command: list[str]) -> int:
    print("\n> " + " ".join(command))
    return subprocess.run(command, cwd=ROOT, env=os.environ.copy()).returncode


def main() -> int:
    print("=" * 72)
    print("DIGITAL PRODUCT FACTORY — ENFORCED RELEASE GATE")
    print("External network and paid API calls are blocked by tests/conftest.py")
    print("=" * 72)
    os.environ["FACTORY_TEST_MODE"] = "1"
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["TAVILY_API_KEY"] = ""
    os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""
    os.environ["PEXELS_API_KEY"] = ""

    missing = check_dependencies()
    if missing:
        return fail(
            "Missing dependencies: " + ", ".join(sorted(set(missing)))
            + ". Run: python -m pip install -r requirements-dev.txt"
        )

    print("\n[1/4] Compiling Python source")
    targets = [ROOT / "app.py", ROOT / "database.py", ROOT / "ai_client.py", ROOT / "services", ROOT / "routes"]
    for target in targets:
        if target.is_dir():
            if not compileall.compile_dir(str(target), quiet=1):
                return fail(f"Python compile failed under {target.relative_to(ROOT)}")
        elif not compileall.compile_file(str(target), quiet=1):
            return fail(f"Python compile failed: {target.name}")

    print("\n[2/4] Checking browser JavaScript syntax")
    node = shutil.which("node")
    if not node:
        return fail("Node.js is required for the JavaScript syntax gate.")
    if run([node, "--check", "static/js/app.js"]):
        return fail("static/js/app.js has a syntax error")

    print("\n[3/4] Validating acceptance manifest")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tests = data.get("tests") or []
    if not tests or len(tests) != len(set(tests)):
        return fail("Acceptance manifest is empty or contains duplicates")
    missing_tests = [item for item in tests if not (ROOT / item).is_file()]
    if missing_tests:
        return fail("Manifest names missing tests: " + ", ".join(missing_tests))

    print(f"\n[4/4] Running {len(tests)} acceptance files")
    RESULT_DIR.mkdir(exist_ok=True)
    command = [sys.executable, "-m", "pytest", "-q", "--junitxml", str(JUNIT), *tests]
    code = run(command)
    if code:
        return fail("One or more acceptance tests failed")

    root = ET.parse(JUNIT).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    totals = {
        key: sum(int(s.attrib.get(key, 0)) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    if totals["skipped"]:
        return fail(f"{totals['skipped']} acceptance test(s) were skipped")
    if totals["failures"] or totals["errors"]:
        return fail("JUnit report contains failures or errors")

    print("\nPASS: release gate completed")
    print(f"Tests: {totals['tests']}  Failures: 0  Errors: 0  Skipped: 0")
    print("Paid API calls permitted: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
