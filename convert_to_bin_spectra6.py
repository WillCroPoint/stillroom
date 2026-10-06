#!/usr/bin/env python3
#encoding: utf-8

"""
Convert images to the Spectra 6 .bin format, for either the 13.3" panel
(EL133UF1 controller, 1200x1600) or the 31.5" panel (EL315, 1440x2560).

Supports several six-colour dithering methods. Instead of saving a BMP it tracks
the per-pixel palette index and packs the 4-bit indexed
.bin the chosen panel expects (two pixels per byte; see the packers below for
each panel's memory layout).
"""

import sys
import os
import os.path
import numpy as np
from PIL import Image, ImageOps
from color_profiles import DEFAULT_PROFILE, PROFILES, enhance_image
import argparse
from image_background import extend_to_frame, flatten, gradient_colors, background_color
from threaded_function_runner import ThreadedFunctionRunner

#################################################################################
# DEBUG: open generated image in browser
#import webbrowser
#################################################################################

# HEIC support is optional: only enabled if pillow-heif is installed. JPEG/PNG/etc
# work without it.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False

# Supported input formats (.heic only when pillow-heif is available)
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp', '.gif']
if HEIC_SUPPORTED:
    IMAGE_EXTENSIONS.append('.heic')

from dithering import (PALETTE_COLORS, DEFAULT_DITHER, DITHERS, dither_options,
                       quantize_image, quantize_atkinson_indexed,
                       quantize_floydsteinberg_indexed)

# 4-bit device codes for the EL133UF1 panel. Note 0x4 is intentionally skipped.
#                       Black White Yellow Red  Blue Green
COLOR_CODES = np.array([0x0,  0x1,  0x2,   0x3, 0x5, 0x6], dtype=np.uint8)

# White. Used for the off-panel dummy pixels in the EL315 padded ICs, which are
# always 0x11 regardless of the image's own border color.
WHITE_CODE = 0x1

# Letterbox border colors, selectable with --letterbox.
LETTERBOX_COLORS = {'black': (0, 0, 0), 'white': (255, 255, 255)}

# Scale an (already EXIF-corrected, RGB) image to its final on-panel pixel size.
# Under 'crop' this returns exactly the panel frame; under letterbox it
# returns the picture alone, which pad_to_frame later centers on the frame.
# Kept separate from padding so enhancement runs on the picture only — see
# process_image.
def scale_to_frame(image, fit, panel, orientation="portrait"):
    img = image
    width, height = img.size
    target_width, target_height = panel.width, panel.height

    # Fit in the user's viewing orientation. Storage rotation happens only
    # after cropping/padding, so source content stays upright on the frame.
    if orientation == 'landscape':
        target_width, target_height = target_height, target_width

    if fit == 'crop':
        # Scale to fill, then center-crop the overflow (no borders, edges lost).
        scale_ratio = max(target_width / width, target_height / height)
        resized_width = max(1, int(round(width * scale_ratio)))
        resized_height = max(1, int(round(height * scale_ratio)))
        resized = img.resize((resized_width, resized_height), Image.LANCZOS)
        left = (resized_width - target_width) // 2
        top = (resized_height - target_height) // 2
        return resized.crop((left, top, left + target_width, top + target_height))

    # 'letterbox': scale to fit entirely inside
    # the frame, no cropping. Any leftover space becomes bars in pad_to_frame.
    scale_ratio = min(target_width / width, target_height / height)
    resized_width = max(1, int(round(width * scale_ratio)))
    resized_height = max(1, int(round(height * scale_ratio)))
    return img.resize((resized_width, resized_height), Image.LANCZOS)


# Center the scaled picture on the panel frame, padding any remainder with
# letterbox_rgb. A no-op when the picture already fills the frame (e.g. --fit crop).
def pad_to_frame(image, panel, letterbox_rgb, orientation="portrait"):
    width, height = panel.width, panel.height
    if orientation == 'landscape':
        width, height = height, width
    if image.size == (width, height):
        return image

    framed = Image.new('RGB', (width, height), letterbox_rgb)
    framed.paste(image, ((width - image.width) // 2,
                         (height - image.height) // 2))
    return framed


# Pack device codes into the EL133UF1 (13.3") .bin layout.
def pack_el133uf1(color_code_array):
    """
    - 1200x1600 pixels, portrait
    - Two pixels per byte (high nibble = even col, low nibble = odd col)
    - Split into left half (cols 0-599) then right half (cols 600-1199):
      all left-half bytes for the whole image come first, then all right-half bytes
    - Total size: 960,000 bytes
    """
    left_half = color_code_array[:, 0:600]
    left_packed = (left_half[:, 0::2] << 4) | left_half[:, 1::2]

    right_half = color_code_array[:, 600:1200]
    right_packed = (right_half[:, 0::2] << 4) | right_half[:, 1::2]

    return np.concatenate([left_packed.ravel(), right_packed.ravel()]).astype(np.uint8)


# EL315 block geometry: 8 IC blocks, each 720 block rows x 800 block pixels.
EL315_BLOCK_ROWS = 720
EL315_BLOCK_PIXELS = 800
EL315_PADDED_PIXELS = 160  # real pixels per row in the padded ICs (IC4, IC8)
EL315_ROW_PIXELS = 2560    # block pixels per block row, across an IC group
EL315_HALF_ROWS = 1280     # image rows covered by one IC group


# Pack device codes into the EL315 (31.5") .bin layout.
def pack_el315(color_code_array):
    """
    - 1440x2560 pixels, portrait
    - 8 IC blocks of 288,000 bytes written sequentially IC1 -> IC8; each block is
      720 block rows x 400 bytes, two pixels per byte (high nibble first)
    - The ICs come in two groups of four, each group covering half the image:
      IC1-IC4 the BOTTOM half (rows 1280-2559), IC5-IC8 the TOP half (rows 0-1279).
    - Within a group, one block row is a 2-pixel-wide VERTICAL STRIP of the image,
      1280 rows tall, read bottom->top; the two pixels of each image row are stored
      left then right. So block row b covers image columns 2b and 2b+1, and block
      pixel p sits at image row offset p // 2 up from the bottom of the half.
    - The four ICs in a group split that 1280-row strip as 400/400/400/80 rows,
      counting up from the bottom of the half, so IC4 and IC8 hold only 160 real
      pixels per row; the remaining 320 bytes of their rows are 0x11 padding.
    - Total size: 2,304,000 bytes
    """
    # Flipping vertically puts the bottom half of the image first, matching the
    # IC1-IC4 group, and makes each half read bottom->top.
    flipped = np.flipud(color_code_array)  # 2560 x 1440

    blocks = []
    for half in range(2):  # IC1-IC4 (bottom half), then IC5-IC8 (top half)
        strip = flipped[half * EL315_HALF_ROWS:(half + 1) * EL315_HALF_ROWS]
        # Regroup 1280 rows x 1440 cols into 720 block rows of 2560 pixels, so that
        # each block row walks one 2-px-wide column pair down the strip.
        band = (strip.reshape(EL315_HALF_ROWS, EL315_BLOCK_ROWS, 2)
                     .transpose(1, 0, 2)
                     .reshape(EL315_BLOCK_ROWS, EL315_ROW_PIXELS))
        for ic in range(4):
            real_pixels = EL315_PADDED_PIXELS if ic == 3 else EL315_BLOCK_PIXELS
            start = ic * EL315_BLOCK_PIXELS
            # Prefill with white so the padded ICs' dummy bytes come out as 0x11.
            nibbles = np.full((EL315_BLOCK_ROWS, EL315_BLOCK_PIXELS), WHITE_CODE, dtype=np.uint8)
            nibbles[:, :real_pixels] = band[:, start:start + real_pixels]
            blocks.append((nibbles[:, 0::2] << 4) | nibbles[:, 1::2])

    return np.concatenate([block.ravel() for block in blocks]).astype(np.uint8)


# A supported screen: its portrait frame, its exact .bin size, and its packer.
class Panel:
    def __init__(self, key, label, width, height, bin_size, packer):
        self.key = key
        self.label = label
        self.width = width
        self.height = height
        self.bin_size = bin_size
        self.packer = packer

    # Output filename suffix, e.g. '_1200x1600_s6.bin'.
    @property
    def suffix(self):
        return f'_{self.width}x{self.height}_s6.bin'


PANELS = {
    '133': Panel('133', 'Spectra 6 13.3" / EL133UF1', 1200, 1600, 960000, pack_el133uf1),
    '315': Panel('315', 'Spectra 6 31.5" / EL315', 1440, 2560, 2304000, pack_el315),
}
DEFAULT_PANEL = '133'


# Pack the per-pixel index array into the given panel's .bin format.
def generate_binary_file(color_indices, output_path, panel):
    height, width = color_indices.shape
    if width != panel.width or height != panel.height:
        raise ValueError(f"Image must be exactly {panel.width}x{panel.height}, got {width}x{height}")

    # Map palette indices to 4-bit device codes (vectorized)
    binary_data = panel.packer(COLOR_CODES[color_indices])

    if len(binary_data) != panel.bin_size:
        raise ValueError(f"Binary file must be exactly {panel.bin_size} bytes, got {len(binary_data)}")

    with open(output_path, 'wb') as f:
        f.write(binary_data.tobytes())


def output_path(image_file, args):
    name = os.path.splitext(os.path.basename(image_file))[0] + PANELS[args.screen].suffix
    return os.path.join(args.output_dir or os.path.dirname(image_file), name)


# Convert a single image file to a .bin. Returns True on success, False on failure.
def process_image(image_file, args):
    panel = PANELS[args.screen]
    try:
        # Read input image and apply EXIF orientation so phone photos aren't sideways.
        input_image = Image.open(image_file)
        if not args.no_transpose:
            input_image = ImageOps.exif_transpose(input_image)
        input_image = input_image.convert('RGBA')
        colors = gradient_colors(input_image)

        # Scale to the final on-panel size, but don't add the letterbox bars yet.
        scaled_image = scale_to_frame(input_image, args.fit, panel, args.orientation)

        scaled_image = enhance_subject(scaled_image, args.brightness, args.contrast, args.saturation, args.profile)
        frame_size = (panel.width, panel.height) if args.orientation == 'portrait' else (panel.height, panel.width)
        scaled_image = extend_to_frame(scaled_image, frame_size, args.fit == 'letterbox')
        framed_image = flatten(scaled_image, getattr(args, 'background', 'solid'),
                               getattr(args, 'background_color', None) or ('#000000' if getattr(args, 'letterbox', None) == 'black' else '#ffffff'),
                               getattr(args, 'background_angle', 90), colors)
        # Both devices expect portrait storage. A landscape-mounted panel is
        # turned counter-clockwise, so store the composed image clockwise.
        if args.orientation == 'landscape':
            framed_image = framed_image.transpose(Image.Transpose.ROTATE_270)

        # Quantize to per-pixel palette indices
        color_indices = quantize_image(framed_image, args.dither)

        # Determine output path (next to input, or in --output-dir if given)
        output_filename = output_path(image_file, args)

        #################################################################################
        ## DEBUG: open generated image in browser
        #debug_output_filename = output_filename + '-DEBUG.png'
        ##scaled_image.save(debug_output_filename)
        #framed_image.save(debug_output_filename)
        #webbrowser.open('file://' + debug_output_filename)
        #################################################################################

        generate_binary_file(color_indices, output_filename, panel)

        #################################################################################
        #print(f'Successfully converted {image_file} to {output_filename}')
        #################################################################################
        return True
    except Exception as e:
        print(f'Error processing {image_file}: {e}')
        return False


def normalize_orientation(value):
    aliases = {'portrait': 'portrait', 'vertical': 'portrait',
               'landscape': 'landscape', 'horizontal': 'landscape'}
    try:
        return aliases[value.lower()]
    except KeyError:
        raise argparse.ArgumentTypeError('use portrait/vertical or landscape/horizontal')


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Convert images to Spectra 6 .bin for the 13.3" (EL133UF1) or 31.5" (EL315) panel.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''Examples (orientation describes the FRAME, not the source photo):
  Vertical frame, fill and crop a landscape photo, then preview:
    %(prog)s -s 315 -O portrait -f crop -p landscape.jpg
  Horizontal frame, keep the whole photo with bars, then preview:
    %(prog)s -s 315 -O landscape -f letterbox -p photo.jpg
  Batch on four CPU processes (no batch preview):
    %(prog)s -s 315 -O landscape -j 4 -r ./photos/

Portrait is the default. Use -O landscape for a horizontally mounted frame.
The preview is displayed upright automatically; no rotation angle is needed.
''')
    parser.add_argument('input_paths', nargs='+', type=str, help='Input image file(s) or directory')
    parser.add_argument('-s', '--screen', choices=sorted(PANELS), default=DEFAULT_PANEL,
                        help='Target panel: 133 (13.3", 1200x1600, EL133UF1) or 315 (31.5", 1440x2560, EL315)')
    parser.add_argument('-O', '--orientation', type=normalize_orientation,
                        choices=['portrait', 'landscape'], default='portrait',
                        help='Frame orientation: portrait/vertical (default), or '
                             'landscape/horizontal; independent of source image shape')
    parser.add_argument('-P', '--profile', choices=list(PROFILES), default=DEFAULT_PROFILE,
                        help='Colour look: soft (default), natural (no enhancement), vivid, original (legacy treatment)')
    parser.add_argument('-d', '--dither', choices=list(DITHERS), default=DEFAULT_DITHER,
                        help='Dithering: fs (default, fast), fs-serpentine, stucki, sierra, atkinson (classic), epd (optional external engine)')
    parser.add_argument('-f', '--fit', choices=['crop', 'letterbox'], default='crop',
                        help='crop (default): fill the frame and trim edges; letterbox: keep the whole image with bars')
    parser.add_argument('-l', '--letterbox', choices=sorted(LETTERBOX_COLORS), default=None,
                        help='Legacy solid background colour shortcut; --background-color takes precedence')
    parser.add_argument('-o', '--output-dir', type=str, default=None,
                        help='Directory to write .bin files into (default: next to each input image)')
    parser.add_argument('-n', '--no-transpose', action='store_true', default=False, help='Disable EXIF rotation')
    parser.add_argument('-j', '--jobs', type=int, default=1,
                        help='Number of worker processes, one image per worker (default: 1)')
    parser.add_argument('-p', '--preview', action='store_true',
                        help='After conversion, open a temporary PNG in the browser in frame orientation; '
                             'requires exactly one input image')
    parser.add_argument('-r', '--recursive', action='store_true',
                        help='Search supplied directories recursively for images')
    parser.add_argument('-b', '--brightness', type=float, default=None, help='Optional brightness override (default: profile setting)')
    parser.add_argument('-c', '--contrast', type=float, default=None, help='Optional contrast override (default: profile setting)')
    parser.add_argument('-S', '--saturation', type=float, default=None, help='Optional saturation override (default: profile setting)')
    parser.add_argument('-B', '--background', choices=['solid', 'gradient'], default='solid', help='Background for transparent areas and letterbox space: solid (default) or automatic gradient')
    parser.add_argument('-C', '--background-color', type=background_color, default=None, help='Solid background as #RRGGBB (default: white)')
    parser.add_argument('-A', '--background-angle', type=float, default=90, help='Gradient direction: 0 right, 90 down, 180 left, 270 up')
    args = parser.parse_args(argv)
    if not np.isfinite(args.background_angle) or not 0 <= args.background_angle <= 360:
        parser.error('--background-angle must be between 0 and 360')
    if args.jobs < 1:
        parser.error('--jobs must be at least 1')
    return args


def enhance_subject(image, brightness=None, contrast=None, saturation=None, profile=DEFAULT_PROFILE):
    """Apply the colour look to the subject while retaining its alpha mask."""
    alpha = image.convert('RGBA').getchannel('A')
    result = enhance_image(image, brightness, contrast, saturation, profile)
    result.putalpha(alpha)
    return result


# Collect image files from the given file/dir paths.
def collect_image_files(input_paths, recursive=False):
    all_image_files = []
    for input_path in input_paths:
        if not os.path.exists(input_path):
            print(f'Error: path {input_path} does not exist')
            continue

        if os.path.isfile(input_path):
            all_image_files.append(input_path)
        elif os.path.isdir(input_path):
            found_any = False
            directories = os.walk(input_path) if recursive else [(input_path, [], os.listdir(input_path))]
            for directory, _, files in directories:
                for file in files:
                    file_path = os.path.join(directory, file)
                    if (os.path.isfile(file_path) and
                            any(file.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)):
                        all_image_files.append(file_path)
                        found_any = True
            if not found_any:
                print(f'Warning: no image files found in directory {input_path}')
        else:
            print(f'Error: {input_path} is not a valid file or directory')
    return all_image_files


def main():
    args = parse_args()

    panel = PANELS[args.screen]

    print(f'Target panel: {panel.label} ({panel.width}x{panel.height}, {panel.bin_size:,} bytes per image)')
    print(f'Colour profile: {PROFILES[args.profile]["label"]}')
    print(f'Frame orientation: {args.orientation}; fit: {args.fit}')
    print(f'Worker processes: {args.jobs}')
    if not HEIC_SUPPORTED:
        print("Note: pillow-heif not installed; .heic input is disabled (install it to enable).")
    print(f'Dithering: {DITHERS[args.dither]["label"]}')

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)

    all_image_files = collect_image_files(args.input_paths, recursive=args.recursive)
    if not all_image_files:
        print('Error: no valid image files to process')
        sys.exit(1)
    if args.preview and len(all_image_files) != 1:
        sys.exit('Error: --preview requires exactly one input image; select one file or omit -p.')

    print(f'Found {len(all_image_files)} image files to process')
    runner = ThreadedFunctionRunner(
        process_image,
        ((image_file, args) for image_file in all_image_files),
        worker_count=args.jobs,
        backend='process',
        show_progress=True,
        progress_description="Processing images",
        progress_unit="file",
    )
    results = runner.run()
    for result in results:
        if not result.succeeded:
            print(f'Error processing {result.call.args[0]}: {result.exception}')
    failures = sum(not result.succeeded or not result.value for result in results)

    if failures:
        print(f'{failures} of {len(all_image_files)} file(s) failed to convert')
        sys.exit(1)

    if args.preview:
        # Read the actual BIN, so the preview includes quantization and packing.
        # Open the browser in the parent, after all workers have finished.
        from decode_bin import decode, show_preview
        import webbrowser
        try:
            preview, _ = decode(output_path(all_image_files[0], args))
            if args.orientation == 'landscape':
                preview = preview.transpose(Image.Transpose.ROTATE_90)
            show_preview(preview)
        except (OSError, ValueError, webbrowser.Error) as error:
            sys.exit(f'BIN saved, but preview failed: {error}')


if __name__ == '__main__':
    main()
