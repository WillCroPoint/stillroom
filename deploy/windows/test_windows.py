"""Cross-platform application tests; Unix deployment is tested separately."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

class WindowsSettingsTests(unittest.TestCase):
    def test_preferences_use_appdata(self):
        from launcher import data_directory
        with patch.dict('os.environ', {'APPDATA': '/test/roaming'}, clear=True), \
                patch('pathlib.Path.home', side_effect=RuntimeError('Home unavailable')):
            self.assertEqual(data_directory(), Path('/test/roaming/Stillroom'))

    def test_isolated_test_directory_takes_priority(self):
        from launcher import data_directory
        with patch.dict('os.environ', {'APPDATA': '/test/roaming',
                        'STILLROOM_DATA_DIR': '/test/isolated'}, clear=True), \
                patch('pathlib.Path.home', side_effect=RuntimeError('Home unavailable')):
            self.assertEqual(data_directory(), Path('/test/isolated'))


if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(WindowsSettingsTests))
    for path in sorted((ROOT / 'tests').glob('test_*.py')):
        if path.name != 'test_deployment.py':
            suite.addTests(loader.discover(str(ROOT / 'tests'), pattern=path.name))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
