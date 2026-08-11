"""Gate 10: artifact state model and revision-transition primitives.

Pure unit coverage — does not wire Generate / enhance / cover / packaging routes.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""

from services.quality.artifact_state import (  # noqa: E402
    ArtifactState,
    ArtifactStateError,
    apply_metadata_fields,
    assert_content_mutable,
    approve_artifact_revision,
    current_revision,
    has_verified_approval_evidence,
    has_verified_lock_evidence,
    resolve_artifact_state,
    transition_artifact_revision,
)


def _draft(**extra):
    base = {
        "product_type": "math_worksheet",
        "title": "Gate10 Draft",
        "package_id": "gate10-draft-pkg-001",
        "artifact_revision": 1,
        "problems": [{"prompt": "1+1", "answer": "2"}],
    }
    base.update(extra)
    return base


def _approved(**extra):
    base = _draft(
        title="Gate10 Approved",
        package_id="gate10-approved-pkg-001",
        content_digest="a" * 64,
        asset_manifest_digest="b" * 64,
        qa_status="accepted",
        product_exports={
            "pdf": {"url": "/download/gate10-approved-pkg-001/sheet.pdf"},
            "files": {"meta": {"package_id": "gate10-approved-pkg-001"}},
        },
        export_package_id="gate10-approved-pkg-001",
        exports={"folder": "exports/gate10-approved-pkg-001"},
    )
    base.update(extra)
    return base


def _locked(**extra):
    base = _approved(
        title="Gate10 Locked",
        package_id="gate10-locked-pkg-001",
        book_locked=True,
        lock_status="LOCKED",
        locked_at="2026-08-10T00:00:00Z",
    )
    base.update(extra)
    return base


class ArtifactStateRevisionPrimitivesTests(unittest.TestCase):
    def test_01_explicit_states_resolve(self):
        self.assertEqual(
            resolve_artifact_state({"artifact_state": "DRAFT"}), ArtifactState.DRAFT
        )
        self.assertEqual(
            resolve_artifact_state(
                {
                    "artifact_state": "APPROVED",
                    "content_digest": "a" * 64,
                    "asset_manifest_digest": "b" * 64,
                }
            ),
            ArtifactState.APPROVED,
        )
        self.assertEqual(
            resolve_artifact_state({"artifact_state": "LOCKED"}), ArtifactState.LOCKED
        )
        self.assertEqual(
            resolve_artifact_state({"artifact_state": ArtifactState.DRAFT}),
            ArtifactState.DRAFT,
        )

    def test_02_legacy_verified_lock_evidence_resolves_locked(self):
        # In-project markers
        self.assertEqual(resolve_artifact_state({"book_locked": True}), ArtifactState.LOCKED)
        self.assertEqual(
            resolve_artifact_state({"lock_status": "LOCKED"}), ArtifactState.LOCKED
        )
        # Committed Thunder Volt package-acceptance lock JSON (read-only registry)
        lock_path = ROOT / "THUNDER_VOLT_COLORING_BOOK_PACKAGE_ACCEPTANCE_LOCK.json"
        self.assertTrue(lock_path.is_file(), "committed lock JSON must exist")
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        pkg = str(payload["package_id"])
        self.assertTrue(payload.get("book_locked") or payload.get("lock_status") == "LOCKED")
        legacy = {
            "product_type": "coloring_book",
            "package_id": pkg,
            "title": "Thunder Volt Coloring Book",
        }
        self.assertTrue(has_verified_lock_evidence(legacy))
        self.assertEqual(resolve_artifact_state(legacy), ArtifactState.LOCKED)

    def test_03_legacy_verified_approval_evidence_resolves_approved(self):
        legacy = {
            "product_type": "math_worksheet",
            "package_id": "legacy-approved-001",
            "content_digest": "c" * 64,
            "asset_manifest_digest": "d" * 64,
        }
        self.assertTrue(has_verified_approval_evidence(legacy))
        self.assertEqual(resolve_artifact_state(legacy), ArtifactState.APPROVED)
        # Digests alone must not yield DRAFT merely because artifact_state is absent.
        self.assertIsNone(legacy.get("artifact_state"))

    def test_04_unapproved_legacy_resolves_draft(self):
        legacy = {
            "product_type": "math_worksheet",
            "package_id": "legacy-draft-001",
            "problems": [],
        }
        self.assertEqual(resolve_artifact_state(legacy), ArtifactState.DRAFT)
        self.assertEqual(resolve_artifact_state({}), ArtifactState.DRAFT)
        self.assertEqual(resolve_artifact_state(None), ArtifactState.DRAFT)

    def test_05_invalid_or_conflicting_evidence_fails_safely(self):
        with self.assertRaises(ArtifactStateError):
            resolve_artifact_state({"artifact_state": "BOGUS"})
        with self.assertRaises(ArtifactStateError):
            resolve_artifact_state(
                {"artifact_state": "DRAFT", "book_locked": True}
            )
        with self.assertRaises(ArtifactStateError):
            resolve_artifact_state(
                {
                    "artifact_state": "APPROVED",
                    "lock_status": "LOCKED",
                    "content_digest": "a" * 64,
                    "asset_manifest_digest": "b" * 64,
                }
            )

    def test_06_draft_metadata_updates_do_not_bump_revision(self):
        record = _draft(artifact_state="DRAFT", artifact_revision=3)
        original = copy.deepcopy(record)
        updated = apply_metadata_fields(
            record, {"audience": "Grade 3", "goal": "Practice"}
        )
        self.assertEqual(current_revision(updated), 3)
        self.assertEqual(resolve_artifact_state(updated), ArtifactState.DRAFT)
        self.assertEqual(updated["audience"], "Grade 3")
        self.assertEqual(record, original)
        with self.assertRaises(ArtifactStateError):
            apply_metadata_fields(record, {"content_digest": "e" * 64})

    def test_07_approved_metadata_updates_do_not_bump_revision(self):
        record = _approved(artifact_state="APPROVED", artifact_revision=2)
        original = copy.deepcopy(record)
        updated = apply_metadata_fields(
            record, {"seller_notes": "ready", "listing_title": "Add Facts"}
        )
        self.assertEqual(current_revision(updated), 2)
        self.assertEqual(resolve_artifact_state(updated), ArtifactState.APPROVED)
        self.assertEqual(updated["seller_notes"], "ready")
        self.assertEqual(record, original)
        self.assertEqual(updated["content_digest"], original["content_digest"])

    def test_08_approved_content_edits_cannot_occur_in_place(self):
        record = _approved()
        with self.assertRaises(ArtifactStateError) as ctx:
            assert_content_mutable(record)
        self.assertIn("APPROVED", str(ctx.exception))
        # Helper must not mutate the record while rejecting.
        self.assertTrue(has_verified_approval_evidence(record))

    def test_09_approved_to_new_draft_preserves_approved_revision(self):
        record = _approved(artifact_revision=4)
        new = transition_artifact_revision(record, reason="user requested edit")
        self.assertEqual(resolve_artifact_state(new), ArtifactState.DRAFT)
        self.assertEqual(new["artifact_revision"], 5)
        prior = new["prior_approved_revision"]
        self.assertEqual(prior["artifact_revision"], 4)
        self.assertEqual(prior["artifact_state"], ArtifactState.APPROVED.value)
        self.assertEqual(prior["content_digest"], record["content_digest"])
        self.assertEqual(
            prior["asset_manifest_digest"], record["asset_manifest_digest"]
        )
        self.assertEqual(new["artifact_lineage"][-1]["artifact_revision"], 4)

    def test_10_new_revision_clears_approval_lock_and_export_refs(self):
        record = _approved(
            book_locked=False,
            lock_status="",
            artifact_revision=1,
        )
        # Ensure source resolves APPROVED (not LOCKED).
        self.assertEqual(resolve_artifact_state(record), ArtifactState.APPROVED)
        new = transition_artifact_revision(record, reason="revise interior")
        self.assertIsNone(new.get("content_digest"))
        self.assertIsNone(new.get("asset_manifest_digest"))
        self.assertIsNone(new.get("qa_status"))
        self.assertFalse(new.get("book_locked"))
        self.assertIsNone(new.get("lock_status"))
        self.assertIsNone(new.get("locked_at"))
        self.assertNotIn("product_exports", new)
        self.assertNotIn("export_package_id", new)
        self.assertNotIn("exports", new)
        self.assertEqual(new["artifact_state"], ArtifactState.DRAFT.value)
        self.assertFalse(has_verified_approval_evidence(new))

    def test_11_locked_new_revision_rejected(self):
        record = _locked()
        self.assertEqual(resolve_artifact_state(record), ArtifactState.LOCKED)
        with self.assertRaises(ArtifactStateError) as ctx:
            transition_artifact_revision(record, reason="should fail")
        self.assertIn("LOCKED", str(ctx.exception))
        with self.assertRaises(ArtifactStateError):
            assert_content_mutable(record)

    def test_12_original_input_record_unchanged(self):
        record = _approved(artifact_revision=7)
        snapshot = copy.deepcopy(record)
        _ = transition_artifact_revision(record, reason="fork draft")
        self.assertEqual(record, snapshot)
        meta = apply_metadata_fields(record, {"audience": "kids"})
        self.assertEqual(record, snapshot)
        self.assertNotEqual(meta.get("audience"), record.get("audience"))
        draft_src = {
            **_draft(),
            "artifact_state": ArtifactState.DRAFT.value,
            "content_digest": "f" * 64,
            "asset_manifest_digest": "e" * 64,
        }
        draft_snap = copy.deepcopy(draft_src)
        approved = approve_artifact_revision(draft_src, reason="qa accepted")
        self.assertEqual(draft_src, draft_snap)
        self.assertEqual(resolve_artifact_state(approved), ArtifactState.APPROVED)

    def test_13_revision_identifiers_deterministic_and_collision_safe(self):
        record = _approved(artifact_revision=1)
        r2 = transition_artifact_revision(record, reason="edit-1")
        self.assertEqual(r2["artifact_revision"], 2)
        # Re-approve the new draft (stamp digests) then transition again.
        r2_approved = {
            **r2,
            "content_digest": "1" * 64,
            "asset_manifest_digest": "2" * 64,
            "artifact_state": ArtifactState.APPROVED.value,
        }
        r3 = transition_artifact_revision(r2_approved, reason="edit-2")
        self.assertEqual(r3["artifact_revision"], 3)
        # Same input always yields the same next revision.
        again = transition_artifact_revision(record, reason="edit-1-repeat")
        self.assertEqual(again["artifact_revision"], 2)
        # Missing / junk revision normalizes then increments deterministically.
        messy = _approved()
        messy["artifact_revision"] = "not-a-number"
        out = transition_artifact_revision(messy, reason="normalize")
        self.assertEqual(out["artifact_revision"], 2)

    def test_14_no_paid_external_generation_or_export_calls(self):
        targets = [
            "services.product.generate_product",
            "services.packaging.build_product_export",
            "services.ebook_package.build_ebook_package",
        ]
        record = _approved()
        with patch("services.product.generate_product") as gen, patch(
            "services.packaging.build_product_export"
        ) as export, patch(
            "services.ebook_package.build_ebook_package", create=True
        ) as ebook:
            resolve_artifact_state(record)
            apply_metadata_fields(record, {"goal": "x"})
            assert_content_mutable(_draft())
            transition_artifact_revision(record, reason="unit")
            approve_artifact_revision(
                {
                    **_draft(),
                    "artifact_state": ArtifactState.DRAFT.value,
                    "content_digest": "9" * 64,
                    "asset_manifest_digest": "8" * 64,
                },
                reason="approve",
            )
            gen.assert_not_called()
            export.assert_not_called()
            ebook.assert_not_called()
        # Network/paid keys remain blank for this focused module.
        self.assertFalse(os.environ.get("OPENAI_API_KEY"))
        self.assertFalse(os.environ.get("TAVILY_API_KEY"))
        _ = targets  # documented surface under patch


if __name__ == "__main__":
    unittest.main()
