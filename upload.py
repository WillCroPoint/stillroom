#!/usr/bin/env python3
"""
Send an image to a Fraimic frame over its local REST API.

Original script contributed by corrin (https://github.com/corrin):
https://github.com/Fraimic/fraimic_bin_converter/pull/1
This version includes subsequent adaptations; those changes are not attributed
to the original contributor.

The converter in this repo produces a `.bin`; this script performs the step the
"Loading onto the display" section used to leave as a TODO -- it pushes a `.bin`
to the panel (POST /api/image), and can optionally convert an ordinary image
first so you go from JPEG/PNG to a rendered frame in one command.

Examples:
    # already have a .bin -> just upload it:
    python upload.py fraimic.local sunset_1200x1600_s6.bin

    # convert an image and upload in one shot:
    python upload.py 192.168.1.42 sunset.jpg --fit crop

    # convert for the 31.5-inch frame (choose the physical frame orientation):
    python upload.py fraimic.local sunset.jpg -s 315 -O landscape -f crop

The frame must be awake (tap it -- it deep-sleeps and is unreachable when
asleep) and on the same LAN. No authentication is required. If mDNS
(`fraimic.local`) doesn't resolve, pass the frame's IP address instead (find it
in your router's DHCP table). With more than one frame, always use IPs -- the
`fraimic.local` name only points at one of them.
"""
import sys
import os
import json
import math
import http.client
import argparse
from color_profiles import DEFAULT_PROFILE, PROFILES
from dithering import DEFAULT_DITHER, DITHERS
from contextlib import ExitStack
import subprocess
import tempfile
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
CONVERTER = os.path.join(HERE, "convert_to_bin_spectra6.py")
PANELS = {
    "133": (1200, 1600, 960000),
    "315": (1440, 2560, 2304000),
}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".gif", ".heic"}


def convert_image_to_bin(image_path, fit, dither, rotate, *, screen="133", orientation="portrait", profile=DEFAULT_PROFILE, output_dir):
    """Convert an image to a .bin using this repo's converter; return the .bin path."""
    tmpdir = output_dir
    src = image_path
    if rotate:
        from PIL import Image, ImageOps
        if os.path.splitext(image_path)[1].lower() == ".heic":
            import pillow_heif
            pillow_heif.register_heif_opener()
        with Image.open(image_path) as source:
            img = ImageOps.exif_transpose(source)
        img = img.rotate(-rotate, expand=True)  # PIL rotates CCW; negate for clockwise
        src = os.path.join(tmpdir, "rotated.png")
        img.save(src)
    subprocess.run(
        [sys.executable, CONVERTER, "--screen", screen, "--fit", fit, "--dither", dither,
         "--orientation", orientation, "--profile", profile, "--output-dir", tmpdir, src],
        check=True,
    )
    stem = os.path.splitext(os.path.basename(src))[0]
    width, height, _ = PANELS[screen]
    out = os.path.join(tmpdir, f"{stem}_{width}x{height}_s6.bin")
    if not os.path.exists(out):
        raise RuntimeError(f"conversion did not produce expected output: {out}")
    return out


def upload_bin(host, bin_path, timeout=30, screen=None):
    """POST a .bin to http://<host>/api/image. Return (http_status, body_text)."""
    with open(bin_path, "rb") as f:
        data = f.read()
    detected = next((key for key, (_, _, size) in PANELS.items() if len(data) == size), None)
    if detected is None:
        raise ValueError(
            f"{bin_path}: expected 960000 bytes (133, 1200x1600) or "
            f"2304000 bytes (315, 1440x2560), got {len(data)}"
        )
    if screen is not None and screen != detected:
        raise ValueError(f"{bin_path}: BIN is for screen {detected}, but --screen {screen} was requested")
    req = urllib.request.Request(
        f"http://{host}/api/image",
        data=data,
        method="POST",
        headers={"Content-Type": "application/octet-stream"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def read_battery(host, timeout=2):
    """One best-effort GET after upload; no retries, cache or background polling."""
    request = urllib.request.Request(f"http://{host}/api/info", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            return None
        info = json.loads(raw)
        battery = info.get('battery') if isinstance(info, dict) else None
        if not isinstance(battery, dict):
            return None
        percent = battery.get('percent')
        if type(percent) not in (int, float) or not 0 <= percent <= 100 or not math.isfinite(percent):
            return None
        charging = battery.get('charging')
        return dict(percent=percent, charging=charging if type(charging) is bool else None)
    except urllib.error.HTTPError as exc:
        exc.close()
        return None
    except (OSError, ValueError, http.client.HTTPException):
        return None


def battery_message(battery):
    if battery is None:
        return 'Battery level unavailable.'
    suffix = ' · charging' if battery['charging'] is True else ''
    return f'Battery: {battery["percent"]:g}%{suffix} (just checked).'


def main():
    ap = argparse.ArgumentParser(
        description="Upload a .bin (or convert an image and upload it) to a Fraimic frame.",
        epilog="Use -O to select the physical frame orientation, independently of the source image. "
               "No -r is normally needed; -r applies an extra clockwise rotation before conversion."
    )
    ap.add_argument("host", help="frame address, e.g. fraimic.local or 192.168.1.42")
    ap.add_argument("path", help="a .bin file, or an image to convert first")
    ap.add_argument("-s", "--screen", choices=sorted(PANELS), default=None,
                    help="panel: 133 (13.3-inch) or 315 (31.5-inch); auto-detected for BIN, "
                         "defaults to 133 for image conversion")
    ap.add_argument("-O", "--orientation", choices=["portrait", "landscape", "vertical", "horizontal"],
                    default=None, help="frame orientation for image conversion (default: portrait)")
    ap.add_argument("-f", "--fit", choices=["crop", "letterbox"], default="crop",
                    help="crop (default): fill the frame and trim edges; letterbox: keep the whole image with bars "
                         "(only used when converting an image)")
    ap.add_argument("-P", "--profile", choices=list(PROFILES), default=None,
                    help="Colour look for image conversion: soft (default), natural, vivid, original")
    ap.add_argument("-d", "--dither", choices=list(DITHERS), default=DEFAULT_DITHER,
                    help="dithering used when converting an image")
    ap.add_argument("-r", "--rotate", type=int, choices=[90, 180, 270], default=None,
                    help="extra clockwise rotation before converting an image; "
                         "normally omit for both portrait and landscape")
    args = ap.parse_args()

    try:
        with ExitStack() as stack:
            ext = os.path.splitext(args.path)[1].lower()
            if ext == ".bin":
                if args.profile is not None:
                    ap.error("--profile only applies when converting an image, not to an existing .bin")
                if args.orientation:
                    ap.error("--orientation only applies when converting an image, not to an existing .bin")
                if args.rotate:
                    ap.error("--rotate only applies when converting an image, not to an existing .bin")
                bin_path = args.path
            elif ext in IMAGE_EXTS:
                print(f"Converting {args.path} ...")
                tmpdir = stack.enter_context(tempfile.TemporaryDirectory(prefix="fraimic_upload_"))
                bin_path = convert_image_to_bin(
                    args.path, args.fit, args.dither, args.rotate,
                    screen=args.screen or "133", orientation=args.orientation or "portrait", profile=args.profile or DEFAULT_PROFILE, output_dir=tmpdir,
                )
            else:
                ap.error(f"Unrecognized input '{args.path}': expected a .bin or an image "
                         f"({', '.join(sorted(IMAGE_EXTS))}).")

            print(f"Uploading {os.path.basename(bin_path)} -> {args.host} ...")
            status, body = upload_bin(args.host, bin_path, screen=args.screen)
    except urllib.error.HTTPError as e:
        with e:
            detail = e.read().decode("utf-8", "replace")
        sys.exit(f"Upload rejected: HTTP {e.code} {e.reason}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"Upload failed -- is the frame awake and on this LAN? ({e})")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, ImportError) as e:
        sys.exit(f"Error: {e}")

    print(f"HTTP {status}: {body}")
    try:
        if json.loads(body).get("status") == "rendering":
            print("OK -- the frame accepted the image and is rendering; it appears in ~20-30s.")
    except (ValueError, AttributeError):
        pass
    if 200 <= status < 300:
        # An application-level rejection must not trigger a status read either.
        try:
            reply = json.loads(body)
        except ValueError:
            reply = {}
        rejected = isinstance(reply, dict) and (reply.get('error') or reply.get('success') is False or reply.get('status') in ('error', 'failed'))
        if not rejected:
            print(battery_message(read_battery(args.host)))


if __name__ == "__main__":
    main()
