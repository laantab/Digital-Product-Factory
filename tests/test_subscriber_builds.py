"""Credit settlement requires the exact current PDF/ZIP, never render success alone."""
import io
import hashlib
import zipfile
import pytest
from tests.test_subscriber_store import wallet,seed,budget
from services.billing import subscriber_store as C,subscriber_builds as B


def bundle(pdf):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:z.writestr('ebook.pdf',pdf)
    return out.getvalue()


@pytest.fixture
def exported(wallet,monkeypatch):
    import database
    from services import ebook_build_orchestrator as O,ebook_revision_identity as R
    from services.storage import compat
    seed();budget();C.reserve('user_1',1)
    monkeypatch.setattr(database,'get_project_owner',lambda _:1)
    monkeypatch.setattr(O,'next_incomplete_stage',lambda _:None)
    monkeypatch.setattr(R,'approvals_match_current_revision',lambda _:(True,[]))
    monkeypatch.setattr(R,'customer_download_refs',lambda _:{'package_id':'book','pdf_path':'book/ebook.pdf','zip_path':'book/package.zip'})
    pdf=b'%PDF-fixture-exact-accepted-bytes'
    monkeypatch.setattr(compat,'read_export_or_legacy',lambda pid,path,legacy:pdf if path.endswith('ebook.pdf') else bundle(pdf))
    return {B.MARKER:'user_1','artifact_revision':1,'ebook_export_identity':{'pdf_sha256':hashlib.sha256(pdf).hexdigest(),'zip_sha256':hashlib.sha256(bundle(pdf)).hexdigest(),'verified_at_revision':1}},O,R,compat


def test_only_verified_files_settle_and_repeated_reopen_is_free(exported):
    data,_,_,_=exported
    assert B.settle(1,data)
    assert not B.settle(1,data)
    assert C.balance('user_1')['consumed']==1


def test_mismatched_pdf_inside_zip_preserves_reserved_credit(exported,monkeypatch):
    data,_,_,compat=exported
    monkeypatch.setattr(compat,'read_export_or_legacy',lambda pid,path,legacy:b'%PDF-current' if path.endswith('ebook.pdf') else bundle(b'%PDF-old'))
    with pytest.raises(C.CreditError,match='ZIP'):B.settle(1,data)
    assert C.reservation(1)['status']=='reserved'


def test_stale_approval_or_incomplete_stage_never_consumes(exported,monkeypatch):
    data,O,R,_=exported
    monkeypatch.setattr(O,'next_incomplete_stage',lambda _:'export')
    with pytest.raises(C.CreditError,match='release checks'):B.settle(1,data)
    monkeypatch.setattr(O,'next_incomplete_stage',lambda _:None)
    monkeypatch.setattr(R,'approvals_match_current_revision',lambda _:(False,['stale']))
    with pytest.raises(C.CreditError,match='approvals'):B.settle(1,data)
    assert C.balance('user_1')['consumed']==0


def test_credit_database_outage_after_export_only_retries_accounting(exported,monkeypatch):
    data,_,_,_=exported
    original=C.consume_verified_export
    monkeypatch.setattr(C,'consume_verified_export',lambda *a:(_ for _ in ()).throw(RuntimeError('credit database outage')))
    with pytest.raises(RuntimeError):B.before_advance(1,data)
    assert C.reservation(1)['status']=='reserved'
    monkeypatch.setattr(C,'consume_verified_export',original)
    B.before_advance(1,data)
    assert C.reservation(1)['status']=='consumed'


def test_wrong_owner_and_missing_checksums_never_deduct(exported,monkeypatch):
    import database
    data,_,_,_=exported
    monkeypatch.setattr(database,'get_project_owner',lambda _:2)
    with pytest.raises(C.CreditError,match='owner'):B.settle(1,data)
    with pytest.raises(C.CreditError,match='checksums'):C.consume_verified_export('user_1',1,'','')


def test_completed_files_are_not_labeled_ready_until_credit_settlement(exported):
    data,_,_,_=exported
    b=B.account_status({'finished':True,'percent':100,'downloads':{'pdf':'p','zip':'z'}},data,1)
    assert b['accounting_pending'] and not b['finished'] and b['percent']==99
    assert b['downloads']=={'pdf':None,'zip':None}
    B.settle(1,data)
    b=B.account_status({'finished':True},data,1)
    assert b['finished'] and not b['accounting_pending']



def test_stored_asset_from_an_earlier_revision_never_consumes(exported,monkeypatch):
    data,_,_,compat=exported
    older=b'%PDF-prior-export'
    monkeypatch.setattr(compat,'read_export_or_legacy',lambda pid,path,legacy:older if path.endswith('ebook.pdf') else bundle(older))
    with pytest.raises(C.CreditError,match='export revision'):B.settle(1,data)
    assert C.reservation(1)['status']=='reserved'
