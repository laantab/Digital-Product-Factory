from unittest.mock import patch
from io import BytesIO

from pypdf import PdfReader

from services.factory.topic_word_source import TopicWordResult
from services.word_search import word_lists
from services.crossword import word_entries
from services.word_search.pdf_builder import WordSearchPdfRequest, build_word_search_pdf
from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf


def _fake_legacy_topics():
    # Reproduces the old accidental Beekeeping -> generic insect pack match.
    return {"topics": [{"id": "insects", "keywords": ["bee", "insect", "wasp"],
                        "words": ["ANT", "WASP", "BEETLE", "MOTH"]}]}


def _free_words(*, crossword=False):
    words = ["APIARY", "HIVE", "HONEY", "NECTAR", "POLLEN", "QUEEN", "WORKER", "WAX"]
    return TopicWordResult(words=words, warnings=["Found free words"], source="datamuse")


def test_beekeeping_uses_free_topic_words_in_word_search_not_insect_pack():
    with patch.object(word_lists, "_load_topics_data", return_value=_fake_legacy_topics()), \
         patch("services.factory.topic_word_source.lookup_topic_words", side_effect=lambda *a, **k: _free_words()):
        words, warnings, errors, source = word_lists.suggest_words_from_topic("Beekeeping", max_words=12)

    assert errors == []
    assert {"Apiary", "Hive", "Honey"}.issubset(set(words))
    assert not {"Ant", "Wasp", "Beetle", "Moth"}.intersection(words)
    assert source == "datamuse"
    assert any("Used free vocabulary source" in warning for warning in warnings)


def test_curated_shared_topic_pack_does_not_call_free_source():
    with patch("services.factory.topic_word_source.lookup_topic_words",
               side_effect=AssertionError("curated pack must win before free lookup")):
        words, warnings, errors, source = word_lists.suggest_words_from_topic("House Plants", max_words=12)

    assert errors == []
    assert len(words) == 12
    assert source == "house_plants"
    assert any("Used local vocabulary pack" in warning for warning in warnings)


def test_beekeeping_uses_free_topic_words_in_crossword_not_insect_pack():
    with patch.object(word_entries, "_load_topics_data", return_value=_fake_legacy_topics()), \
         patch("services.factory.topic_word_source.lookup_topic_words", side_effect=lambda *a, **k: _free_words(crossword=True)), \
         patch("services.crossword.clues.simple_clue", side_effect=lambda answer, theme="": f"Specific clue for {answer} in {theme}."):
        words, warnings, errors = word_entries.suggest_crossword_words_from_topic("Beekeeping", max_words=12)

    assert errors == []
    assert {"APIARY", "HIVE", "HONEY"}.issubset(set(words))
    assert not {"ANT", "WASP", "BEETLE", "MOTH"}.intersection(words)
    assert any("Used free vocabulary source" in warning for warning in warnings)


def test_crossword_short_free_result_fails_with_custom_list_message():
    thin = TopicWordResult(words=["HIVE", "HONEY"], errors=["Only two results."])
    with patch.object(word_entries, "_load_topics_data", return_value={"topics": []}), \
         patch("services.factory.topic_word_source.lookup_topic_words", return_value=thin):
        words, _warnings, errors = word_entries.suggest_crossword_words_from_topic("Rare topic", max_words=12)

    assert words == []
    assert errors
    assert "custom word list" in errors[0].lower()


def test_crossword_does_not_accept_broad_local_clues_for_free_topic_words():
    # The generic local clue rules can describe a word without actually
    # explaining why it belongs in a beekeeping crossword. Do not ship that
    # weak set just because Datamuse returned enough candidate spellings.
    with patch("services.factory.topic_word_source.lookup_topic_words", return_value=TopicWordResult(
        words=["APIARY", "HIVE", "HONEY", "NECTAR", "POLLEN", "WAX",
               "LARVA", "DRONE", "COMB", "BEE", "WORKER", "QUEEN"],
        source="datamuse",
    )):
        words, _warnings, errors = word_entries.suggest_crossword_words_from_topic(
            "Beekeeping", max_words=12,
        )

    assert words == []
    assert errors
    assert "custom word list" in errors[0].lower()


def test_factory_word_search_topic_path_puts_free_words_in_the_real_pdf():
    candidates = ["APIARY", "HIVE", "HONEY", "NECTAR", "POLLEN", "WAX",
                  "LARVA", "DRONE", "COMB", "BEE", "WORKER", "QUEEN"]
    result_words = TopicWordResult(
        words=[word.title() for word in candidates],
        warnings=["Found free words"],
        source="datamuse",
    )
    request = WordSearchPdfRequest(
        product_title="Beekeeping", theme="Beekeeping", grid_size=15,
        number_of_puzzles=1, mode="topic", output_type="single_worksheet",
        words_per_puzzle=10, include_cover=False, seed=42,
    )

    with patch("services.factory.topic_word_source.lookup_topic_words", return_value=result_words):
        result = build_word_search_pdf(request)

    assert result.errors == []
    assert result.pdf_bytes.startswith(b"%PDF")
    puzzle_words = {word.upper() for word in result.puzzles[0].word_bank}
    assert {"APIARY", "HIVE", "HONEY"}.issubset(puzzle_words)
    assert not {"ANT", "WASP", "BEETLE", "MOTH"}.intersection(puzzle_words)
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(result.pdf_bytes)).pages)
    assert "Words to Find" in pdf_text
    assert "Apiary" in pdf_text and "Hive" in pdf_text


def test_factory_crossword_topic_path_puts_free_answers_and_local_clues_in_the_real_pdf():
    candidates = ["APIARY", "HIVE", "HONEY", "NECTAR", "POLLEN", "WAX",
                  "LARVA", "DRONE", "COMB", "BEE", "WORKER", "QUEEN"]
    result_words = TopicWordResult(
        words=candidates, warnings=["Found free words"], source="datamuse",
    )
    request = CrosswordPdfRequest(
        product_title="Beekeeping", theme="Beekeeping", sub_topic="Beekeeping",
        grid_size=15, number_of_puzzles=1, mode="topic",
        output_type="single_worksheet", words_per_puzzle=8,
        include_cover=False, seed=42,
    )

    with patch("services.factory.topic_word_source.lookup_topic_words", return_value=result_words), \
         patch("services.crossword.clues.simple_clue",
               side_effect=lambda answer, theme="": f"Bee-related clue about {answer.lower()} in a hive."):
        result = build_crossword_pdf(request)

    assert result.errors == []
    assert result.pdf_bytes.startswith(b"%PDF")
    assert any("Used free vocabulary source" in warning for warning in result.warnings)
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(result.pdf_bytes)).pages)
    assert "CLUES" in pdf_text
    assert "Bee-related clue" in pdf_text
    placed = {str(word).upper() for puzzle in result.puzzles for word in puzzle.placed_words}
    assert len(placed) >= 8
    assert not {"ANT", "WASP", "BEETLE", "MOTH"}.intersection(placed)
