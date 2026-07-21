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
from .roi_revision_persistence import load_roi_revision_artifact
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
class ResolvedRoiRevisionArtifact:
    """One explicit Module 24 artifact verified against automatic provenance."""

    position_key: PositionKey
    path: Path
    sha256: str
    revision_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        path = Path(self.path)
        for name, value in (
            ("sha256", self.sha256),
            ("revision_sha256", self.revision_sha256),
        ):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(f"{name} must be lowercase SHA-256")
        object.__setattr__(self, "path", path)


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
    resolved_roi_revision_artifacts: tuple[ResolvedRoiRevisionArtifact, ...] = ()

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

        artifacts = tuple(self.resolved_roi_revision_artifacts)
        seen_keys: set[PositionKey] = set()
        for artifact in artifacts:
            if not isinstance(artifact, ResolvedRoiRevisionArtifact):
                raise TypeError(
                    "resolved_roi_revision_artifacts must contain "
                    "ResolvedRoiRevisionArtifact values"
                )
            if artifact.position_key in seen_keys:
                raise ValueError(
                    "resolved_roi_revision_artifacts cannot duplicate positions"
                )
            seen_keys.add(artifact.position_key)
            position = _position_result_for_key(self.analysis, artifact.position_key)
            if position.revision_sha256 != artifact.revision_sha256:
                raise ValueError(
                    "resolved ROI revision artifact must match the published "
                    "position revision SHA-256"
                )

        object.__setattr__(self, "output_directory", output_directory)
        object.__setattr__(self, "review_snapshot_path", snapshot_path)
        object.__setattr__(self, "workbook_exports", exports)
        object.__setattr__(self, "resolved_roi_revision_artifacts", artifacts)

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
    roi_revision_artifact_paths: Mapping[PositionKey, Path | str] | None = None,
) -> ReviewedApplicationRunResult:
    """Run Modules 1-14 and persist D098 evidence from existing review state.

    All scientific configuration and every review decision are caller supplied.
    The D090 snapshot must already cover every D088 position required by D097;
    this function cannot inspect a field, approve a profile, or repair review
    state.  Published artifacts appear together under a new output directory.
    Optional revisions are caller-supplied in-memory Module 24 contracts and
    are validated fail-closed by Module 20 before any experiment analysis.  An
    additional explicit artifact-path mapping may resolve finalized Module 24
    artifacts without replacing the existing in-memory route.  Each path is
    verified against a deterministic automatic preflight before the published
    analysis starts; a position cannot be supplied by both routes.
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
        resolved_artifacts, artifact_revisions = _resolve_roi_revision_artifacts(
            review_setup,
            review_orchestrator,
            position_configs,
            segmentation_registry=segmentation_registry,
            context=context,
            roi_revision_artifact_paths=roi_revision_artifact_paths,
        )
        combined_revisions = _combine_roi_revision_routes(
            roi_revisions,
            artifact_revisions,
        )
        analysis = run_reviewed_acquisition_analysis(
            review_setup,
            review_orchestrator,
            position_configs,
            segmentation_registry=segmentation_registry,
            context=context,
            roi_revisions=combined_revisions,
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
        resolved_roi_revision_artifacts=resolved_artifacts,
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


def _resolve_roi_revision_artifacts(
    review_setup: AcquisitionReviewSetupResult,
    review_orchestrator: ExperimentRoiReviewOrchestrator,
    position_configs: Mapping[PositionKey, PositionAnalysisConfig],
    *,
    segmentation_registry: SegmentationEngineRegistry | None,
    context: Mapping[str, MetadataValue] | None,
    roi_revision_artifact_paths: Mapping[PositionKey, Path | str] | None,
) -> tuple[tuple[ResolvedRoiRevisionArtifact, ...], dict[PositionKey, RoiMaskRevision]]:
    """Resolve explicit root artifacts without changing the in-memory API."""

    if roi_revision_artifact_paths is None:
        return (), {}
    if not isinstance(roi_revision_artifact_paths, Mapping):
        raise TypeError(
            "roi_revision_artifact_paths must be a mapping keyed by PositionKey"
        )

    expected_keys = tuple(pair.position_key for pair in review_setup.assigned_pairs)
    supplied = dict(roi_revision_artifact_paths)
    for key, value in supplied.items():
        if not isinstance(key, PositionKey):
            raise TypeError("roi_revision_artifact_paths keys must be PositionKey values")
        if not isinstance(value, (Path, str)):
            raise TypeError(
                "roi_revision_artifact_paths values must be Path or str values"
            )
    unexpected = set(supplied) - set(expected_keys)
    if unexpected:
        raise ValueError(
            "roi_revision_artifact_paths may contain only positions from the "
            "complete acquisition scope; unexpected "
            + ", ".join(_display_key(key) for key in sorted(unexpected, key=_display_key))
        )

    # Module 24 verification needs the exact automatic Module 7/8 objects.
    # This preflight is never published and leaves the caller's in-memory route
    # untouched; the subsequent run is the sole published analysis.
    automatic = run_reviewed_acquisition_analysis(
        review_setup,
        review_orchestrator,
        position_configs,
        segmentation_registry=segmentation_registry,
        context=context,
    )
    automatic_by_key = {
        position.pair.position_key: position
        for experiment in automatic.experiment_results
        for position in experiment.position_results
    }
    resolved: list[ResolvedRoiRevisionArtifact] = []
    revisions: dict[PositionKey, RoiMaskRevision] = {}
    for key in expected_keys:
        raw_path = supplied.get(key)
        if raw_path is None:
            continue
        path = Path(raw_path).resolve(strict=False)
        before = _file_sha256(path)
        position = automatic_by_key[key]
        replayed = load_roi_revision_artifact(
            path,
            position.segmentation,
            position.roi_filtering,
            key,
        )
        after = _file_sha256(path)
        if after != before:
            raise ReviewedApplicationRunError(
                f"ROI revision artifact changed while loading it: {path}"
            )
        revision = replayed.revision
        resolved.append(
            ResolvedRoiRevisionArtifact(
                position_key=key,
                path=path,
                sha256=before,
                revision_sha256=revision.sha256,
            )
        )
        revisions[key] = revision
    return tuple(resolved), revisions


def _combine_roi_revision_routes(
    in_memory: Mapping[PositionKey, RoiMaskRevision] | None,
    artifact_revisions: Mapping[PositionKey, RoiMaskRevision],
) -> Mapping[PositionKey, RoiMaskRevision] | None:
    if in_memory is None:
        return dict(artifact_revisions) or None
    if not isinstance(in_memory, Mapping):
        # Preserve Module 20's existing public error wording and validation.
        return in_memory
    supplied = dict(in_memory)
    overlap = set(supplied) & set(artifact_revisions)
    if overlap:
        raise ReviewedApplicationRunError(
            "a position cannot use both in-memory and artifact-path ROI revision "
            "routes: "
            + ", ".join(_display_key(key) for key in sorted(overlap, key=_display_key))
        )
    return {**supplied, **artifact_revisions}


def _position_result_for_key(
    analysis: AcquisitionAnalysisResult,
    key: PositionKey,
):
    for experiment in analysis.experiment_results:
        for position in experiment.position_results:
            if position.pair.position_key == key:
                return position
    raise ValueError(f"analysis has no position {_display_key(key)}")


def _display_key(key: PositionKey) -> str:
    return f"{key.experiment} / {key.capture} / {key.position}"
