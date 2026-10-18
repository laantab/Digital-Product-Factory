"""PostgreSQL adapter contracts for billing; no production or provider access."""
import pytest
from services.billing import store
from services.db.connection import PostgresConnection


class Cursor:
    rowcount = 0

    def fetchone(self):
        return {'n': 0, 'id': 1}


class EventCursor:
    def __init__(self, inserted):
        self.rowcount = int(inserted)

    def fetchone(self):
        return {'id': 1} if self.rowcount else None


class PostgreSQLSession:
    """Strict SQL-boundary spy, not a substitute for a live PostgreSQL gate."""
    def __init__(self):
        self.statements = []
        self.commits = self.rollbacks = self.closed = 0

    def execute(self, sql, params=()):
        statement = ' '.join(sql.upper().split())
        self.statements.append(statement)
        if 'BEGIN IMMEDIATE' in statement:
            raise ValueError('PostgreSQL syntax error near IMMEDIATE')
        return Cursor()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


def test_postgres_catalog_serializes_before_expiring_and_counting_seats(monkeypatch):
    session = PostgreSQLSession()
    monkeypatch.setattr(store.database, 'get_conn', lambda: PostgresConnection(session))
    assert store.founder_seats_remaining(100) == 100
    assert session.statements[0] == 'LOCK TABLE BILLING_SUBSCRIPTIONS IN SHARE ROW EXCLUSIVE MODE'
    assert 'UPDATE BILLING_SUBSCRIPTIONS' in session.statements[1]
    assert session.commits == session.closed == 1
    assert not session.rollbacks


def test_postgres_transaction_rolls_back_and_preserves_original_error(monkeypatch):
    session = PostgreSQLSession()
    monkeypatch.setattr(store.database, 'get_conn', lambda: PostgresConnection(session))
    with pytest.raises(RuntimeError, match='operation failed'):
        with store._tx():
            raise RuntimeError('operation failed')
    assert session.rollbacks == session.closed == 1
    assert not session.commits


def test_lock_failure_stops_billing_before_any_seat_query(monkeypatch):
    session = PostgreSQLSession()
    def fail_lock(sql, params=()):
        session.statements.append(sql)
        raise RuntimeError('lock unavailable')
    session.execute = fail_lock
    monkeypatch.setattr(store.database, 'get_conn', lambda: PostgresConnection(session))
    with pytest.raises(RuntimeError, match='lock unavailable'):
        store.founder_seats_remaining(100)
    assert len(session.statements) == 1
    assert session.rollbacks == session.closed == 1
    assert not session.commits


def test_replayed_postgres_webhook_is_a_noop_not_a_database_error(monkeypatch):
    from psycopg.errors import UniqueViolation
    session = PostgreSQLSession()
    events = set()
    def insert(sql, params=()):
        key = params[:2]
        fresh = key not in events
        if not fresh and 'ON CONFLICT' not in sql.upper():
            raise UniqueViolation('duplicate provider event')
        events.add(key)
        return EventCursor(fresh)
    session.execute = insert
    monkeypatch.setattr(store.database, 'get_conn', lambda: PostgresConnection(session))
    event = dict(provider='lemonsqueezy', event_id='event-1', event_type='subscription_created', payload={})
    assert store.record_event(**event) is True
    assert store.record_event(**event) is False
    assert len(events) == 1
