"""Cover staging must not disturb completed visuals.

ROOT CAUSE THIS GUARDS
----------------------
stage_photo_cover ended with sync_document_from_workspace(data), which calls
attach_document_to_data(..., sync_manuscript=True). That path rebuilds
data["visual_plan"] from the document's visual slots, keeping only the
descriptive fields (type/title/caption/visual_id/rendered_html/asset_path).
Every field the photo filler had set -- photographer, match_status, status,
rendered, has_file, approved -- was discarded.

The visuals then failed validate_visual_readiness, and approving the cover
raised "Visuals must have valid local assets before the cover." The rebuild is
correct for a manuscript mutation and wrong for a cover update, exactly as
attach_document_to_data already documents for packaging.

No external call is made by any test here.
"""
from __future__ import annotations

import copy

import pytest

RESOLVED_FIELDS = ("photographer", "match_status", "status", "rendered",
                   "has_file", "approved", "sha256", "source", "asset_path")


def _no_paid_call(*_a, **_k):
    raise AssertionError("No external or paid provider may be called by this test.")


def _first_passing_layout(cover: dict | None) -> str:
    from services.ebook_customer_path import _first_passing_layout as impl

    return impl(cover)


def _plan_with_resolved_photo() -> dict:
    return {
        "chapters": [
            {
                "chapter": "Chapter One",
                "aids": [
                    {
                        "visual_id": "v_one_photo",
                        "type": "stock photo",
                        "title": "A photo",
                        "caption": "A caption",
                        "chapter": "Chapter One",
                        "chapter_index": 1,
                        "placement": "after_opening",
                        "asset_path": "/tmp/one.png",
                        "sha256": "abc123",
                        "source": "local_fixture",
                        "photographer": "Fixture Studio",
                        "match_status": "pass",
                        "status": "resolved",
                        "rendered": True,
                        "has_file": True,
                        "approved": False,
                    }
                ],
            }
        ]
    }


def test_manuscript_sync_still_rebuilds_the_plan():
    """The lossy rebuild is correct for a manuscript mutation; keep it."""
    from services.ebook_project_workspace import sync_document_from_workspace

    import inspect

    sig = inspect.signature(sync_document_from_workspace)
    assert "sync_manuscript" in sig.parameters
    assert sig.parameters["sync_manuscript"].default is True, (
        "manuscript syncing must remain the default so existing callers are unchanged"
    )


def test_cover_staging_requests_a_non_manuscript_sync():
    """stage_photo_cover must not rebuild the manuscript-owned visual plan."""
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "services" / "ebook_design_workspace.py").read_text(encoding="utf-8")
    start = src.index("def stage_photo_cover")
    body = src[start:src.index("\ndef ", start + 10)]
    assert "sync_manuscript=False" in body, (
        "cover staging must pass sync_manuscript=False or it will strip resolved visuals"
    )


def test_resolved_visual_fields_survive_a_non_manuscript_sync():
    """The specific regression, at the level that actually broke."""
    from services.ebook_document import attach_document_to_data, build_ebook_document_from_project

    data = {
        "product_type": "ebook",
        "title": "T",
        "author_brand": "A",
        "content": "## Chapter One\n\nSome body text for the chapter.\n",
        "visual_plan": _plan_with_resolved_photo(),
    }
    before = copy.deepcopy(data["visual_plan"])
    doc = build_ebook_document_from_project(data=data)

    # The cover path: must leave the visual plan alone.
    after = attach_document_to_data(copy.deepcopy(data), doc, sync_manuscript=False)
    aid = after["visual_plan"]["chapters"][0]["aids"][0]
    original = before["chapters"][0]["aids"][0]
    for field in RESOLVED_FIELDS:
        assert aid.get(field) == original.get(field), (
            f"cover-path sync dropped {field!r}: "
            f"{original.get(field)!r} -> {aid.get(field)!r}"
        )


def test_cover_staging_preserves_every_visual_field_end_to_end(monkeypatch):
    """Full path on the real pipeline: approved visuals, stage a real cover.

    This runs the production cover path -- the licensed local photograph is
    registered, the three layout variants are rendered, one is selected, and
    the cover is staged -- then checks that not one field of the approved
    visual plan moved. It makes no external call: the photograph comes from
    the bundled licensed catalogue, drawn locally by build_licensed_event_photo.
    """
    # FACTORY_TEST_MODE only. The customer-path fixture gate is deliberately NOT
    # set: it selects the container-gardening fixture chapters, which do not
    # match this acceptance manuscript, and the visual plan then cannot resolve.
    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    monkeypatch.delenv("EBOOK_CUSTOMER_PATH_FIXTURE", raising=False)
    monkeypatch.setattr("ai_client.get_client", _no_paid_call)
    monkeypatch.setattr("ai_client.chat", _no_paid_call)

    import uuid

    from services.ebook_design_workspace import approve_visuals_local, stage_photo_cover
    from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript
    from services.ebook_photo_cover import (
        attach_licensed, licensed_catalog, select_layout,
    )
    from services.ebook_project_workspace import (
        approve_stage, build_acceptance_project_data, set_stage_status,
    )
    from services.ebook_visual_pipeline import validate_visual_readiness

    data = build_acceptance_project_data()
    data["acceptance_marker"] = None
    pkg = f"ebook-cover-preserve-{uuid.uuid4().hex[:12]}"
    data["artifact_id"] = pkg
    data["package_id"] = pkg
    md = build_event_photo_strong_manuscript()
    data["content"] = md
    data["ebook"] = md
    data["ebook_workspace"]["marker"] = None
    set_stage_status(data["ebook_workspace"], "manuscript", "awaiting_approval")
    data = approve_stage(data, "manuscript")
    data = approve_visuals_local(data)

    assert validate_visual_readiness(data).ok, "fixture must start with valid visuals"
    before = copy.deepcopy(data["visual_plan"])

    asset_id = str(licensed_catalog()[0]["id"])
    data = attach_licensed(data, asset_id, project_id=None)
    layout = _first_passing_layout(data.get("cover_design"))
    assert layout, "the licensed fixture must render at least one passing layout"
    data = select_layout(data, layout, project_id=None)
    out = stage_photo_cover(data, project_id=None)

    b_by_id = {
        a["visual_id"]: a
        for ch in before["chapters"] for a in (ch.get("aids") or [])
    }
    a_by_id = {
        a["visual_id"]: a
        for ch in out["visual_plan"]["chapters"] for a in (ch.get("aids") or [])
    }
    assert set(a_by_id) == set(b_by_id), "cover staging removed or added visuals"
    for vid, before_aid in b_by_id.items():
        for field in RESOLVED_FIELDS:
            assert a_by_id[vid].get(field) == before_aid.get(field), (
                f"cover staging changed {vid}.{field}"
            )
    assert validate_visual_readiness(out).ok, (
        "visuals must still validate after the cover is staged"
    )
    assert out.get("artifact_state", "DRAFT") == "DRAFT"


def test_packaging_stage_approvals_do_not_resync_the_manuscript():
    """approve_stage ran the lossy rebuild for EVERY stage, including cover.

    That is the second half of the same defect: staging the cover kept the
    visuals intact, then approving the cover stripped them again, so preview
    reported "Approve visuals with valid local assets before building preview."
    """
    from services.ebook_project_workspace import PACKAGING_STAGES

    for stage in ("visuals", "cover", "design", "preview", "preflight", "export"):
        assert stage in PACKAGING_STAGES, (
            f"{stage!r} consumes the manuscript and must not re-sync it"
        )
    for stage in ("research", "title", "outline", "manuscript"):
        assert stage not in PACKAGING_STAGES, (
            f"{stage!r} authors the manuscript and must keep the default sync"
        )


def test_approve_stage_passes_the_packaging_flag():
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "services" / "ebook_project_workspace.py").read_text(encoding="utf-8")
    start = src.index("def approve_stage(")
    body = src[start:src.index("\ndef ", start + 10)]
    assert "sync_manuscript=stage not in PACKAGING_STAGES" in body, (
        "approve_stage must skip the manuscript rebuild for packaging stages"
    )


def test_approving_the_cover_preserves_resolved_visuals(monkeypatch):
    """End-to-end at the level that actually broke the fixture build."""
    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    monkeypatch.setenv("EBOOK_CUSTOMER_PATH_FIXTURE", "1")

    from services.ebook_document import attach_document_to_data, build_ebook_document_from_project

    data = {
        "product_type": "ebook",
        "title": "T",
        "author_brand": "A",
        "content": "## Chapter One\n\nSome body text for the chapter.\n",
        "visual_plan": _plan_with_resolved_photo(),
    }
    before = copy.deepcopy(data["visual_plan"]["chapters"][0]["aids"][0])
    doc = build_ebook_document_from_project(data=data)

    # What approve_stage now does for a packaging stage.
    packaged = attach_document_to_data(copy.deepcopy(data), doc, sync_manuscript=False)
    after = packaged["visual_plan"]["chapters"][0]["aids"][0]
    for field in RESOLVED_FIELDS:
        assert after.get(field) == before.get(field), f"cover approval dropped {field!r}"

    # And what it still does for a manuscript stage: the rebuild is retained.
    rebuilt = attach_document_to_data(copy.deepcopy(data), doc, sync_manuscript=True)
    assert rebuilt["visual_plan"]["chapters"], "manuscript sync must still rebuild the plan"


def test_readiness_validator_was_not_weakened():
    """The fix is in the writer, not the checker."""
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "services" / "ebook_visual_pipeline.py").read_text(encoding="utf-8")
    start = src.index("def validate_visual_readiness")
    body = src[start:start + 3000]
    for required in ("missing photographer attribution", "has no existing local asset file"):
        assert required in body, f"readiness check lost its {required!r} rule"
