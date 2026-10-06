# Stillroom command-line tools

[← Back to the README](../README.md)

Run all commands from the repository directory with your Python environment
activated. See [installation](../README.md#installation).

## Contents

- [Conversion](#conversion)
- [Options](#options)
- [Supported input formats](#supported-input-formats)
- [Loading onto the display](#loading-onto-the-display)
- [Previewing a `.bin`](#previewing-a-bin)
- [Image backgrounds](#image-backgrounds)
- [Troubleshooting](#troubleshooting)

## Conversion

Convert ordinary images (JPG, PNG, HEIC, …) into the **`.bin` file format** used by
**Spectra 6** e-ink displays. Two panels are supported:

| `--screen` | Panel                | Controller | Frame              | Output size     |
| ---------- | -------------------- | ---------- | ------------------ | --------------- |
| `133`      | Spectra 6 **13.3"**  | EL133UF1   | 1200 × 1600 portrait | 960,000 bytes   |
| `315`      | Spectra 6 **31.5"**  | EL315TW1   | 1440 × 2560 portrait | 2,304,000 bytes |

Choose a colour profile and dithering method to balance tone, detail and grain.
Floyd–Steinberg is the fast default; the optional epd-dither engine uses its own
Spectra 6 palette. Physical colour matching still depends on the panel and lighting.

The output is a single packed binary file per image that you copy onto the display following
its loading procedure (see [Loading onto the display](#loading-onto-the-display)).

### How conversion works

For each input image, the script:

1. **Auto-orients** the image from its EXIF rotation flag (so phone photos aren't sideways).
2. **Fits** the image into the chosen physical frame orientation (`-O portrait` or
   `-O landscape`, independent of the source image's shape). By default it **crops** —
   scaling to fill the frame and trimming excess edges from the center. Use `-f letterbox`
   to keep the whole photo, with black bars (`-l white` for white bars).
3. Applies the chosen **colour look** (`-P soft` by default). Natural, vivid and the
   original converter treatment are also available.
4. **Quantizes** the image to the 6 panel colors (black, white, yellow, red, blue, green)
   with your choice of dithering.
5. **Packs** the result into the 4-bit indexed `.bin` format the panel expects and saves it
   as `<original-name>_<width>x<height>_s6.bin` (next to the input, or in `--output-dir`).

### Convert a single image

```bash
python3 convert_to_bin_spectra6.py path/to/your/image.jpg
```

This writes `path/to/your/image_1200x1600_s6.bin` for the 13.3" panel (the default).

### Convert for the 31.5" panel

```bash
python3 convert_to_bin_spectra6.py --screen 315 path/to/your/image.jpg
```

This writes `path/to/your/image_1440x2560_s6.bin`. **`--screen` is the one flag you must not
get wrong** — the two panels use completely different memory layouts, and a `.bin` built for
the wrong screen will not display correctly.

### Convert every image in a folder

```bash
python3 convert_to_bin_spectra6.py path/to/your/folder/
```

A `.bin` is created next to each source image. A progress bar shows overall status.

### Convert several files / folders at once

```bash
python3 convert_to_bin_spectra6.py photo1.jpg photo2.png ./album/
```

For the full list of options:

```bash
python3 convert_to_bin_spectra6.py --help
```

> **Existing output files are overwritten without warning.** Each `.bin` is named from the
> source image's base filename (`<name>_<width>x<height>_s6.bin`), so re-running over the same
> input replaces the previous file. The two panels write different filenames, so they don't
> collide with each other. With `--output-dir`, two source images that share a base
> filename (for example `trip1/IMG_0001.jpg` and `trip2/IMG_0001.jpg`) resolve to the same
> output name, and the second overwrites the first.

---

## Options

| Option | Default | Description |
| --- | --- | --- |
| `-s`, `--screen` | `133` | Panel: `133` (13.3″) or `315` (31.5″). |
| `-O`, `--orientation` | `portrait` | Physical frame: `portrait` / `vertical` or `landscape` / `horizontal`. |
| `-f`, `--fit` | `crop` | `letterbox`: whole image with bars; `crop`: fill the frame, trim edges. |
| `-P`, `--profile` | `soft` | Colour look: `soft`, `natural`, `vivid`, `original`. |
| `-d`, `--dither` | `fs` | `fs`, `fs-serpentine`, `stucki`, `sierra`, `atkinson`, or optional `epd`. |
| `-l`, `--letterbox` | unset | Legacy solid background shortcut; `-C` takes precedence. |
| `-o`, `--output-dir` | beside input | Folder for generated BIN files. |
| `-j`, `--jobs` | `1` | Worker processes, one image per worker. |
| `-p`, `--preview` | off | Open the generated BIN as a temporary PNG in a browser, in physical frame orientation. Exactly one input image required. |
| `-r`, `--recursive` | off | Include subdirectories. |
| `-n`, `--no-transpose` | off | Ignore EXIF orientation metadata. |
| `-b`, `--brightness` | profile | Optional brightness override after the profile tone curve. |
| `-c`, `--contrast` | profile | Optional contrast override after the profile tone curve. |
| `-S`, `--saturation` | profile | Optional saturation override after the profile tone curve. |
| `-h`, `--help` | | Show help. |

### Choose the frame orientation, then the fit

A landscape photo on a **vertical frame**, cropped to fill it, with a browser preview:

```bash
./convert_to_bin_spectra6.py -s 315 -O portrait -f crop -p landscape.jpg
```

For a **horizontal frame**, regardless of whether the source photo is portrait or landscape:

```bash
./convert_to_bin_spectra6.py -s 315 -O landscape -f crop -p photo.jpg
```

The default `crop` fills the frame. Use `-f letterbox` to keep the entire photo with bars instead of cropping.
Cropping is centered. The program handles the storage rotation automatically; no angle
is needed. Horizontal mounting follows the existing convention: the panel is turned
90° counter-clockwise from its native portrait position.

**Changed default:** the frame is now explicitly portrait by default. Previously every
landscape source was automatically turned for a horizontal frame. Add `-O landscape`
to your old landscape-frame commands. `--fit rotate` has been removed; use `-f letterbox` if
you relied on its former alias behavior. Orientation is always controlled by `-O`.
The default fit is now `crop` in both the converter and `upload.py`.

`-p` previews the actual generated BIN after a successful conversion, including dithering,
with the storage rotation undone. The BIN is saved normally, while the preview PNG goes
to the system temporary directory. Its path is printed and its cleanup follows the system's
policy. A folder containing exactly one image also works; batches with `-p` are rejected
before any conversion starts.

### Convert a batch using multiple CPU cores

```bash
./convert_to_bin_spectra6.py -s 315 -O landscape -j 4 -r -o ./bins ./photos/
```

`-j 4` uses up to four processes, each converting an independent image. This allows the
Python Atkinson loop to run on multiple cores. It speeds up batches, not a single image;
actual speed depends on the CPU and available memory. The default is one process.
The application no longer offers threads: replace old `--threads N` commands with `-j N`.

The reusable `ThreadedFunctionRunner` class still defaults to threads for existing callers.
Use `backend="process", worker_count=4` for processes, or `backend="thread"` for threads.
Process mode uses `spawn`; worker functions must be importable at module level, and
arguments and results must be picklable. Executable scripts must call the runner inside
an `if __name__ == "__main__":` guard. Results remain in input order, failures are captured
per call, and progress is updated in the parent process.

### Choose a background

Use `-B solid -C '#ffffff'` for a flat colour, or `-B gradient -A 135` for an
automatic pastel gradient. White is the default. The background fills both
transparent pixels and letterbox space. `-l black` and `-l white` remain supported
as colour shortcuts; `-C` takes precedence. An opaque image in Crop mode hides
the background completely. See [Image backgrounds](#image-backgrounds) for examples.

### Choose a colour look (`-P` / `--profile`)

The converter, `upload.py` image conversion and the web editor share the same profiles:

| Look | Effect |
| --- | --- |
| **Soft** (default) | Gentler contrast, slightly lifted shadows and a gradual highlight roll-off. No automatic sharpening. |
| **Natural** | No automatic colour, contrast or sharpness enhancement. Useful for already edited photos. |
| **Vivid** | More contrast and richer colours, with a gradual highlight roll-off and no sharpening chain. |
| **Original** | Exact former treatment: brightness 1.1, contrast 1.2, saturation 1.2, then edge enhancement, smoothing and sharpening. |

```bash
./convert_to_bin_spectra6.py -s 315 -O landscape -P soft -p photo.jpg
./convert_to_bin_spectra6.py -s 315 -O landscape -P original -p photo.jpg
./upload.py fraimic.local photo.jpg -s 315 -O landscape -P natural
```

In the web editor, select **Colour look**, then convert again. Changing the look resets
optional fine-tuning sliders to that profile's defaults and invalidates the old preview.
No slider adjustments are needed. The chosen look appears beside the converted result.

**Changed default:** `soft` replaces the previous enhancement. Use `-P original` to
reproduce the old colour processing with the same other settings. Manual `-b`, `-c`
and `-S` values override the selected profile's multipliers; for the three newer looks,
these are optional adjustments *after* its tone curve (default 1.0). Explicit strong
manual adjustments can still clip highlights. Use `natural` with factors 1.0 for no
preprocessing. Profiles do not alter the selected dithering method or six-colour palette;
they cannot recover detail already clipped in the source or guarantee the physical
panel will match an RGB monitor. Existing BINs cannot be recoloured during upload.

### Which dithering should I use?

The converter, image uploads and GUI use the same choices and default (`fs`):

| Value | Method | What to expect |
|---|---|---|
| `fs` | Floyd–Steinberg, Pillow | Fast default and a good reference for photos. |
| `fs-serpentine` | Floyd–Steinberg, alternating rows | Reduces directional patterns; Python implementation is slower. |
| `stucki` | Stucki, alternating rows | Wider diffusion, often a softer grain; slower. |
| `sierra` | Three-row Sierra, alternating rows | Another balance of grain and detail; slower. |
| `atkinson` | Classic Atkinson | Correct six-neighbour 1/8 kernel (75% error diffusion). Can still lose shadow/highlight detail. |
| `epd` | External epd-dither, blue noise | Spectra 6 colour-mixture approach; optional installation below. |

```bash
python convert_to_bin_spectra6.py -s 315 -O landscape -d stucki -p photo.jpg
python upload.py fraimic.local photo.jpg -s 315 -O landscape -d sierra
```

Built-in diffusion methods use the same six ideal RGB primaries and Euclidean RGB
matching. Pillow's implementation has its own rounding/lookup details, so the custom
Floyd–Steinberg variant will also differ slightly beyond scan direction. These are
not calibrated simulations of your physical frame. Compare with the same profile,
crop and size; judge texture at 100% zoom and at normal viewing distance on the panel.
The Python methods may take several minutes on large frames. Batch `-j` still works.

The previous Fraimic variant (5/8 diffusion and custom RGB/luma metric) is preserved
in `legacy_dithering.py`, as `quantize_fraimic_legacy_indexed`, for historical comparisons.
It is deliberately absent from CLI and GUI choices. The `original` colour profile
still reproduces the old enhancement step, but `-d atkinson` now means the corrected
algorithm and will not reproduce old BINs.

#### Optional epd-dither engine

This integration calls the real [epd-dither](https://github.com/Frans-Willem/epd-dither)
Rust executable as a separate process. No Rust installation or download happens
automatically. Without it, the GUI displays the option disabled and the CLI returns
an explicit error; there is no fallback to another algorithm.

After installing Rust/Cargo, build the revision used to define this integration:

```bash
cargo install --git https://github.com/Frans-Willem/epd-dither \
  --rev a25d70f412f4bcab775aee28de7f0767a5cb2768 \
  --root "$HOME/.local/share/fraimic-epd" --bin dither
export FRAIMIC_EPD_DITHER="$HOME/.local/share/fraimic-epd/bin/dither"
python gui.py
# Or: python convert_to_bin_spectra6.py -d epd -p photo.jpg
```

Alternatively put the executable on PATH under the name `epd-dither`. Restart the
GUI after changing the environment. The adapter uses `--noise blue`,
`--strategy octahedron-closest`, and `--dither-palette spectra6`. This palette comes
from the engine, not measurements of your Fraimic; comparisons also change the palette.
The output uses `--output-palette naive` solely to identify the six device colours:
we map them directly to BIN indices without applying a second dithering pass.
Intermediate PNGs are temporary and cleaned up even on errors. The browser preview
still shows the BIN's ideal RGB colours, not a calibrated physical-panel preview.

The external project is AGPL-3.0-only, with separate notices for its bundled noise
assets. No external source or noise asset is copied into this repository.
The adapter contract is tested with controlled subprocess responses; a real-engine
run requires the optional installation and has not been verified here.

### Battery after upload

After each successful transfer, both the web app and `upload.py` make one local
`GET /api/info` request and display `battery.percent`, plus `battery.charging`
when true. This uses the [official Fraimic REST API](https://github.com/Fraimic/Fraimic_eink_canvas_home_assistant_restAPI_guide).
The reading appears in the transfer confirmation (for example, `Battery: 73% · charging
(just checked)`). It is a snapshot, not a live monitor. There is no periodic polling,
retry or request on page load/frame selection. The network timeout is two seconds.
If the frame is sleeping, busy, unreachable or returns no valid battery reading,
the image transfer stays successful and the message says `Battery level unavailable`.

### Processing notes

- **Edge enhancement, smoothing and sharpening** are applied only by the `original`
  colour profile. The other profiles omit this filter chain.
- **Inputs smaller than the panel frame are scaled up** to fill it, so low-resolution images
  will look soft or blocky — especially on the 31.5" panel, which needs 1440 × 2560.
- **Enhancement runs on the subject before adding the background**, preserving
  its alpha mask. The background colour does not skew contrast adjustment and
  gradients stay gentle. Dithering applies to the finished composition.

---

## Supported input formats

`.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif`, `.webp`, `.gif` — plus `.heic` when `pillow-heif`
is installed.

Any aspect ratio is accepted; how it's fitted into the panel frame depends on `--fit` (see
above). Image orientation is corrected automatically from EXIF metadata.

The repository also ships `calibration_133.png` and `calibration_315.png` — full-frame
six-color bar charts at each panel's native resolution, useful for checking color rendition
and confirming an image displays correctly.

---

## Loading onto the display

Fraimic frames expose a small **local REST API**, so a generated `.bin` can be pushed
straight to the panel over your WiFi network — no cloud, no account, no cable. The
[`upload.py`](../upload.py) helper included here does this for you.

### Quick upload

```bash
# already have a .bin -> just send it:
python upload.py fraimic.local sunset_1200x1600_s6.bin
python upload.py fraimic.local sunset_1440x2560_s6.bin

# convert an ordinary image and upload in one command:
python upload.py 192.168.1.42 sunset.jpg --fit crop

# convert for the 31.5-inch panel:
python upload.py fraimic.local sunset.jpg -s 315 -O landscape -f crop
```

BIN format is detected by size: 960,000 bytes (13.3″) or 2,304,000 bytes (31.5″).
An existing BIN is sent unchanged. Optional `-s` / `--screen` checks that it matches
the requested panel; it does not convert between BIN formats or detect the remote frame.
For source images, `-s 133` is the default; use `-s 315` for the large panel.
Conversion files are temporary and removed after the upload attempt.

Short options: `-s` / `--screen`, `-f` / `--fit`, `-P` / `--profile`, `-d` / `--dither`,
`-O` / `--orientation`, `-r` / `--rotate`, `-h` / `--help`.

The frame **must be awake** — tap it first; it deep-sleeps and is completely unreachable
over the network while asleep. Both the device and the frame must be on the same LAN, and
no authentication is required.

### The endpoint

```
POST http://<frame-address>/api/image
Content-Type: application/octet-stream
(body = the raw .bin: 960,000 or 2,304,000 bytes, matching the panel)
```

A successful upload returns (13.3″ example):

```json
{"status": "rendering", "bytes_received": 960000}
```

The panel then renders automatically — no separate refresh call is needed — and the new
image appears in roughly 20–30 seconds.

The equivalent with `curl`:

```bash
curl -X POST \
  -H "Content-Type: application/octet-stream" \
  --data-binary @sunset_1200x1600_s6.bin \
  http://fraimic.local/api/image
```

### Notes

- **Finding the address.** `fraimic.local` resolves via mDNS on most home networks. If it
  doesn't resolve, use the frame's IP address (visible in your router's DHCP client table).
  **With more than one frame, always use IP addresses** — the `fraimic.local` name only
  points at whichever single frame currently owns it.
- **Orientation.** Both BIN formats store a portrait framebuffer. Use `upload.py -O portrait`
  or `-O landscape` to choose the physical frame when converting a source image (default:
  portrait). Normally omit `-r`; it is only for an extra source rotation before conversion.
  Existing BIN files are uploaded unchanged; orientation cannot be changed during upload.
  To preview a BIN made for a horizontal frame, use `decode_bin.py -p -r 270 image.bin`.
- **Upload errors.** HTTP rejections include the response from the frame. Support for
  a particular BIN format on the device still depends on its panel and firmware.

> Observed against Fraimic firmware **v0.2.21**. The endpoint currently accepts only the
> packed `.bin` format this tool produces (uploading a JPEG/PNG directly is rejected).
## Previewing a `.bin`

The converter only goes image → `.bin`. To check what a `.bin` will actually show — and to
catch orientation or packing mistakes before loading it — decode it back to a PNG:

```bash
python decode_bin.py sunset_1200x1600_s6.bin            # -> sunset_1200x1600_s6_decoded.png
python decode_bin.py sunset_1200x1600_s6.bin -r 270    # preview for a horizontal frame
python decode_bin.py -p portrait_1440x2560_s6.bin       # vertical frame: no rotation
python decode_bin.py -p -r 270 landscape_1440x2560_s6.bin # horizontal frame
```

Both panel formats are detected automatically from the file size: 960,000 bytes for
the 13.3″ (1200×1600) and 2,304,000 bytes for the 31.5″ (1440×2560). The decoder
reverses each panel's pixel layout and rejects invalid color codes or EL315 padding.

Short options: `-p` / `--preview`, `-r` / `--rotate`, `-h` / `--help`.

With `--preview`, only the requested orientation is saved, in the system temporary
directory, and opened in your default browser. No PNG is written beside the BIN.
The temporary path is printed if you want to reopen or delete it manually. The file
is retained after the script exits so the browser can load it; eventual cleanup
depends on your system's temporary-file policy, with no guaranteed deletion time.
Without this option, the original PNG export behavior is preserved.
Rotation angles are clockwise; use `--rotate 270` for a BIN converted with
`-O landscape`. For `-O portrait`, no preview rotation is needed, even if the source
photo was landscape. The converter's own `-p` option handles this automatically.

## Image backgrounds

```sh
./convert_to_bin_spectra6.py -f letterbox -B gradient -A 135 -p render.webp
./convert_to_bin_spectra6.py -f letterbox -B solid -C '#e8dfcf' -p render.png
```

`-B/--background` selects `solid` or `gradient`; `-C/--background-color` accepts
`#RRGGBB`; `-A/--background-angle` accepts 0–360 degrees (0 right, 90 down,
180 left, 270 up). The legacy `-l/--letterbox black|white` is a solid background
colour shortcut; an explicit `-C` takes precedence. Background direction follows
the displayed frame. The colour look is applied to the subject before compositing,
so it does not boost the background's contrast or saturation. Six-colour conversion
then applies to the whole composition; the final preview includes its dithering.
PNG and WebP transparency is preserved; animated files use their first frame.

## Troubleshooting

- **`ModuleNotFoundError: No module named 'pillow_heif'` (or `numpy`, `tqdm`, `PIL`)**
  Run `pip install -r requirements.txt`. On some systems use `pip3` instead of `pip`.
- **`error: externally-managed-environment` when running `pip install`**
  Your system Python blocks global installs (PEP 668). Create and activate a virtual
  environment first — see [Installation](../README.md#installation).
- **`AttributeError: module 'PIL.Image' has no attribute 'Dither'`**
  Your Pillow is older than 9.1. Upgrade with `pip install -U "Pillow>=9.1"`.
- **`python: command not found`**
  Use `python3` (as shown in the examples).
- **HEIC files are skipped or error out**
  Make sure `pillow-heif` installed correctly: `pip install pillow-heif`.
- **A Python dithering method feels slow**
  Stucki, Sierra, serpentine Floyd–Steinberg and Atkinson process pixels in Python.
  Large images can take minutes. Use `-d fs` for fast conversion.
- **The image appears rotated, mirrored, or torn on the panel**
  Check the settings of `--screen`. The 13.3" and 31.5" layouts are not
  interchangeable — check the `.bin` size matches the table at the top of this guide.

For palette codes and panel memory layouts, see the
[binary format reference](BINARY_FORMAT.md).
