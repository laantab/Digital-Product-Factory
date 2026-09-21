"""Phase A migration: users table + project ownership (Factory 1.8.5).

Safe to run any number of times.

    python scripts/migrate_phase_a.py                      # report only
    python scripts/migrate_phase_a.py --owner-email you@x  # give UNOWNED projects to that user

What it does:
  1. Creates the users table and the projects.user_id column if missing
     (database.init_db -- additive; no existing row changes).
  2. Reports project and ownership counts.
  3. Only with --owner-email: assigns every project that has NO owner to that
     EXISTING user. A project that already has an owner is never touched, so
     a second run changes nothing.

It never creates a user and never sets a password. Create the admin account
with scripts/create_admin.py (password typed privately, never stored in
plain text). Unlike the original Phase A script, there is no placeholder
account with a default password.

Back up the database first (the Factory's database is projects.db locally;
production runs on PostgreSQL and is migrated by the app's own init_db at
start-up -- this script does not backfill production unless it is run there
deliberately).
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import database  # noqa: E402


def run(owner_email: str | None = None) -> dict:
    database.init_db()
    before = database.ownership_counts()
    result = {"before": before, "assigned": 0, "owner_id": None,
              "users": database.count_users()}
    if owner_email:
        owner = database.get_user_by_email(owner_email)
        if owner is None:
            raise SystemExit(f"No user with email {owner_email!r}. Nothing changed.")
        if not owner["active"]:
            raise SystemExit("That user is not active. Nothing changed.")
        result["owner_id"] = owner["id"]
        result["assigned"] = database.backfill_project_owners(owner["id"])
    result["after"] = database.ownership_counts()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--owner-email", default=None,
                        help="give every UNOWNED project to this existing user")
    args = parser.parse_args()
    r = run(args.owner_email)
    print("=== Phase A migration ===")
    print(f"users: {r['users']}")
    print(f"before: {r['before']}")
    if args.owner_email:
        print(f"assigned to user {r['owner_id']}: {r['assigned']}")
    print(f"after:  {r['after']}")


if __name__ == "__main__":
    main()
