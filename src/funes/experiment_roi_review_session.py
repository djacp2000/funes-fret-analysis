"""Snapshot-backed application boundary for read-only Module 9 review."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .contracts import PositionKey
from .experiment_roi_review import ExperimentRoiReviewOrchestrator
from .experiment_roi_review_persistence import (
    ExperimentRoiReviewSnapshotResult,
    export_experiment_roi_review_snapshot,
    load_experiment_roi_review_snapshot,
)
from .roi_geometry import RoiFilteringResult
from .roi_review import (
    InteractiveRoiReviewConfig,
    InteractiveRoiReviewDecision,
    InteractiveRoiReviewResult,
)
from .tiff_reader import TiffPair


@dataclass(frozen=True, slots=True)
class PositionRoiReviewMaterial:
    """Already-produced typed inputs needed to review one position."""

    pair: TiffPair
    roi_filtering: RoiFilteringResult

    def __post_init__(self) -> None:
        if not isinstance(self.pair, TiffPair):
            raise TypeError("pair must be a TiffPair")
        if not isinstance(self.roi_filtering, RoiFilteringResult):
            raise TypeError("roi_filtering must be a RoiFilteringResult")
        if self.pair.position_key.experiment is None:
            raise ValueError("review material requires an assigned experiment")

    @property
    def position_key(self) -> PositionKey:
        return self.pair.position_key


@dataclass(frozen=True, slots=True)
class ExperimentRoiReviewSession:
    """Coordinate D089/D090 review without running an analysis pipeline.

    Materials are supplied by the caller and may cover only the positions being
    delivered now. The session reads no TIFF, runs no segmentation, changes no
    ROI mask, and deliberately exposes no global-approval operation.
    """

    orchestrator: ExperimentRoiReviewOrchestrator
    materials: tuple[PositionRoiReviewMaterial, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.orchestrator, ExperimentRoiReviewOrchestrator):
            raise TypeError("orchestrator must be an ExperimentRoiReviewOrchestrator")
        materials = tuple(self.materials)
        keys: list[PositionKey] = []
        for material in materials:
            if not isinstance(material, PositionRoiReviewMaterial):
                raise TypeError(
                    "materials must contain PositionRoiReviewMaterial values"
                )
            self.orchestrator.query(material.position_key)
            keys.append(material.position_key)
        if len(set(keys)) != len(keys):
            raise ValueError("review materials contain duplicate experiment positions")
        object.__setattr__(self, "materials", materials)

    @classmethod
    def from_snapshot(
        cls,
        snapshot_path: Path | str,
        materials: tuple[PositionRoiReviewMaterial, ...] = (),
    ) -> ExperimentRoiReviewSession:
        """Open one strictly validated D090 snapshot with caller-owned materials."""

        return cls(load_experiment_roi_review_snapshot(snapshot_path), materials)

    @property
    def pending_manual_positions(self) -> tuple[PositionKey, ...]:
        """All D088-required inspections still pending, in declared scope order."""

        return tuple(
            key
            for experiment in self.orchestrator.experiments
            for key in experiment.pending_manual_positions
        )

    @property
    def available_pending_positions(self) -> tuple[PositionKey, ...]:
        """Pending manual targets whose typed review material is registered."""

        available = {material.position_key for material in self.materials}
        return tuple(key for key in self.pending_manual_positions if key in available)

    @property
    def missing_pending_positions(self) -> tuple[PositionKey, ...]:
        """Pending manual targets not included in this delivery session."""

        available = {material.position_key for material in self.materials}
        return tuple(key for key in self.pending_manual_positions if key not in available)

    def material_for(self, position_key: PositionKey) -> PositionRoiReviewMaterial:
        """Return exact typed material after enforcing the D089 scope."""

        self.orchestrator.query(position_key)
        for material in self.materials:
            if material.position_key == position_key:
                return material
        raise ValueError(
            "no review material is registered for the requested experiment position"
        )

    def export_position_viewer(
        self,
        position_key: PositionKey,
        output_path: Path | str,
        *,
        title: str | None = None,
        config: InteractiveRoiReviewConfig | None = None,
    ) -> InteractiveRoiReviewResult:
        """Export one existing position through the unchanged D089 viewer boundary."""

        material = self.material_for(position_key)
        return self.orchestrator.export_position_viewer(
            material.pair,
            material.roi_filtering,
            output_path,
            title=title,
            config=config,
        )

    def record_inspection(
        self,
        position_key: PositionKey,
        decision: InteractiveRoiReviewDecision,
    ) -> ExperimentRoiReviewSession:
        """Apply one explicit viewer decision and return a new immutable session."""

        if not isinstance(decision, InteractiveRoiReviewDecision):
            raise TypeError("decision must be an InteractiveRoiReviewDecision")
        material = self.material_for(position_key)
        updated = self.orchestrator.record_inspection(
            material.pair,
            material.roi_filtering,
            decision,
        )
        return replace(self, orchestrator=updated)

    def export_snapshot(
        self, output_path: Path | str
    ) -> ExperimentRoiReviewSnapshotResult:
        """Persist the current state through the unchanged state-neutral D090 API."""

        return export_experiment_roi_review_snapshot(
            self.orchestrator, output_path
        )
