"""Front/back matter must never be scored for a content visual requirement.

Root cause (project 14626): a visual_plan's own "Table of Contents" entry was
evaluated the same as a real content chapter and required to show a
"demonstration" photograph -- a Table of Contents page cannot show a
how-to technique, so this could never be satisfied and blocked export
regardless of how complete the actual book was.
"""

from services.ebook_visual_requirements import validate_visual_plan_typed


def _plan(chapters):
    return {"chapters": [{"chapter": name, "aids": []} for name in chapters]}


class TestFrontBackMatterExcluded:
    def test_table_of_contents_has_no_requirement(self):
        plan = _plan(["Table of Contents", "Getting Started"])
        result = validate_visual_plan_typed(
            plan,
            content_md="## Getting Started\n\nReal chapter content here.",
            title="Some Book",
            topic="a demonstration-led craft topic",
        )
        chapters = {
            c["chapter"]: c
            for c in result.get("unresolved_visual_requirements", [])
        }
        assert "Table of Contents" not in chapters

    def test_other_front_matter_labels_excluded(self):
        for label in (
            "Introduction",
            "Summary",
            "Conclusion",
            "About the Author",
            "Disclaimer",
            "Copyright",
            "References",
        ):
            plan = _plan([label, "Real Chapter"])
            result = validate_visual_plan_typed(
                plan,
                content_md="## Real Chapter\n\nContent.",
                title="T",
                topic="woodworking",
            )
            names = {c["chapter"] for c in result.get("unresolved_visual_requirements", [])}
            assert label not in names, label

    def test_real_content_chapters_still_get_requirements(self):
        plan = _plan(["Table of Contents", "Learning the Waltz Step"])
        result = validate_visual_plan_typed(
            plan,
            content_md="## Learning the Waltz Step\n\nHow to do the waltz step by step.",
            title="Beginner Ballroom Dance",
            topic="learning basic dance steps",
        )
        names = {c["chapter"] for c in result.get("unresolved_visual_requirements", [])}
        assert "Learning the Waltz Step" in names
        assert "Table of Contents" not in names
