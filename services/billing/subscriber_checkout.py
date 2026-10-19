"""Server-derived subscriber identity and a single, verified monthly checkout."""
import json
import os
from urllib.parse import urlparse

from services.billing import plans as P, providers as PR, store as S, subscriber_store as C


def enabled():
    return os.environ.get('FACTORY_SUBSCRIPTIONS_ENABLED','') == '1'


def selected_plan():
    plan = P.get_plan(os.environ.get('FACTORY_SUBSCRIPTION_PLAN_ID',''))
    if plan.monthly_cents <= 0 or not 1 <= plan.products_per_month <= 1000 or plan.limited_seats:
        raise C.CreditError('The monthly subscription offer is not available.')
    return plan


def provider_url(value, provider, *, portal=False):
    u = urlparse(str(value or ''))
    host = (u.hostname or '').lower()
    allowed = host == ('billing.stripe.com' if portal else 'checkout.stripe.com') if provider == 'stripe' else host.endswith('.lemonsqueezy.com')
    if u.scheme != 'https' or not allowed or u.username or u.password or u.port not in (None,443):
        raise C.CreditError('The payment provider returned an invalid link.')
    return str(value)


def _verify_price(provider, price_id, plan):
    if provider == 'stripe':
        p = PR.stripe_price(price_id)
        r = p.get('recurring') or {}
        if (p.get('active') is not True or p.get('type') != 'recurring'
                or r.get('interval') != 'month' or r.get('interval_count') != 1
                or r.get('trial_period_days') not in (None,0)
                or p.get('billing_scheme') != 'per_unit'):
            raise C.CreditError('The monthly offer could not be verified.')
        amount,currency = p.get('unit_amount'),p.get('currency')
    else:
        p = (PR.lemon_variant(price_id).get('data') or {}).get('attributes') or {}
        if (p.get('is_subscription') is not True or p.get('interval') != 'month'
                or p.get('interval_count') != 1 or p.get('has_free_trial') is not False
                or p.get('pay_what_you_want') is not False):
            raise C.CreditError('The monthly offer could not be verified.')
        amount,currency = p.get('price'),p.get('currency')
    if amount != plan.monthly_cents or str(currency or '').lower() != P.CURRENCY:
        raise C.CreditError('The provider price does not match the monthly offer.')


def start_checkout(customer, email, provider, plan_id, period='monthly'):
    customer = C.account(customer)
    if not enabled():
        raise C.CreditError('Subscriptions are not available yet.')
    plan = selected_plan()
    if plan_id != plan.id or period != 'monthly' or provider not in PR.PROVIDERS:
        raise C.CreditError('Choose the available monthly subscription.')
    cfg = PR.provider_config(provider)
    if not cfg.configured:
        raise C.CreditError('The payment service is not ready yet.')
    test_mode = cfg.mode == 'test' if provider == 'stripe' else os.environ.get('FACTORY_BILLING_TEST_MODE') == '1'
    price_id = PR.provider_price_id(provider,plan.id,'monthly')
    # Verify before reserving a local checkout. Failure never falls through.
    _verify_price(provider,price_id,plan)
    with S._tx() as conn:
        claim = conn.execute('SELECT * FROM billing_checkout_claims WHERE account_ref = ?', (customer,)).fetchone()
        if claim:
            if claim['provider'] != provider:
                raise C.CreditError('A checkout already exists for this account.')
            if claim['state'] == 'ready':
                return {'checkout_url':provider_url(claim['checkout_url'],provider),'plan_id':plan.id}
            if claim['state'] != 'retryable' or provider != 'stripe':
                raise C.CreditError('Your checkout is already in progress. Please contact support if it does not open.')
            sub_id = claim['subscription_row']
            conn.execute("UPDATE billing_checkout_claims SET state = 'creating' WHERE id = ?", (claim['id'],))
        else:
            old = C.state_for(conn,customer)
            if old:
                raise C.CreditError('Use Manage Subscription for your existing account.')
            cur = conn.execute('''INSERT INTO billing_subscriptions
                (account_ref,plan_id,billing_period,provider,status,price_cents,currency,metadata,created_at,updated_at)
                VALUES (?, ?, 'monthly', ?, 'reserved', ?, ?, ?, ?, ?)''',
                (customer,plan.id,provider,plan.monthly_cents,P.CURRENCY,
                 json.dumps({'price_id':price_id,'allowance':plan.products_per_month}),C.now(),C.now()))
            sub_id = cur.lastrowid
            conn.execute('''INSERT INTO billing_account_state
                (account_ref,subscription_row,provider,allowance,test_mode,updated_at)
                VALUES (?, ?, ?, ?, ?, ?)''', (customer,sub_id,provider,plan.products_per_month,int(test_mode),C.now()))
            conn.execute('''INSERT INTO billing_checkout_claims
                (account_ref,subscription_row,provider,created_at) VALUES (?, ?, ?, ?)''', (customer,sub_id,provider,C.now()))
    base = os.environ.get('FACTORY_PUBLIC_URL','http://127.0.0.1:5000').rstrip('/')
    u = urlparse(base)
    if u.scheme != 'https' and not (os.environ.get('FACTORY_TEST_MODE') == '1' and u.hostname in ('localhost','127.0.0.1')):
        raise C.CreditError('The secure subscription return address is not configured.')
    metadata = {'account_ref':customer,'subscription_row':str(sub_id),'plan_id':plan.id}
    try:
        if provider == 'stripe':
            # Do not enable promotion codes or trial overrides in this fixed
            # monthly offer. Stable idempotency key recovers unknown outcomes.
            data = {'mode':'subscription','line_items[0][price]':price_id,'line_items[0][quantity]':1,
                    'success_url':base+'/?checkout=success','cancel_url':base+'/?checkout=cancelled',
                    'client_reference_id':customer,'customer_email':email}
            for k,v in metadata.items():
                data[f'metadata[{k}]'] = v
                data[f'subscription_data[metadata][{k}]'] = v
            result = PR._stripe_request('POST','/checkout/sessions',data,idempotency_key=f'factory-subscriber-{sub_id}')
            checkout_id,url = str(result.get('id') or ''),result.get('url')
        else:
            payload = {'data':{'type':'checkouts','attributes':{'test_mode':test_mode,
                'checkout_data':{'email':email,'custom':metadata},
                'product_options':{'redirect_url':base+'/?checkout=success'}},
                'relationships':{'store':{'data':{'type':'stores','id':os.environ.get('LEMONSQUEEZY_STORE_ID','')}},
                                 'variant':{'data':{'type':'variants','id':price_id}}}}}
            result = PR._lemon_request('POST','/checkouts',payload).get('data') or {}
            checkout_id,url = str(result.get('id') or ''),(result.get('attributes') or {}).get('url')
        url = provider_url(url,provider)
        if not checkout_id:
            raise C.CreditError('The payment provider did not confirm checkout.')
        with S._tx() as conn:
            conn.execute("UPDATE billing_checkout_claims SET checkout_id = ?, checkout_url = ?, state = 'ready' WHERE account_ref = ? AND subscription_row = ?", (checkout_id,url,customer,sub_id))
            conn.execute('UPDATE billing_subscriptions SET provider_checkout_id = ?, updated_at = ? WHERE id = ?', (checkout_id,C.now(),sub_id))
        return {'checkout_url':url,'plan_id':plan.id}
    except Exception:
        with S._tx() as conn:
            # Lemon lacks an idempotency key here. Keep its uncertain checkout
            # held for manual reconciliation; never blindly charge a second time.
            conn.execute('UPDATE billing_checkout_claims SET state = ? WHERE account_ref = ?',
                ('retryable' if provider == 'stripe' else 'review',customer))
        raise


def portal(customer):
    with S._tx() as conn:
        s = C.state_for(conn,customer)
    if not s or not s['provider_customer_id'] or not s['provider_subscription_id']:
        raise C.CreditError('No subscription management link is available yet.')
    if s['provider'] == 'stripe':
        body = PR._stripe_request('POST','/billing_portal/sessions',{'customer':s['provider_customer_id']})
        link = body.get('url')
    else:
        body = PR._lemon_request('GET','/subscriptions/'+s['provider_subscription_id'])
        link = (((body.get('data') or {}).get('attributes') or {}).get('urls') or {}).get('customer_portal')
    return provider_url(link,s['provider'],portal=True)
