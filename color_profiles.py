"""Shared, dependency-free profile catalogue; image libraries are loaded on use."""
DEFAULT_PROFILE = 'soft'
PROFILES = {
    'soft': dict(label='Soft', description='Gentler contrast, lifted shadows and restrained highlights.', brightness=1.0, contrast=1.0, saturation=1.0),
    'natural': dict(label='Natural', description='No automatic enhancement. Keep the source tones and colours.', brightness=1.0, contrast=1.0, saturation=1.0),
    'vivid': dict(label='Vivid', description='Richer colours and stronger contrast, with a gradual highlight roll-off.', brightness=1.0, contrast=1.0, saturation=1.0),
    'original': dict(label='Original', description='The original converter: brighter, stronger contrast and sharpening.', brightness=1.1, contrast=1.2, saturation=1.2),
}


def enhance_image(image, brightness=None, contrast=None, saturation=None, profile=DEFAULT_PROFILE):
    """Apply a look before quantization; explicit factors override its defaults.

    Soft/vivid adjust luminance in floating point with endpoint-preserving curves.
    Chroma is compressed toward that luminance only when it would leave RGB gamut,
    rather than clipping individual channels. No profile can recover source detail
    already clipped, or eliminate the limitations of a six-colour display.
    """
    import numpy as np
    from PIL import Image, ImageEnhance, ImageFilter

    if profile not in PROFILES:
        raise ValueError(f'Unknown colour profile: {profile}')
    defaults = PROFILES[profile]
    factors = [defaults[key] if value is None else value for key, value in
               zip(('brightness', 'contrast', 'saturation'), (brightness, contrast, saturation))]
    if any(not np.isfinite(value) or value < 0 for value in factors):
        raise ValueError('Enhancement factors must be finite and non-negative')
    image = image.convert('RGB')
    if profile in ('soft', 'vivid'):
        rgb = np.asarray(image, dtype=np.float32) / 255.0
        lum = (rgb * np.array([.2126, .7152, .0722], dtype=np.float32)).sum(axis=2, keepdims=True)
        shadow, strength, shoulder, colour = ((.12, -.12, .35, .98) if profile == 'soft' else (.10, .50, .15, 1.18))
        target = lum + shadow * lum * (1-lum) + strength * lum * (1-lum) * (2*lum-1) - shoulder * lum**4 * (1-lum)
        chroma = (rgb - lum) * colour
        # Find one scale for all channels, preserving hue at the gamut boundary.
        room = np.where(chroma > 0, 1-target, target)
        scale = np.minimum(1.0, (room / np.maximum(np.abs(chroma), 1e-8)).min(axis=2, keepdims=True))
        mapped = target + chroma * scale
        image = Image.fromarray(np.rint(np.clip(mapped, 0, 1) * 255).astype(np.uint8))
    for enhancement, factor in zip((ImageEnhance.Brightness, ImageEnhance.Contrast, ImageEnhance.Color), factors):
        if factor != 1:
            image = enhancement(image).enhance(factor)
    if profile == 'original':
        for image_filter in (ImageFilter.EDGE_ENHANCE, ImageFilter.SMOOTH, ImageFilter.SHARPEN):
            image = image.filter(image_filter)
    return image
