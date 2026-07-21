"""Experiment-scoped orchestration for read-only Module 9 position review."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path

from .contracts import PositionKey
from .roi_geometry import RoiFilteringResult
from .roi_review import (
    InteractiveRoiReviewConfig,
    InteractiveRoiReviewDecision,
    InteractiveRoiReviewResult,
    apply_interactive_roi_review_decision,
    export_interactive_roi_review_html,
)
from .segmentation_review import (
    SegmentationFieldReviewDecision,
    SegmentationReviewState,
)
from .segmentation_selection import CapturePositionKey, SegmentationReviewStatus
from .tiff_reader import TiffPair


class ExperimentPositionReviewMode(str, Enum):
    """D088 position-coverage choice for one experiment."""

    REVIEW_ALL = "review_all"
    REVIEW_SELECTED = "review_selected"


@dataclass(frozen=True, slots=True)
class ExperimentPositionReviewDecision:
    """One D046 decision restored to its experiment-scoped identity."""

    position_key: PositionKey
    field_review: SegmentationFieldReviewDecision

    def __post_init__(self) -> None:
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if self.position_key.experiment is None:
            raise ValueError("position review decisions require an experiment label")
        if not isinstance(self.field_review, SegmentationFieldReviewDecision):
            raise TypeError("field_review must be a SegmentationFieldReviewDecision")
        if (
            CapturePositionKey.from_position_key(self.position_key)
            != self.field_review.field_key
        ):
            raise ValueError("position_key must match the D046 field review decision")

    @property
    def status(self) -> SegmentationReviewStatus:
        return self.field_review.status

    @property
    def manually_inspected(self) -> bool:
        return self.field_review.manually_inspected

    @property
    def covered(self) -> bool:
        return self.field_review.covered


@dataclass(frozen=True, slots=True)
class ExperimentPositionReview:
    """Immutable D088 scope backed by one isolated D046 ledger."""

    experiment: str
    positions: tuple[PositionKey, ...]
    mode: ExperimentPositionReviewMode
    selected_positions: tuple[PositionKey, ...] = ()
    review_state: SegmentationReviewState = field(
        default_factory=SegmentationReviewState
    )

    def __post_init__(self) -> None:
        _require_text(self.experiment, "experiment")
        if not isinstance(self.mode, ExperimentPositionReviewMode):
            raise TypeError("mode must be an ExperimentPositionReviewMode")
        if not isinstance(self.review_state, SegmentationReviewState):
            raise TypeError("review_state must be a SegmentationReviewState")

        positions = tuple(self.positions)
        if not positions:
            raise ValueError("an experiment review requires at least one position")
        position_fields = _validate_position_scope(
            positions, self.experiment, "positions"
        )
        object.__setattr__(self, "positions", positions)

        selected = tuple(self.selected_positions)
        selected_fields = _validate_position_scope(
            selected, self.experiment, "selected_positions"
        )
        object.__setattr__(self, "selected_positions", selected)
        if not set(selected_fields).issubset(position_fields):
            raise ValueError("selected_positions must belong to the experiment scope")
        if self.mode is ExperimentPositionReviewMode.REVIEW_ALL and selected:
            raise ValueError("review_all does not accept selected_positions")
        if self.mode is ExperimentPositionReviewMode.REVIEW_SELECTED and (
            not selected or len(selected) == len(positions)
        ):
            raise ValueError(
                "review_selected requires a non-empty proper subset; use review_all "
                "when every position is selected"
            )

        ledger_fields = {item.field_key for item in self.review_state.inspections}
        if not ledger_fields.issubset(position_fields):
            raise ValueError(
                "the D046 ledger contains an inspection outside this experiment "
                "position scope"
            )
        override_fields = set(self.review_state.configuration.field_overrides)
        if not override_fields.issubset(position_fields):
            raise ValueError(
                "the D044 configuration contains an override outside this "
                "experiment position scope"
            )

        approval = self.review_state.global_approval
        if approval is not None:
            if self.mode is not ExperimentPositionReviewMode.REVIEW_SELECTED:
                raise ValueError(
                    "review_all cannot contain a D046 global approval; every "
                    "position must be inspected manually"
                )
            approved_after = set(approval.inspected_fields)
            if not set(selected_fields).issubset(approved_after):
                raise ValueError(
                    "experiment approval must be recorded after every selected "
                    "position was manually inspected"
                )

    @property
    def manual_review_targets(self) -> tuple[PositionKey, ...]:
        """Positions required by the chosen mode before optional approval."""

        if self.mode is ExperimentPositionReviewMode.REVIEW_ALL:
            return self.positions
        return self.selected_positions

    @property
    def pending_manual_positions(self) -> tuple[PositionKey, ...]:
        """Required targets that do not yet have their own inspection."""

        return tuple(
            key for key in self.manual_review_targets if not self.query(key).manually_inspected
        )

    @property
    def unreviewed_positions(self) -> tuple[PositionKey, ...]:
        """Known positions still carrying the exact D046 unreviewed status."""

        return tuple(
            key
            for key in self.positions
            if self.query(key).status is SegmentationReviewStatus.UNREVIEWED
        )

    def query(self, position_key: PositionKey) -> ExperimentPositionReviewDecision:
        """Resolve one known position without allowing cross-experiment access."""

        self._require_position(position_key)
        return ExperimentPositionReviewDecision(
            position_key=position_key,
            field_review=self.review_state.query(position_key),
        )

    def export_position_viewer(
        self,
        pair: TiffPair,
        roi_filtering: RoiFilteringResult,
        output_path: Path | str,
        *,
        title: str | None = None,
        config: InteractiveRoiReviewConfig | None = None,
    ) -> InteractiveRoiReviewResult:
        """Export one position on demand, with all of its C0/C1 timepoints."""

        if not isinstance(pair, TiffPair):
            raise TypeError("pair must be a TiffPair")
        self._require_position(pair.position_key)
        display_title = title or (
            f"ROI review — {self.experiment} / {pair.position_key.capture} / "
            f"{pair.position_key.position}"
        )
        return export_interactive_roi_review_html(
            pair,
            roi_filtering,
            self.review_state,
            output_path,
            title=display_title,
            config=config,
        )

    def record_inspection(
        self,
        pair: TiffPair,
        roi_filtering: RoiFilteringResult,
        decision: InteractiveRoiReviewDecision,
    ) -> ExperimentPositionReview:
        """Apply one viewer decision to only this experiment's D046 ledger."""

        if not isinstance(pair, TiffPair):
            raise TypeError("pair must be a TiffPair")
        self._require_position(pair.position_key)
        if decision.experiment != self.experiment:
            raise ValueError(
                "experiment-scoped inspection decisions must carry the exact "
                "experiment identity from their viewer"
            )
        updated = apply_interactive_roi_review_decision(
            self.review_state, pair, roi_filtering, decision
        )
        return replace(self, review_state=updated)

    def approve_remaining(
        self,
        approval_id: str,
        *,
        approved_by: str | None = None,
        approved_at: str | None = None,
        note: str | None = None,
    ) -> ExperimentPositionReview:
        """Explicitly approve this experiment after its selected sample is complete."""

        if self.mode is not ExperimentPositionReviewMode.REVIEW_SELECTED:
            raise ValueError(
                "remaining-position approval is available only in review_selected mode"
            )
        pending = self.pending_manual_positions
        if pending:
            raise ValueError(
                "cannot approve remaining positions until every selected position "
                "has been manually inspected"
            )
        if not self.unreviewed_positions:
            raise ValueError(
                "no unreviewed positions remain in this experiment scope to approve"
            )
        updated = self.review_state.approve_global(
            approval_id,
            approved_by=approved_by,
            approved_at=approved_at,
            note=note,
        )
        return replace(self, review_state=updated)

    def _require_position(self, position_key: PositionKey) -> None:
        if not isinstance(position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if position_key.experiment != self.experiment:
            raise ValueError(
                f"position belongs to experiment {position_key.experiment!r}, not "
                f"the isolated {self.experiment!r} review scope"
            )
        if position_key not in self.positions:
            raise ValueError("position is not registered in this experiment review scope")


@dataclass(frozen=True, slots=True)
class ExperimentRoiReviewOrchestrator:
    """Immutable collection of independently scoped experiment reviews."""

    experiments: tuple[ExperimentPositionReview, ...]

    def __post_init__(self) -> None:
        experiments = tuple(self.experiments)
        if not experiments:
            raise ValueError("the orchestrator requires at least one experiment")
        for item in experiments:
            if not isinstance(item, ExperimentPositionReview):
                raise TypeError(
                    "experiments must contain ExperimentPositionReview values"
                )
        names = tuple(item.experiment for item in experiments)
        if len(set(names)) != len(names):
            raise ValueError("the orchestrator requires one isolated ledger per experiment")
        object.__setattr__(self, "experiments", experiments)

    def for_experiment(self, experiment: str) -> ExperimentPositionReview:
        _require_text(experiment, "experiment")
        for item in self.experiments:
            if item.experiment == experiment:
                return item
        raise ValueError(f"experiment {experiment!r} is not registered")

    def query(self, position_key: PositionKey) -> ExperimentPositionReviewDecision:
        if not isinstance(position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if position_key.experiment is None:
            raise ValueError("position_key requires an experiment label")
        return self.for_experiment(position_key.experiment).query(position_key)

    def export_position_viewer(
        self,
        pair: TiffPair,
        roi_filtering: RoiFilteringResult,
        output_path: Path | str,
        *,
        title: str | None = None,
        config: InteractiveRoiReviewConfig | None = None,
    ) -> InteractiveRoiReviewResult:
        if not isinstance(pair, TiffPair):
            raise TypeError("pair must be a TiffPair")
        experiment = _required_pair_experiment(pair)
        return self.for_experiment(experiment).export_position_viewer(
            pair, roi_filtering, output_path, title=title, config=config
        )

    def record_inspection(
        self,
        pair: TiffPair,
        roi_filtering: RoiFilteringResult,
        decision: InteractiveRoiReviewDecision,
    ) -> ExperimentRoiReviewOrchestrator:
        if not isinstance(pair, TiffPair):
            raise TypeError("pair must be a TiffPair")
        experiment = _required_pair_experiment(pair)
        scoped = self.for_experiment(experiment)
        return self._replace(scoped.record_inspection(pair, roi_filtering, decision))

    def approve_remaining(
        self,
        experiment: str,
        approval_id: str,
        *,
        approved_by: str | None = None,
        approved_at: str | None = None,
        note: str | None = None,
    ) -> ExperimentRoiReviewOrchestrator:
        scoped = self.for_experiment(experiment)
        return self._replace(
            scoped.approve_remaining(
                approval_id,
                approved_by=approved_by,
                approved_at=approved_at,
                note=note,
            )
        )

    def _replace(
        self, updated: ExperimentPositionReview
    ) -> ExperimentRoiReviewOrchestrator:
        return ExperimentRoiReviewOrchestrator(
            tuple(
                updated if item.experiment == updated.experiment else item
                for item in self.experiments
            )
        )


def _validate_position_scope(
    positions: tuple[PositionKey, ...], experiment: str, field_name: str
) -> set[CapturePositionKey]:
    fields: list[CapturePositionKey] = []
    for key in positions:
        if not isinstance(key, PositionKey):
            raise TypeError(f"{field_name} must contain PositionKey values")
        if key.experiment != experiment:
            raise ValueError(
                f"{field_name} must contain only positions from experiment "
                f"{experiment!r}"
            )
        fields.append(CapturePositionKey.from_position_key(key))
    if len(set(fields)) != len(fields):
        raise ValueError(f"{field_name} contains duplicate Capture + Position fields")
    return set(fields)


def _required_pair_experiment(pair: TiffPair) -> str:
    experiment = pair.position_key.experiment
    if experiment is None:
        raise ValueError("experiment-scoped ROI review requires an assigned experiment")
    return experiment


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
