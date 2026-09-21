"""Create an admin login for the Factory (Phase A, Factory 1.8.5).

    python scripts/create_admin.py you@example.com

The password is typed privately (getpass: not shown, not in history), hashed
with bcrypt at once, and never printed, logged or written anywhere. If the
email already exists nothing is changed.
"""
from __future__ import annotations

import getpass
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import database  # noqa: E402
from routes.auth import _hash_password  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/create_admin.py <email>")
    email = sys.argv[1].strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise SystemExit("That is not a valid email address.")
    database.init_db()
    existing = database.get_user_by_email(email)
    if existing:
        raise SystemExit(f"An account for {email} already exists (id {existing['id']}). Nothing changed.")
    while True:
        first = getpass.getpass("Password (at least 8 characters, not shown): ")
        if len(first) < 8:
            print("Too short, try again.")
            continue
        if getpass.getpass("Type it again: ") != first:
            print("They did not match, try again.")
            continue
        break
    user = database.create_user(email, _hash_password(first), role="admin")
    first = None  # noqa: F841 -- drop the plaintext
    print(f"Created admin account {user['email']} (id {user['id']}).")


if __name__ == "__main__":
    main()
