"""Recurring per-chapter section titles must not block release as "duplicates".

Root cause (project 20090): every chapter ends with a "Try This in the Next 24
Hours" exercise section — same title, different exercises. The release validator
counted headings and failed any title repeated 4+ times, so a deliberately
structured book could never pass the release gate. The refined rule only flags
repeats whose section bodies are near-copies of each other (true scaffolding);
copied bodies are additionally caught by the duplicate_paragraph check.
"""

from services.ebook_document import find_customer_content_defects


def _book_with_recurring_exercises(chapters: int = 6) -> str:
    parts = []
    topics = [
        "watering your plants on a schedule that matches the weather",
        "choosing containers with proper drainage holes for each crop",
        "checking sunlight exposure across your balcony through the day",
        "inspecting leaves and stems for early signs of common pests",
        "harvesting herbs without damaging the growing tips",
        "replanting a finished container with a fresh seasonal crop",
    ]
    for i in range(chapters):
        parts.append(
            f"## Chapter {i + 1}\n\n"
            f"This chapter teaches something distinct about {topics[i % len(topics)]}.\n\n"
            "### Try This in the Next 24 Hours\n\n"
            f"Practice {topics[i % len(topics)]} and write down what you notice.\n\n"
        )
    return "".join(parts)


def _book_with_mechanical_scaffolding(chapters: int = 4) -> str:
    parts = []
    for i in range(chapters):
        parts.append(
            f"## Chapter {i + 1}\n\n"
            f"Unique chapter intro number {i + 1}.\n\n"
            "### Key Steps\n\n"
            "Do the thing. Repeat the thing. Check the thing carefully.\n\n"
        )
    return "".join(parts)


class TestRecurringHeadings:
    def test_recurring_exercise_sections_with_distinct_bodies_pass(self):
        defects = find_customer_content_defects(_book_with_recurring_exercises())
        assert not any(d.startswith("duplicate_heading") for d in defects), defects

    def test_identical_body_scaffolding_still_fails(self):
        defects = find_customer_content_defects(_book_with_mechanical_scaffolding())
        assert any(d.startswith("duplicate_heading:key steps") for d in defects), defects

    def test_known_bad_labels_still_fail_on_any_repeat(self):
        md = (
            "## One\n\nIntro one.\n\n### Chapter Takeaway\n\nAlpha beta gamma.\n\n"
            "## Two\n\nIntro two.\n\n### Chapter Takeaway\n\nDelta epsilon zeta.\n\n"
        )
        defects = find_customer_content_defects(md)
        assert any(d.startswith("duplicate_heading:chapter takeaway") for d in defects), defects
