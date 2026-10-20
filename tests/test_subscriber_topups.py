"""One-time purchases use isolated SQL and fixed merchant fixtures only."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import hashlib
import hmac
import json

import pytest
from services.billing import subscriber_topups as T, subscriber_store as C
from services.billing import store as S, subscriber_payments as W
from tests.test_subscriber_store import wallet, seed, budget


KEY = '00000000-0000-4000-8000-000000000001'


@pytest.fixture
def topups(wallet,monkeypatch):
    for k,v in {'FACTORY_SUBSCRIPTIONS_ENABLED':'1','FACTORY_TOPUPS_ENABLED':'1',
        'FACTORY_TOPUP_CREDITS':'3','FACTORY_TOPUP_PRICE_CENTS':'500',
        'LEMONSQUEEZY_TOPUP_VARIANT_ID':'42','LEMONSQUEEZY_STORE_ID':'9',
        'LEMONSQUEEZY_API_KEY':'fixture','LEMONSQUEEZY_WEBHOOK_SECRET':'fixture-signature',
        'FACTORY_BILLING_TEST_MODE':'1','FACTORY_PUBLIC_URL':'https://factory.example.test'}.items():
        monkeypatch.setenv(k,v)
    end=seed(quantity=1)
    with S._tx() as c:
        c.execute("UPDATE billing_account_state SET provider = 'lemon_squeezy', provider_customer_id = '12', test_mode = 1")
    monkeypatch.setattr(T.PR,'lemon_variant',lambda _: {'data':{'id':'42','attributes':{
        'is_subscription':False,'pay_what_you_want':False,'price':500}}})
    remote=Mock(return_value={'data':{'id':'checkout_topup','attributes':{
        'url':'https://tryme.lemonsqueezy.com/checkout/topup','store_id':9,'variant_id':42,
        'test_mode':True,'preview':{'currency':'USD','subtotal':500,'discount_total':0}}}})
    monkeypatch.setattr(T.PR,'_lemon_request',remote)
    return remote,end


def order(kind='order_created',order_id='101'):
    with S._tx() as c:
        claim=dict(c.execute('SELECT * FROM billing_topup_claims ORDER BY id DESC LIMIT 1').fetchone())
    return {'meta':{'event_name':kind,'custom_data':{'account_ref':claim['account_ref'],'topup_token':claim['token']}},
        'data':{'type':'orders','id':order_id,'attributes':{
            'created_at':C.now(),'updated_at':C.now(),'customer_id':12,'store_id':9,
            'user_email':'first@example.test','test_mode':True,'currency':'USD','subtotal':500,
            'discount_total':0,'total':550,'status':'paid','refunded':False,'refunded_amount':0,
            'first_order_item':{'variant_id':42,'price':500}}}}


def start():
    return T.checkout('user_1','first@example.test',KEY)


def test_one_checkout_grants_snapshot_once_and_never_changes_budget(topups,monkeypatch):
    remote,end=topups;budget()
    assert start()==start(); assert remote.call_count==1
    assert C.balance('user_1')['available']==1
    payload=remote.call_args.args[2]['data']['attributes']
    assert payload['product_options']['enabled_variants']==[42]
    assert payload['checkout_data']['variant_quantities']==[{'variant_id':42,'quantity':1}]
    assert payload['expires_at']==end and not payload['checkout_options']['discount']
    monkeypatch.setenv('FACTORY_TOPUP_CREDITS','99')
    event=order(); assert W.enrolled_event('lemon_squeezy',event)
    monkeypatch.setenv('FACTORY_TOPUPS_ENABLED','0');monkeypatch.setenv('FACTORY_SUBSCRIPTIONS_ENABLED','0')
    assert W.handle_event('lemon_squeezy',event)['status']=='topup_credited'
    assert W.handle_event('lemon_squeezy',event)['status']=='duplicate'
    other=deepcopy(event);other['data']['attributes']['updated_at']=C.now()
    assert W.handle_event('lemon_squeezy',other)['status']=='duplicate_topup'
    assert C.balance('user_1')['available']==4
    with S._tx() as c:
        assert c.execute('SELECT baseline_units FROM billing_business_budget').fetchone()['baseline_units']==0
        assert c.execute('SELECT COUNT(*) AS n FROM billing_budget_holds').fetchone()['n']==0


@pytest.mark.parametrize('patch',[
    {'customer_id':77},{'store_id':8},{'test_mode':False},{'test_mode':1},
    {'subtotal':1},{'discount_total':100},{'currency':'EUR'}, {'user_email':'other@example.test'},
    {'first_order_item':{'variant_id':43,'price':500}}, {'first_order_item':{'variant_id':42,'price':1}},
])
def test_mismatched_order_never_grants(topups,patch):
    start();event=order();event['data']['attributes'].update(patch)
    with pytest.raises(C.CreditError):W.handle_event('lemon_squeezy',event)
    assert C.balance('user_1')['available']==1
    with S._tx() as c:assert c.execute('SELECT COUNT(*) AS n FROM billing_subscriber_events').fetchone()['n']==0


def test_refund_before_payment_never_reactivates_or_grants(topups):
    start();paid=order();refund=deepcopy(paid);refund['meta']['event_name']='order_refunded'
    refund['data']['attributes'].update(refunded=True,refunded_amount=500,status='refunded')
    assert W.handle_event('lemon_squeezy',refund)['status']=='topup_refunded'
    assert W.handle_event('lemon_squeezy',paid)['status']=='held'
    assert C.balance('user_1')['available']==1 and C.balance('user_1')['payment_hold']


def test_partial_refund_without_custom_data_revokes_only_topup_and_preserves_files(topups):
    start();paid=order();W.handle_event('lemon_squeezy',paid);budget()
    C.reserve('user_1',99);C.consume_verified_export('user_1',99,'a'*64,'b'*64)
    refund=deepcopy(paid);refund['meta']={'event_name':'order_refunded'}
    refund['data']['attributes']['refunded_amount']=100
    assert W.enrolled_event('lemon_squeezy',refund)
    assert W.handle_event('lemon_squeezy',refund)['status']=='topup_refunded'
    assert C.balance('user_1')['available']==0  # original credit was consumed first
    assert C.balance('user_1')['consumed']==1
    assert C.reservation(99)['pdf_sha256']=='a'*64


def test_grant_fault_rolls_back_claim_receipt_and_credit(topups,monkeypatch):
    start();event=order();original=C.grant_in_transaction
    def fail(conn,**kw):original(conn,**kw);raise RuntimeError('isolated failure')
    monkeypatch.setattr(C,'grant_in_transaction',fail)
    with pytest.raises(RuntimeError):W.handle_event('lemon_squeezy',event)
    assert C.balance('user_1')['available']==1
    monkeypatch.setattr(C,'grant_in_transaction',original)
    assert W.handle_event('lemon_squeezy',event)['status']=='topup_credited'


def test_uncertain_checkout_is_held_without_repeat_request(topups):
    remote,_=topups;remote.side_effect=RuntimeError('timeout')
    with pytest.raises(RuntimeError):start()
    with pytest.raises(C.CreditError):start()
    assert remote.call_count==1


def test_simultaneous_clicks_make_only_one_remote_checkout(topups):
    remote,_=topups
    def attempt(_):
        try:return start()
        except C.CreditError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
    assert any(results) and remote.call_count==1


def test_disabled_unconfigured_unpaid_and_wrong_provider_fail_before_calls(topups,monkeypatch):
    remote,_=topups
    monkeypatch.setenv('FACTORY_TOPUPS_ENABLED','0')
    with pytest.raises(C.CreditError):start()
    monkeypatch.setenv('FACTORY_TOPUPS_ENABLED','1');monkeypatch.delenv('FACTORY_TOPUP_PRICE_CENTS')
    with pytest.raises(C.CreditError):start()
    monkeypatch.setenv('FACTORY_TOPUP_PRICE_CENTS','500')
    with S._tx() as c:c.execute("UPDATE billing_account_state SET status = 'past_due'")
    with pytest.raises(C.CreditError):start()
    assert remote.call_count==0


def test_checkout_preview_and_one_time_variant_must_match(topups,monkeypatch):
    remote,_=topups
    monkeypatch.setattr(T.PR,'lemon_variant',lambda _: {'data':{'id':'42','attributes':{'is_subscription':True,'price':500,'pay_what_you_want':False}}})
    with pytest.raises(C.CreditError):start()
    assert remote.call_count==0


def test_same_request_cannot_buy_twice_after_payment_and_identity_is_not_transferable(topups):
    remote,_=topups;start();event=order()
    wrong=deepcopy(event);wrong['meta']['custom_data']['account_ref']='user_2'
    with pytest.raises(C.CreditError):W.handle_event('lemon_squeezy',wrong)
    W.handle_event('lemon_squeezy',event)
    with pytest.raises(C.CreditError):start()
    assert remote.call_count==1


def test_signed_http_payment_boundary_and_session_identity(topups,monkeypatch,tmp_path):
    # Reuse the isolated SQL fixture for application routes and a real signed
    # webhook. A forged signature cannot reach the grant transaction.
    from app import app
    import database
    database.init_db()
    user=database.create_user('first@example.test','unused-hash')
    account='user_'+str(user['id'])
    with S._tx() as c:c.execute('UPDATE billing_account_state SET account_ref = ?', (account,))
    before=C.balance(account)['available']
    monkeypatch.setenv('FACTORY_ACCESS_MODE','accounts');monkeypatch.setenv('SECRET_KEY','x'*40)
    monkeypatch.setitem(app.config,'SECRET_KEY','x'*40)
    client=app.test_client()
    with client.session_transaction() as sess:sess['_user_id']=str(user['id']);sess['_fresh']=True
    response=client.post('/account/topup',json={'request_key':KEY,'account_ref':'user_999','email':'other@example.test','quantity':999})
    assert response.status_code==200
    event=order();assert event['meta']['custom_data']['account_ref']==account
    raw=json.dumps(event).encode()
    assert client.post('/billing/webhook/lemonsqueezy',data=raw,headers={'X-Signature':'forged'},content_type='application/json').status_code==400
    signature=hmac.new(b'fixture-signature',raw,hashlib.sha256).hexdigest()
    assert client.post('/billing/webhook/lemonsqueezy',data=raw,headers={'X-Signature':signature},content_type='application/json').status_code==200
    assert C.balance(account)['available']==before+3
    assert app.test_client().post('/account/topup',json={'request_key':KEY}).status_code==401


def test_phone_offer_discloses_terms_and_reuses_request_after_back_navigation(topups):
    from pathlib import Path
    from flask import render_template
    from app import app
    from playwright.sync_api import sync_playwright
    offered=T.customer_offer('user_1')
    with app.test_request_context('/'):
        html=render_template('subscriber_dashboard.html',credits=C.balance('user_1'),
            plan=None,providers=[],themes=[],app_version='test',topup=offered)
    script=Path('static/js/subscriber_dashboard.js').read_text()
    keys=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':390,'height':844})
        def fixture(route):
            path=route.request.url.split('factory.example.test')[-1]
            if path=='/account/topup':
                keys.append(route.request.post_data_json['request_key'])
                return route.fulfill(json={'checkout_url':'https://tryme.lemonsqueezy.com/checkout/fixture'})
            if path=='/account/subscription':return route.fulfill(json={'credits':C.balance('user_1'),'topup':offered})
            if path=='/projects':return route.fulfill(json=[])
            if path.startswith('/static/'):return route.fulfill(body=script,content_type='application/javascript')
            return route.fulfill(body=html,content_type='text/html')
        page.route('https://factory.example.test/**',fixture)
        page.route('https://tryme.lemonsqueezy.com/**',lambda r:r.fulfill(body='Fixture checkout',content_type='text/html'))
        page.goto('https://factory.example.test/')
        assert page.get_by_text('3 extra ebook credits for $5.00 USD',exact=False).is_visible()
        assert 'do not roll over or renew' in page.locator('#topupPanel').inner_text()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.get_by_role('button',name='Buy extra credits',exact=True).click()
        page.wait_for_url('https://tryme.lemonsqueezy.com/checkout/fixture')
        page.go_back();page.get_by_role('button',name='Buy extra credits',exact=True).click()
        page.wait_for_url('https://tryme.lemonsqueezy.com/checkout/fixture')
        assert len(keys)==2 and keys[0]==keys[1]
        assert C.balance('user_1')['available']==1
        browser.close()


def test_changed_offer_cannot_reuse_an_earlier_checkout(topups,monkeypatch):
    remote,_=topups;start()
    monkeypatch.setenv('FACTORY_TOPUP_CREDITS','9')
    assert T.customer_offer('user_1') is None
    with pytest.raises(C.CreditError,match='earlier offer'):start()
    assert remote.call_count==1


def test_returned_phone_checkout_waits_for_verified_credits_without_new_purchase(topups):
    from pathlib import Path
    from flask import render_template
    from app import app
    from playwright.sync_api import sync_playwright
    start();offered=T.customer_offer('user_1');event=order()
    with app.test_request_context('/'):
        html=render_template('subscriber_dashboard.html',credits=C.balance('user_1'),
            plan=None,providers=[],themes=[],app_version='test',topup=offered)
    count=[0]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':390,'height':844})
        def fixture(route):
            path=route.request.url.split('factory.example.test')[-1]
            if path=='/account/subscription':
                count[0]+=1
                if count[0]==3:W.handle_event('lemon_squeezy',event)
                return route.fulfill(json={'credits':C.balance('user_1'),'topup':T.customer_offer('user_1')})
            if path=='/projects':return route.fulfill(json=[])
            if path.startswith('/static/'):return route.fulfill(body=Path('static/js/subscriber_dashboard.js').read_text(),content_type='application/javascript')
            assert path.startswith('/?topup=returned')
            return route.fulfill(body=html,content_type='text/html')
        page.route('https://factory.example.test/**',fixture)
        page.goto('https://factory.example.test/?topup=returned')
        page.get_by_text('Checking your payment confirmation. Your existing credits are safe.',exact=True).wait_for()
        assert page.get_by_role('button',name='Buy extra credits').is_disabled()
        page.get_by_text('Payment verified. Your extra credits are ready.',exact=True).wait_for(timeout=15000)
        assert page.get_by_text('4 product credits available',exact=True).is_visible()
        assert page.url=='https://factory.example.test/'
        assert topups[0].call_count==1
        browser.close()
