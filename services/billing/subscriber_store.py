"""Additive subscriber accounting. All mutations share billing's SQL lock.

This module performs no provider calls and makes no public rollout decision.
Money uses integer millionths of USD. Holds remain after failures because they
represent conservative authorizations, not measured or refunded vendor bills.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re

from services.billing import store as S


class CreditError(ValueError):
    """Safe customer-facing refusal before billable work."""


def now():
    return datetime.now(timezone.utc).isoformat()


def utc(value):
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if d.tzinfo is None:
            raise ValueError()
        return d.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        raise CreditError('A verified billing-period date is required.') from None


def money(value):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d < 0 or d > 1000000 or d * 1000000 != (d * 1000000).to_integral_value():
            raise ValueError()
        return int(d * 1000000)
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        raise CreditError('Invalid spending authorization.') from None


def account(value):
    if not re.fullmatch(r'user_[1-9][0-9]{0,17}', str(value)):
        raise CreditError('A signed customer account is required.')
    return str(value)


SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS billing_credit_grants (
        id INTEGER PRIMARY KEY AUTOINCREMENT, account_ref TEXT NOT NULL,
        receipt TEXT NOT NULL UNIQUE, cycle_key TEXT NOT NULL UNIQUE,
        quantity INTEGER NOT NULL, expires_at TEXT NOT NULL,
        revoked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS billing_credit_reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, account_ref TEXT NOT NULL,
        project_id INTEGER NOT NULL UNIQUE, grant_id INTEGER NOT NULL,
        status TEXT NOT NULL, pdf_sha256 TEXT NOT NULL DEFAULT '',
        zip_sha256 TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS billing_business_budget (
        id INTEGER PRIMARY KEY, limit_units INTEGER NOT NULL,
        baseline_units INTEGER NOT NULL, verified_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS billing_budget_holds (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL UNIQUE,
        account_ref TEXT NOT NULL, amount_units INTEGER NOT NULL,
        created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS billing_account_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT, account_ref TEXT NOT NULL UNIQUE,
        subscription_row INTEGER NOT NULL UNIQUE, provider TEXT NOT NULL,
        provider_subscription_id TEXT NOT NULL DEFAULT '',
        provider_customer_id TEXT NOT NULL DEFAULT '', allowance INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', period_end TEXT NOT NULL DEFAULT '',
        pending_period_end TEXT NOT NULL DEFAULT '', test_mode INTEGER NOT NULL DEFAULT 0,
        last_event_at INTEGER NOT NULL DEFAULT 0, terminal INTEGER NOT NULL DEFAULT 0,
        payment_hold INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS billing_subscriber_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL,
        event_key TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE (provider, event_key))''',
    '''CREATE TABLE IF NOT EXISTS billing_invoice_receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL,
        invoice_id TEXT NOT NULL, account_ref TEXT NOT NULL,
        cycle_key TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE (provider, invoice_id))''',
    '''CREATE TABLE IF NOT EXISTS billing_checkout_claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT, account_ref TEXT NOT NULL UNIQUE,
        subscription_row INTEGER NOT NULL, provider TEXT NOT NULL,
        checkout_id TEXT NOT NULL DEFAULT '', checkout_url TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL DEFAULT 'creating', created_at TEXT NOT NULL)''',
)


def init_schema():
    import database
    conn = database.get_conn()
    try:
        for sql in SCHEMA:
            conn.execute(sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def state_for(conn, customer):
    row = conn.execute('SELECT * FROM billing_account_state WHERE account_ref = ?',
                       (account(customer),)).fetchone()
    return dict(row) if row else None


def _available(conn, customer, at):
    return conn.execute('''SELECT g.*, (g.quantity - (
        SELECT COUNT(*) FROM billing_credit_reservations r
        WHERE r.grant_id = g.id AND r.status IN ('reserved', 'consumed'))) AS available
        FROM billing_credit_grants g WHERE g.account_ref = ? AND g.revoked = 0
        AND g.expires_at > ? ORDER BY g.expires_at, g.id''', (customer, at)).fetchall()


def balance(customer):
    customer = account(customer)
    with S._tx() as conn:
        grants = _available(conn, customer, now())
        counts = conn.execute('''SELECT status, COUNT(*) AS n
            FROM billing_credit_reservations WHERE account_ref = ? GROUP BY status''',
            (customer,)).fetchall()
        result = {'available': sum(max(0, int(g['available'])) for g in grants),
                  'reserved': 0, 'consumed': 0}
        result.update({r['status']: int(r['n']) for r in counts if r['status'] in result})
        s = state_for(conn, customer)
        result['status'] = s['status'] if s else 'none'
        result['payment_hold'] = bool(s and s['payment_hold'])
        return result


def grant_in_transaction(conn, *, customer, receipt, cycle_key, quantity, expires_at):
    account(customer)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 1000:
        raise CreditError('Invalid monthly product allowance.')
    if not receipt or not cycle_key:
        raise CreditError('A verified paid receipt is required.')
    end = utc(expires_at)
    cur = conn.execute('''INSERT INTO billing_credit_grants
        (account_ref, receipt, cycle_key, quantity, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING''',
        (customer, receipt, cycle_key, quantity, end, now()))
    return bool(cur.rowcount)


def initialize_verified_budget(*, limit_usd, existing_spend_usd, verified_at):
    limit, baseline = money(limit_usd), money(existing_spend_usd)
    observed = utc(verified_at)
    if limit > money('7') or baseline > limit or observed > now():
        raise CreditError('Budget exceeds the verified owner authorization.')
    with S._tx() as conn:
        if conn.execute('SELECT id FROM billing_business_budget WHERE id = 1').fetchone():
            raise CreditError('The recorded business budget cannot be reset.')
        conn.execute('''INSERT INTO billing_business_budget
            (id, limit_units, baseline_units, verified_at) VALUES (1, ?, ?, ?)''',
            (limit, baseline, observed))


def _budget_hold(conn, customer, project, maximum):
    amount = money(maximum)
    if amount <= 0 or amount > money('3.5'):
        raise CreditError('This build requires an approved spending allowance.')
    old = conn.execute('SELECT * FROM billing_budget_holds WHERE project_id = ?', (project,)).fetchone()
    if old:
        if old['account_ref'] != customer or int(old['amount_units']) != amount:
            raise CreditError('Build spending authorization does not match.')
        return
    budget = conn.execute('SELECT * FROM billing_business_budget WHERE id = 1').fetchone()
    used = conn.execute('SELECT COALESCE(SUM(amount_units), 0) AS n FROM billing_budget_holds').fetchone()['n']
    if not budget or int(budget['baseline_units']) + int(used) + amount > int(budget['limit_units']):
        raise CreditError('Build spending is temporarily unavailable. Your credit is preserved.')
    conn.execute('''INSERT INTO billing_budget_holds (project_id, account_ref, amount_units, created_at)
        VALUES (?, ?, ?, ?)''', (project, customer, amount, now()))


def reserve(customer, project_id, *, build_budget_usd='3.5', concurrency=1):
    customer = account(customer)
    project = int(project_id)
    if project <= 0 or isinstance(concurrency, bool) or concurrency not in (1, 2, 3):
        raise CreditError('Invalid build request.')
    with S._tx() as conn:
        old = conn.execute('SELECT * FROM billing_credit_reservations WHERE project_id = ?', (project,)).fetchone()
        if old and old['account_ref'] != customer:
            raise CreditError('This build belongs to another account.')
        if old and old['status'] == 'consumed':
            return dict(old)
        s = state_for(conn, customer)
        if not s or s['payment_hold'] or s['status'] not in ('active', 'cancelled') or not s['period_end'] or s['period_end'] <= now():
            raise CreditError('An active paid billing period is required to build.')
        if old and old['status'] == 'reserved':
            # Existing work may finish after its grant expires, but never after
            # a payment hold, failed renewal or account cancellation cutoff.
            _budget_hold(conn, customer, project, build_budget_usd)
            return dict(old)
        count = conn.execute("SELECT COUNT(*) AS n FROM billing_credit_reservations WHERE account_ref = ? AND status = 'reserved'", (customer,)).fetchone()['n']
        if int(count) >= concurrency:
            raise CreditError('Finish or recover your current book before starting another.')
        grant = next((g for g in _available(conn, customer, now()) if int(g['available']) > 0), None)
        if not grant:
            raise CreditError('No product credits are available for this billing period.')
        _budget_hold(conn, customer, project, build_budget_usd)
        if old:
            conn.execute("UPDATE billing_credit_reservations SET grant_id = ?, status = 'reserved', updated_at = ? WHERE project_id = ?", (grant['id'], now(), project))
        else:
            conn.execute('''INSERT INTO billing_credit_reservations
                (account_ref, project_id, grant_id, status, created_at, updated_at)
                VALUES (?, ?, ?, 'reserved', ?, ?)''', (customer, project, grant['id'], now(), now()))
        return dict(conn.execute('SELECT * FROM billing_credit_reservations WHERE project_id = ?', (project,)).fetchone())


def reservation(project_id):
    # Kept separate from user-facing reads: callers must first verify ownership.
    with S._tx() as conn:
        row = conn.execute('SELECT * FROM billing_credit_reservations WHERE project_id = ?', (int(project_id),)).fetchone()
        return dict(row) if row else None


def release(customer, project_id):
    with S._tx() as conn:
        cur = conn.execute("UPDATE billing_credit_reservations SET status = 'released', updated_at = ? WHERE account_ref = ? AND project_id = ? AND status = 'reserved'", (now(), account(customer), int(project_id)))
        return bool(cur.rowcount)


def consume_verified_export(customer, project_id, pdf_sha256, zip_sha256):
    if not all(re.fullmatch('[a-f0-9]{64}', str(v)) for v in (pdf_sha256, zip_sha256)):
        raise CreditError('Verified PDF and ZIP checksums are required.')
    with S._tx() as conn:
        row = conn.execute('SELECT * FROM billing_credit_reservations WHERE project_id = ?', (int(project_id),)).fetchone()
        if not row or row['account_ref'] != account(customer) or row['status'] == 'released':
            raise CreditError('No matching credit reservation exists.')
        if row['status'] == 'consumed':
            if row['pdf_sha256'] != pdf_sha256 or row['zip_sha256'] != zip_sha256:
                raise CreditError('The completed build has different export identities.')
            return False
        conn.execute("UPDATE billing_credit_reservations SET status = 'consumed', pdf_sha256 = ?, zip_sha256 = ?, updated_at = ? WHERE id = ?", (pdf_sha256, zip_sha256, now(), row['id']))
        return True
