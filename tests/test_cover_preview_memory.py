"""Previewing a registered high-resolution photo must not decode its pixels."""
import copy
import hashlib

import pytest
from PIL import Image
from services import ebook_photo_cover as pc


@pytest.fixture(params=['JPEG', 'PNG'])
def registered_photo(tmp_path, monkeypatch, request):
    monkeypatch.setattr(pc, 'EXPORTS_DIR', str(tmp_path))
    root = tmp_path / 'ebook-20' / 'cover_photo'
    root.mkdir(parents=True)
    path = root / ('source.jpg' if request.param == 'JPEG' else 'source.png')
    with Image.new('RGB', (4000, 6000), (34, 90, 40)) as photo:
        photo.save(path, request.param)
    thumb = root / 'thumb.png'
    with Image.new('RGB', (240, 310), (34, 90, 40)) as photo:
        photo.save(thumb, 'PNG')
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    row = {'digest': 'approved-render', 'source_sha256': sha,
           'thumb_path': str(thumb), 'png_path': str(thumb),
           'quality': {'pass': True}}
    return {'package_id': 'ebook-20', 'cover_design': {
        'workflow': 'photo_backed', 'source': {
            'path': str(path), 'sha256': sha, 'source_type': 'upload',
            'project_id': 20, 'license_note': 'Owner photograph'},
        'variants': {lid: copy.deepcopy(row) for lid in pc.LAYOUT_IDS}}}


def test_all_three_preview_requests_verify_identity_without_decoding(registered_photo, monkeypatch):
    def forbidden(*args):
        raise AssertionError('A preview request must not decode 24 million pixels')
    monkeypatch.setattr(pc, '_open_rgb', forbidden)
    from PIL import JpegImagePlugin, PngImagePlugin
    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, 'load', forbidden)
    monkeypatch.setattr(PngImagePlugin.PngImageFile, 'load', forbidden)
    data = registered_photo
    for lid in pc.LAYOUT_IDS:
        asset = pc.verified_variant_asset(data, project_id=20, layout=lid,
            digest='approved-render', size='thumb',
            source_sha=data['cover_design']['source']['sha256'])
        assert asset['bytes'].startswith(b'\x89PNG')


@pytest.mark.parametrize('defect', ['hash', 'owner', 'license', 'variant', 'source'])
def test_preview_still_refuses_invalid_identity(registered_photo, defect):
    data = registered_photo
    source = data['cover_design']['source']
    if defect == 'hash':
        source['sha256'] = 'bad-hash'
    elif defect == 'owner':
        source['project_id'] = 21
    elif defect == 'license':
        source['license_note'] = ''
    elif defect == 'variant':
        data['cover_design']['variants'][pc.LAYOUT_IDS[0]]['digest'] = 'changed'
    else:
        data['cover_design']['variants'][pc.LAYOUT_IDS[0]]['source_sha256'] = 'other-photo'
    with pytest.raises(pc.PhotoCoverError):
        pc.verified_variant_asset(data, project_id=20, layout=pc.LAYOUT_IDS[0],
                                 digest='approved-render', size='thumb')


def test_renderer_can_explicitly_load_the_verified_pixels(registered_photo):
    source = registered_photo['cover_design']['source']
    verified = pc.verify_source(source, project_id=20, data=registered_photo, load_pixels=True)
    try:
        assert verified['image'].size == (4000, 6000)
        assert verified['digest'] == source['sha256']
    finally:
        verified['image'].close()
