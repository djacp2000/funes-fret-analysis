"""Explicit one-factor-at-a-time parameter benchmark support for Module 7."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from .contracts import MetadataValue, PositionKey
from .segmentation_engine import SegmentationResult
from .segmentation_profile_catalog import (
    BENCHMARK_BASELINE_PROFILES,
    SegmentationProfile,
)
from .segmentation_registry import (
    DEFAULT_SEGMENTATION_REGISTRY,
    SegmentationEngineRegistry,
)
from .segmentation_selection import (
    BENCHMARK_BASELINE_PROFILE,
    SEGMENTATION_METHOD_ORDER,
    CapturePositionKey,
    SegmentationMethodId,
)


PARAMETER_BENCHMARK_ORIGIN = "module7_ofat_grid_20260714"
PARAMETER_BENCHMARK_STATUS = "parameter_benchmark_not_accuracy_validated"
PARAMETER_BENCHMARK_EXTENSION_ORIGIN = "module7_minimum_ofat_extension_20260718"
PARAMETER_BENCHMARK_EXTENSION_STATUS = "authorized_extension_not_accuracy_validated"


@dataclass(frozen=True, slots=True)
class SegmentationBenchmarkVariant:
    """One baseline or one-parameter deviation from a D044 baseline profile."""

    method: SegmentationMethodId
    variant_id: str
    effective_parameters: Mapping[str, MetadataValue]
    changed_parameter: str | None = None
    baseline_value: MetadataValue = None
    candidate_value: MetadataValue = None
    origin: str = PARAMETER_BENCHMARK_ORIGIN
    status: str = PARAMETER_BENCHMARK_STATUS

    def __post_init__(self) -> None:
        if not self.variant_id.strip():
            raise ValueError("variant_id must be a non-empty string")
        if not self.origin.strip():
            raise ValueError("origin must be a non-empty string")
        if not self.status.strip():
            raise ValueError("status must be a non-empty string")
        parameters = dict(self.effective_parameters)
        if self.changed_parameter is None:
            if self.baseline_value is not None or self.candidate_value is not None:
                raise ValueError("baseline variants cannot declare changed values")
        else:
            if self.changed_parameter not in parameters:
                raise ValueError("changed_parameter must exist in effective_parameters")
            if parameters[self.changed_parameter] != self.candidate_value:
                raise ValueError(
                    "candidate_value must match the effective changed parameter"
                )
            if self.baseline_value == self.candidate_value:
                raise ValueError("an OFAT candidate must differ from its baseline")
        object.__setattr__(
            self,
            "effective_parameters",
            MappingProxyType(parameters),
        )

    @property
    def is_baseline(self) -> bool:
        return self.changed_parameter is None

    def as_profile(self) -> SegmentationProfile:
        """Build an ephemeral profile; it is deliberately not registry state."""

        return SegmentationProfile(
            method=self.method,
            name=self.variant_id,
            parameters=self.effective_parameters,
            status=self.status,
            origin=self.origin,
        )


@dataclass(frozen=True, slots=True)
class SegmentationBenchmarkSummary:
    """Descriptive mask geometry that makes no segmentation-accuracy claim."""

    roi_count: int
    foreground_pixel_count: int
    foreground_fraction: float
    roi_area_min_pixels: int | None
    roi_area_median_pixels: float | None
    roi_area_max_pixels: int | None


@dataclass(frozen=True, slots=True)
class SegmentationBenchmarkRun:
    """One explicit candidate execution with field identity and raw labels."""

    field_key: CapturePositionKey
    variant: SegmentationBenchmarkVariant
    segmentation: SegmentationResult
    summary: SegmentationBenchmarkSummary


_PARAMETER_GRIDS: Mapping[
    SegmentationMethodId,
    tuple[tuple[str, tuple[MetadataValue, ...]], ...],
] = MappingProxyType(
    {
        SegmentationMethodId.KMEANS: (
            ("foreground_cluster_count", (1, 2)),
            ("minimum_object_area_pixels", (32, 64, 128)),
            ("opening_disk_radius", (0, 1, 2)),
            ("closing_disk_radius", (1, 3, 5)),
        ),
        SegmentationMethodId.CELLPOSE_CPSAM: (
            ("cellprob_threshold", (-1.0, 0.0, 1.0)),
            ("minimum_object_area_pixels", (8, 15, 30)),
            ("max_size_fraction", (0.2, 0.4, 0.6)),
        ),
        SegmentationMethodId.MARKER_WATERSHED: (
            ("foreground_threshold_scale", (0.9, 1.0, 1.1)),
            ("minimum_object_area_pixels", (32, 64, 128)),
            ("foreground_opening_disk_radius", (0, 1, 2)),
            ("marker_min_distance_pixels", (8, 12, 16)),
        ),
        SegmentationMethodId.OTSU_GLOBAL: (
            ("threshold_scale", (0.9, 1.0, 1.1)),
            ("minimum_object_area_pixels", (32, 64, 128)),
            ("opening_disk_radius", (0, 1, 2)),
            ("closing_disk_radius", (1, 3, 5)),
        ),
        SegmentationMethodId.CONTROL_P99: (
            ("threshold_percentile", (98.0, 99.0, 99.5)),
        ),
    }
)


def build_parameter_benchmark_variants() -> tuple[SegmentationBenchmarkVariant, ...]:
    """Return the fixed D044 OFAT grid in confirmed method/axis/value order."""

    baselines = {profile.method: profile for profile in BENCHMARK_BASELINE_PROFILES}
    variants: list[SegmentationBenchmarkVariant] = []
    for method in SEGMENTATION_METHOD_ORDER:
        baseline = baselines[method]
        variants.append(
            SegmentationBenchmarkVariant(
                method=method,
                variant_id=BENCHMARK_BASELINE_PROFILE,
                effective_parameters=baseline.parameters,
            )
        )
        for parameter, candidates in _PARAMETER_GRIDS[method]:
            baseline_value = baseline.parameters[parameter]
            for candidate in candidates:
                if candidate == baseline_value:
                    continue
                effective = dict(baseline.parameters)
                effective[parameter] = candidate
                variants.append(
                    SegmentationBenchmarkVariant(
                        method=method,
                        variant_id=(
                            f"ofat__{parameter}__{_value_token(candidate)}"
                        ),
                        effective_parameters=effective,
                        changed_parameter=parameter,
                        baseline_value=baseline_value,
                        candidate_value=candidate,
                    )
                )
    return tuple(variants)


def variants_for_method(
    method: SegmentationMethodId,
) -> tuple[SegmentationBenchmarkVariant, ...]:
    """Return only the explicitly planned variants for one method."""

    return tuple(
        variant for variant in PARAMETER_BENCHMARK_VARIANTS if variant.method is method
    )


def build_minimum_ofat_extension_variants() -> tuple[SegmentationBenchmarkVariant, ...]:
    """Return the three explicitly authorized post-D047 diagnostic variants."""

    baselines = {profile.method: profile for profile in BENCHMARK_BASELINE_PROFILES}
    specifications = (
        (SegmentationMethodId.KMEANS, "minimum_object_area_pixels", 16),
        (SegmentationMethodId.MARKER_WATERSHED, "minimum_object_area_pixels", 16),
        (SegmentationMethodId.MARKER_WATERSHED, "foreground_threshold_scale", 0.8),
    )
    variants: list[SegmentationBenchmarkVariant] = []
    for method, parameter, candidate in specifications:
        baseline = baselines[method]
        effective = dict(baseline.parameters)
        baseline_value = effective[parameter]
        effective[parameter] = candidate
        variants.append(
            SegmentationBenchmarkVariant(
                method=method,
                variant_id=f"ofat_extension__{parameter}__{_value_token(candidate)}",
                effective_parameters=effective,
                changed_parameter=parameter,
                baseline_value=baseline_value,
                candidate_value=candidate,
                origin=PARAMETER_BENCHMARK_EXTENSION_ORIGIN,
                status=PARAMETER_BENCHMARK_EXTENSION_STATUS,
            )
        )
    return tuple(variants)


def run_segmentation_benchmark_variant(
    frame: NDArray[np.generic],
    field_key: CapturePositionKey | PositionKey,
    variant: SegmentationBenchmarkVariant,
    *,
    registry: SegmentationEngineRegistry | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> SegmentationBenchmarkRun:
    """Run exactly one caller-selected variant; never rank or select a winner."""

    key = _capture_position_key(field_key)
    active_registry = registry or DEFAULT_SEGMENTATION_REGISTRY
    engine = active_registry.create_unregistered_profile_engine(variant.as_profile())
    benchmark_context: dict[str, MetadataValue] = {
        **dict(context or {}),
        "capture": key.capture,
        "position": key.position,
        "segmentation_benchmark_variant": variant.variant_id,
        "segmentation_benchmark_changed_parameter": variant.changed_parameter,
    }
    segmentation = engine.segment(frame, context=benchmark_context)
    return SegmentationBenchmarkRun(
        field_key=key,
        variant=variant,
        segmentation=segmentation,
        summary=_summarize(segmentation),
    )


def _summarize(result: SegmentationResult) -> SegmentationBenchmarkSummary:
    labels = result.label_image
    positive = labels[labels > 0]
    if positive.size:
        areas = np.bincount(positive).astype(np.int64)
        areas = areas[areas > 0]
        area_min = int(np.min(areas))
        area_median = float(np.median(areas))
        area_max = int(np.max(areas))
    else:
        area_min = None
        area_median = None
        area_max = None
    foreground_count = int(positive.size)
    return SegmentationBenchmarkSummary(
        roi_count=result.roi_count,
        foreground_pixel_count=foreground_count,
        foreground_fraction=foreground_count / labels.size,
        roi_area_min_pixels=area_min,
        roi_area_median_pixels=area_median,
        roi_area_max_pixels=area_max,
    )


def _capture_position_key(
    value: CapturePositionKey | PositionKey,
) -> CapturePositionKey:
    if isinstance(value, CapturePositionKey):
        return value
    if isinstance(value, PositionKey):
        return CapturePositionKey.from_position_key(value)
    raise TypeError("field_key must be CapturePositionKey or PositionKey")


def _value_token(value: MetadataValue) -> str:
    text = str(value).lower().replace("-", "minus_").replace(".", "_")
    return text.replace(" ", "_")


PARAMETER_BENCHMARK_VARIANTS = build_parameter_benchmark_variants()
PARAMETER_BENCHMARK_EXTENSION_VARIANTS = build_minimum_ofat_extension_variants()
