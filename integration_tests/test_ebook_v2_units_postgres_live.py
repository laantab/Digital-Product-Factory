"""Verify shared worker checkpoints on a disposable PostgreSQL database."""
from concurrent.futures import ThreadPoolExecutor
import os
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from services.ebook_v2.recovery import Store


def test_shared_queue_recovers_with_fenced_leases(tmp_path):
    url = os.environ["FACTORY_TEST_POSTGRES_URL"]
    parsed = urlparse(url)
    assert parsed.hostname in {"localhost", "127.0.0.1"}
    assert parsed.path == "/factory_ebook_recovery_test"
    first = Store(tmp_path / "unused.sqlite", postgres_url=url)
    second = Store(tmp_path / "unused.sqlite", postgres_url=url)
    first.initialize()
    owner = uuid4().hex
    key = uuid4().hex

    def enqueue(store):
        return store.enqueue(owner, key, "chapter", "test", {"chapter": 1})

    with ThreadPoolExecutor(max_workers=2) as pool:
        left, right = pool.map(enqueue, (first, second))
    assert left == right
    with pytest.raises(LookupError):
        second.get("unrelated-owner", left)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda store: store.claim(owner, left, 30), (first, second)))
    (claim,) = [claim for claim in claims if claim is not None]
    assert not second.complete(owner, left, "wrong-token", {})
    assert second.complete(owner, left, claim["token"], {"text": "Verified chapter"})
    assert first.get(owner, left)["output"] == {"text": "Verified chapter"}
    assert first.claim(owner, left, 30) is None
    assert not (tmp_path / "unused.sqlite").exists()


def test_saved_book_queries_use_shared_postgres(tmp_path):
    from services.ebook_v2.books import Books
    from services.ebook_v2.editions import history

    url = os.environ["FACTORY_TEST_POSTGRES_URL"]
    parsed = urlparse(url)
    assert parsed.hostname in {"localhost", "127.0.0.1"}
    assert parsed.path == "/factory_ebook_recovery_test"
    writer = Books(tmp_path / "unused.sqlite", tmp_path, policies={"unused": None}, postgres_url=url)
    writer.initialize()
    reader = Books(tmp_path / "unused.sqlite", tmp_path, policies={"unused": None}, postgres_url=url)
    owner = uuid4().hex
    text = "\n\n".join(f"Paragraph {index} " + "word " * 100 for index in range(3))
    book = writer.create(owner, uuid4().hex, {
        "title": "Shared saved book", "author": "Test author",
        "chapters": [{"title": title, "text": text} for title in ("First", "Second")],
    })
    assert reader.listing(owner)[0]["title"] == "Shared saved book"
    assert reader.listing(uuid4().hex) == []
    assert any(row["id"] == book["id"] for row in reader.pending())
    assert history(reader, owner, book["id"])[0]["title"] == "Shared saved book"
