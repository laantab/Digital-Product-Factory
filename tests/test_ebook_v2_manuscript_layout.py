import copy
import fitz
from services.ebook_v2.publishing import render_pdf
from services.ebook_v2.final_quality import inspect
from tests.ebook_v2_fixture import spec


def test_saved_markdown_renders_as_headings_and_emphasis_without_changing_prose(tmp_path):
    book = spec()
    book['chapters'][0]['text'] = ('### **A practical starting point**\n\n'
        '**Notice your breathing.** Keep *gentle attention* on the next breath.\n\n'
        '- First useful action\n- Second useful action\n\n'
        '| Activity | What to notice |\n| --- | --- |\n| Walking | Notice your feet and breathing |\n\n' + book['chapters'][0]['text'])
    book['visuals'] = [{'overview':['### A practical starting point', 'The most **common** parts of being a **beginner**.']}, {}]
    original = copy.deepcopy(book)
    pdf = render_pdf(book)
    with fitz.open(stream=pdf, filetype='pdf') as doc:
        text = ''.join(page.get_text() for page in doc)
        assert '###' not in text and '**' not in text and '|' not in text
        assert 'A practical starting point' in text
        spans = [span for page in doc for block in page.get_text('dict')['blocks'] if block['type']==0
                 for line in block['lines'] for span in line['spans']]
        assert any('Bold' in s['font'] and 'Notice your breathing.' in s['text'] for s in spans)
    assert inspect(pdf, book, str(tmp_path))['source_text_present']
    assert book == original
