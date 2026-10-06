"""Historical Fraimic quantizer, preserved for comparison only; not exposed in the UI."""
import numpy as np
from dithering import PALETTE_COLORS

# Precompute palette as NumPy arrays for faster access
PALETTE_ARRAY = np.array(PALETTE_COLORS, dtype=np.float32)
# blue and green prints darker, lower its luma value so the distance metric favors it over white, also at luma1
PALETTE_LUMA_ARRAY = np.array([r*250 + g*350 + b*400 for (r, g, b) in PALETTE_COLORS], dtype=np.float32) / (255.0 * 1000)


# Find the closest palette color using floating-point arithmetic (exact RGBL method)
def closest_palette_color(rgb):
    r1, g1, b1 = rgb
    # Calculate luma for the input pixel
    luma1 = (r1 * 250 + g1 * 350 + b1 * 400) / (255.0 * 1000)

    # Calculate differences using precomputed arrays
    diffR = r1 - PALETTE_ARRAY[:, 0]
    diffG = g1 - PALETTE_ARRAY[:, 1]
    diffB = b1 - PALETTE_ARRAY[:, 2]

    # Calculate RGB component of distance
    # boost blue, reduce green a bit and red a little more to compensate for human eye sensitivity and e-ink display characteristics (trial and error)
    rgb_dist = (diffR*diffR*0.250 + diffG*diffG*0.350 + diffB*diffB*0.400) * 0.75 / (255.0*255.0)

    # Calculate luma differences
    luma_diff = luma1 - PALETTE_LUMA_ARRAY
    luma_dist = luma_diff * luma_diff

    # Total distance
    total_dist = 1.5*rgb_dist + 0.60*luma_dist  # hue errors are more important, increased the rgb_dist factor.

    # Find minimum distance index
    return np.argmin(total_dist)


# Atkinson dithering returning a per-pixel palette-index array (not RGB).
# Uses the tuned closest_palette_color metric for each decision.
def quantize_fraimic_legacy_indexed(image):
    img_array = np.array(image.convert('RGB'))
    height, width, _ = img_array.shape
    # Use float array for error diffusion to avoid integer truncation issues
    working_img = img_array.astype(np.float32)
    indices = np.zeros((height, width), dtype=np.uint8)

    for y in range(height):
        for x in range(width):
            old_pixel = working_img[y, x].copy()
            # Use exact color comparison instead of lookup table for better accuracy
            idx = closest_palette_color(tuple(np.clip(old_pixel, 0, 255).astype(int)))
            new_pixel = np.array(PALETTE_COLORS[idx], dtype=np.float32)
            working_img[y, x] = new_pixel
            indices[y, x] = idx

            # Calculate error
            error = old_pixel - new_pixel

            # Atkinson error distribution - only to not-yet-processed pixels (right and down)
            # Weights: Right: 1/8, Bottom-left: 1/8, Bottom: 1/4, Bottom-right: 1/8
            # Total distributed: 5/8. Historical Fraimic variant, NOT standard Atkinson.
            if x + 1 < width:
                working_img[y, x + 1] += error * (1/8)
            if y + 1 < height:
                if x - 1 >= 0:
                    working_img[y + 1, x - 1] += error * (1/8)
                working_img[y + 1, x] += error * (1/4)
                if x + 1 < width:
                    working_img[y + 1, x + 1] += error * (1/8)

    return indices


