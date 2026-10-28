"""Readability changes preserve content and real photo identity."""
import base64
import copy
import hashlib
import io

import pytest
from PIL import Image

from services import ebook_visual_pipeline as visuals
from services.ebook_release_review import _thumb


def test_real_chapter_chart_has_large_labels_and_lossless_scaled_pixels():
    aid = {"type": "checklist", "title": "Healthy materials and indoor air",
           "items": ["Fix water and ventilation problems first.",
                     "Choose low-emission materials for surfaces and finishes."]}
    image = visuals.render_aid_png(aid, scale=2)
    assert image.width == 2800
    assert visuals.label_min_pt(image, column_pt=468) >= 13
    assert visuals.label_min_pt(image, column_pt=260) < 8


def test_review_image_is_large_enough_to_read_when_enlarged():
    source = Image.new("RGB", (2800, 1600), "white")
    with Image.open(io.BytesIO(_thumb(source))) as image:
        assert image.width == 1200
        assert image.height > 600
    small = Image.new("RGB", (500, 300))
    with Image.open(io.BytesIO(_thumb(small))) as image:
        assert image.size == small.size  # Never invent pixels by upscaling.


def test_lossless_chart_embedding_and_high_quality_photo_resolution(tmp_path):
    source = Image.new("RGB", (3200, 2400), "white")
    path = tmp_path / "chart.png"
    source.save(path)
    uri, width, height = visuals._embed_preview_image(str(path), lossless=True)
    assert uri.startswith("data:image/png;base64,") and width == 2400
    assert height == 1800
    payload = io.BytesIO()
    source.save(payload, "JPEG")
    assert visuals.prepare_interior_photo(payload.getvalue()).size == (2400, 1800)


def test_restore_original_preserves_photo_identity_and_verified_backup(tmp_path, monkeypatch):
    old_path = tmp_path / "photo.png"
    Image.new("RGB", (1600, 1200), "white").save(old_path)
    old_sha = hashlib.sha256(old_path.read_bytes()).hexdigest()
    aid = {"visual_id": "v_ch1", "type": "photo", "source": "pexels", "photo_id": "123",
           "asset_path": str(old_path), "sha256": old_sha, "width": 1600, "height": 1200}
    data = {"artifact_state": "DRAFT", "content": "Original manuscript.", "package_id": "test",
            "visual_plan": {"chapters": [{"chapter": "One", "aids": [aid]}]}}
    import services.ebook_pexels as pexels
    payload = io.BytesIO()
    Image.new("RGB", (3200, 2400), "white").save(payload, "JPEG")
    monkeypatch.setattr(pexels, "fetch_pexels_photo", lambda pid: {"photo_id": pid})
    monkeypatch.setattr(pexels, "download_pexels_original", lambda photo: payload.getvalue())
    monkeypatch.setattr(visuals, "local_visual_path", lambda aid: str(old_path))

    def store(aid, raw, **kwargs):
        with visuals.prepare_interior_photo(raw) as image:
            image.save(old_path)
            return {**aid, "width": image.width, "height": image.height,
                    "sha256": hashlib.sha256(old_path.read_bytes()).hexdigest()}

    monkeypatch.setattr(visuals, "store_interior_photo", store)
    monkeypatch.setattr(visuals, "write_visual_contact_sheet", lambda *a, **k: "")
    monkeypatch.setattr(visuals, "stamp_plan_photo_matches", lambda plan: None)
    updated = visuals.replace_photo_aid(data, "v_ch1", mode="higher-resolution")
    result = updated["visual_plan"]["chapters"][0]["aids"][0]
    assert result["photo_id"] == "123" and result["width"] == 2400
    history = result["resolution_history"][0]
    from pathlib import Path
    assert hashlib.sha256(Path(history["path"]).read_bytes()).hexdigest() == old_sha
    assert updated["content"] == "Original manuscript."


def test_clear_print_profile_is_opt_in_and_preserves_text():
    from services.ebook_book_layout import render_designed_ebook_html
    from services.ebook_design_spec import build_ebook_design
    design = build_ebook_design(theme_id="modern_practical", manuscript_digest="test")
    args = dict(title="Clarity", subtitle="", author="Lonnie", manuscript_md="# Chapter 1\nUnchanged text.", design=design)
    original = render_designed_ebook_html(**args)
    design.styles["readability_profile"] = "clear_large"
    revised = render_designed_ebook_html(**args)
    assert "font-size:13pt" not in original
    assert "font-size:13pt" in revised and "font-size:11pt" in revised
    assert "Unchanged text." in original and "Unchanged text." in revised


def test_print_update_invalidates_the_real_design_rail_without_rewriting_content(monkeypatch):
    from services.ebook_workspace_actions import visuals as action
    from services.ebook_project_workspace import ensure_workspace, stage_status
    data = ensure_workspace({"artifact_state": "DRAFT", "content": "Unchanged manuscript.",
                             "title": "Keep this title", "cover_design": {"cover_digest": "approved-cover"},
                             "package_id": "test", "visual_plan": {"chapters": []}})
    monkeypatch.setattr(visuals, "materialize_visual_plan", lambda plan, **kwargs: copy.deepcopy(plan))
    data["ebook_build"] = {"paused_after": "visuals"}
    result, _ = action(data, {"action": "improve-print"})
    assert result["content"] == "Unchanged manuscript."
    assert result["title"] == "Keep this title"
    assert result["cover_design"]["cover_digest"] == "approved-cover"
    assert result["fields"]["readability_profile"] == "clear_large"
    assert result["fields"]["theme_id"] == "modern_practical"
    assert result["export_ready"] is False
    assert result["ebook_build"]["paused_after"] == ""
    assert stage_status(result["ebook_workspace"], "design") == "not_started"
    assert stage_status(result["ebook_workspace"], "preview") == "not_started"


def test_a_photo_caption_stays_on_the_photographs_pdf_page(tmp_path):
    import fitz
    from services.ebook_design_system import theme_css
    from services.pdf_export import _html_to_pdf_xhtml2pdf
    path = tmp_path / "photo.png"
    Image.new("RGB", (600, 300), "#aabbcc").save(path)
    caption = "Fixture caption stays with its photograph."
    figure = visuals.figure_html({"visual_id": "photo", "type": "photo",
                                  "asset_path": str(path), "caption": caption})
    css = theme_css("modern_practical") + "body,p{font-size:13pt;line-height:1.6;}figcaption{font-size:11pt;line-height:1.4;}"
    html = f'<html><head><style>{css}</style></head><body><pdf:spacer height="420pt"/>{figure}</body></html>'
    with fitz.open(stream=_html_to_pdf_xhtml2pdf(html), filetype="pdf") as doc:
        image_pages = [i for i, page in enumerate(doc) if page.get_image_info()]
        caption_pages = [i for i, page in enumerate(doc) if caption in " ".join(page.get_text().split())]
    assert len(image_pages) == 1
    assert caption_pages == image_pages


@pytest.mark.parametrize('height', [580, 600, 620])
def test_section_heading_stays_with_its_first_supporting_sentence(height):
    import fitz
    from services.ebook_design_system import theme_css
    from services.pdf_export import _html_to_pdf_xhtml2pdf
    heading = 'A section that needs its first paragraph'
    sentence = 'This supporting sentence belongs with the heading.'
    html = f'''<html><head><style>{theme_css('modern_practical')}</style></head><body>
      <pdf:spacer height="{height}pt"/><h3>{heading}</h3>
      <p>{sentence} The rest of the paragraph explains the practical action in enough detail
      to fill several lines on a normal book page.</p></body></html>'''
    with fitz.open(stream=_html_to_pdf_xhtml2pdf(html), filetype='pdf') as doc:
        text = [' '.join(page.get_text().split()) for page in doc]
    heading_pages = [i for i, page in enumerate(text) if heading in page]
    sentence_pages = [i for i, page in enumerate(text) if sentence in page]
    assert len(heading_pages) == 1
    assert heading_pages == sentence_pages


def test_review_controls_target_the_clicked_visual_when_two_share_a_page():
    import base64
    import io
    import json
    from urllib.parse import urlparse
    from playwright.sync_api import sync_playwright, expect
    from app import RELEASE_REVIEW_PAGE
    def thumbnail(color):
        buf = io.BytesIO()
        Image.new("RGB", (48, 32), color).save(buf, "PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    photo_thumb = thumbnail("blue")
    review = {"status": "Needs human review", "ready": False, "groups": [], "visuals": [
        {"page": 7, "kind": "chart", "visual_id": "chart-a", "chapter": "Chart", "thumb": thumbnail("red"), "status": "needs_human_review"},
        {"page": 7, "kind": "photo", "visual_id": "photo-b", "chapter": "Photo", "thumb": photo_thumb, "status": "needs_human_review"},
    ]}
    html = RELEASE_REVIEW_PAGE.replace("__PID__", "20").replace("__TITLE__", "Fixture")
    posted = []
    def respond(route):
        path = urlparse(route.request.url).path
        if path == "/review":
            route.fulfill(status=200, content_type="text/html", body=html)
        elif path.endswith("/release-review/current"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(review))
        elif path.endswith("/release-review/estimate"):
            route.fulfill(status=200, content_type="application/json", body="{}")
        elif path.endswith("/visuals"):
            posted.append(json.loads(route.request.post_data))
            route.fulfill(status=400, content_type="application/json", body='{"error":"fixture complete"}')
        else:
            raise AssertionError(path)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/*", respond)
            page.goto("http://factory.test/review")
            expect(page.get_by_role("button", name="View clearly", exact=True)).to_have_count(2)
            page.get_by_role("button", name="View clearly", exact=True).nth(1).click()
            expect(page.locator("#visualViewerImage")).to_have_attribute("src", photo_thumb)
            page.get_by_role("button", name="Close enlarged view", exact=True).click()
            with page.expect_response("**/visuals"):
                page.get_by_role("button", name="Restore original resolution", exact=True).click()
            assert posted[0]["visual_id"] == "photo-b"
        finally:
            browser.close()
