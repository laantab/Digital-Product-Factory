"""The one place the Factory learns its own version number.

WHY THIS EXISTS
---------------
The version lived as a string literal inside app.py. A literal in one file is
a version that goes stale the moment someone forgets it, and there is no way
for a script, a test or a release check to agree with it. So the number now
lives in a plain-text VERSION file at the repository root, and everything that
displays or records a version reads it through this module.

FAIL SAFE, NOT LOUD
-------------------
If the VERSION file is missing or malformed, customers must not see a
traceback, a filesystem path, or a scary "unknown". They see a neutral
placeholder; the real reason goes to the private application log.

The format is Semantic Versioning: MAJOR.MINOR.PATCH, digits only, nothing
else in the file.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

#: Repository root: this file lives in <root>/services/.
ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"

#: MAJOR.MINOR.PATCH and nothing else. No "v", no suffix, no build metadata.
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

#: Shown when the version genuinely cannot be read. Never a path or an error.
FALLBACK_VERSION = "0.0.0"


class InvalidVersion(ValueError):
    """The VERSION file exists but does not hold a bare semantic version."""


def parse_version(raw: str) -> tuple[int, int, int]:
    """Turn '1.4.0' into (1, 4, 0). Raises InvalidVersion for anything else."""
    text = str(raw or "").strip()
    match = SEMVER_RE.match(text)
    if not match:
        raise InvalidVersion(
            f"expected MAJOR.MINOR.PATCH with digits only, got {text!r}"
        )
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def read_version_file(path: Path | str | None = None) -> str:
    """The version as written on disk. Raises if missing or malformed.

    Use this in scripts and tests, where a clear failure is what you want.
    Application code should use ``get_version()``.
    """
    target = Path(path) if path else VERSION_FILE
    text = target.read_text(encoding="utf-8")
    # A stray blank line is fine; anything else is not.
    stripped = text.strip()
    if stripped != text.rstrip("\r\n") and stripped != text:
        raise InvalidVersion("VERSION must contain only the version number")
    if "\n" in stripped or "\r" in stripped:
        raise InvalidVersion("VERSION must contain a single line")
    parse_version(stripped)
    return stripped


def get_version() -> str:
    """The version for display and logging. Never raises, never leaks a path."""
    try:
        return read_version_file()
    except FileNotFoundError:
        log.error("VERSION file is missing at %s", VERSION_FILE)
    except InvalidVersion as exc:
        log.error("VERSION file is not a valid semantic version: %s", exc)
    except OSError as exc:
        log.error("VERSION file could not be read: %s", exc)
    return FALLBACK_VERSION


def version_tuple() -> tuple[int, int, int]:
    """The version as numbers, for comparisons. Never raises."""
    try:
        return parse_version(get_version())
    except InvalidVersion:
        return (0, 0, 0)


def is_newer(candidate: str, previous: str) -> bool:
    """True when ``candidate`` is a strictly higher version than ``previous``."""
    return parse_version(candidate) > parse_version(previous)
