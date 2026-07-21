# Module 2 Real-Data Validation

Validation date: 2026-07-13

Scope: read-only inspection of the four SlideBook TIFF files in `raw_data/`.
No segmentation or later-module processing was performed.

## Result

Module 2 accepts both C0/C1 pairs without issues:

- `Capture 1 + Position 1`
- `Capture 1 + Position 2`

All four files have the same TIFF structure:

- classic little-endian TIFF, not BigTIFF;
- one generic series with axes `IYX`;
- two IFD pages numbered `(0, 2)` and `(1, 2)`;
- normalized shape `(2, 600, 600)` as `T, Y, X`;
- one `600 x 600` grayscale sample per page;
- `uint16`, 16 bits per sample, `MINISBLACK` photometric interpretation;
- uncompressed, one strip per page;
- no OME or ImageJ metadata;
- `Software` tag is `SlideBook`.

For every file, `series.asarray()[i]` is pixel-identical to
`tif.pages[i].asarray()` for both page indices. The internal frame sequence
therefore preserves IFD order exactly. Page numbering is monotonic and agrees
between C0 and C1, so frame index 0 aligns with frame index 0 and frame index 1
aligns with frame index 1 within each pair.

## Pair Compatibility

Within each position, C0 and C1 match in:

- series axes and shape;
- page and frame count;
- width and height;
- dtype, bit depth, samples per pixel, photometric interpretation, orientation,
  compression, and strip layout;
- TIFF page numbering;
- capture date/time, document name, physical stage position, lens metadata,
  and pixel-resolution tags.

Expected channel-specific differences are the private SlideBook channel-name
tag `65004` and measured minimum/maximum sample tags. The sample extrema are
observed data values, not evidence of the camera saturation limit.

## File Inventory

| File | SHA-256 | Frames | Shape | dtype | Axes |
| --- | --- | ---: | --- | --- | --- |
| `Capture 1 - Position 1_XY1757012095_Z0_T0_C0.tif` | `62f229a459f041b3c24907d4b27d835b67919e8139854d5fba9db26d63a5eb21` | 2 | `(2, 600, 600)` | `uint16` | `IYX` |
| `Capture 1 - Position 1_XY1757012095_Z0_T0_C1.tif` | `dd35903c267fb8528136fbadc4e4662bc6527ff6051a5fa1390111fca31307d8` | 2 | `(2, 600, 600)` | `uint16` | `IYX` |
| `Capture 1 - Position 2_XY1757012096_Z0_T0_C0.tif` | `31e137998414ee5204e9e47c1c0fb351c996d227defd0ff15b84fb24eceb3a46` | 2 | `(2, 600, 600)` | `uint16` | `IYX` |
| `Capture 1 - Position 2_XY1757012096_Z0_T0_C1.tif` | `c3eedf9770166c7b73a299df5d6a5f299597f0d504289b07884a3e5b64701238` | 2 | `(2, 600, 600)` | `uint16` | `IYX` |

Each file was stat-checked immediately before and after direct inspection; size
and modification time were unchanged. The TIFFs were never opened for writing.

## Timing Limitation

The associated C0 `.log` files declare two time points but provide no usable
interval (`Average Timelapse Interval: Unknown`) and list only elapsed time
0 ms. The TIFF pages contain no per-frame elapsed-time tag or description.
Module 2 can therefore preserve frame order and zero-based `frame_index`, but
must leave `time_seconds` unknown.

## Validation Boundary

This result validates the observed 2D and three-dimensional `IYX` cases. It does
not justify guessing how a future TIFF with more than three dimensions should
be flattened. Such files remain a structured read error until inspected.
