"""v1.9.10 -- chart and diagram text is readable at its printed size.

Container Gardening for Beginners printed five charts (pages 8, 18, 23, 28,
32) whose labels came out near 6 pt: they are drawn as pictures and scaled to
the text column, and no check measured the words inside them. The one-click
build also never ran the Editor-in-Chief. Zero cost: local drawing only.
"""
import os

os.environ["FACTORY_TEST_MODE"] = "1"

import pytest  # noqa: E402

from services.editor_in_chief import check_diagram_label_size  # noqa: E402
from services.ebook_visual_pipeline import (  # noqa: E402
    MIN_LABEL_PT, label_min_pt, render_aid_png, validate_visual_readiness,
)

CONTAINER_GARDENING = [
    {"visual_id": "v_ch2", "type": "workflow", "title": "Read Your Space: working sequence",
     "items": ["Identify every possible growing spot.", "Measure direct sunlight over several days.",
               "Record the number of hours each spot receives.",
               "Evaluate access to water, daily care, and harvest.",
               "Notice wind, reflected heat, and available room for supports.",
               "Match each plant choice to the conditions you actually have.",
               "Leave yourself room to move containers as the season changes."]},
    {"visual_id": "v_ch4", "type": "checklist", "title": "Use Potting Mix: field checklist",
     "items": ["[ ] Wash and inspect the container before planting",
               "[ ] Confirm that drainage holes are open at the bottom",
               "[ ] Fill the pot with fresh potting mix designed for containers"]},
    {"visual_id": "v_ch5", "type": "workflow", "title": "Pick Plants: working sequence",
     "items": ["**Sun exposure**", "**Season and temperature**", "**Climate pattern**",
               "**Container depth and size**", "**What you actually eat**",
               "**How many hours of sun does this spot get?**",
               "**Is the current season cool or warm?**", "**How deep and wide are my containers?**"]},
    {"visual_id": "v_ch6", "type": "workflow", "title": "Planting Day: working sequence",
     "items": ["Place each container in its final sunny location, check that drainage holes are open, "
               "and fill with moistened potting mix, leaving about an inch below the rim for watering space.",
               "Add supports right away for tomatoes, and for any pepper that may need help later."]},
    {"visual_id": "v_ch7", "type": "workflow", "title": "Watering: key points",
     "items": ["A good watering habit starts with your finger.", "This shallow watering wets only the surface."]},
]


@pytest.mark.parametrize("aid", CONTAINER_GARDENING, ids=lambda a: a["visual_id"])
def test_container_gardening_charts_print_at_least_8pt(aid):
    for scale in (1.0, 2.0):
        assert label_min_pt(render_aid_png(aid, scale=scale)) >= MIN_LABEL_PT


def test_the_editor_in_chief_passes_the_redrawn_charts():
    assert check_diagram_label_size(CONTAINER_GARDENING) == []


def test_the_editor_in_chief_rejects_undersized_labels():
    """A comparison table is still drawn with small text: it must be refused."""
    small = {"visual_id": "v_cmp", "type": "comparison", "title": "Pots compared",
             "table": {"headers": ["Pot", "Size", "Best for"],
                       "rows": [["Clay", "12 in", "Herbs"], ["Plastic", "16 in", "Tomatoes"]]}}
    findings = check_diagram_label_size([small])
    assert [f.code for f in findings] == ["CHART_TEXT_TOO_SMALL"]
    assert findings[0].severity == "critical"
    assert "below the 8 pt" in findings[0].summary


def test_a_chart_that_passes_at_a_wide_column_is_rejected_at_a_narrow_one():
    aid = CONTAINER_GARDENING[0]
    assert check_diagram_label_size([aid], column_pt=468) == []
    assert [f.code for f in check_diagram_label_size([aid], column_pt=300)] == ["CHART_TEXT_TOO_SMALL"]


def test_every_step_is_printed_and_no_checkbox_text_leaks():
    img = render_aid_png(CONTAINER_GARDENING[2])        # eight steps
    assert img.size[1] > 800                             # all eight rows drawn, not six
    from services.ebook_visual_pipeline import _render_steps
    import services.ebook_visual_pipeline as vp
    seen = []
    real = vp.ImageDraw.ImageDraw.text

    def spy(self, xy, text, *a, **k):
        seen.append(str(text))
        return real(self, xy, text, *a, **k)

    vp.ImageDraw.ImageDraw.text = spy
    try:
        _render_steps(CONTAINER_GARDENING[1], kind="checklist")
    finally:
        vp.ImageDraw.ImageDraw.text = real
    assert not any(t.lstrip().startswith("[") for t in seen), seen


def test_the_visuals_check_blocks_an_unreadable_chart():
    small = {"visual_id": "v_cmp", "type": "comparison", "title": "Pots compared",
             "chapter": "Choose Pots", "chapter_index": 3,
             "table": {"headers": ["Pot", "Size"], "rows": [["Clay", "12 in"]]}}
    report = validate_visual_readiness({"visual_plan": {"chapters": [
        {"chapter": "Choose Pots", "chapter_index": 3, "aids": [small]}]}})
    assert not report.ok
    assert any("at least 8 pt" in f for f in report.findings), report.findings
