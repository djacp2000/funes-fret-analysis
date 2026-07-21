"""Deterministic orchestration of reviewed positions for one experiment.

This boundary composes Module 15 over already assigned, in-memory TIFF pairs.
It may propagate one optional finalized root Module 24 revision per position.
It performs no discovery, TIFF reading, review mutation, approval, export,
persistence, ROI editing, or real-data activation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .contracts import MetadataValue, PipelineIssue, PositionKey
from .experiment_roi_review import ExperimentRoiReviewOrchestrator
from .position_analysis import (
    PositionAnalysisConfig,
    PositionAnalysisResult,
    run_reviewed_position_analysis,
)
from .roi_revision import (
    RoiMaskRevision,
    RoiRevisionFinalizationState,
)
from .segmentation_registry import SegmentationEngineRegistry
from .tiff_reader import TiffPair


class ExperimentAnalysisError(RuntimeError):
    """Raised when a complete reviewed experiment cannot enter Module 15."""


@dataclass(frozen=True, slots=True)
class ExperimentAnalysisResult:
    """Ordered in-memory Module 15 results for exactly one experiment."""

    experiment: str
    position_results: tuple[PositionAnalysisResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.experiment, str) or not self.experiment.strip():
            raise ValueError("experiment must be a non-empty string")
        results = tuple(self.position_results)
        if not results:
            raise ValueError("position_results must contain at least one result")
        for result in results:
            if not isinstance(result, PositionAnalysisResult):
                raise TypeError(
                    "position_results must contain PositionAnalysisResult values"
                )
            if result.pair.position_key.experiment != self.experiment:
                raise ValueError(
                    "every position result must belong to the declared experiment"
                )
        keys = tuple(result.pair.position_key for result in results)
        if len(set(keys)) != len(keys):
            raise ValueError("position_results cannot contain duplicate positions")
        object.__setattr__(self, "position_results", results)

    @property
    def issues(self) -> tuple[PipelineIssue, ...]:
        """All stage issues, preserving experiment and position order."""

        return tuple(
            issue for result in self.position_results for issue in result.issues
        )


def run_reviewed_experiment_analysis(
    experiment: str,
    pairs: tuple[TiffPair, ...],
    review_orchestrator: ExperimentRoiReviewOrchestrator,
    configs: Mapping[PositionKey, PositionAnalysisConfig],
    *,
    segmentation_registry: SegmentationEngineRegistry | None = None,
    context: Mapping[str, MetadataValue] | None = None,
    roi_revisions: Mapping[PositionKey, RoiMaskRevision] | None = None,
) -> ExperimentAnalysisResult:
    """Run every declared position in one isolated D089 experiment scope.

    Inputs must cover the scope exactly.  All identities, configurations, and
    D046 coverage are preflighted before the first Module 15 call.  Execution is
    deterministic in the position order already declared by D089.  The
    optional revision mapping may cover any subset of the experiment; absent
    positions retain the unchanged automatic-mask path.
    """

    if not isinstance(experiment, str) or not experiment.strip():
        raise ValueError("experiment must be a non-empty string")
    if not isinstance(review_orchestrator, ExperimentRoiReviewOrchestrator):
        raise TypeError(
            "review_orchestrator must be an ExperimentRoiReviewOrchestrator"
        )
    if not isinstance(configs, Mapping):
        raise TypeError("configs must be a mapping keyed by PositionKey")

    scoped_review = review_orchestrator.for_experiment(experiment)
    ordered_pairs = _validate_complete_pairs(experiment, pairs, scoped_review.positions)
    configs_by_key = _validate_complete_configs(configs, scoped_review.positions)
    revisions_by_key = _validate_optional_roi_revisions(
        roi_revisions,
        scoped_review.positions,
    )
    shared_context = _validate_context(experiment, context)

    # Fail closed for the complete batch before any segmentation or measurement.
    for key in scoped_review.positions:
        decision = scoped_review.query(key)
        if key in scoped_review.manual_review_targets and not decision.manually_inspected:
            raise ExperimentAnalysisError(
                f"{_display_key(key)} is a required D088 manual-review target "
                "without its own explicit D046 inspection"
            )
        if not decision.covered:
            raise ExperimentAnalysisError(
                f"{_display_key(key)} remains unreviewed in the isolated D089 "
                "ledger; experiment analysis cannot infer scientific approval"
            )

    results: list[PositionAnalysisResult] = []
    for pair in ordered_pairs:
        try:
            result = run_reviewed_position_analysis(
                pair,
                review_orchestrator,
                configs_by_key[pair.position_key],
                segmentation_registry=segmentation_registry,
                context=shared_context,
                roi_revision=revisions_by_key.get(pair.position_key),
            )
        except Exception as exc:
            raise ExperimentAnalysisError(
                f"reviewed analysis failed for {_display_key(pair.position_key)}: "
                f"{exc}"
            ) from exc
        results.append(result)

    return ExperimentAnalysisResult(
        experiment=experiment,
        position_results=tuple(results),
    )


def _validate_complete_pairs(
    experiment: str,
    pairs: tuple[TiffPair, ...],
    expected_keys: tuple[PositionKey, ...],
) -> tuple[TiffPair, ...]:
    supplied = tuple(pairs)
    for pair in supplied:
        if not isinstance(pair, TiffPair):
            raise TypeError("pairs must contain only TiffPair values")
        if pair.position_key.experiment != experiment:
            raise ExperimentAnalysisError(
                "every TiffPair must belong to the requested isolated experiment; "
                f"received {_display_key(pair.position_key)}"
            )
    keys = tuple(pair.position_key for pair in supplied)
    if len(set(keys)) != len(keys):
        raise ExperimentAnalysisError("pairs cannot contain duplicate positions")
    pair_by_key = {pair.position_key: pair for pair in supplied}
    _require_exact_scope("pairs", set(pair_by_key), set(expected_keys))
    return tuple(pair_by_key[key] for key in expected_keys)


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
    _require_exact_scope("configs", set(supplied), set(expected_keys))
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
        raise ExperimentAnalysisError(
            "roi_revisions may contain only positions from the complete D089 "
            "experiment scope; unexpected "
            + ", ".join(sorted(_display_key(key) for key in unexpected))
        )

    for key, revision in supplied.items():
        if revision.source.position_key != key:
            raise ExperimentAnalysisError(
                f"Module 24 revision source identity does not match mapping key "
                f"{_display_key(key)}"
            )
        if (
            revision.finalization_state
            is not RoiRevisionFinalizationState.FINALIZED
        ):
            raise ExperimentAnalysisError(
                f"Module 24 revision for {_display_key(key)} must be finalized "
                "before experiment analysis"
            )
        if revision.parent_revision_sha256 is not None:
            raise ExperimentAnalysisError(
                f"Module 24 revision for {_display_key(key)} must be a root "
                "revision; revision-chain propagation remains outside Module 16"
            )
    return supplied


def _require_exact_scope(
    name: str,
    supplied: set[PositionKey],
    expected: set[PositionKey],
) -> None:
    missing = expected - supplied
    unexpected = supplied - expected
    if not missing and not unexpected:
        return
    details: list[str] = []
    if missing:
        details.append(
            "missing " + ", ".join(sorted(_display_key(key) for key in missing))
        )
    if unexpected:
        details.append(
            "unexpected "
            + ", ".join(sorted(_display_key(key) for key in unexpected))
        )
    raise ExperimentAnalysisError(
        f"{name} must match the complete D089 experiment scope exactly: "
        + "; ".join(details)
    )


def _validate_context(
    experiment: str,
    context: Mapping[str, MetadataValue] | None,
) -> dict[str, MetadataValue]:
    supplied = dict(context or {})
    if "experiment" in supplied and supplied["experiment"] != experiment:
        raise ValueError("context 'experiment' conflicts with the requested experiment")
    for position_field in ("capture", "position"):
        if position_field in supplied:
            raise ValueError(
                f"batch context cannot define position-specific {position_field!r}"
            )
    return {**supplied, "experiment": experiment}


def _display_key(key: PositionKey) -> str:
    return f"{key.experiment} / {key.capture} / {key.position}"
