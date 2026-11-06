"""Fresh local-only engineering acceptance; never uses an existing customer DB."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from threading import Event,Thread
import uuid
import zipfile
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def save(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2),encoding='utf-8')
    temporary.replace(path)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',required=True)
    parser.add_argument('--chapters',type=int,default=8)
    parser.add_argument('--min-words',type=int,default=650)
    parser.add_argument('--deadline',type=int,default=5400)
    args=parser.parse_args()
    root=Path(args.data).resolve()
    if root.exists() and any(root.iterdir()):parser.error('Acceptance requires a fresh empty directory')
    root.mkdir(parents=True,exist_ok=True)
    os.environ.update(FACTORY_TEST_MODE='1',FACTORY_DB_BACKEND='sqlite',
        FACTORY_DB_PATH=str(root/'qa.sqlite'),DATABASE_URL='',
        OPENAI_API_KEY='',ANTHROPIC_API_KEY='',TAVILY_API_KEY='',
        AI_INTEGRATIONS_OPENAI_API_KEY='',PEXELS_API_KEY='',
        UNSPLASH_ACCESS_KEY='',UNSPLASH_API_KEY='')
    from services.ebook_v2.books import Books
    from services.ebook_v2.local_text import ready,review_valid
    from services.ebook_v2.topics import data
    from services.ebook_v2.publishing import export_valid
    from services.ebook_v2.manuscript import inspect as inspect_word
    paths=sorted((ROOT/'services'/'ebook_v2').glob('*.py'))
    before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    if not ready():raise RuntimeError('Install and start the selected local model before acceptance')
    books=Books(root/'qa.sqlite',root/'objects');books.initialize()
    spec={'source':'ollama','topic':'Organizing a simple weekly plan for a small volunteer team',
        'audience':'Coordinators of small community volunteer groups',
        'outcome':'Create a clear weekly task list and run a short progress check-in',
        'author':'Engineering acceptance fixture','chapter_count':args.chapters,
        'min_words':args.min_words,'mode':'automatic','research_acknowledged':True}
    owner='engineering-acceptance'
    book=books.create(owner,'fresh-'+uuid.uuid4().hex,spec)
    stopped=Event()
    def heartbeat():
        while not stopped.is_set():
            books.record_worker('acceptance',local_text=True)
            stopped.wait(3)
    monitor=Thread(target=heartbeat,daemon=True);monitor.start()
    marker=None;deadline=time.monotonic()+args.deadline
    try:
        while time.monotonic()<deadline:
            book=books.get(owner,book['id']);view=books.status(owner,book['id'])
            save(root/'status.json',view)
            current=(view['state'],view.get('activity'),view.get('words_saved'),view['chapters_checked'])
            if marker!=current:print('ACTUAL_LOCAL_PROGRESS',json.dumps(current),flush=True);marker=current
            if book['state']=='READY':break
            if book['state']=='NEEDS_ATTENTION':
                with books.units.transaction() as conn:
                    failures=[dict(row) for row in conn.execute(
                        "SELECT stage,state,attempts,error FROM ebook_v2_units WHERE owner=? AND state='NEEDS_ATTENTION'",(owner,))]
                save(root/'failure.json',{'status':view,'units':failures})
                raise RuntimeError('Fresh generation needs attention; saved work was retained')
            if book['state']=='WAITING_TITLE':books.decide(owner,book['id'],book['revision'],'title',view['titles'][0])
            elif book['state']=='WAITING_COVER':books.decide(owner,book['id'],book['revision'],'cover','editorial')
            elif book['state']=='RUNNING':books.advance(owner,book['id'])
            else:raise RuntimeError('Unexpected engineering acceptance state')
            stopped.wait(.15)
        else:raise RuntimeError('Fresh acceptance deadline reached')
        state=data(books,book)
        chapters=[]
        for index in range(args.chapters):
            unit=books.units.get(owner,state['units'][f'review:{index}'])
            assert unit['state']=='COMPLETE' and review_valid(unit['output'])
            chapter=unit['output']['chapter']
            assert len(chapter['text'].split())>=args.min_words
            chapters.append(chapter)
        exported=books.units.get(owner,state['units']['export'])
        assert exported['state']=='COMPLETE' and export_valid(exported['output'])
        assert exported['payload']['book']['chapters']==chapters
        checksums={}
        for name in exported['output']['files']:
            payload,checksum=books.download(owner,book['id'],name)
            assert hashlib.sha256(payload).hexdigest()==checksum
            (root/name).write_bytes(payload);checksums[name]=checksum
        inspect_word((root/'manuscript.docx').read_bytes(),exported['payload']['book'])
        with zipfile.ZipFile(root/'ebook.epub') as archive:
            ns={'h':'http://www.w3.org/1999/xhtml'}
            for index,chapter in enumerate(chapters,1):
                document=ET.fromstring(archive.read(f'EPUB/chapter-{index}.xhtml'))
                paragraphs=document.findall('h:body/h:section/h:p',ns)
                text=[(p.text or '')+''.join('\n'+(node.tail or '') for node in p) for p in paragraphs]
                assert text==chapter['text'].split('\n\n')
        import fitz
        with fitz.open(root/'ebook.pdf') as document:
            for index,page in enumerate(document):
                assert page.get_text().strip()
                for block in page.get_text('dict')['blocks']:
                    for line in block.get('lines',[]):
                        for span in line['spans']:
                            x0,y0,x1,y1=span['bbox']
                            assert x0>=-1 and y0>=-1 and x1<=page.rect.width+1 and y1<=page.rect.height+1
                            if index and span['size']>9:assert y1<=605
                page.get_pixmap(matrix=fitz.Matrix(1,1),alpha=False).save(str(root/f'page-{index+1}.png'))
            pages=len(document)
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        assert before==after
        with books.units.transaction() as conn:
            units=[dict(row) for row in conn.execute(
                'SELECT stage,state,attempts,error,policy FROM ebook_v2_units WHERE owner=?',(owner,))]
            lessons=[dict(row) for row in conn.execute(
                'SELECT stage,policy,error,repair,successes FROM ebook_v2_lessons')]
        summary={'result':'technical acceptance complete; human text and rendered-page review still required',
            'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'runtime_source_sha256':before,'chapter_count':len(chapters),
            'chapter_words':[len(ch['text'].split()) for ch in chapters],
            'pages':pages,'file_sha256':checksums,'units':units,'validated_repair_lessons':lessons,
            'default_size':args.chapters==8 and args.min_words==650,
            'model':os.environ.get('FACTORY_V2_OLLAMA_MODEL','qwen3:8b'),
            'paid_generation_calls':0,'market_demand':'unassessed','external_fact_originality_certification':False}
        save(root/'summary.json',summary)
        print('TECHNICAL_LOCAL_ACCEPTANCE',json.dumps(summary),flush=True)
        print('BEGIN ENGINEERING MANUSCRIPT NOT FOR SALE',flush=True)
        print((root/'manuscript.md').read_text(encoding='utf-8'),flush=True)
        print('END ENGINEERING MANUSCRIPT NOT FOR SALE',flush=True)
    finally:
        stopped.set();monitor.join(4)


if __name__=='__main__':main()
