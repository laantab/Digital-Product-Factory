import json
import sqlite3
from pathlib import Path

con = sqlite3.connect("projects.db")
con.row_factory = sqlite3.Row
print("projects:")
for r in con.execute(
    "SELECT id,name,updated_at,length(data) dlen FROM projects ORDER BY id DESC LIMIT 40"
):
    print(dict(r))

print("--- matches ---")
for r in con.execute("SELECT id,name,updated_at FROM projects"):
    raw = con.execute("SELECT data FROM projects WHERE id=?", (r["id"],)).fetchone()[0]
    data = json.loads(raw or "{}")
    content = data.get("content") or data.get("ebook") or ""
    ws = data.get("ebook_workspace") or {}
    ledger = ws.get("paid_call_ledger") or {}
    spent = float(ledger.get("spent_usd") or 0)
    name = r["name"] or ""
    if content or spent > 1.0 or "ACCEPTANCE" in name or "Lonnie" in name:
        rail = ws.get("rail") if isinstance(ws.get("rail"), dict) else {}
        ms = (rail.get("manuscript") or {}).get("status") if rail else None
        print(
            f"id={r['id']} name={name!r} updated={r['updated_at']} "
            f"content_len={len(content)} spent={spent} ms={ms}"
        )

# outline export titles
p = Path("exports/ebook_live_acceptance_lonnie_event_photo/outline_options.json")
d = json.loads(p.read_text(encoding="utf-8"))
o1 = next(o for o in d["options"] if o["id"] == "O1")
print("--- export O1 ---")
for i, c in enumerate(o1.get("chapters") or [], 1):
    print(f"{i}. {c.get('title')}")
