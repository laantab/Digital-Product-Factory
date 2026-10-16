"""The manuscript review controls must preserve safe review and rejection."""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]


def test_editor_renders_original_proposal_and_reject_controls():
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                      autoescape=select_autoescape(["html"]))
    page = env.get_template("ebook_manuscript_editor.html").render(
        project_id=42, manuscript="Safe draft.", manuscript_digest="digest")
    assert 'id="comparison"' in page
    assert 'id="before"' in page
    assert 'id="after"' in page
    assert 'id="reject"' in page
    assert "reviewed.original" in page
    assert "reviewed.edited" in page
    assert "nothing saved" in page
    assert "apply',{manuscript:reviewed.edited}" in page
    assert "action('undo')" in page
