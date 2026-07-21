"""Reviewed analysis orchestration across every experiment in one acquisition.

This Module 20 boundary composes Module 16 only after the complete D096 scope,
the caller-supplied D089 review state, and every scientific position
configuration pass one acquisition-wide preflight.  It may propagate an
optional finalized root Module 24 revision for any subset of positions.  It
does not load files, inspect or approve fields, persist results, export
workbooks, edit ROI masks, or activate real acquisition data implicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .acquisition_review_setup import AcquisitionReviewSetupResult
from .contracts import MetadataValue, PipelineIssue, PositionKey
from .experiment_analysis import (
    ExperimentAnalysisResult,
    run_reviewed_experiment_analysis,
)
from .experiment_roi_review import (
    ExperimentPositionReview,
    ExperimentRoiReviewOrchestrator,
)
from .position_analysis import PositionAnalysisConfig
from .roi_revision import (
    RoiMaskRevision,
    RoiRevisionFinalizationState,
)
from .segmentation_registry import SegmentationEngineRegistry
from .tiff_reader import TiffPair


class AcquisitionAnalysisError(RuntimeError):
    """Raised when a complete D096 acquisition cannot enter Module 16."""


@dataclass(frozen=True, slots=True)
class AcquisitionAnalysisResult:
    """Ordered in-memory Module 16 results for one complete D096 acquisition."""

    review_setup: AcquisitionReviewSetupResult
    review_orchestrator: ExperimentRoiReviewOrchestrator
    experiment_results: tuple[ExperimentAnalysisResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.review_setup, AcquisitionReviewSetupResult):
            raise TypeError("review_setup must be an AcquisitionReviewSetupResult")
        if not isinstance(
            self.review_orchestrator, ExperimentRoiReviewOrchestrator
        ):
            raise TypeError(
                "review_orchestrator must be an ExperimentRoiReviewOrchestrator"
            )
        try:
            _validate_review_scopes(
                self.review_setup.review_orchestrator.experiments,
                self.review_orchestrator.experiments,
            )
        except AcquisitionAnalysisError as exc:
            raise ValueError(
                "review_orchestrator must retain the exact D096 scopes and "
                "D044 configuration objects"
            ) from exc
        results = tuple(self.experiment_results)
        if any(not isinstance(item, ExperimentAnalysisResult) for item in results):
            raise TypeError(
                "experiment_results must contain ExperimentAnalysisResult values"
            )

        expected_experiments = tuple(
            config.experiment for config in self.review_setup.experiment_configs
        )
        if tuple(item.experiment for item in results) != expected_experiments:
            raise ValueError(
                "experiment_results must follow the unchanged D096 experiment order"
            )
        for result in results:
            expected_pairs = self.review_setup.pairs_for_experiment(
                result.experiment
            )
            actual_pairs = tuple(
                position_result.pair for position_result in result.position_results
            )
            if len(actual_pairs) != len(expected_pairs) or any(
                actual is not expected
                for actual, expected in zip(actual_pairs, expected_pairs)
            ):
                raise ValueError(
                    "every experiment result must retain the exact ordered D096 "
                    "TiffPair objects"
                )

        object.__setattr__(self, "experiment_results", results)

    @property
    def issues(self) -> tuple[PipelineIssue, ...]:
        """All unchanged analysis issues in experiment and position order."""

        return tuple(
            issue for result in self.experiment_results for issue in result.issues
        )

    def result_for_experiment(self, experiment: str) -> ExperimentAnalysisResult:
        """Return the completed result for one registered experiment."""

        self.review_orchestrator.for_experiment(experiment)
        for result in self.experiment_results:
            if result.experiment == experiment:
                return result
        raise ValueError(f"experiment {experiment!r} has no analysis result")


def run_reviewed_acquisition_analysis(
    review_setup: AcquisitionReviewSetupResult,
    review_orchestrator: ExperimentRoiReviewOrchestrator,
    configs: Mapping[PositionKey, PositionAnalysisConfig],
    *,
    segmentation_registry: SegmentationEngineRegistry | None = None,
    context: Mapping[str, MetadataValue] | None = None,
    roi_revisions: Mapping[PositionKey, RoiMaskRevision] | None = None,
) -> AcquisitionAnalysisResult:
    """Run Module 16 once per D096 experiment after a full fail-closed audit.

    The supplied review orchestrator may contain explicit inspections or an
    explicit experiment-scoped approval recorded after D096.  It must retain
    the exact D096 scopes and D044 configuration objects.  No review decision
    is created or changed here.
    """

    if not isinstance(review_setup, AcquisitionReviewSetupResult):
        raise TypeError("review_setup must be an AcquisitionReviewSetupResult")
    if not isinstance(review_orchestrator, ExperimentRoiReviewOrchestrator):
        raise TypeError(
            "review_orchestrator must be an ExperimentRoiReviewOrchestrator"
        )
    if not isinstance(configs, Mapping):
        raise TypeError("configs must be a mapping keyed by PositionKey")

    expected_reviews = review_setup.review_orchestrator.experiments
    supplied_reviews = review_orchestrator.experiments
    _validate_review_scopes(expected_reviews, supplied_reviews)
    configs_by_key = _validate_complete_configs(
        configs,
        tuple(pair.position_key for pair in review_setup.assigned_pairs),
    )
    revisions_by_key = _validate_optional_roi_revisions(
        roi_revisions,
        tuple(pair.position_key for pair in review_setup.assigned_pairs),
    )
    shared_context = _validate_context(context)

    # Audit every experiment before the first Module 16 call.  This prevents a
    # later invalid review scope from allowing earlier analysis to begin.
    for review in supplied_reviews:
        for key in review.positions:
            decision = review.query(key)
            if key in review.manual_review_targets and not decision.manually_inspected:
                raise AcquisitionAnalysisError(
                    f"{_display_key(key)} is a required D088 manual-review target "
                    "without its own explicit D046 inspection"
                )
            if not decision.covered:
                raise AcquisitionAnalysisError(
                    f"{_display_key(key)} remains unreviewed; acquisition analysis "
                    "cannot infer scientific approval"
                )

    results: list[ExperimentAnalysisResult] = []
    for review in supplied_reviews:
        pairs = review_setup.pairs_for_experiment(review.experiment)
        experiment_configs = {
            key: configs_by_key[key] for key in review.positions
        }
        experiment_revisions = {
            key: revisions_by_key[key]
            for key in review.positions
            if key in revisions_by_key
        }
        try:
            result = run_reviewed_experiment_analysis(
                review.experiment,
                pairs,
                review_orchestrator,
                experiment_configs,
                segmentation_registry=segmentation_registry,
                context=shared_context,
                roi_revisions=experiment_revisions,
            )
        except Exception as exc:
            raise AcquisitionAnalysisError(
                f"reviewed analysis failed for experiment "
                f"{review.experiment!r}: {exc}"
            ) from exc
        results.append(result)

    return AcquisitionAnalysisResult(
        review_setup=review_setup,
        review_orchestrator=review_orchestrator,
        experiment_results=tuple(results),
    )


def _validate_review_scopes(
    expected: tuple[ExperimentPositionReview, ...],
    supplied: tuple[ExperimentPositionReview, ...],
) -> None:
    expected_names = tuple(review.experiment for review in expected)
    supplied_names = tuple(review.experiment for review in supplied)
    if supplied_names != expected_names:
        raise AcquisitionAnalysisError(
            "review_orchestrator must contain exactly the D096 experiments in "
            "unchanged order"
        )
    for original, current in zip(expected, supplied):
        if (
            current.positions != original.positions
            or current.mode is not original.mode
            or current.selected_positions != original.selected_positions
        ):
            raise AcquisitionAnalysisError(
                f"review scope for experiment {original.experiment!r} no longer "
                "matches D096"
            )
        if current.review_state.configuration is not original.review_state.configuration:
            raise AcquisitionAnalysisError(
                f"review scope for experiment {original.experiment!r} must retain "
                "the exact D044 configuration object supplied to D096"
            )


def _validate_complete_configs(
    configs: Mapping[PositionKey, PositionAnalysisConfig],
    expected_keys: tuple[PositionKey, ...],
) -> dict[PositionKey, PositionAnalysisConfig]:
    supplied = dict(configs)
    for key, config in supplied.items():
        if not isinstance(key, PositionKey):
            raise TypeError("configs keys must be PositionKey values")
        if not isinstance(config, PositionAnalysisConfig):
            raise TypeError("configs values must be PositionAnalysisConfig values")
    missing = set(expected_keys) - set(supplied)
    unexpected = set(supplied) - set(expected_keys)
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append(
                "missing "
                + ", ".join(sorted(_display_key(key) for key in missing))
            )
        if unexpected:
            details.append(
                "unexpected "
                + ", ".join(sorted(_display_key(key) for key in unexpected))
            )
        raise AcquisitionAnalysisError(
            "configs must match every D096 position exactly: " + "; ".join(details)
        )
    return supplied


def _validate_context(
    context: Mapping[str, MetadataValue] | None,
) -> dict[str, MetadataValue]:
    supplied = dict(context or {})
    forbidden = tuple(
        name for name in ("experiment", "capture", "position") if name in supplied
    )
    if forbidden:
        raise ValueError(
            "acquisition context cannot define scoped identity fields: "
            + ", ".join(forbidden)
        )
    return supplied


def _validate_optional_roi_revisions(
    roi_revisions: Mapping[PositionKey, RoiMaskRevision] | None,
    expected_keys: tuple[PositionKey, ...],
) -> dict[PositionKey, RoiMaskRevision]:
    if roi_revisions is None:
        return {}
    if not isinstance(roi_revisions, Mapping):
        raise TypeError(
            "roi_revisions must be a mapping keyed by PositionKey when present"
        )

    supplied = dict(roi_revisions)
    for key, revision in supplied.items():
        if not isinstance(key, PositionKey):
            raise TypeError("roi_revisions keys must be PositionKey values")
        if not isinstance(revision, RoiMaskRevision):
            raise TypeError("roi_revisions values must be RoiMaskRevision values")

    unexpected = set(supplied) - set(expected_keys)
    if unexpected:
        raise AcquisitionAnalysisError(
            "roi_revisions may contain only positions from the complete D096 "
            "acquisition scope; unexpected "
            + ", ".join(sorted(_display_key(key) for key in unexpected))
        )

    for key, revision in supplied.items():
        if revision.source.position_key != key:
            raise AcquisitionAnalysisError(
                f"Module 24 revision source identity does not match mapping key "
                f"{_display_key(key)}"
            )
        if (
            revision.finalization_state
            is not RoiRevisionFinalizationState.FINALIZED
        ):
            raise AcquisitionAnalysisError(
                f"Module 24 revision for {_display_key(key)} must be finalized "
                "before acquisition analysis"
            )
        if revision.parent_revision_sha256 is not None:
            raise AcquisitionAnalysisError(
                f"Module 24 revision for {_display_key(key)} must be a root "
                "revision; revision-chain propagation remains outside Module 20"
            )
    return supplied


def _display_key(key: PositionKey) -> str:
    return f"{key.experiment} / {key.capture} / {key.position}"
