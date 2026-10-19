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


@pytest.fixture
def subscriber_pg(billing_pg):
    from services.billing import subscriber_store as C
    C.init_schema()
    return billing_pg


def _subscriber_seed(customer, quantity=1):
    from datetime import datetime, timedelta, timezone
    from services.billing import subscriber_store as C
    end = (datetime.now(timezone.utc) + timedelta(days=28)).isoformat()
    with store._tx() as c:
        c.execute('''INSERT INTO billing_account_state
            (account_ref, subscription_row, provider, allowance, status, period_end, updated_at)
            VALUES (?, ?, 'stripe', ?, 'active', ?, ?)''',
            (customer, int(customer.split('_')[1]), quantity, end, C.now()))
        C.grant_in_transaction(c, customer=customer, receipt=customer+'-invoice',
            cycle_key=customer+'-cycle', quantity=quantity, expires_at=end)


def test_postgres_competing_credit_and_budget_reservations(subscriber_pg):
    from services.billing import subscriber_store as C
    _subscriber_seed('user_101'); _subscriber_seed('user_102')
    C.initialize_verified_budget(limit_usd='7', existing_spend_usd='1', verified_at=C.now())
    ready = Barrier(2)
    def build(pair):
        account, project = pair
        ready.wait(timeout=10)
        try:
            C.reserve(account, project)
            return True
        except C.CreditError:
            return False
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(build, [('user_101',101),('user_102',102)])) == [False,True]
    assert sum(C.balance(a)['available'] for a in ('user_101','user_102')) == 1


def test_postgres_completion_is_exactly_once_under_concurrency(subscriber_pg):
    from services.billing import subscriber_store as C
    _subscriber_seed('user_103')
    C.initialize_verified_budget(limit_usd='7', existing_spend_usd='0', verified_at=C.now())
    C.reserve('user_103',103)
    ready = Barrier(2)
    def finish(_):
        ready.wait(timeout=10)
        return C.consume_verified_export('user_103',103,'a'*64,'b'*64)
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(finish, range(2))) == [False,True]
    assert C.balance('user_103')['consumed'] == 1


def test_postgres_failed_credit_transaction_rolls_back_budget_hold(subscriber_pg):
    from services.billing import subscriber_store as C
    _subscriber_seed('user_104')
    C.initialize_verified_budget(limit_usd='7', existing_spend_usd='0', verified_at=C.now())
    with pytest.raises(RuntimeError):
        with store._tx() as c:
            C._budget_hold(c,'user_104',104,'3.5')
            raise RuntimeError('failure after budget authorization')
    with subscriber_pg() as c:
        assert c.execute('SELECT COUNT(*) AS n FROM billing_budget_holds').fetchone()['n'] == 0
    assert C.balance('user_104')['available'] == 1


def _pending_subscriber():
    from services.billing import subscriber_store as C
    from datetime import datetime, timedelta, timezone
    import json
    end=(datetime.now(timezone.utc)+timedelta(days=25)).isoformat()
    with store._tx() as c:
        cur=c.execute('''INSERT INTO billing_subscriptions
            (account_ref,plan_id,billing_period,provider,status,price_cents,currency,metadata,created_at,updated_at)
            VALUES ('user_105','starter','monthly','stripe','reserved',1900,'usd',?, ?, ?)''',
            (json.dumps({'price_id':'price_monthly'}),C.now(),C.now()))
        row_id=cur.lastrowid
        c.execute('''INSERT INTO billing_account_state
            (account_ref,subscription_row,provider,allowance,test_mode,updated_at)
            VALUES ('user_105',?,'stripe',2,1,?)''',(row_id,C.now()))
        c.execute('''INSERT INTO billing_checkout_claims
            (account_ref,subscription_row,provider,checkout_id,created_at)
            VALUES ('user_105',?,'stripe','cs_fixture',?)''',(row_id,C.now()))
    return row_id


def test_postgres_payment_receipt_and_grant_rollback_together(subscriber_pg,monkeypatch):
    from services.billing import subscriber_store as C, subscriber_payments as W
    from tests.test_subscriber_payments import bind,invoice
    _pending_subscriber()
    event=bind();event['data']['object']['client_reference_id']='user_105'
    W.handle_event('stripe',event)
    original=C.grant_in_transaction
    def fail(conn,**kwargs):
        original(conn,**kwargs)
        raise RuntimeError('rollback paid grant')
    monkeypatch.setattr(C,'grant_in_transaction',fail)
    with pytest.raises(RuntimeError): W.handle_event('stripe',invoice())
    assert C.balance('user_105')['available']==0
    monkeypatch.setattr(C,'grant_in_transaction',original)
    assert W.handle_event('stripe',invoice())['status']=='credited'
    assert C.balance('user_105')['available']==2


def test_postgres_concurrent_paid_webhooks_grant_once(subscriber_pg):
    from services.billing import subscriber_store as C, subscriber_payments as W
    from tests.test_subscriber_payments import bind,invoice
    _pending_subscriber()
    event=bind();event['data']['object']['client_reference_id']='user_105'
    W.handle_event('stripe',event)
    ready=Barrier(2)
    def deliver(_):
        ready.wait(timeout=10)
        return W.handle_event('stripe',invoice())['status']
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(deliver,range(2)))==['credited','duplicate']
    assert C.balance('user_105')['available']==2
