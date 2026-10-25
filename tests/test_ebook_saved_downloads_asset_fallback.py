"""Asset-only saved ebook downloads must remain truthful after an ephemeral disk loss.

This is offline: no customer data, network, AI provider, or real storage calls.
"""
import io
import zipfile

import pytest


@pytest.mark.parametrize("failure", ["", "missing_pdf", "missing_zip", "mismatched_pdf", "broken_zip"])
def test_saved_ebook_downloads_use_only_a_verified_matching_asset_pair(
    tmp_path, monkeypatch, failure
):
    import services.packaging as packaging
    import services.storage.compat as compat
    from services.ebook_saved_downloads import saved_downloads

    monkeypatch.setattr(packaging, "EXPORTS_DIR", str(tmp_path))
    # Deliberately do NOT create a local package directory: Render instances
    # may restart while the approved PDF and ZIP remain in persistent storage.
    pdf = b"%PDF-1.4\nasset-only saved ebook\n%%EOF"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "ebook.pdf",
            b"%PDF-1.4\nother ebook\n%%EOF" if failure == "mismatched_pdf" else pdf,
        )
    payloads = {
        "asset-only/ebook.pdf": None if failure == "missing_pdf" else pdf,
        "asset-only/package.zip": (
            None if failure == "missing_zip" else
            b"invalid zip" if failure == "broken_zip" else stream.getvalue()
        ),
    }
    reads = []

    def verified_read(project_id, relative_path):
        assert project_id == 42
        reads.append(relative_path)
        return payloads[relative_path]

    monkeypatch.setattr(compat, "read_export_or_legacy", verified_read)
    data = {"export_package_id": "asset-only"}
    before = dict(data)
    result = saved_downloads(data, 42)

    assert bool(result) == (not failure)
    if not failure:
        assert result == {
            "pdf": "/download/asset-only/ebook.pdf",
            "zip": "/download/asset-only/package.zip",
        }
    assert reads == ["asset-only/ebook.pdf", "asset-only/package.zip"]
    assert data == before
    assert not (tmp_path / "asset-only").exists()


def test_asset_only_saved_downloads_never_read_an_unowned_package(tmp_path, monkeypatch):
    import services.packaging as packaging
    import services.storage.compat as compat
    from services.ebook_saved_downloads import saved_downloads

    monkeypatch.setattr(packaging, "EXPORTS_DIR", str(tmp_path))

    def forbidden_read(*_args, **_kwargs):
        raise AssertionError("Unowned package must not reach persistent storage")

    monkeypatch.setattr(compat, "read_export_or_legacy", forbidden_read)
    assert saved_downloads({"export_package_id": "asset-only"}, 0) == {}
    assert saved_downloads({"export_package_id": "../asset-only"}, 42) == {}
