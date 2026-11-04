"""Real signed Factory requests preserve exact source data without generation."""
import copy

import pytest
import database
from app import app
from services.ebook_v2.legacy_snapshot import Snapshots
from tests.test_customer_account_isolation import accounts


def source(client, project):
    return client.get(f"/api/ebook-recovery/projects/{project['id']}")


def preserve(client, project, version=None):
    response = source(client, project)
    assert response.status_code == 200, response.get_json()
    info = response.get_json()
    return client.post(f"/api/ebook-recovery/projects/{project['id']}/snapshots",
                       json={"source_version": info["source_version"] if version is None else version},
                       headers={"X-CSRF-Token": info["csrf_token"]})


def test_save_restart_reopen_preserves_original_row_and_pending_findings(accounts, monkeypatch):
    users, projects, _, clients = accounts
    from services.ebook_v2.books import Books
    monkeypatch.setattr(Books, "create", lambda *a, **k: pytest.fail("Generation must not start"))
    original = database.get_project(projects[0]["id"])
    original["data"]["ebook_workspace"]["accepted_chapters"] = [
        {"title": "Accepted chapter", "body": "Exact original - keep this.\n"}]
    original["data"]["ebook_workspace"]["pending"] = {
        "body": "Unapproved draft.\n", "quality": {"pass": False, "findings": ["GENERIC_FILLER"]}}
    database.update_project(original["id"], original["name"], original["data"])
    original = database.get_project(original["id"])
    before = copy.deepcopy(original)
    saved_data={k:v for k,v in before["data"].items() if k!=database.ROW_VERSION_KEY}
    response = preserve(clients[0], original)
    assert response.status_code == 201
    result = response.get_json()
    assert result["generation_started"] is False
    assert database.get_project(original["id"]) == before
    reopened = clients[0].get("/api/ebook-recovery/snapshots/" + result["snapshot_id"])
    assert reopened.status_code == 200
    assert reopened.get_json()["snapshot"]["data"] == saved_data
    assert reopened.headers["Cache-Control"] == "no-store"
    # Fresh store instance is restart proof, not an in-memory response cache.
    assert Snapshots(database.get_conn).reopen(users[0]["id"], result["snapshot_id"])["data"] == saved_data
    assert preserve(clients[0], original).get_json()["snapshot_id"] == result["snapshot_id"]


def test_other_account_and_admin_cannot_snapshot_a_foreign_book(accounts):
    _, projects, _, clients = accounts
    assert source(clients[1], projects[0]).status_code == 404
    assert source(clients[2], projects[0]).status_code == 404
    saved = preserve(clients[0], projects[0]).get_json()
    assert clients[1].get("/api/ebook-recovery/snapshots/" + saved["snapshot_id"]).status_code == 404
    assert clients[2].get("/api/ebook-recovery/snapshots/" + saved["snapshot_id"]).status_code == 404


def test_signed_out_and_missing_csrf_are_refused_before_any_write(accounts):
    _, projects, _, clients = accounts
    path = f"/api/ebook-recovery/projects/{projects[0]['id']}"
    assert app.test_client().get(path).status_code == 401
    assert clients[0].post(path + "/snapshots", json={"source_version": 0}).status_code == 403
    assert clients[0].post(path + "/snapshots", json={"source_version": 0},
                           headers={"X-CSRF-Token": "wrong"}).status_code == 403


def test_stale_source_version_does_not_create_snapshot(accounts):
    _, projects, _, clients = accounts
    info = source(clients[0], projects[0]).get_json()
    result = preserve(clients[0], projects[0], info["source_version"] + 1)
    assert result.status_code == 409


@pytest.mark.parametrize("body", [{}, {"source_version": True}, {"source_version": -1},
                                  {"source_version": 0, "data": {"content": "replacement"}}])
def test_client_cannot_submit_snapshot_content_or_invalid_version(accounts, body):
    _, projects, _, clients = accounts
    info = source(clients[0], projects[0]).get_json()
    result = clients[0].post(f"/api/ebook-recovery/projects/{projects[0]['id']}/snapshots",
                            json=body, headers={"X-CSRF-Token": info["csrf_token"]})
    assert result.status_code == 400


def test_transferred_source_is_not_reopened_by_previous_owner(accounts):
    users, projects, _, clients = accounts
    saved = preserve(clients[0], projects[0]).get_json()
    conn = database.get_conn()
    try:
        conn.execute("UPDATE projects SET user_id=? WHERE id=?", (users[1]["id"], projects[0]["id"]))
        conn.commit()
    finally:
        conn.close()
    assert clients[0].get("/api/ebook-recovery/snapshots/" + saved["snapshot_id"]).status_code == 404


def test_corrupt_snapshot_never_reaches_http_response(accounts):
    _, projects, _, clients = accounts
    saved = preserve(clients[0], projects[0]).get_json()
    conn = database.get_conn()
    try:
        conn.execute("UPDATE ebook_v2_legacy_snapshots SET payload='{}' WHERE id=?", (saved["snapshot_id"],))
        conn.commit()
    finally:
        conn.close()
    result = clients[0].get("/api/ebook-recovery/snapshots/" + saved["snapshot_id"])
    assert result.status_code == 409
    assert "snapshot" not in result.get_json()


def test_invalid_json_is_a_request_error_and_original_is_unchanged(accounts):
    _, projects, _, clients=accounts
    original=database.get_project(projects[0]['id'])
    info=source(clients[0],original).get_json()
    response=clients[0].post(f"/api/ebook-recovery/projects/{original['id']}/snapshots",
                             data='{',content_type='application/json',
                             headers={'X-CSRF-Token':info['csrf_token']})
    assert response.status_code==400
    assert database.get_project(original['id'])==original
