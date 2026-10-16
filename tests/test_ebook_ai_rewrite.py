"""The new rewrite feature must remain opt-in, reversible and cost-free."""
import pytest
from services.ebook_ai_rewrite import proposal


def test_default_does_not_invoke_a_provider():
    calls = []
    out = proposal("Keep this exact original.", "clarity",
                   provider=lambda text: calls.append(text) or "Change")
    assert out["status"] == "provider_not_authorized"
    assert out["proposed"] == out["original"]
    assert out["paid_calls"] == 0
    assert not calls


def test_authorized_local_provider_returns_suggestion_not_saved_book():
    original = "This passage is somewhat complicated."
    out = proposal(original, "clarity", provider=lambda _: "This passage is clear.",
                   allow_provider=True)
    assert out["status"] == "review_required"
    assert out["original"] == original
    assert out["proposed"] == "This passage is clear."
    assert out["requires_review"]
    assert out["paid_calls"] == 0


def test_rejects_unsafe_structural_change():
    with pytest.raises(ValueError, match="protected"):
        proposal("## Chapter One\nText", "shorten",
                 provider=lambda _: "## New Chapter\nShort", allow_provider=True)


def test_rejects_link_changes():
    with pytest.raises(ValueError, match="protected"):
        proposal("Source: https://example.com/x", "clarity",
                 provider=lambda _: "Source: https://wrong.example/x", allow_provider=True)


def test_paid_mode_and_invalid_mode_rejected():
    with pytest.raises(ValueError, match="cost gate"):
        proposal("Test", "friendly", provider=lambda s: s,
                 allow_provider=True, allow_paid=True)
    with pytest.raises(ValueError, match="Unsupported"):
        proposal("Test", "fabricate", allow_provider=False)
