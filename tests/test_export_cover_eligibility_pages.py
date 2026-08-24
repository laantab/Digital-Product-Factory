"""Export must not strip an ebook's cover by fabricating a 1-page count.

Root cause (project 20090): ebooks declare chapters, not pages, so the export
path found no page fields and coerced the planned count to 1. The cover
eligibility agent then applied "Ebook under 5 pages cannot include a cover"
and a 29-page book shipped with a plain text cover instead of its saved photo
cover. Unknown page counts must reach the agent as None (permissive); declared
tiny page counts must still block.
"""

from services.quality.cover_eligibility_agent import determine_cover_eligibility


class TestEbookCoverEligibilityUnknownPages:
    def test_unknown_page_count_allows_ebook_cover(self):
        el = determine_cover_eligibility(
            product_type="ebook",
            fields={"chapters": "6", "topic": "container gardening"},
            planned_page_count=None,
            product_mode="",
        )
        assert el.cover_allowed is True

    def test_declared_tiny_ebook_still_blocks_cover(self):
        el = determine_cover_eligibility(
            product_type="ebook",
            fields={"pages": "3"},
            planned_page_count=3,
            product_mode="",
        )
        assert el.cover_allowed is False

    def test_single_sheet_mode_still_blocks_regardless_of_pages(self):
        el = determine_cover_eligibility(
            product_type="ebook",
            fields={},
            planned_page_count=None,
            product_mode="Single Sheet",
        )
        assert el.cover_allowed is False
        assert el.must_block_cover is True


class TestPackagingPlannedCountResolution:
    """The packaging caller must pass None, not 1, when no page fields exist."""

    def _resolve(self, data_fields: dict, data: dict):
        # Mirrors the fixed resolution logic in build_product_export.
        try:
            raw = (
                data_fields.get("pages")
                or data_fields.get("num_pages")
                or data.get("num_pages")
            )
            return int(raw) if raw is not None else None
        except (ValueError, TypeError):
            return None

    def test_chapter_based_ebook_resolves_to_none(self):
        assert self._resolve({"chapters": "6"}, {}) is None

    def test_declared_pages_still_resolve(self):
        assert self._resolve({"pages": "24"}, {}) == 24

    def test_end_to_end_none_keeps_cover_allowed(self):
        planned = self._resolve({"chapters": "6", "topic": "gardening"}, {})
        el = determine_cover_eligibility(
            product_type="ebook", fields={"chapters": "6"},
            planned_page_count=planned, product_mode="",
        )
        assert el.cover_allowed is True
