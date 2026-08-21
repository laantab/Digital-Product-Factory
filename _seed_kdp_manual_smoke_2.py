"""DATA PREP ONLY: create disposable KDP MANUAL SMOKE 2 fixture.

Zero paid/external calls. Does not modify application code or existing projects.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from pypdf import PdfReader  # noqa: E402

from database import (  # noqa: E402
    DB_PATH,
    create_project,
    get_project,
    is_test_name,
    list_projects,
    update_project,
)
from services.kdp.preflight import RESULT_PASS, run_kdp_preflight  # noqa: E402
from services.math_worksheet.pdf_builder import (  # noqa: E402
    MathWorksheetPdfRequest,
    build_math_worksheet_pdf,
)
from services.quality.artifact_identity import (  # noqa: E402
    content_digest_from_pdf_bytes,
    stamp_artifact_identity,
    verify_artifact_identity,
)
from services.quality.artifact_state import (  # noqa: E402
    ArtifactState,
    approve_artifact_revision,
    resolve_artifact_state,
)

ZWSP = "\u200b"
VISIBLE_TITLE = "KDP MANUAL SMOKE 2 — DELETE AFTER TEST"
STORED_NAME = f"KDP MANUAL S{ZWSP}MOKE 2 — DELETE AFTER TE{ZWSP}ST"
PROBLEM_COUNT = 320  # 16 worksheet + 8 answer-key pages = 24
AUTHOR = "Manual Smoke Author"
DESCRIPTION = (
    "Disposable Grade 3 addition practice book for local KDP manual smoke 2. "
    "Deterministic fixture — not a customer artifact. DELETE AFTER TEST."
)


def main() -> int:
    assert STORED_NAME.replace(ZWSP, "") == VISIBLE_TITLE
    assert not is_test_name(STORED_NAME), "ZWSP visibility trick failed"

    req = MathWorksheetPdfRequest(
        worksheet_title=VISIBLE_TITLE,
        grade="3",
        math_topic="Addition",
        difficulty="Easy",
        problem_count=PROBLEM_COUNT,
        include_answer_key=True,
        include_challenge=False,
        output_type="book",
        include_cover=False,
        seed=20260811,
    )
    result = build_math_worksheet_pdf(req)
    if result.errors:
        raise SystemExit(f"PDF build errors: {result.errors}")

    pdf_bytes = result.pdf_bytes
    page_count = len(PdfReader(BytesIO(pdf_bytes)).pages)
    print("GENERATED_PAGES", page_count)
    print("LAYOUT", result.layout_info)
    if page_count < 24:
        raise SystemExit(f"Need >=24 pages, got {page_count}")

    package_id = uuid.uuid4().hex
    export_package_id = uuid.uuid4().hex
    filename = "kdp_manual_smoke_2_math.pdf"
    export_dir = ROOT / "exports" / export_package_id
    export_dir.mkdir(parents=True, exist_ok=True)
    pkg_dir = ROOT / "exports" / package_id
    pkg_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = export_dir / filename
    pdf_path.write_bytes(pdf_bytes)
    (pkg_dir / filename).write_bytes(pdf_bytes)

    meta = {
        "product_type": "math_worksheet",
        "title": VISIBLE_TITLE,
        "worksheet_title": VISIBLE_TITLE,
        "grade": "3",
        "math_topic": "Addition",
        "difficulty": "Easy",
        "problems": PROBLEM_COUNT,
        "challenge_problems": 0,
        "include_answer_key": True,
        "include_challenge": False,
        "filename": filename,
    }
    (export_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def _expr(p: dict) -> str:
        return str(p.get("problem") or p.get("expression") or p.get("question") or p)

    problems_txt = (
        "Math Problems\n"
        + ("-" * 30)
        + "\n"
        + "\n".join(
            f"{i}. {_expr(p)} = {p.get('answer')}"
            for i, p in enumerate(result.problems, 1)
        )
        + "\n"
    )
    answer_txt = (
        "Answer Key\n"
        + ("-" * 30)
        + "\n"
        + "\n".join(f"{i}. {p.get('answer')}" for i, p in enumerate(result.problems, 1))
        + "\n"
    )
    (export_dir / "problems.txt").write_text(problems_txt, encoding="utf-8")
    (export_dir / "answer_key.txt").write_text(answer_txt, encoding="utf-8")

    zip_path = export_dir / "package.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, pdf_bytes)
        zf.writestr("metadata.json", json.dumps(meta, indent=2))
        zf.writestr("problems.txt", problems_txt)
        zf.writestr("answer_key.txt", answer_txt)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zpdf = zf.read(filename)
    assert zpdf == pdf_bytes
    assert len(PdfReader(BytesIO(zpdf)).pages) == page_count

    content_digest = content_digest_from_pdf_bytes(pdf_bytes)
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    fields = {
        "worksheet_title": VISIBLE_TITLE,
        "grade": "3",
        "math_topic": "Addition",
        "difficulty": "Easy",
        "problems": str(PROBLEM_COUNT),
        "include_answer_key": "yes",
        "include_challenge": "no",
        "include_cover": "no",
        "output_format": "book",
        "author_name": AUTHOR,
        "audience": "Grade 3 students",
        "goal": "Addition practice",
    }

    data = {
        "product_type": "math_worksheet",
        "product_label": "Math Worksheet",
        "title": VISIBLE_TITLE,
        "author": AUTHOR,
        "author_name": AUTHOR,
        "description": DESCRIPTION,
        "listing_description": DESCRIPTION,
        "filename": filename,
        "is_pdf": True,
        "is_book": True,
        "package_id": package_id,
        "artifact_id": package_id,
        "export_package_id": export_package_id,
        "pdf_bytes": pdf_b64,
        "page_count": page_count,
        "problems": result.problems,
        "challenge_problems": [],
        "include_challenge": False,
        "warnings": list(result.warnings or []),
        "image_jobs": [],
        "fields": fields,
        "layout_info": result.layout_info,
        "content": {},
        "publication_format": "paperback",
        "qa_status": "accepted",
        "qa_report": {
            "product_type": "math_worksheet",
            "passed": True,
            "blocked_export": False,
            "answer_key_included": True,
            "answer_key_requested": True,
            "cover_allowed": False,
            "output_format": "book",
            "errors": [],
            "warnings": [],
            "fixes_applied": [],
        },
        "kdp_print_settings": {
            "binding": "paperback",
            "ink": "black",
            "paper": "white",
            "trim_width_in": "6",
            "trim_height_in": "9",
            "bleed": "no_bleed",
            "page_count": page_count,
        },
        "kdp_metadata": {
            "title": VISIBLE_TITLE,
            "author": AUTHOR,
            "description": DESCRIPTION,
            "isbn": "",
            "isbn_option": "kdp_free",
            "product_type": "math_worksheet",
        },
        "kdp_ai_disclosure": {
            "text": "none",
            "images": "none",
            "translations": "none",
        },
        "product_exports": {
            "files": {
                "pdf": {
                    "name": filename,
                    "sha256": content_digest,
                    "url": f"/download/{export_package_id}/{filename}",
                },
                "zip": {
                    "name": "package.zip",
                    "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
                    "url": f"/download/{export_package_id}/package.zip",
                },
            },
            "meta": {
                "artifact_id": package_id,
                "artifact_revision": 1,
                "content_digest": content_digest,
                "package_id": export_package_id,
            },
            "pdf_available": True,
        },
        "user_saved": True,
        "artifact_state": "DRAFT",
        "artifact_revision": 1,
    }

    stamp_artifact_identity(data)
    assert data.get("content_digest") == content_digest
    verify_artifact_identity(data)

    data = approve_artifact_revision(
        data,
        reason="KDP MANUAL SMOKE 2 disposable fixture APPROVED stamp",
        repo_root=ROOT,
    )
    assert resolve_artifact_state(data, repo_root=ROOT) is ArtifactState.APPROVED

    proj = create_project(
        name=STORED_NAME,
        type_="product",
        data=data,
        user_saved=True,
        system_test=False,
        temporary=False,
    )
    pid = int(proj["id"])
    print("CREATED_ID", pid)
    print("DB_PATH", DB_PATH)
    print("NAME_REPR", repr(proj["name"]))
    print("FLAGS", proj["user_saved"], proj["system_test"], proj["temporary"])
    print("IS_TEST_NAME", is_test_name(proj["name"]))

    reloaded = get_project(pid)
    assert reloaded is not None
    rdata = reloaded["data"]
    pref = run_kdp_preflight(
        rdata,
        publication_format="paperback",
        print_settings=rdata["kdp_print_settings"],
        metadata=rdata["kdp_metadata"],
        ai_disclosure=rdata["kdp_ai_disclosure"],
    )
    print("PREFLIGHT_OVERALL", pref.overall)
    fails = [f for f in pref.findings if f.severity == "FAIL"]
    for f in fails:
        print("FAIL", f.rule_id, f.affected, f.explanation)
    if pref.overall != RESULT_PASS:
        raise SystemExit(f"Preflight did not PASS: {pref.overall}")

    rdata = dict(rdata)
    rdata["kdp_settings"] = {
        "publication_format": pref.publication_format,
        "print": rdata["kdp_print_settings"],
        "metadata": rdata["kdp_metadata"],
        "ai_disclosure": rdata["kdp_ai_disclosure"],
    }
    rdata["kdp_preflight"] = pref.as_dict()
    update_project(
        pid,
        name=STORED_NAME,
        type_="product",
        data=rdata,
        user_saved=True,
        system_test=False,
        temporary=False,
    )

    visible = list_projects(include_system=False)
    hit = next((p for p in visible if p["id"] == pid), None)
    print("VISIBLE_IN_LIST", bool(hit))
    if not hit:
        raise SystemExit("New project not visible in list_projects")

    info = {
        "project_id": pid,
        "title": VISIBLE_TITLE,
        "stored_name_repr": repr(STORED_NAME),
        "package_id": package_id,
        "export_package_id": export_package_id,
        "artifact_state": "APPROVED",
        "artifact_revision": 1,
        "content_digest": content_digest,
        "asset_manifest_digest": rdata.get("asset_manifest_digest"),
        "page_count": page_count,
        "preflight_overall": pref.overall,
        "print_settings": rdata["kdp_print_settings"],
        "ai_disclosure": rdata["kdp_ai_disclosure"],
        "pdf_path": str(pdf_path),
        "zip_path": str(zip_path),
        "pdf_url": f"/download/{export_package_id}/{filename}",
        "zip_url": f"/download/{export_package_id}/package.zip",
        "paid_calls": 0,
    }
    (export_dir / "kdp_manual_smoke_2_info.json").write_text(
        json.dumps(info, indent=2), encoding="utf-8"
    )
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
