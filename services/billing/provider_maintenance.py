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
