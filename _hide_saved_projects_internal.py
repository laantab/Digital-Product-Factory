"""One-time hide of internal/test Saved Projects. Does not delete records."""
from __future__ import annotations

import hashlib
import json

import database


def snap(pid: int) -> dict | None:
    project = database.get_project(pid)
    if not project:
        return None
    data = project.get("data") or {}
    raw = json.dumps(data, sort_keys=True, default=str)
    return {
        "id": project["id"],
        "name": project["name"],
        "user_saved": project["user_saved"],
        "system_test": project["system_test"],
        "temporary": project["temporary"],
        "data_sha": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }


def main() -> None:
    before_4249 = snap(4249)
    before_14626 = snap(14626)
    print("BEFORE 4249", before_4249)
    print("BEFORE 14626", before_14626)

    report = database.hide_internal_records_from_customers()
    print("HIDDEN_COUNT", report["hidden_count"])
    print("TEST_DEBUG_HIDDEN", report["test_debug_hidden"])
    print("INTERNAL_HIDDEN", report["internal_hidden"])
    print("NEEDS_DECISION", len(report["needs_decision"]))
    for item in report["needs_decision"][:50]:
        print("  NEED", item)
    print("SKIPPED_PROTECTED", report["skipped_protected"])

    after_4249 = snap(4249)
    after_14626 = snap(14626)
    print("AFTER 4249", after_4249)
    print("AFTER 14626", after_14626)
    print("4249_UNCHANGED", before_4249 == after_4249)
    print("14626_UNCHANGED", before_14626 == after_14626)
    if before_4249 != after_4249:
        raise SystemExit("REFUSING TO CONTINUE: project 4249 changed")
    if before_14626 != after_14626:
        raise SystemExit("REFUSING TO CONTINUE: project 14626 changed")

    visible = database.list_projects(include_system=False)
    names = [p["name"] for p in visible]
    print("CUSTOMER_VISIBLE_COUNT", len(visible))
    for needle in (
        "Guided Cover Isolated",
        "Seed Self Refuse",
        "Research: view only",
        "PIPELINE TEST",
        "DEBUG",
    ):
        hits = [n for n in names if needle.lower() in n.lower()]
        print("VISIBLE_HITS", needle, len(hits), hits[:5])
    print("4249_IN_LIST", any(p["id"] == 4249 for p in visible))
    print("14626_IN_LIST", any(p["id"] == 14626 for p in visible))
    print("SAMPLE_VISIBLE")
    for project in visible[:25]:
        print(f"  {project['id']} {project['type']} {project['name'][:90]}")


if __name__ == "__main__":
    main()
