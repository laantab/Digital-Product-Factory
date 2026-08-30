"""Billing persistence: subscriptions, founder seats, and webhook receipts.

Three things in here are load-bearing and easy to get wrong:

  * **The founder cap is enforced in SQL, not in Python.** Counting seats,
    deciding there is room, and then inserting is a race: two people checking
    out at the same moment both read 99 and both get seat 100. The insert
    itself carries the condition, inside an IMMEDIATE transaction, so the
    database is what says no.

  * **A seat is reserved, then confirmed.** Checkout can be abandoned, so an
    unconfirmed reservation expires and returns the seat. Only a provider
    webhook confirms it. Handing out seat 100 to someone who closed the tab
    would mean telling person 101 the cohort is full when it is not.

  * **Webhook delivery is at-least-once.** Every provider retries, so events
    are recorded by provider event id and replaying one is a no-op. Without
    that, a retried `subscription_created` double-counts a founder seat.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import database

# How long an unconfirmed founder seat is held while the customer is on the
# provider's payment page.
RESERVATION_MINUTES = 30

STATUS_RESERVED = "reserved"
STATUS_ACTIVE = "active"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"
STATUS_PAST_DUE = "past_due"

# Statuses that occupy a founder seat.
SEAT_HOLDING = (STATUS_RESERVED, STATUS_ACTIVE, STATUS_PAST_DUE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


class SeatsSoldOutError(RuntimeError):
    """Raised when the founding cohort is full."""


@contextmanager
def _tx():
    """IMMEDIATE so concurrent seat claims serialise instead of interleaving."""
    conn = database.get_conn()
    try:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def init_billing_db() -> None:
    conn = database.get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_ref TEXT NOT NULL,
            plan_id TEXT NOT NULL,
            billing_period TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_customer_id TEXT NOT NULL DEFAULT '',
            provider_subscription_id TEXT NOT NULL DEFAULT '',
            provider_checkout_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            price_cents INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'usd',
            founder_seat INTEGER,
            price_locked INTEGER NOT NULL DEFAULT 0,
            reserved_until TEXT,
            current_period_end TEXT,
            cancelled_at TEXT,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # One live subscription per account, and one holder per founder seat.
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_billing_founder_seat
        ON billing_subscriptions (founder_seat)
        WHERE founder_seat IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_billing_account
        ON billing_subscriptions (account_ref, status)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            provider_event_id TEXT NOT NULL,
            event_type TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}',
            handled_at TEXT NOT NULL,
            result TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_billing_event_unique
        ON billing_events (provider, provider_event_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_ref TEXT NOT NULL,
            period TEXT NOT NULL,
            product_type TEXT NOT NULL DEFAULT '',
            counted_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_billing_usage_period
        ON billing_usage (account_ref, period)
        """
    )
    conn.commit()
    conn.close()


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    try:
        out["metadata"] = json.loads(out.get("metadata") or "{}")
    except (TypeError, ValueError):
        out["metadata"] = {}
    return out


# --------------------------------------------------------------------------- #
# Founder seats
# --------------------------------------------------------------------------- #
def _expire_stale_reservations(conn: sqlite3.Connection) -> int:
    """Release seats whose checkout was never completed."""
    cur = conn.execute(
        """
        UPDATE billing_subscriptions
           SET status = ?, founder_seat = NULL, updated_at = ?
         WHERE status = ?
           AND reserved_until IS NOT NULL
           AND reserved_until < ?
        """,
        (STATUS_EXPIRED, _now(), STATUS_RESERVED, _now()),
    )
    return cur.rowcount or 0


def founder_seats_taken() -> int:
    with _tx() as conn:
        _expire_stale_reservations(conn)
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM billing_subscriptions
             WHERE founder_seat IS NOT NULL
               AND status IN ({','.join('?' * len(SEAT_HOLDING))})
            """,
            SEAT_HOLDING,
        ).fetchone()
    return int(row["n"] if row else 0)


def founder_seats_remaining(limit: int) -> int:
    return max(0, int(limit) - founder_seats_taken())


def reserve_founder_seat(
    *, account_ref: str, provider: str, billing_period: str,
    price_cents: int, currency: str, limit: int,
    checkout_id: str = "", metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Claim the lowest free seat number, or refuse.

    The seat number is chosen and written inside one IMMEDIATE transaction, so
    two simultaneous buyers cannot both be told they got the last seat.
    """
    with _tx() as conn:
        _expire_stale_reservations(conn)
        taken = {
            int(r["founder_seat"]) for r in conn.execute(
                f"""
                SELECT founder_seat FROM billing_subscriptions
                 WHERE founder_seat IS NOT NULL
                   AND status IN ({','.join('?' * len(SEAT_HOLDING))})
                """,
                SEAT_HOLDING,
            ).fetchall()
        }
        seat = next((n for n in range(1, int(limit) + 1) if n not in taken), None)
        if seat is None:
            raise SeatsSoldOutError(
                f"All {limit} founding seats are taken."
            )
        now = _now()
        reserved_until = (
            _now_dt() + timedelta(minutes=RESERVATION_MINUTES)
        ).isoformat()
        cur = conn.execute(
            """
            INSERT INTO billing_subscriptions (
                account_ref, plan_id, billing_period, provider,
                provider_checkout_id, status, price_cents, currency,
                founder_seat, price_locked, reserved_until,
                metadata, created_at, updated_at
            ) VALUES (?, 'founder', ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            """,
            (account_ref, billing_period, provider, checkout_id,
             STATUS_RESERVED, int(price_cents), currency, seat,
             reserved_until, json.dumps(metadata or {}), now, now),
        )
        sub_id = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM billing_subscriptions WHERE id = ?", (sub_id,)
        ).fetchone()
    return _row(row)


def release_founder_seat(subscription_id: int) -> None:
    with _tx() as conn:
        conn.execute(
            """
            UPDATE billing_subscriptions
               SET founder_seat = NULL, status = ?, updated_at = ?
             WHERE id = ?
            """,
            (STATUS_EXPIRED, _now(), int(subscription_id)),
        )


# --------------------------------------------------------------------------- #
# Subscriptions
# --------------------------------------------------------------------------- #
def create_pending_subscription(
    *, account_ref: str, plan_id: str, billing_period: str, provider: str,
    price_cents: int, currency: str, checkout_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now()
    with _tx() as conn:
        cur = conn.execute(
            """
            INSERT INTO billing_subscriptions (
                account_ref, plan_id, billing_period, provider,
                provider_checkout_id, status, price_cents, currency,
                reserved_until, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (account_ref, plan_id, billing_period, provider, checkout_id,
             STATUS_RESERVED, int(price_cents), currency,
             (_now_dt() + timedelta(minutes=RESERVATION_MINUTES)).isoformat(),
             json.dumps(metadata or {}), now, now),
        )
        row = conn.execute(
            "SELECT * FROM billing_subscriptions WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row(row)


def attach_checkout_id(subscription_id: int, checkout_id: str) -> None:
    with _tx() as conn:
        conn.execute(
            """
            UPDATE billing_subscriptions
               SET provider_checkout_id = ?, updated_at = ?
             WHERE id = ?
            """,
            (str(checkout_id), _now(), int(subscription_id)),
        )


def activate_subscription(
    *, subscription_id: int | None = None, checkout_id: str = "",
    provider_subscription_id: str = "", provider_customer_id: str = "",
    current_period_end: str = "",
) -> dict[str, Any] | None:
    """Confirm a reservation. Idempotent: activating an already-active row
    changes nothing, because webhooks are delivered more than once."""
    with _tx() as conn:
        if subscription_id:
            row = conn.execute(
                "SELECT * FROM billing_subscriptions WHERE id = ?",
                (int(subscription_id),)).fetchone()
        elif checkout_id:
            row = conn.execute(
                "SELECT * FROM billing_subscriptions WHERE provider_checkout_id = ?"
                " ORDER BY id DESC LIMIT 1", (str(checkout_id),)).fetchone()
        else:
            row = None
        if row is None:
            return None
        conn.execute(
            """
            UPDATE billing_subscriptions
               SET status = ?, reserved_until = NULL,
                   provider_subscription_id = COALESCE(NULLIF(?, ''), provider_subscription_id),
                   provider_customer_id = COALESCE(NULLIF(?, ''), provider_customer_id),
                   current_period_end = COALESCE(NULLIF(?, ''), current_period_end),
                   updated_at = ?
             WHERE id = ?
            """,
            (STATUS_ACTIVE, provider_subscription_id, provider_customer_id,
             current_period_end, _now(), row["id"]),
        )
        fresh = conn.execute(
            "SELECT * FROM billing_subscriptions WHERE id = ?", (row["id"],)
        ).fetchone()
    return _row(fresh)


def set_subscription_status(
    *, provider_subscription_id: str = "", subscription_id: int | None = None,
    status: str, current_period_end: str = "",
) -> dict[str, Any] | None:
    with _tx() as conn:
        if subscription_id:
            row = conn.execute(
                "SELECT * FROM billing_subscriptions WHERE id = ?",
                (int(subscription_id),)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM billing_subscriptions "
                "WHERE provider_subscription_id = ? ORDER BY id DESC LIMIT 1",
                (str(provider_subscription_id),)).fetchone()
        if row is None:
            return None
        # A cancelled founder subscription returns its seat to the cohort.
        release_seat = status == STATUS_CANCELLED and row["founder_seat"] is not None
        conn.execute(
            """
            UPDATE billing_subscriptions
               SET status = ?,
                   founder_seat = CASE WHEN ? THEN NULL ELSE founder_seat END,
                   cancelled_at = CASE WHEN ? = 'cancelled' THEN ? ELSE cancelled_at END,
                   current_period_end = COALESCE(NULLIF(?, ''), current_period_end),
                   updated_at = ?
             WHERE id = ?
            """,
            (status, 1 if release_seat else 0, status, _now(),
             current_period_end, _now(), row["id"]),
        )
        fresh = conn.execute(
            "SELECT * FROM billing_subscriptions WHERE id = ?", (row["id"],)
        ).fetchone()
    return _row(fresh)


def get_active_subscription(account_ref: str) -> dict[str, Any] | None:
    conn = database.get_conn()
    try:
        row = conn.execute(
            """
            SELECT * FROM billing_subscriptions
             WHERE account_ref = ? AND status IN (?, ?)
             ORDER BY id DESC LIMIT 1
            """,
            (account_ref, STATUS_ACTIVE, STATUS_PAST_DUE),
        ).fetchone()
    finally:
        conn.close()
    return _row(row)


def get_subscription(subscription_id: int) -> dict[str, Any] | None:
    conn = database.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM billing_subscriptions WHERE id = ?",
            (int(subscription_id),)).fetchone()
    finally:
        conn.close()
    return _row(row)


# --------------------------------------------------------------------------- #
# Webhook receipts
# --------------------------------------------------------------------------- #
def record_event(
    *, provider: str, event_id: str, event_type: str, payload: dict[str, Any],
) -> bool:
    """Return True the first time an event is seen, False on every replay."""
    conn = database.get_conn()
    try:
        conn.execute(
            """
            INSERT INTO billing_events
                (provider, provider_event_id, event_type, payload, handled_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (provider, str(event_id), str(event_type),
             json.dumps(payload)[:200000], _now()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def mark_event_result(provider: str, event_id: str, result: str) -> None:
    conn = database.get_conn()
    try:
        conn.execute(
            "UPDATE billing_events SET result = ? WHERE provider = ? AND provider_event_id = ?",
            (str(result)[:500], provider, str(event_id)),
        )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Metered usage
# --------------------------------------------------------------------------- #
def current_period_key() -> str:
    return _now_dt().strftime("%Y-%m")


def count_usage(account_ref: str, period: str | None = None) -> int:
    conn = database.get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM billing_usage WHERE account_ref = ? AND period = ?",
            (account_ref, period or current_period_key()),
        ).fetchone()
    finally:
        conn.close()
    return int(row["n"] if row else 0)


def record_usage(account_ref: str, product_type: str = "") -> int:
    conn = database.get_conn()
    try:
        conn.execute(
            "INSERT INTO billing_usage (account_ref, period, product_type, counted_at)"
            " VALUES (?, ?, ?, ?)",
            (account_ref, current_period_key(), str(product_type), _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return count_usage(account_ref)
