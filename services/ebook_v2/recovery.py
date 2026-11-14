"""Durable local work, fenced leases and evidence-backed repair memory.

SQLite is the default for local Studio. PostgreSQL is opt-in for shared worker state.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


class CorruptCheckpoint(RuntimeError):
    pass


class InputConflict(ValueError):
    pass


class _PostgresStudioConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        from services.db.dialect import to_postgres

        return self.connection.execute(to_postgres(sql), params)


class Store:
    def __init__(self, path, clock=time.time, *, postgres_url=None):
        self.path = str(Path(path).resolve())
        self.clock = clock
        self.postgres_url = postgres_url

    @contextmanager
    def transaction(self):
        if self.postgres_url:
            import psycopg
            from psycopg.rows import dict_row

            conn = psycopg.connect(self.postgres_url, row_factory=dict_row)
        else:
            conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            conn.row_factory = sqlite3.Row
        try:
            if self.postgres_url:
                # Match SQLite's serialization for read-then-write leases and keys.
                conn.execute("SELECT pg_advisory_xact_lock(1162628930, 2)")
                yield _PostgresStudioConnection(conn)
            else:
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("BEGIN IMMEDIATE")
                yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        if not self.postgres_url:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS ebook_v2_units (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_key TEXT NOT NULL,
                stage TEXT NOT NULL, policy TEXT NOT NULL, payload TEXT NOT NULL,
                input_sha TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'QUEUED',
                attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
                due DOUBLE PRECISION NOT NULL DEFAULT 0, token TEXT, expires DOUBLE PRECISION NOT NULL DEFAULT 0,
                output TEXT, output_sha TEXT, error TEXT NOT NULL DEFAULT '',
                repair TEXT NOT NULL DEFAULT '', created DOUBLE PRECISION NOT NULL,
                UNIQUE(owner,request_key))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS ebook_v2_dependencies (
                unit_id TEXT NOT NULL REFERENCES ebook_v2_units(id),
                parent_id TEXT NOT NULL REFERENCES ebook_v2_units(id),
                PRIMARY KEY(unit_id,parent_id))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS ebook_v2_lessons (
                stage TEXT NOT NULL, policy TEXT NOT NULL, error TEXT NOT NULL,
                repair TEXT NOT NULL, successes INTEGER NOT NULL, output_sha TEXT NOT NULL,
                PRIMARY KEY(stage,policy,error,repair))""")

    @staticmethod
    def checked(row):
        if row is None:
            raise LookupError("Saved work was not found")
        result = dict(row)
        payload = json.loads(result["payload"])
        if digest(payload) != result["input_sha"]:
            raise CorruptCheckpoint("Saved input checksum does not match")
        result["payload"] = payload
        if result["output"] is not None:
            result["output"] = json.loads(result["output"])
            if digest(result["output"]) != result["output_sha"]:
                raise CorruptCheckpoint("Saved output checksum does not match")
        if result["state"] == "COMPLETE" and result["output"] is None:
            raise CorruptCheckpoint("Completed work has no verified output")
        return result

    def _get(self, conn, owner, unit_id):
        return self.checked(conn.execute(
            "SELECT * FROM ebook_v2_units WHERE id=? AND owner=?", (unit_id, str(owner))).fetchone())

    def get(self, owner, unit_id):
        with self.transaction() as conn:
            return self._get(conn, owner, unit_id)

    def outputs(self,owner,ids):
        """Batch view metadata without repeatedly loading saved input manuscripts."""
        ids=list(dict.fromkeys(ids));result={}
        with self.transaction() as conn:
            for start in range(0,len(ids),400):
                batch=ids[start:start+400]
                placeholders=",".join("?" for _ in batch)
                for row in conn.execute("SELECT id,stage,state,request_key,error,output,output_sha FROM ebook_v2_units WHERE owner=? AND id IN ("+placeholders+")",(str(owner),*batch)):
                    value=dict(row)
                    if value["output"] is not None:
                        try:value["output"]=json.loads(value["output"])
                        except (ValueError,TypeError):raise CorruptCheckpoint("Saved output is not valid JSON") from None
                        if digest(value["output"])!=value["output_sha"]:raise CorruptCheckpoint("Saved output checksum does not match")
                    if value["state"]=="COMPLETE" and value["output"] is None:raise CorruptCheckpoint("Missing completed output")
                    result[value["id"]]=value
        if len(result)!=len(ids):raise LookupError("Saved work was not found")
        return result

    def enqueue(self, owner, key, stage, policy, payload, parents=(), max_attempts=3):
        if (not str(owner) or not key or not stage or not policy or not isinstance(payload,dict)
                or type(max_attempts) is not int or not 1 <= max_attempts <= 10):
            raise ValueError("Invalid work request")
        parents = sorted(set(parents))
        fingerprint = digest({"stage": stage, "policy": policy, "payload": payload,
                              "parents": parents, "max_attempts": max_attempts})
        with self.transaction() as conn:
            prior = conn.execute("SELECT * FROM ebook_v2_units WHERE owner=? AND request_key=?",
                                 (str(owner), key)).fetchone()
            if prior:
                prior = self.checked(prior)
                saved_parents = sorted(r["parent_id"] for r in conn.execute(
                    "SELECT parent_id FROM ebook_v2_dependencies WHERE unit_id=?", (prior["id"],)))
                previous = digest({"stage": prior["stage"], "policy": prior["policy"],
                    "payload": prior["payload"], "parents": saved_parents, "max_attempts": prior["max_attempts"]})
                if previous != fingerprint:
                    raise InputConflict("This request key already names different work")
                return prior["id"]
            for parent in parents:
                self._get(conn, owner, parent)
            unit_id = uuid.uuid4().hex
            conn.execute("""INSERT INTO ebook_v2_units
                (id,owner,request_key,stage,policy,payload,input_sha,max_attempts,created)
                VALUES (?,?,?,?,?,?,?,?,?)""", (unit_id,str(owner),key,stage,policy,encode(payload),
                                              digest(payload),max_attempts,self.clock()))
            for parent in parents:
                conn.execute("INSERT INTO ebook_v2_dependencies VALUES (?,?)", (unit_id,parent))
            return unit_id

    def claim(self, owner, unit_id, seconds):
        if not 0 < seconds <= 3500:
            raise ValueError("Invalid lease duration")
        with self.transaction() as conn:
            unit = self._get(conn, owner, unit_id)
            now = self.clock()
            if unit["state"] in {"COMPLETE", "NEEDS_ATTENTION"} or unit["due"] > now:
                return None
            if unit["state"] == "RUNNING" and unit["expires"] > now:
                return None
            if unit["attempts"] >= unit["max_attempts"]:
                conn.execute("UPDATE ebook_v2_units SET state='NEEDS_ATTENTION',token=NULL,error='TIMEOUT' WHERE id=?",
                             (unit_id,))
                return None
            for row in conn.execute("SELECT parent_id FROM ebook_v2_dependencies WHERE unit_id=?", (unit_id,)):
                if self._get(conn, owner, row["parent_id"])["state"] != "COMPLETE":
                    return None
            token = uuid.uuid4().hex
            conn.execute("""UPDATE ebook_v2_units SET state='RUNNING',attempts=attempts+1,
                token=?,expires=? WHERE id=?""", (token,now+seconds,unit_id))
            return self._get(conn, owner, unit_id)

    def _owned(self, conn, owner, unit_id, token):
        unit = self._get(conn, owner, unit_id)
        return unit if (unit["state"] == "RUNNING" and unit["token"] == token
                        and unit["expires"] > self.clock()) else None

    def complete(self, owner, unit_id, token, output):
        # Only Worker calls this after its code-owned validator passes.
        if not isinstance(output,dict):
            raise ValueError("A checkpoint output must be an object")
        serialized, checksum = encode(output), digest(output)
        with self.transaction() as conn:
            unit = self._owned(conn, owner, unit_id, token)
            if unit is None:
                return False
            conn.execute("""UPDATE ebook_v2_units SET state='COMPLETE',output=?,output_sha=?,
                token=NULL,expires=0 WHERE id=?""", (serialized,checksum,unit_id))
            if unit["error"] and unit["repair"]:
                conn.execute("""INSERT INTO ebook_v2_lessons VALUES (?,?,?,?,1,?)
                    ON CONFLICT(stage,policy,error,repair) DO UPDATE SET
                    successes=successes+1,output_sha=excluded.output_sha""",
                    (unit["stage"],unit["policy"],unit["error"],unit["repair"],checksum))
            return True

    def fail(self, owner, unit_id, token, code, repair="", delay=1, candidate=None):
        if not 0 <= delay <= 3600:
            raise ValueError("Invalid retry delay")
        with self.transaction() as conn:
            unit = self._owned(conn, owner, unit_id, token)
            if unit is None:
                return False
            state = "QUEUED" if repair and unit["attempts"] < unit["max_attempts"] else "NEEDS_ATTENTION"
            serialized = encode(candidate) if candidate is not None else (encode(unit["output"]) if unit["output"] is not None else None)
            checksum = digest(candidate) if candidate is not None else unit["output_sha"]
            conn.execute("""UPDATE ebook_v2_units SET state=?,error=?,repair=?,due=?,token=NULL,
                expires=0,output=?,output_sha=? WHERE id=?""",
                (state,code,repair,self.clock()+delay,serialized,checksum,unit_id))
            return True

    def best_repair(self, stage, policy, code, allowed):
        with self.transaction() as conn:
            rows = conn.execute("""SELECT repair FROM ebook_v2_lessons
                WHERE stage=? AND policy=? AND error=? ORDER BY successes DESC,repair""",
                (stage,policy,code)).fetchall()
        return next((r["repair"] for r in rows if r["repair"] in allowed), allowed[0] if allowed else "")

    def seed_recovery(self,owner,new_id,prior_id,code,repair):
        """Explicit manual continuation retains rejected text, never its success."""
        with self.transaction() as conn:
            new=self._get(conn,owner,new_id);prior=self._get(conn,owner,prior_id)
            if new["state"]!="QUEUED" or new["attempts"]!=0:raise ValueError("Recovery unit already started")
            if prior["state"]!="NEEDS_ATTENTION" or prior["stage"]!=new["stage"]:
                raise ValueError("Recovery source must be the matching exhausted work")
            if prior["output"] is None:return
            conn.execute("UPDATE ebook_v2_units SET output=?,output_sha=?,error=?,repair=? WHERE id=?",
                (encode(prior["output"]),prior["output_sha"],code,repair,new_id))
