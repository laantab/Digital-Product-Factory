"""Subject-led classification must match whole words, not bare substrings.

Root cause (project 14626, "How to keep your teen safe online"): the subtitle
"practical, calm guidance for parents and teens" classified the ENTIRE book as
photo_led / demonstration-led, because "dance" -- a literal hint token meant
for dance-instruction books -- is a substring of "guidance". Every chapter
was then required to show a literal how-to/technique photograph, including
the book's own Table of Contents, and the export was blocked.

The same bare-substring bug pattern applies to other short hint tokens
("cat" inside "vacation", "dog" inside "dogma", "pet" inside "carpet"), so
this is fixed once at the matching layer, not by removing "dance" from the
list -- a real dance-instruction book must still classify as photo_led.
"""

from services.ebook_visual_match import classify_ebook_subject


class TestWordBoundaryHintMatching:
    def test_guidance_does_not_trigger_dance_hint(self):
        result = classify_ebook_subject(
            title="How to keep your teen safe online",
            topic="How to keep your teen safe online",
            content=(
                "How to Keep Your Teen Safe Online\n"
                "Practical, calm guidance for parents and teens to build "
                "smart habits, stronger boundaries, and better digital safety"
            ),
        )
        assert result == "information_led"

    def test_real_dance_book_still_classifies_photo_led(self):
        result = classify_ebook_subject(
            title="Beginner Ballroom Dance",
            topic="learning basic dance steps",
            content="This guide teaches you how to dance the waltz step by step.",
        )
        assert result == "photo_led"

    def test_vacation_does_not_trigger_cat_hint(self):
        result = classify_ebook_subject(
            title="Planning Your Vacation Budget",
            topic="vacation budgeting and expense tracking",
            content="A vacation does not have to break your budget.",
        )
        assert result == "information_led"

    def test_real_cat_book_still_classifies_photo_led(self):
        result = classify_ebook_subject(
            title="Caring for Your New Cat",
            topic="cat care for new pet owners",
            content="Every cat needs fresh water and a clean litter box.",
        )
        assert result == "photo_led"

    def test_carpet_does_not_trigger_pet_hint(self):
        result = classify_ebook_subject(
            title="Home Office Organization",
            topic="organizing a small home office",
            content="Choose a carpet that is easy to clean under a desk chair.",
        )
        assert result == "information_led"
