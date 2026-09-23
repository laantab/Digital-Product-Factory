"""SQLite persistence for Product Projects."""
import json
import logging
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH = os.environ.get("FACTORY_DB_PATH") or os.path.join(os.path.dirname(__file__), "projects.db")

# Real customer products that must stay visible even if a broad token matches.
_PROTECTED_PROJECT_IDS = frozenset({4249, 14626})
# Explicit customer Saved Projects restore allowlist. Does not loosen the
# global completed-output filter for other needs_correction / DRAFT rows.
CUSTOMER_KEEP_PROJECT_IDS = frozenset({4249, 14626})
_PROTECTED_TITLE_NEEDLES = (
    "flexible focus weekly kit",
    "ai at work made simple",
    "the no-screen bedtime audio pack",
    "the 4-week budget meal plan",
    "etsy digital shop starter toolkit",
    "remote job resume & cover letter kit",
    "local service social media content kit",
    "reclaim the night",
    "fit after 50",
    "taming your pup",
    "unbreakable super hero",
    "farm animals",
    "wining ai prompts",
    "ai for beginners",
    "how to keep your teen safe online",
    "from first booking to on-site prints",
)

# High-confidence phrases — hide without relying on broad single tokens.
_STRONG_TEST_PHRASES = (
    "guided cover isolated",
    "cover isolated",
    "photo cover isolated",
    "isolated cover",
    "workflow test",
    "pipeline test",
    "smoke test",
    "download proof",
    "final download proof",
    "verification test",
    "next-steps",
    "next steps",
    "qa test",
    "unit test",
    "integration test",
    "math final",
    "nest steps",
    "product smoke",
    "coloring smoke",
    "math smoke",
    "disposable math",
    "manuscript gate",
    "title outline persist",
    "research persist ebook",
    "no cover preview",
)
_STRONG_INTERNAL_PHRASES = (
    "seed self refuse",
    "final acceptance seed",
    "acceptance seed target",
    "seed target",
    "research: view only",
    "view only",
    "view-only",
    "read-only",
    "readonly",
    "auto-generated",
    "sample data",
    "demo record",
)

# Word-boundary tokens that are safe enough for titles (Contest != test).
_TEST_WORD_RE = re.compile(
    r"(?i)(?<![a-z])(test|debug|regression|fixture|handoff)(?![a-z])"
)
_QA_WORD_RE = re.compile(r"(?i)(?<![a-z])qa(?![a-z])")
_SMOKE_TEST_RE = re.compile(r"(?i)(?<![a-z])smoke(?![a-z])")
_ISOLATED_COVER_RE = re.compile(
    r"(?i)((guided\s+)?cover\s+isolated|isolated\s+cover)"
)
_SEED_INTERNAL_RE = re.compile(
    r"(?i)\bseed\s+(self|refuse|record|test|system)\b"
)
_SYSTEM_INTERNAL_RE = re.compile(
    r"(?i)\bsystem[\s_-]+(test|debug|internal|record)\b"
)
_INTERNAL_RECORD_RE = re.compile(
    r"(?i)\binternal[\s_-]+(record|test|system|debug)\b"
)
_PIPELINE_TEST_RE = re.compile(
    r"(?i)\b(pipeline\s+test|test\s+pipeline|workflow\s+pipeline)\b"
)
_VALIDATION_TEST_RE = re.compile(
    r"(?i)(\bvalidation\s+(test|record|proof|qa)\b|^\s*validation\s*$)"
)
_TEMPORARY_RECORD_RE = re.compile(
    r"(?i)\btemporary\s+(auto|record|save|project)\b"
)
_PLACEHOLDER_RE = re.compile(r"(?i)\bplaceholder\b")
_BROAD_DECISION_RE = re.compile(
    r"(?i)(?<![a-z])(system|internal|isolated|seed|pipeline|validation|temporary)(?![a-z])"
)

# Columns on the projects table (must match CREATE TABLE + ALTER TABLE below).
_TABLE_COLS = (
    "id", "name", "type", "data",
    "user_saved", "system_test", "temporary",
    "created_at", "updated_at", "version",
)

#: Key under which a read stamps the row's version into the returned `data`
#: dict. In-memory bookkeeping only -- never persisted into the stored blob.
ROW_VERSION_KEY = "_row_version"


class StaleProjectWrite(RuntimeError):
    """A write was rejected because the row changed after it was read.

    The whole of a project's state lives in one JSON blob, so a write
    replaces everything. A caller holding a copy read before someone
    else's write would erase that write -- the mechanism behind the
    v1.7.9 production data loss. Rejecting is the safe outcome.

    Deliberately NOT retried inside this module: a blind retry would
    re-apply the same stale blob and reintroduce the lost update. The
    caller must re-read, re-apply its change, and save again.
    """

    def __init__(self, project_id: int, expected: int, actual: int | None = None):
        self.project_id = int(project_id)
        self.expected_version = int(expected)
        self.actual_version = actual
        super().__init__(
            f"Project {project_id} changed since it was read "
            f"(expected version {expected}, found {actual}). "
            "Re-read the project, re-apply the change, and save again."
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _use_postgres() -> bool:
    """True only when explicitly switched to PostgreSQL (Upgrade 0, 0B-4).

    Requires BOTH FACTORY_DB_BACKEND=postgres AND a DATABASE_URL. Either
    alone leaves the Factory on SQLite exactly as before -- which is what
    lets the database be created, migrated and verified while production
    carries on serving customers from SQLite.
    """
    try:
        from services.db.connection import use_postgres

        return use_postgres()
    except Exception:
        return False


def get_conn():
    if _use_postgres():
        from services.db.connection import connect as _pg_connect

        return _pg_connect()

    # A freshly mounted persistent disk (e.g. Render's /var/data) is empty, and
    # sqlite3 will not create missing parent directories for us. Make the DB's
    # directory first so the very first boot on a new volume succeeds instead
    # of raising "unable to open database file". No-op when it already exists.
    _db_dir = os.path.dirname(DB_PATH)
    if _db_dir:
        os.makedirs(_db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    if _use_postgres():
        # The same logical schema, in PostgreSQL's spelling. Idempotent.
        from services.db.connection import init_postgres_schema

        init_postgres_schema(conn)
        conn.close()
        return
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
            updated_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    # Backward-compat: add new columns to existing DBs that were created before
    # these columns existed. Each ALTER is idempotent (IF NOT EXISTS skips if ok).
    for col, default in [
        ("user_saved", "1"),
        ("system_test", "0"),
        ("temporary", "0"),
        # Optimistic-concurrency counter (Upgrade 0, Phase 0B-2). Existing
        # rows start at 0; every write increments it. Additive and
        # backward-compatible: an older database simply gains the column.
        ("version", "0"),
    ]:
        try:
            conn.execute(
                f"ALTER TABLE projects ADD COLUMN {col} INTEGER NOT NULL DEFAULT {default}"
            )
        except sqlite3.OperationalError:
            pass  # column already exists

    # Asset metadata (Upgrade 0, Phase 0B-3A). The database records WHERE a
    # customer binary lives and how to prove it is intact; the bytes live in
    # the storage layer. Additive: creating this table changes nothing about
    # existing rows, and no artifact is migrated into it during 0B-3A.
    #
    # storage_key is UNIQUE, which is what makes recording an asset
    # idempotent -- a restarted or repeated migration re-records the same
    # key instead of creating a duplicate.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            storage_key TEXT NOT NULL UNIQUE,
            content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
            byte_size INTEGER NOT NULL DEFAULT 0,
            checksum TEXT NOT NULL DEFAULT '',
            approved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS assets_project_kind_idx "
        "ON assets (project_id, kind, approved)"
    )
    _init_auth_schema_sqlite(conn)
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# Users and project ownership (Phase A, forward-ported for Factory 1.8.5).
#
# Additive only. A users table is created and projects gain a NULLABLE
# user_id column. No existing row is changed by creating them: NULL means
# "not yet assigned", and ownership is only ever written by an explicit call
# (create_project(user_id=...), set_project_owner, or the operator-run
# scripts/migrate_phase_a.py). The project list and Saved Projects code does
# not read user_id, so their behaviour is unchanged.
# --------------------------------------------------------------------------

_USERS_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
)
"""


def _init_auth_schema_sqlite(conn) -> None:
    try:
        conn.execute("ALTER TABLE projects ADD COLUMN user_id INTEGER")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.execute(_USERS_DDL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS projects_user_id_idx ON projects (user_id)"
    )


_USER_COLS = "id, email, password_hash, role, active, created_at"


def _user_row_to_dict(row) -> dict | None:
    if not row:
        return None
    return {
        "id": int(row_field(row, "id", 0)),
        "email": str(row_field(row, "email", 1) or ""),
        "password_hash": str(row_field(row, "password_hash", 2) or ""),
        "role": str(row_field(row, "role", 3) or "user"),
        "active": bool(row_field(row, "active", 4)),
        "created_at": str(row_field(row, "created_at", 5) or ""),
    }


def get_user(user_id: int) -> dict | None:
    """The user row, or None. The dict includes password_hash: never return
    it to a browser -- auth.User and the /auth routes expose id/email/role."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    conn = get_conn()
    try:
        row = conn.execute(
            f"SELECT {_USER_COLS} FROM users WHERE id = ?", (uid,)
        ).fetchone()
    finally:
        conn.close()
    return _user_row_to_dict(row)


def get_user_by_email(email: str) -> dict | None:
    key = str(email or "").strip().lower()
    if not key:
        return None
    conn = get_conn()
    try:
        row = conn.execute(
            f"SELECT {_USER_COLS} FROM users WHERE email = ?", (key,)
        ).fetchone()
    finally:
        conn.close()
    return _user_row_to_dict(row)


def count_users() -> int:
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    finally:
        conn.close()
    return int(row_field(row, "n", 0) or 0)


def create_user(email: str, password_hash: str, role: str = "user") -> dict:
    """Create a user. The email is stored lower-cased. Raises on a duplicate."""
    key = str(email or "").strip().lower()
    if not key or not password_hash:
        raise ValueError("email and password_hash are required")
    if role not in ("user", "admin"):
        raise ValueError("role must be 'user' or 'admin'")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, role, active, created_at) "
            "VALUES (?, ?, ?, 1, ?)",
            (key, password_hash, role, _now()),
        )
        conn.commit()
        user_id = cur.lastrowid
    finally:
        conn.close()
    return get_user(user_id)


def set_user_active(user_id: int, active: bool) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE users SET active = ? WHERE id = ?", (int(bool(active)), int(user_id))
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0) == 1
    finally:
        conn.close()


def get_project_owner(project_id: int) -> int | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT user_id FROM projects WHERE id = ?", (int(project_id),)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    value = row_field(row, "user_id", 0)
    return int(value) if value is not None else None


def set_project_owner(project_id: int, owner_id: int) -> bool:
    """Assign one project to one existing user. False if either is missing."""
    if get_user(owner_id) is None:
        return False
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE projects SET user_id = ? WHERE id = ?", (int(owner_id), int(project_id))
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0) == 1
    finally:
        conn.close()


def backfill_project_owners(owner_id: int) -> int:
    """Give every UNOWNED project to one existing user. Idempotent: a second
    run finds nothing unowned and changes nothing. Never reassigns a project
    that already has an owner. Returns the number of rows changed."""
    if get_user(owner_id) is None:
        raise ValueError("owner does not exist")
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE projects SET user_id = ? WHERE user_id IS NULL", (int(owner_id),)
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0)
    finally:
        conn.close()


def ownership_counts() -> dict:
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()
        unowned = conn.execute(
            "SELECT COUNT(*) AS n FROM projects WHERE user_id IS NULL"
        ).fetchone()
    finally:
        conn.close()
    t = int(row_field(total, "n", 0) or 0)
    u = int(row_field(unowned, "n", 0) or 0)
    return {"projects": t, "unowned": u, "owned": t - u}


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = json.loads(row["data"] or "{}")
    if not isinstance(data, dict):
        data = {}
    # Stamp the row version the caller just read, so that when this dict is
    # handed back to update_project() we can prove nobody else wrote in the
    # meantime. In-memory only: update_project() strips it before storing,
    # because a version persisted inside the blob would go stale and could
    # then be trusted wrongly. Every read path funnels through here, so every
    # read is protected, not just get_project().
    try:
        data[ROW_VERSION_KEY] = int(row["version"] or 0)
    except (IndexError, KeyError, TypeError):
        # A database created before the version column existed. Leave the
        # dict unstamped; writes from it are treated as unversioned.
        pass
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "data": data,
        "user_saved": bool(row["user_saved"]),
        "system_test": bool(row["system_test"]),
        "temporary": bool(row["temporary"]),
        "hidden_from_customer": bool(data.get("hidden_from_customer")),
        "internal_record": bool(data.get("internal_record")),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _col(col: str) -> str:
    """Return column expression — handles missing columns for old DBs gracefully."""
    return col if col in _TABLE_COLS else "0"


def _ebook_build_is_unfinished(data: dict) -> bool:
    """True when a one-click build was started and never finished.

    Kept here rather than imported so the customer list can never be
    broken by an import problem in the orchestrator; the orchestrator's
    `build_is_unfinished` holds the same rule and is tested against this.
    """
    state = data.get("ebook_build") if isinstance(data, dict) else None
    if not isinstance(state, dict):
        return False
    if not (state.get("stages") or state.get("build_id") or state.get("started_at")):
        return False
    return not bool(state.get("finished")) and not bool(state.get("failed"))


def list_unfinished_ebook_workspaces() -> list[dict]:
    """Ebook projects still being built, newest first.

    Saved Projects deliberately lists only finished, downloadable products --
    a DRAFT workspace is filtered out of it by design. That left a customer who
    started a book and closed the tab with no way back to it, even though the
    project was safely stored. This is the resume surface for exactly those
    projects; it does not change what Saved Projects shows.

    Same visibility rules as the customer list: real user saves only, no
    system/test/temporary rows.
    """
    conn = get_conn()
    rows = conn.execute(
        f"SELECT {','.join(_TABLE_COLS)} FROM projects "
        "WHERE user_saved = 1 AND system_test = 0 AND temporary = 0 "
        "AND type = 'ebook' ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()

    out: list[dict] = []
    for row in rows:
        project = _row_to_dict(row)
        data = project.get("data") if isinstance(project.get("data"), dict) else {}
        has_workspace = bool(
            data.get("ebook_project_workspace") or data.get("ebook_workspace"))
        # A ONE-CLICK build that is still writing its manuscript has no
        # workspace yet -- the workspace keys only appear once the build
        # reaches visuals/cover/design. Requiring one therefore hid every
        # book stalled mid-manuscript from this list, and a half-built book
        # has no PDF so Saved Projects excludes it too. Between them a
        # customer stopped at "Writing your chapters (5 of 9)" had no route
        # back from any screen. An unfinished build counts on its own.
        has_unfinished_build = _ebook_build_is_unfinished(data)
        if not has_workspace and not has_unfinished_build:
            continue
        # Finished books belong in Saved Projects -- but only once they are
        # actually there. A one-button build finishes as a DRAFT the customer
        # has not yet approved, so it is not an explicit save and Saved
        # Projects excludes it. Dropping it from here too would strand a
        # finished book in neither list.
        if data.get("export_ready") is True and is_customer_saved_product(project):
            continue
        if is_customer_clutter_record(project):
            continue
        ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
        rail = ws.get("rail") if isinstance(ws.get("rail"), dict) else {}
        done = sum(
            1 for v in rail.values()
            if isinstance(v, dict) and str(v.get("status") or "") == "approved"
        )
        out.append(
            {
                "id": project.get("id"),
                "name": project.get("name"),
                "updated_at": project.get("updated_at"),
                "next_action": ws.get("next_action") or "",
                "current_stage": ws.get("current_stage") or "",
                "steps_done": done,
                "steps_total": len(rail) or 0,
                # True when this book was started by the one-button build, so
                # the browser continues it on the customer screen instead of
                # the operational stage rail.
                "one_click": bool(data.get("ebook_build")),
            }
        )
    return out


def list_projects(
    include_system: bool = False,
) -> list[dict]:
    """List projects. By default hides system/test/temporary/internal records.

    Customer list requires user_saved=true, temporary=false, system_test=false,
    internal_record=false, hidden_from_customer=false, plus a name/metadata
    safety net for older rows whose flags were never set.
    """
    conn = get_conn()
    if include_system:
        rows = conn.execute(
            f"SELECT {','.join(_TABLE_COLS)} FROM projects ORDER BY updated_at DESC"
        ).fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]
    rows = conn.execute(
        f"SELECT {','.join(_TABLE_COLS)} FROM projects "
        "WHERE user_saved = 1 AND system_test = 0 AND temporary = 0 "
        "ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    visible: list[dict] = []
    for row in rows:
        project = _row_to_dict(row)
        if not is_customer_visible_project(project):
            continue
        visible.append(project)
    return visible


_CUSTOMER_PRODUCT_TYPES = frozenset({"product", "ebook"})
_CUSTOMER_PLAN_TYPES = frozenset({"research_plan", "product_plan"})
_CUSTOMER_HIDE_PHRASES = (
    "download proof",
    "next-steps",
    "next steps",
    "guided cover",
    "cover guided",
    "cover isolated",
    "view only",
    "view-only",
    "research: view only",
    "sample data",
    "demo record",
    "research persist",
    "product plan saved",
    "research saved",
    "title outline persist",
    "manuscript gate",
    "no cover preview",
    "live acceptance",
    "final acceptance",
    "seed target",
    "seed self refuse",
    "auto-generated",
)
_CUSTOMER_HIDE_WORD_RE = re.compile(
    r"(?i)(?<![a-z])("
    r"test|debug|qa|validation|pipeline|workflow|smoke|handoff|"
    r"isolated|isolation|seed|internal|temporary|placeholder|fixture"
    r")(?![a-z])"
)


def _customer_sort_key(project: dict) -> tuple:
    return (
        str(project.get("updated_at") or ""),
        str(project.get("created_at") or ""),
        int(project.get("id") or 0),
    )


def _normalize_customer_title(name: str | None) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _customer_product_type(project: dict) -> str:
    return str(project.get("type") or "").strip().lower()


def _customer_status(project: dict) -> str:
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    return str(data.get("status") or data.get("stage") or data.get("artifact_state") or "").strip().lower()


def _customer_hide_haystack(project: dict) -> str:
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    parts = [
        project.get("name"),
        project.get("type"),
        data.get("title"),
        data.get("name"),
        data.get("source"),
        data.get("product_type"),
        data.get("product_label"),
        data.get("status"),
        data.get("_test_reason"),
    ]
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def is_customer_clutter_record(project: dict) -> bool:
    """True when a record must not appear on the customer Saved Projects list."""
    if is_protected_customer_product(project.get("id"), project.get("name")):
        return False
    haystack = _customer_hide_haystack(project).lower()
    if any(phrase in haystack for phrase in _CUSTOMER_HIDE_PHRASES):
        return True
    return bool(_CUSTOMER_HIDE_WORD_RE.search(haystack))


_CUSTOMER_ALLOWED_STATUSES = frozenset(
    {"completed", "export_ready", "product_generated", "saved"}
)
_CUSTOMER_BLOCKED_STATUSES = frozenset(
    {
        "needs_correction",
        "draft",
        "research_saved",
        "product_plan_saved",
        "pending",
        "incomplete",
        "failed",
        "workflow",
        "validation",
        "temporary",
    }
)
_COVER_ONLY_PDF_NAMES = frozenset({"cover_local.pdf", "cover_page.pdf"})


def _is_confirmed_plan(project: dict) -> bool:
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    return bool(
        project.get("user_saved")
        and data.get("user_confirmed_save")
        and not project.get("hidden_from_customer")
        and not data.get("hidden_from_customer")
    )


def _normalize_status_token(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.replace(".", " ").replace("-", " ")
    return re.sub(r"\s+", "_", text).strip("_")


def _is_ebook_like_project(project: dict) -> bool:
    if _customer_product_type(project) == "ebook":
        return True
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    return str(data.get("product_type") or "").strip().lower() == "ebook"


def _is_explicit_user_save(project: dict) -> bool:
    """True only for an intentional customer save, not workflow/test auto-saves."""
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    if data.get("user_confirmed_save") is True:
        return True
    if str(data.get("_saved_at") or "").strip():
        return True
    return False


def _customer_status_allows_saved_list(project: dict) -> bool:
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    tokens: list[str] = []
    # artifact_state is a write-policy lifecycle (DRAFT/APPROVED/LOCKED), not a
    # product-completion status. Newly generated coloring books (and other PDF
    # products) remain DRAFT until the user locks them. Treating DRAFT as the
    # blocked "draft" workflow status hid complete books from Saved Projects.
    for key in ("status", "stage", "status_label"):
        token = _normalize_status_token(data.get(key))
        if token:
            tokens.append(token)
    if any(token in _CUSTOMER_BLOCKED_STATUSES for token in tokens):
        return False
    if data.get("quality_blocking") is True:
        return False
    label = str(data.get("status_label") or data.get("next_action") or "").lower()
    if "needs correction" in label:
        return False
    if _is_ebook_like_project(project):
        if data.get("ebook_ready") is False:
            return False
        if data.get("pdf_available") is False:
            return False
        if data.get("export_ready") is False and "export_ready" not in tokens:
            if not any(token in _CUSTOMER_ALLOWED_STATUSES for token in tokens):
                return False
    return any(token in _CUSTOMER_ALLOWED_STATUSES for token in tokens)


def _coloring_book_ready_for_customer_list(project: dict) -> bool:
    """Hide cover-only / QA-blocked coloring books; keep complete generated books."""
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    if str(data.get("product_type") or "").strip().lower() != "coloring_book":
        return True
    gen = _normalize_status_token(data.get("generation_stage"))
    if gen in {"cover_preview", "sample_interior"}:
        return False
    if data.get("needs_approval") is True:
        return False
    if data.get("qa_passed") is False:
        return False
    qa_result = data.get("qa_result") if isinstance(data.get("qa_result"), dict) else {}
    if qa_result.get("blocked_export") is True:
        return False
    if qa_result.get("all_passed") is False:
        return False
    return True


def _exports_root() -> Path:
    raw = (
        os.environ.get("FACTORY_EXPORTS_DIR")
        or os.environ.get("FLASK_EXPORTS_DIR")
        or ""
    ).strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent / "exports"


def _existing_customer_output_files(project: dict) -> list[Path]:
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    exports_root = _exports_root()
    found: list[Path] = []
    seen: set[str] = set()

    def _add(raw: object) -> None:
        text = str(raw or "").strip()
        if not text:
            return
        path = Path(text)
        if not path.is_absolute():
            slash = text.replace("\\", "/")
            if slash.startswith("exports/"):
                # Relative "exports/<...>" references must resolve against the
                # configured exports root (FACTORY_EXPORTS_DIR when set during
                # tests), not always the real flask_app/exports folder.
                path = exports_root / slash[len("exports/"):]
            elif path.suffix.lower() in {".pdf", ".zip"}:
                path = exports_root / path
            else:
                return
        if path.is_dir():
            for child in path.iterdir():
                if child.is_file() and child.suffix.lower() in {".pdf", ".zip"}:
                    _add(child)
            return
        if not path.is_file() or path.stat().st_size <= 0:
            return
        key = str(path.resolve()) if path.exists() else str(path)
        if key not in seen:
            seen.add(key)
            found.append(path)

    for key in ("pdf_path", "zip_path", "package_path", "export_path", "_pdf_path"):
        _add(data.get(key))
    for bundle_key in ("exports", "product_exports"):
        bundle = data.get(bundle_key)
        if not isinstance(bundle, dict):
            continue
        _add(bundle.get("folder"))
        files = bundle.get("files")
        if isinstance(files, dict):
            for entry in files.values():
                if isinstance(entry, dict):
                    _add(entry.get("path") or entry.get("local_path"))
                    name = str(entry.get("name") or "").strip()
                    url = str(entry.get("url") or "").strip()
                    if name.lower().endswith((".pdf", ".zip")):
                        for pkg in (
                            data.get("package_id"),
                            data.get("export_package_id"),
                            data.get("artifact_id"),
                            bundle.get("package_id"),
                        ):
                            if pkg:
                                _add(exports_root / str(pkg) / name)
                    if "/download/" in url.replace("\\", "/"):
                        tail = url.replace("\\", "/").split("/download/", 1)[-1]
                        _add(exports_root / tail)
    for key in ("package_id", "export_package_id", "artifact_id", "export_package"):
        pkg = str(data.get(key) or "").strip()
        if not pkg:
            continue
        folder = exports_root / pkg
        if not folder.is_dir():
            continue
        for child in folder.iterdir():
            if child.is_file() and child.suffix.lower() in {".pdf", ".zip"}:
                _add(child)

    found.extend(_asset_backed_customer_outputs(project, found, exports_root))
    return found


def _asset_backed_customer_outputs(
    project: dict, already_found: list[Path], exports_root: Path
) -> list[Path]:
    """Export files this project has a VERIFIED asset for but no disk copy.

    Upgrade 0, Phase 0B-3B1. Saved Projects decides whether a customer can
    see their product by whether a real file exists on disk. Once an
    artifact's bytes live in object storage, that test would wrongly hide
    the product -- so a verified asset also counts as "the file exists".

    Deliberately additive: the disk behaviour above is unchanged and runs
    first, and a disk copy always wins. With zero asset rows this returns
    nothing, so it is a no-op for every existing customer.

    An asset counts only when it fully verifies (record + object + byte
    count + SHA-256). An unverifiable asset must never make a product look
    downloadable when it is not.
    """
    project_id = int(project.get("id") or 0)
    if project_id <= 0:
        return []
    try:
        if not list_assets_exist():
            return []  # fast path: nothing migrated, so nothing to add
        assets = list_assets(project_id)
    except Exception:
        return []
    if not assets:
        return []

    try:
        from services.storage.compat import export_asset_is_available
        from services.storage.keys import export_key_to_relpath
    except Exception:
        return []

    seen = {str(p) for p in already_found}
    extra: list[Path] = []
    for asset in assets:
        if not asset.get("approved"):
            continue
        try:
            rel = export_key_to_relpath(str(asset.get("storage_key") or ""))
        except Exception:
            continue  # embedded-binary assets are not export files
        if Path(rel).suffix.lower() not in {".pdf", ".zip"}:
            continue
        path = exports_root / rel
        if str(path) in seen or path.is_file():
            continue  # a real file already covers this one
        if export_asset_is_available(project_id, rel):
            seen.add(str(path))
            extra.append(path)
    return extra


def _has_usable_customer_output(project: dict) -> bool:
    """Require a real PDF/ZIP/package file, not draft HTML/TXT or cover-only PDF."""
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    files = _existing_customer_output_files(project)
    real_pdfs = [
        path
        for path in files
        if path.suffix.lower() == ".pdf"
        and path.name.lower() not in _COVER_ONLY_PDF_NAMES
    ]
    real_zips = [path for path in files if path.suffix.lower() == ".zip"]
    pdf_marked = data.get("pdf_available") is True
    zip_marked = data.get("zip_available") is True
    if _is_ebook_like_project(project):
        # HTML/TXT or a QA-blocked zip of drafts is not a customer product.
        return bool(real_pdfs) and not (
            data.get("pdf_available") is False or data.get("quality_blocking") is True
        )
    if real_pdfs:
        return True
    if real_zips and (zip_marked or data.get("pdf_available") is not False):
        return True
    if pdf_marked and real_pdfs:
        return True
    if zip_marked and real_zips:
        return True
    return False


def is_customer_saved_product(project: dict) -> bool:
    """Strict customer Saved Projects rule. Does not delete or mutate rows.

    Protected ids are not auto-included unless they also carry customer_keep
    and an explicit user save. Other DRAFT / needs_correction rows stay hidden.
    """
    if not project:
        return False
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    if project.get("system_test") or data.get("system_test"):
        return False
    if project.get("temporary") or data.get("temporary"):
        return False
    if project.get("user_saved") is False or not project.get("user_saved"):
        return False
    if project.get("hidden_from_customer") or data.get("hidden_from_customer"):
        return False
    if project.get("internal_record") or data.get("internal_record"):
        return False
    type_ = _customer_product_type(project)
    if type_ in _CUSTOMER_PLAN_TYPES or type_ not in _CUSTOMER_PRODUCT_TYPES:
        return False
    if is_customer_clutter_record(project):
        return False
    if classify_customer_visibility(
        project.get("name") or "",
        project.get("type"),
        data,
        project_id=project.get("id"),
    ).get("hide"):
        return False
    if not _is_explicit_user_save(project):
        return False
    if is_customer_keep_product(project):
        return True
    if not _customer_status_allows_saved_list(project):
        return False
    if not _coloring_book_ready_for_customer_list(project):
        return False
    if not _has_usable_customer_output(project):
        return False
    return True


def is_customer_saved_candidate(project: dict) -> bool:
    """Alias kept for callers; customer list no longer includes plans."""
    return is_customer_saved_product(project)


def _dedupe_customer_projects(projects: list[dict]) -> list[dict]:
    """Keep the newest row for the same title, preferring keep/protected ids."""
    keep_id_by_title: dict[str, int] = {}
    for project in projects:
        try:
            pid = int(project.get("id"))
        except (TypeError, ValueError):
            continue
        if pid in _PROTECTED_PROJECT_IDS or pid in CUSTOMER_KEEP_PROJECT_IDS or is_customer_keep_product(project):
            title = _normalize_customer_title(project.get("name"))
            keep_id_by_title[title] = pid
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for project in projects:
        title = _normalize_customer_title(project.get("name"))
        type_ = _customer_product_type(project)
        try:
            pid = int(project.get("id"))
        except (TypeError, ValueError):
            pid = 0
        if title in keep_id_by_title and pid != keep_id_by_title[title]:
            continue
        key = (title, type_)
        if key in seen:
            continue
        seen.add(key)
        unique.append(project)
    return unique


def get_customer_saved_products(
    limit: int = 10,
    offset: int = 0,
) -> tuple[list[dict], bool]:
    """Customer Saved Projects: only intentionally saved completed products.

    Query-time filter. Does not delete or update rows. Does not pad to `limit`.
    """
    try:
        limit = max(0, int(limit))
    except (TypeError, ValueError):
        limit = 10
    try:
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        offset = 0
    conn = get_conn()
    rows = conn.execute(
        f"SELECT {','.join(_TABLE_COLS)} FROM projects "
        "WHERE user_saved = 1 AND system_test = 0 AND temporary = 0 "
        "ORDER BY updated_at DESC, created_at DESC, id DESC"
    ).fetchall()
    conn.close()
    candidates = []
    for row in rows:
        project = _row_to_dict(row)
        if not is_customer_saved_product(project):
            continue
        candidates.append(project)
    candidates.sort(key=_customer_sort_key, reverse=True)
    unique = _dedupe_customer_projects(candidates)
    sliced = unique[offset : offset + limit] if limit else unique[offset:]
    has_more = len(unique) > offset + len(sliced)
    return sliced, has_more


def get_customer_saved_projects(
    limit: int = 10,
    offset: int = 0,
) -> tuple[list[dict], bool]:
    """Backward-compatible alias for get_customer_saved_products."""
    return get_customer_saved_products(limit=limit, offset=offset)


def list_factory_source_projects() -> list[dict]:
    """Source list for Publishing Studio / Platform Packages dropdowns.

    Broader than the Saved Projects list — plans are publishable too — but
    collapsed with the same newest-wins dedupe, so repeated QA runs of one
    title contribute a single option instead of hundreds.
    """
    projects = list_projects(include_system=False)
    projects.sort(key=_customer_sort_key, reverse=True)
    return _dedupe_customer_projects(projects)


def get_project(project_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        f"SELECT {','.join(_TABLE_COLS)} FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


# --------------------------------------------------------------------------
# Export package -> project. ONE resolver, identical on both backends.
#
# THE DEFECT THIS EXISTS TO END
# -----------------------------
# Every download in production returned
# "403 stale_or_orphan_export_package" while the same download served 200
# locally. Two copies of this lookup (download_pipeline_agent and
# final_output_gate) read their rows POSITIONALLY:
#
#     for pid, name, ptype, data_str in rows:
#         try:
#             d = json.loads(data_str or "{}")
#         except Exception:
#             pass
#
# SQLite hands back sqlite3.Row, which unpacks as a sequence, so that worked.
# PostgreSQL is opened with psycopg's dict_row (services/db/dialect.connect),
# so each row is a MAPPING: unpacking it yields its KEYS. `data_str` became
# the literal string "data", json.loads raised, and the bare `except: pass`
# swallowed it -- so the resolver silently reported "no project owns this
# package" for every row, and the orphan guard correctly refused to serve a
# package it had been told was orphaned. The guard was right; its input was
# wrong.
#
# Rows are therefore read BY COLUMN NAME here (sqlite3.Row and dict both
# support that), never by position, and a parse failure is never silent.
# --------------------------------------------------------------------------

#: A package id as it appears inside a stored customer download URL, e.g.
#: "/download/6c905b99.../flower_parts.pdf". Saved Projects builds its buttons
#: from these, so a URL the app stored must resolve to the project that stores it.
_DOWNLOAD_URL_PACKAGE_RE = re.compile(r"/download/([A-Za-z0-9_-]{1,128})/")


def row_field(row, key: str, index: int | None = None):
    """One column value, whatever row type the active backend returns.

    sqlite3.Row supports both name and index; psycopg's dict_row supports
    name only. Name works for both, so name is what we use.
    """
    if row is None:
        return None
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        pass
    if index is not None:
        try:
            return row[index]
        except (KeyError, IndexError, TypeError):
            return None
    return None


def package_ids_for_data(data: dict | None) -> set[str]:
    """Every export package id this project's own metadata claims.

    Structured parsing, not a substring guess: each id is read from the field
    that holds it. Stored download URLs are included because Saved Projects
    builds the customer's buttons from them, so the URL the app handed out
    must resolve back to the project that handed it out.
    """
    found: set[str] = set()
    if not isinstance(data, dict):
        return found

    def _add(value) -> None:
        text = str(value or "").strip()
        if text:
            found.add(text)

    _add(data.get("package_id"))
    _add(data.get("export_package_id"))

    for container_key in ("product_exports", "exports"):
        container = data.get(container_key)
        if not isinstance(container, dict):
            continue
        _add(container.get("package_id"))
        meta = container.get("meta")
        if isinstance(meta, dict):
            _add(meta.get("package_id"))
        files = container.get("files")
        if isinstance(files, dict):
            for entry in files.values():
                if isinstance(entry, dict):
                    _add(entry.get("package_id"))
                    for match in _DOWNLOAD_URL_PACKAGE_RE.finditer(
                        str(entry.get("url") or "")
                    ):
                        _add(match.group(1))
        for entry in container.values():
            if isinstance(entry, dict):
                _add(entry.get("package_id"))
    return found


def find_project_by_package(
    package_id: str, types: tuple[str, ...] = ("product", "ebook")
) -> dict | None:
    """The project that owns this export package id, or None.

    The SQL substring is a PREFILTER only and can produce no false negatives:
    an id stored anywhere in the row's JSON is by definition a substring of
    that JSON text (`data` is TEXT on both backends). What actually decides a
    match is package_ids_for_data() parsing the structure.
    """
    pkg = str(package_id or "").strip()
    if not pkg:
        return None

    placeholders = ", ".join("?" for _ in types)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, type, data FROM projects "
            f"WHERE type IN ({placeholders}) AND data LIKE ?",
            (*types, f"%{pkg}%"),
        ).fetchall()
    finally:
        conn.close()

    for row in rows or []:
        raw = row_field(row, "data", 3)
        try:
            data = json.loads(raw or "{}")
        except (TypeError, ValueError):
            # Never silent: a row we cannot parse is a real problem, and
            # swallowing it is what hid this defect for an entire release.
            log.warning(
                "project row %r has unreadable data while resolving package %s",
                row_field(row, "id", 0), pkg,
            )
            continue
        if pkg in package_ids_for_data(data):
            return {
                "id": row_field(row, "id", 0),
                "name": row_field(row, "name", 1),
                "type": row_field(row, "type", 2),
                "data": data,
            }
    return None


def create_project(
    name: str,
    type_: str,
    data: dict,
    user_saved: bool | None = None,
    system_test: bool | None = None,
    temporary: bool | None = None,
    user_confirmed_save: bool = False,
    user_id: int | None = None,
) -> dict:
    """Create a new project record.

    Flags:
        user_saved  — user explicitly chose to save (show in normal list).
                      None = apply backend safety guard + default to True.
        system_test — system/test/debug project (hidden by default).
                      None = apply backend safety guard + default to False.
        temporary   — session/temporary record (hidden by default).
                      None = apply backend safety guard + default to False.
        user_confirmed_save — only this overrides the internal/test name guard.
    """
    payload = dict(data or {})
    resolved_user, resolved_sys, resolved_temp = apply_save_flags(
        name=name,
        explicit_user_save=user_saved,
        system_test=system_test,
        temporary=temporary,
        type_=type_,
        data=payload,
        user_confirmed_save=user_confirmed_save,
    )
    if not resolved_user:
        vis = classify_customer_visibility(name, type_, payload)
        payload = _stamp_hidden_metadata(
            payload,
            internal_record=bool(vis.get("internal_record")),
            system_test=resolved_sys,
        )
    elif user_confirmed_save:
        payload = _stamp_visible_metadata(payload)

    now = _now()
    conn = get_conn()
    cur = conn.execute(
        f"INSERT INTO projects (name, type, data, user_saved, system_test, temporary, created_at, updated_at) "
        f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            name,
            type_,
            json.dumps(payload),
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
    if user_id is not None:
        # Phase A ownership. Written separately so the insert above -- and
        # every caller that does not pass an owner -- is exactly as before.
        set_project_owner(project_id, int(user_id))
    return get_project(project_id)


def update_project(
    project_id: int,
    name: str | None,
    data: dict | None,
    type_: str | None = None,
    user_saved: bool | None = None,
    system_test: bool | None = None,
    temporary: bool | None = None,
    user_confirmed_save: bool = False,
) -> dict | None:
    """Update an existing project. Only non-None values are changed; flags
    are only updated when explicitly passed (None = keep existing).

    Optimistic concurrency (Upgrade 0, Phase 0B-2): this replaces the whole
    `data` blob, so a caller holding a copy read before someone else's write
    would erase that write. When the supplied dict carries the row version it
    was read at (every read stamps it -- see _row_to_dict), this write becomes
    a compare-and-swap and raises StaleProjectWrite if the row moved on.
    Data built from scratch carries no version and is written unconditionally,
    exactly as before: there is no earlier read for it to be stale against.
    """
    expected_version = None
    if isinstance(data, dict) and ROW_VERSION_KEY in data:
        try:
            expected_version = int(data[ROW_VERSION_KEY])
        except (TypeError, ValueError):
            expected_version = None

    existing = get_project(project_id)
    if not existing:
        return None

    new_name = name if name is not None else existing["name"]
    new_data = dict(data) if isinstance(data, dict) else dict(existing.get("data") or {})
    new_type = type_ if type_ is not None else existing["type"]
    new_user_saved = (
        user_saved if user_saved is not None else existing["user_saved"]
    )
    new_system_test = (
        system_test if system_test is not None else existing["system_test"]
    )
    new_temporary = (
        temporary if temporary is not None else existing["temporary"]
    )
    if not is_protected_customer_product(project_id, new_name):
        resolved_user, resolved_sys, resolved_temp = apply_save_flags(
            name=new_name,
            explicit_user_save=user_saved,
            system_test=system_test,
            temporary=temporary,
            type_=new_type,
            data=new_data,
            user_confirmed_save=user_confirmed_save,
        )
        vis = classify_customer_visibility(new_name, new_type, new_data)
        should_reapply = (
            user_confirmed_save
            or user_saved is not None
            or name is not None
            or type_ is not None
            or vis.get("hide")
        )
        if should_reapply:
            new_user_saved, new_system_test, new_temporary = (
                resolved_user,
                resolved_sys,
                resolved_temp,
            )
            if not new_user_saved:
                new_data = _stamp_hidden_metadata(
                    new_data,
                    internal_record=bool(vis.get("internal_record")),
                    system_test=new_system_test,
                )
            elif user_confirmed_save:
                new_data = _stamp_visible_metadata(new_data)

    # The version is in-memory bookkeeping between a read and its write. It
    # must never reach the stored blob: a persisted version goes stale the
    # moment the next write lands, and a later reader could trust it wrongly.
    new_data.pop(ROW_VERSION_KEY, None)

    params = [
        new_name,
        new_type,
        json.dumps(new_data),
        int(new_user_saved),
        int(new_system_test),
        int(new_temporary),
        _now(),
        project_id,
    ]
    sql = (
        "UPDATE projects SET name=?, type=?, data=?, "
        "user_saved=?, system_test=?, temporary=?, updated_at=?, "
        "version=version+1 WHERE id=?"
    )
    if expected_version is not None:
        sql += " AND version=?"
        params.append(expected_version)

    conn = get_conn()
    try:
        cur = conn.execute(sql, tuple(params))
        if expected_version is not None and cur.rowcount == 0:
            # The row still exists (checked above), so the only way to match
            # nothing is that its version moved: somebody wrote after this
            # caller read. Refuse rather than overwrite their work. No retry
            # here by design -- re-applying this same blob is precisely the
            # lost update being prevented.
            conn.rollback()
            actual = conn.execute(
                "SELECT version FROM projects WHERE id=?", (project_id,)
            ).fetchone()
            raise StaleProjectWrite(
                project_id, expected_version, int(actual["version"]) if actual else None
            )
        conn.commit()
    finally:
        conn.close()

    saved = get_project(project_id)
    # Re-stamp the caller's own dict with the version it now sits at, so a
    # caller that saves the same evolving dict repeatedly (the build
    # orchestrator's checkpoint pattern) stays protected on every write
    # instead of silently dropping to unversioned after the first one.
    if isinstance(data, dict) and saved is not None:
        data[ROW_VERSION_KEY] = saved["data"].get(ROW_VERSION_KEY, 0)
    return saved


def _asset_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "kind": row["kind"],
        "storage_key": row["storage_key"],
        "content_type": row["content_type"],
        "byte_size": row["byte_size"],
        "checksum": row["checksum"],
        "approved": bool(row["approved"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def record_asset(
    project_id: int,
    kind: str,
    storage_key: str,
    *,
    content_type: str = "application/octet-stream",
    byte_size: int = 0,
    checksum: str = "",
    approved: bool | None = None,
) -> dict:
    """Record (or refresh) where a customer artifact lives.

    Idempotent by storage_key: re-recording the same key updates its
    metadata in place and never creates a second row. That is what makes
    the future migration restartable -- running it twice produces one
    asset, not two.

    The database stores metadata and the key only. Bytes belong in the
    storage layer; a 56 MB row is what Phase 0B-3 exists to end.
    """
    now = _now()
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM assets WHERE storage_key=?", (storage_key,)
        ).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE assets SET project_id=?, kind=?, content_type=?, "
                "byte_size=?, checksum=?, approved=?, updated_at=? "
                "WHERE storage_key=?",
                (
                    int(project_id),
                    str(kind),
                    str(content_type),
                    int(byte_size),
                    str(checksum),
                    int(bool(existing["approved"]) if approved is None else bool(approved)),
                    now,
                    storage_key,
                ),
            )
        else:
            conn.execute(
                "INSERT INTO assets (project_id, kind, storage_key, content_type, "
                "byte_size, checksum, approved, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    int(project_id),
                    str(kind),
                    str(storage_key),
                    str(content_type),
                    int(byte_size),
                    str(checksum),
                    int(bool(approved)),
                    now,
                    now,
                ),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM assets WHERE storage_key=?", (storage_key,)
        ).fetchone()
    finally:
        conn.close()
    return _asset_row_to_dict(row) if row is not None else {}


def list_assets_exist() -> bool:
    """True when ANY asset row exists.

    A one-row probe so the customer download path can skip all asset work
    while nothing has been migrated -- which is the state throughout Phase
    0B-3B1. Cheap enough to call per request and always safe: on any error
    it reports False, which means "use the legacy source".
    """
    try:
        conn = get_conn()
        try:
            row = conn.execute("SELECT 1 FROM assets LIMIT 1").fetchone()
        finally:
            conn.close()
        return row is not None
    except sqlite3.Error:
        return False


def find_asset_by_export_path(export_dir: str, filename: str) -> dict | None:
    """The asset recorded for `exports/<export_dir>/<filename>`, if any.

    A download URL names the export directory and the file, but not the
    project. Rather than scanning every project's artifacts to work out
    the owner -- which would read the whole filesystem on every request --
    this matches the one part of the key that is fixed by the key rule:
    `projects/<id>/exports/<dir>/<file>`.

    Returns None when nothing matches, which means "use the legacy file".
    """
    directory = str(export_dir or "")
    name = str(filename or "")
    if not directory or not name:
        return None
    # The suffix is data, so LIKE wildcards in it are escaped rather than
    # trusted -- a filename containing % must not match other assets.
    suffix = f"/exports/{directory}/{name}"
    escaped = suffix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    try:
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM assets WHERE storage_key LIKE ? ESCAPE '\\' "
                "ORDER BY id LIMIT 8",
                (f"projects/%{escaped}",),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return None

    for row in rows:
        record = _asset_row_to_dict(row)
        # Confirm the match exactly rather than trusting the pattern.
        if record["storage_key"] == f"projects/{record['project_id']}/exports/{directory}/{name}":
            return record
    return None


def get_asset_by_key(storage_key: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM assets WHERE storage_key=?", (str(storage_key),)
        ).fetchone()
    finally:
        conn.close()
    return _asset_row_to_dict(row) if row is not None else None


def list_assets(project_id: int, kind: str | None = None) -> list[dict]:
    conn = get_conn()
    try:
        if kind:
            rows = conn.execute(
                "SELECT * FROM assets WHERE project_id=? AND kind=? ORDER BY id",
                (int(project_id), str(kind)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM assets WHERE project_id=? ORDER BY id",
                (int(project_id),),
            ).fetchall()
    finally:
        conn.close()
    return [_asset_row_to_dict(r) for r in rows]


# NOTE: _exports_root() is defined once, near the top of this file (it must
# honor FACTORY_EXPORTS_DIR/FLASK_EXPORTS_DIR — see that definition). A second,
# hardcoded definition used to live here and silently shadow it (Python keeps
# whichever `def` runs last at module load), which meant every caller in this
# file was actually using the real flask_app/exports path even when isolation
# env vars were set. Removed rather than duplicated.


def iter_project_asset_paths(
    data: dict | None,
    *,
    exports_root: Path | None = None,
) -> list[Path]:
    """Export/package/cover paths belonging to a project record."""
    root = Path(exports_root) if exports_root is not None else _exports_root()
    app_root = Path(__file__).resolve().parent
    found: list[Path] = []
    seen: set[str] = set()

    def _add(raw: object) -> None:
        text = str(raw or "").strip()
        if not text:
            return
        path = Path(text)
        if not path.is_absolute():
            if text.replace("\\", "/").startswith("exports/"):
                path = app_root / path
            else:
                path = root / path
        key = str(path)
        if key not in seen:
            seen.add(key)
            found.append(path)

    record = data if isinstance(data, dict) else {}
    for key in ("package_id", "artifact_id", "export_package_id"):
        pkg = str(record.get(key) or "").strip()
        if pkg:
            _add(root / pkg)
    exports = record.get("exports")
    if isinstance(exports, dict):
        _add(exports.get("folder"))
    cover = record.get("cover_design")
    if isinstance(cover, dict):
        _add(cover.get("local_image_path"))
        _add(cover.get("image_path"))
    _add(record.get("cover_image"))
    return found


def _assert_unlocked_for_deletion(data: dict | None) -> None:
    from services.quality.artifact_state import assert_project_deletion_allowed

    assert_project_deletion_allowed(data or {})


def delete_project(project_id: int) -> bool:
    """Delete one unlocked project row. LOCKED raises ArtifactStateError."""
    existing = get_project(project_id)
    if not existing:
        return False
    _assert_unlocked_for_deletion(existing.get("data"))
    conn = get_conn()
    cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def delete_matching_projects(
    where_sql: str,
    params: tuple = (),
) -> dict:
    """Delete unlocked rows matching ``where_sql``. Never deletes LOCKED projects.

    Returns deleted count, locked/skipped count, and skipped project IDs.
    """
    from services.quality.artifact_state import ArtifactStateError

    conn = get_conn()
    rows = conn.execute(
        f"SELECT {','.join(_TABLE_COLS)} FROM projects WHERE {where_sql}",
        params,
    ).fetchall()
    deleted = 0
    skipped_ids: list[int] = []
    for row in rows:
        project = _row_to_dict(row)
        pid = int(project["id"])
        try:
            _assert_unlocked_for_deletion(project.get("data"))
        except ArtifactStateError:
            skipped_ids.append(pid)
            continue
        cur = conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
        if cur.rowcount > 0:
            deleted += 1
    conn.commit()
    conn.close()
    return {
        "deleted": deleted,
        "locked_skipped": len(skipped_ids),
        "skipped_ids": skipped_ids,
    }


def remove_project_assets(
    project_id: int,
    *,
    exports_root: Path | None = None,
) -> bool:
    """Remove on-disk assets for an unlocked project. LOCKED: no file changes."""
    existing = get_project(project_id)
    if not existing:
        return False
    _assert_unlocked_for_deletion(existing.get("data"))
    for path in iter_project_asset_paths(
        existing.get("data"), exports_root=exports_root
    ):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    return True


def cleanup_project_storage(
    project_id: int,
    *,
    exports_root: Path | None = None,
    remove_assets: bool = True,
    remove_db_row: bool = True,
) -> dict:
    """Prune/orphan/export/revision/database-reference cleanup for one project.

    LOCKED raises before any asset, folder, or database-reference mutation.
    """
    existing = get_project(project_id)
    if not existing:
        return {"deleted": False, "assets_removed": False}
    _assert_unlocked_for_deletion(existing.get("data"))
    assets_removed = False
    if remove_assets:
        assets_removed = bool(
            remove_project_assets(project_id, exports_root=exports_root)
        )
    deleted = False
    if remove_db_row:
        deleted = bool(delete_project(project_id))
    return {"deleted": deleted, "assets_removed": assets_removed}


# ---------------------------------------------------------------------------
# Safety helpers
# ---------------------------------------------------------------------------

def _record_metadata_haystack(type_: str | None = None, data: dict | None = None) -> str:
    """Everything the SYSTEM wrote about a record -- never the customer's title.

    v1.9.1. "test", "qa", "debug", "fixture", "placeholder", "regression" and
    "handoff" are ordinary words in a real book title: Test Kitchen Favourites,
    The QA Handbook, Debug Your Life, Seed Starting for Beginners. Matching them
    anywhere stamped system_test=1 on a paid-for book at the moment it was
    created, so it vanished from its owner's Saved Projects with no message and
    no route back, and the bulk clean-up route counted it as deletable.

    In one of these fields the same word is the system's own label, not the
    customer's wording, and it still means what it always meant.
    """
    record = data if isinstance(data, dict) else {}
    parts = [
        type_,
        record.get("source"),
        record.get("product_type"),
        record.get("product_label"),
        record.get("_test_reason"),
    ]
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


#: An unmistakable label a customer does not put on a book they are selling:
#: "[TEST] ...", "(QA) ...", "TEST: ...", "DEBUG - ...".
_EXPLICIT_MARKER_RE = re.compile(
    r"(?i)(^|\s)[\[\(]\s*(test|qa|debug|fixture|placeholder|regression|handoff)\s*[\]\)]"
    r"|^(test|qa|debug|fixture|placeholder|regression|handoff)\s*[:\-\u2013\u2014]"
)


def _visibility_haystack(name: str, type_: str | None = None, data: dict | None = None) -> str:
    """Scan title/name/source/type/metadata only — never manuscript content."""
    record = data if isinstance(data, dict) else {}
    parts = [
        name,
        type_,
        record.get("title"),
        record.get("name"),
        record.get("source"),
        record.get("product_type"),
        record.get("product_label"),
        record.get("_test_reason"),
    ]
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def is_customer_keep_product(project: dict | None) -> bool:
    """True only for the explicit restore allowlist with customer_keep=true."""
    if not project:
        return False
    try:
        pid = int(project.get("id"))
    except (TypeError, ValueError):
        return False
    if pid not in CUSTOMER_KEEP_PROJECT_IDS:
        return False
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    return data.get("customer_keep") is True


def is_protected_customer_product(project_id: int | None, name: str | None) -> bool:
    if project_id is not None:
        try:
            if int(project_id) in _PROTECTED_PROJECT_IDS:
                return True
        except (TypeError, ValueError):
            pass
    lowered = str(name or "").strip().lower()
    if not lowered:
        return False
    return any(needle in lowered for needle in _PROTECTED_TITLE_NEEDLES)


def classify_customer_visibility(
    name: str,
    type_: str | None = None,
    data: dict | None = None,
    project_id: int | None = None,
) -> dict:
    """Classify a record as customer-visible, test, or internal.

    Conservative: broad tokens like system/internal/Isolated/Seed alone do not
    hide a real-looking product title. Those are reported as needs_decision.
    """
    if is_protected_customer_product(project_id, name):
        return {"hide": False, "system_test": False, "internal_record": False}
    haystack = _visibility_haystack(name, type_, data)
    lowered = haystack.lower()
    title = str(name or "").strip()

    system_test = False
    internal_record = False
    if any(phrase in lowered for phrase in _STRONG_TEST_PHRASES):
        system_test = True
    if any(phrase in lowered for phrase in _STRONG_INTERNAL_PHRASES):
        internal_record = True
    # v1.9.1. A bare word is evidence only where the customer did not write it:
    # in the record's own metadata, or behind an unmistakable label.
    metadata = _record_metadata_haystack(type_, data)
    bare_word_re_list = (_TEST_WORD_RE, _QA_WORD_RE)
    bare_in_metadata = any(rx.search(metadata) for rx in bare_word_re_list)
    bare_in_title = any(rx.search(title) for rx in bare_word_re_list)
    marked_title = bool(_EXPLICIT_MARKER_RE.search(title))
    if bare_in_metadata or marked_title:
        system_test = True
    if _SMOKE_TEST_RE.search(haystack) and (
        "test" in lowered or "workflow" in lowered or "pipeline" in lowered
    ):
        system_test = True
    if _ISOLATED_COVER_RE.search(haystack):
        system_test = True
    if _SEED_INTERNAL_RE.search(haystack):
        internal_record = True
    if _SYSTEM_INTERNAL_RE.search(haystack):
        system_test = True
        internal_record = True
    if _INTERNAL_RECORD_RE.search(title) or _INTERNAL_RECORD_RE.search(haystack):
        internal_record = True
    if _PIPELINE_TEST_RE.search(haystack) or _VALIDATION_TEST_RE.search(haystack):
        system_test = True
    if _TEMPORARY_RECORD_RE.search(haystack):
        system_test = True
    if _PLACEHOLDER_RE.search(metadata):
        system_test = True

    if system_test or internal_record:
        return {
            "hide": True,
            "system_test": system_test,
            "internal_record": internal_record,
        }

    if bare_in_title or _PLACEHOLDER_RE.search(title):
        return {
            "hide": False,
            "system_test": False,
            "internal_record": False,
            "needs_decision": "a test-sounding word appears only in the customer's own title",
        }

    broad = _BROAD_DECISION_RE.search(title)
    if broad:
        return {
            "hide": False,
            "system_test": False,
            "internal_record": False,
            "needs_decision": f"broad token '{broad.group(1)}' in real-looking title",
        }
    return {"hide": False, "system_test": False, "internal_record": False}


def is_test_name(name: str) -> bool:
    """Return True if `name` matches test/debug/internal hide patterns."""
    return bool(classify_customer_visibility(name).get("hide"))


def is_customer_visible_project(project: dict) -> bool:
    """Customer Saved Projects rule: saved, not temp/test/internal/hidden."""
    if not project:
        return False
    if is_protected_customer_product(project.get("id"), project.get("name")):
        return True
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    if project.get("system_test") or project.get("temporary"):
        return False
    if project.get("user_saved") is False:
        return False
    if data.get("hidden_from_customer") or data.get("internal_record"):
        return False
    if project.get("hidden_from_customer") or project.get("internal_record"):
        return False
    if classify_customer_visibility(
        project.get("name") or "",
        project.get("type"),
        data,
        project_id=project.get("id"),
    ).get("hide"):
        return False
    return bool(project.get("user_saved", True))


def _stamp_hidden_metadata(
    data: dict,
    *,
    internal_record: bool,
    system_test: bool,
) -> dict:
    payload = dict(data or {})
    payload["hidden_from_customer"] = True
    payload["user_saved"] = False
    payload["temporary"] = True
    if internal_record:
        payload["internal_record"] = True
    if system_test:
        payload["system_test"] = True
    return payload


def _stamp_visible_metadata(data: dict) -> dict:
    payload = dict(data or {})
    payload["hidden_from_customer"] = False
    payload["internal_record"] = False
    payload["user_saved"] = True
    payload["user_confirmed_save"] = True
    payload.pop("system_test", None)
    payload.pop("temporary", None)
    return payload


def apply_save_flags(
    name: str,
    explicit_user_save: bool | None,
    system_test: bool | None,
    temporary: bool | None,
    type_: str | None = None,
    data: dict | None = None,
    user_confirmed_save: bool = False,
) -> tuple[bool, bool, bool]:
    """Resolve final save flags for a create/update call.

    Internal/test names are hidden unless the request includes
    user_confirmed_save=true. user_saved=true alone is not enough.
    """
    vis = classify_customer_visibility(name, type_, data)
    is_hidden_kind = bool(vis.get("hide"))

    if is_hidden_kind and not user_confirmed_save:
        return False, bool(vis.get("system_test") or system_test), True

    user_saved = explicit_user_save if explicit_user_save is not None else True
    sys_test = bool(system_test) if system_test is not None else False
    temp = bool(temporary) if temporary is not None else False
    if is_hidden_kind and user_confirmed_save:
        return True, sys_test, temp
    return bool(user_saved), sys_test, temp


def hide_internal_records_from_customers() -> dict:
    """Flag matching rows as hidden. Does not delete records or change #4249."""
    conn = get_conn()
    rows = conn.execute(
        f"SELECT {','.join(_TABLE_COLS)} FROM projects"
    ).fetchall()
    hidden_ids: list[int] = []
    test_hidden = 0
    internal_hidden = 0
    needs_decision: list[dict] = []
    skipped_protected: list[int] = []
    # Rows that changed underneath this sweep and were left alone rather than
    # overwritten (Phase 0B-2 compare-and-swap).
    skipped_stale: list[int] = []
    for row in rows:
        pid = int(row["id"])
        name = row["name"] or ""
        if is_protected_customer_product(pid, name):
            skipped_protected.append(pid)
            continue
        data = json.loads(row["data"] or "{}")
        if not isinstance(data, dict):
            data = {}
        vis = classify_customer_visibility(name, row["type"], data, project_id=pid)
        if vis.get("needs_decision"):
            currently_visible = (
                bool(row["user_saved"])
                and not bool(row["system_test"])
                and not bool(row["temporary"])
            )
            if currently_visible:
                needs_decision.append(
                    {"id": pid, "name": name, "reason": vis["needs_decision"]}
                )
            continue
        if not vis.get("hide"):
            continue
        currently_visible = (
            bool(row["user_saved"])
            and not bool(row["system_test"])
            and not bool(row["temporary"])
        )
        if not currently_visible:
            continue
        data = _stamp_hidden_metadata(
            data,
            internal_record=bool(vis.get("internal_record")),
            system_test=bool(vis.get("system_test")),
        )
        # This sweep reads every row up front, then writes in a loop, so a
        # build running concurrently could have written between the two.
        # Compare-and-swap on the version read with the row: skip anything
        # that moved rather than clobbering newer state (Phase 0B-2).
        try:
            row_version = int(row["version"] or 0)
        except (IndexError, KeyError, TypeError):
            row_version = None
        stamped = dict(data)
        stamped.pop(ROW_VERSION_KEY, None)
        if row_version is None:
            cur = conn.execute(
                "UPDATE projects SET user_saved=0, system_test=?, temporary=1, data=? "
                "WHERE id=?",
                (
                    int(bool(vis.get("system_test")) or bool(row["system_test"])),
                    json.dumps(stamped),
                    pid,
                ),
            )
        else:
            cur = conn.execute(
                "UPDATE projects SET user_saved=0, system_test=?, temporary=1, data=?, "
                "version=version+1 WHERE id=? AND version=?",
                (
                    int(bool(vis.get("system_test")) or bool(row["system_test"])),
                    json.dumps(stamped),
                    pid,
                    row_version,
                ),
            )
        if cur.rowcount == 0:
            skipped_stale.append(pid)
            continue
        hidden_ids.append(pid)
        if vis.get("system_test"):
            test_hidden += 1
        if vis.get("internal_record"):
            internal_hidden += 1
    conn.commit()
    conn.close()
    return {
        "hidden_ids": hidden_ids,
        "hidden_count": len(hidden_ids),
        "test_debug_hidden": test_hidden,
        "internal_hidden": internal_hidden,
        "needs_decision": needs_decision,
        "skipped_protected": skipped_protected,
        "skipped_stale": skipped_stale,
    }
