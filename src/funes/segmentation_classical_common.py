"""Shared validation and label helpers for classical segmentation engines."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
from numpy.typing import NDArray

from .contracts import IssueSeverity, MetadataValue, PipelineIssue
from .segmentation_engine import (
    SegmentationEngineRecord,
    SegmentationEngineUnavailableError,
    SegmentationResult,
)
from .segmentation_selection import SegmentationMethodId


def scientific_image_dependencies(method: SegmentationMethodId) -> tuple[Any, Any, Any, Any]:
    try:
        from scipy import ndimage as ndi
        from skimage import filters, measure, morphology
    except ImportError as exc:
        raise classical_unavailable(method) from exc
    return filters, measure, morphology, ndi


def classical_unavailable(method: SegmentationMethodId) -> SegmentationEngineUnavailableError:
    return SegmentationEngineUnavailableError(
        method,
        "SciPy and scikit-image are required but unavailable",
        "Install the declared FUNES production dependencies (for example, 'pip install -e .').",
    )


def remove_small_binary_objects(
    mask: NDArray[np.bool_],
    minimum_area: int,
    connectivity: int,
    measure: Any,
) -> NDArray[np.bool_]:
    labels = measure.label(mask, connectivity=connectivity)
    counts = np.bincount(labels.ravel())
    keep = counts >= minimum_area
    keep[0] = False
    return keep[labels]


def remove_small_labels(
    labels: NDArray[np.int32],
    minimum_area: int,
) -> NDArray[np.int32]:
    result = np.asarray(labels, dtype=np.int32).copy()
    counts = np.bincount(result.ravel())
    for label_id in range(1, len(counts)):
        if int(counts[label_id]) < minimum_area:
            result[result == label_id] = 0
    return canonicalize_labels(result)


def canonicalize_labels(labels: NDArray[np.generic]) -> NDArray[np.int32]:
    source = np.asarray(labels)
    flat = source.ravel()
    positive_flat = flat[flat > 0]
    result = np.zeros(source.shape, dtype=np.int32)
    if positive_flat.size == 0:
        return result
    positive, first_indices = np.unique(positive_flat, return_index=True)
    first_seen_order = positive[np.argsort(first_indices)]
    for new_label, old_label in enumerate(first_seen_order, start=1):
        result[source == old_label] = new_label
    return result


def roi_count(labels: NDArray[np.int32]) -> int:
    return int(np.count_nonzero(np.unique(labels) > 0))


def segmentation_result(
    labels: NDArray[np.int32],
    count: int,
    record: SegmentationEngineRecord,
    context: Mapping[str, MetadataValue] | None,
) -> SegmentationResult:
    issues: tuple[PipelineIssue, ...] = ()
    if count == 0:
        issues = (
            PipelineIssue(
                code="segmentation_no_foreground",
                message="Segmentation produced no foreground ROIs.",
                severity=IssueSeverity.WARNING,
                context={
                    **dict(context or {}),
                    "segmentation_method": record.method.value if record.method else record.name,
                    "segmentation_profile": record.profile,
                },
            ),
        )
    return SegmentationResult(
        label_image=labels,
        roi_count=count,
        engine=record,
        issues=issues,
    )


def validate_radius(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be zero or greater")


def validate_positive(value: int, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero")


def validate_connectivity(value: int) -> None:
    if value not in (1, 2):
        raise ValueError("connectivity must be 1 or 2 for 2D scikit-image operations")
