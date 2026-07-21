"""Reviewed, single-position orchestration across analysis Modules 5 through 13.

This application boundary consumes an already assigned in-memory TIFF pair and an
existing experiment-scoped Module 9 review ledger.  It performs no discovery,
TIFF reading, scientific approval, ROI editing, export, or persistence.  One
already-finalized Module 24 revision may optionally replace the automatic Module 8
measurement mask without replacing its preserved automatic provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .contracts import Channel, MetadataValue, PipelineIssue
from .experiment_roi_review import (
    ExperimentPositionReviewDecision,
    ExperimentRoiReviewOrchestrator,
)
from .fret_calculation import (
    FretCalculationConfig,
    FretCalculationResult,
    FretCalculationStrategy,
    calculate_fret,
)
from .intensity_qc import (
    IntensityQcConfig,
    IntensityQcResult,
    IntensityQcStrategy,
    evaluate_filtered_roi_intensity_qc,
)
from .quantitative_background import (
    QuantitativeBackgroundResult,
    QuantitativeBackgroundStrategy,
    estimate_quantitative_background,
)
from .roi_geometry import (
    RoiFilteringResult,
    RoiGeometryFilterConfig,
    filter_segmentation_rois,
)
from .roi_revision import RoiMaskRevision, RoiRevisionError, RoiRevisionSourceIdentity
from .roi_revision_chain import RoiRevisionChainError, RoiRevisionChainResult
from .roi_revision_replay import RoiRevisionResult, replay_roi_revision
from .segmentation_channel import (
    SegmentationChannelSelection,
    SegmentationChannelSelectionConfig,
    select_segmentation_channel,
)
from .segmentation_engine import SegmentationResult
from .segmentation_preprocessing import (
    SegmentationPreprocessingResult,
    SegmentationPreprocessingStrategy,
    preprocess_for_segmentation,
)
from .segmentation_registry import (
    SegmentationEngineRegistry,
    segment_configured_first_frame,
)
from .temporal_intensity import (
    TemporalIntensityExtractionConfig,
    TemporalIntensityExtractionStrategy,
    TemporalIntensityResult,
    extract_filtered_roi_temporal_intensities,
)
from .tiff_reader import TiffPair


class PositionAnalysisError(RuntimeError):
    """Raised when a position is not eligible to enter the reviewed pipeline."""


@dataclass(frozen=True, slots=True)
class PositionAnalysisConfig:
    """Every scientific configuration required for one Modules 5-13 run.

    There are intentionally no scientific defaults at this orchestration boundary.
    Optional strategy values replace implementation mechanics while their matching
    typed configurations remain explicit.
    """

    channel_selection: SegmentationChannelSelectionConfig
    segmentation_preprocessor: SegmentationPreprocessingStrategy
    roi_geometry: RoiGeometryFilterConfig
    quantitative_background: QuantitativeBackgroundStrategy
    intensity_qc: IntensityQcConfig
    temporal_intensity: TemporalIntensityExtractionConfig
    fret: FretCalculationConfig
    intensity_qc_strategy: IntensityQcStrategy | None = None
    temporal_intensity_strategy: TemporalIntensityExtractionStrategy | None = None
    fret_strategy: FretCalculationStrategy | None = None

    def __post_init__(self) -> None:
        for name, value, expected in (
            (
                "channel_selection",
                self.channel_selection,
                SegmentationChannelSelectionConfig,
            ),
            ("roi_geometry", self.roi_geometry, RoiGeometryFilterConfig),
            ("intensity_qc", self.intensity_qc, IntensityQcConfig),
            (
                "temporal_intensity",
                self.temporal_intensity,
                TemporalIntensityExtractionConfig,
            ),
            ("fret", self.fret, FretCalculationConfig),
        ):
            if not isinstance(value, expected):
                raise TypeError(f"{name} must be a {expected.__name__}")
        _require_strategy(
            self.segmentation_preprocessor,
            "segmentation_preprocessor",
            "preprocess",
        )
        _require_strategy(
            self.quantitative_background,
            "quantitative_background",
            "estimate",
        )
        if self.intensity_qc_strategy is not None:
            _require_strategy(
                self.intensity_qc_strategy, "intensity_qc_strategy", "evaluate"
            )
        if self.temporal_intensity_strategy is not None:
            _require_strategy(
                self.temporal_intensity_strategy,
                "temporal_intensity_strategy",
                "extract",
            )
        if self.fret_strategy is not None:
            _require_strategy(self.fret_strategy, "fret_strategy", "calculate")


@dataclass(frozen=True, slots=True)
class PositionAnalysisResult:
    """Complete in-memory evidence from one reviewed position analysis."""

    pair: TiffPair
    review_decision: ExperimentPositionReviewDecision
    channel_selection: SegmentationChannelSelection
    preprocessing: SegmentationPreprocessingResult
    segmentation: SegmentationResult
    roi_filtering: RoiFilteringResult
    background: QuantitativeBackgroundResult
    intensity_qc: IntensityQcResult
    temporal_intensity: TemporalIntensityResult
    fret: FretCalculationResult
    roi_revision: RoiRevisionResult | None = None
    roi_revision_chain: RoiRevisionChainResult | None = None
    issues: tuple[PipelineIssue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.pair, TiffPair):
            raise TypeError("pair must be a TiffPair")
        if self.review_decision.position_key != self.pair.position_key:
            raise ValueError("review_decision must match the analyzed position exactly")
        selection = self.segmentation.engine.selection
        if selection is None:
            raise ValueError("configured segmentation must preserve D046 provenance")
        field_review = self.review_decision.field_review
        if (
            selection.effective_method is not field_review.selection.method
            or selection.effective_profile != field_review.selection.profile
            or selection.review_status is not field_review.status
        ):
            raise ValueError(
                "segmentation provenance must match the exact D046 review decision"
            )
        if self.roi_filtering.source_segmentation is not self.segmentation:
            raise ValueError(
                "roi_filtering must retain the exact segmentation result as provenance"
            )
        if self.roi_revision_chain is not None:
            if not isinstance(self.roi_revision_chain, RoiRevisionChainResult):
                raise TypeError(
                    "roi_revision_chain must be a RoiRevisionChainResult when present"
                )
            if self.roi_revision is not self.roi_revision_chain.terminal_result:
                raise ValueError(
                    "roi_revision_chain must retain the exact terminal ROI revision result"
                )
            expected_source = RoiRevisionSourceIdentity.from_automatic_results(
                self.pair.position_key,
                self.segmentation,
                self.roi_filtering,
            )
            if self.roi_revision_chain.terminal_result.source_identity != expected_source:
                raise ValueError(
                    "roi_revision_chain terminal result is incompatible with the "
                    "automatic Module 7 and Module 8 provenance"
                )
        if self.roi_revision is not None:
            if not isinstance(self.roi_revision, RoiRevisionResult):
                raise TypeError("roi_revision must be a RoiRevisionResult when present")
            if self.roi_revision_chain is None and (
                self.roi_revision.original_segmentation is not self.segmentation
                or self.roi_revision.original_filtering is not self.roi_filtering
            ):
                raise ValueError(
                    "roi_revision must retain the exact automatic Module 7 and "
                    "Module 8 results from this position run"
                )
        object.__setattr__(self, "issues", tuple(self.issues))

    @property
    def measurement_roi_filtering(self) -> RoiFilteringResult:
        """Return the sole geometry result consumed by Modules 10 through 13."""

        if self.roi_revision is None:
            return self.roi_filtering
        return self.roi_revision.geometry_audit

    @property
    def mask_source(self) -> str:
        """Stable provenance value for the effective quantitative mask."""

        return "automatic" if self.roi_revision is None else "manual_revision"

    @property
    def revision_sha256(self) -> str | None:
        """Return the finalized Module 24 hash, or ``None`` for automatic masks."""

        if self.roi_revision is None:
            return None
        return self.roi_revision.revision_sha256


def run_reviewed_position_analysis(
    pair: TiffPair,
    review_orchestrator: ExperimentRoiReviewOrchestrator,
    config: PositionAnalysisConfig,
    *,
    segmentation_registry: SegmentationEngineRegistry | None = None,
    context: Mapping[str, MetadataValue] | None = None,
    roi_revision: RoiMaskRevision | None = None,
    roi_revision_chain: RoiRevisionChainResult | None = None,
) -> PositionAnalysisResult:
    """Run one assigned, review-covered position through Modules 5 through 13.

    Review coverage is consumed but never created.  A required D088 manual target
    must have its own inspection; any other position must already be covered by the
    isolated D089 ledger.  This function exposes no approval or ROI mutation path.
    A supplied Module 24 root revision is replayed fail-closed against the
    automatic Module 7/8 results. Alternatively, one already-validated revision
    chain may supply its terminal result. The two routes are mutually exclusive;
    the complete chain remains provenance while Modules 10--13 receive only its
    terminal measurement mask.
    """

    if not isinstance(pair, TiffPair):
        raise TypeError("pair must be a TiffPair")
    if not isinstance(review_orchestrator, ExperimentRoiReviewOrchestrator):
        raise TypeError(
            "review_orchestrator must be an ExperimentRoiReviewOrchestrator"
        )
    if not isinstance(config, PositionAnalysisConfig):
        raise TypeError("config must be a PositionAnalysisConfig")
    if roi_revision is not None and not isinstance(roi_revision, RoiMaskRevision):
        raise TypeError("roi_revision must be a RoiMaskRevision when present")
    if roi_revision_chain is not None and not isinstance(
        roi_revision_chain, RoiRevisionChainResult
    ):
        raise TypeError(
            "roi_revision_chain must be a RoiRevisionChainResult when present"
        )
    if roi_revision is not None and roi_revision_chain is not None:
        raise PositionAnalysisError(
            "roi_revision and roi_revision_chain are mutually exclusive"
        )

    experiment = pair.position_key.experiment
    if experiment is None:
        raise PositionAnalysisError(
            "reviewed position analysis requires an experiment-assigned TiffPair"
        )
    scoped_review = review_orchestrator.for_experiment(experiment)
    decision = scoped_review.query(pair.position_key)
    if (
        pair.position_key in scoped_review.manual_review_targets
        and not decision.manually_inspected
    ):
        raise PositionAnalysisError(
            "position is a required D088 manual-review target but has no explicit "
            "D046 inspection; export and apply its read-only review decision first"
        )
    if not decision.covered:
        raise PositionAnalysisError(
            "position remains unreviewed in the isolated D089 ledger; this runner "
            "cannot infer scientific approval or review coverage"
        )

    run_context = _position_context(pair, context)
    channel_selection = select_segmentation_channel(pair, config.channel_selection)
    selected_frames = (
        pair.c0.frames
        if channel_selection.selected_channel is Channel.C0
        else pair.c1.frames
    )
    preprocessing = preprocess_for_segmentation(
        selected_frames[0],
        strategy=config.segmentation_preprocessor,
        context=run_context,
    )
    segmentation = segment_configured_first_frame(
        preprocessing.processed_frame,
        scoped_review.review_state.configuration,
        pair.position_key,
        registry=segmentation_registry,
        review_state=scoped_review.review_state,
        context=run_context,
    )
    roi_filtering = filter_segmentation_rois(
        segmentation,
        config=config.roi_geometry,
        context=run_context,
    )

    revision_result: RoiRevisionResult | None = None
    if roi_revision is not None:
        try:
            revision_result = replay_roi_revision(
                roi_revision,
                segmentation,
                roi_filtering,
                pair.position_key,
            )
        except RoiRevisionError as exc:
            raise PositionAnalysisError(
                "supplied Module 24 ROI revision is not eligible for quantitative "
                f"analysis of {experiment} / {pair.position_key.capture} / "
                f"{pair.position_key.position}: {exc}"
            ) from exc
    elif roi_revision_chain is not None:
        try:
            validated_chain = RoiRevisionChainResult(roi_revision_chain.entries)
            expected_source = RoiRevisionSourceIdentity.from_automatic_results(
                pair.position_key,
                segmentation,
                roi_filtering,
            )
            if validated_chain.terminal_result.source_identity != expected_source:
                raise RoiRevisionChainError(
                    "terminal result is incompatible with the current automatic "
                    "Module 7 and Module 8 provenance"
                )
            revision_result = roi_revision_chain.terminal_result
        except RoiRevisionChainError as exc:
            raise PositionAnalysisError(
                "supplied finalized Module 24 ROI revision chain is not eligible "
                f"for quantitative analysis of {experiment} / "
                f"{pair.position_key.capture} / {pair.position_key.position}: {exc}"
            ) from exc

    measurement_filtering = (
        roi_filtering
        if revision_result is None
        else revision_result.geometry_audit
    )
    if measurement_filtering.accepted_count == 0:
        mask_description = (
            "reviewed segmentation"
            if revision_result is None
            else "finalized Module 24 revision"
        )
        raise PositionAnalysisError(
            f"{mask_description} produced no retained ROI for "
            f"{experiment} / {pair.position_key.capture} / "
            f"{pair.position_key.position}; no downstream measurement was run"
        )

    measurement_context = {
        **run_context,
        "mask_source": (
            "automatic" if revision_result is None else "manual_revision"
        ),
        "revision_sha256": (
            None if revision_result is None else revision_result.revision_sha256
        ),
    }
    background = estimate_quantitative_background(
        pair,
        roi_label_image=measurement_filtering.filtered_label_image,
        strategy=config.quantitative_background,
        context=measurement_context,
    )
    intensity_qc = evaluate_filtered_roi_intensity_qc(
        pair,
        measurement_filtering,
        background,
        config.intensity_qc,
        strategy=config.intensity_qc_strategy,
        context=measurement_context,
    )
    temporal_intensity = extract_filtered_roi_temporal_intensities(
        pair,
        measurement_filtering,
        background,
        intensity_qc,
        config=config.temporal_intensity,
        strategy=config.temporal_intensity_strategy,
        context=measurement_context,
    )
    fret = calculate_fret(
        temporal_intensity,
        config.fret,
        strategy=config.fret_strategy,
        context=measurement_context,
    )
    issues = (
        *channel_selection.issues,
        *preprocessing.issues,
        *segmentation.issues,
        *roi_filtering.issues,
        *(
            ()
            if revision_result is None
            else revision_result.geometry_audit.issues
        ),
        *background.issues,
        *intensity_qc.issues,
        *temporal_intensity.issues,
        *fret.issues,
    )
    return PositionAnalysisResult(
        pair=pair,
        review_decision=decision,
        channel_selection=channel_selection,
        preprocessing=preprocessing,
        segmentation=segmentation,
        roi_filtering=roi_filtering,
        background=background,
        intensity_qc=intensity_qc,
        temporal_intensity=temporal_intensity,
        fret=fret,
        roi_revision=revision_result,
        roi_revision_chain=roi_revision_chain,
        issues=issues,
    )


def _position_context(
    pair: TiffPair,
    context: Mapping[str, MetadataValue] | None,
) -> Mapping[str, MetadataValue]:
    expected: dict[str, MetadataValue] = {
        "experiment": pair.position_key.experiment,
        "capture": pair.position_key.capture,
        "position": pair.position_key.position,
    }
    supplied = dict(context or {})
    for key, value in expected.items():
        if key in supplied and supplied[key] != value:
            raise ValueError(
                f"context {key!r} conflicts with the exact TiffPair position identity"
            )
    return {**supplied, **expected, "purpose": "reviewed_position_analysis"}


def _require_strategy(value: object, field_name: str, method_name: str) -> None:
    name = getattr(value, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise TypeError(f"{field_name} must expose a non-empty strategy name")
    if not callable(getattr(value, method_name, None)):
        raise TypeError(f"{field_name} must expose a callable {method_name}()")
