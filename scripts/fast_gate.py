"""The Fast Stability Gate, derived from the function-lock registry.

The gate used to be a list of file names typed into CLAUDE.md and a .bat. Every
LOCKED and PROTECTED function in the registry carries fast_gate: true, but 17 of
their protected test files were not in that list -- so a change could pass the
gate and still have broken a guarantee the registry says the gate protects.

The list is now computed: the core customer-path files below, plus every
protected_test_file of every function whose registry entry says fast_gate.
Nothing can drop out by being forgotten, and tests/test_the_fast_gate_covers_
what_it_claims.py fails if a protected file is neither included nor listed in
EXCLUDED with a reason.

    python scripts/fast_gate.py            # run it
    python scripts/fast_gate.py --list     # print the files, run nothing
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "command_center" / "function_lock_registry.json"

#: Customer-path files that belong in the gate whether or not a lock claims them.
CORE = (
    "tests/factory_golden_customer_path_smoke_suite.py",
    "tests/test_universal_topic_puzzle_engine.py",
    "tests/test_crossword_scope_answerkey_zip_repair.py",
    "tests/test_coloring_book_sea_creatures_customer_path.py",
    "tests/test_coloring_book_local_fallback_theme_classification.py",
    "tests/test_spelling_worksheet_topic_relevance.py",
    "tests/test_spelling_worksheet_release_readiness.py",
    "tests/test_spelling_worksheet_semantic_scope.py",
    "tests/test_african_animals_topic_repair.py",
    "tests/test_invite_gate.py",
    "tests/test_the_invite_gate_fails_closed.py",
    "tests/test_admin_routes_require_an_admin.py",
    "tests/test_paid_image_authorization_is_per_thread.py",
    "tests/test_a_customers_title_does_not_hide_their_book.py",
    "tests/test_render_persistence_patch.py",
    "tests/test_customer_journey_every_product_type.py",
    "tests/test_ebook_saved_projects_visibility.py",
    "tests/test_saved_projects_reopen_build.py",
    "tests/test_reopen_packaging_identity_pass2.py",
    "tests/test_download_slug_package_id.py",
    "tests/test_word_search_topic_scope_contract.py",
    "tests/test_coloring_book_interior_no_text_contract.py",
    "tests/test_function_lock_registry_integrity.py",
    "tests/test_function_lock_enforcement.py",
    "tests/test_storage_foundation.py",
    "tests/test_storage_r2_cutover.py",
    "tests/test_v190_six_template_studio.py",
    "tests/test_v190_templates_render_differently.py",
)

#: Protected files deliberately kept OUT of the fast gate, each with a reason
#: a reader can check. The gate is meant to be seconds and offline; anything
#: here still runs in the full release gate.
EXCLUDED = {
    "tests/test_ebook_real_browser_customer_path.py":
        "drives a real browser: needs a Playwright Chromium download, which is "
        "not available on every machine and is not a seconds-long check. Runs in "
        "the full release gate.",
}


def registry_files() -> list[str]:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    out: list[str] = []
    for entry in (data.get("functions") or {}).values():
        if not entry.get("fast_gate"):
            continue
        for path in entry.get("protected_test_files") or []:
            out.append(str(path).replace("\\", "/"))
    return out


def gate_files() -> list[str]:
    seen: dict[str, None] = {}
    for path in list(CORE) + registry_files():
        path = path.replace("\\", "/")
        if path in EXCLUDED:
            continue
        if not (ROOT / path).is_file():
            continue
        seen.setdefault(path, None)
    return sorted(seen)


def main() -> int:
    files = gate_files()
    if "--list" in sys.argv[1:]:
        print("\n".join(files))
        return 0
    print(f"Fast Stability Gate: {len(files)} files")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *files],
        cwd=str(ROOT),
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
