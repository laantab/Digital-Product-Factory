"""One final, zero-provider editorial review for both ebook export paths."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


def review_exported_ebook(data: dict, *, package_dir: str) -> dict:
    """Inspect existing outputs without rewriting the book or its files.

    Missing outputs or an unavailable reviewer can never inherit an old PASS.
    Temporary page renders and PDF handles are released on success and failure.
    """
    from services.factory_version import get_version

    result = {"verdict": "EDITOR-IN-CHIEF — REVIEW ERROR",
              "review_engine": "editor_in_chief_ebook",
              "review_contract_version": "ebook-final-v1",
              "factory_version": get_version(),
              "reviewed_at": datetime.now(timezone.utc).isoformat(),
              "pdf_sha256": "", "zip_sha256": ""}
    try:
        import fitz
        from services.editor_in_chief_ebook import collect_ebook_candidate, review_ebook

        if not package_dir:
            raise ValueError("No export package")
        package = Path(package_dir)
        pdf, archive = package / "ebook.pdf", package / "package.zip"
        result["pdf_sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
        result["zip_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        with TemporaryDirectory(prefix="ebook_quality_") as page_dir:
            paths = []
            with fitz.open(pdf) as doc:
                if doc.page_count < 1:
                    raise ValueError("No PDF pages")
                for i, page in enumerate(doc):
                    path = str(Path(page_dir) / f"p{i + 1:03d}.png")
                    page.get_pixmap(dpi=72).save(path)
                    paths.append(path)
            report = review_ebook(collect_ebook_candidate(
                data, package_dir=str(package), page_images=paths))
        result.update(verdict=report.verdict, overall=report.overall,
                      scores=report.scores,
                      findings=[vars(f).copy() for f in report.findings],
                      checks_run=report.checks_run, checks_skipped=report.checks_skipped)
    except Exception:
        logging.getLogger(__name__).exception("ebook completion quality review unavailable")
        result["error"] = "The final quality check could not finish. Your draft is saved; resume to retry."
    data["editor_in_chief"] = result
    return result
