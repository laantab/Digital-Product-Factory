"""YouTube Support Finder for the Visual Enhancement module.

Two modes:
1. Analyze a user-provided YouTube link: fetch the transcript when available,
   summarize it, extract teaching points, and recommend how to use it in the
   ebook. Transcripts are used for research only and are never copied verbatim.
2. Search for helpful YouTube videos for a topic/chapter using Tavily (live),
   or fail open to AI-suggested search phrases when no API key is set.
"""
import logging
import os

from ai_client import chat_json
from services.ebook import _fetch_youtube_transcript, _youtube_id

logger = logging.getLogger(__name__)


def _context_clause(ebook_topic: str, chapter_topic: str) -> str:
    bits = []
    if ebook_topic:
        bits.append(f"Ebook topic: {ebook_topic}")
    if chapter_topic:
        bits.append(f"Chapter/section topic: {chapter_topic}")
    if not bits:
        return "The user has not specified the ebook or chapter topic yet."
    return "\n".join(bits)


_ANALYZE_KEYS = [
    "video_title",
    "summary",
    "key_teaching_points",
    "suggested_placement",
    "recommendation",
    "recommendation_reason",
    "caption",
    "resource_note",
]


def analyze_youtube_video(
    url: str, ebook_topic: str = "", chapter_topic: str = ""
) -> dict:
    """Option 1: analyze a YouTube link the user supplies."""
    url = (url or "").strip()
    if not url:
        raise ValueError("Please paste a YouTube link.")
    video_id = _youtube_id(url)
    if not video_id:
        raise ValueError(
            "That does not look like a YouTube link. Paste a full watch, "
            "share, or shorts URL."
        )

    ebook_topic = (ebook_topic or "").strip()
    chapter_topic = (chapter_topic or "").strip()

    transcript = ""
    transcript_available = True
    try:
        transcript = _fetch_youtube_transcript(video_id)
    except Exception:  # noqa: BLE001
        logger.warning("Transcript unavailable for %s", video_id, exc_info=True)
        transcript_available = False

    context = _context_clause(ebook_topic, chapter_topic)

    if transcript_available:
        source_clause = (
            "Use the transcript below ONLY as research. Never copy any sentence "
            "from it word-for-word. Summarize and rewrite everything in your own "
            "original words.\n\n"
            f"TRANSCRIPT:\n{transcript[:14000]}"
        )
    else:
        source_clause = (
            "No transcript was available for this video, so base your guidance on "
            "the video URL and the ebook/chapter context. State clearly in the "
            "summary that the video could not be transcribed automatically."
        )

    raw = chat_json(
        system=(
            "You help a beginner ebook creator decide how to use a YouTube video "
            "as a supporting resource. You never plagiarize: transcripts are for "
            "research only and all output must be original. You are practical and "
            "encouraging."
        ),
        user=(
            "Analyze this YouTube video for use in an ebook.\n\n"
            f"VIDEO URL: {url}\n"
            f"CONTEXT:\n{context}\n\n"
            f"{source_clause}\n\n"
            "Return a JSON object with EXACTLY these keys:\n"
            '- "video_title": string, a short descriptive title for the video '
            "based on its content.\n"
            '- "summary": string, a 2-4 sentence original summary of what the '
            "video teaches.\n"
            '- "key_teaching_points": array of 3-6 short original strings.\n'
            '- "suggested_placement": string naming the chapter or section this '
            "best supports.\n"
            '- "recommendation": string, EXACTLY one of "Include as a resource", '
            '"Rewrite into original content", or "Use as visual inspiration".\n'
            '- "recommendation_reason": string, 1-2 sentences.\n'
            '- "caption": string, a short caption to show near the video link in '
            "the ebook.\n"
            '- "resource_note": string, a one-line note for a '
            "resources/further-watching list.\n"
            "Do not use emojis. Return only the JSON object."
        ),
        max_completion_tokens=2000,
    )

    result = {key: raw.get(key, "") for key in _ANALYZE_KEYS}
    pts = result.get("key_teaching_points")
    if isinstance(pts, str):
        result["key_teaching_points"] = [pts] if pts.strip() else []
    elif not isinstance(pts, list):
        result["key_teaching_points"] = []
    result["video_id"] = video_id
    result["video_url"] = url
    result["transcript_available"] = transcript_available
    return result


def _tavily_youtube(topic: str) -> tuple[bool, list[dict]]:
    """Return (live_used, results). Fails open when Tavily is missing/errors."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return False, []
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=key)
        search = client.search(
            query=f"best helpful YouTube videos about {topic}",
            search_depth="advanced",
            max_results=8,
            include_domains=["youtube.com", "youtu.be"],
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "Tavily YouTube search failed; falling back to suggestions",
            exc_info=True,
        )
        return False, []

    results = []
    for r in search.get("results", []):
        vid_url = r.get("url", "")
        if not _youtube_id(vid_url):
            continue
        results.append(
            {
                "title": r.get("title", "Untitled"),
                "url": vid_url,
                "content": r.get("content", ""),
            }
        )
    return True, results


def search_youtube_videos(
    topic: str, ebook_topic: str = "", chapter_topic: str = ""
) -> dict:
    """Option 2: find helpful YouTube videos for a topic/chapter."""
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("Please enter a chapter or ebook topic to search for.")
    ebook_topic = (ebook_topic or "").strip()
    chapter_topic = (chapter_topic or "").strip()
    context = _context_clause(ebook_topic, chapter_topic)

    live_used, results = _tavily_youtube(topic)

    if live_used and results:
        numbered = "\n".join(
            f"{i}. {r['title']} ({r['url']})\n{r['content'][:500]}"
            for i, r in enumerate(results)
        )
        raw = chat_json(
            system=(
                "You help a beginner ebook creator pick helpful YouTube videos to "
                "support their ebook. You are practical and concise."
            ),
            user=(
                f'Pick the most useful videos for the topic "{topic}".\n\n'
                f"CONTEXT:\n{context}\n\n"
                f"CANDIDATE VIDEOS:\n{numbered}\n\n"
                'Return a JSON object with key "videos": an array (max 5) of '
                'objects with keys: "index" (integer matching the candidate '
                'number), "why_useful" (string), "suggested_placement" (string '
                'naming the chapter/section), "caption" (short caption), '
                '"resource_note" (one-line note for a resources list). Only '
                "include genuinely useful videos. Do not invent URLs. Do not use "
                "emojis. Return only the JSON object."
            ),
            max_completion_tokens=2000,
        )
        videos = []
        for item in raw.get("videos") or []:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("index"))
            except (TypeError, ValueError):
                continue
            if idx < 0 or idx >= len(results):
                continue
            base = results[idx]
            videos.append(
                {
                    "video_title": base["title"],
                    "video_url": base["url"],
                    "why_useful": item.get("why_useful", ""),
                    "suggested_placement": item.get("suggested_placement", ""),
                    "caption": item.get("caption", ""),
                    "resource_note": item.get("resource_note", ""),
                }
            )
        if not videos:
            # AI returned nothing usable; surface the raw live results instead.
            videos = [
                {
                    "video_title": r["title"],
                    "video_url": r["url"],
                    "why_useful": "",
                    "suggested_placement": "",
                    "caption": "",
                    "resource_note": "",
                }
                for r in results[:5]
            ]
        return {
            "topic": topic,
            "mode": "live",
            "note": "",
            "videos": videos,
            "search_phrases": [],
        }

    # Fail open: no live search available -> suggest search phrases instead.
    raw = chat_json(
        system=(
            "You help a beginner ebook creator find helpful YouTube videos by "
            "hand. You are practical and concise."
        ),
        user=(
            f'Suggest YouTube search phrases to find helpful videos about '
            f'"{topic}".\n\n'
            f"CONTEXT:\n{context}\n\n"
            'Return a JSON object with key "search_phrases": an array of 5-8 '
            "short search phrases the user can paste into YouTube. Do not use "
            "emojis. Return only the JSON object."
        ),
        max_completion_tokens=800,
    )
    phrases = raw.get("search_phrases")
    if isinstance(phrases, str):
        phrases = [phrases] if phrases.strip() else []
    elif not isinstance(phrases, list):
        phrases = []
    return {
        "topic": topic,
        "mode": "suggestions",
        "note": (
            "Live video results require the research API key (TAVILY_API_KEY). "
            "Until it is added, here are search phrases you can paste into "
            "YouTube yourself."
        ),
        "videos": [],
        "search_phrases": phrases,
    }
