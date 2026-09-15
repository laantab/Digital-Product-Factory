"""Short entry point for the PostgreSQL cutover — Upgrade 0, Phase 0B-4.

Render's Web Shell mangles pasted multi-line input, so this is driveable
by a few typed words from the project root:

    python pgmig.py              status   (READ ONLY -- the default)
    python pgmig.py backup       verified SQLite backup on the disk
    python pgmig.py schema       create the PostgreSQL schema
    python pgmig.py migrate      guarded: backup -> schema -> import -> parity
    python pgmig.py parity       re-verify SQLite vs PostgreSQL
    python pgmig.py health       which backend the app is actually using

Nothing here deletes the SQLite database, and nothing prints a
credential.
"""
import json
import os
import sys

from services.db import cutover

if __name__ == "__main__":
    args = sys.argv[1:]
    action = (args[0] if args else "status").strip().lower()
    try:
        if action in ("status", ""):
            result = cutover.status()
        elif action == "backup":
            result = cutover.backup_sqlite()
        elif action == "schema":
            result = cutover.create_schema()
        elif action == "migrate":
            result = cutover.run_cutover_migration()
        elif action == "parity":
            result = cutover.parity()
        elif action == "health":
            result = cutover.health()
        else:
            print(f"unknown action: {action!r}")
            raise SystemExit(2)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                         indent=2, default=str))
        raise SystemExit(1)
    print(json.dumps(result, indent=2, default=str))
    raise SystemExit(0 if result.get("ok", True) else 1)
