from tests.test_subscriber_store import wallet
from datetime import date
from services.billing.provider_maintenance import report


def test_report_never_discloses_a_key_or_claims_live_balances(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY','secret-value-not-for-output')
    monkeypatch.setenv('FACTORY_ANTHROPIC_KEY_EXPIRES_ON','2026-10-20')
    r=report(date(2026,10,19))
    assert 'secret-value' not in str(r)
    row=next(x for x in r['providers'] if x['provider']=='anthropic')
    assert row['configured'] and row['alerts']==['renew_within_1_days']
    assert row['balance_source']=='unavailable' and r['network_calls']==0


def test_invalid_and_low_balance_observations_are_explicit(monkeypatch):
    monkeypatch.setenv('FACTORY_OPENAI_OBSERVED_BALANCE_USD','NaN')
    monkeypatch.setenv('FACTORY_OPENAI_KEY_EXPIRES_ON','bad-date')
    monkeypatch.setenv('FACTORY_TAVILY_OBSERVED_BALANCE_USD','2.50')
    rows={x['provider']:x for x in report()['providers']}
    assert 'invalid_balance_observation' in rows['openai']['alerts']
    assert 'invalid_expiry_date' in rows['openai']['alerts']
    assert 'low_balance' in rows['tavily']['alerts']
    assert rows['tavily']['balance_source']=='owner_recorded'


def test_observed_errors_store_only_sanitized_categories(wallet):
    from services.billing.provider_maintenance import record_failure,owner_report
    from services.billing import store as S
    assert record_failure(11,RuntimeError('401 invalid_api_key secret-should-never-be-stored'))
    assert record_failure(11,RuntimeError('401 invalid_api_key second-private-message'))
    with S._tx() as c:
        rows=c.execute('SELECT * FROM billing_service_notices').fetchall()
    assert len(rows)==1 and rows[0]['category']=='credentials'
    r=owner_report()
    assert len(r['notices'])==1 and 'secret-' not in str(r)
