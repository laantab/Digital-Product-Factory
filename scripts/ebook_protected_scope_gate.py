"""Fail ebook-only releases if protected generator files were changed.

Compare the PR head with the base commit; never edit working product code.
"""
import subprocess
import sys

PROTECTED_PARTS = (
    "coloring", "crossword", "word_search", "wordsearch",
    "faith_planner", "budget_planner", "faith-planner", "budget-planner",
)
PROTECTED_ROOTS = ("services/", "templates/", "static/", "routes/", "app/", "config/")


def changed_paths(base="origin/main"):
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        text=True, capture_output=True, check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def protected_changes(paths):
    return [path for path in paths if path.startswith(PROTECTED_ROOTS)
            and any(term in path.lower() for term in PROTECTED_PARTS)]


if __name__ == "__main__":
    violations = protected_changes(changed_paths(sys.argv[1] if len(sys.argv) > 1 else "origin/main"))
    if violations:
        print("BLOCKED: Ebook-only upgrade touches protected generator files:")
        for path in violations:
            print(f" - {path}")
        sys.exit(1)
    print("PASS: No protected generator-specific files changed.")
