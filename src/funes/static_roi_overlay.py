"""Static numbered ROI overlays for visual quality-control review."""

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

from .contracts import MetadataValue
from .roi_geometry import RoiFilterRecord, RoiFilterStatus, RoiFilteringResult


@dataclass(frozen=True, slots=True)
class StaticRoiOverlayConfig:
    """Display-only settings that never alter segmentation or ROI decisions."""

    lower_percentile: float = 1.0
    upper_percentile: float = 99.5
    accepted_color: str = "#00D9FF"
    flagged_color: str = "#FFD166"
    rejected_color: str = "#FF6B6B"
    contour_width: float = 1.5
    label_font_size: float = 10.0
    sidebar_width: int = 260
    header_height: int = 76
    padding: int = 20

    def __post_init__(self) -> None:
        if not 0 <= self.lower_percentile < self.upper_percentile <= 100:
            raise ValueError(
                "lower_percentile must be below upper_percentile within 0..100"
            )
        if self.contour_width <= 0:
            raise ValueError("contour_width must be greater than zero")
        if self.label_font_size <= 0:
            raise ValueError("label_font_size must be greater than zero")
        if self.sidebar_width < 180:
            raise ValueError("sidebar_width must be at least 180 pixels")
        if self.header_height < 50:
            raise ValueError("header_height must be at least 50 pixels")
        if self.padding < 0:
            raise ValueError("padding must be zero or greater")
        for name, value in (
            ("accepted_color", self.accepted_color),
            ("flagged_color", self.flagged_color),
            ("rejected_color", self.rejected_color),
        ):
            if not _is_hex_color(value):
                raise ValueError(f"{name} must be a #RRGGBB color")


@dataclass(frozen=True, slots=True)
class StaticRoiOverlayResult:
    """Created SVG path and the exact ROI labels displayed by status."""

    path: Path
    accepted_labels: tuple[int, ...]
    flagged_labels: tuple[int, ...]
    rejected_labels: tuple[int, ...]
    display_minimum: float
    display_maximum: float


def export_static_roi_overlay_svg(
    frame: NDArray[np.generic],
    roi_filtering: RoiFilteringResult,
    output_path: Path | str,
    *,
    title: str,
    subtitle: str,
    context: Mapping[str, MetadataValue] | None = None,
    config: StaticRoiOverlayConfig | None = None,
) -> StaticRoiOverlayResult:
    """Overlay numbered ROI contours on one 2D frame and write a static SVG."""

    config = config or StaticRoiOverlayConfig()
    values = _validated_frame(frame)
    labels = roi_filtering.source_label_image
    if values.shape != labels.shape:
        raise ValueError(
            "static ROI overlay requires the frame and ROI labels to have the same shape"
        )
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")
    if not isinstance(subtitle, str) or not subtitle.strip():
        raise ValueError("subtitle must be a non-empty string")

    records = _validated_records(labels, roi_filtering.records)
    destination = Path(output_path)
    if destination.suffix.casefold() != ".svg":
        raise ValueError("static ROI overlay output path must use the .svg extension")

    normalized, display_minimum, display_maximum = _normalize_for_display(values, config)
    png_data = base64.b64encode(_grayscale_png_bytes(normalized)).decode("ascii")
    svg = _build_svg(
        labels=labels,
        records=records,
        png_data=png_data,
        title=title,
        subtitle=subtitle,
        context=dict(context or {}),
        config=config,
        display_minimum=display_minimum,
        display_maximum=display_maximum,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(svg, encoding="utf-8", newline="\n")

    return StaticRoiOverlayResult(
        path=destination,
        accepted_labels=_labels_for_status(records, RoiFilterStatus.ACCEPTED),
        flagged_labels=_labels_for_status(records, RoiFilterStatus.FLAGGED),
        rejected_labels=_labels_for_status(records, RoiFilterStatus.REJECTED),
        display_minimum=display_minimum,
        display_maximum=display_maximum,
    )


def export_static_roi_overlay_png(
    frame: NDArray[np.generic],
    roi_filtering: RoiFilteringResult,
    output_path: Path | str,
    *,
    config: StaticRoiOverlayConfig | None = None,
) -> StaticRoiOverlayResult:
    """Write a dependency-free raster preview with contours and numeric labels."""

    config = config or StaticRoiOverlayConfig()
    values = _validated_frame(frame)
    labels = roi_filtering.source_label_image
    if values.shape != labels.shape:
        raise ValueError(
            "static ROI overlay requires the frame and ROI labels to have the same shape"
        )
    records = _validated_records(labels, roi_filtering.records)
    destination = Path(output_path)
    if destination.suffix.casefold() != ".png":
        raise ValueError("static ROI overlay output path must use the .png extension")

    normalized, display_minimum, display_maximum = _normalize_for_display(values, config)
    raster = _raster_overlay(normalized, labels, records, config)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_rgb_png_bytes(raster))
    return StaticRoiOverlayResult(
        path=destination,
        accepted_labels=_labels_for_status(records, RoiFilterStatus.ACCEPTED),
        flagged_labels=_labels_for_status(records, RoiFilterStatus.FLAGGED),
        rejected_labels=_labels_for_status(records, RoiFilterStatus.REJECTED),
        display_minimum=display_minimum,
        display_maximum=display_maximum,
    )


def _validated_frame(frame: NDArray[np.generic]) -> NDArray[np.float64]:
    values = np.asarray(frame, dtype=np.float64)
    if values.ndim != 2 or values.size == 0:
        raise ValueError("static ROI overlay requires a non-empty 2D frame")
    if not np.all(np.isfinite(values)):
        raise ValueError("static ROI overlay requires finite pixel values")
    return values


def _validated_records(
    labels: NDArray[np.int32],
    records: tuple[RoiFilterRecord, ...],
) -> tuple[RoiFilterRecord, ...]:
    record_labels = tuple(record.geometry.label for record in records)
    if len(record_labels) != len(set(record_labels)):
        raise ValueError("static ROI overlay requires one geometry record per ROI label")
    observed_labels = tuple(sorted(int(label) for label in np.unique(labels) if label > 0))
    if tuple(sorted(record_labels)) != observed_labels:
        raise ValueError(
            "static ROI overlay geometry records must match the source label image"
        )
    return tuple(sorted(records, key=lambda record: record.geometry.label))


def _normalize_for_display(
    values: NDArray[np.float64],
    config: StaticRoiOverlayConfig,
) -> tuple[NDArray[np.uint8], float, float]:
    low = float(np.percentile(values, config.lower_percentile))
    high = float(np.percentile(values, config.upper_percentile))
    if high <= low:
        return np.zeros(values.shape, dtype=np.uint8), low, high
    scaled = np.clip((values - low) / (high - low), 0.0, 1.0)
    return np.rint(scaled * 255.0).astype(np.uint8), low, high


def _build_svg(
    *,
    labels: NDArray[np.int32],
    records: tuple[RoiFilterRecord, ...],
    png_data: str,
    title: str,
    subtitle: str,
    context: Mapping[str, MetadataValue],
    config: StaticRoiOverlayConfig,
    display_minimum: float,
    display_maximum: float,
) -> str:
    height, width = labels.shape
    canvas_width = config.padding * 3 + width + config.sidebar_width
    canvas_height = config.header_height + height + config.padding * 2
    image_x = config.padding
    image_y = config.header_height
    sidebar_x = image_x + width + config.padding
    counts = {
        status: sum(record.status is status for record in records)
        for status in RoiFilterStatus
    }
    context_text = " • ".join(
        f"{key}: {value}" for key, value in context.items() if value is not None
    )

    roi_groups = "\n".join(
        _roi_group(labels, record, image_x, image_y, config)
        for record in records
    )
    status_rows = (
        _legend_row(sidebar_x, image_y + 58, "Accepted", counts[RoiFilterStatus.ACCEPTED], config.accepted_color, "solid")
        + _legend_row(sidebar_x, image_y + 88, "Flagged", counts[RoiFilterStatus.FLAGGED], config.flagged_color, "dotted")
        + _legend_row(sidebar_x, image_y + 118, "Rejected", counts[RoiFilterStatus.REJECTED], config.rejected_color, "dashed")
    )
    desc = (
        "First-frame segmentation geometry overlay. Solid cyan contours are accepted, "
        "dotted yellow contours are flagged, and dashed coral contours are rejected. "
        "Numbers are original segmentation labels."
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_width}" height="{canvas_height}" viewBox="0 0 {canvas_width} {canvas_height}" role="img" aria-labelledby="overlay-title overlay-desc">
  <title id="overlay-title">{escape(title)}</title>
  <desc id="overlay-desc">{escape(desc)}</desc>
  <rect width="100%" height="100%" fill="#111820"/>
  <text x="{config.padding}" y="29" fill="#F5F7FA" font-family="Arial, sans-serif" font-size="20" font-weight="600">{escape(title)}</text>
  <text x="{config.padding}" y="51" fill="#B8C4CE" font-family="Arial, sans-serif" font-size="13">{escape(subtitle)}</text>
  <text x="{config.padding}" y="68" fill="#7F92A3" font-family="Arial, sans-serif" font-size="11">{escape(context_text)}</text>
  <rect x="{image_x - 1}" y="{image_y - 1}" width="{width + 2}" height="{height + 2}" fill="#000000" stroke="#52606D"/>
  <image x="{image_x}" y="{image_y}" width="{width}" height="{height}" href="data:image/png;base64,{png_data}"/>
  {roi_groups}
  <g aria-label="Legend">
    <text x="{sidebar_x}" y="{image_y + 24}" fill="#F5F7FA" font-family="Arial, sans-serif" font-size="16" font-weight="600">ROI geometry</text>
    {status_rows}
    <text x="{sidebar_x}" y="{image_y + 164}" fill="#B8C4CE" font-family="Arial, sans-serif" font-size="12">Numbers = original labels</text>
    <text x="{sidebar_x}" y="{image_y + 188}" fill="#F5F7FA" font-family="Arial, sans-serif" font-size="13" font-weight="600">Display stretch only</text>
    <text x="{sidebar_x}" y="{image_y + 209}" fill="#B8C4CE" font-family="Arial, sans-serif" font-size="12">P{config.lower_percentile:g}: {display_minimum:.1f}</text>
    <text x="{sidebar_x}" y="{image_y + 228}" fill="#B8C4CE" font-family="Arial, sans-serif" font-size="12">P{config.upper_percentile:g}: {display_maximum:.1f}</text>
    <text x="{sidebar_x}" y="{image_y + 265}" fill="#FFB86B" font-family="Arial, sans-serif" font-size="12" font-weight="600">VALIDATION ONLY</text>
    <text x="{sidebar_x}" y="{image_y + 285}" fill="#B8C4CE" font-family="Arial, sans-serif" font-size="12">Not production thresholds</text>
  </g>
</svg>
'''


def _roi_group(
    labels: NDArray[np.int32],
    record: RoiFilterRecord,
    image_x: int,
    image_y: int,
    config: StaticRoiOverlayConfig,
) -> str:
    label = record.geometry.label
    path_data = _boundary_path(labels, label, image_x, image_y)
    color, dash = _status_style(record.status, config)
    center_x = image_x + record.geometry.centroid_col + 0.5
    center_y = image_y + record.geometry.centroid_row + 0.5
    dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
    reasons = ",".join(record.reasons) or "none"
    return f'''<g data-roi-label="{label}" data-status="{record.status.value}" data-reasons="{escape(reasons)}">
    <path d="{path_data}" fill="none" stroke="{color}" stroke-width="{config.contour_width:g}"{dash_attribute} stroke-linecap="round" vector-effect="non-scaling-stroke"/>
    <text x="{center_x:.2f}" y="{center_y:.2f}" fill="{color}" stroke="#0A0F14" stroke-width="2.8" paint-order="stroke" text-anchor="middle" dominant-baseline="central" font-family="Arial, sans-serif" font-size="{config.label_font_size:g}" font-weight="600">{label}</text>
  </g>'''


def _boundary_path(
    labels: NDArray[np.int32],
    label: int,
    offset_x: int,
    offset_y: int,
) -> str:
    height, width = labels.shape
    segments: list[str] = []
    for row, col in np.argwhere(labels == label):
        y = int(row) + offset_y
        x = int(col) + offset_x
        if row == 0 or labels[row - 1, col] != label:
            segments.append(f"M{x} {y}H{x + 1}")
        if row == height - 1 or labels[row + 1, col] != label:
            segments.append(f"M{x} {y + 1}H{x + 1}")
        if col == 0 or labels[row, col - 1] != label:
            segments.append(f"M{x} {y}V{y + 1}")
        if col == width - 1 or labels[row, col + 1] != label:
            segments.append(f"M{x + 1} {y}V{y + 1}")
    return "".join(segments)


def _legend_row(
    x: int,
    y: int,
    label: str,
    count: int,
    color: str,
    line_style: str,
) -> str:
    dash = {
        "solid": "",
        "dotted": ' stroke-dasharray="1 3"',
        "dashed": ' stroke-dasharray="5 3"',
    }[line_style]
    return f'''<line x1="{x}" y1="{y}" x2="{x + 34}" y2="{y}" stroke="{color}" stroke-width="3"{dash}/>
    <text x="{x + 46}" y="{y + 4}" fill="#F5F7FA" font-family="Arial, sans-serif" font-size="13">{label}: {count}</text>
    '''


def _status_style(
    status: RoiFilterStatus,
    config: StaticRoiOverlayConfig,
) -> tuple[str, str | None]:
    if status is RoiFilterStatus.ACCEPTED:
        return config.accepted_color, None
    if status is RoiFilterStatus.FLAGGED:
        return config.flagged_color, "1 3"
    return config.rejected_color, "5 3"


def _labels_for_status(
    records: tuple[RoiFilterRecord, ...],
    status: RoiFilterStatus,
) -> tuple[int, ...]:
    return tuple(
        record.geometry.label
        for record in records
        if record.status is status
    )


_DIGITS = {
    "0": ("11111", "10001", "10011", "10101", "11001", "10001", "11111"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("11110", "00001", "00001", "01110", "10000", "10000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("10010", "10010", "10010", "11111", "00010", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01111", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "11110"),
}


def _raster_overlay(
    grayscale: NDArray[np.uint8],
    labels: NDArray[np.int32],
    records: tuple[RoiFilterRecord, ...],
    config: StaticRoiOverlayConfig,
) -> NDArray[np.uint8]:
    rgb = np.repeat(grayscale[:, :, np.newaxis], 3, axis=2)
    for record in records:
        color = _hex_rgb(_status_style(record.status, config)[0])
        boundary = _boundary_pixels(labels == record.geometry.label)
        coordinates = np.argwhere(boundary)
        for row, col in coordinates:
            if not _keep_raster_segment(record.status, int(row), int(col)):
                continue
            _paint_square(rgb, int(row), int(col), color, radius=1)

    for record in records:
        color = _hex_rgb(_status_style(record.status, config)[0])
        _draw_number(
            rgb,
            str(record.geometry.label),
            center_row=int(round(record.geometry.centroid_row)),
            center_col=int(round(record.geometry.centroid_col)),
            color=color,
        )
    return rgb


def _boundary_pixels(mask: NDArray[np.bool_]) -> NDArray[np.bool_]:
    padded = np.pad(mask, 1, mode="constant", constant_values=False)
    interior = (
        padded[1:-1, 1:-1]
        & padded[:-2, 1:-1]
        & padded[2:, 1:-1]
        & padded[1:-1, :-2]
        & padded[1:-1, 2:]
    )
    return mask & ~interior


def _keep_raster_segment(status: RoiFilterStatus, row: int, col: int) -> bool:
    if status is RoiFilterStatus.ACCEPTED:
        return True
    if status is RoiFilterStatus.FLAGGED:
        return (row + col) % 4 == 0
    return (row + col) % 7 < 4


def _paint_square(
    image: NDArray[np.uint8],
    row: int,
    col: int,
    color: tuple[int, int, int],
    *,
    radius: int,
) -> None:
    min_row = max(0, row - radius)
    max_row = min(image.shape[0], row + radius + 1)
    min_col = max(0, col - radius)
    max_col = min(image.shape[1], col + radius + 1)
    image[min_row:max_row, min_col:max_col] = color


def _draw_number(
    image: NDArray[np.uint8],
    text: str,
    *,
    center_row: int,
    center_col: int,
    color: tuple[int, int, int],
) -> None:
    glyph_width = len(text) * 5 + max(0, len(text) - 1)
    top = max(0, min(max(0, image.shape[0] - 7), center_row - 3))
    left = max(
        0,
        min(max(0, image.shape[1] - glyph_width), center_col - glyph_width // 2),
    )
    glyph_pixels: set[tuple[int, int]] = set()
    cursor = left
    for character in text:
        for row_offset, pattern_row in enumerate(_DIGITS[character]):
            for col_offset, value in enumerate(pattern_row):
                if value == "1":
                    row = top + row_offset
                    col = cursor + col_offset
                    if 0 <= row < image.shape[0] and 0 <= col < image.shape[1]:
                        glyph_pixels.add((row, col))
        cursor += 6

    outline: set[tuple[int, int]] = set()
    for row, col in glyph_pixels:
        for row_offset in (-1, 0, 1):
            for col_offset in (-1, 0, 1):
                candidate = (row + row_offset, col + col_offset)
                if candidate not in glyph_pixels:
                    outline.add(candidate)
    for row, col in outline:
        if 0 <= row < image.shape[0] and 0 <= col < image.shape[1]:
            image[row, col] = (5, 8, 12)
    for row, col in glyph_pixels:
        image[row, col] = color


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


def _is_hex_color(value: str) -> bool:
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        return False
    return all(character in "0123456789abcdefABCDEF" for character in value[1:])


def _hex_rgb(value: str) -> tuple[int, int, int]:
    return (
        int(value[1:3], 16),
        int(value[3:5], 16),
        int(value[5:7], 16),
    )
