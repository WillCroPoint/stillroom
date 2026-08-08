# Spectra 6 `.bin` Image Converter

Convert ordinary images (JPG, PNG, HEIC, …) into the **`.bin` file format** used by
**Spectra 6** e-ink displays. Two panels are supported:

| `--screen` | Panel                | Controller | Frame              | Output size     |
| ---------- | -------------------- | ---------- | ------------------ | --------------- |
| `133`      | Spectra 6 **13.3"**  | EL133UF1   | 1200 × 1600 portrait | 960,000 bytes   |
| `315`      | Spectra 6 **31.5"**  | EL315TW1   | 1440 × 2560 portrait | 2,304,000 bytes |

The script reuses a color-quantization metric tuned for the muted, real-world colors of
Spectra 6 displays, so photos look more natural on the panel than a naive RGB conversion.

The output is a single packed binary file per image that you copy onto the display following
its loading procedure (see [Loading onto the display](#loading-onto-the-display)).

---

## What it does

For each input image, the script:

1. **Auto-orients** the image from its EXIF rotation flag (so phone photos aren't sideways).
2. **Fits** the image into the target panel's portrait frame. By default it *letterboxes* —
   scaling to fit entirely (no cropping) and padding the rest with a **black** border (see
   `--fit` for rotate/crop alternatives and `--letterbox` for white bars).
3. Applies light **brightness / contrast / saturation** enhancement plus edge-enhance,
   smoothing, and sharpening to compensate for the e-ink display's characteristics.
4. **Quantizes** the image to the 6 panel colors (black, white, yellow, red, blue, green)
   using a perceptual distance metric, with your choice of dithering.
5. **Packs** the result into the 4-bit indexed `.bin` format the panel expects and saves it
   as `<original-name>_<width>x<height>_s6.bin` (next to the input, or in `--output-dir`).

---

## Requirements

- **Python 3.8 or newer**
- **Pillow 9.1 or newer**, plus `numpy` and `tqdm`
- Optional: `pillow-heif` (only for `.heic` input)

> Pillow must be **9.1+** — the converter uses the `Image.Dither` enum introduced in that
> release. Older versions fail with `AttributeError: module 'PIL.Image' has no attribute
> 'Dither'`.
>
> `pillow-heif` is optional. Without it the script runs normally for JPG, PNG, etc. and simply
> disables `.heic` support.

## Installation

Download or clone the repository, then from the repository directory create a virtual
environment and install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

A virtual environment is recommended: recent macOS (Homebrew) and Debian/Ubuntu Python
installs block a global `pip install` with `error: externally-managed-environment`.

Run the commands in the rest of this README from the repository directory, or give the full
path to `convert_to_bin_spectra6.py`.

---

## Usage

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

| Option         | Default     | Description                                                                 |
| -------------- | ----------- | --------------------------------------------------------------------------- |
| `--screen`     | `133`       | Target panel: `133` (13.3", 1200 × 1600) or `315` (31.5", 1440 × 2560).      |
| `--dither`     | `atkinson`  | Dithering algorithm. `atkinson` = best color, slower. `fs` = Floyd–Steinberg, much faster. |
| `--fit`        | `letterbox` | How to fit the image into the panel frame. See below.                       |
| `--letterbox`  | `black`     | Letterbox bar color: `black` or `white`. Ignored by `--fit crop`.           |
| `--output-dir` | _(none)_    | Folder to write `.bin` files into. Default: next to each input image.       |
| `--brightness` | `1.1`       | Brightness multiplier (`1.0` = no change).                                  |
| `--contrast`   | `1.2`       | Contrast multiplier (`1.0` = no change).                                    |
| `--saturation` | `1.2`       | Color saturation multiplier (`1.0` = no change).                            |

Example with custom settings:

```bash
python3 convert_to_bin_spectra6.py --dither fs --contrast 1.4 --saturation 1.3 photo.jpg
```

Convert a whole album for the 31.5" panel into a separate output folder, with white bars:

```bash
python3 convert_to_bin_spectra6.py --screen 315 --letterbox white --output-dir ./bins ./album/
```

### How should I fit images? (`--fit`)

- **`letterbox`** (default) — scale to fit the whole image, padding with bars in the
  `--letterbox` color. No cropping, nothing lost.
- **`rotate`** — turn landscape images 90° upright so they fill the frame better,
  then letterbox the remainder. Best for mixed-orientation photo albums.
- **`crop`** — scale to fill the frame completely and crop the overflow. No bars, but the
  edges of the image are trimmed.

### Which letterbox color? (`--letterbox`)

- **`black`** (default) — recessive; the frame disappears and the image reads as a floating
  picture. Best for photos and dark artwork.
- **`white`** — matches the panel's unpowered white state, so bars blend into a light room or
  a white mount. Best for documents, line art, and posters on a white background.

`--letterbox` only affects the `letterbox` and `rotate` fits; with `--fit crop` there are no
bars, so the flag does nothing.

### Which dithering should I use?

- **`atkinson`** (default) uses the color-tuned matching metric and generally gives the most
  pleasing, color-accurate result. It runs a per-pixel pass in Python, so expect roughly
  **20–30 seconds per image** on the 13.3" panel — and **around twice that on the 31.5"**,
  which has 1.9× the pixels.
- **`fs`** (Floyd–Steinberg) is near-instant and suited to fast iteration or converting many
  images in one batch, with slightly less color accuracy.

### Processing notes

- **Edge-enhance, smoothing, and sharpening are always applied** (on top of the
  brightness/contrast/saturation multipliers) to suit the e-ink panel. These three filters
  have no flags. Setting `--brightness 1.0 --contrast 1.0 --saturation 1.0` neutralizes the
  multipliers only — the filters still run.
- **Inputs smaller than the panel frame are scaled up** to fill it, so low-resolution images
  will look soft or blocky — especially on the 31.5" panel, which needs 1440 × 2560.
- **Enhancement runs on the picture before the bars are added**, so `--letterbox` affects only
  the bars. The picture area is byte-identical whichever bar color you pick, the bars stay a
  pure flat color, and the contrast adjustment — which pivots on mean brightness — isn't
  skewed by them.

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

> To load a .bin file will depend on your device's access point. For Fraimic devices, you can load .bin files from either the Fraimic portal (via IP address or fraimic.local) or through the [Fraimic REST API](https://github.com/Fraimic/Fraimic_eink_canvas_home_assistant_restAPI_guide).

---

## Output format (technical details)

The `.bin` is a raw frame buffer — no header, no footer, no compression. Both panels share the
same palette, and store **6 colors as 4-bit device codes**:

| Color  | Code  |
| ------ | ----- |
| Black  | `0x0` |
| White  | `0x1` |
| Yellow | `0x2` |
| Red    | `0x3` |
| Blue   | `0x5` |
| Green  | `0x6` |

Both pack **two pixels per byte, high nibble first**.

Full specifications live alongside this readme in `EL133UF1 Image Conversion Spec.txt` and
`EL315 Image Conversion Spec.txt`.

### 13.3" / EL133UF1 (`--screen 133`)

- **1200 × 1600** pixels, portrait.
- The high nibble is the even column, the low nibble the odd column.
- Each row is split into a **left half (columns 0–599)** and a **right half (columns
  600–1199)**. All left-half bytes for the whole image come first, then all right-half bytes.
- Total size is always exactly **960,000 bytes** (1600 rows × 300 bytes × 2 halves).

### 31.5" / EL315 (`--screen 315`)

- **1440 × 2560** pixels, portrait.
- **8 IC blocks** of 288,000 bytes, written sequentially IC1 → IC8. Each block is 720 block
  rows × 400 bytes.
- The ICs come in **two groups of four, each covering half the image**: IC1–IC4 the **bottom**
  half (rows 1280–2559), IC5–IC8 the **top** half (rows 0–1279).
- Within a group, a block row is **not** an image row — it's a **2-pixel-wide vertical strip**
  of the image, 1280 rows tall, read **bottom → top**, with each image row's two pixels stored
  left then right. Block row *b* covers columns *2b* and *2b+1*, which is how 720 block rows
  span all 1440 columns.
- Each group's four ICs split its half into bands of 400 / 400 / 400 / 80 rows, counting up
  from the bottom of that half:

  | Block | Portrait rows           | Block | Portrait rows          |
  | ----- | ----------------------- | ----- | ---------------------- |
  | IC1   | 2160–2559 (bottom band) | IC5   | 880–1279               |
  | IC2   | 1760–2159               | IC6   | 480–879                |
  | IC3   | 1360–1759               | IC7   | 80–479                 |
  | IC4   | 1280–1359 (80 rows)     | IC8   | 0–79 (**top** 80 rows) |

- **IC4 and IC8 are padded**: only the first 80 bytes of each of their rows are image data
  (160 real pixels = 80 image rows × 2 columns); the remaining 320 bytes are `0x11` off-panel
  dummy pixels, always, no matter what `--letterbox` is set to.
- Total size is always exactly **2,304,000 bytes** (8 × 288,000).

---

## Troubleshooting

- **`ModuleNotFoundError: No module named 'pillow_heif'` (or `numpy`, `tqdm`, `PIL`)**
  Run `pip install -r requirements.txt`. On some systems use `pip3` instead of `pip`.
- **`error: externally-managed-environment` when running `pip install`**
  Your system Python blocks global installs (PEP 668). Create and activate a virtual
  environment first — see [Installation](#installation).
- **`AttributeError: module 'PIL.Image' has no attribute 'Dither'`**
  Your Pillow is older than 9.1. Upgrade with `pip install -U "Pillow>=9.1"`.
- **`python: command not found`**
  Use `python3` (as shown in the examples).
- **HEIC files are skipped or error out**
  Make sure `pillow-heif` installed correctly: `pip install pillow-heif`.
- **Atkinson feels stuck**
  It isn't — it's just slow (~20–30 s per image on `--screen 133`, roughly double on
  `--screen 315`). Use `--dither fs` if you need speed.
- **The image appears rotated, mirrored, or torn on the panel**
  Check the settings of `--screen`. The 13.3" and 31.5" layouts are not
  interchangeable — check the `.bin` size matches the table at the top of this readme.

---

## Credits

This converter builds on prior open-source work:

- **[PhotoPainter E-Ink Spectra 6 image converter](https://github.com/Toon-nooT/PhotoPainter-E-Ink-Spectra-6-image-converter)**
  by Toon-nooT — for their tuned RGB + luma color-distance metric and the
  Atkinson dithering that this tool reuses.

## Issues & contributing

Bug reports and pull requests are welcome at
[github.com/Fraimic/fraimic_bin_converter](https://github.com/Fraimic/fraimic_bin_converter/issues).

## License

This project is open source under the **MIT License** — see [LICENSE](LICENSE).
