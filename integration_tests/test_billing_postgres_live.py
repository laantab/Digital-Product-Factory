"""Run only against the disposable localhost database created by CI."""
from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
from urllib.parse import urlparse
import uuid

import psycopg
from psycopg.rows import dict_row
import pytest

from services.billing import store
from services.db.connection import PostgresConnection


@pytest.fixture
def billing_pg(monkeypatch):
    url = os.environ.get('FACTORY_TEST_POSTGRES_URL', '')
    parsed = urlparse(url)
    assert parsed.hostname in {'127.0.0.1', 'localhost'}, 'Only isolated localhost PostgreSQL is permitted'
    assert parsed.path == '/factory_billing_test', 'Refusing a non-test database'
    schema = 'billing_probe_' + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA {schema}')
    def connect():
        raw = psycopg.connect(url, row_factory=dict_row, options=f'-c search_path={schema}')
        return PostgresConnection(raw)
    monkeypatch.setattr(store.database, 'get_conn', connect)
    # Payment providers must never be reachable from these tests.
    import requests
    def blocked(*args, **kwargs):
        raise AssertionError('Payment/network provider calls are forbidden')
    monkeypatch.setattr(requests.sessions.Session, 'request', blocked)
    try:
        store.init_billing_db()
        yield connect
    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA {schema} CASCADE')


def reserve(account):
    return store.reserve_founder_seat(account_ref=account, provider='lemonsqueezy',
        billing_period='monthly', price_cents=2900, currency='usd', limit=1)


def test_real_postgres_pricing_and_reservation(billing_pg):
    assert store.founder_seats_remaining(100) == 100
    seat = reserve('first')
    assert seat['founder_seat'] == 1
    assert store.founder_seats_remaining(1) == 0


def test_two_buyers_cannot_both_claim_the_last_seat(billing_pg):
    ready = Barrier(2)
    def buy(account):
        ready.wait(timeout=10)
        try:
            return reserve(account)['founder_seat']
        except store.SeatsSoldOutError:
            return 'sold_out'
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(buy, ('buyer-a', 'buyer-b')))
    assert results.count(1) == results.count('sold_out') == 1
    assert store.founder_seats_remaining(1) == 0


def test_failed_transaction_does_not_commit_partial_usage(billing_pg):
    with pytest.raises(RuntimeError, match='rollback probe'):
        with store._tx() as conn:
            conn.execute("INSERT INTO billing_usage (account_ref, period, counted_at) VALUES (?, ?, ?)",
                         ('probe', 'test', 'now'))
            raise RuntimeError('rollback probe')
    with billing_pg() as conn:
        assert conn.execute('SELECT COUNT(*) AS n FROM billing_usage').fetchone()['n'] == 0


def test_repeated_webhook_is_recorded_once(billing_pg):
    event = dict(provider='lemonsqueezy', event_id='event-1', event_type='subscription_created', payload={})
    assert store.record_event(**event) is True
    assert store.record_event(**event) is False
    with billing_pg() as conn:
        assert conn.execute('SELECT COUNT(*) AS n FROM billing_events').fetchone()['n'] == 1


def test_concurrent_webhook_delivery_is_recorded_once(billing_pg):
    ready = Barrier(2)
    def deliver(_):
        ready.wait(timeout=10)
        return store.record_event(provider='lemonsqueezy', event_id='same-event',
                                  event_type='subscription_created', payload={})
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(deliver, range(2)))
    assert sorted(results) == [False, True]


def test_released_seat_can_be_reserved_again(billing_pg):
    first = reserve('first')
    store.release_founder_seat(first['id'])
    assert reserve('second')['founder_seat'] == 1
