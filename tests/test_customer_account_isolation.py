"""Real HTTP + database tenant boundaries. Disposable records; no provider calls."""
import copy
import uuid

import pytest
import database
from app import app
from services.project_access import export_directory


@pytest.fixture
def accounts(monkeypatch):
    monkeypatch.setenv('FACTORY_ACCESS_MODE', 'accounts')
    monkeypatch.setenv('SECRET_KEY', 'account-isolation-test-secret-key-32-characters')
    monkeypatch.setitem(app.config, 'SECRET_KEY', 'account-isolation-test-secret-key-32-characters')
    suffix = uuid.uuid4().hex
    users = [database.create_user(f'{name}-{suffix}@example.test', 'unusable-test-hash', role)
             for name, role in [('alice', 'user'), ('bob', 'user'), ('owner', 'admin')]]
    projects = [database.create_project(f'{name} Gardening Handbook', 'ebook',
                {'title': f'{name} Gardening Handbook', 'content': f'{name} private manuscript',
                 'package_id': f'{name}-{suffix}', 'ebook_project_workspace': True,
                 'ebook_workspace': {'rail': {}, 'next_action': 'research'}}, user_id=user['id'])
                for name, user in zip(('Alice', 'Bob'), users)]
    legacy = database.create_project('Preserved owner book', 'ebook', {'content': 'legacy original'})
    clients = []
    for user in users:
        client = app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = str(user['id'])
            session['_fresh'] = True
        clients.append(client)
    yield users, projects, legacy, clients
    for p in projects + [legacy]:
        database.delete_project(p['id'])


@pytest.mark.parametrize('route', [
    '/projects/{id}', '/ebook-workspace/{id}', '/ebook/build/{id}/status',
    '/ebook-workspace/{id}/edit-manuscript', '/ebook-workspace/{id}/full-preview',
    '/ebook-workspace/{id}/edit-chart/v_ch4',
    '/ebook-workspace/{id}/previous-exports/0123456789abcdef/ebook.pdf',
])
def test_foreign_project_routes_are_not_found_and_leave_every_byte_unchanged(accounts, route):
    _, projects, _, clients = accounts
    before = copy.deepcopy(database.get_project(projects[1]['id']))
    response = clients[0].get(route.format(id=projects[1]['id']))
    assert response.status_code == 404
    assert 'Bob private' not in response.get_data(as_text=True)
    assert database.get_project(projects[1]['id']) == before


def test_saved_sources_and_resume_lists_exclude_other_customers(accounts):
    _, projects, _, clients = accounts
    for path in ['/projects?factory_sources=1', '/ebook-workspaces/in-progress']:
        response = clients[0].get(path)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'Bob' not in body and 'legacy original' not in body
        assert 'Alice' in body


def test_owned_read_still_works_and_legacy_is_admin_only(accounts):
    _, projects, legacy, clients = accounts
    assert clients[0].get(f"/projects/{projects[0]['id']}").status_code == 200
    assert clients[0].get(f"/projects/{legacy['id']}").status_code == 404
    assert clients[2].get(f"/projects/{legacy['id']}").status_code == 200


def test_owned_chart_editor_is_available_without_exposing_another_accounts_words(accounts):
    _, projects, _, clients = accounts
    project = projects[0]
    data = copy.deepcopy(project['data'])
    data['visual_plan'] = {'chapters': [{'aids': [{'visual_id': 'nightly', 'type': 'workflow',
        'title': 'Private nightly routine', 'items': ['Return dishes to the kitchen.', 'Clear the table.']}]}]}
    database.update_project(project['id'], None, data)
    path = f"/ebook-workspace/{project['id']}/edit-chart/nightly"
    response = clients[0].get(path)
    assert response.status_code == 200
    assert 'Private nightly routine' in response.get_data(as_text=True)
    assert clients[1].get(path).status_code == 404


@pytest.mark.parametrize('payload', [
    {'project_id': 'foreign'}, {'fields': {'_project_id': 'foreign'}},
    {'data': {'source_project_id': 'foreign'}},
])
def test_build_requests_cannot_smuggle_foreign_references(accounts, payload, monkeypatch):
    _, projects, _, clients = accounts
    def substitute(value):
        if isinstance(value, dict):
            return {k: substitute(v) for k, v in value.items()}
        return projects[1]['id'] if value == 'foreign' else value
    monkeypatch.setitem(app.view_functions, 'ebook_build_start_route',
                        lambda: pytest.fail('foreign request reached the builder'))
    assert clients[0].post('/ebook/build', json=substitute(payload)).status_code == 404


def test_foreign_package_is_blocked_before_download_or_storage_access(accounts, monkeypatch):
    _, projects, _, clients = accounts
    monkeypatch.setitem(app.view_functions, 'download_export_route',
                        lambda **kw: ('owned download handler', 200))
    foreign = projects[1]['data']['package_id']
    own = projects[0]['data']['package_id']
    assert clients[0].get(f'/download/{foreign}/ebook.pdf').status_code == 404
    assert clients[0].get(f'/download/{own}/ebook.pdf').status_code == 200


def test_new_project_ownership_is_atomic_and_ignores_client_owner_ids(accounts):
    users, _, _, clients = accounts
    response = clients[0].post('/ebook-workspace', json={
        'topic': 'Kitchen gardening', 'author': 'Alice', 'user_id': users[1]['id']})
    assert response.status_code == 200
    project = response.get_json()['project']
    try:
        assert database.get_project_owner(project['id']) == users[0]['id']
        assert clients[1].get(f"/projects/{project['id']}").status_code == 404
    finally:
        database.delete_project(project['id'])


def test_database_scope_also_blocks_service_reads_updates_and_deletes(accounts):
    users, projects, _, _ = accounts
    from flask_login import login_user
    from auth import User
    with app.test_request_context('/'):
        login_user(User(users[0]))
        assert database.get_project(projects[1]['id']) is None
        assert database.update_project(projects[1]['id'], 'Stolen', {}) is None
        assert not database.delete_project(projects[1]['id'])
        assert {p['id'] for p in database.list_projects(include_system=True)} == {projects[0]['id']}
        with pytest.raises(Exception, match='Administrator'):
            database.set_project_owner(projects[1]['id'], users[0]['id'])


def test_standalone_exports_have_separate_owner_directories(accounts, tmp_path):
    users, _, _, _ = accounts
    from flask_login import login_user
    from auth import User
    paths = []
    for user in users[:2]:
        with app.test_request_context('/'):
            login_user(User(user))
            paths.append(export_directory(str(tmp_path)))
    assert paths[0] != paths[1]
    assert str(users[0]['id']) in paths[0] and str(users[1]['id']) in paths[1]


@pytest.mark.parametrize('path', ['/', '/projects', '/download/some-book/ebook.pdf', '/ebook/build/1/status'])
def test_signed_out_customer_cannot_fall_back_to_the_private_workspace(accounts, path):
    assert app.test_client().get(path).status_code == 401


def test_customer_admin_flags_and_unreviewed_mutations_are_refused(accounts):
    _, projects, _, clients = accounts
    assert clients[0].get('/projects?admin=1').status_code == 403
    assert clients[0].put(f"/projects/{projects[0]['id']}", json={'data': {}}).status_code == 403
    assert clients[0].post('/billing/checkout', json={}).status_code == 403


def test_customer_does_not_receive_operator_controls_even_if_admin_ui_is_enabled(accounts, monkeypatch):
    monkeypatch.setenv('ADMIN_MODE', '1')
    clients = accounts[3]
    assert 'window.FACTORY_ADMIN_MODE = false;' in clients[0].get('/').get_data(as_text=True)
    assert 'window.FACTORY_ADMIN_MODE = true;' in clients[2].get('/').get_data(as_text=True)


def test_malformed_mode_and_unstable_session_config_fail_closed(accounts, monkeypatch):
    _, _, _, clients = accounts
    monkeypatch.setenv('FACTORY_ACCESS_MODE', 'typo')
    assert clients[0].get('/projects').status_code == 503
    monkeypatch.setenv('FACTORY_ACCESS_MODE', 'accounts')
    monkeypatch.delenv('SECRET_KEY')
    assert clients[0].get('/projects').status_code == 503
    # Restore for fixture cleanup; background database access stays trusted.


def test_private_invite_mode_keeps_existing_owner_access(accounts, monkeypatch):
    _, _, legacy, _ = accounts
    monkeypatch.setenv('FACTORY_ACCESS_MODE', 'private')
    assert app.test_client().get(f"/projects/{legacy['id']}").status_code == 200


def test_deactivated_session_cannot_read_its_own_project(accounts):
    users, projects, _, clients = accounts
    database.set_user_active(users[0]['id'], False)
    assert clients[0].get(f"/projects/{projects[0]['id']}").status_code == 401


@pytest.mark.parametrize('operation', ['update', 'delete'])
def test_ownership_change_between_read_and_write_cannot_modify_the_new_owners_book(accounts, monkeypatch, operation):
    from flask_login import login_user
    from auth import User
    users, projects, _, _ = accounts
    project = projects[0]
    before = copy.deepcopy(database.get_project(project['id']))
    def transfer():
        # Simulate a concurrent operator action in this disposable database.
        conn = database.get_conn()
        try:
            conn.execute('UPDATE projects SET user_id=? WHERE id=?', (users[1]['id'], project['id']))
            conn.commit()
        finally:
            conn.close()
    if operation == 'update':
        original = database._encode_project_data
        def encode(data):
            transfer()
            return original(data)
        monkeypatch.setattr(database, '_encode_project_data', encode)
    else:
        original = database._assert_unlocked_for_deletion
        def deletion(data):
            original(data)
            transfer()
        monkeypatch.setattr(database, '_assert_unlocked_for_deletion', deletion)
    with app.test_request_context('/'):
        login_user(User(users[0]))
        if operation == 'update':
            assert database.update_project(project['id'], 'Stolen', {'content': 'changed'}) is None
        else:
            assert not database.delete_project(project['id'])
    assert database.get_project(project['id']) == before


@pytest.mark.parametrize('kind', ['word_search', 'crossword'])
def test_standalone_puzzle_file_cannot_be_downloaded_from_another_account(accounts, tmp_path, monkeypatch, kind):
    from types import SimpleNamespace
    import importlib
    module = importlib.import_module(f'routes.{kind}_builder')
    monkeypatch.setattr(module, f'{kind.upper()}_EXPORT_DIR', str(tmp_path / kind))
    raw = b'%PDF-1.4 disposable ownership fixture'
    result = SimpleNamespace(errors=[], pdf_bytes=raw, filename='garden.pdf',
                             warnings=[], puzzles=[1], qa_report=None)
    monkeypatch.setattr(module, f'build_{kind}_pdf', lambda request: result)
    monkeypatch.setattr(module, 'pipeline_download',
                        lambda **kwargs: (None, SimpleNamespace(status='passed')))
    clients = accounts[3]
    path = '/' + kind.replace('_', '-') + '-builder'
    created = clients[0].post(path + '/generate', json={
        'theme': 'Garden', 'product_title': 'Garden Handbook'})
    assert created.status_code == 200
    url = created.get_json()['download_url']
    assert clients[0].get(url).data == raw
    assert clients[1].get(url).status_code == 404


def test_account_registration_never_promotes_a_customer_even_when_count_is_zero(accounts, monkeypatch):
    monkeypatch.setattr(database, 'count_users', lambda: 0)
    response = app.test_client().post('/auth/register', json={
        'email': f'new-{uuid.uuid4().hex}@example.test',
        'password': 'Disposable-test-password', 'role': 'admin'})
    assert response.status_code == 201
    assert response.get_json()['user']['role'] == 'user'


def test_real_signed_in_build_downloads_are_private_to_the_account(monkeypatch):
    from tests.test_ebook_real_browser_customer_path import EbookRealBrowserCustomerPathTests as server
    import io
    import json
    import zipfile
    from pathlib import Path
    monkeypatch.setenv('FACTORY_ACCESS_MODE', 'accounts')
    monkeypatch.setenv('SECRET_KEY', 'browser-isolation-test-secret-key-32-characters')
    server.setUpClass()
    context = server()._new_context(accept_downloads=True)
    other = server()._new_context()
    try:
        for ctx, name in [(context, 'alice'), (other, 'bob')]:
            response = ctx.request.post(server.base + '/auth/register', data={
                'email': f'{name}@browser.example.test', 'password': 'Disposable-test-password'})
            assert response.status == 201
        page = context.new_page()
        page.goto(server.base)
        page.locator('#nav [data-go="ebook"]').click()
        page.locator('#ebookInput').fill('container gardening for beginners')
        page.locator('#ebookAuthor').fill('Alice')
        page.locator('#ebookWorkspaceStartBtn').click()
        page.locator('[data-ebook-dl-pdf]').wait_for(state='visible', timeout=180000)
        with page.expect_download() as downloaded:
            page.locator('[data-ebook-dl-pdf]').click()
        pdf = Path(downloaded.value.path()).read_bytes()
        assert pdf.startswith(b'%PDF')
        with page.expect_download() as downloaded:
            page.locator('[data-ebook-dl-zip]').click()
        with zipfile.ZipFile(io.BytesIO(Path(downloaded.value.path()).read_bytes())) as archive:
            assert archive.testzip() is None
            assert archive.read('ebook.pdf') == pdf
        projects = context.request.get(server.base + '/projects?factory_sources=1').json()
        assert len(projects) == 1
        pid = projects[0]['id']
        assert other.request.get(server.base + f'/projects/{pid}').status == 404
        status = context.request.get(server.base + f'/ebook/build/{pid}/status').json()
        assert other.request.get(server.base + status['downloads']['pdf']).status == 404
        assert other.request.get(server.base + '/ebook-workspaces/in-progress').json()['projects'] == []
        calls = json.loads(server.call_log.read_text())
        assert calls.get('paid') == calls.get('pexels_http') == 0
    finally:
        context.close()
        other.close()
        server.tearDownClass()


@pytest.mark.parametrize('nested', [False, True])
def test_customer_cannot_import_server_file_paths(accounts, monkeypatch, nested):
    _, projects, _, clients = accounts
    monkeypatch.setitem(app.view_functions, 'ebook_workspace_visuals_route',
                        lambda **kw: pytest.fail('server-path import reached visual handler'))
    payload = {'action': 'replace-photo', 'local_path': '/other-account/private-image.jpg'}
    if nested:
        payload = {'data': payload}
    response = clients[0].post(f"/ebook-workspace/{projects[0]['id']}/visuals", json=payload)
    assert response.status_code == 403


def test_signed_out_first_visit_reaches_the_signin_and_join_page(accounts):
    client = app.test_client()
    response = client.get('/', headers={'Accept': 'text/html'})
    assert response.status_code == 302
    assert response.headers['Location'] == '/plans'
    plans = client.get(response.headers['Location'])
    assert plans.status_code == 200
    assert b'Simple, Transparent Pricing' in plans.data
    assert b'id="nav"' not in plans.data
    landing = client.get('/auth/signin')
    assert landing.status_code == 200
    assert b'id="login-form"' in landing.data and b'id="register-form"' in landing.data
    assert client.get('/projects').status_code == 401


def test_real_browser_first_visit_join_signout_and_signin_reach_dashboard(monkeypatch):
    from tests.test_ebook_real_browser_customer_path import EbookRealBrowserCustomerPathTests as server
    monkeypatch.setenv('FACTORY_ACCESS_MODE', 'accounts')
    monkeypatch.setenv('SECRET_KEY', 'browser-onboarding-test-secret-key-32-characters')
    server.setUpClass()
    context = server()._new_context()
    try:
        page = context.new_page()
        arrival = page.goto(server.base)
        assert page.url == server.base + '/plans', page.locator('body').inner_text()[:500]
        page.get_by_role('heading', name='Simple, Transparent Pricing').wait_for()
        page.get_by_role('link', name='Join free', exact=True).click()
        page.wait_for_url(server.base + '/auth/signin')
        assert page.locator('#login-form').is_visible()
        assert page.locator('#register-form').is_visible()
        email = 'join-' + uuid.uuid4().hex + '@example.test'
        password = 'Disposable-test-password'
        page.locator('#reg-email').fill(email)
        page.locator('#reg-password').fill(password)
        page.locator('#reg-confirm').fill(password)
        page.locator('#register-form button').click()
        page.wait_for_url(server.base + '/')
        page.locator('#pageTitle').wait_for()
        assert page.locator('#pageTitle').inner_text() == 'Dashboard'
        assert context.request.get(server.base + '/auth/me').json()['user']['role'] == 'user'
        page.locator('#factorySignOut').click()
        page.wait_for_url(server.base + '/auth/signin')
        assert context.request.get(server.base + '/projects').status == 401
        page.locator('#login-email').fill(email)
        page.locator('#login-password').fill('Wrong-disposable-password')
        page.locator('#login-form button').click()
        page.locator('#login-msg').get_by_text('Invalid email or password.', exact=True).wait_for()
        assert page.url == server.base + '/auth/signin'
        page.locator('#login-password').fill(password)
        page.locator('#login-form button').click()
        page.wait_for_url(server.base + '/')
        assert page.locator('#pageTitle').inner_text() == 'Dashboard'
    finally:
        context.close()
        server.tearDownClass()


def test_accounts_mode_uses_signed_identity_instead_of_the_shared_invite(accounts, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, '_invite_code_required', lambda: 'private-beta-invite')
    monkeypatch.setattr(app_module, '_access_control_is_unconfigured', lambda: True)
    client = app.test_client()
    assert client.get('/', headers={'Accept': 'text/html'}).headers['Location'] == '/plans'
    assert client.get('/plans').status_code == 200
    assert client.get('/auth/signin').status_code == 200
    assert client.get('/projects').status_code == 401
    joined = client.post('/auth/register', json={'email': f'join-{uuid.uuid4().hex}@example.test',
                                               'password': 'Disposable-test-password'})
    assert joined.status_code == 201 and joined.get_json()['user']['role'] == 'user'
    assert client.get('/').status_code == 200
    monkeypatch.setenv('FACTORY_ACCESS_MODE', 'private')
    assert app.test_client().get('/').status_code == 503


def test_public_plans_never_accept_a_customer_billing_identity(accounts, monkeypatch):
    import services.billing as billing
    from services.billing.plans import catalog
    refs = []
    def pricing(ref):
        refs.append(ref)
        return {**catalog(founder_seats_remaining=17), 'current': {'private': 'other-customer-secret'}}
    monkeypatch.setattr(billing, 'pricing_payload', pricing)
    response = app.test_client().get('/plans?account_ref=foreign', headers={'X-Factory-Account': 'foreign'})
    assert response.status_code == 200 and refs == ['']
    assert b'other-customer-secret' not in response.data
    assert b'17 of 100 seats left' in response.data


def test_public_plans_fallback_keeps_real_catalog_prices_without_inventing_availability(accounts, monkeypatch):
    import services.billing as billing
    def unavailable(*args):
        raise RuntimeError('disposable unavailable count')
    monkeypatch.setattr(billing, 'pricing_payload', unavailable)
    response = app.test_client().get('/plans')
    assert response.status_code == 200
    for price in (b'$0', b'$19', b'$29', b'$39', b'$99'):
        assert price in response.data
    assert b'seats left' not in response.data
