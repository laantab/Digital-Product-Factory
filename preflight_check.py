"""One enforced, zero-paid-call release gate for the whole Factory."""
from __future__ import annotations

import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    runner = os.path.join(ROOT, "scripts", "run_factory_tests.py")
    completed = subprocess.run([sys.executable, runner], cwd=ROOT)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
