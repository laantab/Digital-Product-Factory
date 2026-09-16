"""A real source must not be mistaken for a social-media link.

"Container Gardening for Beginners" could never be finished. Research
found earthbox.com — EarthBox, the self-watering planter maker, exactly
the kind of place a container-gardening book cites. The authority check
asked whether the string "x.com" appeared anywhere in the back matter.
It appears inside "earthbo<x.com>".

So QA reported WEAK_SOURCES, the manuscript could not be approved, and
the correction pass could not help: the citation is a genuine research
result, so every regeneration wrote it again. The build retried to its
60-attempt ceiling in about a minute and died FAILED_FINAL with
"Resolve structural/content findings before approving the manuscript."

A domain must therefore be matched on a domain boundary — the host
itself or a subdomain of it — never as a bare substring.
"""
from __future__ import annotations

import pytest

from services.ebook_manuscript_engine import (
    NON_AUTHORITATIVE_SOURCE_DOMAINS,
    _non_authoritative_sources,
)


# ======================================= the books that could not be built ==


def test_earthbox_is_not_twitter():
    """The exact live failure on project "Container Gardening for Beginners"."""
    back = (
        "**Sources**\n"
        "- https://ecogardener.com/blogs/news/beginners-guide-to-container-gardening\n"
        "- http://www.earthbox.com/blog/container-gardening-for-beginners\n"
        "- https://earthbox.com/blog/container-gardening-for-beginners\n"
    )
    assert _non_authoritative_sources(back) == set(), (
        "earthbox.com is a planter manufacturer, not the social site x.com"
    )


@pytest.mark.parametrize(
    "host",
    [
        "earthbox.com",        # x.com
        "linux.com",           # x.com
        "netflix.com",         # x.com
        "phoenix.com",         # x.com
        "equinox.com",         # x.com
        "mailbox.com",         # x.com
        "dropbox.com",         # x.com
        "essentialoilsetsy.com",  # etsy.com
    ],
)
def test_legitimate_hosts_ending_in_a_blocked_string_are_allowed(host):
    """Any host whose tail happens to spell a blocked domain was rejected."""
    back = f"**Sources**\n- https://www.{host}/guide\n"
    assert _non_authoritative_sources(back) == set()


# ============================================ the check still has its teeth ==


@pytest.mark.parametrize("domain", list(NON_AUTHORITATIVE_SOURCE_DOMAINS))
def test_every_blocked_domain_is_still_caught_when_actually_cited(domain):
    back = f"**Sources**\n- https://{domain}/some/page\n"
    assert domain in _non_authoritative_sources(back)


@pytest.mark.parametrize("domain", list(NON_AUTHORITATIVE_SOURCE_DOMAINS))
def test_www_prefixed_blocked_domains_are_caught(domain):
    back = f"**Sources**\n- https://www.{domain}/some/page\n"
    assert domain in _non_authoritative_sources(back)


def test_a_subdomain_of_a_blocked_domain_is_caught():
    back = "**Sources**\n- https://mobile.twitter.com/someone/status/1\n"
    assert "twitter.com" in _non_authoritative_sources(back)


def test_a_bare_domain_without_a_scheme_is_caught():
    back = "**Sources**\n- See the discussion on reddit.com for more.\n"
    assert "reddit.com" in _non_authoritative_sources(back)


def test_several_weak_sources_are_all_reported():
    back = (
        "**Sources**\n"
        "- https://quora.com/q\n"
        "- https://www.pinterest.com/pin/1\n"
        "- https://earthbox.com/blog/ok\n"
    )
    assert _non_authoritative_sources(back) == {"quora.com", "pinterest.com"}


# =================================================== it must never blow up ===


@pytest.mark.parametrize("value", ["", None, "   ", "no links here at all."])
def test_empty_or_linkless_back_matter_reports_nothing(value):
    assert _non_authoritative_sources(value) == set()


def test_ordinary_prose_with_sentence_punctuation_is_not_read_as_hosts():
    """"...pots.The soil..." must not become a cited domain."""
    back = (
        "**Sources**\n"
        "Water the pots.Then check the soil.Feed weekly.No links were used.\n"
    )
    assert _non_authoritative_sources(back) == set()


# ====== the same substring bug lived in the market-research evidence table ==


class TestResearchSourceClassification:
    """`source_class_for` accepted any host CONTAINING a social domain, so
    earthbox.com was shown to the customer as a "Social signal"."""

    @staticmethod
    def _cls(url):
        from services.factory_advantage import source_class_for

        return source_class_for({"url": url, "title": "Container gardening guide"})

    def test_earthbox_is_not_classified_as_a_social_signal(self):
        assert self._cls("https://earthbox.com/blog/container-gardening") != "Social signal"

    @pytest.mark.parametrize(
        "url",
        [
            "https://linux.com/guide",
            "https://dropbox.com/s/file",
            "https://netflix.com/title/1",
        ],
    )
    def test_other_hosts_ending_in_x_com_are_not_social(self, url):
        assert self._cls(url) != "Social signal"

    @pytest.mark.parametrize(
        "url",
        [
            "https://x.com/someone/status/1",
            "https://twitter.com/someone",
            "https://mobile.twitter.com/someone",
            "https://www.facebook.com/groups/1",
            "https://facebook.com.au/page",
            "https://instagram.com/p/abc",
            "https://tiktok.com/@someone",
        ],
    )
    def test_real_social_sources_are_still_classified_as_social(self, url):
        assert self._cls(url) == "Social signal"
