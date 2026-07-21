"""Module 22 complete runner for one already reviewed acquisition.

This application boundary composes the existing durable review, loading,
analysis, workbook-export, and analysis-package APIs.  It consumes review
coverage already present in a D090 snapshot and has no operation that records
an inspection or grants scientific approval.  It may propagate one optional
finalized root Module 24 revision per position through the existing Module 20
and Module 21 boundaries without loading standalone revision artifacts.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .acquisition_analysis import (
    AcquisitionAnalysisResult,
    run_reviewed_acquisition_analysis,
)
from .acquisition_loading import AcquisitionLoadResult, load_assigned_acquisition
from .acquisition_review_setup import (
    AcquisitionReviewExperimentConfig,
    AcquisitionReviewSetupResult,
    initialize_acquisition_review,
)
from .contracts import MetadataValue, PositionKey
from .experiment_assignment import ExperimentAssignmentRule
from .experiment_roi_review import ExperimentRoiReviewOrchestrator
from .experiment_roi_review_persistence import (
    load_experiment_roi_review_snapshot,
)
from .module14_exporter import Module14ExportResult
from .position_analysis import PositionAnalysisConfig
from .roi_revision import RoiMaskRevision
from .reviewed_analysis_persistence import (
    REVIEWED_ANALYSIS_PACKAGE_SUFFIX,
    ReviewedAnalysisPackageWriteResult,
    export_reviewed_analysis_package,
)
from .reviewed_experiment_export import (
    ReviewedExperimentExportResult,
    export_reviewed_experiment_workbook,
)
from .segmentation_registry import SegmentationEngineRegistry


APPLICATION_ANALYSIS_PACKAGE_NAME = (
    "reviewed_analysis" + REVIEWED_ANALYSIS_PACKAGE_SUFFIX
)
APPLICATION_WORKBOOK_DIRECTORY = "workbooks"


class ReviewedApplicationRunError(RuntimeError):
    """Raised when a complete reviewed application run cannot finish safely."""


@dataclass(frozen=True, slots=True)
class ReviewedApplicationRunResult:
    """Complete audit trail and published artifacts for one Module 22 run."""

    output_directory: Path
    review_snapshot_path: Path
    review_snapshot_sha256: str
    acquisition: AcquisitionLoadResult
    review_setup: AcquisitionReviewSetupResult
    review_orchestrator: ExperimentRoiReviewOrchestrator
    analysis: AcquisitionAnalysisResult
    workbook_exports: tuple[ReviewedExperimentExportResult, ...]
    analysis_package: ReviewedAnalysisPackageWriteResult

    def __post_init__(self) -> None:
        output_directory = Path(self.output_directory)
        snapshot_path = Path(self.review_snapshot_path)
        if (
            len(self.review_snapshot_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.review_snapshot_sha256
            )
        ):
            raise ValueError("review_snapshot_sha256 must be lowercase SHA-256")
        if not isinstance(self.acquisition, AcquisitionLoadResult):
            raise TypeError("acquisition must be an AcquisitionLoadResult")
        if not isinstance(self.review_setup, AcquisitionReviewSetupResult):
            raise TypeError("review_setup must be an AcquisitionReviewSetupResult")
        if self.review_setup.acquisition is not self.acquisition:
            raise ValueError("review_setup must retain the exact acquisition result")
        if not isinstance(
            self.review_orchestrator, ExperimentRoiReviewOrchestrator
        ):
            raise TypeError(
                "review_orchestrator must be an ExperimentRoiReviewOrchestrator"
            )
        if not isinstance(self.analysis, AcquisitionAnalysisResult):
            raise TypeError("analysis must be an AcquisitionAnalysisResult")
        if (
            self.analysis.review_setup is not self.review_setup
            or self.analysis.review_orchestrator is not self.review_orchestrator
        ):
            raise ValueError(
                "analysis must retain the exact review setup and loaded review state"
            )

        exports = tuple(self.workbook_exports)
        if len(exports) != len(self.analysis.experiment_results):
            raise ValueError(
                "workbook_exports must match every analyzed experiment exactly"
            )
        expected_workbook_root = output_directory / APPLICATION_WORKBOOK_DIRECTORY
        for analysis_result, export_result in zip(
            self.analysis.experiment_results, exports
        ):
            if not isinstance(export_result, ReviewedExperimentExportResult):
                raise TypeError(
                    "workbook_exports must contain ReviewedExperimentExportResult values"
                )
            if export_result.analysis is not analysis_result:
                raise ValueError(
                    "workbook_exports must retain the exact Module 20 experiment order"
                )
            if export_result.workbook_path.parent != expected_workbook_root:
                raise ValueError(
                    "every workbook must be published under the application output"
                )
        if not isinstance(
            self.analysis_package, ReviewedAnalysisPackageWriteResult
        ):
            raise TypeError(
                "analysis_package must be a ReviewedAnalysisPackageWriteResult"
            )
        if self.analysis_package.path != (
            output_directory / APPLICATION_ANALYSIS_PACKAGE_NAME
        ):
            raise ValueError(
                "analysis_package must use the fixed application package path"
            )

        object.__setattr__(self, "output_directory", output_directory)
        object.__setattr__(self, "review_snapshot_path", snapshot_path)
        object.__setattr__(self, "workbook_exports", exports)

    @property
    def workbook_paths(self) -> tuple[Path, ...]:
        """Published D032 workbooks in unchanged experiment order."""

        return tuple(item.workbook_path for item in self.workbook_exports)


def run_reviewed_application(
    acquisition_root: Path | str,
    assignment_rules: tuple[ExperimentAssignmentRule, ...],
    review_snapshot_path: Path | str,
    position_configs: Mapping[PositionKey, PositionAnalysisConfig],
    output_directory: Path | str,
    *,
    segmentation_registry: SegmentationEngineRegistry | None = None,
    context: Mapping[str, MetadataValue] | None = None,
    roi_revisions: Mapping[PositionKey, RoiMaskRevision] | None = None,
) -> ReviewedApplicationRunResult:
    """Run Modules 1-14 and persist D098 evidence from existing review state.

    All scientific configuration and every review decision are caller supplied.
    The D090 snapshot must already cover every D088 position required by D097;
    this function cannot inspect a field, approve a profile, or repair review
    state.  Published artifacts appear together under a new output directory.
    Optional revisions are caller-supplied in-memory Module 24 contracts and
    are validated fail-closed by Module 20 before any experiment analysis.
    """

    destination = Path(output_directory).resolve(strict=False)
    if destination.exists():
        raise ReviewedApplicationRunError(
            f"application output directory already exists: {destination}"
        )

    try:
        acquisition = load_assigned_acquisition(acquisition_root, assignment_rules)
        # Force the fail-closed D095 readiness check at the application boundary.
        acquisition.assigned_pairs
    except Exception as exc:
        raise ReviewedApplicationRunError(
            f"application acquisition loading failed: {exc}"
        ) from exc

    snapshot_path = Path(review_snapshot_path).resolve(strict=False)
    try:
        snapshot_sha256_before = _file_sha256(snapshot_path)
        review_orchestrator = load_experiment_roi_review_snapshot(snapshot_path)
        snapshot_sha256_after = _file_sha256(snapshot_path)
        if snapshot_sha256_after != snapshot_sha256_before:
            raise ReviewedApplicationRunError(
                "review snapshot changed while the application was loading it"
            )
    except ReviewedApplicationRunError:
        raise
    except Exception as exc:
        raise ReviewedApplicationRunError(
            f"application review snapshot loading failed for {snapshot_path}: {exc}"
        ) from exc

    experiment_configs = tuple(
        AcquisitionReviewExperimentConfig(
            experiment=review.experiment,
            mode=review.mode,
            segmentation_configuration=review.review_state.configuration,
            selected_positions=review.selected_positions,
        )
        for review in review_orchestrator.experiments
    )
    try:
        review_setup = initialize_acquisition_review(
            acquisition, experiment_configs
        )
        analysis = run_reviewed_acquisition_analysis(
            review_setup,
            review_orchestrator,
            position_configs,
            segmentation_registry=segmentation_registry,
            context=context,
            roi_revisions=roi_revisions,
        )
    except Exception as exc:
        raise ReviewedApplicationRunError(
            f"reviewed application analysis preflight or execution failed: {exc}"
        ) from exc

    staging: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{destination.name}.", dir=destination.parent
            )
        )
        package_write = export_reviewed_analysis_package(
            analysis,
            position_configs,
            staging / APPLICATION_ANALYSIS_PACKAGE_NAME,
        )
        workbook_exports = tuple(
            export_reviewed_experiment_workbook(
                experiment_result,
                staging / APPLICATION_WORKBOOK_DIRECTORY,
            )
            for experiment_result in analysis.experiment_results
        )
        if destination.exists():
            raise ReviewedApplicationRunError(
                "application output directory appeared during the run; refusing "
                f"to replace it: {destination}"
            )
        os.replace(staging, destination)
        staging = None
    except ReviewedApplicationRunError:
        raise
    except Exception as exc:
        raise ReviewedApplicationRunError(
            f"application artifact publication failed for {destination}: {exc}"
        ) from exc
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)

    relocated_exports = tuple(
        _relocate_workbook_export(item, destination)
        for item in workbook_exports
    )
    relocated_package = ReviewedAnalysisPackageWriteResult(
        path=destination / APPLICATION_ANALYSIS_PACKAGE_NAME,
        sha256=package_write.sha256,
        payload_sha256=package_write.payload_sha256,
        experiment_count=package_write.experiment_count,
        position_count=package_write.position_count,
        array_count=package_write.array_count,
    )
    return ReviewedApplicationRunResult(
        output_directory=destination,
        review_snapshot_path=snapshot_path,
        review_snapshot_sha256=snapshot_sha256_before,
        acquisition=acquisition,
        review_setup=review_setup,
        review_orchestrator=review_orchestrator,
        analysis=analysis,
        workbook_exports=relocated_exports,
        analysis_package=relocated_package,
    )


def _relocate_workbook_export(
    value: ReviewedExperimentExportResult,
    output_directory: Path,
) -> ReviewedExperimentExportResult:
    relocated = Module14ExportResult(
        workbook_paths=(
            output_directory
            / APPLICATION_WORKBOOK_DIRECTORY
            / value.workbook_path.name,
        )
    )
    return ReviewedExperimentExportResult(
        analysis=value.analysis,
        position_exports=value.position_exports,
        module14_export=relocated,
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
