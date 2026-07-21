"""Focused display-only artifacts for the D062 K-means causal extension."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from html import escape
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from .segmentation_benchmark_artifacts import (
    _label_boundaries,
    _normalize,
    _rgb_png_bytes,
)


@dataclass(frozen=True, slots=True)
class KMeansCausalReviewRegion:
    name: str
    x_start: int
    x_stop: int
    y_start: int
    y_stop: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("causal review region name must be non-empty")
        if not (0 <= self.x_start < self.x_stop and 0 <= self.y_start < self.y_stop):
            raise ValueError("causal review region coordinates must be ordered and non-negative")


def export_kmeans_causal_focus_svg(
    frame: NDArray[np.generic],
    reference_labels: NDArray[np.generic],
    candidate_labels: NDArray[np.generic],
    raw_added_support: NDArray[np.generic],
    region: KMeansCausalReviewRegion,
    output_path: Path | str,
    *,
    title: str,
) -> Path:
    """Write three aligned crop panels without assigning a biological class."""

    values = np.asarray(frame, dtype=np.float64)
    reference = np.asarray(reference_labels)
    candidate = np.asarray(candidate_labels)
    additions = np.asarray(raw_added_support, dtype=bool)
    if values.ndim != 2 or values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("causal focus artifact requires a non-empty finite 2D frame")
    if any(item.shape != values.shape for item in (reference, candidate, additions)):
        raise ValueError("causal focus artifact arrays must share one 2D shape")
    if region.x_stop > values.shape[1] or region.y_stop > values.shape[0]:
        raise ValueError("causal review region falls outside the prepared frame")
    destination = Path(output_path)
    if destination.suffix.casefold() != ".svg":
        raise ValueError("causal focus output path must use the .svg extension")

    crop = values[region.y_start : region.y_stop, region.x_start : region.x_stop]
    normalized, display_low, display_high = _normalize(crop, 1.0, 99.5)
    panels = (
        _panel(normalized, _label_boundaries(reference[region.y_start : region.y_stop, region.x_start : region.x_stop].astype(np.int32)), (0, 217, 255)),
        _panel(normalized, _label_boundaries(candidate[region.y_start : region.y_stop, region.x_start : region.x_stop].astype(np.int32)), (255, 193, 7)),
        _panel(normalized, additions[region.y_start : region.y_stop, region.x_start : region.x_stop], (255, 68, 204)),
    )
    encoded = tuple(base64.b64encode(_rgb_png_bytes(panel)).decode("ascii") for panel in panels)
    panel_width = crop.shape[1]
    panel_height = crop.shape[0]
    gap = 18
    margin = 20
    header = 86
    canvas_width = margin * 2 + panel_width * 3 + gap * 2
    canvas_height = header + panel_height + 54
    labels = ("Saved K area-32 reference", "Candidate final contour", "Raw selection-only additions")
    colors = ("#00D9FF", "#FFC107", "#FF44CC")
    images: list[str] = []
    for index, (png_data, label, color) in enumerate(zip(encoded, labels, colors, strict=True)):
        x = margin + index * (panel_width + gap)
        images.append(
            f'<text x="{x}" y="{header - 12}" fill="{color}" font-family="Arial, sans-serif" font-size="12" font-weight="600">{escape(label)}</text>'
            f'<image x="{x}" y="{header}" width="{panel_width}" height="{panel_height}" href="data:image/png;base64,{png_data}"/>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_width}" height="{canvas_height}" viewBox="0 0 {canvas_width} {canvas_height}">
  <rect width="100%" height="100%" fill="#111820"/>
  <text x="{margin}" y="28" fill="#F5F7FA" font-family="Arial, sans-serif" font-size="18" font-weight="600">{escape(title)}</text>
  <text x="{margin}" y="50" fill="#B8C4CE" font-family="Arial, sans-serif" font-size="12">{escape(region.name)} | x={region.x_start}:{region.x_stop}, y={region.y_start}:{region.y_stop} | display P1={display_low:.3g}, P99.5={display_high:.3g}</text>
  {''.join(images)}
  <text x="{margin}" y="{header + panel_height + 30}" fill="#FFB86B" font-family="Arial, sans-serif" font-size="12">UNCLASSIFIED CAUSAL REVIEW — no accuracy, cell identity, ranking, or approval assigned</text>
</svg>
'''
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(svg, encoding="utf-8", newline="\n")
    return destination


def _panel(
    grayscale: NDArray[np.uint8],
    overlay: NDArray[np.bool_],
    color: tuple[int, int, int],
) -> NDArray[np.uint8]:
    rgb = np.repeat(grayscale[:, :, np.newaxis], 3, axis=2)
    rgb[np.asarray(overlay, dtype=bool)] = color
    return rgb
