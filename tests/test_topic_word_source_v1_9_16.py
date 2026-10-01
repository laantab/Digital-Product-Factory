from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from services.factory.topic_word_source import clear_topic_word_cache, lookup_topic_words


def _rows(words):
    return [{"word": word, "tags": ["n"]} for word in words]


def test_free_topic_lookup_uses_only_topic_and_returns_relevant_candidates():
    clear_topic_word_cache()
    calls = []

    def fake_fetch(url):
        calls.append(url)
        query = parse_qs(urlparse(url).query)
        assert query["ml"] == ["Beekeeping"]
        assert query["md"] == ["p"]
        assert int(query["max"][0]) <= 100
        return _rows(["hive", "apiary", "queen bee", "game", "hive", "wax comb"])

    result = lookup_topic_words("Beekeeping", 12, fetch_json=fake_fetch)

    assert result.errors == []
    assert result.words == ["Hive", "Apiary", "Queen Bee", "Wax Comb"]
    assert result.source == "datamuse"
    assert len(calls) == 1


def test_crossword_source_keeps_single_grid_words_and_minimum():
    clear_topic_word_cache()
    candidates = ["apiary", "honey", "nectar", "pollen", "wax", "hive", "larva", "worker", "queen bee"]
    result = lookup_topic_words(
        "Beekeeping", 12, crossword=True,
        fetch_json=lambda _url: _rows(candidates),
    )

    assert result.words == ["Apiary", "Honey", "Nectar", "Pollen", "Wax", "Hive", "Larva", "Worker"]
    assert len(result.words) == 8
    assert result.errors == []
    assert result.clues == {}


def test_thin_result_fails_closed_without_generic_filler():
    clear_topic_word_cache()
    result = lookup_topic_words(
        "Rare subject", 20, fetch_json=lambda _url: _rows(["game", "theme", "rare"]),
    )

    assert result.words == ["Rare"]
    assert result.errors and "only 1 usable words" in result.errors[0]
    assert "puzzle" not in result.words


def test_network_failure_is_not_cached_and_returns_custom_list_guidance():
    clear_topic_word_cache()
    first = lookup_topic_words("No source", 12, fetch_json=lambda _url: (_ for _ in ()).throw(TimeoutError()))
    second = lookup_topic_words("No source", 12, fetch_json=lambda _url: _rows(["one", "two", "three", "four"]))

    assert first.words == []
    assert "custom word list" in first.errors[0].lower()
    assert second.words == ["One", "Two", "Three", "Four"]


def test_successful_lookup_is_cached_for_repeated_build_steps():
    clear_topic_word_cache()
    calls = []

    def fake_fetch(_url):
        calls.append(True)
        return _rows(["fern", "pothos", "monstera", "orchid"])

    first = lookup_topic_words("House plants", 4, fetch_json=fake_fetch)
    second = lookup_topic_words("House plants", 4, fetch_json=fake_fetch)

    assert first.words == second.words
    assert len(calls) == 1


def test_test_mode_never_makes_a_network_request():
    clear_topic_word_cache()
    with patch.dict("os.environ", {"FACTORY_TEST_MODE": "1"}):
        result = lookup_topic_words("Beekeeping", 12)

    assert result.words == []
    assert "test mode" in result.errors[0].lower()


def test_oversized_topic_is_rejected_before_network_request():
    clear_topic_word_cache()
    result = lookup_topic_words("x" * 121, 12, fetch_json=lambda _url: (_ for _ in ()).throw(
        AssertionError("oversized topic must be rejected before fetch")
    ))

    assert result.words == []
    assert "120 characters" in result.errors[0]
