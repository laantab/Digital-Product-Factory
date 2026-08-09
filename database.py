"""SQLite persistence for Product Projects."""
import json
import os
import re
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "projects.db")

# Keywords that indicate a test/debug/system project — triggers automatic
# system_test=True flag unless the request explicitly passes user_confirmed_save.
_TEST_PATTERNS = re.compile(
    r"(?i)"
    r"\b("
    r"test|workflow\.?test|pipeline\.?test|validation|regression|smoke|"
    r"qa\.?test|debug|unit\.?test|integration\.?test|bench"
    r"|download\.?proof|next\.?steps|nest\.?steps|math\.?final|handoff"
    r"|verification\.?test|\[test\]|test/|test-"
    r")\b"
)

# Columns on the projects table (must match CREATE TABLE + ALTER TABLE below).
_TABLE_COLS = (
    "id", "name", "type", "data",
    "user_saved", "system_test", "temporary",
    "created_at", "updated_at",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            data TEXT NOT NULL DEFAULT '{}',
            user_saved INTEGER NOT NULL DEFAULT 1,
            system_test INTEGER NOT NULL DEFAULT 0,
            temporary INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # Backward-compat: add new columns to existing DBs that were created before
    # these columns existed. Each ALTER is idempotent (IF NOT EXISTS skips if ok).
    for col, default in [
        ("user_saved", "1"),
        ("system_test", "0"),
        ("temporary", "0"),
    ]:
        try:
            conn.execute(
                f"ALTER TABLE projects ADD COLUMN {col} INTEGER NOT NULL DEFAULT {default}"
            )
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "data": json.loads(row["data"] or "{}"),
        "user_saved": bool(row["user_saved"]),
        "system_test": bool(row["system_test"]),
        "temporary": bool(row["temporary"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _col(col: str) -> str:
    """Return column expression — handles missing columns for old DBs gracefully."""
    return col if col in _TABLE_COLS else "0"


def list_projects(
    include_system: bool = False,
) -> list[dict]:
    """List projects. By default hides system/test/temporary projects.
    Also applies a name-based safety filter even when flags are set incorrectly
    (belt-and-suspenders for old records that predate the flag system)."""
    conn = get_conn()
    if include_system:
        rows = conn.execute(
            f"SELECT {','.join(_TABLE_COLS)} FROM projects ORDER BY updated_at DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT {','.join(_TABLE_COLS)} FROM projects "
            "WHERE user_saved = 1 AND system_test = 0 AND temporary = 0 "
            "ORDER BY updated_at DESC"
        ).fetchall()
        # Name-based safety net: also hide records that match test patterns
        # even if their flags say user_saved=1 (old records pre-dating the guard).
        rows = [r for r in rows if not is_test_name(r["name"])]
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_project(project_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        f"SELECT {','.join(_TABLE_COLS)} FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def create_project(
    name: str,
    type_: str,
    data: dict,
    user_saved: bool | None = None,
    system_test: bool | None = None,
    temporary: bool | None = None,
) -> dict:
    """Create a new project record.

    Flags:
        user_saved  — user explicitly chose to save (show in normal list).
                      None = apply backend safety guard + default to True.
        system_test — system/test/debug project (hidden by default).
                      None = apply backend safety guard + default to False.
        temporary   — session/temporary record (hidden by default).
                      None = apply backend safety guard + default to False.
    """
    # Apply safety guard: detects test names and resolves None defaults.
    # Explicit True/False values always win (except test-name guard can still
    # override when explicit save=False was not intentionally set).
    resolved_user, resolved_sys, resolved_temp = apply_save_flags(
        name=name,
        explicit_user_save=user_saved,
        system_test=system_test,
        temporary=temporary,
    )

    now = _now()
    conn = get_conn()
    cur = conn.execute(
        f"INSERT INTO projects (name, type, data, user_saved, system_test, temporary, created_at, updated_at) "
        f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            name,
            type_,
            json.dumps(data),
            int(resolved_user),
            int(resolved_sys),
            int(resolved_temp),
            now,
            now,
        ),
    )
    conn.commit()
    project_id = cur.lastrowid
    conn.close()
    return get_project(project_id)


def update_project(
    project_id: int,
    name: str | None,
    data: dict | None,
    type_: str | None = None,
    user_saved: bool | None = None,
    system_test: bool | None = None,
    temporary: bool | None = None,
) -> dict | None:
    """Update an existing project. Only non-None values are changed; flags
    are only updated when explicitly passed (None = keep existing)."""
    existing = get_project(project_id)
    if not existing:
        return None

    new_name = name if name is not None else existing["name"]
    new_data = data if data is not None else existing["data"]
    new_type = type_ if type_ is not None else existing["type"]
    # Flags: only override if explicitly passed (allows safe partial updates)
    new_user_saved = (
        user_saved if user_saved is not None else existing["user_saved"]
    )
    new_system_test = (
        system_test if system_test is not None else existing["system_test"]
    )
    new_temporary = (
        temporary if temporary is not None else existing["temporary"]
    )

    conn = get_conn()
    conn.execute(
        f"UPDATE projects SET name=?, type=?, data=?, "
        f"user_saved=?, system_test=?, temporary=?, updated_at=? "
        f"WHERE id=?",
        (
            new_name,
            new_type,
            json.dumps(new_data),
            int(new_user_saved),
            int(new_system_test),
            int(new_temporary),
            _now(),
            project_id,
        ),
    )
    conn.commit()
    conn.close()
    return get_project(project_id)


def delete_project(project_id: int) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ---------------------------------------------------------------------------
# Safety helpers
# ---------------------------------------------------------------------------

def is_test_name(name: str) -> bool:
    """Return True if `name` matches test/debug/system patterns."""
    return bool(_TEST_PATTERNS.search(name))


def apply_save_flags(
    name: str,
    explicit_user_save: bool | None,
    system_test: bool | None,
    temporary: bool | None,
) -> tuple[bool, bool, bool]:
    """Resolve final save flags for a create/update call.

    Logic:
      - If the name matches a test pattern and no explicit user_save
        choice was made → auto-flag as system_test + temporary, hide from
        normal list.
      - If the name matches a test pattern AND user explicitly opted in with
        user_saved=True → respect the opt-in (treat as intentional save).
      - Explicit flags (True or False) always override default behavior.
    """
    is_test = is_test_name(name)

    if is_test:
        # Backend safety guard: test patterns → hide by default.
        # Only override if the request explicitly chose user_saved=True.
        if explicit_user_save is True:
            # Explicit opt-in → treat as intentional save
            return True, bool(system_test or False), bool(temporary or False)
        else:
            # No explicit save opt-in → auto-flag as system/temp
            return False, True, True

    # Not a test name → use explicit flags or defaults
    user_saved = explicit_user_save if explicit_user_save is not None else True
    sys_test = bool(system_test) if system_test is not None else False
    temp = bool(temporary) if temporary is not None else False
    return bool(user_saved), sys_test, temp
