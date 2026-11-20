"""Known buyer-facing defects cannot be approved by an agreeable model."""
import copy

import pytest

from services.ebook_v2 import local_text
from services.ebook_v2.editorial_contract import chapter_issues
from services.ebook_v2.publishing import export_handler
from services.ebook_v2.worker import Repairable
from tests.test_ebook_v2_topics import developed_chapter, topic_spec
from tests.ebook_v2_fixture import spec


@pytest.mark.parametrize('defect',[
    'Use the checklists provided to prepare each room.',
    'Stack folding tables in the living room to create a dining area.',
    'Stack two air mattresses in the hallway.',
    'Another option is to use an air mattress in a living room or hallway.',
])
def test_approving_model_cannot_override_independent_findings(monkeypatch,defect):
    chapter=developed_chapter('Choose one clear working area')
    chapter['text']+='\n\n'+defect
    monkeypatch.setattr(local_text,'generate',lambda *a,**kw:{'checks':{k:True for k in local_text.CHECKS},'issues':[]})
    with pytest.raises(Repairable) as failure:
        local_text.review_handler({'spec':topic_spec(),'chapter':chapter},'')
    assert failure.value.code=='EDITORIAL_FINDINGS'
    assert not local_text.review_valid(failure.value.candidate)


def test_concrete_checklist_satisfies_promised_tool_without_rewriting_source():
    chapter={'title':'Final preparation','text':'Use the checklist below.\n\nCheck: Clear a path through the entryway.\nCheck: Set out the clean towels you already own.\nCheck: Confirm the guest has a place for belongings.'}
    original=copy.deepcopy(chapter)
    assert chapter_issues(chapter)==[] and chapter==original


def test_internal_title_label_is_rejected_but_hypothetical_prose_is_allowed():
    assert not local_text.titles_valid({'titles':['Hypothetical: A welcoming home','A useful home guide','Make room for guests']})
    assert local_text.titles_valid({'titles':['A welcoming home','A useful home guide','Make room for guests']})
    assert chapter_issues({'title':'Entryway','text':'In this hypothetical example, a host clears one shelf.'})==[]


@pytest.mark.parametrize('defect',['title','checklist','tables','mattresses'])
def test_final_export_blocks_known_defects_before_creating_files(tmp_path,defect):
    book=spec();book['source']='local_model'
    if defect=='title':book['title']='Hypothetical: Make room for guests'
    else:book['chapters'][0]['text']+='\n\n'+({'checklist':'Use the checklist provided.','tables':'Stack folding tables to make a dining surface.','mattresses':'Stack two air mattresses in the hallway.'}[defect])
    before=copy.deepcopy(book)
    with pytest.raises(ValueError,match='Editorial correction required'):
        export_handler({'root':str(tmp_path),'book':book},'')
    assert list(tmp_path.iterdir())==[] and book==before


def test_negative_sleeping_safety_instructions_are_allowed():
    assert chapter_issues({'title':'Sleeping safely','text':'Do not stack two air mattresses. Never put a mattress in the hallway. Keep the exit clear.'})==[]
