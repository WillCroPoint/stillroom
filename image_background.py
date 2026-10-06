"""Transparency backgrounds shared by the CLI and Studio; no extra dependencies."""
import re
import numpy as np
from PIL import Image


def has_transparency(image):
    return image.convert('RGBA').getchannel('A').getextrema()[0] < 255


def background_color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Background colour must be #RRGGBB')
    return value


def gradient_colors(image):
    # Ignore hidden RGB in transparent pixels; weight edges by their coverage.
    sample = image.convert('RGBA')
    sample.thumbnail((128, 128))
    pixels = np.asarray(sample, dtype=np.float32).reshape(-1, 4)
    weights = pixels[:, 3]
    mean = np.average(pixels[:, :3], axis=0, weights=weights) if weights.sum() else np.array([180., 180., 180.])
    luminance = mean @ np.array([.2126, .7152, .0722])
    tint = luminance + (mean - luminance) * .3
    return ['#' + ''.join(f'{int(v):02x}' for v in np.rint(tint * amount + 255 * (1 - amount))) for amount in (.12, .38)]


def flatten(image, mode='solid', color='#ffffff', angle=90, colors=None):
    """Angle in display coordinates: 0 left→right, 90 top→bottom."""
    if not has_transparency(image):
        return image.convert('RGB')
    if mode not in ('solid', 'gradient'):
        raise ValueError('Unknown background mode')
    background_color(color)
    if not np.isfinite(angle) or not 0 <= angle <= 360:
        raise ValueError('Background angle must be between 0 and 360')
    rgba = image.convert('RGBA')
    background = Image.new('RGB', image.size, color)
    if mode == 'gradient':
        colors = colors or gradient_colors(image)
        ends = [np.array(tuple(bytes.fromhex(c[1:])), dtype=np.float32) for c in colors]
        w, h = image.size
        dx, dy = np.cos(np.deg2rad(angle)), np.sin(np.deg2rad(angle))
        span = abs(dx) * w + abs(dy) * h
        x = (np.arange(w, dtype=np.float32) + .5 - w/2) * dx
        # Work one row at a time to keep memory bounded at panel resolution.
        for y in range(h):
            t = np.clip(.5 + (x + (y + .5 - h/2) * dy) / span, 0, 1)
            row = np.rint(ends[0] + t[:, None] * (ends[1] - ends[0])).astype('uint8')
            background.paste(Image.fromarray(row[None, :, :]), (0, y))
    background.paste(rgba, mask=rgba.getchannel('A'))
    return background


def extend_to_frame(image, size, enabled):
    """Centre the fitted RGBA subject on a transparent full-frame canvas."""
    if not enabled or image.size == size:
        return image
    canvas = Image.new('RGBA', size)
    canvas.paste(image.convert('RGBA'), ((size[0]-image.width)//2, (size[1]-image.height)//2))
    return canvas
