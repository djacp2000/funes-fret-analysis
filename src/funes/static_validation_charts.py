"""Dependency-free SVG charts for the static real-pair validation report."""

from __future__ import annotations

from html import escape
from typing import Iterable, Protocol

import numpy as np


class RatioPoint(Protocol):
    """Minimum record interface needed by the diagnostic charts."""

    roi_label: int
    c0_value: float | None
    c1_value: float | None
    ratio: float | None

    @property
    def frame(self):  # type: ignore[no-untyped-def]
        """Frame reference carrying ``frame_index``."""


def ratio_scatter_svg(records: Iterable[RatioPoint]) -> str:
    """Render corrected C0 versus C1 values in one panel per frame."""

    usable = tuple(
        record
        for record in records
        if record.c0_value is not None and record.c1_value is not None
    )
    frame_indices = sorted({record.frame.frame_index for record in usable})
    if not usable or not frame_indices:
        return _empty_svg("No hay valores C0/C1 disponibles")

    width = 980
    height = 410
    panel_width = (width - 80) / len(frame_indices)
    parts = [_svg_open(width, height)]
    for panel_index, frame_index in enumerate(frame_indices):
        frame_records = tuple(
            record for record in usable if record.frame.frame_index == frame_index
        )
        left = 55 + panel_index * panel_width
        top = 36
        plot_width = panel_width - 52
        plot_height = 310
        c0_values = np.asarray([record.c0_value for record in frame_records], dtype=float)
        c1_values = np.asarray([record.c1_value for record in frame_records], dtype=float)
        x_min, x_max = _padded_range(c0_values)
        y_min, y_max = _padded_range(c1_values)
        parts.extend(
            _axes(
                left,
                top,
                plot_width,
                plot_height,
                x_min,
                x_max,
                y_min,
                y_max,
                title=f"frame_index {frame_index}",
            )
        )
        for record in frame_records:
            x = left + (float(record.c0_value) - x_min) / (x_max - x_min) * plot_width
            y = top + plot_height - (float(record.c1_value) - y_min) / (y_max - y_min) * plot_height
            parts.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#00A6D6" '
                f'stroke="#072B3A"><title>ROI {record.roi_label}; ratio={record.ratio:.4f}</title></circle>'
            )
            parts.append(
                f'<text x="{x + 5:.2f}" y="{y - 4:.2f}" font-size="8" '
                f'fill="#293241">{record.roi_label}</text>'
            )
        parts.append(
            f'<text x="{left + plot_width / 2:.2f}" y="390" text-anchor="middle" '
            'font-size="12" fill="#293241">C0 corregido</text>'
        )
        if panel_index == 0:
            parts.append(
                '<text x="16" y="205" text-anchor="middle" font-size="12" '
                'fill="#293241" transform="rotate(-90 16 205)">C1 corregido</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def ratio_histogram_svg(records: Iterable[RatioPoint], *, bin_count: int = 12) -> str:
    """Render a descriptive histogram without defining an exclusion interval."""

    ratios = np.asarray(
        [record.ratio for record in records if record.ratio is not None],
        dtype=float,
    )
    if ratios.size == 0:
        return _empty_svg("No hay ratios disponibles")
    counts, edges = np.histogram(ratios, bins=min(bin_count, max(1, ratios.size)))
    width = 760
    height = 330
    left, top, plot_width, plot_height = 58, 28, 670, 240
    maximum_count = max(1, int(counts.max()))
    bar_width = plot_width / len(counts)
    parts = [_svg_open(width, height)]
    parts.append(
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" '
        f'y2="{top + plot_height}" stroke="#293241"/>'
    )
    parts.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" '
        'stroke="#293241"/>'
    )
    for index, count in enumerate(counts):
        bar_height = float(count) / maximum_count * plot_height
        x = left + index * bar_width + 1
        y = top + plot_height - bar_height
        parts.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(1.0, bar_width - 2):.2f}" '
            f'height="{bar_height:.2f}" fill="#5BC0BE"><title>{edges[index]:.3f}–{edges[index + 1]:.3f}: {int(count)}</title></rect>'
        )
    for value, anchor in ((float(edges[0]), "start"), (float(edges[-1]), "end")):
        x = left if anchor == "start" else left + plot_width
        parts.append(
            f'<text x="{x}" y="{top + plot_height + 22}" text-anchor="{anchor}" '
            f'font-size="11" fill="#293241">{value:.3f}</text>'
        )
    median = float(np.median(ratios))
    median_x = left + (median - edges[0]) / (edges[-1] - edges[0]) * plot_width
    parts.append(
        f'<line x1="{median_x:.2f}" y1="{top}" x2="{median_x:.2f}" '
        f'y2="{top + plot_height}" stroke="#E76F51" stroke-width="2" stroke-dasharray="5 4"/>'
    )
    parts.append(
        f'<text x="{median_x:.2f}" y="18" text-anchor="middle" font-size="11" '
        f'fill="#A23E2A">mediana {median:.3f}</text>'
    )
    parts.append(
        '<text x="393" y="320" text-anchor="middle" font-size="12" '
        'fill="#293241">ratio C0 / C1 de medias corregidas</text>'
    )
    parts.append(
        '<text x="16" y="150" text-anchor="middle" font-size="12" '
        'fill="#293241" transform="rotate(-90 16 150)">número de ROI-frame</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _axes(
    left: float,
    top: float,
    width: float,
    height: float,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    *,
    title: str,
) -> list[str]:
    parts = [
        f'<rect x="{left}" y="{top}" width="{width}" height="{height}" fill="#F8FAFC" stroke="#CBD5E1"/>',
        f'<text x="{left + width / 2:.2f}" y="20" text-anchor="middle" font-size="13" font-weight="bold" fill="#293241">{escape(title)}</text>',
    ]
    for step in range(5):
        fraction = step / 4
        x = left + fraction * width
        y = top + height - fraction * height
        x_value = x_min + fraction * (x_max - x_min)
        y_value = y_min + fraction * (y_max - y_min)
        parts.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + height}" stroke="#E2E8F0"/>')
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + width}" y2="{y:.2f}" stroke="#E2E8F0"/>')
        parts.append(f'<text x="{x:.2f}" y="{top + height + 15}" text-anchor="middle" font-size="9" fill="#475569">{x_value:.0f}</text>')
        parts.append(f'<text x="{left - 5}" y="{y + 3:.2f}" text-anchor="end" font-size="9" fill="#475569">{y_value:.0f}</text>')
    return parts


def _padded_range(values: np.ndarray) -> tuple[float, float]:
    minimum = float(values.min())
    maximum = float(values.max())
    if maximum == minimum:
        return minimum - 0.5, maximum + 0.5
    padding = (maximum - minimum) * 0.06
    return minimum - padding, maximum + padding


def _svg_open(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">'
    )


def _empty_svg(message: str) -> str:
    return (
        _svg_open(500, 100)
        + f'<text x="250" y="55" text-anchor="middle" fill="#475569">{escape(message)}</text></svg>'
    )
