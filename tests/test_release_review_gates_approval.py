"""v1.9.11 -- a book can be approved only after its exact PDF passes the review,
and the AI part of the review never runs (or charges) without authorization."""
from __future__ import annotations

import hashlib
import os
from unittest.mock import patch

os.environ["FACTORY_TEST_MODE"] = "1"

import pytest  # noqa: E402

import database  # noqa: E402
from tests.test_release_review_container_gardening import CH7_AS_SHIPPED, _book  # noqa: E402


@pytest.fixture
def world(tmp_path):
    import app as app_module

    database.init_db()
    data, pdf, z = _book()
    pid = int(database.create_project("Grow Herbs and Greens in Small Pots", "ebook", data)["id"])
    pkg = f"ebook-{pid}"
    data.update({"package_id": pkg, "export_package_id": pkg,
                 "ebook_workspace": {"paid_call_ledger": {"budget_cap_usd": 7.0, "spent_usd": 4.1,
                                                          "paid_calls": 26, "remaining_usd": 2.9}}})
    database.update_project(pid, None, data)
    root = tmp_path / "exports"
    (root / pkg).mkdir(parents=True)
    (root / pkg / "ebook.pdf").write_bytes(pdf)
    (root / pkg / "package.zip").write_bytes(z)
    app_module.app.config["TESTING"] = True
    def fake_save(data, *, name, project_id=None, user_confirmed=True):
        database.update_project(project_id, None, data)
        return {"message": "Product approved."}

    with patch.object(app_module, "EXPORTS_DIR", str(root)), \
         patch.object(app_module, "_ebook_workspace_project_or_404",
                      lambda p: (database.get_project(p), None)), \
         patch("services.ebook_customer_path.save_factory_ebook", fake_save):
        yield {"client": app_module.app.test_client(), "pid": pid, "root": root, "pkg": pkg, "pdf": pdf}


def _no_provider(*a, **k):
    raise AssertionError("a paid provider was called without authorization")


def test_approval_is_refused_before_any_review(world):
    r = world["client"].post(f"/ebook-workspace/{world['pid']}/approve-product")
    assert r.status_code == 409 and "not reviewed" in r.get_json()["error"]


def test_review_without_authorization_calls_no_provider_and_is_not_ready(world):
    with patch("services.ebook_release_review.make_provider_reviewer", _no_provider):
        d = world["client"].post(f"/ebook-workspace/{world['pid']}/release-review", json={}).get_json()
    assert d["status"] == "Not verified" and not d["ready"]
    assert [v["page"] for v in d["visuals"]] == [1, 3, 4, 5, 6, 7]
    assert all(v.get("thumb", "").startswith("data:image/jpeg") for v in d["visuals"])
    r = world["client"].post(f"/ebook-workspace/{world['pid']}/approve-product")
    assert r.status_code == 409
    led = database.get_project(world["pid"])["data"]["ebook_workspace"]["paid_call_ledger"]
    assert (led["paid_calls"], led["spent_usd"]) == (26, 4.1)


def test_authorizing_less_than_the_stated_cost_runs_nothing(world):
    with patch("services.ebook_release_review.make_provider_reviewer", _no_provider), \
         patch("services.ebook_release_review.estimate_ai_cost",
               lambda d: {"provider": "openai", "billable": True, "estimated_usd": 0.05, "calls": 1}):
        d = world["client"].post(f"/ebook-workspace/{world['pid']}/release-review",
                                 json={"authorize_ai_usd": 0.01}).get_json()
    assert d["ai"]["ran"] is False and "below the stated cost" in d["ai"]["note"]


def test_an_authorized_passing_review_allows_approval_of_that_exact_pdf(world):
    with patch("services.ebook_release_review.make_provider_reviewer", lambda: (lambda req: [])), \
         patch("services.ebook_release_review.estimate_ai_cost",
               lambda d: {"provider": "openai", "billable": True, "estimated_usd": 0.05, "calls": 1}):
        d = world["client"].post(f"/ebook-workspace/{world['pid']}/release-review",
                                 json={"authorize_ai_usd": 0.05}).get_json()
    assert d["status"] == "Ready for approval", d["groups"]
    led = database.get_project(world["pid"])["data"]["ebook_workspace"]["paid_call_ledger"]
    assert (led["paid_calls"], round(led["spent_usd"], 2)) == (27, 4.15)
    r = world["client"].post(f"/ebook-workspace/{world['pid']}/approve-product")
    assert r.status_code == 200 and r.get_json()["ok"]
    appr = database.get_project(world["pid"])["data"]["product_approval"]
    assert appr["pdf_sha256"] == hashlib.sha256(world["pdf"]).hexdigest()


def test_a_changed_pdf_needs_a_new_review(world):
    with patch("services.ebook_release_review.make_provider_reviewer", lambda: (lambda req: [])), \
         patch("services.ebook_release_review.estimate_ai_cost",
               lambda d: {"provider": "openai", "billable": True, "estimated_usd": 0.05, "calls": 1}):
        world["client"].post(f"/ebook-workspace/{world['pid']}/release-review", json={"authorize_ai_usd": 0.05})
    _, pdf2, _ = _book(ch7=CH7_AS_SHIPPED)
    (world["root"] / world["pkg"] / "ebook.pdf").write_bytes(pdf2)
    r = world["client"].post(f"/ebook-workspace/{world['pid']}/approve-product")
    assert r.status_code == 409 and "changed" in r.get_json()["error"]


def test_the_review_screen_renders(world):
    r = world["client"].get(f"/ebook-workspace/{world['pid']}/release-review")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Editor-in-Chief review" in html and "Approve all acceptable visuals" in html
