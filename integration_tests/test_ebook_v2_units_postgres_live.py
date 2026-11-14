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
