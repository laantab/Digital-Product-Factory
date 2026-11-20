"""Exact-source patches preserve saved prose and still require independent review."""
import copy
import json

import pytest

from services.ebook_v2 import local_text, targeted_edit
from services.ebook_v2.worker import Repairable
from tests.test_ebook_v2_topics import developed_chapter,topic_spec


def test_multiple_edits_apply_to_original_offsets_without_cascading():
    chapter={'title':'Keep the title','text':'First exact sentence. Middle exact sentence. Last exact sentence.'}
    before=copy.deepcopy(chapter)
    actual=targeted_edit.apply(chapter,{'edits':[
        {'old':'Last exact sentence.','new':'First exact sentence.'},
        {'old':'First exact sentence.','new':'A revised beginning.'}]})
    assert actual=={'title':chapter['title'],'text':'A revised beginning. Middle exact sentence. First exact sentence.'}
    assert chapter==before


@pytest.mark.parametrize('response',[
    {'title':'A full rewrite','text':'Discarded manuscript.'},
    {'edits':[]},
    {'edits':[{'old':'Missing exact text.','new':'New sentence.'}]},
    {'edits':[{'old':'Repeated sentence.','new':'New sentence.'}]},
    {'edits':[{'old':'Original sentence.','new':'Original sentence.'}]},
    {'edits':[{'old':'Original sentence.','new':'New sentence.','extra':'ignored'}]},
    {'edits':[{'old':'Original sentence.','new':'A.'},{'old':'Original sentence. Repeated sentence.','new':'B.'}]},
    {'edits':[{'old':'Original sentence.','new':'x'*2401}]},
])
def test_ambiguous_stale_overlapping_or_unbounded_edits_are_refused(response):
    chapter={'title':'Original','text':'Original sentence. Repeated sentence. Repeated sentence.'}
    before=copy.deepcopy(chapter)
    with pytest.raises(Repairable):targeted_edit.apply(chapter,response)
    assert chapter==before


def test_invalid_patch_retains_source_and_findings_for_later_repair(monkeypatch):
    chapter=developed_chapter('Choose one clear working area')
    report={'checks':{k:False for k in local_text.CHECKS},'issues':['Clarify the next action.']}
    payload={'spec':topic_spec(),'chapter':chapter,'_recovery':{'chapter':chapter,'report':report}}
    before=copy.deepcopy(payload)
    monkeypatch.setattr(local_text,'generate',lambda *a,**kw:{'edits':[{'old':'Not in the saved source.','new':'Changed.'}]})
    with pytest.raises(Repairable) as failure:local_text.review_handler(payload,'apply_editorial_feedback')
    assert failure.value.code=='CONTENT_QUALITY'
    assert failure.value.candidate=={'chapter':chapter,'report':report} and payload==before


def test_small_correction_has_bounded_output_and_cannot_auto_approve(monkeypatch):
    chapter=developed_chapter('Choose one clear working area')
    chapter['text']+='\n\nStack two air mattresses in the hallway.'
    issues=local_text.chapter_issues(chapter)
    previous={'chapter':chapter,'report':{'issues':issues,'checks':{k:False for k in local_text.CHECKS}}}
    payload={'spec':topic_spec(),'chapter':chapter,'_recovery':previous}
    calls=[]
    response={'edits':[{'old':'Stack two air mattresses in the hallway.','new':'Keep hallways and exits clear. Use an available bed in its intended configuration.'}]}
    def generate(prompt,schema,repair='',**kwargs):
        calls.append((schema,kwargs))
        return response
    monkeypatch.setattr(local_text,'generate',generate)
    with pytest.raises(Repairable) as pending:local_text.review_handler(payload,'apply_editorial_feedback')
    result=pending.value.candidate
    assert pending.value.code=='EDITORIAL_RECHECK' and result['awaiting_review'] is True
    assert result['chapter']['text']==chapter['text'].replace('Stack two air mattresses in the hallway.','Keep hallways and exits clear. Use an available bed in its intended configuration.')
    assert not local_text.review_valid(result) and not local_text.chapter_issues(result['chapter'])
    assert len(calls)==1 and calls[0][1]['max_tokens']==1800
    assert len(json.dumps(response))<300
