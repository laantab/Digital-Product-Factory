"""Immutable, owner-scoped preservation before a legacy book is imported.

This stores JSON checkpoints through an explicitly supplied Factory connection
factory. It does not update projects, schedule work, approve chapters or copy
artifact bytes. Referenced customer artifacts must be verified separately.
SQL uses the common SQLite/Factory PostgreSQL connection surface; hosted
PostgreSQL execution still requires integration verification.
"""
from contextlib import contextmanager
import json
import uuid

from .recovery import CorruptCheckpoint, InputConflict, digest, encode


def snapshot(project, owner):
    """Copy the complete saved data only after checking its persisted owner."""
    owner = str(owner or "")
    if not owner or not isinstance(project, dict):
        raise LookupError("Book not found")
    if project.get("user_id") is None or str(project["user_id"]) != owner:
        raise LookupError("Book not found")
    if project.get("type") != "ebook":
        raise ValueError("Choose a saved ebook")
    project_id, version = project.get("id"), project.get("version")
    if type(project_id) is not int or project_id < 1:
        raise ValueError("Saved project identity is missing")
    if type(version) is not int or version < 0:
        raise ValueError("Saved project version is missing")
    if not isinstance(project.get("data"), dict):
        raise ValueError("Saved project data must be a decoded object")
    payload = {
        "schema_version": 1, "owner": owner, "project_id": project_id,
        "source_version": version, "name": project.get("name", ""),
        "data": project["data"],
    }
    # A JSON round trip detaches every nested body and preserves its text.
    return json.loads(encode(payload))


class Snapshots:
    def __init__(self, connection_factory):
        self.connection_factory = connection_factory

    @contextmanager
    def transaction(self):
        conn = self.connection_factory()
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        with self.transaction() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS ebook_v2_legacy_snapshots (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                project_id BIGINT NOT NULL, source_version BIGINT NOT NULL,
                payload TEXT NOT NULL, payload_sha TEXT NOT NULL,
                UNIQUE(owner,project_id,source_version))""")

    def save(self, project, owner):
        payload = snapshot(project, owner)
        checksum = digest(payload)
        with self.transaction() as conn:
            conn.execute("""INSERT INTO ebook_v2_legacy_snapshots
                (id,owner,project_id,source_version,payload,payload_sha)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(owner,project_id,source_version) DO NOTHING""",
                (uuid.uuid4().hex, payload["owner"], payload["project_id"],
                 payload["source_version"], encode(payload), checksum))
            row = conn.execute("""SELECT id,payload_sha FROM ebook_v2_legacy_snapshots
                WHERE owner=? AND project_id=? AND source_version=?""",
                (payload["owner"], payload["project_id"], payload["source_version"])).fetchone()
            if row is None or row["payload_sha"] != checksum:
                raise InputConflict("This saved project version has different content")
            return row["id"]

    def reopen(self, owner, snapshot_id):
        with self.transaction() as conn:
            row = conn.execute("""SELECT payload,payload_sha,owner,project_id,source_version
                FROM ebook_v2_legacy_snapshots WHERE id=? AND owner=?""",
                (snapshot_id, str(owner or ""))).fetchone()
            if row is None:
                raise LookupError("Book not found")
            try:
                payload = json.loads(row["payload"])
                if digest(payload) != row["payload_sha"]:
                    raise ValueError("checksum")
                if (payload["schema_version"] != 1 or payload["owner"] != row["owner"]
                        or payload["project_id"] != row["project_id"]
                        or payload["source_version"] != row["source_version"]):
                    raise ValueError("identity")
                return payload
            except (KeyError, ValueError, TypeError):
                raise CorruptCheckpoint("Saved recovery snapshot failed integrity checks") from None
