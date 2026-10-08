"""Real local fixtures prove the automatic build stops once and exports the choice."""
import copy
from pathlib import Path
from unittest import mock
import pytest
import database
from services import ebook_build_orchestrator as orch
from services import ebook_guided_build as guided


def test_the_real_fixture_build_waits_for_a_cover_then_exports_the_selected_title(monkeypatch):
    monkeypatch.setenv('EBOOK_CUSTOMER_PATH_FIXTURE', '1')
    from app import app
    client = app.test_client()
    p, _ = orch.start_build({'topic': 'container gardening', 'ebook_title': 'Container Gardening for Beginners', 'author_brand': 'Fixture Author',
                             'include_images': 'Yes', 'guided_cover_choice': True})
    pid = p['id']
    try:
        for _ in range(100):
            status = orch.advance_build(pid)
            assert not status.get('failed'), (database.get_project(pid)['data'].get('ebook_build'), orch._picture_review(database.get_project(pid)['data']))
            assert not status.get('awaiting_picture_approval')
            if status.get('awaiting_cover_choice'):
                break
        assert status['awaiting_cover_choice'], status
        data = database.get_project(pid)['data']
        original_content = data.get('content')
        original_spend = copy.deepcopy(data['ebook_workspace'].get('budget'))
        before_attempts = copy.deepcopy(data['ebook_build']['stages'])
        with mock.patch.dict(orch.STAGE_RUNNERS, {s: mock.Mock(side_effect=AssertionError('ran while choosing')) for s in orch.STAGES}):
            assert orch.advance_build(pid)['awaiting_cover_choice']
        assert database.get_project(pid)['data']['ebook_build']['stages'] == before_attempts
        titles = status['cover_choice']['title_options']
        assert len(titles) >= 2
        chosen = titles[1]
        with mock.patch('services.jobs.dispatch.hand_off'):
            response = client.post(f'/ebook/build/{pid}/cover-choice', json={'action':'title','title_id':chosen['id']})
        assert response.status_code == 200, response.json
        status = orch.advance_build(pid)
        assert status['awaiting_cover_choice'], status
        assert status['title'] == chosen['title']
        data = database.get_project(pid)['data']
        assert data.get('content') == original_content
        assert data['ebook_workspace'].get('budget') == original_spend
        from services.ebook_visual_pipeline import validate_visual_readiness
        report = validate_visual_readiness(data)
        assert report.ok, report.findings
        variants = status['cover_choice']['variants']
        assert variants
        cover = variants[-1]
        with mock.patch('services.jobs.dispatch.hand_off'):
            stale = client.post(f'/ebook/build/{pid}/cover-choice', json={'action':'finish','title_id':chosen['id'],
                'layout_id':cover['layout_id'],'digest':'stale'})
            assert stale.status_code == 400
            response = client.post(f'/ebook/build/{pid}/cover-choice', json={'action':'finish','title_id':chosen['id'],
                'layout_id':cover['layout_id'],'digest':cover['digest']})
        assert response.status_code == 200, response.json
        for _ in range(30):
            status = orch.advance_build(pid)
            assert not status.get('failed'), (database.get_project(pid)['data'].get('ebook_build'), orch._picture_review(database.get_project(pid)['data']))
            assert not status.get('awaiting_cover_choice')
            if status['finished']:
                break
        assert status['finished'], status
        assert status['downloads']['pdf'] and status['downloads']['zip']
        data = database.get_project(pid)['data']
        assert data['cover_design']['selected_layout'] == cover['layout_id']
        assert data['title'] == chosen['title']
        assert data.get('content') == original_content
        # Serve the actual bytes through the customer's download routes.
        pdf = client.get(status['downloads']['pdf'])
        archive = client.get(status['downloads']['zip'])
        assert pdf.status_code == 200 and pdf.data.startswith(b'%PDF')
        assert archive.status_code == 200 and archive.data.startswith(b'PK')
        import fitz
        document = fitz.open(stream=pdf.data, filetype='pdf')
        assert chosen['title'].split()[0] in document[0].get_text()
        document.close()
    finally:
        database.delete_project(pid)


@pytest.mark.parametrize('state', ['APPROVED','LOCKED'])
def test_generate_project_never_mutates_a_protected_artifact(state):
    with pytest.raises(ValueError):
        guided.start({'artifact_state':state})


def test_a_bad_visual_plan_is_never_approved_automatically():
    data = {'fields':{'guided_cover_choice':True}}
    with mock.patch('services.ebook_design_workspace.prepare_visuals_local', return_value=data), \
         mock.patch('services.ebook_design_workspace.approve_visuals_local', side_effect=ValueError('quality failed')):
        with pytest.raises(ValueError, match='quality failed'):
            orch._run_visuals(data, 1)
