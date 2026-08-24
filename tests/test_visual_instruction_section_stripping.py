"""Leaked visual-production sections must be removed whole, not just their heading.

Root cause (project 1961): strip_visual_instructions() matched the heading
"### Visual plan for this chapter" and set skip_block, but the very next line
in any markdown document is blank — and the loop treated a blank line as the
end of the block. The bullet body it introduces ("**Chart suggestion:** ...",
"**Diagram suggestion:** ...", "**Photo placement:** ...") therefore survived
into the customer manuscript and shipped inside the PDF.
"""

import re

from services.ebook_document import find_customer_content_defects, strip_visual_instructions

LEAKED = """# Money Guide

## Chapter One

Real prose that the customer is supposed to read, with enough words to look
like an actual paragraph of a real book chapter.

### Visual plan for this chapter

- **Chart suggestion:** A four-column comparison chart showing income types.
- **Diagram suggestion:** A simple flow diagram from skill to payment.
- **Photo placement:** A photo of a young adult working at a desk.

### A clearer view before you move on

More real prose that must be kept in the finished book for the reader.

## Chapter Two

Another real chapter body that must survive the cleaning pass untouched.
"""


class TestVisualInstructionSectionStripping:
    def test_entire_instruction_section_is_removed(self):
        cleaned, removed = strip_visual_instructions(LEAKED)
        low = cleaned.lower()
        for phrase in (
            "visual plan for this chapter",
            "chart suggestion",
            "diagram suggestion",
            "photo placement",
        ):
            assert phrase not in low, f"{phrase!r} leaked into customer manuscript"
        assert removed, "removal must be reported"

    def test_real_content_and_structure_survive(self):
        cleaned, _ = strip_visual_instructions(LEAKED)
        assert "Real prose that the customer is supposed to read" in cleaned
        assert "More real prose that must be kept" in cleaned
        assert "Another real chapter body" in cleaned
        # Both H2 chapters and the following H3 keep their place.
        assert len(re.findall(r"^##\s+Chapter", cleaned, re.M)) == 2
        assert "### A clearer view before you move on" in cleaned

    def test_defect_scan_is_clean_after_stripping(self):
        cleaned, _ = strip_visual_instructions(LEAKED)
        defects = [
            d
            for d in find_customer_content_defects(cleaned)
            if d.startswith("leaked_visual_instruction")
        ]
        assert defects == [], defects

    def test_manuscript_without_instructions_is_unchanged(self):
        plain = "# T\n\n## One\n\nJust ordinary prose here for the reader.\n"
        cleaned, removed = strip_visual_instructions(plain)
        assert "Just ordinary prose here for the reader." in cleaned
        assert removed == []
