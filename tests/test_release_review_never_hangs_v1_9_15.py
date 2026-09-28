"""v1.9.15: the Release Review screen never sits on "Reviewing..." forever,
and a click on Accept / Reject does not start the whole review again.

Before: the page ran the full PDF + ZIP review on load and again after every
Accept, Reject or "I have read the notes". It read the answer with
``await r.json()`` and nothing else, so when the website answered with an
error page (a 502 while the review was still running, or the service being
restarted) the script stopped and the page kept showing "Reviewing the PDF
and ZIP..." with no buttons, indefinitely. Every click also re-scanned every
page and picture of the book, which is what made those failures likely.

Now:
* the measured review is stored once; decisions are applied to it, so the
  status and counts change with each click without a new scan;
* opening the page shows the saved review of the current PDF;
* any failure shows what happened and a "Try again" button.
"""
from __future__ import annotations

import os
from unittest.mock import patch

os.environ["FACTORY_TEST_MODE"] = "1"

import pytest  # noqa: E402

import database  # noqa: E402
from tests.test_release_review_container_gardening import CH7_AS_SHIPPED, _book  # noqa: E402
from tests.test_release_review_gates_approval import world  # noqa: E402,F401  (fixture)


def _counting_review():
    """Wrap review_release so the test can count full scans."""
    import services.ebook_release_review as rr

    real = rr.review_release
    calls = {"n": 0}

    def counted(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    return calls, patch.object(rr, "review_release", counted)


# --------------------------------------------------------------------------- routes
def test_each_decision_updates_status_without_rescanning_the_pdf(world):
    c, pid = world["client"], world["pid"]
    calls, p = _counting_review()
    with p:
        d = c.post(f"/ebook-workspace/{pid}/release-review", json={}).get_json()
        assert calls["n"] == 1
        assert d["status"] == "Needs human review" and d["counts"]["needs_human_review"] == 6
        pages = [v["page"] for v in d["visuals"]]
        for i, page in enumerate(pages, start=1):
            d = c.post(f"/ebook-workspace/{pid}/release-review/decision",
                       json={"page": page, "decision": "accept"}).get_json()
            # The answer is the updated review itself, with pictures.
            assert d["counts"]["needs_human_review"] == 6 - i
            assert all(v.get("thumb", "").startswith("data:image/jpeg") for v in d["visuals"])
        assert calls["n"] == 1, "a decision started a full review again"
    assert d["status"] == "Ready for approval", d["groups"]
    stored = database.get_project(pid)["data"]["release_review"]
    assert stored["status"] == "Ready for approval" and stored["counts"]["needs_human_review"] == 0
    assert c.post(f"/ebook-workspace/{pid}/approve-product").get_json()["ok"] is True


def test_stored_decisions_give_the_same_result_as_a_full_review(world):
    """Applying decisions to the stored measurement equals a fresh scan with them."""
    c, pid = world["client"], world["pid"]
    d = c.post(f"/ebook-workspace/{pid}/release-review", json={}).get_json()
    first, second = d["visuals"][0]["page"], d["visuals"][1]["page"]
    c.post(f"/ebook-workspace/{pid}/release-review/decision", json={"page": first, "decision": "accept"})
    quick = c.post(f"/ebook-workspace/{pid}/release-review/decision",
                   json={"page": second, "decision": "reject"}).get_json()
    full = c.post(f"/ebook-workspace/{pid}/release-review", json={}).get_json()
    for key in ("status", "counts", "groups", "accepted", "pdf_sha256", "decisions"):
        assert quick[key] == full[key], key
    assert [(v["page"], v["status"]) for v in quick["visuals"]] == \
           [(v["page"], v["status"]) for v in full["visuals"]]
    assert quick["status"] == "Changes required"


def test_opening_the_page_again_shows_the_saved_review_without_a_scan(world):
    c, pid = world["client"], world["pid"]
    assert c.get(f"/ebook-workspace/{pid}/release-review/current").status_code == 404
    d = c.post(f"/ebook-workspace/{pid}/release-review", json={}).get_json()
    c.post(f"/ebook-workspace/{pid}/release-review/decision",
           json={"page": d["visuals"][0]["page"], "decision": "accept"})
    calls, p = _counting_review()
    with p:
        r = c.get(f"/ebook-workspace/{pid}/release-review/current")
    assert r.status_code == 200 and calls["n"] == 0
    cur = r.get_json()
    assert cur["counts"]["needs_human_review"] == 5 and len(cur["accepted"]) == 1
    assert all(v.get("thumb", "").startswith("data:image/jpeg") for v in cur["visuals"])


def test_the_saved_review_is_not_shown_for_a_changed_pdf(world):
    c, pid = world["client"], world["pid"]
    c.post(f"/ebook-workspace/{pid}/release-review", json={})
    _, pdf2, _ = _book(ch7=CH7_AS_SHIPPED)
    (world["root"] / world["pkg"] / "ebook.pdf").write_bytes(pdf2)
    r = c.get(f"/ebook-workspace/{pid}/release-review/current")
    assert r.status_code == 404 and r.get_json()["needs_run"] is True


def test_a_review_saved_before_this_release_still_accepts_decisions(world):
    c, pid = world["client"], world["pid"]
    c.post(f"/ebook-workspace/{pid}/release-review", json={})
    data = database.get_project(pid)["data"]
    data["release_review"].pop("base")             # as saved by 1.9.14
    database.update_project(pid, None, data)
    r = c.post(f"/ebook-workspace/{pid}/release-review/decision", json={"page": 1, "decision": "accept"})
    assert r.status_code == 200 and r.get_json()["needs_run"] is True
    assert database.get_project(pid)["data"]["release_review"]["decisions"] == {"1": "accept"}


# --------------------------------------------------------------------------- the page itself
def _page_html(pid: int = 5) -> str:
    import app as app_module

    return app_module.RELEASE_REVIEW_PAGE.replace("__PID__", str(pid)).replace("__TITLE__", "Test Book")


REVIEW = {"status": "Needs human review", "ready": False, "counts": {"needs_human_review": 1},
          "accepted": [], "ai": {"ran": False}, "decisions": {},
          "groups": [{"correction": "Check the picture", "level": "needs_human_review",
                      "findings": [{"code": "X", "level": "needs_human_review", "page": 3, "chapter": "One",
                                    "subject": "photo", "why": "check", "fix": "look"}]}],
          "visuals": [{"page": 3, "kind": "photo", "chapter": "One", "status": "needs_human_review"}]}


def _open(pw, handler):
    import json

    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    seen: list[str] = []

    def route(r):
        url, method = r.request.url, r.request.method
        seen.append(f"{method} {url.split('factory.test', 1)[-1]}")
        if url.endswith("/review-page"):
            return r.fulfill(status=200, content_type="text/html", body=_page_html())
        if url.endswith("/release-review/estimate"):
            return r.fulfill(status=200, content_type="application/json", body='{"estimated_usd":0.05}')
        status, body = handler(method, url)
        return r.fulfill(status=status, content_type="application/json" if status < 500 else "text/html",
                         body=body if isinstance(body, str) else json.dumps(body))

    page.route("**/*", route)
    page.goto("http://factory.test/review-page")
    return browser, page, seen


def test_page_shows_an_error_and_try_again_when_the_review_fails():
    from playwright.sync_api import expect, sync_playwright

    def handler(method, url):
        if url.endswith("/current"):
            return 404, {"needs_run": True}
        return 502, "<html><body>Bad Gateway</body></html>"

    with sync_playwright() as pw:
        browser, page, _ = _open(pw, handler)
        try:
            expect(page.locator("#status")).to_have_text("The review did not finish.", timeout=5000)
            assert "502" in page.inner_text("#actions")
            expect(page.locator("#actions button", has_text="Try again")).to_be_visible()
        finally:
            browser.close()


def test_page_retry_recovers_after_a_failure():
    from playwright.sync_api import expect, sync_playwright

    state = {"posts": 0}

    def handler(method, url):
        if url.endswith("/current"):
            return 404, {"needs_run": True}
        state["posts"] += 1
        return (502, "Bad Gateway") if state["posts"] == 1 else (200, REVIEW)

    with sync_playwright() as pw:
        browser, page, _ = _open(pw, handler)
        try:
            expect(page.locator("#actions button", has_text="Try again")).to_be_visible(timeout=5000)
            page.locator("#actions button", has_text="Try again").click()
            expect(page.locator("#status")).to_have_text("Needs human review", timeout=5000)
        finally:
            browser.close()


def test_page_uses_the_saved_review_and_a_decision_does_not_rerun_it():
    from playwright.sync_api import expect, sync_playwright

    accepted = {**REVIEW, "status": "Ready for approval", "ready": True, "counts": {},
                "groups": [], "visuals": [{**REVIEW["visuals"][0], "status": "accepted_by_owner"}]}

    def handler(method, url):
        if url.endswith("/current"):
            return 200, REVIEW
        if url.endswith("/decision"):
            return 200, accepted
        return 500, "a full review must not be started"

    with sync_playwright() as pw:
        browser, page, seen = _open(pw, handler)
        try:
            expect(page.locator("#status")).to_have_text("Needs human review", timeout=5000)
            page.locator("#sheet button", has_text="Accept").click()
            expect(page.locator("#status")).to_have_text("Ready for approval", timeout=5000)
            expect(page.locator("#actions button", has_text="Approve Product")).to_be_enabled()
        finally:
            browser.close()
    assert not [s for s in seen if s.startswith("POST") and s.endswith("/release-review")], seen


def test_the_visuals_link_opens_the_workspace():
    html = _page_html(7)
    assert "/?view=ebook-workspace&project_id=${PID}&stage=visuals" in html
    assert "/?ebook-workspace=" not in html
