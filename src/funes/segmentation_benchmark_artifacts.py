"""Display-only overlays for explicit Module 7 OFAT benchmark runs."""

from __future__ import annotations

import base64
import struct
import zlib
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Mapping

import numpy as np
from numpy.typing import NDArray
from skimage.measure import find_contours

from .contracts import MetadataValue


@dataclass(frozen=True, slots=True)
class SegmentationBenchmarkOverlayResult:
    """Path and display-only scaling used for one raw-label overlay."""

    path: Path
    roi_labels: tuple[int, ...]
    display_minimum: float
    display_maximum: float


def export_segmentation_benchmark_overlay_svg(
    frame: NDArray[np.generic],
    label_image: NDArray[np.generic],
    output_path: Path | str,
    *,
    title: str,
    subtitle: str,
    context: Mapping[str, MetadataValue] | None = None,
    lower_percentile: float = 1.0,
    upper_percentile: float = 99.5,
) -> SegmentationBenchmarkOverlayResult:
    """Write a numbered raw-mask overlay without assigning review status."""

    values = np.asarray(frame, dtype=np.float64)
    labels = np.asarray(label_image)
    if values.ndim != 2 or values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("benchmark overlay requires a non-empty finite 2D frame")
    if labels.ndim != 2 or labels.shape != values.shape:
        raise ValueError("benchmark overlay frame and label image must have the same 2D shape")
    if not np.issubdtype(labels.dtype, np.integer) or np.any(labels < 0):
        raise ValueError("benchmark overlay labels must be non-negative integers")
    if not 0 <= lower_percentile < upper_percentile <= 100:
        raise ValueError("display percentiles must be ordered within 0..100")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")
    if not isinstance(subtitle, str) or not subtitle.strip():
        raise ValueError("subtitle must be a non-empty string")

    destination = Path(output_path)
    if destination.suffix.casefold() != ".svg":
        raise ValueError("benchmark overlay output path must use the .svg extension")

    normalized, display_minimum, display_maximum = _normalize(
        values,
        lower_percentile,
        upper_percentile,
    )
    roi_labels = tuple(int(value) for value in np.unique(labels) if value > 0)
    png_data = base64.b64encode(_grayscale_png_bytes(normalized)).decode("ascii")
    svg = _build_svg(
        labels=labels.astype(np.int32, copy=False),
        png_data=png_data,
        roi_labels=roi_labels,
        title=title,
        subtitle=subtitle,
        context=dict(context or {}),
        display_minimum=display_minimum,
        display_maximum=display_maximum,
        lower_percentile=lower_percentile,
        upper_percentile=upper_percentile,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(svg, encoding="utf-8", newline="\n")
    return SegmentationBenchmarkOverlayResult(
        path=destination,
        roi_labels=roi_labels,
        display_minimum=display_minimum,
        display_maximum=display_maximum,
    )


def export_segmentation_benchmark_overlay_png(
    frame: NDArray[np.generic],
    label_image: NDArray[np.generic],
    output_path: Path | str,
    *,
    lower_percentile: float = 1.0,
    upper_percentile: float = 99.5,
) -> SegmentationBenchmarkOverlayResult:
    """Write a raster preview with one unclassified color for every raw boundary."""

    values = np.asarray(frame, dtype=np.float64)
    labels = np.asarray(label_image)
    if values.ndim != 2 or values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("benchmark overlay requires a non-empty finite 2D frame")
    if labels.ndim != 2 or labels.shape != values.shape:
        raise ValueError("benchmark overlay frame and label image must have the same 2D shape")
    if not np.issubdtype(labels.dtype, np.integer) or np.any(labels < 0):
        raise ValueError("benchmark overlay labels must be non-negative integers")
    if not 0 <= lower_percentile < upper_percentile <= 100:
        raise ValueError("display percentiles must be ordered within 0..100")
    destination = Path(output_path)
    if destination.suffix.casefold() != ".png":
        raise ValueError("benchmark overlay output path must use the .png extension")

    normalized, display_minimum, display_maximum = _normalize(
        values,
        lower_percentile,
        upper_percentile,
    )
    roi_labels = tuple(int(value) for value in np.unique(labels) if value > 0)
    rgb = np.repeat(normalized[:, :, np.newaxis], 3, axis=2)
    boundary = _label_boundaries(labels.astype(np.int32, copy=False))
    thick_boundary = boundary.copy()
    thick_boundary[:-1] |= boundary[1:]
    thick_boundary[1:] |= boundary[:-1]
    thick_boundary[:, :-1] |= boundary[:, 1:]
    thick_boundary[:, 1:] |= boundary[:, :-1]
    rgb[thick_boundary] = (0, 217, 255)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_rgb_png_bytes(rgb))
    return SegmentationBenchmarkOverlayResult(
        path=destination,
        roi_labels=roi_labels,
        display_minimum=display_minimum,
        display_maximum=display_maximum,
    )


def _normalize(
    values: NDArray[np.float64],
    lower_percentile: float,
    upper_percentile: float,
) -> tuple[NDArray[np.uint8], float, float]:
    low = float(np.percentile(values, lower_percentile))
    high = float(np.percentile(values, upper_percentile))
    if high <= low:
        return np.zeros(values.shape, dtype=np.uint8), low, high
    scaled = np.clip((values - low) / (high - low), 0.0, 1.0)
    return np.rint(scaled * 255.0).astype(np.uint8), low, high


def _build_svg(
    *,
    labels: NDArray[np.int32],
    png_data: str,
    roi_labels: tuple[int, ...],
    title: str,
    subtitle: str,
    context: Mapping[str, MetadataValue],
    display_minimum: float,
    display_maximum: float,
    lower_percentile: float,
    upper_percentile: float,
) -> str:
    height, width = labels.shape
    padding = 20
    header_height = 76
    sidebar_width = 270
    image_x = padding
    image_y = header_height
    canvas_width = padding * 3 + width + sidebar_width
    canvas_height = header_height + height + padding * 2
    sidebar_x = image_x + width + padding
    context_text = " | ".join(
        f"{key}: {value}" for key, value in context.items() if value is not None
    )
    roi_groups = "\n".join(
        _roi_group(labels, label, image_x, image_y) for label in roi_labels
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_width}" height="{canvas_height}" viewBox="0 0 {canvas_width} {canvas_height}" role="img" aria-labelledby="benchmark-title benchmark-desc">
  <title id="benchmark-title">{escape(title)}</title>
  <desc id="benchmark-desc">Raw segmentation labels for descriptive OFAT visual review. No ROI status, method ranking, or profile approval is assigned.</desc>
  <rect width="100%" height="100%" fill="#111820"/>
  <text x="{padding}" y="29" fill="#F5F7FA" font-family="Arial, sans-serif" font-size="20" font-weight="600">{escape(title)}</text>
  <text x="{padding}" y="51" fill="#B8C4CE" font-family="Arial, sans-serif" font-size="13">{escape(subtitle)}</text>
  <text x="{padding}" y="68" fill="#7F92A3" font-family="Arial, sans-serif" font-size="11">{escape(context_text)}</text>
  <rect x="{image_x - 1}" y="{image_y - 1}" width="{width + 2}" height="{height + 2}" fill="#000000" stroke="#52606D"/>
  <image x="{image_x}" y="{image_y}" width="{width}" height="{height}" href="data:image/png;base64,{png_data}"/>
  {roi_groups}
  <g aria-label="Descriptive artifact notes">
    <text x="{sidebar_x}" y="{image_y + 24}" fill="#F5F7FA" font-family="Arial, sans-serif" font-size="16" font-weight="600">Raw labels: {len(roi_labels)}</text>
    <line x1="{sidebar_x}" y1="{image_y + 54}" x2="{sidebar_x + 36}" y2="{image_y + 54}" stroke="#00D9FF" stroke-width="3"/>
    <text x="{sidebar_x + 48}" y="{image_y + 59}" fill="#F5F7FA" font-family="Arial, sans-serif" font-size="13">Unclassified contour</text>
    <text x="{sidebar_x}" y="{image_y + 96}" fill="#B8C4CE" font-family="Arial, sans-serif" font-size="12">Numbers = original labels</text>
    <text x="{sidebar_x}" y="{image_y + 132}" fill="#F5F7FA" font-family="Arial, sans-serif" font-size="13" font-weight="600">Display stretch only</text>
    <text x="{sidebar_x}" y="{image_y + 153}" fill="#B8C4CE" font-family="Arial, sans-serif" font-size="12">P{lower_percentile:g}: {display_minimum:.1f}</text>
    <text x="{sidebar_x}" y="{image_y + 172}" fill="#B8C4CE" font-family="Arial, sans-serif" font-size="12">P{upper_percentile:g}: {display_maximum:.1f}</text>
    <text x="{sidebar_x}" y="{image_y + 217}" fill="#FFB86B" font-family="Arial, sans-serif" font-size="12" font-weight="600">VISUAL REVIEW ONLY</text>
    <text x="{sidebar_x}" y="{image_y + 239}" fill="#B8C4CE" font-family="Arial, sans-serif" font-size="12">No accuracy metric</text>
    <text x="{sidebar_x}" y="{image_y + 258}" fill="#B8C4CE" font-family="Arial, sans-serif" font-size="12">No ranking or approval</text>
  </g>
</svg>
'''


def _roi_group(
    labels: NDArray[np.int32],
    label: int,
    offset_x: int,
    offset_y: int,
) -> str:
    mask = labels == label
    contours = find_contours(np.pad(mask, 1), 0.5)
    paths: list[str] = []
    for contour in contours:
        points = [
            (float(col - 1 + offset_x), float(row - 1 + offset_y))
            for row, col in contour
        ]
        if not points:
            continue
        commands = [f"M{points[0][0]:.2f} {points[0][1]:.2f}"]
        commands.extend(f"L{x:.2f} {y:.2f}" for x, y in points[1:])
        commands.append("Z")
        paths.append("".join(commands))
    coordinates = np.argwhere(mask)
    center_row, center_col = np.mean(coordinates, axis=0)
    return f'''<g data-roi-label="{label}">
    <path d="{' '.join(paths)}" fill="none" stroke="#00D9FF" stroke-width="1.5" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
    <text x="{offset_x + center_col:.2f}" y="{offset_y + center_row:.2f}" fill="#00D9FF" stroke="#0A0F14" stroke-width="2.8" paint-order="stroke" text-anchor="middle" dominant-baseline="central" font-family="Arial, sans-serif" font-size="10" font-weight="600">{label}</text>
  </g>'''


def _label_boundaries(labels: NDArray[np.int32]) -> NDArray[np.bool_]:
    foreground = labels > 0
    boundary = np.zeros(labels.shape, dtype=bool)
    vertical = (labels[:-1] != labels[1:]) & (foreground[:-1] | foreground[1:])
    horizontal = (labels[:, :-1] != labels[:, 1:]) & (foreground[:, :-1] | foreground[:, 1:])
    boundary[:-1] |= vertical
    boundary[1:] |= vertical
    boundary[:, :-1] |= horizontal
    boundary[:, 1:] |= horizontal
    boundary[0] |= foreground[0]
    boundary[-1] |= foreground[-1]
    boundary[:, 0] |= foreground[:, 0]
    boundary[:, -1] |= foreground[:, -1]
    return boundary


def _grayscale_png_bytes(image: NDArray[np.uint8]) -> bytes:
    return _png_bytes(image, color_type=0)


def _rgb_png_bytes(image: NDArray[np.uint8]) -> bytes:
    return _png_bytes(image, color_type=2)


def _png_bytes(image: NDArray[np.uint8], *, color_type: int) -> bytes:
    if color_type == 2:
        height, width, channels = image.shape
        if channels != 3:
            raise ValueError("RGB PNG input must have exactly three channels")
    else:
        height, width = image.shape
    raw = b"".join(b"\x00" + image[row].tobytes() for row in range(height))
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return (
        signature
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)
