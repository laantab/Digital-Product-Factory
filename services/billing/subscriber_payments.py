"""Signed-user subscription payment lifecycle, applied in one SQL transaction.

The HTTP boundary must verify the provider signature before handle_event. Only
known checkout/subscription/customer bindings can grant credits. Provider event
receipt and effects commit together; exceptions deliberately cause retry.
"""
from datetime import datetime, timezone
import hashlib
import json

from services.billing import store as S, subscriber_store as C


def _id(value):
    return str((value.get('id') if isinstance(value, dict) else value) or '')


def _date(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return C.utc(value)


def _stamp(value):
    try:
        return int(datetime.fromisoformat(C.utc(value)).timestamp())
    except C.CreditError:
        return 0


def _event(provider, event):
    if provider == 'stripe':
        obj = (event.get('data') or {}).get('object') or {}
        return str(event.get('id') or ''), str(event.get('type') or ''), int(event.get('created') or 0), obj
    if provider != 'lemon_squeezy':
        raise C.CreditError('Unsupported payment provider.')
    meta, data = event.get('meta') or {}, event.get('data') or {}
    attrs = data.get('attributes') or {}
    kind = str(meta.get('event_name') or '')
    # Lemon has no guaranteed event ID. Mutable resource + kind + exact signed
    # payload gives a stable retry receipt without merging distinct renewals.
    key = str(meta.get('webhook_id') or '') or hashlib.sha256(
        json.dumps(event, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return key, kind, _stamp(attrs.get('updated_at') or attrs.get('created_at')), attrs


def _find(conn, provider, subscription, customer):
    row = conn.execute('''SELECT * FROM billing_account_state
        WHERE provider = ? AND provider_subscription_id = ?''', (provider, subscription)).fetchone()
    if not row or not subscription or not customer or row['provider_customer_id'] != customer:
        raise C.CreditError('Payment mapping is not ready; retry the event.')
    return dict(row)


def enrolled_event(provider, event):
    """Route a stored enrollment even when the public rollout is switched off."""
    _, kind, _, obj = _event(provider, event)
    if provider == 'lemon_squeezy':
        from services.billing import subscriber_topups as T
        if T.handles(event):
            return True
    if provider == 'stripe':
        metadata = obj.get('metadata') or ((obj.get('parent') or {}).get('subscription_details') or {}).get('metadata') or (obj.get('subscription_details') or {}).get('metadata') or {}
    else:
        metadata = (event.get('meta') or {}).get('custom_data') or {}
    if str(metadata.get('account_ref') or '').startswith('user_'):
        return True
    with S._tx() as conn:
        if provider == 'stripe' and kind == 'checkout.session.completed':
            row = conn.execute('SELECT id FROM billing_checkout_claims WHERE provider = ? AND checkout_id = ?', (provider, _id(obj))).fetchone()
        elif provider == 'lemon_squeezy' and kind == 'subscription_created':
            ref = ((event.get('meta') or {}).get('custom_data') or {}).get('account_ref')
            row = conn.execute('SELECT id FROM billing_account_state WHERE provider = ? AND account_ref = ?', (provider, str(ref or ''))).fetchone()
        else:
            sub = _subscription_id(provider, kind, obj, event)
            row = conn.execute('SELECT id FROM billing_account_state WHERE provider = ? AND provider_subscription_id = ?', (provider, sub)).fetchone() if sub else None
            if not row and kind in ('charge.refunded', 'refund.created') and _id(obj.get('customer')):
                row = conn.execute('SELECT id FROM billing_account_state WHERE provider = ? AND provider_customer_id = ?', (provider, _id(obj.get('customer')))).fetchone()
        return bool(row)


def _subscription_id(provider, kind, obj, event):
    if provider == 'lemon_squeezy':
        return str(obj.get('subscription_id') or '') if (event.get('data') or {}).get('type') == 'subscription-invoices' else _id(event.get('data'))
    if kind.startswith('customer.subscription.'):
        return _id(obj)
    return _id(obj.get('subscription') or ((obj.get('parent') or {}).get('subscription_details') or {}).get('subscription'))


def _bind(conn, provider, kind, stamp, obj, event):
    if provider == 'stripe':
        claim = conn.execute('SELECT * FROM billing_checkout_claims WHERE provider = ? AND checkout_id = ?', (provider, _id(obj))).fetchone()
        ref = str(obj.get('client_reference_id') or '')
        sub, customer = _id(obj.get('subscription')), _id(obj.get('customer'))
    else:
        custom = (event.get('meta') or {}).get('custom_data') or {}
        ref = str(custom.get('account_ref') or '')
        claim = conn.execute('SELECT * FROM billing_checkout_claims WHERE provider = ? AND account_ref = ?', (provider, ref)).fetchone()
        if claim and str(custom.get('subscription_row') or '') != str(claim['subscription_row']):
            raise C.CreditError('Checkout identity does not match.')
        sub, customer = _id(event.get('data')), str(obj.get('customer_id') or '')
    if not claim or claim['account_ref'] != ref or not sub or not customer:
        raise C.CreditError('Checkout identity is not ready; retry the event.')
    row = C.state_for(conn, ref)
    if not row or row['subscription_row'] != claim['subscription_row'] or row['provider'] != provider:
        raise C.CreditError('Checkout identity does not match.')
    mode = not bool(event.get('livemode')) if provider == 'stripe' else bool(obj.get('test_mode'))
    if bool(row['test_mode']) != mode:
        raise C.CreditError('Payment mode does not match checkout.')
    if row['provider_subscription_id'] and (row['provider_subscription_id'] != sub or row['provider_customer_id'] != customer):
        raise C.CreditError('Checkout is already bound to another subscription.')
    if row['terminal'] or stamp < row['last_event_at']:
        return 'stale'
    pending = ''
    if provider == 'lemon_squeezy' and obj.get('status') == 'active' and obj.get('renews_at'):
        pending = C.utc(obj['renews_at'])
    conn.execute('''UPDATE billing_account_state SET provider_subscription_id = ?,
        provider_customer_id = ?, pending_period_end = ?, last_event_at = ?, updated_at = ? WHERE id = ?''',
        (sub, customer, pending, stamp, C.now(), row['id']))
    conn.execute("UPDATE billing_checkout_claims SET state = 'bound' WHERE id = ?", (claim['id'],))
    # Binding grants no entitlement or credits, even if checkout says paid.
    return 'bound'


def _grant_invoice(conn, provider, stamp, obj, event):
    sub = _subscription_id(provider, '', obj, event)
    customer = _id(obj.get('customer')) if provider == 'stripe' else str(obj.get('customer_id') or '')
    row = _find(conn, provider, sub, customer)
    mode = not bool(event.get('livemode')) if provider == 'stripe' else bool(obj.get('test_mode'))
    if mode != bool(row['test_mode']):
        raise C.CreditError('Payment mode does not match checkout.')
    invoice = _id(obj) if provider == 'stripe' else _id(event.get('data'))
    old = conn.execute('SELECT id FROM billing_invoice_receipts WHERE provider = ? AND invoice_id = ?', (provider, invoice)).fetchone()
    if old:
        return 'duplicate_invoice'
    if row['terminal'] or row['payment_hold'] or row['status'] == 'cancelled':
        return 'held'
    recorded = conn.execute('SELECT * FROM billing_subscriptions WHERE id = ?', (row['subscription_row'],)).fetchone()
    if not recorded:
        raise C.CreditError('Checkout mapping is missing.')
    if provider == 'stripe':
        if obj.get('status') != 'paid' or obj.get('paid') is not True or obj.get('billing_reason') not in ('subscription_create', 'subscription_cycle'):
            return 'ignored'
        amount = int(obj.get('amount_paid') or 0)
        metadata = json.loads(recorded['metadata'] or '{}')
        price_id = metadata.get('price_id')
        lines = (obj.get('lines') or {}).get('data') or []
        recurring = [l for l in lines if _id(l.get('price') or ((l.get('pricing') or {}).get('price_details') or {}).get('price')) == price_id
                     and int(l.get('quantity') or 0) == 1 and not l.get('proration')
                     and not (((l.get('parent') or {}).get('subscription_item_details') or {}).get('proration'))]
        if len(recurring) != 1:
            raise C.CreditError('A verified recurring invoice line is required.')
        end = _date((recurring[0].get('period') or {}).get('end'))
    else:
        if obj.get('status') != 'paid' or obj.get('refunded') or obj.get('billing_reason') not in ('initial','renewal'):
            return 'ignored'
        amount = int(obj.get('total') or 0)
        end = row['pending_period_end']
        # Failed-payment renews_at can be a retry date, so only an active
        # subscription update may supply this candidate. Never invent a month.
        invoice_start = C.utc(obj.get('created_at'))
        if not end or end <= invoice_start:
            raise C.CreditError('The confirmed renewal period is not ready; retry the invoice.')
    if not invoice or str(obj.get('currency') or '').lower() != str(recorded['currency']).lower() or amount < int(recorded['price_cents']):
        raise C.CreditError('Invoice does not match the recorded monthly offer.')
    cycle = provider + ':' + sub + ':' + end
    C.grant_in_transaction(conn, customer=row['account_ref'], receipt=provider+':'+invoice,
        cycle_key=cycle, quantity=int(row['allowance']), expires_at=end)
    conn.execute('''INSERT INTO billing_invoice_receipts
        (provider, invoice_id, account_ref, cycle_key, created_at) VALUES (?, ?, ?, ?, ?)''',
        (provider,invoice,row['account_ref'],cycle,C.now()))
    # Paying an earlier invoice cannot undo a later failed-payment or lifecycle
    # update. The grant is stored once but new work remains denied until recovery.
    if stamp >= int(row['last_event_at']):
        conn.execute("UPDATE billing_account_state SET status = 'active', period_end = ?, last_event_at = ?, updated_at = ? WHERE id = ?", (max(end,row['period_end']),stamp,C.now(),row['id']))
        conn.execute("UPDATE billing_subscriptions SET provider_subscription_id = ?, provider_customer_id = ?, status = 'active', current_period_end = ?, updated_at = ? WHERE id = ?", (sub,customer,max(end,row['period_end']),C.now(),row['subscription_row']))
    return 'credited'


def _lifecycle(conn, provider, kind, stamp, obj, event):
    sub = _subscription_id(provider,kind,obj,event)
    customer = _id(obj.get('customer')) if provider == 'stripe' else str(obj.get('customer_id') or '')
    if not sub and kind in ('charge.refunded','refund.created'):
        found = conn.execute('SELECT * FROM billing_account_state WHERE provider = ? AND provider_customer_id = ?', (provider, customer)).fetchone()
        sub = found['provider_subscription_id'] if found else ''
    row = _find(conn,provider,sub,customer)
    mode = not bool(event.get('livemode')) if provider == 'stripe' else bool(obj.get('test_mode'))
    if mode != bool(row['test_mode']):
        raise C.CreditError('Payment mode does not match checkout.')
    # Refund signals always take priority, including delayed delivery.
    refund = kind in ('subscription_payment_refunded','charge.refunded','refund.created')
    if refund:
        conn.execute('UPDATE billing_account_state SET payment_hold = 1, updated_at = ? WHERE id = ?', (C.now(),row['id']))
        invoice = _id(obj.get('invoice')) if provider == 'stripe' else _id(event.get('data'))
        full = obj.get('refunded') is True or obj.get('status') == 'refunded'
        if full and invoice:
            conn.execute('UPDATE billing_credit_grants SET revoked = 1 WHERE account_ref = ? AND receipt = ?', (row['account_ref'],provider+':'+invoice))
        return 'payment_hold'
    if row['terminal'] or stamp < int(row['last_event_at']):
        return 'stale'
    failed = kind in ('invoice.payment_failed','subscription_payment_failed')
    expired = kind in ('customer.subscription.deleted','subscription_expired')
    cancelled = kind == 'subscription_cancelled' or bool(obj.get('cancel_at_period_end'))
    status = 'past_due' if failed else 'expired' if expired else 'cancelled' if cancelled else str(obj.get('status') or '')
    if status in ('unpaid','paused','incomplete','incomplete_expired'):
        status = 'past_due'
    if status == 'canceled':
        status = 'expired'
    if status not in ('active','past_due','cancelled','expired'):
        return 'ignored'
    pending = row['pending_period_end']
    if status == 'active' and provider == 'lemon_squeezy' and obj.get('renews_at'):
        pending = C.utc(obj['renews_at'])
    # Lifecycle status alone cannot activate an unpaid billing period.
    if status == 'active' and not row['period_end']:
        status = 'pending'
    conn.execute('''UPDATE billing_account_state SET status = ?, pending_period_end = ?,
        last_event_at = ?, terminal = ?, updated_at = ? WHERE id = ?''',
        (status,pending,stamp,int(status == 'expired'),C.now(),row['id']))
    return status


def handle_event(provider, event):
    key,kind,stamp,obj = _event(provider,event)
    if not key or stamp <= 0:
        raise C.CreditError('Payment event is missing its verified identity or timestamp.')
    with S._tx() as conn:
        if conn.execute('SELECT id FROM billing_subscriber_events WHERE provider = ? AND event_key = ?', (provider,key)).fetchone():
            return {'status':'duplicate'}
        from services.billing import subscriber_topups as T
        topup = provider == 'lemon_squeezy' and (
            ((event.get('meta') or {}).get('custom_data') or {}).get('topup_token')
            or ((event.get('data') or {}).get('type') == 'orders' and T.event_claim(conn,event)))
        if topup:
            result = T.apply_event(conn,kind,obj,event)
        elif (provider == 'stripe' and kind == 'checkout.session.completed') or (provider == 'lemon_squeezy' and kind == 'subscription_created'):
            result = _bind(conn,provider,kind,stamp,obj,event)
        elif kind in ('invoice.paid','invoice.payment_succeeded','subscription_payment_success','subscription_payment_recovered'):
            result = _grant_invoice(conn,provider,stamp,obj,event)
        else:
            result = _lifecycle(conn,provider,kind,stamp,obj,event)
        conn.execute('INSERT INTO billing_subscriber_events (provider,event_key,result,created_at) VALUES (?, ?, ?, ?)', (provider,key,result,C.now()))
        return {'status':result}
