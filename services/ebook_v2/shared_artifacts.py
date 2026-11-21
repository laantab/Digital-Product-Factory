"""Verified PDF/ZIP handoff from a Studio worker to shared object storage.

Uses the existing storage-driver contract without changing legacy exports.
The database receipt is committed only after both objects pass readback.
"""
import hashlib
import json

from .publishing import inspect
from .recovery import CorruptCheckpoint, InputConflict, digest, encode


class SharedArtifacts:
    def __init__(self, books, storage):
        self.books = books
        self.storage = storage

    def initialize(self):
        with self.books.units.transaction() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS ebook_v2_artifacts (
                book_id TEXT PRIMARY KEY REFERENCES ebook_v2_books(id),
                owner TEXT NOT NULL, receipt TEXT NOT NULL, sha TEXT NOT NULL)""")

    @staticmethod
    def key(owner, book_id, name, checksum):
        identity = digest([str(owner), book_id])
        return f"ebook-v2/{identity}/{checksum}/{name}"

    def publish(self, owner, book_id):
        book = self.books.get(owner, book_id)
        payloads = {name: self.books.download(owner, book_id, name, preview=True)[0]
                    for name in ("ebook.pdf", "package.zip")}
        integrity = inspect(payloads["ebook.pdf"], payloads["package.zip"])
        files = {}
        for name, data in payloads.items():
            checksum = hashlib.sha256(data).hexdigest()
            key = self.key(owner, book_id, name, checksum)
            if not self.storage.verify(key, expected_checksum=checksum, expected_size=len(data)):
                self.storage.put(key, data, content_type=(
                    "application/pdf" if name.endswith(".pdf") else "application/zip"))
            # Do not trust object metadata or a successful upload response alone.
            if not self.storage.verify(key, expected_checksum=checksum, expected_size=len(data)):
                raise CorruptCheckpoint("Shared book file failed readback verification")
            files[name] = {"key": key, "sha256": checksum, "size": len(data)}
        receipt = {"spec_sha": book["spec_sha"], "files": files, "integrity": integrity}
        encoded = encode(receipt)
        with self.books.units.transaction() as conn:
            previous = conn.execute("SELECT sha FROM ebook_v2_artifacts WHERE book_id=?",
                                    (book_id,)).fetchone()
            if previous and previous["sha"] != digest(receipt):
                raise InputConflict("This book already has different published files")
            conn.execute("""INSERT INTO ebook_v2_artifacts (book_id,owner,receipt,sha)
                VALUES (?,?,?,?) ON CONFLICT(book_id) DO NOTHING""",
                         (book_id, str(owner), encoded, digest(receipt)))
        return receipt

    def download(self, owner, book_id, name, *, preview=False):
        book = self.books.get(owner, book_id)
        if book["state"] != "READY" and not (preview and book["state"] == "REVIEW"):
            raise ValueError("Review the completed book before downloading")
        with self.books.units.transaction() as conn:
            row = conn.execute("SELECT receipt,sha FROM ebook_v2_artifacts WHERE book_id=? AND owner=?",
                               (book_id, str(owner))).fetchone()
        if row is None:
            raise LookupError("Shared files are not ready")
        receipt = json.loads(row["receipt"])
        if digest(receipt) != row["sha"] or receipt["spec_sha"] != book["spec_sha"]:
            raise CorruptCheckpoint("Shared book receipt failed verification")
        if name not in receipt["files"]:
            raise LookupError("File not found")
        item = receipt["files"][name]
        if item["key"] != self.key(owner, book_id, name, item["sha256"]):
            raise CorruptCheckpoint("Shared book location failed verification")
        data = self.storage.get(item["key"])
        if len(data) != item["size"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise CorruptCheckpoint("Shared book file failed verification")
        return data, item["sha256"]
