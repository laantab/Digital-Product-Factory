"""Ebook generation from a topic, web page, or YouTube video."""
import re
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi

from ai_client import chat

from services.ebook_contract import EbookContract, contract_to_prompt_guidance

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _is_url(text: str) -> bool:
    return bool(_URL_RE.match(text.strip()))


def _youtube_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "youtu.be" in host:
        return parsed.path.lstrip("/") or None
    if "youtube.com" in host:
        if parsed.path.startswith("/watch"):
            return parse_qs(parsed.query).get("v", [None])[0]
        if parsed.path.startswith("/embed/") or parsed.path.startswith("/shorts/"):
            return parsed.path.split("/")[2]
    return None


def _fetch_youtube_transcript(video_id: str) -> str:
    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id)
        text = " ".join(snippet.text for snippet in fetched)
    except AttributeError:
        # Fallback for older youtube-transcript-api versions
        segments = YouTubeTranscriptApi.get_transcript(video_id)
        text = " ".join(seg["text"] for seg in segments)
    if not text.strip():
        raise RuntimeError("The video transcript was empty.")
    return text


def _fetch_web_content(url: str) -> str:
    resp = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0 (compatible; DigitalProductFactory/1.0)"},
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    if not text:
        raise RuntimeError("No readable content was found at that URL.")
    return text


def _gather_source(source: str) -> tuple[str, str]:
    """Return (source_label, content) for the AI prompt."""
    source = source.strip()
    if _is_url(source):
        video_id = _youtube_id(source)
        if video_id:
            return ("YouTube transcript", _fetch_youtube_transcript(video_id))
        return ("web article", _fetch_web_content(source))
    return ("topic", source)


def generate_ebook(
    source: str,
    contract: EbookContract | None = None,
    *,
    author: str = "",
    research_notes: str = "",
) -> dict:
    source = (source or "").strip()
    if not source:
        raise ValueError("Please enter a topic or URL.")

    label, content = _gather_source(source)
    # Keep the prompt within a sane size.
    content = content[:16000]
    research_notes = (research_notes or "").strip()[:12000]

    contract_guidance = ""
    if contract:
        contract_guidance = "\n\n" + contract_to_prompt_guidance(contract)

    research_block = ""
    if research_notes or (contract and contract.research_requested):
        research_block = (
            "\n\nRESEARCH NOTES (use these; paraphrase fully — never copy sentences):\n"
            f"{research_notes or '(Use only the brief angles in the contract. Do not invent studies.)'}\n"
            "When you use a research-backed point, keep it general or attribute the "
            "source name if it appears in the notes. Add a short Sources section at the end "
            "listing only sources that actually appeared in the notes."
        )

    author_line = f"\nAuthor / brand byline: {author.strip()}" if author.strip() else ""

    ebook = chat(
        system=(
            "You are a professional non-fiction author and instructional "
            "designer who produces topic-specific, audience-appropriate, "
            "practical digital ebooks that are honest, useful, and sellable. "
            "You rewrite all source material into original prose (Designrr-quality "
            "clarity). You never copy sentences from research notes or transcripts. "
            "You do not invent statistics, studies, testimonials, or case "
            "studies. You do not use hype language. You do not make health, "
            "financial, or legal claims without appropriate disclaimers. "
            "Every chapter must be substantive, specific, and actionable. "
            "Vary chapter structures — do not repeat identical H3 labels."
        ),
        user=(
            f"Create a structured ebook based on the following {label}. "
            f"Produce clean Markdown with: a compelling title (H1), a one-paragraph "
            f"introduction, then 5-8 chapters (H2) each with 2-3 subsections (H3) "
            f"and substantive, specific content per subsection, and a short conclusion. "
            f"Do not use emojis.{author_line}{contract_guidance}{research_block}\n\n"
            f"SOURCE MATERIAL:\n{content}"
        ),
    )

    from services.ebook_originality_agent import score_originality

    sources = [content]
    if research_notes:
        sources.append(research_notes)
    originality = score_originality(ebook, sources)

    return {
        "source": source,
        "source_type": label,
        "ebook": ebook,
        "author_brand": (author or "").strip(),
        "research_notes": research_notes,
        "source_content": content,
        "originality": originality.to_dict(),
    }
