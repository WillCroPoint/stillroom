import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

import convert_to_bin_spectra6 as converter
from decode_bin import decode
from threaded_function_runner import ThreadedFunctionRunner


def dither_sample(seed):
    pixels = np.random.default_rng(seed).integers(0, 256, (24, 32, 3), dtype=np.uint8)
    return converter.quantize_atkinson_indexed(Image.fromarray(pixels))


class OrientationTests(unittest.TestCase):
    def test_fit_for_all_source_and_frame_orientations(self):
        panel = SimpleNamespace(width=12, height=20)
        for source_size in ((36, 20), (20, 36), (24, 24)):
            source = Image.fromarray(np.random.default_rng(1).integers(
                0, 256, (source_size[1], source_size[0], 3), dtype=np.uint8))
            for orientation in ('portrait', 'landscape'):
                frame_size = (12, 20) if orientation == 'portrait' else (20, 12)
                for fit in ('crop', 'letterbox'):
                    with self.subTest(source=source_size, orientation=orientation, fit=fit):
                        actual = converter.pad_to_frame(
                            converter.scale_to_frame(source, fit, panel, orientation), panel, (0, 0, 0), orientation)
                        if fit == 'crop':
                            # Same whole-pixel resize/center crop, in display coordinates.
                            ratio = max(frame_size[0] / source.width, frame_size[1] / source.height)
                            resized = source.resize(tuple(round(v * ratio) for v in source.size), Image.Resampling.LANCZOS)
                            x, y = ((resized.width-frame_size[0])//2, (resized.height-frame_size[1])//2)
                            expected = resized.crop((x, y, x+frame_size[0], y+frame_size[1]))
                        else:
                            ratio = min(frame_size[0] / source.width, frame_size[1] / source.height)
                            resized = source.resize(tuple(round(v * ratio) for v in source.size), Image.Resampling.LANCZOS)
                            expected = Image.new('RGB', frame_size)
                            expected.paste(resized, ((expected.width-resized.width)//2, (expected.height-resized.height)//2))
                        np.testing.assert_array_equal(actual, expected)

    def test_landscape_crop_on_portrait_keeps_top_at_top(self):
        source = Image.new('RGB', (40, 20), 'red')
        source.paste('blue', (0, 10, 40, 20))
        result = converter.scale_to_frame(source, 'crop', SimpleNamespace(width=10, height=20), 'portrait')
        self.assertEqual(result.getpixel((5, 2)), (255, 0, 0))
        self.assertEqual(result.getpixel((5, 17)), (0, 0, 255))

    def test_short_options_and_no_threads_in_app(self):
        args = converter.parse_args(['-s', '315', '-O', 'horizontal', '-f', 'crop', '-j', '4',
            '-d', 'fs', '-l', 'white', '-o', 'output', '-n', '-r', '-b', '1', '-c', '1', '-S', '1', 'input'])
        self.assertEqual((args.orientation, args.jobs, args.screen), ('landscape', 4, '315'))
        self.assertTrue(args.no_transpose and args.recursive)
        self.assertEqual(converter.parse_args(['input']).orientation, 'portrait')
        for flags in (['--threads', '2'], ['-t', '2'], ['--parallel', 'thread'], ['-j', '0']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                converter.parse_args(flags + ['input'])

    def test_atkinson_process_results_equal_serial_results(self):
        seeds = [1, 2, 3]
        expected = [dither_sample(seed) for seed in seeds]
        results = ThreadedFunctionRunner(dither_sample, seeds, backend='process', worker_count=2).run()
        for result, pixels in zip(results, expected):
            np.testing.assert_array_equal(result.result(), pixels)

    def test_preview_uses_generated_bin_in_frame_orientation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = Image.new('RGB', (40, 20), 'red')
            source.paste('blue', (0, 10, 40, 20))
            path = root / 'wide.png'
            source.save(path)
            for orientation, size in [('portrait', (1200, 1600)), ('landscape', (1600, 1200))]:
                argv = ['convert', '-O', orientation, '-f', 'crop', '-d', 'fs', '-p',
                        '-b', '1', '-c', '1', '-S', '1', str(path)]
                with patch('sys.argv', argv), patch('decode_bin.show_preview') as show, \
                     contextlib.redirect_stdout(io.StringIO()):
                    converter.main()
                show.assert_called_once()
                preview = show.call_args.args[0]
                self.assertEqual(preview.size, size)
                self.assertEqual(preview.getpixel((size[0]//2, 10)), (255, 0, 0))
                self.assertEqual(preview.getpixel((size[0]//2, size[1]-10)), (0, 0, 255))
                decoded, _ = decode(root / 'wide_1200x1600_s6.bin')
                if orientation == 'landscape':
                    decoded = decoded.transpose(Image.Transpose.ROTATE_90)
                np.testing.assert_array_equal(preview, decoded)
            second = root / 'second.png'
            source.save(second)
            with patch('sys.argv', ['convert', '-p', str(root)]), \
                 patch('convert_to_bin_spectra6.ThreadedFunctionRunner') as runner, \
                 patch('decode_bin.show_preview') as show, \
                 contextlib.redirect_stdout(io.StringIO()), \
                 self.assertRaisesRegex(SystemExit, 'exactly one input image'):
                converter.main()
            runner.assert_not_called()
            show.assert_not_called()

    def test_real_batch_conversion_and_failure_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, size in [('wide', (40, 20)), ('tall', (20, 40))]:
                source = Image.new('RGB', size, 'red')
                source.paste('blue', (0, size[1]//2, size[0], size[1]))
                source.save(root / f'{name}.png')
            command = [sys.executable, str(Path(converter.__file__)), '-s', '315', '-O', 'portrait',
                       '-f', 'crop', '-d', 'fs', '-j', '2', '-b', '1', '-c', '1', '-S', '1', str(root)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name in ('wide', 'tall'):
                image, _ = decode(root / f'{name}_1440x2560_s6.bin')
                self.assertEqual(image.getpixel((720, 100)), (255, 0, 0))
                self.assertEqual(image.getpixel((720, 2460)), (0, 0, 255))
            (root / 'broken.png').write_bytes(b'not an image')
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 1)
            self.assertIn('1 of 3 file(s) failed', result.stdout)


if __name__ == '__main__':
    unittest.main()
