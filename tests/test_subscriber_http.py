"""Real signed-session HTTP boundaries; payment transport uses fixed fixtures."""
import hashlib,hmac,json,time
from unittest.mock import Mock
import pytest
import database
from app import app
from services.billing import store as S,subscriber_store as C,subscriber_checkout as Q
from tests.test_subscriber_payments import bind,invoice


@pytest.fixture
def clients(tmp_path,monkeypatch):
    monkeypatch.setattr(database,'DB_PATH',str(tmp_path/'accounts.sqlite'))
    monkeypatch.setenv('FACTORY_DB_PATH',str(tmp_path/'accounts.sqlite'))
    monkeypatch.setenv('FACTORY_ACCESS_MODE','accounts')
    monkeypatch.setenv('FACTORY_SUBSCRIPTIONS_ENABLED','1')
    monkeypatch.setenv('FACTORY_SUBSCRIPTION_PLAN_ID','starter')
    monkeypatch.setenv('SECRET_KEY','subscriber-http-secret-longer-than-32-characters')
    monkeypatch.setitem(app.config,'SECRET_KEY','subscriber-http-secret-longer-than-32-characters')
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_fixture')
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_fixture')
    monkeypatch.setenv('STRIPE_PRICE_STARTER_MONTHLY','price_monthly')
    database.init_db();S.init_billing_db();C.init_schema()
    users=[database.create_user('first@example.test','unused-hash'),database.create_user('second@example.test','unused-hash'),database.create_user('owner@example.test','unused-hash','admin')]
    cs=[]
    for u in users:
        c=app.test_client()
        with c.session_transaction() as sess:sess['_user_id']=str(u['id']);sess['_fresh']=True
        cs.append(c)
    monkeypatch.setattr(Q.PR,'stripe_price',lambda _: {'active':True,'type':'recurring','billing_scheme':'per_unit','unit_amount':1900,'currency':'usd','recurring':{'interval':'month','interval_count':1}})
    remote=Mock(return_value={'id':'cs_fixture','url':'https://checkout.stripe.com/c/pay/fixture'})
    monkeypatch.setattr(Q.PR,'_stripe_request',remote)
    return users,cs,remote


def signed_post(event):
    raw=json.dumps(event,separators=(',',':')).encode();at=str(int(time.time()))
    signature=hmac.new(b'whsec_fixture',at.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    return app.test_client().post('/billing/webhook/stripe',data=raw,content_type='application/json',headers={'Stripe-Signature':f't={at},v1={signature}'})


def test_checkout_and_paid_webhooks_use_session_identity_and_block_cross_account(clients,monkeypatch):
    users,cs,remote=clients;customer='user_'+str(users[0]['id'])
    r=cs[0].post('/account/checkout',json={'provider':'stripe','plan_id':'starter','account_ref':'user_999','email':'attacker@example.test'})
    assert r.status_code==200
    data=remote.call_args.args[2]
    assert data['client_reference_id']==customer and data['customer_email']=='first@example.test'
    b=bind();b['data']['object']['client_reference_id']=customer
    assert signed_post(b).json['status']=='bound'
    assert cs[0].get('/account/subscription').json['credits']['available']==0
    # Public switches do not orphan a verified payment for a stored enrollment.
    monkeypatch.setenv('FACTORY_SUBSCRIPTIONS_ENABLED','0')
    assert signed_post(invoice()).json['status']=='credited'
    monkeypatch.setenv('FACTORY_SUBSCRIPTIONS_ENABLED','1')
    assert cs[0].get('/account/subscription?account_ref=user_999').json['credits']['available']==10
    assert cs[1].get('/account/subscription?account_ref='+customer).json['credits']['available']==0
    assert cs[0].post('/billing/account',json={}).status_code==403
    assert app.test_client().get('/account/subscription').status_code==401


def test_forged_payment_does_not_grant_or_create_a_receipt(clients):
    users,cs,_=clients
    cs[0].post('/account/checkout',json={'provider':'stripe','plan_id':'starter'})
    r=app.test_client().post('/billing/webhook/stripe',json=invoice(),headers={'Stripe-Signature':'t=1,v1=forged'})
    assert r.status_code==400
    assert C.balance('user_'+str(users[0]['id']))['available']==0


def test_dashboard_offers_only_ebook_and_manual_budget_or_other_generators_are_denied(clients):
    _,cs,_=clients
    html=cs[0].get('/').get_data(as_text=True)
    assert 'Create My Ebook' in html and 'Join monthly plan' in html and 'Saved books' in html
    assert 'crossword-builder' not in html and 'Faith Planner' not in html
    assert cs[0].get('/crossword-builder').status_code==403
    assert cs[0].post('/ebook-workspace/1/authorize-budget',json={'budget_cap_usd':100}).status_code==403
    assert cs[0].get('/admin/provider-maintenance').status_code==403
    assert cs[2].get('/admin/provider-maintenance').status_code==200
    public=app.test_client().get('/plans').get_data(as_text=True)
    assert 'completed ebooks' in public and 'Join free' not in public and 'Agency' not in public


def test_hosted_accounts_fail_closed_without_subscription_rollout(clients,monkeypatch):
    _,cs,_=clients
    monkeypatch.setenv('FACTORY_SUBSCRIPTIONS_ENABLED','0');monkeypatch.setenv('RENDER','true')
    assert cs[0].post('/ebook/build',json={'fields':{'topic':'gardening'}}).status_code==403


def test_unpaid_build_is_denied_before_provider_or_queue_work(clients,monkeypatch):
    users,cs,_=clients
    from services.jobs import dispatch
    handoff=Mock();monkeypatch.setattr(dispatch,'hand_off',handoff)
    response=cs[0].post('/ebook/build',json={'fields':{'topic':'container gardening','author_brand':'Test author','ebook_creation_mode':'ai_recommended'}})
    assert response.status_code==409
    assert 'paid billing period' in response.json['error']
    assert handoff.call_count==0
    assert C.balance('user_'+str(users[0]['id']))['consumed']==0
