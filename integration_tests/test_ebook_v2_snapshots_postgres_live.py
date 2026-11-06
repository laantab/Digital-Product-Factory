"""The same seven preservation contracts on real, disposable PostgreSQL.

Refuses any URL except the named localhost test database. No hosted production
database, customer artifact or provider is accessed by this suite.
"""
import os
from urllib.parse import urlparse
import uuid
import json

import psycopg
from psycopg.rows import dict_row

from services.db.connection import PostgresConnection
from services.ebook_v2.legacy_snapshot import Snapshots
from tests.test_ebook_v2_legacy_snapshot import LegacySnapshots as _Contracts


class TestPostgresSnapshots(_Contracts):
    def setUp(self):
        super().setUp()
        self.url = os.environ.get("FACTORY_TEST_POSTGRES_URL", "")
        parsed = urlparse(self.url)
        assert parsed.hostname in {"127.0.0.1", "localhost"}
        assert parsed.path == "/factory_ebook_recovery_test", "Refusing a non-test database"
        self.schema = "ebook_snapshot_probe_" + uuid.uuid4().hex
        with psycopg.connect(self.url, autocommit=True) as conn:
            conn.execute(f"CREATE SCHEMA {self.schema}")
        self.addCleanup(self.drop_schema)
        self.store = Snapshots(self.connect)
        self.store.initialize()

    def connect(self):
        # The base setUp first creates its isolated SQLite fixture. The URL
        # is assigned only afterward; keep that initial call on SQLite.
        if not hasattr(self, "url"):
            return super().connect()
        return PostgresConnection(psycopg.connect(
            self.url, row_factory=dict_row, options=f"-c search_path={self.schema}"))

    def drop_schema(self):
        with psycopg.connect(self.url, autocommit=True) as conn:
            conn.execute(f"DROP SCHEMA {self.schema} CASCADE")

    def http_client(self, owner="7"):
        from flask import Flask
        from flask_login import LoginManager, UserMixin
        from services.ebook_v2.hosted_recovery import blueprint
        class User(UserMixin):
            def __init__(self, user_id):self.id=user_id
        app=Flask(__name__)
        app.secret_key="disposable-postgres-snapshot-session-key"
        manager=LoginManager(app);manager.user_loader(User)
        app.register_blueprint(blueprint(self.connect))
        client=app.test_client()
        with client.session_transaction() as session:
            session['_user_id']=owner;session['_fresh']=True
        return client

    def source_row(self):
        conn=self.connect()
        try:
            conn.execute("""CREATE TABLE projects (id BIGINT PRIMARY KEY,user_id BIGINT,
                type TEXT,name TEXT,version BIGINT,data TEXT)""")
            conn.execute("INSERT INTO projects VALUES (?,?,?,?,?,?)",(42,7,'ebook',
                self.project['name'],3,json.dumps(self.project['data'],ensure_ascii=False)))
            conn.commit()
        finally:conn.close()

    def test_real_postgres_http_preservation_uses_atomic_owner_version_and_raw_data(self):
        self.source_row();client=self.http_client()
        info=client.get('/api/ebook-recovery/projects/42')
        self.assertEqual(info.status_code,200)
        response=client.post('/api/ebook-recovery/projects/42/snapshots',json={'source_version':3},
            headers={'X-CSRF-Token':info.json['csrf_token']})
        self.assertEqual(response.status_code,201)
        reopened=self.http_client().get('/api/ebook-recovery/snapshots/'+response.json['snapshot_id'])
        self.assertEqual(reopened.status_code,200)
        self.assertEqual(reopened.json['snapshot']['data'],self.project['data'])
        self.assertFalse(reopened.json['generation_started'])
        conn=self.connect()
        try:
            row=conn.execute('SELECT version,data FROM projects WHERE id=?',(42,)).fetchone()
            self.assertEqual(row['version'],3)
            self.assertEqual(row['data'],json.dumps(self.project['data'],ensure_ascii=False))
        finally:conn.close()

    def test_real_postgres_http_foreign_owner_and_stale_version_fail_closed(self):
        self.source_row();client=self.http_client()
        info=client.get('/api/ebook-recovery/projects/42').json
        response=client.post('/api/ebook-recovery/projects/42/snapshots',json={'source_version':4},
            headers={'X-CSRF-Token':info['csrf_token']})
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.http_client('8').get('/api/ebook-recovery/projects/42').status_code,404)
        self.assertEqual(client.post('/api/ebook-recovery/projects/42/snapshots',json={'source_version':3}).status_code,403)


# Avoid collecting the imported base class as another seven SQLite tests.
del _Contracts
