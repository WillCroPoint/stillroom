import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse
from urllib.request import url2pathname

import numpy as np
from PIL import Image

import decode_bin
from convert_to_bin_spectra6 import PANELS, COLOR_CODES


class DecodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_bin(self, data):
        path = self.root / 'image with spaces.bin'
        path.write_bytes(data)
        return path

    def test_round_trip_both_panels(self):
        rng = np.random.default_rng(42)
        for panel in PANELS.values():
            with self.subTest(panel=panel.key):
                codes = rng.choice(COLOR_CODES, size=(panel.height, panel.width))
                path = self.write_bin(panel.packer(codes).tobytes())
                image, actual = decode_bin.decode(path)
                self.assertEqual(image.size, (panel.width, panel.height))
                np.testing.assert_array_equal(actual, codes)
                palette = np.zeros((16, 3), dtype=np.uint8)
                for code, rgb in decode_bin.CODE2RGB.items():
                    palette[code] = rgb
                np.testing.assert_array_equal(np.asarray(image), palette[codes])

    def test_el315_spec_coordinates(self):
        # Independent byte fixtures at the first/last row of every IC,
        # checking nibble order, column pairs, band boundaries and both halves.
        blocks = np.full((8, 720, 400), 0x11, dtype=np.uint8)
        expected = np.ones((2560, 1440), dtype=np.uint8)
        for ic in range(8):
            rows = 80 if ic % 4 == 3 else 400
            for b in (0, 719):
                for offset in (0, rows - 1):
                    blocks[ic, b, offset] = 0x35
                    y = 2559 - ((ic // 4) * 1280 + (ic % 4) * 400 + offset)
                    expected[y, 2 * b:2 * b + 2] = [3, 5]
        _, actual = decode_bin.decode(self.write_bin(blocks.tobytes()))
        np.testing.assert_array_equal(actual, expected)

    def test_invalid_files(self):
        with self.assertRaisesRegex(ValueError, 'got 3'):
            decode_bin.decode(self.write_bin(b'bad'))
        with self.assertRaisesRegex(ValueError, 'invalid color codes: 0x4'):
            decode_bin.decode(self.write_bin(bytes([0x14]) * 960000))
        with self.assertRaisesRegex(ValueError, 'invalid EL315 padding'):
            decode_bin.decode(self.write_bin(bytes(2304000)))

    def test_preview_rotations_and_browser_failure(self):
        path = self.write_bin(bytes([0x35]) * 960000)
        real_named_temp = tempfile.NamedTemporaryFile
        for rotation in (None, 90, 180, 270):
            with self.subTest(rotation=rotation):
                argv = ['decode_bin.py', '-p' if rotation else '--preview', str(path)]
                if rotation:
                    argv += ['-r', str(rotation)]
                with patch('sys.argv', argv), \
                     patch('decode_bin.tempfile.NamedTemporaryFile',
                           side_effect=lambda **kw: real_named_temp(dir=self.root, **kw)), \
                     patch('decode_bin.webbrowser.open', return_value=False) as browser, \
                     contextlib.redirect_stdout(io.StringIO()), \
                     contextlib.redirect_stderr(io.StringIO()) as errors:
                    decode_bin.main()
                preview = Path(url2pathname(urlparse(browser.call_args.args[0]).path))
                self.assertTrue(preview.exists())  # survives main() for asynchronous browser loading
                with Image.open(preview) as actual:
                    portrait, _ = decode_bin.decode(path)
                    expected = portrait.rotate(-(rotation or 0), expand=True)
                    np.testing.assert_array_equal(actual, expected)
                self.assertEqual(list(self.root.glob('*_decoded.png')), [])
                self.assertEqual(list(self.root.glob('*_rot*.png')), [])
                self.assertIn('open the temporary preview manually', errors.getvalue())

    def test_legacy_export(self):
        path = self.write_bin(bytes([0x35]) * 960000)
        with patch('sys.argv', ['decode_bin.py', str(path), '--rotate', '90']), \
             contextlib.redirect_stdout(io.StringIO()):
            decode_bin.main()
        with Image.open(path.with_name(path.stem + '_decoded.png')) as image:
            self.assertEqual(image.size, (1200, 1600))
        with Image.open(path.with_name(path.stem + '_rot90.png')) as image:
            self.assertEqual(image.size, (1600, 1200))


if __name__ == '__main__':
    unittest.main()
