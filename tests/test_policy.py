import importlib.util
from pathlib import Path
import base64
import unittest

spec = importlib.util.spec_from_file_location('policy', Path(__file__).parents[1] / 'odoo/addons/workshop_hub/models/policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

class PolicyTests(unittest.TestCase):
    def test_approved_job_can_start(self):
        policy.technician_transition('approved', 'in_progress')

    def test_pending_quote_cannot_start(self):
        for current in ['requested', 'awaiting_approval']:
            with self.subTest(current=current), self.assertRaises(ValueError):
                policy.technician_transition(current, 'in_progress')

    def test_completed_job_cannot_reopen(self):
        with self.assertRaises(ValueError):
            policy.technician_transition('completed', 'in_progress')

    def test_cannot_skip_straight_to_completion(self):
        with self.assertRaises(ValueError):
            policy.technician_transition('approved', 'completed')

    def test_waiting_job_can_resume(self):
        policy.technician_transition('waiting_parts', 'in_progress')

    def test_quantity_accepts_fraction(self):
        self.assertEqual(policy.positive_quantity('1.5'), 1.5)

    def test_invalid_quantities(self):
        for value in [0, -1, 'nan', 'inf', None, 'x', 10001]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                policy.positive_quantity(value)

    def test_invalid_photo_base64(self):
        with self.assertRaises(ValueError):
            policy.photo_bytes('%%%')

    def test_svg_is_rejected(self):
        with self.assertRaises(ValueError):
            policy.photo_bytes(base64.b64encode(b'<svg onload="alert(1)"/>').decode())

    def test_photo_size_cap(self):
        with self.assertRaises(ValueError):
            policy.photo_bytes('A' * 7_000_001)

    def test_jpeg_signature(self):
        raw, mime = policy.photo_bytes(base64.b64encode(b'\xff\xd8\xffdemo').decode())
        self.assertEqual(mime, 'image/jpeg')
        self.assertTrue(raw.startswith(b'\xff'))

if __name__ == '__main__':
    unittest.main()
