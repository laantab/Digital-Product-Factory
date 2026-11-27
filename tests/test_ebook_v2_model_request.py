"""A user test brief cannot change the model boundary or start work in preflight."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.verify_ebook_v2_local import requested_spec


ROOT=Path(__file__).resolve().parents[1]


def test_preflight_resolves_real_brief_without_creating_book_directory(tmp_path):
    destination=tmp_path/'not-started'
    result=subprocess.run([sys.executable,str(ROOT/'scripts/verify_ebook_v2_local.py'),
        '--data',str(destination),'--request',str(ROOT/'release_evidence/ebook_v2_model_acceptance_request.json'),
        '--prepare-only'],capture_output=True,text=True,check=True)
    report=json.loads(result.stdout)
    assert report['generation_started'] is False
    assert report['spec']['source']=='ollama' and report['spec']['require_photos'] is False
    assert not destination.exists()


@pytest.mark.parametrize('change',[
    {'paid_providers':True},
    {'spec':{'source':'paid-cloud'}},
    {'spec':{'chapter_count':True}},
    {'spec':{'min_words':0}},
])
def test_request_cannot_override_provider_or_send_invalid_work(tmp_path,change):
    request=json.loads((ROOT/'release_evidence/ebook_v2_model_acceptance_request.json').read_text())
    if 'spec' in change:request['spec'].update(change['spec'])
    else:request.update(change)
    path=tmp_path/'request.json';path.write_text(json.dumps(request))
    with pytest.raises(ValueError):requested_spec(path,8,650)
