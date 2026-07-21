"""Module 17 bridge from reviewed experiment analysis to Module 14 export.

This boundary consumes one already completed in-memory Module 16 result. It
does not discover or read TIFF files, run analysis, mutate review state, grant
approval, persist a D090 snapshot, or edit ROI masks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .experiment_analysis import ExperimentAnalysisResult
from .module14_exporter import (
    Module14ExportResult,
    Module14PositionExport,
    export_module14_workbooks,
)


class ReviewedExperimentExportError(RuntimeError):
    """Raised when a completed Module 16 result cannot be exported."""


@dataclass(frozen=True, slots=True)
class ReviewedExperimentExportResult:
    """One Module 16 result and the exact Module 14 inputs derived from it."""

    analysis: ExperimentAnalysisResult
    position_exports: tuple[Module14PositionExport, ...]
    module14_export: Module14ExportResult

    def __post_init__(self) -> None:
        if not isinstance(self.analysis, ExperimentAnalysisResult):
            raise TypeError("analysis must be an ExperimentAnalysisResult")
        exports = tuple(self.position_exports)
        if len(exports) != len(self.analysis.position_results):
            raise ValueError(
                "position_exports must match every Module 16 position exactly"
            )
        for position_result, position_export in zip(
            self.analysis.position_results, exports
        ):
            if not isinstance(position_export, Module14PositionExport):
                raise TypeError(
                    "position_exports must contain Module14PositionExport values"
                )
            if position_export.position_key != position_result.pair.position_key:
                raise ValueError(
                    "position_exports must preserve Module 16 position order"
                )
            for field_name in (
                "pair",
                "roi_filtering",
                "background",
                "intensity_qc",
                "temporal_intensity",
                "fret",
            ):
                if getattr(position_export, field_name) is not getattr(
                    position_result, field_name
                ):
                    raise ValueError(
                        "position_exports must retain the exact Module 16 "
                        f"{field_name} object"
                    )
            if position_export.mask_source != position_result.mask_source:
                raise ValueError("position_exports must preserve Module 16 mask_source")
            if position_export.revision_sha256 != position_result.revision_sha256:
                raise ValueError("position_exports must preserve Module 16 revision_sha256")
            if position_export.issues != position_result.issues:
                raise ValueError(
                    "position_exports must preserve Module 16 issues unchanged"
                )
        if not isinstance(self.module14_export, Module14ExportResult):
            raise TypeError("module14_export must be a Module14ExportResult")
        if len(self.module14_export.workbook_paths) != 1:
            raise ValueError(
                "one reviewed experiment must produce exactly one Module 14 workbook"
            )
        object.__setattr__(self, "position_exports", exports)

    @property
    def workbook_path(self) -> Path:
        """The single D032 workbook created for the reviewed experiment."""

        return self.module14_export.workbook_paths[0]


def export_reviewed_experiment_workbook(
    analysis: ExperimentAnalysisResult,
    output_dir: Path | str,
) -> ReviewedExperimentExportResult:
    """Export one completed Module 16 result through the existing Module 14.

    The adapter passes the exact already-computed Module 8/10/11/12/13 result
    objects, assigned pair, position key, and aggregated issues for each
    position. It provides no path back into analysis or review operations.
    """

    if not isinstance(analysis, ExperimentAnalysisResult):
        raise TypeError("analysis must be an ExperimentAnalysisResult")

    position_exports = tuple(
        Module14PositionExport(
            position_key=result.pair.position_key,
            roi_filtering=result.roi_filtering,
            background=result.background,
            intensity_qc=result.intensity_qc,
            temporal_intensity=result.temporal_intensity,
            fret=result.fret,
            pair=result.pair,
            issues=result.issues,
            mask_source=result.mask_source,
            revision_sha256=result.revision_sha256,
        )
        for result in analysis.position_results
    )
    try:
        module14_export = export_module14_workbooks(position_exports, output_dir)
    except Exception as exc:
        raise ReviewedExperimentExportError(
            f"Module 14 export failed for reviewed experiment "
            f"{analysis.experiment!r}: {exc}"
        ) from exc

    return ReviewedExperimentExportResult(
        analysis=analysis,
        position_exports=position_exports,
        module14_export=module14_export,
    )
