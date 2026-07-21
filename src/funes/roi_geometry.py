"""Geometric filtering for labeled ROI masks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from .contracts import IssueSeverity, MetadataValue, PipelineIssue
from .segmentation_engine import SegmentationResult


class BorderTouchPolicy(str, Enum):
    """How geometric filtering should handle ROIs touching an image border."""

    ACCEPT = "accept"
    FLAG = "flag"
    EXCLUDE = "exclude"


class RoiFilterStatus(str, Enum):
    """Geometric status assigned to one ROI label."""

    ACCEPTED = "accepted"
    FLAGGED = "flagged"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class RoiGeometryFilterConfig:
    """Configurable pixel-geometry limits for labeled ROI masks."""

    min_area_pixels: int | None = None
    max_area_pixels: int | None = None
    border_policy: BorderTouchPolicy = BorderTouchPolicy.FLAG

    def __post_init__(self) -> None:
        if self.min_area_pixels is not None and self.min_area_pixels < 1:
            raise ValueError("min_area_pixels must be at least 1 when provided")
        if self.max_area_pixels is not None and self.max_area_pixels < 1:
            raise ValueError("max_area_pixels must be at least 1 when provided")
        if (
            self.min_area_pixels is not None
            and self.max_area_pixels is not None
            and self.min_area_pixels > self.max_area_pixels
        ):
            raise ValueError("min_area_pixels must be less than or equal to max_area_pixels")
        object.__setattr__(self, "border_policy", BorderTouchPolicy(self.border_policy))


@dataclass(frozen=True, slots=True)
class RoiBoundingBox:
    """Inclusive pixel bounding box for one labeled ROI."""

    min_row: int
    min_col: int
    max_row: int
    max_col: int

    def __post_init__(self) -> None:
        if min(self.min_row, self.min_col, self.max_row, self.max_col) < 0:
            raise ValueError("ROI bounding-box coordinates must be zero or greater")
        if self.min_row > self.max_row:
            raise ValueError("min_row must be less than or equal to max_row")
        if self.min_col > self.max_col:
            raise ValueError("min_col must be less than or equal to max_col")


@dataclass(frozen=True, slots=True)
class RoiGeometry:
    """Measured geometry for one positive label in a segmentation mask."""

    label: int
    area_pixels: int
    bounding_box: RoiBoundingBox
    centroid_row: float
    centroid_col: float
    touches_border: bool

    def __post_init__(self) -> None:
        if self.label < 1:
            raise ValueError("ROI label must be a positive integer")
        if self.area_pixels < 1:
            raise ValueError("ROI area_pixels must be at least 1")


@dataclass(frozen=True, slots=True)
class RoiFilterRecord:
    """Geometry and filtering decision for one ROI label."""

    geometry: RoiGeometry
    status: RoiFilterStatus
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", RoiFilterStatus(self.status))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        if self.status is not RoiFilterStatus.ACCEPTED and not self.reasons:
            raise ValueError("flagged or rejected ROI records must include at least one reason")

    @property
    def accepted(self) -> bool:
        """Whether this ROI remains in the filtered label image."""

        return self.status in (RoiFilterStatus.ACCEPTED, RoiFilterStatus.FLAGGED)


@dataclass(frozen=True, slots=True)
class RoiFilteringResult:
    """Filtered ROI labels plus source segmentation and geometric audit records."""

    source_label_image: NDArray[np.int32]
    filtered_label_image: NDArray[np.int32]
    records: tuple[RoiFilterRecord, ...]
    config: RoiGeometryFilterConfig = field(default_factory=RoiGeometryFilterConfig)
    issues: tuple[PipelineIssue, ...] = ()
    source_segmentation: SegmentationResult | None = None

    def __post_init__(self) -> None:
        source = _validated_label_image(self.source_label_image)
        filtered = _validated_label_image(self.filtered_label_image)
        if source.shape != filtered.shape:
            raise ValueError("source_label_image and filtered_label_image must have the same shape")
        if self.source_segmentation is not None:
            if not isinstance(self.source_segmentation, SegmentationResult):
                raise TypeError("source_segmentation must be a SegmentationResult when present")
            segmentation_labels = self.source_segmentation.label_image
            if source.shape != segmentation_labels.shape or not np.array_equal(
                source, segmentation_labels
            ):
                raise ValueError(
                    "source_label_image must match source_segmentation.label_image exactly"
                )
            source = segmentation_labels
        object.__setattr__(self, "source_label_image", source)
        object.__setattr__(self, "filtered_label_image", filtered)
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "issues", tuple(self.issues))

    @property
    def accepted_count(self) -> int:
        """Number of accepted or flagged ROI labels in the filtered mask."""

        return sum(record.accepted for record in self.records)

    @property
    def rejected_count(self) -> int:
        """Number of ROI labels removed from the filtered mask."""

        return sum(record.status is RoiFilterStatus.REJECTED for record in self.records)


def filter_labeled_rois(
    label_image: NDArray[np.generic],
    config: RoiGeometryFilterConfig | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> RoiFilteringResult:
    """Apply geometric filtering to a label array without segmentation provenance.

    Use :func:`filter_segmentation_rois` at the Module 7-to-8 boundary so the
    complete ``SegmentationResult`` provenance remains attached.
    """

    return _filter_labeled_rois(
        label_image,
        config=config,
        context=context,
        source_segmentation=None,
    )


def filter_segmentation_rois(
    segmentation: SegmentationResult,
    config: RoiGeometryFilterConfig | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> RoiFilteringResult:
    """Filter ``SegmentationResult.label_image`` without relabeling or lost provenance."""

    if not isinstance(segmentation, SegmentationResult):
        raise TypeError("segmentation must be a SegmentationResult")
    return _filter_labeled_rois(
        segmentation.label_image,
        config=config,
        context=context,
        source_segmentation=segmentation,
    )


def _filter_labeled_rois(
    label_image: NDArray[np.generic],
    config: RoiGeometryFilterConfig | None,
    context: Mapping[str, MetadataValue] | None,
    source_segmentation: SegmentationResult | None,
) -> RoiFilteringResult:

    config = config or RoiGeometryFilterConfig()
    labels = _validated_label_image(label_image)
    filtered = np.zeros(labels.shape, dtype=np.int32)
    context_values = dict(context or {})

    records: list[RoiFilterRecord] = []
    issues: list[PipelineIssue] = []
    for label in _positive_labels(labels):
        geometry = _measure_roi_geometry(labels, label)
        record = _classify_roi_geometry(geometry, config)
        records.append(record)
        if record.accepted:
            filtered[labels == label] = label
        if record.status is not RoiFilterStatus.ACCEPTED:
            issues.append(_issue_for_record(record, config, context_values))

    return RoiFilteringResult(
        source_label_image=labels,
        filtered_label_image=filtered,
        records=tuple(records),
        source_segmentation=source_segmentation,
        config=config,
        issues=tuple(issues),
    )


def _validated_label_image(label_image: NDArray[np.generic]) -> NDArray[np.int32]:
    labels = np.asarray(label_image)
    if labels.ndim != 2 or labels.size == 0:
        raise ValueError("ROI geometry filtering requires a non-empty 2D label image")
    if not np.issubdtype(labels.dtype, np.integer):
        raise ValueError("ROI geometry filtering labels must use an integer dtype")
    if np.any(labels < 0):
        raise ValueError("ROI geometry filtering labels must be zero or greater")
    if int(labels.max()) > np.iinfo(np.int32).max:
        raise ValueError("ROI geometry filtering labels must fit within int32")
    return labels.astype(np.int32, copy=False)


def _positive_labels(labels: NDArray[np.int32]) -> tuple[int, ...]:
    return tuple(sorted(int(label) for label in np.unique(labels) if label > 0))


def _measure_roi_geometry(labels: NDArray[np.int32], label: int) -> RoiGeometry:
    coordinates = np.argwhere(labels == label)
    rows = coordinates[:, 0]
    cols = coordinates[:, 1]
    min_row = int(rows.min())
    max_row = int(rows.max())
    min_col = int(cols.min())
    max_col = int(cols.max())
    height, width = labels.shape
    return RoiGeometry(
        label=label,
        area_pixels=int(coordinates.shape[0]),
        bounding_box=RoiBoundingBox(
            min_row=min_row,
            min_col=min_col,
            max_row=max_row,
            max_col=max_col,
        ),
        centroid_row=float(rows.mean()),
        centroid_col=float(cols.mean()),
        touches_border=(
            min_row == 0
            or min_col == 0
            or max_row == height - 1
            or max_col == width - 1
        ),
    )


def _classify_roi_geometry(
    geometry: RoiGeometry,
    config: RoiGeometryFilterConfig,
) -> RoiFilterRecord:
    rejection_reasons: list[str] = []
    if config.min_area_pixels is not None and geometry.area_pixels < config.min_area_pixels:
        rejection_reasons.append("roi_area_below_minimum")
    if config.max_area_pixels is not None and geometry.area_pixels > config.max_area_pixels:
        rejection_reasons.append("roi_area_above_maximum")
    if (
        geometry.touches_border
        and config.border_policy is BorderTouchPolicy.EXCLUDE
    ):
        rejection_reasons.append("roi_touches_border")

    if rejection_reasons:
        return RoiFilterRecord(
            geometry=geometry,
            status=RoiFilterStatus.REJECTED,
            reasons=tuple(rejection_reasons),
        )
    if geometry.touches_border and config.border_policy is BorderTouchPolicy.FLAG:
        return RoiFilterRecord(
            geometry=geometry,
            status=RoiFilterStatus.FLAGGED,
            reasons=("roi_touches_border",),
        )
    return RoiFilterRecord(geometry=geometry, status=RoiFilterStatus.ACCEPTED)


def _issue_for_record(
    record: RoiFilterRecord,
    config: RoiGeometryFilterConfig,
    context: Mapping[str, MetadataValue],
) -> PipelineIssue:
    geometry = record.geometry
    message = (
        "ROI was rejected by geometric filtering."
        if record.status is RoiFilterStatus.REJECTED
        else "ROI touches the image border and remains flagged."
    )
    return PipelineIssue(
        code=f"geometry_filter_{record.status.value}",
        message=message,
        severity=IssueSeverity.WARNING,
        context={
            **dict(context),
            "label": geometry.label,
            "status": record.status.value,
            "reasons": ",".join(record.reasons),
            "area_pixels": geometry.area_pixels,
            "min_area_pixels": config.min_area_pixels,
            "max_area_pixels": config.max_area_pixels,
            "border_policy": config.border_policy.value,
            "touches_border": geometry.touches_border,
            "bbox_min_row": geometry.bounding_box.min_row,
            "bbox_min_col": geometry.bounding_box.min_col,
            "bbox_max_row": geometry.bounding_box.max_row,
            "bbox_max_col": geometry.bounding_box.max_col,
        },
    )
