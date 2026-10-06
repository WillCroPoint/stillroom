import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
from PIL import Image
import dithering as d
import convert_to_bin_spectra6 as converter
import gui
from legacy_dithering import quantize_fraimic_legacy_indexed


class DitheringTests(unittest.TestCase):
    def test_defaults_and_dispatch_in_interfaces(self):
        self.assertEqual(converter.parse_args(['photo.png']).dither, 'fs')
        self.assertEqual(gui.validate_settings({})['dither'], 'fs')
        for method in d.DITHERS:
            self.assertEqual(converter.parse_args(['-d', method, 'photo.png']).dither, method)
            self.assertEqual(gui.validate_settings({'dither': method})['dither'], method)
        with self.assertRaises(ValueError):
            d.quantize_image(Image.new('RGB', (1,1)), 'legacy')

    def test_standard_atkinson_kernel(self):
        divisor, weights = d.KERNELS['atkinson']
        self.assertEqual(divisor, 8)
        self.assertEqual(set(weights), {(1,0,1),(2,0,1),(-1,1,1),(0,1,1),(1,1,1),(0,2,1)})
        for name in ('stucki', 'sierra', 'fs-serpentine'):
            divisor, kernel = d.KERNELS[name]
            self.assertEqual(sum(weight for _,_,weight in kernel), divisor)

    def test_palette_identity_edges_and_determinism(self):
        for method in [name for name in d.DITHERS if name != 'epd']:
            for index, colour in enumerate(d.PALETTE_COLORS):
                image = Image.new('RGB', (5,4), colour)
                np.testing.assert_array_equal(d.quantize_image(image, method), np.full((4,5),index))
            for size in [(1,1),(1,9),(9,1),(9,7)]:
                pixels=np.random.default_rng(12).integers(0,256,(size[1],size[0],3),dtype=np.uint8)
                image=Image.fromarray(pixels)
                actual=d.quantize_image(image,method)
                self.assertEqual(actual.shape,(size[1],size[0]))
                self.assertLess(actual.max(),6)
                np.testing.assert_array_equal(actual,d.quantize_image(image,method))

    def test_tones_are_not_crushed_by_full_diffusion(self):
        palette=np.array(d.PALETTE_COLORS)
        for rgb in [(35,35,35),(220,220,220),(200,150,120)]:
            image=Image.new('RGB',(64,64),rgb)
            for method in ('fs','fs-serpentine','stucki','sierra'):
                mean=palette[d.quantize_image(image,method)][8:-8,8:-8].mean(axis=(0,1))
                self.assertLess(np.abs(mean-rgb).max(),5,(method,rgb,mean))
        # Regression: corrected Atkinson must not preserve the old 5/8 variant.
        image=Image.fromarray(np.tile(np.arange(256,dtype=np.uint8),(24,1))[...,None].repeat(3,axis=2))
        self.assertFalse(np.array_equal(d.quantize_atkinson_indexed(image),quantize_fraimic_legacy_indexed(image)))

    def test_epd_unavailable_does_not_fall_back(self):
        with patch('dithering.epd_executable',return_value=None):
            self.assertFalse(d.dither_options()['epd']['available'])
            with self.assertRaisesRegex(ValueError,'not installed'):
                d.quantize_image(Image.new('RGB',(2,2)),'epd')

    def test_epd_output_is_mapped_by_colour_and_temp_files_removed(self):
        directories=[]
        def run(command, **kwargs):
            self.assertEqual(command[3:], ['--noise','blue','--strategy','octahedron-closest',
                '--dither-palette','spectra6','--output-palette','naive'])
            directories.append(Path(command[1]).parent)
            # Reversed palette slots exercise RGB identity mapping, not PNG slot order.
            output=Image.fromarray(np.arange(6,dtype=np.uint8).reshape(1,6)).convert('P')
            output.putpalette([v for rgb in reversed(d.PALETTE_COLORS) for v in rgb]+[0]*750)
            output.save(command[2])
            return SimpleNamespace(returncode=0)
        with patch('dithering.epd_executable',return_value='/fake/epd-dither'),patch('dithering.subprocess.run',side_effect=run):
            result=d.quantize_image(Image.new('RGB',(6,1)),'epd')
        np.testing.assert_array_equal(result,[[5,4,3,2,1,0]])
        self.assertFalse(directories[0].exists())

    def test_epd_rejects_bad_output_and_failures(self):
        for mode in ('size','colour','exit'):
            directories=[]
            def run(command, **kwargs):
                directories.append(Path(command[1]).parent)
                Image.new('RGB',(1,1) if mode=='size' else (2,2),(123,44,11)).save(command[2])
                return SimpleNamespace(returncode=1 if mode=='exit' else 0,stderr='engine failed',stdout='')
            with patch('dithering.epd_executable',return_value='/fake/epd-dither'),patch('dithering.subprocess.run',side_effect=run):
                with self.assertRaises(ValueError):
                    d.quantize_image(Image.new('RGB',(2,2)),'epd')
            self.assertFalse(directories[0].exists())


if __name__ == '__main__':
    unittest.main()
