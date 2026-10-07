# Stillroom binary format

[← Back to the README](../README.md) · [Command-line tools](CLI.md)

This reference describes the files written by Stillroom's converter and read by
its BIN preview decoder. The two panels share colour codes and byte packing,
but **their pixel storage layouts are different and not interchangeable**.

## Contents

- [Rules shared by both panels](#rules-shared-by-both-panels)
- [13.3-inch panel: EL133UF1](#133-inch-panel-el133uf1)
- [31.5-inch panel: EL315](#315-inch-panel-el315)
- [Checking a BIN file](#checking-a-bin-file)
- [Specifications and implementation](#specifications-and-implementation)

## Rules shared by both panels

### File structure and dimensions

A `.bin` is a raw frame buffer: **no header, footer, metadata or compression**.
The file itself does not declare its panel model or viewing orientation.

| Panel option | Storage dimensions (width × height) | Exact file size | Storage layout |
| --- | --- | --- | --- |
| `--screen 133` | 1200 × 1600 | 960,000 bytes | Left half, then right half |
| `--screen 315` | 1440 × 2560 | 2,304,000 bytes | Eight controller blocks, including padding |

All coordinates below refer to the **portrait storage image**, starting at
`(x=0, y=0)` in its top-left corner. `x` increases to the right and `y` downwards.
Byte offsets are zero-based; ranges in the tables are inclusive.

### Palette and byte packing

Both panels use the following six 4-bit device codes:

| Colour | Code |
| --- | --- |
| Black | `0x0` |
| White | `0x1` |
| Yellow | `0x2` |
| Red | `0x3` |
| Blue | `0x5` |
| Green | `0x6` |

Codes `0x4` and `0x7`–`0xF` are not valid. These are device codes, not consecutive
palette indices from 0 to 5; the converter maps its palette indices before packing.

Each byte stores two pixels, **first pixel in the high nibble**:

```text
byte = (first_code << 4) | second_code
Red then blue → (0x3 << 4) | 0x5 → 0x35
```

Which pair comes next in the file depends on the panel layout described below.
Sharing a palette does not make the two layouts interchangeable.

### Orientation and visible backgrounds

Both formats always use the storage dimensions above. For landscape viewing,
Stillroom composes the image at the swapped dimensions, then rotates it 90°
clockwise into portrait storage before quantization and packing. The decoder's
landscape preview reverses that rotation; there is no orientation flag in the BIN.

Cropping, colour adjustments, visible letterbox backgrounds and dithering prepare
the image before binary packing. A solid or gradient background is ordinary image
content on either panel. It is separate from the **off-panel padding** required
only by the EL315 layout.

## 13.3-inch panel: EL133UF1

Select `--screen 133`. The storage image is **1200 × 1600** pixels.

### Storage order

The image is split vertically into two 600-pixel-wide halves. Write the **entire
left half first**, followed by the **entire right half**. Within each half, read
rows from top to bottom and pixel pairs from left to right.

| Part | Image columns | File byte range | Size |
| --- | --- | --- | --- |
| Left half | 0–599 | 0–479,999 | 480,000 bytes |
| Right half | 600–1199 | 480,000–959,999 | 480,000 bytes |

Each half contains 1600 rows of 300 bytes. Within a row, the even column occupies
the high nibble and its right neighbour occupies the low nibble.

For example, byte 0 contains `(0, 0)` and `(1, 0)`; byte 299 contains `(598, 0)`
and `(599, 0)`. Byte 300 starts the next row of the **left** half. The first row
of the right half starts at byte 480,000, not byte 300.

### Padding and size

There is **no off-panel padding**. Every nibble represents an image pixel:

```text
2 halves × 1600 rows × 300 bytes = 960,000 bytes
```

## 31.5-inch panel: EL315

Select `--screen 315`. The storage image is **1440 × 2560** pixels.

### Storage order

The file contains eight controller blocks, written in order **IC1 → IC8**.
Each block contains **720 block rows × 400 bytes = 288,000 bytes**.

A *block row* is a storage unit, not a horizontal image row. Its real data follows
a vertical pair of image columns: block row `b` covers columns `2b` and `2b+1`.
Within that pair, read image rows **bottom to top**, storing the left pixel in the
high nibble and the right pixel in the low nibble.

IC1–IC4 cover the bottom half of the image; IC5–IC8 cover the top half. Each group
splits its half into bands of 400, 400, 400 and 80 image rows:

| Block | File offset (bytes) | Image rows covered | Reading direction |
| --- | --- | --- | --- |
| IC1 | 0 | 2160–2559 | 2559 → 2160 |
| IC2 | 288,000 | 1760–2159 | 2159 → 1760 |
| IC3 | 576,000 | 1360–1759 | 1759 → 1360 |
| IC4 | 864,000 | 1280–1359 | 1359 → 1280 |
| IC5 | 1,152,000 | 880–1279 | 1279 → 880 |
| IC6 | 1,440,000 | 480–879 | 879 → 480 |
| IC7 | 1,728,000 | 80–479 | 479 → 80 |
| IC8 | 2,016,000 | 0–79 | 79 → 0 |

For example, byte 0 stores `(0, 2559)` and `(1, 2559)`. Byte 1 stores `(0, 2558)`
and `(1, 2558)`. After 400 bytes, IC1's next block row begins with `(2, 2559)`
and `(3, 2559)`. This is a walk through **column pairs**, not a simple transpose.

### Padding and size

IC1, IC2, IC3, IC5, IC6 and IC7 contain only real image data. **IC4 and IC8 alone**
need off-panel padding in each of their 720 block rows:

| Byte positions within a block row | Contents |
| --- | --- |
| 0–79 | 80 image rows × 2 pixels = 160 real pixels, packed into 80 bytes |
| 80–399 | 320 bytes of `0x11` (white dummy pixels) |

The padding is always `0x11`, regardless of the visible background colour or
Letterbox setting. It does not appear on the display.

```text
Real image data: 1440 × 2560 ÷ 2           = 1,843,200 bytes
Padding:        2 blocks × 720 rows × 320 =   460,800 bytes
Total:          8 blocks × 288,000        = 2,304,000 bytes
```

## Checking a BIN file

For **either panel**, check the exact file size, allowed nibble values and pixel
layout. File size alone does not prove that the pixels are in the right order.
For **EL315 only**, also check the padding in IC4 and IC8.

Stillroom's decoder detects the panel from the file size, rejects invalid colour
codes, checks EL315 padding and reverses the corresponding storage layout. From
the repository directory:

```bash
python decode_bin.py image.bin -p          # portrait preview
python decode_bin.py image.bin -p -r 270   # landscape preview
```

Inspect an asymmetric image or test pattern to catch orientation and mapping
mistakes. A round trip through a matching encoder and decoder is useful, but does
not by itself prove compatibility with a physical display. See the
[preview guide](CLI.md#previewing-a-bin) for details.

## Specifications and implementation

- [13.3-inch specification](../EL133UF1%20Image%20Conversion%20Spec.txt)
- [31.5-inch specification](../EL315TWI%20Image%20Conversion%20Spec.txt)
- [Encoder](../convert_to_bin_spectra6.py): `pack_el133uf1`, `pack_el315` and `generate_binary_file`
- [Decoder](../decode_bin.py): `unpack` and `decode`

Colour profiles and dithering affect the image's appearance, not these storage
rules. See [colour profiles](CLI.md#colour-profiles) and
[dithering methods](CLI.md#which-dithering-should-i-use) for those choices.
