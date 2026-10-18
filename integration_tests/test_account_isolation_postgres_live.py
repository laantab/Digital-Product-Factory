"""Tenant SQL against an explicitly disposable localhost PostgreSQL database."""
import os
from urllib.parse import urlparse
import uuid

import psycopg
from psycopg.rows import dict_row
import pytest
from flask import Flask
from flask_login import LoginManager, login_user
from werkzeug.exceptions import Unauthorized

import database
from auth import User
from services.db.connection import PostgresConnection


@pytest.fixture
def pg_accounts(monkeypatch):
    url = os.environ.get('FACTORY_TEST_POSTGRES_URL', '')
    parsed = urlparse(url)
    assert parsed.hostname in {'127.0.0.1', 'localhost'}
    assert parsed.path == '/factory_accounts_test', 'Refusing a non-test database'
    schema = 'accounts_probe_' + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA {schema}')
    def connect():
        return PostgresConnection(psycopg.connect(
            url, row_factory=dict_row, options=f'-c search_path={schema}'))
    monkeypatch.setattr(database, 'get_conn', connect)
    monkeypatch.setattr(database, '_use_postgres', lambda: True)
    monkeypatch.setenv('FACTORY_ACCESS_MODE', 'accounts')
    mini = Flask(__name__)
    mini.secret_key = 'disposable-postgres-account-test-secret'
    manager = LoginManager(mini)
    manager.user_loader(User.get)
    try:
        database.init_db()
        users = [database.create_user(name+'@example.test', 'unusable-test-hash', role)
                 for name, role in [('alice','user'), ('bob','user'), ('owner','admin')]]
        projects = [database.create_project(name+' handbook', 'ebook',
                    {'content':name+' manuscript','package_id':name+'-package'}, user_id=user['id'])
                    for name, user in zip(('alice','bob'), users)]
        legacy = database.create_project('Preserved legacy book', 'ebook', {'content':'original'})
        yield mini, users, projects, legacy
    finally:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA {schema} CASCADE')


def test_postgres_request_creation_binds_the_signed_actor_atomically(pg_accounts):
    app, users, _, _ = pg_accounts
    with app.test_request_context('/'):
        login_user(User(users[0]))
        p = database.create_project('New private book', 'ebook', {}, user_id=users[1]['id'])
        assert database.get_project_owner(p['id']) == users[0]['id']


def test_postgres_foreign_reads_updates_and_deletes_are_refused(pg_accounts):
    app, users, projects, _ = pg_accounts
    before = database.get_project(projects[1]['id'])
    with app.test_request_context('/'):
        login_user(User(users[0]))
        assert database.get_project(projects[1]['id']) is None
        assert database.update_project(projects[1]['id'], 'Stolen', {}) is None
        assert not database.delete_project(projects[1]['id'])
    assert database.get_project(projects[1]['id']) == before


def test_postgres_lists_and_streams_only_the_current_customers_rows(pg_accounts):
    app, users, projects, _ = pg_accounts
    with app.test_request_context('/'):
        login_user(User(users[0]))
        assert [p['id'] for p in database.list_projects(include_system=True)] == [projects[0]['id']]
        assert [p['id'] for p in database._iter_project_records('1=1', 'id')] == [projects[0]['id']]


def test_postgres_package_resolution_cannot_select_another_customer(pg_accounts):
    app, users, projects, _ = pg_accounts
    with app.test_request_context('/'):
        login_user(User(users[0]))
        assert database.find_project_by_package('alice-package')['id'] == projects[0]['id']
        assert database.find_project_by_package('bob-package') is None


def test_postgres_legacy_records_require_the_operator_account(pg_accounts):
    app, users, _, legacy = pg_accounts
    with app.test_request_context('/'):
        login_user(User(users[0]))
        assert database.get_project(legacy['id']) is None
    with app.test_request_context('/'):
        login_user(User(users[2]))
        assert database.get_project(legacy['id'])['data']['content'] == 'original'


def test_postgres_owned_edits_still_enforce_optimistic_concurrency(pg_accounts):
    app, users, projects, _ = pg_accounts
    with app.test_request_context('/'):
        login_user(User(users[0]))
        first = database.get_project(projects[0]['id'])
        stale = database.get_project(projects[0]['id'])
        assert database.update_project(first['id'], 'Updated', first['data'])
        with pytest.raises(database.StaleProjectWrite):
            database.update_project(stale['id'], 'Stale overwrite', stale['data'])


def test_postgres_signed_out_requests_cannot_read_a_legacy_project(pg_accounts):
    app, _, _, legacy = pg_accounts
    with app.test_request_context('/'):
        with pytest.raises(Unauthorized):
            database.get_project(legacy['id'])
