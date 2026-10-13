import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import app


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = patch.object(app, 'DATA', Path(self.temp.name))
        self.data.start()
        stream = io.BytesIO()
        Image.new('RGB', (100, 80), '#447788').save(stream, format='PNG')
        self.image = 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()

    def tearDown(self):
        self.data.stop()
        self.temp.cleanup()

    def register(self):
        return app.handle('register', {'image': self.image, 'method': 'spherical', 'bits': '0101'})

    def test_registration_does_not_claim_detection(self):
        record = self.register()
        self.assertEqual(record['results'], {})
        self.assertIn('尚未验证', record['origin'])
        self.assertIn('unrun', app.report().decode())

    def test_attack_preserves_original(self):
        record = self.register()
        value = app.handle('transform', {'id': record['id'], 'operation': 'crop70'})
        self.assertEqual(value['size'], (70, 56))
        with Image.open(app.DATA / (record['id'] + '.png')) as original:
            self.assertEqual(original.size, (100, 80))
        self.assertFalse(app.database()[record['id']]['results'])

    def test_resize_and_jpeg_are_real_image_operations(self):
        image = Image.new('RGB', (100, 80))
        self.assertEqual(app.transform(image, 'resize50').size, (50, 40))
        self.assertEqual(app.transform(image, 'jpeg50').size, image.size)
        with self.assertRaises(ValueError):
            app.transform(image, '../anything')

    def test_worker_failure_is_not_a_negative_detection(self):
        record = self.register()
        with patch.object(app, 'execute', side_effect=RuntimeError('missing CUDA')):
            result = app.handle('detect', {'id': record['id']})
        self.assertEqual(result['state'], 'error')
        self.assertNotIn('detected', result)
        self.assertIn('missing CUDA', app.report().decode())

    def test_real_result_persistence_contract(self):
        # Protocol unit test only; this fixture is never used as a model result in the app.
        record = self.register()
        with patch.object(app, 'execute', return_value={'full_message_match': False, 'bit_accuracy': .5, 'seconds': 2}):
            result = app.handle('detect', {'id': record['id']})
        self.assertNotIn('detected', result)
        self.assertEqual(app.database()[record['id']]['results']['original']['bit_accuracy'], .5)

    def test_invalid_expected_message(self):
        with self.assertRaises(ValueError):
            app.handle('register', {'image': self.image, 'method': 'spherical', 'bits': '01invalid'})

    def test_photo_watermark_keeps_before_and_changes_after(self):
        result = app.handle('watermark', {'image': self.image, 'method': 'visible', 'owner': 'Photo Studio'})
        with Image.open(app.DATA / (result['id'] + '-before.png')) as before, Image.open(app.DATA / (result['id'] + '.png')) as after:
            self.assertEqual(before.size, after.size)
            self.assertNotEqual(before.tobytes(), after.tobytes())
        self.assertEqual(result['method'], 'visible')
        self.assertNotIn('detected', result)

    def test_invisible_failure_never_creates_a_success_record(self):
        with patch.object(app, 'execute', side_effect=RuntimeError('model unavailable')):
            with self.assertRaises(RuntimeError):
                app.handle('watermark', {'image': self.image, 'method': 'trustmark'})
        self.assertEqual(app.database(), {})

    def test_builtin_watermark_completes_real_local_workflow(self):
        stream = io.BytesIO()
        image = Image.effect_noise((512, 512), 36).convert('RGB')
        image.save(stream, format='PNG')
        source = 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()
        result = app.handle('watermark', {'image': source, 'method': 'builtin',
                                          'title': 'Local workflow test'})
        original = app.handle('detect', {'id': result['id'], 'operation': 'original'})
        compressed = app.handle('detect', {'id': result['id'], 'operation': 'jpeg50'})
        self.assertTrue(original['detected'])
        self.assertTrue(compressed['detected'])
        self.assertGreaterEqual(compressed['bit_accuracy'], .875)
        self.assertEqual(app.database()[result['id']]['method'], 'builtin')


if __name__ == '__main__':
    unittest.main()
