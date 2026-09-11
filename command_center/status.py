"""Read-only status gathering for the Command Center.

Every function here either returns data or fails safe to a clearly-labeled
"not available" value. Nothing in this module raises on missing or
malformed optional data, and nothing here writes to ``projects.db``, calls
an AI/API client, or imports ``services.product`` or anything that could
generate a product. The one write path the Command Center has at all is
``save_handoff`` below, and it only ever writes
``command_center/handoff_status.json``.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# command_center/ lives one level below the Factory-v1.3 checkout root.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

HANDOFF_FILE = HERE / "handoff_status.json"
COMPONENT_VERSIONS_FILE = HERE / "component_versions.json"
GATE_JUNIT_FILE = ROOT / "test-results" / "factory-junit.xml"

#: The name CLAUDE.md says this checkout must have, and the branch every
#: launcher and gate expects. Used only to label the source-of-truth panel
#: as trusted or not — it never blocks the page from rendering.
EXPECTED_FOLDER_NAME = "Factory-v1.3"
EXPECTED_BRANCH = "main"


def _load_json_safe(path: Path, default: Any) -> Any:
    """Read a JSON file. Missing, empty, or malformed -> `default`, never raises."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default
    except OSError as exc:
        log.warning("Command Center: could not read %s: %s", path, exc)
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        log.warning("Command Center: %s is not valid JSON: %s", path, exc)
        return default


def _run_git(*args: str) -> str | None:
    """Run a read-only git command in ROOT. None on any failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Command Center: git %s failed: %s", args, exc)
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def get_git_info() -> dict[str, Any]:
    """Branch, commit, and whether this checkout matches what CLAUDE.md expects."""
    branch = _run_git("rev-parse", "--abbrev-ref", "HEAD")
    commit = _run_git("rev-parse", "HEAD")
    commit_short = _run_git("rev-parse", "--short", "HEAD")
    commit_summary = _run_git("log", "-1", "--format=%ad %s", "--date=short")
    dirty = _run_git("status", "--porcelain")
    return {
        "path": str(ROOT),
        "folder_name": ROOT.name,
        "is_expected_folder": ROOT.name == EXPECTED_FOLDER_NAME,
        "branch": branch,
        "is_expected_branch": branch == EXPECTED_BRANCH,
        "commit": commit,
        "commit_short": commit_short or "unknown",
        "commit_summary": commit_summary,
        "working_tree_clean": dirty == "" if dirty is not None else None,
    }


def get_factory_version() -> str:
    """The Factory's own semantic version, via the one module that reads VERSION."""
    try:
        from services.factory_version import get_version
    except ImportError as exc:
        log.warning("Command Center: could not read Factory version: %s", exc)
        return "unknown"
    return get_version()


def load_component_versions() -> dict[str, Any]:
    """The durable component-version manifest (word search / crossword / resolver / …)."""
    data = _load_json_safe(COMPONENT_VERSIONS_FILE, {})
    return data if isinstance(data, dict) else {}


def load_gate_result() -> dict[str, Any] | None:
    """Summarize the most recent full-gate JUnit report already on disk, if any.

    This reads ``test-results/factory-junit.xml``, the file the Windows release
    gate (``scripts/run_factory_tests.py``) already produces — no test is run to
    populate this. Returns None (never raises) if the file is missing or unreadable.
    """
    if not GATE_JUNIT_FILE.exists():
        return None
    try:
        root = ET.parse(GATE_JUNIT_FILE).getroot()
    except ET.ParseError as exc:
        log.warning("Command Center: could not parse %s: %s", GATE_JUNIT_FILE, exc)
        return None
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    if suite is None:
        return None
    attrib = suite.attrib
    try:
        tests = int(attrib.get("tests", 0))
        failures = int(attrib.get("failures", 0))
        errors = int(attrib.get("errors", 0))
        skipped = int(attrib.get("skipped", 0))
    except ValueError:
        return None
    return {
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "passed": failures == 0 and errors == 0,
        "timestamp": attrib.get("timestamp"),
    }


def list_recent_handoffs(limit: int = 6) -> list[dict[str, str]]:
    """Filenames of the SESSION_HANDOFF_*.md files, newest first, for the details view."""
    try:
        files = sorted(ROOT.glob("SESSION_HANDOFF_*.md"), reverse=True)
    except OSError:
        return []
    out = []
    for f in files[:limit]:
        match = re.search(r"SESSION_HANDOFF_(\d{4}-\d{2}-\d{2})\.md$", f.name)
        out.append({"date": match.group(1) if match else f.name, "filename": f.name})
    return out


def default_handoff() -> dict[str, Any]:
    """What a Command Center with no saved handoff yet should show."""
    return {
        "updated_at": None,
        "current_task": "Not set yet — use \"Update handoff\" below, or edit "
        "command_center/handoff_status.json.",
        "stopped_at": "No handoff has been saved yet.",
        "next_step": "Open the newest SESSION_HANDOFF_*.md in the Factory root "
        "and save its next step here.",
        "next_claude": "code",
        "open_issues": [],
        "completed_log": [],
        "notes": "",
    }


def load_handoff() -> dict[str, Any]:
    """The one canonical current handoff record. Missing fields fall back safely."""
    data = _load_json_safe(HANDOFF_FILE, None)
    defaults = default_handoff()
    if not isinstance(data, dict):
        return defaults
    merged = {**defaults, **data}
    if not isinstance(merged.get("open_issues"), list):
        merged["open_issues"] = []
    if not isinstance(merged.get("completed_log"), list):
        merged["completed_log"] = []
    return merged


def save_handoff(data: dict[str, Any]) -> None:
    """Write the canonical handoff record atomically. The only write this app does."""
    data = {**default_handoff(), **data}
    data["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    tmp = HANDOFF_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(HANDOFF_FILE)


def bucket_completed_log(completed_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group the completed-work log into Today / Yesterday / Earlier, newest first."""
    today = date.today()
    buckets: list[dict[str, Any]] = []
    for entry in sorted(completed_log, key=lambda e: e.get("date", ""), reverse=True):
        raw_date = entry.get("date", "")
        try:
            entry_date = date.fromisoformat(raw_date)
        except ValueError:
            label = raw_date or "Undated"
        else:
            delta = (today - entry_date).days
            if delta == 0:
                label = "Today"
            elif delta == 1:
                label = "Yesterday"
            else:
                label = "Earlier"
        items = entry.get("items", [])
        if not isinstance(items, list):
            items = [str(items)]
        # NOTE: the key is "entries", not "items" -- Jinja2 resolves `foo.items`
        # to the dict method `dict.items` (attribute access wins over `__getitem__`
        # for a name every dict already has), so a literal "items" key here would
        # silently make `bucket.items` an unbound method instead of the list.
        buckets.append({"label": label, "date": raw_date, "entries": items})
    return buckets


def build_context() -> dict[str, Any]:
    """Everything the template needs, each piece failing independently and safely."""
    try:
        git_info = get_git_info()
    except Exception as exc:  # noqa: BLE001 - never let a status page crash itself
        log.warning("Command Center: git info failed: %s", exc)
        git_info = {"path": str(ROOT), "folder_name": ROOT.name, "is_expected_folder": False,
                    "branch": None, "is_expected_branch": False, "commit": None,
                    "commit_short": "unknown", "commit_summary": None, "working_tree_clean": None}
    try:
        factory_version = get_factory_version()
    except Exception as exc:  # noqa: BLE001
        log.warning("Command Center: factory version failed: %s", exc)
        factory_version = "unknown"
    try:
        components = load_component_versions()
    except Exception as exc:  # noqa: BLE001
        log.warning("Command Center: component versions failed: %s", exc)
        components = {}
    try:
        gate = load_gate_result()
    except Exception as exc:  # noqa: BLE001
        log.warning("Command Center: gate result failed: %s", exc)
        gate = None
    try:
        handoff = load_handoff()
    except Exception as exc:  # noqa: BLE001
        log.warning("Command Center: handoff load failed: %s", exc)
        handoff = default_handoff()
    try:
        recent_handoffs = list_recent_handoffs()
    except Exception as exc:  # noqa: BLE001
        log.warning("Command Center: recent handoffs failed: %s", exc)
        recent_handoffs = []

    completed_buckets = bucket_completed_log(handoff.get("completed_log", []))
    latest_completed = completed_buckets[0] if completed_buckets else None

    return {
        "git": git_info,
        "factory_version": factory_version,
        "components": components.get("components", {}),
        "component_manifest_note": components.get("note"),
        "gate": gate,
        "handoff": handoff,
        "completed_buckets": completed_buckets,
        "latest_completed": latest_completed,
        "recent_handoffs": recent_handoffs,
        "root": str(ROOT),
        "expected_folder_name": EXPECTED_FOLDER_NAME,
        "expected_branch": EXPECTED_BRANCH,
    }
