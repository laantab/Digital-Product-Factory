"""Real generated files survive loss of the worker's export directory."""
import shutil

import pytest

from services.ebook_v2.books import Books
from services.ebook_v2.recovery import CorruptCheckpoint
from services.ebook_v2.shared_artifacts import SharedArtifacts
from services.storage.local import LocalFilesystemDriver
from tests.test_ebook_v2_books import reviewed


@pytest.fixture
def prepared(tmp_path):
    books = Books(tmp_path / "state.db", tmp_path / "worker")
    books.initialize()
    book = reviewed(books)
    storage = LocalFilesystemDriver(tmp_path / "shared")
    bridge = SharedArtifacts(books, storage)
    bridge.initialize()
    return books, book, storage, bridge


def test_restart_download_without_worker_files_preserves_owner_and_review(prepared, tmp_path):
    books, book, storage, bridge = prepared
    expected = {name: books.download("alice", book["id"], name, preview=True)[0]
                for name in ("ebook.pdf", "package.zip")}
    first = bridge.publish("alice", book["id"])
    assert bridge.publish("alice", book["id"]) == first
    with pytest.raises(ValueError):
        bridge.download("alice", book["id"], "ebook.pdf")
    with pytest.raises(LookupError):
        bridge.download("bob", book["id"], "ebook.pdf", preview=True)
    books.approve("alice", book["id"], book["revision"])
    shutil.rmtree(books.root)
    reopened = Books(tmp_path / "state.db", tmp_path / "different-worker")
    reader = SharedArtifacts(reopened, LocalFilesystemDriver(tmp_path / "shared"))
    for name, data in expected.items():
        assert reader.download("alice", book["id"], name)[0] == data
    with pytest.raises(LookupError):
        reader.download("alice", book["id"], "../ebook.pdf")


def test_partial_upload_never_commits_receipt_and_retry_recovers(prepared, monkeypatch):
    books, book, storage, bridge = prepared
    original = storage.put
    def fail_zip(key, data, **kwargs):
        if key.endswith("package.zip"):
            raise OSError("Simulated upload interruption")
        return original(key, data, **kwargs)
    monkeypatch.setattr(storage, "put", fail_zip)
    with pytest.raises(OSError):
        bridge.publish("alice", book["id"])
    with pytest.raises(LookupError):
        bridge.download("alice", book["id"], "ebook.pdf", preview=True)
    monkeypatch.setattr(storage, "put", original)
    receipt = bridge.publish("alice", book["id"])
    assert receipt["integrity"]["embedded_pdf_matches"]
    assert bridge.download("alice", book["id"], "package.zip", preview=True)[0]


def test_corrupt_remote_bytes_and_receipts_are_rejected(prepared):
    books, book, storage, bridge = prepared
    receipt = bridge.publish("alice", book["id"])
    storage.put(receipt["files"]["ebook.pdf"]["key"], b"corrupted")
    with pytest.raises(CorruptCheckpoint):
        bridge.download("alice", book["id"], "ebook.pdf", preview=True)
    bridge.publish("alice", book["id"])
    with books.units.transaction() as conn:
        conn.execute("UPDATE ebook_v2_artifacts SET receipt='{}' WHERE book_id=?", (book["id"],))
    with pytest.raises(CorruptCheckpoint):
        bridge.download("alice", book["id"], "ebook.pdf", preview=True)
