"""Provisional, non-blocking automatic FRET route for standalone use."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Callable

from .contracts import Channel
from .file_discovery import discover_tiff_files
from .module14_exporter import Module14ExportResult, export_module14_workbooks
from .real_data_validation import (
    RealPairValidationConfig,
    RealPairValidationError,
    RealPairValidationResult,
    run_real_pair_validation,
)
from .roi_geometry import BorderTouchPolicy, RoiGeometryFilterConfig
from .segmentation_registry import create_default_segmentation_engine
from .static_roi_overlay import export_static_roi_overlay_png, export_static_roi_overlay_svg
from .tiff_reader import validate_tiff_pairs


class SimpleAnalysisError(RuntimeError):
    """Raised only when the batch has no exportable automatic result."""


@dataclass(frozen=True, slots=True)
class SimpleFretAnalysisConfig:
    """Fixed provisional settings for the non-reviewed standalone route."""

    experiment_label: str = "Experiment 1"
    min_roi_area_pixels: int = 32
    write_overlays: bool = True
    progress_callback: Callable[[str, int, int], None] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.experiment_label, str) or not self.experiment_label.strip():
            raise ValueError("experiment_label must be a non-empty string")
        if self.min_roi_area_pixels < 1:
            raise ValueError("min_roi_area_pixels must be at least 1")


@dataclass(frozen=True, slots=True)
class SimplePositionFailure:
    """A non-fatal per-position error retained in the side report and summary."""

    capture: str
    position: str
    message: str
    report_path: Path


@dataclass(frozen=True, slots=True)
class SimpleFretAnalysisResult:
    """Auditable paths and per-position automatic-analysis evidence."""

    positions: tuple[RealPairValidationResult, ...]
    failures: tuple[SimplePositionFailure, ...]
    export: Module14ExportResult
    summary_path: Path
    overlay_paths: tuple[Path, ...]
    report_paths: tuple[Path, ...]


def run_simple_fret_analysis(
    input_dir: Path | str,
    output_dir: Path | str,
    config: SimpleFretAnalysisConfig | None = None,
) -> SimpleFretAnalysisResult:
    """Process every valid C0/C1 pair in ``input_dir`` without interaction.

    Each valid pair gets the same automatic provisional profile. A failure in one
    position is written as a side report and does not stop later positions. The
    batch fails only if no pair produces a result that can be exported.
    """

    active_config = config or SimpleFretAnalysisConfig()
    input_path = Path(input_dir)
    if not input_path.is_dir():
        raise SimpleAnalysisError(f"Input directory does not exist: {input_path}")
    output_path = Path(output_dir)
    if output_path.exists() and not output_path.is_dir():
        raise SimpleAnalysisError(f"Output path is not a directory: {output_path}")

    discovery = discover_tiff_files(input_path)
    validation = validate_tiff_pairs(discovery.files)
    if not validation.pairs:
        raise SimpleAnalysisError("No valid C0/C1 TIFF pairs were found in the input directory")

    position_results: list[RealPairValidationResult] = []
    failures: list[SimplePositionFailure] = []
    overlays: list[Path] = []
    reports: list[Path] = []
    _report_progress(active_config, "Preparando análisis automático…", 0, len(validation.pairs))
    for pair in validation.pairs:
        capture = pair.position_key.capture
        position = pair.position_key.position
        _report_progress(active_config, f"Procesando {capture} / {position}", len(position_results) + len(failures), len(validation.pairs))
        try:
            result = run_real_pair_validation(
                input_path,
                output_path / "workbooks",
                RealPairValidationConfig(
                    experiment_label=active_config.experiment_label,
                    capture=capture,
                    position=position,
                    segmentation_engine=create_default_segmentation_engine(),
                    roi_geometry=RoiGeometryFilterConfig(
                        min_area_pixels=active_config.min_roi_area_pixels,
                        border_policy=BorderTouchPolicy.FLAG,
                    ),
                ),
                export_workbook=False,
            )
            position_results.append(result)
            overlay_paths = _write_overlays(result, output_path, active_config.write_overlays)
            overlays.extend(overlay_paths)
            report_path = _write_position_report(
                output_path,
                result=result,
                overlay_paths=overlay_paths,
            )
            reports.append(report_path)
        except Exception as exc:
            report_path = _write_position_report(
                output_path,
                capture=capture,
                position=position,
                error=str(exc),
            )
            failures.append(SimplePositionFailure(capture, position, str(exc), report_path))
            reports.append(report_path)
        _report_progress(active_config, f"Procesando {capture} / {position}", len(position_results) + len(failures), len(validation.pairs))

    if not position_results:
        raise SimpleAnalysisError(
            "No valid input pair completed automatic analysis; see position_reports for details"
        )
    export = export_module14_workbooks(
        tuple(result.position_export for result in position_results),
        output_path / "workbooks",
        include_simple_results=True,
    )
    summary_path = output_path / "simple_analysis_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "analysis_status": "automatic_provisional_not_scientifically_validated",
                "warning": (
                    "Automatic provisional analysis: no D090 manual review, D099 authorization, "
                    "activation plan, or user-supplied scientific configuration was required."
                ),
                "input_directory": str(input_path),
                "discovery_issue_count": len(discovery.issues),
                "pair_validation_issue_count": len(validation.issues),
                "workbooks": [str(path) for path in export.workbook_paths],
                "positions": [_summary_position(result) for result in position_results],
                "failed_positions": [
                    {
                        "capture": failure.capture,
                        "position": failure.position,
                        "message": failure.message,
                        "report": str(failure.report_path),
                    }
                    for failure in failures
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return SimpleFretAnalysisResult(
        tuple(position_results),
        tuple(failures),
        export,
        summary_path,
        tuple(overlays),
        tuple(reports),
    )


def _report_progress(
    config: SimpleFretAnalysisConfig,
    status: str,
    completed: int,
    total: int,
) -> None:
    """Send optional UI progress without affecting the automatic batch."""

    if config.progress_callback is not None:
        config.progress_callback(status, completed, total)


def _write_overlays(
    result: RealPairValidationResult,
    output_path: Path,
    write_overlays: bool,
) -> tuple[Path, ...]:
    if not write_overlays:
        return ()
    pair = result.position_export.pair
    assert pair is not None
    frame = pair.c0.frames[0] if result.selected_channel.selected_channel is Channel.C0 else pair.c1.frames[0]
    key = result.position_export.position_key
    stem = _safe_stem(key.capture, key.position)
    overlay_dir = output_path / "roi_overlays"
    subtitle = "Automatic provisional mask; fixed for both channels and all frames."
    return (
        export_static_roi_overlay_svg(
            frame,
            result.roi_filtering,
            overlay_dir / f"{stem}.svg",
            title=f"{key.experiment} / {key.capture} / {key.position}",
            subtitle=subtitle,
        ).path,
        export_static_roi_overlay_png(
            frame, result.roi_filtering, overlay_dir / f"{stem}.png"
        ).path,
    )


def _write_position_report(
    output_path: Path,
    *,
    result: RealPairValidationResult | None = None,
    overlay_paths: tuple[Path, ...] = (),
    capture: str | None = None,
    position: str | None = None,
    error: str | None = None,
) -> Path:
    if result is not None:
        key = result.position_export.position_key
        capture, position = key.capture, key.position
        body = (
            f"<p><b>Estado:</b> completado automáticamente (provisional).</p>"
            f"<p>Canal de segmentación: {escape(result.selected_channel.selected_channel.value)}<br>"
            f"ROIs detectados: {result.roi_filtering.accepted_count}<br>"
            f"ROIs rechazados: {result.roi_filtering.rejected_count}</p>"
            f"<p>La misma máscara del primer frame se usó para C0, C1 y todos los frames.</p>"
        )
        links = " ".join(
            f'<a href="../roi_overlays/{escape(path.name)}">{escape(path.name)}</a>'
            for path in overlay_paths
        ) or "Sin overlays solicitados."
        body += f"<p>Control visual: {links}</p>"
    else:
        assert capture is not None and position is not None and error is not None
        body = f"<p><b>Estado:</b> no completado; se continuó con otras posiciones.</p><pre>{escape(error)}</pre>"
    report_path = output_path / "position_reports" / f"{_safe_stem(capture, position)}.html"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "<!doctype html><meta charset=\"utf-8\"><title>FUNES Lite - informe de posición</title>"
        f"<h1>FUNES Lite — {escape(capture)} / {escape(position)}</h1>"
        "<p><i>Informe lateral automático provisional; no constituye validación científica.</i></p>"
        + body,
        encoding="utf-8",
    )
    return report_path


def _summary_position(result: RealPairValidationResult) -> dict[str, object]:
    key = result.position_export.position_key
    return {
        "experiment": key.experiment,
        "capture": key.capture,
        "position": key.position,
        "selected_segmentation_channel": result.selected_channel.selected_channel.value,
        "detected_rois": result.roi_filtering.accepted_count,
        "rejected_rois": result.roi_filtering.rejected_count,
    }


def _safe_stem(capture: str, position: str) -> str:
    return "_".join("".join(char if char.isalnum() else "_" for char in value).strip("_").lower() for value in (capture, position))
