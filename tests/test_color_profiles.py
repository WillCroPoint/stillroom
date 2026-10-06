import unittest
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from unittest.mock import patch
import io
import contextlib

from color_profiles import enhance_image, PROFILES
import convert_to_bin_spectra6 as converter
import gui
import upload


class ColourProfileTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.fromarray(np.random.default_rng(7).integers(0,256,(48,64,3),dtype=np.uint8))

    def test_original_is_exactly_legacy(self):
        expected = ImageEnhance.Brightness(self.image).enhance(1.1)
        expected = ImageEnhance.Contrast(expected).enhance(1.2)
        expected = ImageEnhance.Color(expected).enhance(1.2)
        for effect in (ImageFilter.EDGE_ENHANCE,ImageFilter.SMOOTH,ImageFilter.SHARPEN):
            expected = expected.filter(effect)
        np.testing.assert_array_equal(enhance_image(self.image,profile='original'),expected)

    def test_natural_is_identity_and_overrides_are_explicit(self):
        np.testing.assert_array_equal(enhance_image(self.image,profile='natural'),self.image)
        np.testing.assert_array_equal(enhance_image(self.image,brightness=.8,profile='natural'),
                                      ImageEnhance.Brightness(self.image).enhance(.8))

    def test_highlight_ramp_retains_gradation(self):
        ramp = np.arange(180,256,dtype=np.uint8)
        image = Image.fromarray(np.tile(ramp[None,:,None],(16,1,3)))
        for profile in ('soft','vivid'):
            actual=np.asarray(enhance_image(image,profile=profile))[8,:,0]
            self.assertTrue(np.all(np.diff(actual.astype(int))>=0))
            self.assertGreater(len(np.unique(actual)),55)
            self.assertLess(np.sum(actual==255),3)
        legacy=np.asarray(enhance_image(image,profile='original'))[8,:,0]
        self.assertGreater(np.sum(legacy==255),10)

    def test_profiles_are_distinct_and_shared_with_gui(self):
        outputs=[np.asarray(enhance_image(self.image,profile=p)).tobytes() for p in PROFILES]
        self.assertEqual(len(set(outputs)),len(PROFILES))
        for p in PROFILES:
            settings=gui.validate_settings({'profile':p})
            actual=enhance_image(self.image,settings['brightness'],settings['contrast'],settings['saturation'],settings['profile'])
            np.testing.assert_array_equal(actual,enhance_image(self.image,profile=p))
        with self.assertRaises(gui.APIError): gui.validate_settings({'profile':'bad'})
        self.assertEqual(converter.parse_args(['photo.png']).profile,'soft')
        self.assertEqual(converter.parse_args(['-P','original','photo.png']).profile,'original')

    def test_upload_forwards_profile(self):
        with patch('sys.argv',['upload.py','frame','photo.jpg','-P','natural']), \
             patch('upload.convert_image_to_bin',return_value='photo.bin') as convert, \
             patch('upload.read_battery',return_value=None), patch('upload.upload_bin',return_value=(200,'{}')),contextlib.redirect_stdout(io.StringIO()):
            upload.main()
        self.assertEqual(convert.call_args.kwargs['profile'],'natural')
        with patch('sys.argv',['upload.py','frame','photo.bin','-P','natural']), \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            upload.main()


if __name__=='__main__': unittest.main()
