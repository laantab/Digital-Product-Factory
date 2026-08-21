"""Recover overwritten manuscript blob from projects.db freelist pages (local only)."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "projects.db"
OUT_DIR = ROOT / "exports" / "ebook_live_acceptance_lonnie_event_photo" / "manuscript_failure_evidence"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REVISED_OUTLINE = [
    "What This Business Actually Looks Like",
    "Startup Reality Check: Budget, Legal Basics, and Insurance",
    "Core Camera Kit, Printing Equipment, and Backup Gear",
    "Finding Clients and Turning Inquiries into Signed Bookings",
    "Packages and Pricing Scenarios That Protect Your Margin",
    "Planning the Event: Contracts, Timelines, Space, Power, and Staffing",
    "Event-Day Operations: From Photograph to Guest Delivery",
    "Dye-Sublimation Printing: Setup, Queue, Ordering, Payment, and Pickup",
    "Keepsakes Beyond Photo Prints: Separate Equipment and Workflow",
    "Common Mistakes and Your 30-Day First Paid Event Plan",
]


def _extract_json_string(raw: bytes, value_start: int) -> str | None:
    """value_start points at first char after opening quote of a JSON string."""
    i = value_start
    out = []
    while i < len(raw):
        c = raw[i]
        if c == 0x5C:  # backslash
            if i + 1 >= len(raw):
                break
            nxt = raw[i + 1]
            if nxt == ord("n"):
                out.append("\n")
            elif nxt == ord("r"):
                out.append("\r")
            elif nxt == ord("t"):
                out.append("\t")
            elif nxt == ord('"'):
                out.append('"')
            elif nxt == ord("\\"):
                out.append("\\")
            elif nxt == ord("u") and i + 5 < len(raw):
                hexpart = raw[i + 2 : i + 6].decode("ascii", "replace")
                try:
                    out.append(chr(int(hexpart, 16)))
                    i += 6
                    continue
                except ValueError:
                    out.append("\\u" + hexpart)
                    i += 6
                    continue
            else:
                out.append(chr(nxt))
            i += 2
            continue
        if c == 0x22:  # closing quote
            return "".join(out)
        if c < 128:
            out.append(chr(c))
        else:
            # decode multi-byte utf-8 greedily
            for n in (4, 3, 2):
                try:
                    out.append(raw[i : i + n].decode("utf-8"))
                    i += n
                    break
                except UnicodeDecodeError:
                    continue
            else:
                out.append("\ufffd")
                i += 1
                continue
            continue
        i += 1
    return None


def main() -> None:
    raw = DB.read_bytes()
    conclusion = raw.find(b"## Conclusion")
    print("conclusion_at", conclusion)
    if conclusion < 0:
        raise SystemExit("No conclusion marker in DB bytes")

    # Prefer the nearest content/ebook/manuscript_md JSON field before the marker.
    candidates = []
    for marker in (b'"content": "', b'"ebook": "', b'"manuscript_md": "'):
        pos = raw.rfind(marker, max(0, conclusion - 500_000), conclusion)
        if pos >= 0:
            candidates.append((pos, marker))
    if not candidates:
        # Fallback: walk back to a plausible markdown H1/H2 start inside a string
        raise SystemExit("Could not find JSON string field for manuscript")
    pos, marker = max(candidates, key=lambda x: x[0])
    value_start = pos + len(marker)
    text = _extract_json_string(raw, value_start)
    if not text:
        raise SystemExit("Failed to decode JSON string")
    print("recovered_chars", len(text))
    heads = re.findall(r"(?m)^##\s+(.+)$", text)
    print("h2_count", len(heads))
    for i, h in enumerate(heads, 1):
        print(f"{i}. {h}")

    (OUT_DIR / "recovered_manuscript.md").write_text(text, encoding="utf-8")
    (OUT_DIR / "recovered_chapter_list.json").write_text(
        json.dumps({"chapters": heads, "char_count": len(text)}, indent=2),
        encoding="utf-8",
    )

    # Also try to recover ledger / generation meta near generate_manuscript after conclusion area
    # Restore into project 2472 without regenerating.
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT data FROM projects WHERE id=2472").fetchone()
    data = json.loads(row["data"])
    ws = data.setdefault("ebook_workspace", {})
    ledger = ws.setdefault("paid_call_ledger", {})

    # Preserve / restore accounting: if wipe reset spent to 0.928, re-apply the $1.50 charge once.
    spent = float(ledger.get("spent_usd") or 0)
    cap = float(ledger.get("budget_cap_usd") or 3.5)
    paid_calls = int(ledger.get("paid_calls") or 0)
    calls = list(ledger.get("calls") or [])
    has_ms_charge = any(
        (c.get("purpose") == "generate_manuscript") for c in calls if isinstance(c, dict)
    )
    if not has_ms_charge:
        charge = 1.50
        if spent < 2.428 - 1e-9:
            spent = round(0.928 + charge, 4)
        paid_calls = max(paid_calls, 11)
        calls.append(
            {
                "ts": "2026-08-12T19:17:45+00:00",
                "provider": "openai",
                "purpose": "generate_manuscript",
                "estimated_cost_usd": charge,
                "idempotency_key": "recovered-from-db-freelist",
                "meta": {
                    "title": data.get("title"),
                    "recovered": True,
                    "note": "Restored after acceptance-seed overwrite wiped live generation",
                    "server_log": "POST /ebook-workspace/2472/generate-manuscript 200 at 12:17:45",
                },
            }
        )
        ledger["calls"] = calls
        ledger["spent_usd"] = spent
        ledger["remaining_usd"] = round(cap - spent, 4)
        ledger["paid_calls"] = paid_calls
        ledger["budget_cap_usd"] = cap

    # Install REVISED approved outline as authoritative (the fidelity target).
    # Keep a copy of the early O1 that was incorrectly stored/prompted.
    early = list(data.get("outline") or [])
    (OUT_DIR / "stored_outline_before_repair.json").write_text(
        json.dumps(early, indent=2), encoding="utf-8"
    )

    # Update outline option O1 + data.outline to revised titles; preserve purposes where possible.
    opts = ws.get("outline_options") or []
    o1 = next((o for o in opts if o.get("id") == "O1"), None)
    revised_chapters = []
    for i, title in enumerate(REVISED_OUTLINE, 1):
        old = None
        if o1:
            chs = o1.get("chapters") or []
            if i - 1 < len(chs):
                old = chs[i - 1]
        purpose = ""
        if isinstance(old, dict):
            purpose = "\n".join(old.get("bullets") or []) or str(old.get("purpose") or "")
        if not purpose and i - 1 < len(early) and isinstance(early[i - 1], dict):
            purpose = str(early[i - 1].get("purpose") or "")
        revised_chapters.append(
            {
                "n": i,
                "order": i,
                "title": title,
                "bullets": (old.get("bullets") if isinstance(old, dict) else None) or [],
                "purpose": purpose,
            }
        )
    if o1:
        o1["chapters"] = [
            {
                "n": c["n"],
                "title": c["title"],
                "bullets": c["bullets"]
                or [line for line in str(c["purpose"]).splitlines() if line.strip()],
            }
            for c in revised_chapters
        ]
        o1["estimated_chapters"] = 10
        o1["name"] = "Journey outline (recommended) — revised 10-chapter approval"
    ws["outline_options"] = opts
    ws["approved_outline_id"] = "O1"
    data["outline"] = [
        {
            "order": c["order"],
            "title": c["title"],
            "purpose": c["purpose"],
            "approved": True,
        }
        for c in revised_chapters
    ]

    # Store manuscript + structural findings; mark needs_correction.
    from services.ebook_document import (
        attach_document_to_data,
        build_ebook_document_from_project,
        manuscript_to_chapters,
    )
    from services.ebook_project_workspace import (
        STATUS_NEEDS_CORRECTION,
        _append_history,
        _recompute_next_action,
        outline_digest,
        set_stage_status,
        sync_document_from_workspace,
    )

    data["content"] = text
    data["ebook"] = text
    data["export_ready"] = False
    data["release_status"] = "FAIL"
    findings = [
        "OUTLINE_FIDELITY_FAIL: generated manuscript chapter structure does not match the user-approved revised 10-chapter outline.",
        "Approved outline has exactly 10 chapters; generated draft used earlier O1 headings and added extra numbered sections (Conclusion / Disclaimer / Sources).",
        "Conclusion, Disclaimer, and Sources must not be silently inserted as numbered chapters unless approved in the outline.",
        "Manuscript draft and $1.50 ledger entry are preserved for inspection; Approve Manuscript is blocked until structural correction.",
    ]
    # Detailed mismatches
    gen_heads = heads
    for i, title in enumerate(REVISED_OUTLINE):
        got = gen_heads[i] if i < len(gen_heads) else "<missing>"
        if _norm(got) != _norm(title):
            findings.append(f"Chapter {i+1} mismatch: approved={title!r} generated={got!r}")
    if len(gen_heads) != 10:
        findings.append(
            f"Chapter count mismatch: approved=10 generated={len(gen_heads)} "
            f"(extra={[h for h in gen_heads[10:]]})"
        )

    ws["manuscript_qa"] = findings
    ws["manuscript_structure_findings"] = findings
    ws["last_manuscript_generation"] = {
        "ts": "2026-08-12T19:17:45+00:00",
        "charge_usd": 1.50,
        "idempotency_key": "recovered-from-db-freelist",
        "qa_defect_count": len(findings),
        "chapter_count": len(gen_heads),
        "outline_digest_at_generation": outline_digest(
            {"outline": early}
        ),  # early outline that was actually bound
        "approved_outline_digest_now": outline_digest(data),
        "recovered": True,
        "structural_status": "FAIL",
    }
    set_stage_status(
        ws,
        "manuscript",
        STATUS_NEEDS_CORRECTION,
        note="Approved-outline fidelity FAIL — draft preserved",
    )
    for later in ("visuals", "cover", "design", "preview", "preflight", "export"):
        set_stage_status(ws, later, "not_started")
    _recompute_next_action(ws)
    _append_history(
        ws,
        "manuscript_structure_fail",
        findings_count=len(findings),
        charge_usd=1.50,
        recovered=True,
    )

    chapters = manuscript_to_chapters(text)
    data = sync_document_from_workspace(data)
    doc = build_ebook_document_from_project(data=data)
    doc.manuscript_md = text
    doc.chapters = chapters
    doc.release_status = "FAIL"
    doc.release_messages = list(findings)
    data = attach_document_to_data(data, doc, sync_manuscript=True)
    data["ebook_workspace"] = ws
    data["release_messages"] = list(findings)

    # Evidence pack (not committed): provider-ish capture
    evidence = {
        "project_id": 2472,
        "spent_usd": ledger.get("spent_usd"),
        "remaining_usd": ledger.get("remaining_usd"),
        "paid_calls": ledger.get("paid_calls"),
        "outline_stored_at_generation_early_o1": early,
        "outline_revised_authoritative_now": data["outline"],
        "generated_chapter_titles": gen_heads,
        "findings": findings,
        "manuscript_chars": len(text),
        "outline_digest_early": outline_digest({"outline": early}),
        "outline_digest_revised": outline_digest(data),
    }
    (OUT_DIR / "evidence_summary.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )

    con.execute(
        "UPDATE projects SET data=?, updated_at=? WHERE id=2472",
        (json.dumps(data), "2026-08-12T19:30:00+00:00"),
    )
    con.commit()
    con.close()
    print("RESTORED project 2472")
    print("spent", ledger.get("spent_usd"), "remaining", ledger.get("remaining_usd"))
    print("status needs_correction findings", len(findings))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


if __name__ == "__main__":
    main()
