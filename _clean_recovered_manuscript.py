"""Clean SQLite-page-header corruption from recovered manuscript and re-save #2472."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

DB = Path("projects.db")
EVIDENCE = Path("exports/ebook_live_acceptance_lonnie_event_photo/manuscript_failure_evidence")


def clean_sqlite_interleave(text: str) -> str:
    # Remove NULs and other C0 controls except \t \n \r
    text = "".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 32)
    # Common freelist page header fragments that leak into recovered strings
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", "", text)
    # Collapse accidental word splits from removed headers: "unlimit ed" already ok;
    # fix leftover replacement chars
    text = text.replace("\ufffd", "")
    return text


def main() -> None:
    con = sqlite3.connect(DB)
    row = con.execute("SELECT data FROM projects WHERE id=2472").fetchone()
    data = json.loads(row[0])
    raw = data.get("content") or ""
    cleaned = clean_sqlite_interleave(raw)
    print("before", len(raw), "after", len(cleaned), "nulls", cleaned.count("\x00"))
    heads = re.findall(r"(?m)^##\s+(.+)$", cleaned)
    print("h2", len(heads))
    for i, h in enumerate(heads, 1):
        print(f"{i}. {h}")
    data["content"] = cleaned
    data["ebook"] = cleaned
    ed = data.get("ebook_document")
    if isinstance(ed, dict):
        ed["manuscript_md"] = cleaned
    ws = data["ebook_workspace"]
    # Keep generated chapter titles (from H2) on document
    from services.ebook_document import manuscript_to_chapters

    chapters = manuscript_to_chapters(cleaned)
    if isinstance(ed, dict):
        ed["chapters"] = [
            {
                "chapter_id": c.chapter_id,
                "order": c.order,
                "title": c.title,
                "purpose": c.purpose,
                "blocks": [
                    {"block_id": b.block_id, "kind": b.kind, "text": b.text}
                    for b in c.blocks
                ],
            }
            for c in chapters
        ]
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "recovered_manuscript.md").write_text(cleaned, encoding="utf-8")
    (EVIDENCE / "recovered_chapter_list.json").write_text(
        json.dumps({"chapters": [c.title for c in chapters]}, indent=2), encoding="utf-8"
    )
    con.execute(
        "UPDATE projects SET data=? WHERE id=2472",
        (json.dumps(data),),
    )
    con.commit()
    con.close()
    print("cleaned and saved")


if __name__ == "__main__":
    main()
