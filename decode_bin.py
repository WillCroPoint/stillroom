#!/usr/bin/env python3
"""Decode either Spectra 6 panel format, detected from the BIN's byte size.

Original script contributed by corrin (https://github.com/corrin):
https://github.com/Fraimic/fraimic_bin_converter/pull/1
This version includes subsequent adaptations; those changes are not attributed
to the original contributor.

By default, write <name>_decoded.png and, with --rotate, <name>_rot<deg>.png.
Use -p/--preview to open only the requested orientation in a browser, with
its PNG stored in the system temporary directory instead of beside the BIN.
"""
import argparse
from pathlib import Path
import sys
import tempfile
import webbrowser

import numpy as np
from PIL import Image

# Both panels use these 4-bit device codes (0x4 is unused).
CODE2RGB = {
    0x0: (0, 0, 0),        # black
    0x1: (255, 255, 255),  # white
    0x2: (255, 255, 0),    # yellow
    0x3: (255, 0, 0),      # red
    0x5: (0, 0, 255),      # blue
    0x6: (0, 255, 0),      # green
}
CODE_NAMES = {0x0: "black", 0x1: "white", 0x2: "yellow", 0x3: "red", 0x5: "blue", 0x6: "green"}


def unpack(data):
    """Expand the last axis into pixels, high nibble first."""
    codes = np.empty((*data.shape[:-1], data.shape[-1] * 2), dtype=np.uint8)
    codes[..., 0::2] = data >> 4
    codes[..., 1::2] = data & 0xF
    return codes


def decode(path):
    """Return (portrait RGB image, device-code array) for either supported panel."""
    data = np.frombuffer(Path(path).read_bytes(), dtype=np.uint8)
    if data.size == 960000:
        # EL133UF1: all left-half rows, then all right-half rows.
        halves = unpack(data.reshape(2, 1600, 300))
        codes = np.concatenate(halves, axis=1)
    elif data.size == 2304000:
        # EL315: two groups of four ICs, bottom half first. Each block
        # row walks upward through a pair of image columns.
        blocks = data.reshape(2, 4, 720, 400)
        if np.any(blocks[:, 3, :, 80:] != 0x11):
            raise ValueError(f"{path}: invalid EL315 padding (IC4/IC8 must contain 0x11)")
        halves = []
        for group in blocks:
            band = np.concatenate([unpack(group[i, :, :80 if i == 3 else 400])
                                   for i in range(4)], axis=1)
            halves.append(band.reshape(720, 1280, 2).transpose(1, 0, 2)
                          .reshape(1280, 1440))
        codes = np.flipud(np.concatenate(halves, axis=0))
    else:
        raise ValueError(
            f"{path}: expected 960000 bytes (13.3-inch, 1200x1600) or "
            f"2304000 bytes (31.5-inch, 1440x2560), got {data.size}"
        )

    invalid = np.setdiff1d(np.unique(codes), list(CODE2RGB))
    if invalid.size:
        raise ValueError(f"{path}: invalid color codes: " + ", ".join(hex(int(v)) for v in invalid))
    palette = np.zeros((16, 3), dtype=np.uint8)
    for code, colour in CODE2RGB.items():
        palette[code] = colour
    return Image.fromarray(palette[codes]), codes


def show_preview(preview):
    """Open a temporary PNG; keep it available for asynchronous browser loading."""
    with tempfile.NamedTemporaryFile(prefix="fraimic-preview-", suffix=".png", delete=False) as f:
        preview.save(f, format="PNG")
        preview_path = Path(f.name).resolve()
    print("temporary preview:", preview_path)
    if not webbrowser.open(preview_path.as_uri()):
        print("Could not open a browser; open the temporary preview manually.", file=sys.stderr)
    return preview_path


def main():
    ap = argparse.ArgumentParser(
        description="Decode a Spectra 6 .bin to a PNG preview (panel auto-detected).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Orientation for images made with convert_to_bin_spectra6.py:
  Portrait frame (-O portrait): no rotation needed.
    ./decode_bin.py -p portrait.bin
  Landscape frame (-O landscape): use -r 270 (270 degrees clockwise = 90 counter-clockwise).
    ./decode_bin.py -p -r 270 landscape.bin
  For a landscape frame, the converter stores a clockwise-rotated image; -r 270 undoes it.
""")
    ap.add_argument("bin_path")
    ap.add_argument("-r", "--rotate", type=int, choices=[90, 180, 270], default=None,
                    help="rotate clockwise: omit for a portrait frame, use 270 for a landscape frame; "
                         "without --preview, also save the portrait PNG")
    ap.add_argument("-p", "--preview", action="store_true",
                    help="open the preview in a browser using a system temporary PNG; "
                         "do not write beside the BIN (temporary file retained for the browser)")
    args = ap.parse_args()

    try:
        portrait, codes = decode(args.bin_path)
        print(f"decoded {portrait.width}x{portrait.height}")
        # PIL rotates counter-clockwise, so negate for clockwise.
        preview = portrait.rotate(-args.rotate, expand=True) if args.rotate else portrait
        if args.preview:
            show_preview(preview)
        else:
            stem = Path(args.bin_path).with_suffix("")
            portrait.save(f"{stem}_decoded.png")
            print("wrote", f"{stem}_decoded.png")
            if args.rotate:
                preview.save(f"{stem}_rot{args.rotate}.png")
                print("wrote", f"{stem}_rot{args.rotate}.png")
    except (OSError, ValueError, webbrowser.Error) as exc:
        ap.exit(1, f"Error: {exc}\n")

    vals, counts = np.unique(codes, return_counts=True)
    print("colors:", {CODE_NAMES[int(v)]: int(c) for v, c in zip(vals, counts)})


if __name__ == "__main__":
    main()
