"""v1.9.11 -- the owner can correct a Factory chart's words; the manuscript is untouched."""
import copy
import os

os.environ["FACTORY_TEST_MODE"] = "1"

import pytest  # noqa: E402

from services import ebook_workspace_actions as wsa  # noqa: E402
from tests.test_release_review_container_gardening import (  # noqa: E402
    CH5_AS_SHIPPED, CH5_CORRECTED, CH7_AS_SHIPPED, CH7_CORRECTED, _book,
)


def _data():
    data, _, _ = _book(ch5=CH5_AS_SHIPPED, ch7=CH7_AS_SHIPPED)
    data["ebook_build"] = {"finished": True, "stages": {"export": {"status": "COMPLETE"}}}
    data["export_ready"] = True
    return data


def _aid(data, vid):
    return next(a for ch in data["visual_plan"]["chapters"] for a in ch["aids"] if a["visual_id"] == vid)


def test_chapter_5_and_7_are_corrected_and_the_book_is_marked_for_re_export():
    data = _data()
    manuscript = data["content"]
    data, msg = wsa.visuals(data, {"action": "edit-chart", "visual_id": "v_ch3",
                                   "title": "Pick Plants That Match Your Conditions: five questions to ask",
                                   "items": CH5_CORRECTED})
    data, _ = wsa.visuals(data, {"action": "edit-chart", "visual_id": "v_ch4",
                                 "title": "Watering and Feeding: key points", "items": CH7_CORRECTED})
    assert _aid(data, "v_ch3")["items"] == CH5_CORRECTED
    assert _aid(data, "v_ch4")["items"] == CH7_CORRECTED
    assert _aid(data, "v_ch4")["previous_text"]["items"] == CH7_AS_SHIPPED
    assert data["content"] == manuscript                      # never rewrites the manuscript
    assert data["export_ready"] is False
    assert data["ebook_build"]["stages"]["export"]["status"] == "NOT_STARTED"
    assert "Continue" in msg


@pytest.mark.parametrize("items", [CH5_AS_SHIPPED, CH7_AS_SHIPPED])
def test_text_the_editor_in_chief_would_refuse_is_refused(items):
    data = _data()
    before = copy.deepcopy(data)
    with pytest.raises(ValueError, match="still has a problem"):
        wsa.visuals(data, {"action": "edit-chart", "visual_id": "v_ch4", "items": items})
    assert data == before


def test_photos_cannot_be_edited_as_charts():
    with pytest.raises(ValueError, match="photo"):
        wsa.visuals(_data(), {"action": "edit-chart", "visual_id": "v_ch1", "items": ["a b c", "d e f"]})


def test_edit_chart_is_a_light_action_with_no_paid_call():
    assert "edit-chart" in wsa.VISUAL_TEXT_ACTIONS
    assert wsa.is_light("/ebook-workspace/<int:project_id>/visuals", "edit-chart")


def test_the_manuscript_and_every_other_part_of_the_book_are_byte_identical():
    import json

    data = _data()
    snapshot = copy.deepcopy(data)
    data, _ = wsa.visuals(data, {"action": "edit-chart", "visual_id": "v_ch4", "items": CH7_CORRECTED})
    changed = {k for k in set(snapshot) | set(data) if snapshot.get(k) != data.get(k)}
    assert changed == {"visual_plan", "export_ready", "ebook_build"}, changed
    assert data["content"] == snapshot["content"]
    for ch_old, ch_new in zip(snapshot["visual_plan"]["chapters"], data["visual_plan"]["chapters"]):
        for a_old, a_new in zip(ch_old["aids"], ch_new["aids"]):
            if a_old["visual_id"] != "v_ch4":
                assert json.dumps(a_old, sort_keys=True) == json.dumps(a_new, sort_keys=True)


def test_every_earlier_wording_is_kept_across_repeated_edits():
    data = _data()
    first = ["Check the mix with your finger before you water.", "Water deeply until it drains."]
    data, _ = wsa.visuals(data, {"action": "edit-chart", "visual_id": "v_ch4", "items": first})
    data, _ = wsa.visuals(data, {"action": "edit-chart", "visual_id": "v_ch4", "items": CH7_CORRECTED})
    aid = _aid(data, "v_ch4")
    assert [h["items"] for h in aid["text_history"]] == [CH7_AS_SHIPPED, first]
    assert aid["previous_text"]["items"] == first and aid["items"] == CH7_CORRECTED
