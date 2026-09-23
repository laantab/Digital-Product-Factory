"""List books that were hidden only because of a word in their own title.

The old classifier stamped system_test=1 at creation on any record whose title
contained "test", "qa", "debug", "fixture", "placeholder", "regression" or
"handoff". Those are ordinary words in a real book title, so a customer's
finished book could vanish from their own Saved Projects. v1.9.1 stops that
happening to NEW records. Rows already stamped keep their flags, because a
sweep that guessed again could just as easily un-hide a genuine internal
record.

This script only looks. It changes nothing unless you name one project id and
pass --unhide, and it refuses any row that still has a real reason to be hidden.

    python scripts/review_hidden_books.py                  # list candidates
    python scripts/review_hidden_books.py --unhide 370     # restore one row
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database  # noqa: E402


def candidates() -> list[dict]:
    """Rows hidden today whose only evidence is a word in the customer's title."""
    conn = database.get_conn()
    rows = conn.execute(
        f"SELECT {','.join(database._TABLE_COLS)} FROM projects "
        "WHERE system_test = 1 OR temporary = 1 OR user_saved = 0"
    ).fetchall()
    conn.close()
    out: list[dict] = []
    for row in rows:
        name = row["name"] or ""
        try:
            data = json.loads(row["data"] or "{}")
        except (TypeError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        verdict = database.classify_customer_visibility(name, row["type"], data, project_id=int(row["id"]))
        # Under today's rules this record would NOT be hidden, and the old rule
        # that hid it was a word in the title.
        if verdict.get("hide"):
            continue
        if not verdict.get("needs_decision"):
            continue
        out.append({
            "id": int(row["id"]),
            "name": name,
            "type": row["type"],
            "user_saved": int(row["user_saved"] or 0),
            "system_test": int(row["system_test"] or 0),
            "temporary": int(row["temporary"] or 0),
            "reason_recorded_now": verdict["needs_decision"],
        })
    return out


def unhide(project_id: int) -> int:
    row = database.get_project(project_id)
    if not row:
        print(f"No project {project_id}.")
        return 1
    name = row.get("name") or ""
    data = row.get("data")
    if not isinstance(data, dict):
        try:
            data = json.loads(data or "{}")
        except (TypeError, ValueError):
            data = {}
    verdict = database.classify_customer_visibility(name, row.get("type"), data, project_id=project_id)
    if verdict.get("hide"):
        print(f"Refusing: project {project_id} still classifies as hidden today ({verdict}).")
        return 2
    # The row carries its own hidden markers inside the data blob as well as in
    # the columns; the customer list reads both, so both have to be cleared.
    payload = database._stamp_visible_metadata(data)
    conn = database.get_conn()
    conn.execute(
        "UPDATE projects SET user_saved = 1, system_test = 0, temporary = 0, "
        "data = ?, updated_at = ? WHERE id = ?",
        (json.dumps(payload), database._now(), project_id),
    )
    conn.commit()
    conn.close()
    print(f"Project {project_id} ({name!r}) is visible in Saved Projects again.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unhide", type=int, default=None,
                        help="restore ONE project id to the customer's Saved Projects")
    args = parser.parse_args()

    print(f"Database: {database.DB_PATH}")
    if args.unhide is not None:
        return unhide(args.unhide)

    rows = candidates()
    if not rows:
        print("\nNo book is hidden only because of a word in its own title. Nothing to do.")
        return 0
    print(f"\n{len(rows)} record(s) hidden only because of a word in the title:\n")
    for row in rows:
        print(f"  id {row['id']:>6}  {row['name']}")
        print(f"          flags: user_saved={row['user_saved']} "
              f"system_test={row['system_test']} temporary={row['temporary']}")
    print("\nThese are CANDIDATES, not a verdict. Look at each one, then restore")
    print("the ones that are real customer books, one at a time:")
    print("    python scripts/review_hidden_books.py --unhide <id>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
