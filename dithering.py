"""Shared six-colour dithering. Optional engines are never silently substituted."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

PALETTE_COLORS = [(0, 0, 0), (255, 255, 255), (255, 255, 0),
                  (255, 0, 0), (0, 0, 255), (0, 255, 0)]
DEFAULT_DITHER = 'fs'
DITHERS = {
    'fs': dict(label='Floyd–Steinberg · fast', description='A balanced starting point for photos. Fast conversion with Pillow.'),
    'fs-serpentine': dict(label='Floyd–Steinberg · serpentine', description='Alternates scan direction on each row to reduce directional patterns. Slower.'),
    'stucki': dict(label='Stucki', description='Spreads error across a wider neighbourhood for a different, often softer grain. Slower.'),
    'sierra': dict(label='Sierra', description='Three-row error diffusion, another balance between detail and grain. Slower.'),
    'atkinson': dict(label='Atkinson · classic', description='Correct six-neighbour algorithm. Discards 25% of the error: a graphic look that can lose shadow and highlight detail.'),
    'epd': dict(label='epd-dither · blue noise', description='Optional external Spectra 6 engine: colour mixtures and blue noise. Uses its own panel palette, not calibrated to your frame.'),
}

# (dx, dy, numerator); standard kernels, no renormalisation at image edges.
KERNELS = {
    'fs-serpentine': (16, ((1,0,7), (-1,1,3), (0,1,5), (1,1,1))),
    'atkinson': (8, ((1,0,1), (2,0,1), (-1,1,1), (0,1,1), (1,1,1), (0,2,1))),
    'stucki': (42, ((1,0,8), (2,0,4), (-2,1,2), (-1,1,4), (0,1,8), (1,1,4), (2,1,2),
                    (-2,2,1), (-1,2,2), (0,2,4), (1,2,2), (2,2,1))),
    'sierra': (32, ((1,0,5), (2,0,3), (-2,1,2), (-1,1,4), (0,1,5), (1,1,4), (2,1,2),
                    (-1,2,2), (0,2,3), (1,2,2))),
}


def epd_executable():
    """Only resolve an explicitly named engine, not an unrelated 'dither' command."""
    configured = os.environ.get('FRAIMIC_EPD_DITHER')
    return shutil.which(os.path.expanduser(configured)) if configured else shutil.which('epd-dither')


def dither_options():
    return {key: dict(value, available=key != 'epd' or epd_executable() is not None)
            for key, value in DITHERS.items()}


def quantize_floydsteinberg_indexed(image):
    import numpy as np
    from PIL import Image
    palette = Image.new('P', (1, 1))
    # Keep the historical Pillow palette; padded slots duplicate black.
    palette.putpalette([v for rgb in PALETTE_COLORS for v in rgb] + [0,0,0] * 250)
    result = np.array(image.convert('RGB').quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG))
    # Pillow may return a duplicated palette slot; device indices are always 0..5.
    result[result >= 6] = 0
    return result


def quantize_diffusion(image, method):
    import numpy as np
    working = np.array(image.convert('RGB'), dtype=np.float32)
    height, width = working.shape[:2]
    result = np.empty((height, width), dtype=np.uint8)
    palette = np.asarray(PALETTE_COLORS, dtype=np.float32)
    divisor, kernel = KERNELS[method]
    for y in range(height):
        direction = -1 if method != 'atkinson' and y % 2 else 1
        for x in (range(width) if direction == 1 else range(width-1, -1, -1)):
            old = working[y, x].copy()
            # One common RGB metric; retain floating point error, including overshoot.
            distances = ((palette - old) ** 2).sum(axis=1)
            index = int(np.argmin(distances))
            result[y, x] = index
            error = (old - palette[index]) / divisor
            for dx, dy, weight in kernel:
                nx, ny = x + direction * dx, y + dy
                if 0 <= nx < width and ny < height:
                    working[ny, nx] += error * weight
    return result


def quantize_atkinson_indexed(image):
    return quantize_diffusion(image, 'atkinson')


def quantize_epd_indexed(image):
    import numpy as np
    from PIL import Image
    executable = epd_executable()
    if not executable:
        raise ValueError('epd-dither is not installed. See the optional engine instructions in docs/CLI.md; '
                         'set FRAIMIC_EPD_DITHER to its executable, or choose another dithering method.')
    with tempfile.TemporaryDirectory(prefix='fraimic-epd-') as directory:
        source, target = Path(directory) / 'source.png', Path(directory) / 'result.png'
        image.convert('RGB').save(source)
        # Use the engine's actual Spectra palette for its calculations. Output pure
        # RGB labels preserve device colour identities; never quantize its output again.
        command = [executable, str(source), str(target), '--noise', 'blue',
                   '--strategy', 'octahedron-closest', '--dither-palette', 'spectra6',
                   '--output-palette', 'naive']
        try:
            run = subprocess.run(command, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f'epd-dither could not complete: {exc}') from exc
        if run.returncode:
            raise ValueError(f'epd-dither failed: {(run.stderr or run.stdout)[-1500:].strip()}')
        try:
            with Image.open(target) as output:
                if output.size != image.size:
                    raise ValueError('epd-dither returned an unexpected image size')
                pixels = np.array(output.convert('RGB'))
        except OSError as exc:
            raise ValueError('epd-dither did not produce a readable image') from exc
        indices = np.full(pixels.shape[:2], 255, dtype=np.uint8)
        for index, colour in enumerate(PALETTE_COLORS):
            indices[np.all(pixels == colour, axis=2)] = index
        if np.any(indices == 255):
            raise ValueError('epd-dither returned colours outside the six-colour output palette')
        return indices


def quantize_image(image, method=DEFAULT_DITHER):
    if method == 'fs':
        return quantize_floydsteinberg_indexed(image)
    if method in KERNELS:
        return quantize_diffusion(image, method)
    if method == 'epd':
        return quantize_epd_indexed(image)
    raise ValueError(f'Unknown dithering method: {method}')
