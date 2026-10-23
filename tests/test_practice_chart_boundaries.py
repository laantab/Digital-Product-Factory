"""A chapter's questions and section introductions cannot become workflow steps."""
import copy

from services import ebook_visual_pipeline as vp
from services.ebook_release_review import chart_wording_findings

BODY = """## Clear Counters

Begin with every item on the countertop. Take a quick look and ask:

- Do I use this often?
- Does it need to stay plugged in?

Keep only true daily essentials out.
Put these in the most reachable shelf.

Keep zones basic and practical:

### Cooking zone
Place pots, pans, and spices near the stove.

Try three routines:

- **Nightly reset:** Put away dishes and wipe counters.
"""


def test_practice_chart_preserves_structural_boundaries_and_passes_review():
    aid = vp.derive_local_aid_from_prose(1, "Clear Counters", BODY)
    assert aid["items"] == [
        "Begin with every item on the countertop.",
        "Keep only true daily essentials out.",
        "Place pots, pans, and spices near the stove.",
    ]
    assert chart_wording_findings(aid, page=None, chapter="Clear Counters") == []


def test_redraw_recovers_saved_generated_wording_and_keeps_history(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "EXPORTS_DIR", str(tmp_path))
    aid = vp.derive_local_aid_from_prose(1, "Clear Counters", BODY)
    bad = [aid["items"][0], "Take a quick look and ask: - Do I use this often?", aid["items"][1]]
    aid["items"] = bad
    plan = {"chapters": [{"chapter": "Clear Counters", "chapter_index": 1,
                          "chapter_body": BODY, "aids": [aid]}]}
    before = copy.deepcopy(plan)
    result = vp.materialize_visual_plan(plan, package_id="boundary-recovery")
    fixed = result["chapters"][0]["aids"][0]
    assert chart_wording_findings(fixed, page=None, chapter="Clear Counters") == []
    assert fixed["text_history"][0]["items"] == bad
    assert plan == before
    assert fixed["status"] == "resolved"


def test_redraw_does_not_replace_owner_edited_words(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "EXPORTS_DIR", str(tmp_path))
    aid = vp.derive_local_aid_from_prose(1, "Clear Counters", BODY)
    aid.update(items=["Is this used daily?", "Keep this next to the stove."], text_edited={"by": "owner"})
    result = vp.materialize_visual_plan({"chapters": [{"chapter": "Clear Counters",
        "chapter_index": 1, "chapter_body": BODY, "aids": [aid]}]}, package_id="owner-edit")
    assert result["chapters"][0]["aids"][0]["items"] == aid["items"]
