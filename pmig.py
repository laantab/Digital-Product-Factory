"""Short entry point for the production embedded-PDF migration.

Render's Web Shell mangles pasted multi-line input, so this exists purely
so the migration can be driven by a few typed words from the project root:

    python pmig.py                 inventory  (READ ONLY -- the default)
    python pmig.py backup          timestamped verified copy of the database
    python pmig.py migrate 10      migrate up to 10 projects, bounded
    python pmig.py verify          re-verify every migrated asset
    python pmig.py verify 5        re-verify a random sample of 5

All the logic lives in services/storage/production_migration.py. This file
is a shim and nothing else; it is removed once the migration is complete.
"""
from services.storage.production_migration import main

if __name__ == "__main__":
    raise SystemExit(main())
