# Stillroom binary format

[← Back to the README](../README.md) · [Command-line tools](CLI.md)

## Contents

- [Palette and packing](#palette-and-packing)
- [13.3" / EL133UF1 (`--screen 133`)](#133--el133uf1---screen-133)
- [31.5" / EL315 (`--screen 315`)](#315--el315---screen-315)

## Palette and packing

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

Full specifications are included in the repository:
[EL133UF1](../EL133UF1%20Image%20Conversion%20Spec.txt) and
[EL315TWI](../EL315TWI%20Image%20Conversion%20Spec.txt).

## 13.3" / EL133UF1 (`--screen 133`)

- **1200 × 1600** pixels, portrait.
- The high nibble is the even column, the low nibble the odd column.
- Each row is split into a **left half (columns 0–599)** and a **right half (columns
  600–1199)**. All left-half bytes for the whole image come first, then all right-half bytes.
- Total size is always exactly **960,000 bytes** (1600 rows × 300 bytes × 2 halves).

## 31.5" / EL315 (`--screen 315`)

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
