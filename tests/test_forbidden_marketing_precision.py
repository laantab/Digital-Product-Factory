"""Marketing-claim blocking must catch hype without blocking subject vocabulary.

Root cause (project 14626, a teen online-safety guide): FOREVER_FORBIDDEN_MARKETING
contained the bare token "secret", so legitimate safeguarding language — "people
who pressure teens for photos, secrets", "meeting someone in secret", "I don't
talk in secret from my parents" — was reported as a forbidden marketing claim
and blocked the export. The rule now lists the hype constructions instead.
"""

from services.ebook_quality_agent import _find_forbidden_marketing

SAFETY_PROSE = (
    "Contact risk can include strangers who ask personal questions or people "
    "who pressure teens for photos, secrets, or private chats. Teach a teen to "
    "say: I don't talk in secret from my parents. Meeting someone in secret is "
    "the single riskiest step, so agree on that rule early."
)


class TestLegitimateSubjectVocabulary:
    def test_safeguarding_language_is_not_a_marketing_claim(self):
        assert _find_forbidden_marketing(SAFETY_PROSE) == []

    def test_ordinary_secret_usage_allowed(self):
        for line in (
            "Keep your password secret.",
            "She kept the surprise party a secret.",
            "Trade secrets are protected by law.",
        ):
            assert _find_forbidden_marketing(line) == [], line


class TestHypeStillBlocked:
    def test_secret_hype_constructions_still_fail(self):
        for line in (
            "This is the secret formula for passive income.",
            "Learn the secret method nobody teaches.",
            "The secret to overnight riches.",
            "An insider secret from the industry.",
        ):
            assert _find_forbidden_marketing(line), line

    def test_other_forbidden_claims_unaffected(self):
        assert _find_forbidden_marketing("Results are guaranteed.")
        assert _find_forbidden_marketing("A miracle cure for back pain.")
        assert _find_forbidden_marketing("This is scientifically proven.")

    def test_honest_negation_still_allowed(self):
        assert _find_forbidden_marketing("Results are not guaranteed.") == []
