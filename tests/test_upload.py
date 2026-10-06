import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from PIL import Image

import upload


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_upload_both_formats_unchanged(self):
        for screen, (_, _, size) in upload.PANELS.items():
            with self.subTest(screen=screen):
                path = self.root / 'image.bin'
                data = b'\x11' * size
                path.write_bytes(data)
                response = MagicMock()
                response.__enter__.return_value = response
                response.status = 200
                response.read.return_value = b'{"status":"rendering"}'
                with patch('upload.urllib.request.urlopen', return_value=response) as send:
                    self.assertEqual(upload.upload_bin('frame.local', path),
                                     (200, '{"status":"rendering"}'))
                request = send.call_args.args[0]
                self.assertEqual(request.full_url, 'http://frame.local/api/image')
                self.assertEqual(request.get_method(), 'POST')
                self.assertEqual(request.get_header('Content-type'), 'application/octet-stream')
                self.assertEqual(request.data, data)

    def test_bad_size_and_wrong_screen_never_send(self):
        path = self.root / 'image.bin'
        with patch('upload.urllib.request.urlopen') as send:
            path.write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'got 3'):
                upload.upload_bin('frame.local', path)
            path.write_bytes(b'\x11' * 2304000)
            with self.assertRaisesRegex(ValueError, 'BIN is for screen 315'):
                upload.upload_bin('frame.local', path, screen='133')
            send.assert_not_called()

    def test_real_conversion_both_panels(self):
        source = self.root / 'photo.png'
        Image.new('RGB', (20, 10), 'red').save(source)
        for screen, (width, height, size) in upload.PANELS.items():
            with self.subTest(screen=screen):
                path = Path(upload.convert_image_to_bin(
                    str(source), 'letterbox', 'fs', None,
                    screen=screen, output_dir=str(self.root)))
                self.assertEqual(path.name, f'photo_{width}x{height}_s6.bin')
                self.assertEqual(path.stat().st_size, size)

    def test_cli_short_options_and_cleanup_on_failure(self):
        source = self.root / 'photo.png'
        Image.new('RGB', (20, 10), 'red').save(source)
        generated = []

        def reject(host, path, screen):
            generated.append(Path(path))
            self.assertEqual(screen, '315')
            self.assertEqual(Path(path).stat().st_size, 2304000)
            raise urllib.error.HTTPError('http://frame/api/image', 400, 'Bad Request', {},
                                         io.BytesIO(b'unsupported panel'))

        with patch('sys.argv', ['upload.py', 'frame', str(source), '-s', '315',
                                '-f', 'crop', '-d', 'fs', '-r', '180', '-O', 'landscape']), \
             patch('upload.upload_bin', side_effect=reject), \
             contextlib.redirect_stdout(io.StringIO()), \
             self.assertRaisesRegex(SystemExit, 'HTTP 400 Bad Request: unsupported panel'):
            upload.main()
        self.assertEqual(len(generated), 1)
        self.assertFalse(generated[0].parent.exists())

    def test_missing_file_cli_error(self):
        with patch('sys.argv', ['upload.py', 'frame', str(self.root / 'missing.bin')]), \
             contextlib.redirect_stdout(io.StringIO()), \
             self.assertRaisesRegex(SystemExit, 'Error:'):
            upload.main()


if __name__ == '__main__':
    unittest.main()
