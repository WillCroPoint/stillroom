import unittest
from PIL import Image
from image_background import flatten, gradient_colors, has_transparency
import gui
import convert_to_bin_spectra6 as converter


class BackgroundTests(unittest.TestCase):
    def test_hidden_rgb_does_not_tint_gradient(self):
        image = Image.new('RGBA', (2, 1), (255, 0, 255, 0))
        image.putpixel((0, 0), (100, 60, 30, 255))
        self.assertEqual(gradient_colors(image), gradient_colors(Image.new('RGB', (1, 1), (100, 60, 30))))

    def test_composite_and_opaque_subject(self):
        image = Image.new('RGBA', (3, 1), (200, 100, 50, 0))
        image.putpixel((1, 0), (200, 100, 50, 128))
        image.putpixel((2, 0), (200, 100, 50, 255))
        result = flatten(image, color='#ffffff')
        self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(result.getpixel((1, 0)), (227, 177, 152))
        self.assertEqual(result.getpixel((2, 0)), (200, 100, 50))

    def test_gradient_direction_and_opaque_passthrough(self):
        image = Image.new('RGBA', (10, 10))
        right = flatten(image, 'gradient', angle=0)
        down = flatten(image, 'gradient', angle=90)
        self.assertEqual(right.getpixel((9, 0)), down.getpixel((0, 9)))
        self.assertNotEqual(right.getpixel((0, 0)), right.getpixel((9, 0)))
        opaque = Image.new('RGB', (4, 4), 'red')
        self.assertFalse(has_transparency(opaque))
        self.assertEqual(flatten(opaque, 'gradient').tobytes(), opaque.tobytes())

    def test_settings_validation_and_cli(self):
        for settings in ({'background_color':'red'}, {'background_angle':float('nan')}, {'background':'bad'}):
            with self.assertRaises(gui.APIError):
                gui.validate_settings(settings)
        args = converter.parse_args(['-B','gradient','-A','180','-C','#123456','image.png'])
        self.assertEqual(args.background_angle, 180)

    def test_letterbox_gradient_covers_frame_without_seam(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from image_background import extend_to_frame
        source = Image.new('RGBA', (8, 4))
        source.putpixel((4, 2), (100, 40, 20, 255))
        panel = SimpleNamespace(width=12, height=20)
        for orientation, size in [('portrait', (12, 20)), ('landscape', (20, 12))]:
            frame = dict(screen='133', orientation=orientation)
            settings = gui.validate_settings(dict(fit='letterbox', profile='natural', background='gradient', background_angle=135))
            with patch.dict(converter.PANELS, {'133':panel}):
                result = gui.compose_image(source, frame, settings)
                fitted = converter.scale_to_frame(source, 'letterbox', panel, orientation)
                expected = flatten(extend_to_frame(fitted, size, True), 'gradient', angle=135, colors=gradient_colors(source))
                self.assertEqual(result.tobytes(), expected.tobytes())
                self.assertNotEqual(result.getpixel((0, 0)), (0, 0, 0))
                settings['background'] = 'solid'
                self.assertEqual(gui.compose_image(source, frame, settings).getpixel((0, 0)), (255, 255, 255))
                settings['background'] = 'gradient'
                self.assertNotEqual(gui.compose_image(source.convert('RGB'), frame, settings).getpixel((0, 0)), (0, 0, 0))

    def test_solid_unifies_transparency_and_letterbox(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        source = Image.new('RGBA', (8, 4), (200, 40, 20, 0))
        source.putpixel((4, 2), (200, 40, 20, 255))
        settings = gui.validate_settings(dict(fit='letterbox', background_color='#123456', profile='natural'))
        with patch.dict(converter.PANELS, {'133':SimpleNamespace(width=8, height=8)}):
            result = gui.compose_image(source, dict(screen='133', orientation='portrait'), settings)
            self.assertEqual(result.getpixel((0, 0)), (18, 52, 86))
            self.assertEqual(result.getpixel((0, 3)), (18, 52, 86))
            self.assertEqual(result.getpixel((4, 4)), (200, 40, 20))
