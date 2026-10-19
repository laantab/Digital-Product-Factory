"""Bridge subscriber accounting to the existing ebook orchestrator.

Enrollment is persisted before queueing. Workers honor stored enrollment even
if their public rollout switches differ from the website. A failed credit write
after export is recovered by settlement, never by rendering the book again.
"""
import hashlib
import io
import os
import re
import zipfile

from services.billing import subscriber_store as C, subscriber_checkout as Q

MARKER = '_subscription_account'


def request_customer():
    from flask import has_request_context
    if not has_request_context():
        return None
    from services.project_access import accounts_mode
    from flask_login import current_user
    if not accounts_mode() or not current_user.is_authenticated or current_user.is_admin:
        return None
    if not Q.enabled():
        raise C.CreditError('Subscription building is not available yet.')
    return C.account('user_'+str(current_user.id))


def enroll(project):
    customer = request_customer()
    if not customer:
        return project
    import database
    pid = int(project['id'])
    if database.get_project_owner(pid) != int(customer.split('_')[1]):
        raise C.CreditError('Project not found.')
    data = dict(project.get('data') or {})
    from services.ebook_build_orchestrator import next_incomplete_stage
    if next_incomplete_stage(data) is None:
        return project  # Previously finished downloads do not cost a new credit.
    if data.get(MARKER) and data[MARKER] != customer:
        raise C.CreditError('This build belongs to another account.')
    if not data.get(MARKER):
        data[MARKER] = customer
        project = database.update_project(pid,None,data) or project
    # Conservative ceiling matches the existing server-created workspace;
    # subscriber request fields cannot increase that authorization.
    C.reserve(customer,pid)
    return project


def enrolled_account(project_id, data):
    customer = data.get(MARKER)
    if not customer:
        return None
    import database
    C.account(customer)
    if database.get_project_owner(int(project_id)) != int(customer.split('_')[1]):
        raise C.CreditError('The enrolled build owner does not match.')
    C.init_schema()
    return customer


def before_advance(project_id, data):
    customer = enrolled_account(project_id,data)
    if not customer:
        return
    # A completed export with a reserved credit is accounting recovery only.
    from services.ebook_build_orchestrator import next_incomplete_stage
    if next_incomplete_stage(data) is None:
        settle(project_id,data)
    else:
        C.reserve(customer,int(project_id))


def settle(project_id, data):
    customer = enrolled_account(project_id,data)
    if not customer:
        return False
    from services.ebook_revision_identity import approvals_match_current_revision, customer_download_refs
    from services.ebook_build_orchestrator import next_incomplete_stage
    from services.storage.compat import read_export_or_legacy
    if next_incomplete_stage(data) is not None:
        raise C.CreditError('The current ebook revision has not passed release checks.')
    approved, _ = approvals_match_current_revision(data)
    if not approved:
        raise C.CreditError('The exported files do not match current approvals.')
    refs=customer_download_refs(data)
    package=refs['package_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',package):
        raise C.CreditError('The current export identity is invalid.')
    pdf=read_export_or_legacy(project_id,package+'/ebook.pdf',refs['pdf_path'])
    bundle=read_export_or_legacy(project_id,package+'/package.zip',refs['zip_path'])
    if not pdf or not bundle or not pdf.startswith(b'%PDF'):
        raise C.CreditError('Verified PDF and ZIP files are required.')
    try:
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            names=archive.namelist()
            if names.count('ebook.pdf')!=1 or archive.testzip() is not None or archive.read('ebook.pdf')!=pdf:
                raise C.CreditError('The ZIP does not contain the verified PDF.')
    except (zipfile.BadZipFile,KeyError,RuntimeError):
        raise C.CreditError('The ZIP could not be verified.') from None
    return C.consume_verified_export(customer,project_id,hashlib.sha256(pdf).hexdigest(),hashlib.sha256(bundle).hexdigest())


def release_failed(project_id,data):
    customer=enrolled_account(project_id,data)
    if customer:
        return C.release(customer,project_id)
    return False


def account_status(payload, data, project_id):
    if not data.get(MARKER):
        return payload
    row=C.reservation(project_id)
    pending=not row or row['status']!='consumed'
    payload['accounting_pending']=bool(pending and payload.get('finished'))
    if payload['accounting_pending']:
        payload.update(finished=False,percent=min(99,int(payload.get('percent') or 0)),
            downloads={'pdf':None,'zip':None},message='Your files are saved. Finishing credit accounting; Continue safely retries this step.')
    return payload
