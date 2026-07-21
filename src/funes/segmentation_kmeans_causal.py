"""D062 K-means foreground-boundary causal extension for Module 7."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from .contracts import MetadataValue, PositionKey
from .segmentation_benchmark import SegmentationBenchmarkVariant
from .segmentation_engine import SegmentationResult
from .segmentation_kmeans import (
    KMeansForegroundDiagnosticTrace,
    KMeansMorphologySegmentationEngine,
)
from .segmentation_profile_catalog import BENCHMARK_BASELINE_PROFILES
from .segmentation_registry import (
    DEFAULT_SEGMENTATION_REGISTRY,
    SegmentationEngineRegistry,
)
from .segmentation_selection import CapturePositionKey, SegmentationMethodId


KMEANS_FOREGROUND_CAUSAL_EXTENSION_ORIGIN = (
    "module7_kmeans_foreground_causal_extension_20260718"
)
KMEANS_FOREGROUND_CAUSAL_EXTENSION_STATUS = (
    "implemented_not_real_data_executed_or_accuracy_validated"
)


def _reference_parameters() -> Mapping[str, MetadataValue]:
    baseline = next(
        profile
        for profile in BENCHMARK_BASELINE_PROFILES
        if profile.method is SegmentationMethodId.KMEANS
    )
    parameters = dict(baseline.parameters)
    parameters["minimum_object_area_pixels"] = 32
    parameters["foreground_boundary_relaxation_fraction"] = 0.0
    return MappingProxyType(parameters)


KMEANS_AREA32_CAUSAL_REFERENCE_PARAMETERS = _reference_parameters()


def build_kmeans_foreground_causal_extension_variants(
) -> tuple[SegmentationBenchmarkVariant, ...]:
    """Return the single D062 candidate relative to immutable K-means area 32."""

    effective = dict(KMEANS_AREA32_CAUSAL_REFERENCE_PARAMETERS)
    effective["foreground_boundary_relaxation_fraction"] = 0.5
    return (
        SegmentationBenchmarkVariant(
            method=SegmentationMethodId.KMEANS,
            variant_id="causal_extension__foreground_boundary_relaxation_fraction__0_5",
            effective_parameters=effective,
            changed_parameter="foreground_boundary_relaxation_fraction",
            baseline_value=0.0,
            candidate_value=0.5,
            origin=KMEANS_FOREGROUND_CAUSAL_EXTENSION_ORIGIN,
            status=KMEANS_FOREGROUND_CAUSAL_EXTENSION_STATUS,
        ),
    )


KMEANS_FOREGROUND_CAUSAL_EXTENSION_VARIANTS = (
    build_kmeans_foreground_causal_extension_variants()
)


@dataclass(frozen=True, slots=True)
class KMeansForegroundCausalRun:
    """One caller-authorized synthetic or real candidate call with its trace."""

    field_key: CapturePositionKey
    variant: SegmentationBenchmarkVariant
    segmentation: SegmentationResult
    trace: KMeansForegroundDiagnosticTrace


def run_kmeans_foreground_causal_variant(
    frame: NDArray[np.generic],
    field_key: CapturePositionKey | PositionKey,
    variant: SegmentationBenchmarkVariant,
    *,
    registry: SegmentationEngineRegistry | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> KMeansForegroundCausalRun:
    """Run only the exact D062 catalog member and return its diagnostic trace."""

    if variant not in KMEANS_FOREGROUND_CAUSAL_EXTENSION_VARIANTS:
        raise ValueError(
            "causal execution requires the unchanged D062 K-means foreground catalog member"
        )
    key = _capture_position_key(field_key)
    active_registry = registry or DEFAULT_SEGMENTATION_REGISTRY
    engine = active_registry.create_unregistered_profile_engine(variant.as_profile())
    if not isinstance(engine, KMeansMorphologySegmentationEngine):
        raise TypeError("D062 causal execution requires KMeansMorphologySegmentationEngine")
    if engine.config.minimum_object_area_pixels != 32:
        raise ValueError("D062 causal execution requires minimum_object_area_pixels = 32")
    segmentation, trace = engine.segment_with_diagnostic_trace(
        frame,
        context={
            **dict(context or {}),
            "capture": key.capture,
            "position": key.position,
            "segmentation_causal_variant": variant.variant_id,
            "segmentation_causal_origin": variant.origin,
        },
    )
    return KMeansForegroundCausalRun(
        field_key=key,
        variant=variant,
        segmentation=segmentation,
        trace=trace,
    )


def _capture_position_key(
    value: CapturePositionKey | PositionKey,
) -> CapturePositionKey:
    if isinstance(value, CapturePositionKey):
        return value
    if isinstance(value, PositionKey):
        return CapturePositionKey.from_position_key(value)
    raise TypeError("field_key must be CapturePositionKey or PositionKey")
