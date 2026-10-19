"""Real subscriber phone journey, local deterministic providers, exact downloads."""
import json,sqlite3,zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path


def test_subscriber_phone_build_cover_choice_download_and_reopen(monkeypatch,tmp_path):
    from tests.test_ebook_real_browser_customer_path import EbookRealBrowserCustomerPathTests as server
    monkeypatch.setenv('FACTORY_ACCESS_MODE','accounts')
    monkeypatch.setenv('FACTORY_SUBSCRIPTIONS_ENABLED','1')
    monkeypatch.setenv('SECRET_KEY','subscriber-browser-test-key-with-32-characters')
    server.setUpClass()
    context=server()._new_context(accept_downloads=True)
    try:
        r=context.request.post(server.base+'/auth/register',data={'email':'subscriber@example.test','password':'Disposable-test-password'})
        assert r.status==201
        uid=r.json()['user']['id'];customer='user_'+str(uid)
        at=datetime.now(timezone.utc).isoformat();end=(datetime.now(timezone.utc)+timedelta(days=28)).isoformat()
        with sqlite3.connect(server.db_path) as c:
            c.execute('INSERT INTO billing_business_budget (id,limit_units,baseline_units,verified_at) VALUES (1,7000000,0,?)',(at,))
            c.execute('''INSERT INTO billing_account_state
                (account_ref,subscription_row,provider,allowance,status,period_end,updated_at)
                VALUES (?,1,'stripe',1,'active',?,?)''',(customer,end,at))
            c.execute('''INSERT INTO billing_credit_grants
                (account_ref,receipt,cycle_key,quantity,expires_at,created_at)
                VALUES (?,'verified-test-invoice','test-paid-period',1,?,?)''',(customer,end,at))
        page=context.new_page();page.set_viewport_size({'width':390,'height':844})
        page.goto(server.base)
        page.get_by_text('1 product credit available',exact=True).wait_for()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('#topic').fill('container gardening for beginners')
        page.locator('#author').fill('Test Subscriber')
        page.locator('#createBook').click()
        page.get_by_role('button',name='Use this cover and finish').first.wait_for(timeout=180000)
        # Title/cover remains the one deliberate decision; saved progress
        # survives refreshing the phone before that choice is confirmed.
        page.reload()
        page.get_by_role('button',name='Use this cover and finish').first.wait_for(timeout=30000)
        page.get_by_role('button',name='Use this cover and finish').first.click()
        page.get_by_role('link',name='Download PDF',exact=True).wait_for(timeout=180000)
        with page.expect_download() as pdf_dl:page.get_by_role('link',name='Download PDF',exact=True).click()
        with page.expect_download() as zip_dl:page.get_by_role('link',name='Download ZIP',exact=True).click()
        pdf=Path(pdf_dl.value.path()).read_bytes()
        with zipfile.ZipFile(zip_dl.value.path()) as z:
            assert z.testzip() is None and z.read('ebook.pdf')==pdf
        page.reload()
        page.get_by_role('link',name='Download PDF',exact=True).wait_for(timeout=30000)
        balance=context.request.get(server.base+'/account/subscription').json()['credits']
        assert balance['available']==0 and balance['consumed']==1
        with sqlite3.connect(server.db_path) as c:
            assert c.execute('SELECT COUNT(*) FROM billing_credit_reservations').fetchone()[0]==1
            assert c.execute('SELECT COUNT(*) FROM projects').fetchone()[0]==1
        assert json.loads(server.call_log.read_text())=={'paid':0,'pexels_http':0}
        page.screenshot(path=str(tmp_path/'subscriber-phone.png'),full_page=True)
    finally:
        context.close();server.tearDownClass()
