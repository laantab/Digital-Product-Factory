"""Small opt-in subscriber surface. Existing private owner tools stay intact."""
from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user
from werkzeug.exceptions import Forbidden, Unauthorized

from services.billing import subscriber_checkout as Q, subscriber_store as C

bp=Blueprint('subscriber',__name__)


def identity():
    from services.project_access import accounts_mode
    if not accounts_mode() or not Q.enabled():
        raise Forbidden('Subscriptions are not available yet.')
    if not current_user.is_authenticated or not current_user.is_active:
        raise Unauthorized('Please sign in.')
    return C.account('user_'+str(current_user.id))


@bp.get('/account/subscription')
def subscription():
    customer=identity()
    return jsonify(credits=C.balance(customer))


@bp.post('/account/checkout')
def checkout():
    customer=identity(); body=request.get_json(silent=True) or {}
    try:
        return jsonify(Q.start_checkout(customer,current_user.email,
            str(body.get('provider') or ''),str(body.get('plan_id') or ''),str(body.get('billing_period') or 'monthly')))
    except C.CreditError as e:
        return jsonify(ok=False,error=str(e)),409
    except Exception:
        return jsonify(ok=False,error='Checkout is temporarily unavailable. Please try again or contact support.'),503


@bp.post('/account/portal')
def portal():
    customer=identity()
    try:
        return jsonify(url=Q.portal(customer))
    except C.CreditError as e:
        return jsonify(ok=False,error=str(e)),409
    except Exception:
        return jsonify(ok=False,error='Subscription management is temporarily unavailable.'),503


@bp.get('/admin/provider-maintenance')
def maintenance():
    from services.billing.provider_maintenance import owner_report
    if not current_user.is_authenticated or not current_user.is_active:
        raise Unauthorized('Please sign in.')
    if not current_user.is_admin:
        raise Forbidden('Administrator access required.')
    return jsonify(owner_report())


def dashboard():
    customer=identity()
    try:
        offer=Q.selected_plan()
        plan={'id':offer.id,'price':offer.monthly_display if hasattr(offer,'monthly_display') else offer.as_dict()['monthly_display'],
              'quantity':offer.products_per_month}
    except ValueError:
        plan=None
    from services.billing import providers as PR
    providers=PR.configured_providers() if plan else []
    from services.ebook_design_export import theme_catalog_payload
    themes=theme_catalog_payload()['themes']
    return render_template('subscriber_dashboard.html',credits=C.balance(customer),plan=plan,providers=providers,themes=themes)


@bp.app_context_processor
def owner_notices():
    if not current_user.is_authenticated or not current_user.is_active or not current_user.is_admin:
        return {}
    from services.billing.provider_maintenance import owner_report
    return {'provider_maintenance':owner_report()}
