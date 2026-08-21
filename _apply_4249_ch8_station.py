"""Replace ONLY project 4249 Chapter 8 visual with a station-map PNG. No preview rebuild."""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"

import database  # noqa: E402
from services.ebook_project_workspace import is_approved, manuscript_digest, stage_status  # noqa: E402
from services.ebook_visual_pipeline import (  # noqa: E402
    _stamp_aid_from_file,
    manifest_from_plan,
    render_aid_png,
)

PROJECT_ID = 4249
PKG = ROOT / "exports" / "ebook-ws-0f45e1eab3a0"
CH8_PATH = PKG / "visuals" / "v_ch8.png"
BACKUP = ROOT / "_visual_swap_4249_snapshot" / "v_ch8_pre_station_map.png"
COVER_SHA = "465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd"
MS_DIGEST = "cf08285598b6d7ac722844a97a5d54f89da2b37e8b11a5bd3df9768b8010cf98"
PREVIEW_DIGEST = "b853a69507da0c3a3e5d350f1160bb7675ac6ae076314ed76711de9cadf14126"
CH4_SHA = "92c560876ae61aba7e694ae84cf20731e1a4575cc6a297b99588e638734bc333"
OLD_CH8_SHA = "729cacb7c30a071ddf14cd22a24a84abb37388a1c94aaa5af75efb028e9fab68"
KEEP_VIDS = ("v_ch1", "v_ch2", "v_ch3", "v_ch4", "v_ch5", "v_ch6", "v_ch7", "v_ch9", "v_ch10")
STAGES = [
    "Prepare equipment and supplies",
    "Capture or receive the photograph",
    "Take the guest's order and payment",
    "Add the order to the print queue",
    "Print the photograph",
    "Perform a quality check",
    "Package and deliver it at guest pickup",
]


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    row = database.get_project(PROJECT_ID)
    data = row["data"]
    before_cover = ((data.get("cover_design") or {}).get("source") or {}).get("sha256")
    before_ms = manuscript_digest(data)
    before_ident = dict(data.get("ebook_export_identity") or {})
    before_preview = str(data.get("ebook_preview_html") or "")
    before_preview2 = str(data.get("preview_html") or "")
    before_html_sha = hashlib.sha256(before_preview.encode("utf-8")).hexdigest()
    before_content = data.get("content")
    before_ebook = data.get("ebook")
    before_design = data.get("ebook_design")
    before_ledger = ((data.get("ebook_workspace") or {}).get("paid_call_ledger") or {}).copy()
    ws = data.get("ebook_workspace") or {}
    before_visuals = stage_status(ws, "visuals")
    before_preview_status = stage_status(ws, "preview")

    vis_dir = PKG / "visuals"
    before_files = {p.name: sha_file(p) for p in sorted(vis_dir.glob("v_ch*.png"))}
    assert before_files["v_ch4.png"] == CH4_SHA, before_files["v_ch4.png"]
    assert before_files["v_ch8.png"] == OLD_CH8_SHA, before_files["v_ch8.png"]

    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if not BACKUP.is_file():
        shutil.copy2(CH8_PATH, BACKUP)
    assert sha_file(BACKUP) == OLD_CH8_SHA

    aid_spec = {
        "type": "workflow",
        "layout": "station_map",
        "title": "Dye-sub production station",
        "items": STAGES,
    }
    img = render_aid_png(aid_spec)
    buf_path = ROOT / "_visual_swap_4249_snapshot" / "v_ch8_station_preview.png"
    img.save(buf_path, format="PNG", optimize=True)
    payload = buf_path.read_bytes()
    new_sha = hashlib.sha256(payload).hexdigest()
    assert new_sha != CH4_SHA
    assert new_sha != OLD_CH8_SHA
    assert img.size == (1400, 900)

    CH8_PATH.write_bytes(payload)
    assert sha_file(CH8_PATH) == new_sha

    plan = data["visual_plan"]
    target = None
    for ch in plan.get("chapters") or []:
        for aid in ch.get("aids") or []:
            if aid.get("visual_id") == "v_ch8" or int(aid.get("chapter_index") or 0) == 8:
                target = aid
                break
        if target is not None:
            break
    assert target is not None, "v_ch8 aid missing"
    target["type"] = "workflow"
    target["layout"] = "station_map"
    target["title"] = "Dye-sub production station"
    target["caption"] = "Seven-station production line from equipment prep through guest pickup."
    target["items"] = list(STAGES)
    target["source"] = "local_manuscript_workflow"
    target["required"] = True
    target["placement"] = target.get("placement") or "after_opening"
    _stamp_aid_from_file(
        target,
        CH8_PATH,
        ctitle=str(target.get("chapter") or "Dye-Sublimation Printing: Setup, Queue, Ordering, Payment, and Pickup"),
        cidx=8,
    )
    target["source"] = "local_manuscript_workflow"
    target["layout"] = "station_map"
    target["items"] = list(STAGES)
    target["title"] = "Dye-sub production station"
    target["caption"] = "Seven-station production line from equipment prep through guest pickup."

    manifest = manifest_from_plan(plan)
    data["visual_plan"] = plan
    data["ebook_visual_manifest"] = manifest
    data["ebook_visual_manifest_digest"] = manifest["digest"]
    data["ebook_preview_html"] = before_preview
    data["preview_html"] = before_preview2
    data["ebook_export_identity"] = before_ident
    data["content"] = before_content
    data["ebook"] = before_ebook
    data["ebook_design"] = before_design

    database.update_project(PROJECT_ID, None, data)

    stored = database.get_project(PROJECT_ID)["data"]
    after_files = {p.name: sha_file(p) for p in sorted(vis_dir.glob("v_ch*.png"))}
    for vid in KEEP_VIDS:
        name = f"{vid}.png"
        assert after_files[name] == before_files[name], f"changed {name}"
    assert after_files["v_ch8.png"] == new_sha
    cover = ((stored.get("cover_design") or {}).get("source") or {}).get("sha256")
    ident = stored.get("ebook_export_identity") or {}
    ws2 = stored.get("ebook_workspace") or {}
    ledger2 = ws2.get("paid_call_ledger") or {}
    html2 = str(stored.get("ebook_preview_html") or "")
    assert cover == COVER_SHA == before_cover
    assert manuscript_digest(stored) == MS_DIGEST == before_ms
    assert ident.get("preview_digest") == PREVIEW_DIGEST
    assert hashlib.sha256(html2.encode("utf-8")).hexdigest() == before_html_sha
    assert stored.get("content") == before_content
    assert stored.get("ebook") == before_ebook
    assert stored.get("ebook_design") == before_design
    assert ledger2.get("paid_calls") == before_ledger.get("paid_calls")
    assert ledger2.get("spent_usd") == before_ledger.get("spent_usd")
    assert stage_status(ws2, "visuals") == before_visuals
    assert stage_status(ws2, "preview") == before_preview_status
    assert not is_approved(ws2, "visuals")
    assert stored.get("export_ready") is False
    print("NEW_CH8_SHA", new_sha)
    print("NEW_CH8_BYTES", len(payload), "SIZE", img.size)
    print("BACKUP", BACKUP, sha_file(BACKUP))
    print("VISUALS_STATUS", stage_status(ws2, "visuals"))
    print("OK")


if __name__ == "__main__":
    main()
