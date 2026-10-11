"""Automatic retries can recover a refused photo with a free manuscript graphic."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['FACTORY_TEST_MODE'] = '1'
from services import ebook_visual_pipeline as vp


class VisualRetryLocalFallback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.aid = {'type': 'photo', 'visual_id': 'v_ch7', 'chapter_index': 7,
                    'chapter': 'Living Areas Checklist', 'title': 'Living Areas',
                    'caption': 'Living room comfort', 'required': True,
                    'placement': 'after_opening', 'match_status': 'reject',
                    'chapter_body': 'Check the window seals for drafts. Notice worn door sweeps. Choose compatible LEDs for frequently used lights. Keep ventilation openings clear.'}
        self.data = {'package_id': 'retry-regression', 'content': 'Original manuscript',
                     'visual_plan': {'chapters': [{'chapter': self.aid['chapter'],
                         'chapter_index': 7, 'aids': [copy.deepcopy(self.aid)]}]}}

    def test_automatic_retry_materializes_real_graphic_without_paid_call(self):
        from services import ebook_factory_pipeline as fp
        stock = dict(self.aid, status='missing', error='Wrong scene')
        with patch.object(vp, 'EXPORTS_DIR', self.tmp.name), \
             patch.object(fp, 'fill_photo_aid_from_pexels', return_value=stock), \
             patch.object(fp, 'fill_photo_aid_with_ai') as paid:
            result = vp.replace_photo_aid(self.data, 'v_ch7')
        paid.assert_not_called()
        aid = result['visual_plan']['chapters'][0]['aids'][0]
        self.assertFalse(vp.is_photo_aid(aid))
        self.assertTrue(Path(aid['asset_path']).is_file())
        self.assertEqual(aid['sha256'], vp._file_sha(aid['asset_path']))
        self.assertGreater(aid['width'], 0)
        self.assertTrue(aid['items'])
        self.assertFalse(aid['approved'])
        self.assertEqual(result['content'], 'Original manuscript')
        self.assertEqual(result['ebook_visual_manifest_digest'], result['ebook_visual_manifest']['digest'])

    def test_explicit_stock_source_stays_stock_only(self):
        from services import ebook_factory_pipeline as fp
        with patch.object(fp, 'fill_photo_aid_from_pexels', return_value=dict(self.aid)) as stock, \
             patch.object(fp, 'fill_photo_aid_automatic') as automatic:
            vp.replace_photo_aid(self.data, 'v_ch7', mode='pixabay')
        automatic.assert_not_called()
        self.assertEqual(stock.call_args.kwargs['providers'], ('pixabay',))

    def test_no_suitable_prose_does_not_approve_or_spend(self):
        from services import ebook_factory_pipeline as fp
        self.data['visual_plan']['chapters'][0]['aids'][0]['chapter_body'] = ''
        stock = dict(self.aid, chapter_body='', status='missing')
        with patch.object(fp, 'fill_photo_aid_from_pexels', return_value=stock), \
             patch.object(fp, 'fill_photo_aid_with_ai') as paid:
            result = vp.replace_photo_aid(self.data, 'v_ch7')
        paid.assert_not_called()
        aid = result['visual_plan']['chapters'][0]['aids'][0]
        self.assertTrue(vp.is_photo_aid(aid))
        self.assertFalse(aid['approved'])
        self.assertFalse(aid.get('asset_path'))
