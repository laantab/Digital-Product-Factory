"""SQLite persistence for Product Projects."""
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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
    data = json.loads(row["data"] or "{}")
    if not isinstance(data, dict):
        data = {}
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
    return found


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
    user_confirmed_save: bool = False,
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
    are only updated when explicitly passed (None = keep existing)."""
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
    if _TEST_WORD_RE.search(haystack) or _QA_WORD_RE.search(haystack):
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
    if _TEMPORARY_RECORD_RE.search(haystack) or _PLACEHOLDER_RE.search(haystack):
        system_test = True

    if system_test or internal_record:
        return {
            "hide": True,
            "system_test": system_test,
            "internal_record": internal_record,
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
        conn.execute(
            "UPDATE projects SET user_saved=0, system_test=?, temporary=1, data=? "
            "WHERE id=?",
            (
                int(bool(vis.get("system_test")) or bool(row["system_test"])),
                json.dumps(data),
                pid,
            ),
        )
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
    }
