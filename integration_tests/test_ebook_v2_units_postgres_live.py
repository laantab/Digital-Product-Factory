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
    writer = Books(tmp_path / "unused.sqlite", tmp_path, postgres_url=url)
    writer.initialize()
    reader = Books(tmp_path / "unused.sqlite", tmp_path, postgres_url=url)
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


def test_on_demand_saved_book_with_real_postgres(tmp_path):
    from functools import partial
    import io
    import shutil
    import zipfile
    from services.ebook_v2.books import Books
    from services.ebook_v2.shared_artifacts import SharedArtifacts
    from services.ebook_v2.shared_work_files import install
    from services.ebook_v2.workflow_recovery import Dispatch, run_saved_book
    from services.storage.local import LocalFilesystemDriver
    from tests.ebook_v2_fixture import spec

    url = os.environ['FACTORY_TEST_POSTGRES_URL']
    parsed = urlparse(url)
    assert parsed.hostname in {'localhost', '127.0.0.1'}
    assert parsed.path == '/factory_ebook_recovery_test'
    books = Books(tmp_path/'unused.sqlite', tmp_path/'worker', postgres_url=url)
    books.initialize()
    factory = partial(LocalFilesystemDriver, tmp_path/'shared')
    install(books, factory)
    artifacts = SharedArtifacts(books, factory()); artifacts.initialize()
    calls = []
    dispatch = Dispatch(books, 'builder/recover_saved_ebook', lambda *args: calls.append(args) or 'run-test')
    dispatch.initialize()
    owner = uuid4().hex
    book = books.create(owner, 'snapshot:'+uuid4().hex, spec())
    dispatch(owner, book['id']); dispatch(owner, book['id'])
    assert len(calls) == 1
    result = run_saved_book({'books': books, 'artifacts': artifacts}, owner, book['id'],
                            pause=lambda _: shutil.rmtree(books.root, ignore_errors=True))
    assert result['state'] == 'REVIEW'
    pdf, _ = artifacts.download(owner, book['id'], 'ebook.pdf', preview=True)
    package, _ = artifacts.download(owner, book['id'], 'package.zip', preview=True)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        assert archive.testzip() is None
        assert archive.read('ebook.pdf') == pdf
