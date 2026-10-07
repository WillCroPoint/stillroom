"""Run with python -m unittest discover -s deploy/macos -p 'test_*.py'."""
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from launcher import confirm_active_work


class ClosingTests(unittest.TestCase):
    def test_idle_and_finished_work_quit_without_dialog(self):
        for statuses in ([], ['ready', 'sent', 'error', 'upload_error']):
            studio = SimpleNamespace(lock=RLock(), jobs={
                str(i): {'status': status} for i, status in enumerate(statuses)})
            window = Mock()
            self.assertTrue(confirm_active_work(studio, window))
            window.create_confirmation_dialog.assert_not_called()

    def test_active_work_can_keep_window_open_or_close(self):
        for status in ('converting', 'sending'):
            for answer in (True, False):
                studio = SimpleNamespace(lock=RLock(), jobs={'1': {'status': status}})
                window = Mock()
                window.create_confirmation_dialog.return_value = answer
                self.assertIs(confirm_active_work(studio, window), answer)
                window.create_confirmation_dialog.assert_called_once()


class BrandingTests(unittest.TestCase):
    def test_build_name_is_explicit_and_path_safe(self):
        from mac_branding import build_name
        self.assertEqual(build_name({'STUDIO_APP_NAME': 'Private'}), 'Stillroom')
        self.assertEqual(build_name({'MACOS_APP_NAME': 'Fraimic Studio'}), 'Fraimic Studio')
        for name in ('../outside', 'a/b', 'a:b', '.', '..', 'a\nb'):
            with self.assertRaises(ValueError):
                build_name({'MACOS_APP_NAME': name})

    def test_runtime_override_and_bundle_default(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from mac_branding import window_name
        with tempfile.TemporaryDirectory() as temporary, patch.dict('os.environ', {}, clear=True), patch('mac_branding.bundle_name', return_value='Custom bundle'):
            directory = Path(temporary)
            self.assertEqual(window_name(directory), 'Custom bundle')
            (directory / 'branding.local.json').write_text('{"app_name":"Local title"}')
            self.assertEqual(window_name(directory), 'Local title')
            with patch.dict('os.environ', {'STUDIO_APP_NAME': 'Environment title'}):
                self.assertEqual(window_name(directory), 'Environment title')


if __name__ == '__main__':
    unittest.main()
