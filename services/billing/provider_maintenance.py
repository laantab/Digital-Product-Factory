"""Secret-free, network-free owner observations; never a provider health claim."""
import os
from datetime import date
from decimal import Decimal, InvalidOperation

PROVIDERS={
    'openai':('OPENAI_API_KEY','AI_INTEGRATIONS_OPENAI_API_KEY'),
    'anthropic':('ANTHROPIC_API_KEY',),'tavily':('TAVILY_API_KEY',),
    'pexels':('PEXELS_API_KEY',),'unsplash':('UNSPLASH_ACCESS_KEY',),
    'pixabay':('PIXABAY_API_KEY',),'stripe':('STRIPE_SECRET_KEY',),
    'lemon_squeezy':('LEMONSQUEEZY_API_KEY',),
}


def report(today=None):
    today=today or date.today()
    rows=[]
    for provider,keys in PROVIDERS.items():
        prefix='FACTORY_'+provider.upper()
        alerts=[]; days=None; balance=None
        expiry=os.environ.get(prefix+'_KEY_EXPIRES_ON','')
        if expiry:
            try:
                days=(date.fromisoformat(expiry)-today).days
                if days<=30:
                    band=next((n for n in (1,7,14,30) if days<=n),30)
                    alerts.append('expired' if days<0 else f'renew_within_{band}_days')
            except ValueError: alerts.append('invalid_expiry_date')
        raw=os.environ.get(prefix+'_OBSERVED_BALANCE_USD','')
        if raw:
            try:
                v=Decimal(raw); threshold=Decimal(os.environ.get(prefix+'_LOW_BALANCE_USD','5'))
                if not v.is_finite() or not threshold.is_finite() or min(v,threshold)<0:
                    raise ValueError()
                balance=str(v)
                if v<=threshold: alerts.append('low_balance')
            except (ValueError,InvalidOperation): alerts.append('invalid_balance_observation')
        rows.append({'provider':provider,'configured':any(bool(os.environ.get(k)) for k in keys),
            'expiry_known':days is not None,'days_until_expiry':days,
            'observed_balance_usd':balance,'balance_source':'owner_recorded' if balance is not None else 'unavailable',
            'balance_observed_on':os.environ.get(prefix+'_BALANCE_OBSERVED_ON',''),'alerts':alerts})
    return {'checked_on':today.isoformat(),'network_calls':0,'providers':rows}


NOTICE_MESSAGES={
    'credentials':'A recent AI service request reported a credentials problem.',
    'balance':'A recent AI service request reported a billing or quota problem.',
    'availability':'A recent AI service request was temporarily unavailable.',
    'accounting':'A finished book is waiting for credit accounting to recover.',
    'payments':'A payment notification needs review; customer progress is preserved.',
}


def record_failure(project_id,error,category=None):
    from datetime import datetime,timedelta,timezone
    from services.billing import store as S
    if category is None:
        text=(type(error).__name__+' '+str(error)).lower()
        if any(x in text for x in ('401','authentication','unauthorized','invalid_api_key')):category='credentials'
        elif any(x in text for x in ('402','insufficient_quota','insufficient balance','credit balance')):category='balance'
        elif any(x in text for x in ('timeout','connectionerror','connection refused','service unavailable','rate limit')):category='availability'
    if category not in NOTICE_MESSAGES:return False
    at=datetime.now(timezone.utc)
    with S._tx() as c:
        if not c.execute('SELECT id FROM billing_service_notices WHERE project_id = ? AND category = ? AND observed_at > ?',
                         (int(project_id),category,(at-timedelta(hours=1)).isoformat())).fetchone():
            c.execute('INSERT INTO billing_service_notices (project_id,category,observed_at) VALUES (?, ?, ?)',
                      (int(project_id),category,at.isoformat()))
    return True


def owner_report():
    from datetime import datetime,timedelta,timezone
    from services.billing import store as S
    payload=report()
    try:
        with S._tx() as c:
            since=(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()
            rows=c.execute('SELECT category,observed_at FROM billing_service_notices WHERE observed_at > ? ORDER BY id DESC LIMIT 10',(since,)).fetchall()
            payload['notices']=[{'message':NOTICE_MESSAGES[r['category']],'observed_at':r['observed_at']} for r in rows if r['category'] in NOTICE_MESSAGES]
            payload['billing_review_count']=c.execute('SELECT COUNT(*) AS n FROM billing_account_state WHERE payment_hold = 1').fetchone()['n']
        payload['notice_status']='available'
    except Exception:
        payload.update(notices=[],billing_review_count=None,notice_status='unavailable')
    return payload
