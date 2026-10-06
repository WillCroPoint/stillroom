import tempfile
import unittest
from pathlib import Path

from branding import DEFAULT_APP_NAME, load_app_name


class BrandingTests(unittest.TestCase):
    def test_public_default_private_name_and_environment_override(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'branding.local.json'
            self.assertEqual(load_app_name(config, {}), DEFAULT_APP_NAME)
            config.write_text('{"app_name": "Fraimic Studio"}')
            self.assertEqual(load_app_name(config, {}), 'Fraimic Studio')
            self.assertEqual(load_app_name(config, {'STUDIO_APP_NAME': 'Public Studio'}), 'Public Studio')
            self.assertEqual(load_app_name(config, {'STUDIO_APP_NAME': ''}), 'Fraimic Studio')
            for invalid in ['[]', '{"app_name": null}', '{"app_name": ""}', '{"app_name": "a\\nb"}']:
                config.write_text(invalid)
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    load_app_name(config, {})
