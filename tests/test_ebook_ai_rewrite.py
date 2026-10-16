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


def test_manuscript_adapter_requires_authorization_without_mutation():
    from services.ebook_manuscript_editor import preview_ai_rewrite
    data = {"content": "This is the draft."}
    original = dict(data)
    result = preview_ai_rewrite(data, "clarity")
    assert result["can_apply"] is False
    assert result["rewrite"]["status"] == "provider_not_authorized"
    assert data == original


def test_manuscript_adapter_uses_existing_quality_preview(monkeypatch):
    from services import ebook_manuscript_editor as editor
    data = {"content": "An original sentence."}
    monkeypatch.setattr(editor, "preview", lambda data, proposed: {
        "edited": proposed, "can_apply": True})
    result = editor.preview_ai_rewrite(
        data, "clarity", provider=lambda _: "A clearer sentence.",
        allow_provider=True)
    assert result["can_apply"] is True
    assert result["review"]["edited"] == "A clearer sentence."
    assert result["requires_acceptance"] is True
    assert data["content"] == "An original sentence."


def test_selection_preserves_unselected_text_and_word_boundaries():
    from services.ebook_rewrite_selection import replace_selection
    assert replace_selection("Before. Middle. After.", 8, 15, "Better.") == "Before. Better. After."
    with pytest.raises(ValueError, match="inside a word"):
        replace_selection("abcdef", 1, 4, "new")


def test_selected_rewrite_uses_quality_preview_without_saving(monkeypatch):
    from services import ebook_manuscript_editor as editor
    data = {"content": "Before. Middle. After."}
    monkeypatch.setattr(editor, "preview", lambda _data, draft: {"edited": draft, "can_apply": True})
    result = editor.preview_selected_ai_rewrite(data, "clarity", 8, 15,
                provider=lambda text: "Better.", allow_provider=True)
    assert result["review"]["edited"] == "Before. Better. After."
    assert result["requires_acceptance"]
    assert data["content"] == "Before. Middle. After."


def test_selection_rejects_markdown_headings_and_tables():
    from services.ebook_rewrite_selection import selected_text
    for text in ("## Chapter One\nProse", "| Cell | Cell |", "> A quoted source"):
        with pytest.raises(ValueError, match="Markdown structure"):
            selected_text(text, 0, len(text))
