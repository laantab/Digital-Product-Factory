"""Opt-in Lemon Squeezy top-ups; no defaults, live calls or credit on redirects.

Webhook entry points remain behind the existing signature verifier. Checkout
claims, event receipts and grants use the shared billing transaction boundary.
"""
import os
import re
import secrets
from urllib.parse import urlparse

from services.billing import subscriber_store as C, store as S
from services.billing import subscriber_checkout as Q, providers as PR


def offer():
    if not Q.enabled() or os.environ.get('FACTORY_TOPUPS_ENABLED') != '1':
        raise C.CreditError('Extra credits are not available yet.')
    try:
        quantity = int(os.environ['FACTORY_TOPUP_CREDITS'])
        cents = int(os.environ['FACTORY_TOPUP_PRICE_CENTS'])
        variant = os.environ['LEMONSQUEEZY_TOPUP_VARIANT_ID']
        store = os.environ['LEMONSQUEEZY_STORE_ID']
        if not 1 <= quantity <= 1000 or not 1 <= cents <= 1000000:
            raise ValueError()
        if not re.fullmatch(r'[1-9][0-9]*', variant) or not re.fullmatch(r'[1-9][0-9]*', store):
            raise ValueError()
    except (KeyError, ValueError):
        raise C.CreditError('The extra-credit offer is not configured.') from None
    return dict(quantity=quantity, cents=cents, variant=variant, store=store)


def _eligible(conn, customer):
    row = C.state_for(conn, customer)
    if (not row or row['provider'] != 'lemon_squeezy' or row['status'] != 'active'
            or row['payment_hold'] or row['terminal'] or row['period_end'] <= C.now()
            or not row['provider_customer_id']):
        raise C.CreditError('An active Lemon Squeezy subscription is required for extra credits.')
    return row


def customer_offer(customer):
    """Local configuration only. Do not contact a payment API on page loads."""
    try:
        o = offer()
        with S._tx() as conn:
            row = _eligible(conn, customer)
            claim = conn.execute('SELECT state FROM billing_topup_claims WHERE account_ref = ? ORDER BY id DESC LIMIT 1', (customer,)).fetchone()
        return dict(quantity=o['quantity'], price=f"${o['cents']/100:.2f}",
                    expires_at=row['period_end'], last_state=claim['state'] if claim else '')
    except C.CreditError:
        return None


def checkout(customer, email, request_key):
    customer = C.account(customer)
    if not re.fullmatch(r'[a-zA-Z0-9-]{20,80}', str(request_key or '')):
        raise C.CreditError('A checkout request identifier is required.')
    o = offer()
    if not PR.lemon_config().configured:
        raise C.CreditError('The payment service is not ready yet.')
    base = os.environ.get('FACTORY_PUBLIC_URL', '').rstrip('/')
    parsed = urlparse(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise C.CreditError('A secure return address is required.')
    with S._tx() as conn:
        row = _eligible(conn, customer)
        if bool(row['test_mode']) != (os.environ.get('FACTORY_BILLING_TEST_MODE') == '1'):
            raise C.CreditError('Payment mode does not match your subscription.')
        old = conn.execute('''SELECT * FROM billing_topup_claims WHERE account_ref = ?
            AND (request_key = ? OR state IN ('creating','ready','review')) ORDER BY id DESC LIMIT 1''', (customer, request_key)).fetchone()
        if old:
            if old['state'] == 'ready' and old['expires_at'] > C.now():
                return dict(checkout_url=Q.provider_url(old['checkout_url'], 'lemon_squeezy'))
            raise C.CreditError('This checkout is already recorded. Check your credit balance or contact support.')
        token = secrets.token_urlsafe(32)
        cur = conn.execute('''INSERT INTO billing_topup_claims
            (account_ref,request_key,token,customer_id,email,variant_id,store_id,quantity,
             price_cents,test_mode,expires_at,created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (customer,request_key,token,row['provider_customer_id'],email.casefold(),o['variant'],o['store'],
             o['quantity'],o['cents'],row['test_mode'],row['period_end'],C.now()))
        claim_id = cur.lastrowid
    try:
        variant = PR.lemon_variant(o['variant']).get('data') or {}
        attrs = variant.get('attributes') or {}
        if (str(variant.get('id')) != o['variant'] or attrs.get('is_subscription') is not False
                or attrs.get('pay_what_you_want') is not False or attrs.get('price') != o['cents']):
            raise C.CreditError('The one-time offer could not be verified.')
        payload = {'data':{'type':'checkouts','attributes':{
            'test_mode':bool(row['test_mode']), 'preview':True, 'expires_at':row['period_end'],
            'product_options':{'enabled_variants':[int(o['variant'])], 'redirect_url':base+'/?topup=returned'},
            'checkout_options':{'discount':False},
            'checkout_data':{'email':email,'custom':{'account_ref':customer,'topup_token':token},
                             'variant_quantities':[{'variant_id':int(o['variant']),'quantity':1}]}},
            'relationships':{'store':{'data':{'type':'stores','id':o['store']}},
                             'variant':{'data':{'type':'variants','id':o['variant']}}}}}
        result = PR._lemon_request('POST','/checkouts',payload).get('data') or {}
        a = result.get('attributes') or {}; preview = a.get('preview') or {}
        if (not result.get('id') or str(a.get('store_id')) != o['store']
                or str(a.get('variant_id')) != o['variant'] or a.get('test_mode') is not bool(row['test_mode'])
                or str(preview.get('currency','')).lower() != 'usd'
                or preview.get('subtotal') != o['cents'] or preview.get('discount_total') != 0):
            raise C.CreditError('The checkout amount or mode could not be verified.')
        url = Q.provider_url(a.get('url'),'lemon_squeezy')
        with S._tx() as conn:
            changed = conn.execute("UPDATE billing_topup_claims SET checkout_id = ?, checkout_url = ?, state = 'ready' WHERE id = ? AND state = 'creating'", (str(result['id']),url,claim_id)).rowcount
            if not changed:
                raise C.CreditError('Checkout needs payment review before opening.')
        return dict(checkout_url=url)
    except Exception:
        with S._tx() as conn:
            conn.execute("UPDATE billing_topup_claims SET state = 'review' WHERE id = ? AND state = 'creating'", (claim_id,))
        raise


def event_claim(conn, event):
    custom = (event.get('meta') or {}).get('custom_data') or {}
    token = str(custom.get('topup_token') or '')
    order = str((event.get('data') or {}).get('id') or '')
    if token:
        return conn.execute('SELECT * FROM billing_topup_claims WHERE token = ?', (token,)).fetchone()
    return conn.execute("SELECT * FROM billing_topup_claims WHERE order_id = ? AND order_id <> ''", (order,)).fetchone()


def handles(event):
    custom = (event.get('meta') or {}).get('custom_data') or {}
    if custom.get('topup_token'):
        return True
    if (event.get('data') or {}).get('type') != 'orders':
        return False
    with S._tx() as conn:
        return bool(event_claim(conn,event))


def apply_event(conn, kind, obj, event):
    if kind not in ('order_created','order_refunded') or (event.get('data') or {}).get('type') != 'orders':
        return 'ignored'
    claim = event_claim(conn,event)
    if not claim:
        raise C.CreditError('Top-up mapping is not ready; retry the event.')
    custom = (event.get('meta') or {}).get('custom_data') or {}
    order = str((event.get('data') or {}).get('id') or '')
    item = obj.get('first_order_item') or {}
    if (not order or (claim['order_id'] and claim['order_id'] != order)
            or (custom and (custom.get('account_ref') != claim['account_ref'] or custom.get('topup_token') != claim['token']))
            or str(obj.get('customer_id')) != claim['customer_id']
            or str(obj.get('store_id')) != claim['store_id']
            or type(obj.get('test_mode')) is not bool or obj['test_mode'] != bool(claim['test_mode'])
            or str(obj.get('currency','')).lower() != 'usd'
            or str(item.get('variant_id')) != claim['variant_id']):
        raise C.CreditError('Top-up payment identity does not match checkout.')
    receipt = 'lemon_topup:'+order
    if kind == 'order_refunded' or obj.get('refunded') or obj.get('refunded_amount',0):
        # Any partial or full reversal stops new work for review. Never erase
        # consumed products, release vendor cost holds or undo a later refund.
        conn.execute('UPDATE billing_credit_grants SET revoked = 1 WHERE receipt = ?', (receipt,))
        conn.execute('UPDATE billing_account_state SET payment_hold = 1, updated_at = ? WHERE account_ref = ?', (C.now(),claim['account_ref']))
        conn.execute("UPDATE billing_topup_claims SET state = 'refunded', order_id = ? WHERE id = ?", (order,claim['id']))
        return 'topup_refunded'
    if claim['state'] == 'refunded':
        return 'held'
    if claim['state'] == 'credited':
        return 'duplicate_topup'
    if obj.get('status') != 'paid':
        return 'ignored'
    if (obj.get('subtotal') != claim['price_cents'] or obj.get('discount_total') != 0
            or item.get('price') != claim['price_cents']
            or str(obj.get('user_email','')).casefold() != claim['email']):
        raise C.CreditError('Top-up amount does not match the recorded offer.')
    C.grant_in_transaction(conn,customer=claim['account_ref'],receipt=receipt,
        cycle_key=receipt,quantity=int(claim['quantity']),expires_at=claim['expires_at'])
    conn.execute("UPDATE billing_topup_claims SET state = 'credited', order_id = ? WHERE id = ?", (order,claim['id']))
    return 'topup_credited'
