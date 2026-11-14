"""Final customer bytes must satisfy the source text and photograph contract."""
import hashlib
import io
import json
import zipfile

import fitz
from PIL import Image
import pytest

from services.ebook_v2.final_quality import inspect
from services.ebook_v2.publishing import render_pdf, export_handler, export_valid
from services.ebook_v2.visuals import handler, prepare, Stock
from services.ebook_v2.worker import Repairable
from tests.ebook_v2_fixture import spec


def picture(root, color, name):
    stream=io.BytesIO();Image.new('RGB',(1800,1200),color).save(stream,'JPEG')
    data=stream.getvalue();(root/name).write_bytes(data)
    return {'file':{'key':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()},
            'width':1800,'height':1200,'provider':'Pexels','photographer':'QA fixture',
            'source_url':'https://www.pexels.com/photo/'+name,
            'license_url':'https://www.pexels.com/license/','alt':'Mechanical image fixture - not for sale'}


def illustrated(root):
    book=spec();book['require_photos']=True
    book['visuals']=[{'photo':picture(root,color,name),'overview':[]} for color,name in [('red','a.jpg'),('blue','b.jpg')]]
    return book


def test_source_text_and_actual_photo_pixels_are_verified(tmp_path):
    book=illustrated(tmp_path)
    pdf=render_pdf(book,root=tmp_path)
    report=inspect(pdf,book,tmp_path)
    assert report['source_text_present'] is True
    assert report['photographs_expected']==report['photographs_placed']==2
    assert report['photograph_pixels_verified'] is True
    assert report['designer_review']=='not_certified_by_mechanical_checks'


def test_missing_source_paragraph_blocks_final_pages(tmp_path):
    book=spec();pdf=render_pdf(book)
    book['chapters'][0]['text']+='\n\nThis source paragraph was lost during layout.'
    with pytest.raises(ValueError,match='missing manuscript text'):inspect(pdf,book,tmp_path)


def test_missing_promised_photographs_block_final_pages(tmp_path):
    pdf=render_pdf(spec())
    with pytest.raises(ValueError,match='missing promised photographs'):
        inspect(pdf,illustrated(tmp_path),tmp_path)


def test_different_photo_pixels_do_not_satisfy_expected_photograph(tmp_path):
    book=illustrated(tmp_path);pdf=render_pdf(book,root=tmp_path)
    book['visuals'][0]['photo']=picture(tmp_path,'green','substitute.jpg')
    with pytest.raises(ValueError,match='different photograph'):inspect(pdf,book,tmp_path)


def test_text_overlapping_a_chapter_photo_blocks_delivery(tmp_path):
    book=illustrated(tmp_path)
    with fitz.open(stream=render_pdf(book,root=tmp_path),filetype='pdf') as document:
        page=document[2];rect=fitz.Rect(page.get_image_info()[0]['bbox'])
        page.insert_text((rect.x0+10,rect.y0+30),'OVERLAP',fontsize=11)
        pdf=document.tobytes()
    with pytest.raises(ValueError,match='overlapping a photograph'):inspect(pdf,book,tmp_path)


@pytest.mark.parametrize('point,size,expected',[((4,100),11,'clipped text'),((70,100),4,'small text')])
def test_clipped_and_tiny_text_block_final_pages(tmp_path,point,size,expected):
    book=spec()
    with fitz.open(stream=render_pdf(book),filetype='pdf') as document:
        document[2].insert_text(point,'FAIL THIS PAGE',fontsize=size)
        pdf=document.tobytes()
    with pytest.raises(ValueError,match=expected):inspect(pdf,book,tmp_path)


def test_photo_required_book_cannot_finish_as_text_summaries(tmp_path,monkeypatch):
    for name in ('PEXELS_API_KEY','UNSPLASH_ACCESS_KEY','UNSPLASH_API_KEY'):monkeypatch.delenv(name,raising=False)
    monkeypatch.setattr(Stock,'request',lambda *a,**k:pytest.fail('No remote request is allowed'))
    book={**spec(),'require_photos':True}
    with pytest.raises(Repairable) as result:handler({'root':str(tmp_path),'book':book},'')
    assert result.value.code=='MISSING_PHOTOS'
    assert all(v['photo'] is None for v in result.value.candidate['visuals'])
    assert not list(tmp_path.glob('ebook-v2-media/*'))


def test_continue_reuses_completed_photograph_and_only_searches_missing_chapter(tmp_path,monkeypatch):
    photo=picture(tmp_path,'red','retained.jpg');queries=[]
    monkeypatch.setattr(Stock,'acquire',lambda self,query:queries.append(query))
    retained=[{'photo':photo,'overview':[]},{'photo':None,'overview':[]}]
    visuals=prepare(spec(),tmp_path,retained)
    assert visuals[0]['photo']==photo
    assert len(queries)==1
    assert visuals[1]['photo'] is None


def test_export_packs_quality_report_linked_to_exact_pdf_bytes(tmp_path):
    book=illustrated(tmp_path)
    output=export_handler({'root':str(tmp_path),'book':book},'')
    assert export_valid(output)
    with zipfile.ZipFile(tmp_path/output['files']['package.zip']['key']) as archive:
        report=json.loads(archive.read('quality-report.json'))
        assert report==output['page_quality']
        assert report['pdf_sha256']==hashlib.sha256(archive.read('ebook.pdf')).hexdigest()
    output['page_quality']['photographs_expected']=0
    assert not export_valid(output)


def test_one_repeated_photo_does_not_satisfy_distinct_photo_requirement(tmp_path):
    book=illustrated(tmp_path);book['visuals'][1]['photo']=book['visuals'][0]['photo']
    with pytest.raises(ValueError,match='distinct photographs'):
        inspect(render_pdf(book,root=tmp_path),book,tmp_path)


def test_missing_photos_preserve_chapters_and_resume_only_the_image_step(tmp_path,monkeypatch):
    from services.ebook_v2.books import Books
    for name in ('PEXELS_API_KEY','UNSPLASH_ACCESS_KEY','UNSPLASH_API_KEY'):monkeypatch.delenv(name,raising=False)
    books=Books(tmp_path/'studio.sqlite',tmp_path/'objects');books.initialize()
    book=books.create('alice','photo-recovery-contract-001',{**spec(),'require_photos':True})
    for _ in range(20):
        book=books.advance('alice',book['id'])
        if book['state']=='NEEDS_ATTENTION':break
    assert book['state']=='NEEDS_ATTENTION'
    assert 'photographs' in books.status('alice',book['id'])['attention']
    chapters=book['units'][:2]
    before=[books.units.get('alice',i) for i in chapters]
    failed=books.units.get('alice',book['units'][2])
    assert failed['error']=='MISSING_PHOTOS' and failed['attempts']==1
    assert all(row['state']=='COMPLETE' for row in before)
    resumed=books.resume('alice',book['id'],book['revision'])
    assert resumed['units'][:2]==chapters
    images=books.units.get('alice',resumed['units'][2])
    assert images['payload']['retained_visuals']==failed['output']['visuals']
    assert [books.units.get('alice',i) for i in chapters]==before
    assert not list((tmp_path/'objects').glob('ebook-v2/*/ebook.pdf'))
