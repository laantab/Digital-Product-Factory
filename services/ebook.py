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
    """LEGACY one-shot full-book generator.

    Cannot create Export Ready workspace ebooks. Workspace manuscripts must
    use ``generate_one_chapter`` through the chapter pipeline. Kept only for
    the non-workspace Factory ``/generate-ebook`` route.
    """
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

    outline_bound = "APPROVED OUTLINE" in research_notes
    chapter_count = int(getattr(contract, "chapter_count", 0) or 0) if contract else 0

    if outline_bound or chapter_count >= 3:
        n = chapter_count if chapter_count >= 3 else "the approved"
        structure_block = (
            f"Produce clean Markdown with: a compelling title (H1), a short introduction, "
            f"then EXACTLY {n} chapters as ## H2 headings. "
            "Use the approved outline titles verbatim, in order. "
            "Each chapter needs 2-3 ### subsections (H3) with substantive content. "
            "Do NOT add Conclusion, Disclaimer, Sources, References, or Appendix as ## H2 "
            "chapters unless those exact titles appear in the approved outline. "
            "If a disclaimer or sources list is needed, place it AFTER the approved chapters "
            "as plain paragraphs labeled **Disclaimer** and **Sources** (not H2 chapters). "
            "Do not use emojis."
        )
        sources_instruction = (
            "When you use a research-backed point, keep it general or attribute the "
            "source name if it appears in the notes. If you include sources, put them in a "
            "**Sources** back-matter block after the approved chapters — never as an H2 chapter "
            "unless Sources is an approved outline title."
        )
    else:
        structure_block = (
            "Produce clean Markdown with: a compelling title (H1), a one-paragraph "
            "introduction, then 5-8 chapters (H2) each with 2-3 subsections (H3) "
            "and substantive, specific content per subsection, and a short conclusion. "
            "Do not use emojis."
        )
        sources_instruction = (
            "When you use a research-backed point, keep it general or attribute the "
            "source name if it appears in the notes. Add a short Sources section at the end "
            "listing only sources that actually appeared in the notes."
        )

    research_block = ""
    if research_notes or (contract and contract.research_requested):
        research_block = (
            "\n\nRESEARCH NOTES (use these; paraphrase fully — never copy sentences):\n"
            f"{research_notes or '(Use only the brief angles in the contract. Do not invent studies.)'}\n"
            f"{sources_instruction}"
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
            "Vary chapter structures — do not repeat identical H3 labels. "
            "When an approved outline is provided, you must follow it exactly."
        ),
        user=(
            f"Create a structured ebook based on the following {label}. "
            f"{structure_block}{author_line}{contract_guidance}{research_block}\n\n"
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
        "legacy_oneshot": True,
    }


def fixture_one_chapter(book, chapter) -> dict:
    """Deterministic chapter for Safe Mode acceptance testing.

    DUAL-GATED: only reachable when FACTORY_TEST_MODE=1 and
    EBOOK_CUSTOMER_PATH_FIXTURE=1. Never used in production.

    This does NOT bypass validation. The text is written to satisfy the real
    ``validate_chapter`` contract the same way a compliant writer would: it
    engages the chapter's own purpose vocabulary, meets the minimum word count,
    and supplies whichever deliverables the contract requires. If the validator
    rejects it, that is a genuine failure to fix here -- not something to
    silence.
    """
    from services.ebook_manuscript_engine import PURPOSE_KEYWORDS_CHECKED, purpose_keywords

    title = str(getattr(chapter, "title", "") or "Chapter")
    purpose = str(getattr(chapter, "purpose", "") or "")
    order = int(getattr(chapter, "order", 1) or 1)
    keywords = purpose_keywords(purpose)[:PURPOSE_KEYWORDS_CHECKED]
    focus = ", ".join(keywords[:6]) if keywords else "the approach described here"
    lead = keywords[0] if keywords else "this routine"
    short = title.split(":")[0].strip() or title

    # Every chapter must read differently: the manuscript validator rejects
    # substantially repeated paragraphs across chapters, and it is right to.
    # Variation is deterministic -- driven by the chapter's own title, purpose
    # vocabulary and order -- so a given outline always yields the same book.
    openers = [
        f"{short} rewards a reader who works in small, deliberate passes rather than one long effort.",
        f"Anyone approaching {short} for the first time benefits from settling the basics before adding anything else.",
        f"The material in {short} is arranged so each part can stand on its own if the reader needs to stop and return.",
        f"Readers usually find {short} easier once they stop treating it as one task and start treating it as a short sequence.",
        f"There is a plain version of {short} that works, and this chapter stays with that version throughout.",
    ]
    middles = [
        f"Attention here belongs on {focus}, because that is what determines whether the rest holds together.",
        f"The details that matter most are {focus}; everything else can be adjusted later without much cost.",
        f"Keeping {focus} in view prevents the common detour of optimising something that was never the constraint.",
        f"Where readers get stuck is rarely effort. It is usually {focus} being left undecided.",
        f"Decisions about {focus} are worth making once, deliberately, so they need not be revisited under pressure.",
    ]
    closers = [
        f"Applied steadily, {short} stops feeling like a separate job and becomes part of an ordinary week.",
        f"The measure of {short} is whether it still runs on a bad day, not whether it looks impressive on a good one.",
        f"A reader who follows {short} exactly as written will have a working version before adding refinements.",
        f"None of {short} depends on special equipment, and nothing here needs to be bought before starting.",
        f"By the end of {short}, the reader should be able to repeat the whole sequence without rereading it.",
    ]

    def pick(bank, offset=0):
        return bank[(order + offset) % len(bank)]

    keyword_lines = "\n\n".join(
        f"Considered inside {short}, {kw} is less complicated than it first appears. "
        f"Handle {kw} in the same place and at the same point in the sequence, and it "
        f"stops competing for attention with everything else in this chapter."
        for kw in (keywords[:7] or ["this method"])
    )

    para_a = f"{pick(openers)} {pick(middles)} {pick(closers, 1)}"
    para_b = f"{pick(middles, 2)} {pick(closers, 3)} {pick(openers, 4)}"
    para_c = f"{pick(closers, 2)} {pick(openers, 3)} {pick(middles, 1)}"

    body = (
        f"## {title}\n\n"
        f"{para_a}\n\n{para_a}\n\n"
        f"{keyword_lines}\n\n"
        f"| Stage of {short} | What the reader does | Why it matters |\n"
        "| --- | --- | --- |\n"
        f"| Setting up | Gather what {short} needs in one place | Removes the usual delay |\n"
        f"| Working through | Follow the sequence for {lead} | Builds a habit that repeats |\n"
        f"| Checking | Review {short} before moving on | Catches problems while small |\n\n"
        # Every list line carries the chapter title. Two chapters can share a
        # leading purpose keyword, and identical checklist lines are flagged as
        # duplicate deliverables -- correctly, since a book should not repeat
        # the same checklist verbatim.
        f"1. Prepare everything {short} calls for before starting.\n"
        f"2. Work through the {short} sequence in the order given.\n"
        f"3. Review the result of {short} before continuing.\n\n"
        f"- Everything {short} needs is within reach\n"
        f"- The steps described in {short} were followed in order\n"
        f"- The outcome of {short} was reviewed before moving on\n\n"
        f"For example, a reader starting {short} with {lead} can keep the first pass "
        f"deliberately small, repeat it until it feels automatic, and only then extend it. "
        f"{pick(closers, 4)}\n\n"
        f"{para_b}\n\n{para_c}\n\n{para_b}"
    )

    return {
        "chapter": body,
        "ebook": body,
        "assigned_research": "",
        "chapter_contract": {},
        "billable_calls": 0,
        "provider": "fixture",
    }


def generate_one_chapter(book, chapter) -> dict:
    """Production chapter provider: exactly one approved chapter per request.

    Uses that chapter's authoritative contract and assigned research only.
    Tests inject mocks; live calls go through ``ai_client.chat``.
    """
    import json
    from dataclasses import asdict

    from services.ebook_manuscript_engine import (
        assigned_research_for_chapter,
        chapter_contract_prompt,
        format_unresolved_findings_for_prompt,
    )

    research = assigned_research_for_chapter(book, chapter)
    contract_payload = asdict(chapter)
    if contract_payload.get("unresolved_findings"):
        contract_payload["unresolved_findings"] = format_unresolved_findings_for_prompt(
            list(contract_payload.get("unresolved_findings") or [])
        )
    contract_json = json.dumps(contract_payload, ensure_ascii=False)
    prompt = chapter_contract_prompt(book, chapter)

    system_prompt = (
        "You are a professional non-fiction author. Write exactly one chapter. "
        "Do not write any other chapter. Do not add Disclaimer or Sources as H2 headings. "
        "Follow the chapter contract exactly. Every named mandatory deliverable is required. "
        "Repair unresolved defects; never copy finding codes, finding messages, or "
        "production labels into the chapter. Preserve valid existing chapter material when a "
        "prior draft is supplied. Paraphrase research; never copy sentences. "
        "Do not invent statistics, testimonials, guaranteed income, or current market prices."
    )
    user_prompt = (
        f"Write EXACTLY one chapter as Markdown starting with ## {chapter.title}\n"
        "Do not write any other chapter.\n\n"
        f"{prompt}\n\n"
        f"AUTHORITATIVE CHAPTER CONTRACT (do not alter):\n{contract_json}\n\n"
        f"ASSIGNED RESEARCH (use only this slice):\n{research}\n"
    )

    # The two tasks the Local Manuscript Pilot may route to Factory AI. A chapter
    # carrying unresolved findings is a repair pass, not a fresh write. No other
    # Factory AI task is tagged, so nothing else changes provider.
    from services.ai_providers import routes_local

    task = "chapter_repair" if contract_payload.get("unresolved_findings") else "chapter"

    if routes_local(task):
        from ai_client import chat_with_meta

        generated = chat_with_meta(task=task, system=system_prompt, user=user_prompt)
        text = generated.text
        billable_calls = int(generated.billable_calls)
        provider = generated.provider
    else:
        # Paid path, deliberately untouched: still the module-level ``chat``
        # name, so every existing caller, mock and patch behaves exactly as it
        # did before the provider boundary existed.
        text = chat(system=system_prompt, user=user_prompt)
        billable_calls = 1
        provider = "openai"

    return {
        "chapter": text,
        "ebook": text,
        "assigned_research": research,
        "chapter_contract": contract_payload,
        # 0 for a local generation, 1 for OpenAI. Drives the Factory's meter so
        # a locally written chapter is not charged.
        "billable_calls": billable_calls,
        "provider": provider,
    }


def correct_ebook_manuscript(
    *,
    existing_manuscript: str,
    approved_outline: list,
    author: str = "",
    research_notes: str = "",
    title: str = "",
    subtitle: str = "",
) -> dict:
    """Rewrite an existing manuscript to match the approved outline exactly.

    Does not gather new research URLs. Paid chat call only when invoked.
    """
    existing_manuscript = (existing_manuscript or "").strip()
    if not existing_manuscript:
        raise ValueError("Existing manuscript is required for correction.")
    research_notes = (research_notes or "").strip()[:12000]
    outline_lines = []
    for i, item in enumerate(approved_outline or [], 1):
        if isinstance(item, dict):
            outline_lines.append(
                f"{int(item.get('order') or i)}. {item.get('title')}\n"
                f"{str(item.get('purpose') or '')[:500]}"
            )
        else:
            outline_lines.append(f"{i}. {item}")
    outline_block = "\n\n".join(outline_lines)
    author_line = f"\nAuthor / brand byline: {author.strip()}" if author.strip() else ""
    ebook = chat(
        system=(
            "You correct ebook manuscripts to match an approved outline exactly. "
            "Reuse useful facts from the existing draft. Do not invent research. "
            "Do not add Conclusion/Disclaimer/Sources as H2 chapters unless listed."
        ),
        user=(
            f"Revise the manuscript so it has EXACTLY these approved chapters as ## H2 "
            f"headings in this order and wording:\n\n{outline_block}\n\n"
            f"Title (H1): {title or 'keep existing'}\nSubtitle context: {subtitle}\n"
            f"{author_line}\n"
            "Put any disclaimer/sources after chapters as **Disclaimer** / **Sources** "
            "paragraphs, not H2 chapters.\n\n"
            f"RESEARCH NOTES (paraphrase only):\n{research_notes or '(none)'}\n\n"
            f"EXISTING MANUSCRIPT DRAFT:\n{existing_manuscript[:20000]}"
        ),
    )
    return {"ebook": ebook, "content": ebook, "source_type": "correction"}
