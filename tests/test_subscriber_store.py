"""Transactional customer credit and budget regressions; isolated SQL only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
import sqlite3

import pytest
from services.billing import store as S, subscriber_store as C


@pytest.fixture
def wallet(tmp_path, monkeypatch):
    path = tmp_path / 'billing.sqlite'
    def connect():
        conn = sqlite3.connect(path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn
    monkeypatch.setattr(S.database, 'get_conn', connect)
    S.init_billing_db()
    C.init_schema()
    return connect


def seed(customer='user_1', *, quantity=2, expires=None, receipt='invoice', cycle='period'):
    expiry = expires or (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
    with S._tx() as c:
        c.execute('''INSERT INTO billing_account_state
            (account_ref, subscription_row, provider, allowance, status, period_end, updated_at)
            VALUES (?, ?, 'stripe', ?, 'active', ?, ?)''',
            (customer, int(customer.split('_')[1]), quantity, expiry, C.now()))
        C.grant_in_transaction(c, customer=customer, receipt=receipt,
            cycle_key=cycle, quantity=quantity, expires_at=expiry)
    return expiry


def budget(spend='0'):
    C.initialize_verified_budget(limit_usd='7', existing_spend_usd=spend, verified_at=C.now())


def test_failed_build_releases_credit_but_keeps_spend_hold(wallet):
    seed(quantity=1); budget()
    C.reserve('user_1', 11)
    assert C.balance('user_1')['available'] == 0
    assert C.release('user_1', 11)
    assert C.balance('user_1')['available'] == 1
    assert C.reserve('user_1', 11)['status'] == 'reserved'
    with wallet() as c:
        assert c.execute('SELECT COUNT(*) AS n FROM billing_budget_holds').fetchone()['n'] == 1


def test_unknown_budget_blocks_without_reserving_credit(wallet):
    seed()
    with pytest.raises(C.CreditError, match='spending'):
        C.reserve('user_1', 11)
    assert C.balance('user_1')['available'] == 2
    assert C.reservation(11) is None


def test_duplicate_completion_does_not_charge_twice_or_change_hashes(wallet):
    seed(); budget(); C.reserve('user_1', 11)
    assert C.consume_verified_export('user_1', 11, 'a'*64, 'b'*64)
    assert not C.consume_verified_export('user_1', 11, 'a'*64, 'b'*64)
    with pytest.raises(C.CreditError, match='different export'):
        C.consume_verified_export('user_1', 11, 'c'*64, 'd'*64)
    assert C.balance('user_1')['consumed'] == 1
    assert C.balance('user_1')['available'] == 1
    assert not C.release('user_1', 11)


def test_one_remaining_budget_cannot_fund_two_concurrent_books(wallet):
    seed('user_1', receipt='i1', cycle='c1')
    seed('user_2', receipt='i2', cycle='c2')
    budget(spend='1')
    ready = Barrier(2)
    def run(pair):
        a,p = pair; ready.wait(timeout=10)
        try:
            C.reserve(a,p); return True
        except C.CreditError:
            return False
    with ThreadPoolExecutor(max_workers=2) as w:
        assert sorted(w.map(run, [('user_1',11),('user_2',12)])) == [False,True]
    assert C.balance('user_1')['reserved'] + C.balance('user_2')['reserved'] == 1


def test_credit_reservation_is_idempotent_and_not_transferable(wallet):
    seed(); budget()
    first = C.reserve('user_1',11)
    assert C.reserve('user_1',11)['id'] == first['id']
    with pytest.raises(C.CreditError, match='another account'):
        C.reserve('user_2',11)
    with pytest.raises(C.CreditError, match='current book'):
        C.reserve('user_1',12)


def test_expired_credits_cannot_start_a_build(wallet):
    seed(expires=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()); budget()
    with pytest.raises(C.CreditError, match='paid billing period'):
        C.reserve('user_1',11)


def test_duplicate_invoice_or_same_cycle_never_grants_twice(wallet):
    end = seed()
    with S._tx() as c:
        assert not C.grant_in_transaction(c, customer='user_1',receipt='invoice',cycle_key='other',quantity=2,expires_at=end)
        assert not C.grant_in_transaction(c, customer='user_1',receipt='other',cycle_key='period',quantity=2,expires_at=end)
    assert C.balance('user_1')['available'] == 2


def test_refund_hold_blocks_new_work_and_preserves_completed_history(wallet):
    seed(); budget(); C.reserve('user_1',11)
    C.consume_verified_export('user_1',11,'a'*64,'b'*64)
    with S._tx() as c:
        c.execute('UPDATE billing_account_state SET payment_hold = 1')
        c.execute('UPDATE billing_credit_grants SET revoked = 1')
    assert C.balance('user_1')['consumed'] == 1
    assert C.balance('user_1')['available'] == 0
    with pytest.raises(C.CreditError): C.reserve('user_1',12)


@pytest.mark.parametrize('value', ['nan','Infinity','-1','0.0000001','text'])
def test_invalid_money_fails_closed(value):
    with pytest.raises(C.CreditError): C.money(value)


def test_budget_cannot_be_reset_or_exceed_seven_dollars(wallet):
    with pytest.raises(C.CreditError): C.initialize_verified_budget(limit_usd='8',existing_spend_usd='0',verified_at=C.now())
    budget()
    with pytest.raises(C.CreditError, match='reset'): budget()
