"""Deterministic replay and geometric finalization for Module 24 revisions."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from .contracts import PositionKey
from .roi_geometry import RoiFilteringResult, filter_labeled_rois
from .roi_review import roi_label_sha256
from .roi_revision import (
    RoiMaskRevision,
    RoiPixel,
    RoiRevisionError,
    RoiRevisionFinalizationState,
    RoiRevisionOperation,
    RoiRevisionOperationType,
    RoiRevisionSourceIdentity,
    RoiRevisionTraceEntry,
    _validate_automatic_results,
)
from .segmentation_engine import SegmentationResult


_INT32_MAX = int(np.iinfo(np.int32).max)


@dataclass(frozen=True, slots=True)
class RoiRevisionResult:
    """Finalized revision output with exact automatic and geometric provenance."""

    source_identity: RoiRevisionSourceIdentity
    revision: RoiMaskRevision
    original_segmentation: SegmentationResult
    original_filtering: RoiFilteringResult
    edited_label_image: NDArray[np.int32]
    geometry_audit: RoiFilteringResult
    operation_trace: tuple[RoiRevisionTraceEntry, ...]
    input_label_sha256: str
    edited_label_sha256: str
    measurement_label_sha256: str
    revision_sha256: str
    finalization_state: RoiRevisionFinalizationState = field(
        default=RoiRevisionFinalizationState.FINALIZED
    )

    def __post_init__(self) -> None:
        if self.finalization_state is not RoiRevisionFinalizationState.FINALIZED:
            raise RoiRevisionError("RoiRevisionResult must be finalized")
        if self.revision.finalization_state is not RoiRevisionFinalizationState.FINALIZED:
            raise RoiRevisionError("result revision must be finalized")
        if self.source_identity != self.revision.source:
            raise RoiRevisionError("result source identity must match its revision")
        _validate_automatic_results(self.original_segmentation, self.original_filtering)
        if self.original_filtering.source_segmentation is not self.original_segmentation:
            raise RoiRevisionError(
                "result must retain the exact original Module 7 and Module 8 objects"
            )
        edited = _readonly_label_image(self.edited_label_image, "edited_label_image")
        if tuple(edited.shape) != self.source_identity.image_shape:
            raise RoiRevisionError("edited label image shape does not match source identity")
        if not isinstance(self.geometry_audit, RoiFilteringResult):
            raise TypeError("geometry_audit must be a RoiFilteringResult")
        if self.geometry_audit.config != self.original_filtering.config:
            raise RoiRevisionError("geometry audit must reuse the Module 8 filter config")
        if not np.array_equal(self.geometry_audit.source_label_image, edited):
            raise RoiRevisionError("geometry audit source must equal the edited label image")
        trace = tuple(self.operation_trace)
        if not trace:
            raise RoiRevisionError("result operation_trace must not be empty")
        object.__setattr__(self, "edited_label_image", edited)
        object.__setattr__(self, "operation_trace", trace)
        for name, value in (
            ("input_label_sha256", self.input_label_sha256),
            ("edited_label_sha256", self.edited_label_sha256),
            ("measurement_label_sha256", self.measurement_label_sha256),
            ("revision_sha256", self.revision_sha256),
        ):
            _require_sha256(value, name)
        if self.revision_sha256 != self.revision.sha256:
            raise RoiRevisionError("result revision_sha256 does not match its revision")
        if self.edited_label_sha256 != roi_label_sha256(edited):
            raise RoiRevisionError("result edited_label_sha256 does not match its mask")
        if self.measurement_label_sha256 != roi_label_sha256(
            self.geometry_audit.filtered_label_image
        ):
            raise RoiRevisionError(
                "result measurement_label_sha256 does not match its mask"
            )

    @property
    def measurement_label_image(self) -> NDArray[np.int32]:
        """The sole revised mask eligible for future quantitative consumers."""

        return self.geometry_audit.filtered_label_image


def replay_roi_revision(
    revision: RoiMaskRevision,
    segmentation: SegmentationResult,
    filtering: RoiFilteringResult,
    position_key: PositionKey,
    *,
    parent_result: RoiRevisionResult | None = None,
) -> RoiRevisionResult:
    """Replay one finalized revision exactly and recompute Module 8 geometry."""

    if not isinstance(revision, RoiMaskRevision):
        raise TypeError("revision must be a RoiMaskRevision")
    if revision.finalization_state is not RoiRevisionFinalizationState.FINALIZED:
        raise RoiRevisionError(
            "only a finalized ROI revision may be replayed for quantitative analysis"
        )
    expected_source = RoiRevisionSourceIdentity.from_automatic_results(
        position_key,
        segmentation,
        filtering,
    )
    if revision.source != expected_source:
        raise RoiRevisionError(
            "ROI revision source identity is stale or does not match the supplied "
            "Experiment + Capture + Position and automatic masks"
        )

    if revision.parent_revision_sha256 is None:
        if parent_result is not None:
            raise RoiRevisionError(
                "parent_result was supplied but the revision has no parent hash"
            )
        current = np.array(filtering.filtered_label_image, dtype=np.int32, copy=True)
        inherited_trace: tuple[RoiRevisionTraceEntry, ...] = ()
    else:
        if parent_result is None:
            raise RoiRevisionError(
                "revision declares a parent hash but no parent_result was supplied"
            )
        if parent_result.revision_sha256 != revision.parent_revision_sha256:
            raise RoiRevisionError("parent revision hash does not match parent_result")
        if parent_result.source_identity != expected_source:
            raise RoiRevisionError("parent revision source does not match this revision")
        if (
            parent_result.original_segmentation is not segmentation
            or parent_result.original_filtering is not filtering
        ):
            raise RoiRevisionError(
                "parent result must retain the same exact Module 7 and Module 8 objects"
            )
        current = np.array(parent_result.edited_label_image, dtype=np.int32, copy=True)
        inherited_trace = parent_result.operation_trace

    input_hash = roi_label_sha256(current)
    original = segmentation.label_image
    original_filtered = filtering.filtered_label_image
    original_labels = set(_positive_labels(original))
    historical_added = {
        entry.operation.label
        for entry in inherited_trace
        if entry.operation.operation_type is RoiRevisionOperationType.ADD
    }
    largest_allocated_label = max(original_labels | historical_added, default=0)
    revision_hash = revision.sha256
    new_trace: list[RoiRevisionTraceEntry] = []

    for index, operation in enumerate(revision.operations):
        before = roi_label_sha256(current)
        largest_allocated_label = _apply_operation(
            current,
            original,
            original_filtered,
            operation,
            largest_allocated_label,
        )
        after = roi_label_sha256(current)
        if before == after:
            raise RoiRevisionError(
                f"operation {index} ({operation.operation_type.value}) is a no-op"
            )
        new_trace.append(
            RoiRevisionTraceEntry(
                revision_sha256=revision_hash,
                operation_index=index,
                operation=operation,
                input_label_sha256=before,
                output_label_sha256=after,
            )
        )

    edited_hash = roi_label_sha256(current)
    if edited_hash == input_hash:
        raise RoiRevisionError("ROI revision is a no-op after all operations")
    geometry = filter_labeled_rois(
        current,
        config=filtering.config,
        context={
            "experiment": expected_source.experiment,
            "capture": expected_source.capture,
            "position": expected_source.position,
            "mask_source": "manual_revision",
            "revision_sha256": revision_hash,
        },
    )
    immutable_geometry = _immutable_geometry_result(geometry)
    return RoiRevisionResult(
        source_identity=expected_source,
        revision=revision,
        original_segmentation=segmentation,
        original_filtering=filtering,
        edited_label_image=current,
        geometry_audit=immutable_geometry,
        operation_trace=inherited_trace + tuple(new_trace),
        input_label_sha256=input_hash,
        edited_label_sha256=edited_hash,
        measurement_label_sha256=roi_label_sha256(
            immutable_geometry.filtered_label_image
        ),
        revision_sha256=revision_hash,
    )


def _apply_operation(
    current: NDArray[np.int32],
    original: NDArray[np.int32],
    original_filtered: NDArray[np.int32],
    operation: RoiRevisionOperation,
    largest_allocated_label: int,
) -> int:
    operation_type = operation.operation_type
    label = operation.label
    present = bool(np.any(current == label))

    if operation_type is RoiRevisionOperationType.DELETE:
        if not present:
            raise RoiRevisionError(f"cannot delete unknown or already deleted label {label}")
        current[current == label] = 0
        return largest_allocated_label

    if operation_type is RoiRevisionOperationType.REPLACE:
        if not present:
            raise RoiRevisionError(f"cannot replace unknown or deleted label {label}")
        rows, cols = _pixel_indices(operation.pixels, current.shape)
        prior_support = current == label
        replacement_support = np.zeros(current.shape, dtype=bool)
        replacement_support[rows, cols] = True
        if np.array_equal(prior_support, replacement_support):
            raise RoiRevisionError(f"replacement for label {label} is unchanged")
        candidate = current.copy()
        candidate[prior_support] = 0
        _reject_overlap(candidate, rows, cols, operation)
        candidate[rows, cols] = label
        current[:] = candidate
        return largest_allocated_label

    if operation_type is RoiRevisionOperationType.ADD:
        if label <= largest_allocated_label:
            raise RoiRevisionError(
                f"new label {label} must be greater than every original or earlier "
                f"revision label ({largest_allocated_label})"
            )
        if present:
            raise RoiRevisionError(f"new label {label} is already present")
        rows, cols = _pixel_indices(operation.pixels, current.shape)
        _reject_overlap(current, rows, cols, operation)
        current[rows, cols] = label
        return label

    if not np.any(original == label):
        raise RoiRevisionError(f"cannot restore unknown original label {label}")
    if np.any(original_filtered == label):
        raise RoiRevisionError(
            f"label {label} was retained by Module 8 and is not restorable"
        )
    if present:
        raise RoiRevisionError(f"restored label {label} is already present")
    rows, cols = np.nonzero(original == label)
    _reject_overlap(current, rows, cols, operation)
    current[rows, cols] = label
    return largest_allocated_label


def _reject_overlap(
    current: NDArray[np.int32],
    rows: NDArray[np.intp],
    cols: NDArray[np.intp],
    operation: RoiRevisionOperation,
) -> None:
    overlaps = sorted(int(value) for value in np.unique(current[rows, cols]) if value > 0)
    if overlaps:
        raise RoiRevisionError(
            f"{operation.operation_type.value} operation for label {operation.label} "
            f"overlaps existing labels {overlaps}"
        )


def _pixel_indices(
    pixels: tuple[RoiPixel, ...],
    shape: tuple[int, ...],
) -> tuple[NDArray[np.intp], NDArray[np.intp]]:
    height, width = shape
    for pixel in pixels:
        row = pixel.row
        col = pixel.col
        if row >= height or col >= width:
            raise RoiRevisionError(
                f"pixel ({row}, {col}) is outside image shape ({height}, {width})"
            )
    rows = np.fromiter((pixel.row for pixel in pixels), dtype=np.intp)
    cols = np.fromiter((pixel.col for pixel in pixels), dtype=np.intp)
    return rows, cols


def _immutable_geometry_result(result: RoiFilteringResult) -> RoiFilteringResult:
    source = _readonly_label_image(result.source_label_image, "geometry source")
    filtered = _readonly_label_image(result.filtered_label_image, "geometry filtered")
    return RoiFilteringResult(
        source_label_image=source,
        filtered_label_image=filtered,
        records=result.records,
        config=result.config,
        issues=result.issues,
    )


def _readonly_label_image(
    values: NDArray[np.generic],
    name: str,
) -> NDArray[np.int32]:
    labels = np.asarray(values)
    if labels.ndim != 2 or labels.size == 0:
        raise RoiRevisionError(f"{name} must be a non-empty 2D label image")
    if not np.issubdtype(labels.dtype, np.integer) or np.any(labels < 0):
        raise RoiRevisionError(f"{name} must contain non-negative integer labels")
    if int(labels.max()) > _INT32_MAX:
        raise RoiRevisionError(f"{name} labels must fit within int32")
    stable = labels.astype(np.int32, copy=True)
    stable.setflags(write=False)
    return stable


def _positive_labels(values: NDArray[np.generic]) -> tuple[int, ...]:
    return tuple(int(value) for value in np.unique(values) if value > 0)


def _require_sha256(value: object, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise RoiRevisionError(f"{name} must be a lowercase SHA-256 value")
