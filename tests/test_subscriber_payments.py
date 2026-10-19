"""Paid invoice lifecycle including retry, ordering and cancellation boundaries."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from tests.test_subscriber_store import wallet
from services.billing import store as S, subscriber_store as C, subscriber_payments as W
from services.billing import subscriber_checkout as Q


@pytest.fixture
def checkout(wallet, monkeypatch):
    monkeypatch.setenv('FACTORY_SUBSCRIPTIONS_ENABLED','1')
    monkeypatch.setenv('FACTORY_SUBSCRIPTION_PLAN_ID','starter')
    monkeypatch.setenv('FACTORY_TEST_MODE','1')
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_fixture')
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_fixture')
    monkeypatch.setenv('STRIPE_PRICE_STARTER_MONTHLY','price_monthly')
    monkeypatch.setattr(Q.PR,'stripe_price',lambda _: {'active':True,'type':'recurring','billing_scheme':'per_unit',
        'unit_amount':1900,'currency':'usd','recurring':{'interval':'month','interval_count':1}})
    remote = Mock(return_value={'id':'cs_fixture','url':'https://checkout.stripe.com/c/pay/fixture'})
    monkeypatch.setattr(Q.PR,'_stripe_request',remote)
    Q.start_checkout('user_1','first@example.test','stripe','starter')
    return remote


def bind(stamp=100):
    return {'id':'evt_bind','type':'checkout.session.completed','created':stamp,'livemode':False,
        'data':{'object':{'id':'cs_fixture','client_reference_id':'user_1','subscription':'sub_1','customer':'cus_1','payment_status':'paid'}}}


def invoice(event='evt_invoice',stamp=200,invoice_id='in_1',end=None):
    end = end or int((datetime.now(timezone.utc)+timedelta(days=25)).timestamp())
    return {'id':event,'type':'invoice.paid','created':stamp,'livemode':False,
        'data':{'object':{'id':invoice_id,'subscription':'sub_1','customer':'cus_1',
            'paid':True,'status':'paid','billing_reason':'subscription_create','amount_paid':1900,'currency':'usd',
            'lines':{'data':[{'price':{'id':'price_monthly'},'quantity':1,'period':{'end':end}}]}}}}


def lifecycle(kind='customer.subscription.updated',stamp=300,**values):
    obj = {'id':'sub_1','customer':'cus_1','status':'active'}
    obj.update(values)
    return {'id':'evt_'+str(stamp),'type':kind,'created':stamp,'livemode':False,'data':{'object':obj}}


def test_checkout_binds_without_grant_then_paid_invoice_grants_once(checkout):
    assert W.handle_event('stripe',bind())['status'] == 'bound'
    assert C.balance('user_1')['available'] == 0
    assert W.handle_event('stripe',invoice())['status'] == 'credited'
    assert W.handle_event('stripe',invoice())['status'] == 'duplicate'
    assert W.handle_event('stripe',invoice(event='evt_other'))['status'] == 'duplicate_invoice'
    assert C.balance('user_1')['available'] == 10


def test_invoice_before_checkout_binding_rolls_back_receipt_for_retry(checkout):
    event = invoice()
    event['data']['object']['parent']={'subscription_details':{'metadata':{'account_ref':'user_1'}}}
    assert W.enrolled_event('stripe',event)
    with pytest.raises(C.CreditError, match='mapping'): W.handle_event('stripe',event)
    W.handle_event('stripe',bind())
    assert W.handle_event('stripe',event)['status'] == 'credited'


def test_fault_after_grant_rolls_back_event_receipt_and_credits(checkout,monkeypatch):
    W.handle_event('stripe',bind())
    original = C.grant_in_transaction
    def fail(conn,**kwargs):
        original(conn,**kwargs)
        raise RuntimeError('after grant')
    monkeypatch.setattr(C,'grant_in_transaction',fail)
    with pytest.raises(RuntimeError): W.handle_event('stripe',invoice())
    assert C.balance('user_1')['available'] == 0
    monkeypatch.setattr(C,'grant_in_transaction',original)
    assert W.handle_event('stripe',invoice())['status'] == 'credited'


def test_cancel_at_period_end_preserves_paid_access_then_expiry_blocks(checkout):
    W.handle_event('stripe',bind()); W.handle_event('stripe',invoice())
    W.handle_event('stripe',lifecycle(cancel_at_period_end=True))
    C.initialize_verified_budget(limit_usd='7',existing_spend_usd='0',verified_at=C.now())
    C.reserve('user_1',1)
    W.handle_event('stripe',lifecycle('customer.subscription.deleted',400))
    assert W.handle_event('stripe',lifecycle(stamp=500))['status'] == 'stale'
    assert W.handle_event('stripe',invoice(event='after_cancel',stamp=600,invoice_id='in_2'))['status'] == 'held'
    with pytest.raises(C.CreditError): C.reserve('user_1',1)


def test_failed_payment_cannot_be_undone_by_older_paid_event(checkout):
    W.handle_event('stripe',bind()); W.handle_event('stripe',invoice())
    ev = lifecycle('invoice.payment_failed',400,subscription='sub_1')
    W.handle_event('stripe',ev)
    W.handle_event('stripe',invoice(event='late_invoice',stamp=300,invoice_id='in_2'))
    assert C.balance('user_1')['status'] == 'past_due'
    W.handle_event('stripe',invoice(event='recovered',stamp=500,invoice_id='in_3'))
    assert C.balance('user_1')['status'] == 'active'
    assert C.balance('user_1')['available'] == 10  # same cycle, no additional grant


@pytest.mark.parametrize('patch', [
    {'customer':'other'}, {'currency':'eur'}, {'amount_paid':1},
    {'lines':{'data':[]}}, {'paid':False},
])
def test_unverified_or_unpaid_invoice_never_grants(checkout,patch):
    W.handle_event('stripe',bind())
    event = invoice(); event['data']['object'].update(patch)
    try: W.handle_event('stripe',event)
    except C.CreditError: pass
    assert C.balance('user_1')['available'] == 0


def test_wrong_checkout_or_mode_cannot_bind_another_account(checkout):
    ev=bind(); ev['data']['object']['client_reference_id']='user_2'
    with pytest.raises(C.CreditError): W.handle_event('stripe',ev)
    ev=bind(); ev['livemode']=True
    with pytest.raises(C.CreditError): W.handle_event('stripe',ev)
    assert W.handle_event('stripe',bind())['status']=='bound'


def test_refund_revokes_unused_credits_and_preserves_consumed_history(checkout):
    W.handle_event('stripe',bind()); W.handle_event('stripe',invoice())
    C.initialize_verified_budget(limit_usd='7',existing_spend_usd='0',verified_at=C.now())
    C.reserve('user_1',1); C.consume_verified_export('user_1',1,'a'*64,'b'*64)
    event = {'id':'refund_1','type':'charge.refunded','created':500,'livemode':False,
        'data':{'object':{'id':'ch_1','customer':'cus_1','invoice':'in_1','refunded':True}}}
    assert W.enrolled_event('stripe',event)
    assert W.handle_event('stripe',event)['status']=='payment_hold'
    assert C.balance('user_1')['available']==0
    assert C.balance('user_1')['consumed']==1
    assert C.balance('user_1')['payment_hold']


def test_same_checkout_is_reused_and_price_outage_never_falls_through(checkout,monkeypatch):
    assert Q.start_checkout('user_1','first@example.test','stripe','starter')['checkout_url'].startswith('https://checkout.stripe.com/')
    assert checkout.call_count==1
    monkeypatch.setattr(Q.PR,'stripe_price',lambda _: (_ for _ in ()).throw(Q.PR.BillingProviderError('offline')))
    with pytest.raises(Q.PR.BillingProviderError): Q.start_checkout('user_2','second@example.test','stripe','starter')
    assert checkout.call_count==1


@pytest.mark.parametrize('url', ['http://checkout.stripe.com/a','https://checkout.stripe.com.attacker.test/a','https://user@checkout.stripe.com/a','https://checkout.stripe.com:444/a'])
def test_hosted_provider_urls_are_restricted(url):
    with pytest.raises(C.CreditError): Q.provider_url(url,'stripe')


def test_modern_stripe_invoice_subscription_and_price_fields(checkout):
    W.handle_event('stripe',bind())
    ev=invoice(); obj=ev['data']['object']; del obj['subscription']
    obj['parent']={'subscription_details':{'subscription':'sub_1'}}
    line=obj['lines']['data'][0]; del line['price']; line['pricing']={'price_details':{'price':'price_monthly'}}
    assert W.handle_event('stripe',ev)['status']=='credited'


@pytest.fixture
def lemon(wallet):
    with S._tx() as c:
        cur=c.execute('''INSERT INTO billing_subscriptions
            (account_ref,plan_id,billing_period,provider,status,price_cents,currency,metadata,created_at,updated_at)
            VALUES ('user_2','starter','monthly','lemon_squeezy','reserved',1900,'usd','{}',?,?)''',(C.now(),C.now()))
        row=cur.lastrowid
        c.execute('''INSERT INTO billing_account_state
            (account_ref,subscription_row,provider,allowance,test_mode,updated_at)
            VALUES ('user_2',?,'lemon_squeezy',3,1,?)''',(row,C.now()))
        c.execute('''INSERT INTO billing_checkout_claims
            (account_ref,subscription_row,provider,checkout_id,created_at)
            VALUES ('user_2',?,'lemon_squeezy','lemon_checkout',?)''',(row,C.now()))
    return row


def lemon_event(row,kind='subscription_created',stamp=None,**updates):
    at=stamp or datetime.now(timezone.utc)
    attrs={'customer_id':22,'status':'active','renews_at':(at+timedelta(days=28)).isoformat(),
        'created_at':at.isoformat(),'updated_at':at.isoformat(),'test_mode':True}
    attrs.update(updates)
    return {'meta':{'event_name':kind,'custom_data':{'account_ref':'user_2','subscription_row':str(row)}},
            'data':{'id':'lemon_sub','type':'subscriptions','attributes':attrs}}


def lemon_invoice(at,invoice_id='lemon_invoice',**updates):
    attrs={'customer_id':22,'subscription_id':'lemon_sub','status':'paid','billing_reason':'initial',
           'total':1900,'currency':'USD','refunded':False,'test_mode':True,'created_at':at.isoformat(),'updated_at':at.isoformat()}
    attrs.update(updates)
    return {'meta':{'event_name':'subscription_payment_success'},
            'data':{'id':invoice_id,'type':'subscription-invoices','attributes':attrs}}


def test_lemon_created_does_not_grant_and_distinct_cycles_do(lemon):
    at=datetime.now(timezone.utc)
    W.handle_event('lemon_squeezy',lemon_event(lemon,stamp=at))
    assert C.balance('user_2')['available']==0
    assert W.handle_event('lemon_squeezy',lemon_invoice(at))['status']=='credited'
    assert W.handle_event('lemon_squeezy',lemon_invoice(at))['status']=='duplicate'
    later=at+timedelta(days=28)
    W.handle_event('lemon_squeezy',lemon_event(lemon,'subscription_updated',later))
    assert W.handle_event('lemon_squeezy',lemon_invoice(later,'renewal',billing_reason='renewal'))['status']=='credited'
    # Future-dated fixture grant is not an actual provider transaction.
    assert C.balance('user_2')['available']==6


def test_lemon_failed_payment_retry_date_is_never_a_paid_credit_period(lemon):
    at=datetime.now(timezone.utc)
    W.handle_event('lemon_squeezy',lemon_event(lemon,stamp=at))
    W.handle_event('lemon_squeezy',lemon_invoice(at))
    renewal=at+timedelta(days=28)
    W.handle_event('lemon_squeezy',lemon_event(lemon,'subscription_updated',renewal,status='past_due',renews_at=(renewal+timedelta(days=1)).isoformat()))
    inv=lemon_invoice(renewal,'second_invoice',billing_reason='renewal')
    inv['meta']['event_name']='subscription_payment_recovered'
    with pytest.raises(C.CreditError,match='renewal period'): W.handle_event('lemon_squeezy',inv)
    W.handle_event('lemon_squeezy',lemon_event(lemon,'subscription_updated',renewal+timedelta(hours=1)))
    assert W.handle_event('lemon_squeezy',inv)['status']=='credited'
    # Paid event was older than the recovery update; lifecycle now reads active
    # from its previously paid state. No retry date was used for expiry.
    with S._tx() as c:
        grants=c.execute('SELECT expires_at FROM billing_credit_grants ORDER BY id').fetchall()
    assert grants[-1]['expires_at']==C.utc((renewal+timedelta(hours=1,days=28)).isoformat())


def test_lemon_wrong_checkout_row_never_binds(lemon):
    ev=lemon_event(lemon)
    ev['meta']['custom_data']['subscription_row']='999'
    with pytest.raises(C.CreditError): W.handle_event('lemon_squeezy',ev)
    assert C.balance('user_2')['available']==0
