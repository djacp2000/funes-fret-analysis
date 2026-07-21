"""Stable registry for named Module 7 engines and auditable profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Mapping, cast

import numpy as np
from numpy.typing import NDArray

from .contracts import MetadataValue, PositionKey
from .segmentation_cellpose import (
    CELLPOSE_CPU_WARNING,
    CellposeCPSamConfig,
    CellposeCPSamSegmentationEngine,
)
from .segmentation_classical import (
    KMeansMorphologyConfig,
    KMeansMorphologySegmentationEngine,
    MarkerWatershedConfig,
    MarkerWatershedSegmentationEngine,
    OtsuMorphologyConfig,
    OtsuMorphologySegmentationEngine,
)
from .segmentation_engine import (
    PercentileThresholdSegmentationConfig,
    PercentileThresholdSegmentationEngine,
    SegmentationEngine,
    SegmentationResult,
)
from .segmentation_profile_catalog import (
    BENCHMARK_BASELINE_PROFILES,
    PROVISIONAL_WORKING_KMEANS_PROFILE,
    REGISTERED_SEGMENTATION_PROFILES,
    SegmentationProfile,
)
from .segmentation_review import (
    SegmentationFieldReviewDecision,
    SegmentationReviewState,
)
from .segmentation_selection import (
    SEGMENTATION_METHOD_ORDER,
    CapturePositionKey,
    ResolvedSegmentationSelection,
    SegmentationConfiguration,
    SegmentationMethodId,
    SegmentationSelectionProvenance,
    selection_provenance,
)


@dataclass(frozen=True, slots=True)
class SegmentationMethodDescriptor:
    """User-facing registry metadata, independent from GUI implementation."""

    method: SegmentationMethodId
    display_name: str
    optional_dependency: bool = False
    note: str | None = None


EngineFactory = Callable[
    [SegmentationProfile, SegmentationSelectionProvenance | None],
    SegmentationEngine,
]


@dataclass(frozen=True, slots=True)
class SegmentationEngineRegistry:
    """Immutable engine/profile registry with explicit, non-fallback creation."""

    methods: tuple[SegmentationMethodDescriptor, ...]
    profiles: tuple[SegmentationProfile, ...]
    factories: Mapping[SegmentationMethodId, EngineFactory] = field(repr=False)

    def __post_init__(self) -> None:
        method_ids = tuple(descriptor.method for descriptor in self.methods)
        if len(set(method_ids)) != len(method_ids):
            raise ValueError("segmentation registry method identifiers must be unique")
        if tuple(method_ids) != SEGMENTATION_METHOD_ORDER:
            raise ValueError("segmentation registry methods must use the confirmed display order")
        profile_keys = [(profile.method, profile.name) for profile in self.profiles]
        if len(set(profile_keys)) != len(profile_keys):
            raise ValueError("segmentation registry profile keys must be unique")
        if set(self.factories) != set(method_ids):
            raise ValueError("segmentation registry requires exactly one factory per method")
        object.__setattr__(self, "factories", MappingProxyType(dict(self.factories)))

    def descriptor(self, method: SegmentationMethodId) -> SegmentationMethodDescriptor:
        for descriptor in self.methods:
            if descriptor.method is method:
                return descriptor
        raise ValueError(f"segmentation method is not registered: {method.value}")

    def profiles_for(self, method: SegmentationMethodId) -> tuple[SegmentationProfile, ...]:
        return tuple(profile for profile in self.profiles if profile.method is method)

    def profile(self, method: SegmentationMethodId, name: str) -> SegmentationProfile:
        for profile in self.profiles:
            if profile.method is method and profile.name == name:
                return profile
        available = ", ".join(profile.name for profile in self.profiles_for(method)) or "none"
        raise ValueError(
            f"unknown profile '{name}' for segmentation method '{method.value}'; "
            f"available profiles: {available}"
        )

    def create_engine(
        self,
        resolved: ResolvedSegmentationSelection,
        field_review: SegmentationFieldReviewDecision | None = None,
    ) -> SegmentationEngine:
        profile = self.profile(resolved.method, resolved.profile)
        return self.factories[resolved.method](
            profile,
            selection_provenance(resolved, field_review),
        )

    def create_unregistered_profile_engine(
        self,
        profile: SegmentationProfile,
    ) -> SegmentationEngine:
        """Create an explicit benchmark engine without registering a new preset."""

        self.descriptor(profile.method)
        return self.factories[profile.method](profile, None)


DEFAULT_SEGMENTATION_CONFIGURATION = SegmentationConfiguration()


def create_default_segmentation_engine() -> SegmentationEngine:
    """Create the provisional K-means area-32 working profile."""

    return DEFAULT_SEGMENTATION_REGISTRY.create_engine(
        DEFAULT_SEGMENTATION_CONFIGURATION.resolve()
    )


def segment_configured_first_frame(
    frame: NDArray[np.generic],
    configuration: SegmentationConfiguration,
    field_key: CapturePositionKey | PositionKey,
    *,
    registry: SegmentationEngineRegistry | None = None,
    review_state: SegmentationReviewState | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> SegmentationResult:
    """Resolve and execute one field with optional D045 review provenance."""

    active_registry = registry or DEFAULT_SEGMENTATION_REGISTRY
    field_review = None
    if review_state is not None:
        if review_state.configuration != configuration:
            raise ValueError(
                "review_state configuration does not match the segmentation "
                "configuration; use the same immutable configuration for review and "
                "execution"
            )
        field_review = review_state.query(field_key)
        resolved = field_review.selection
    else:
        resolved = configuration.resolve(field_key)
    engine = active_registry.create_engine(resolved, field_review)
    return engine.segment(frame, context=context).require_frame_shape(frame)


def _kmeans_factory(
    profile: SegmentationProfile,
    provenance: SegmentationSelectionProvenance | None,
) -> SegmentationEngine:
    values = profile.parameters
    return KMeansMorphologySegmentationEngine(
        KMeansMorphologyConfig(
            clusters=_int(values, "clusters"),
            foreground_cluster_count=_int(values, "foreground_cluster_count"),
            foreground_boundary_relaxation_fraction=(
                _float(values, "foreground_boundary_relaxation_fraction")
                if "foreground_boundary_relaxation_fraction" in values
                else 0.0
            ),
            fit_max_pixels=_int(values, "fit_max_pixels"),
            n_init=_int(values, "n_init"),
            random_state=_int(values, "random_state"),
            opening_disk_radius=_int(values, "opening_disk_radius"),
            closing_disk_radius=_int(values, "closing_disk_radius"),
            fill_holes=_bool(values, "fill_holes"),
            minimum_object_area_pixels=_int(values, "minimum_object_area_pixels"),
            connectivity=_int(values, "connectivity"),
        ),
        profile.name,
        provenance,
    )


def _cellpose_factory(
    profile: SegmentationProfile,
    provenance: SegmentationSelectionProvenance | None,
) -> SegmentationEngine:
    values = profile.parameters
    return CellposeCPSamSegmentationEngine(
        CellposeCPSamConfig(
            pretrained_model=_str(values, "pretrained_model"),
            gpu=_bool(values, "gpu"),
            diameter=_optional_float(values, "diameter"),
            normalize=_bool(values, "normalize"),
            augment=_bool(values, "augment"),
            batch_size=_int(values, "batch_size"),
            resample=_bool(values, "resample"),
            flow_threshold=_float(values, "flow_threshold"),
            cellprob_threshold=_float(values, "cellprob_threshold"),
            minimum_object_area_pixels=_int(values, "minimum_object_area_pixels"),
            max_size_fraction=_float(values, "max_size_fraction"),
            tile_overlap=_float(values, "tile_overlap"),
            random_seed=_int(values, "random_seed"),
            torch_threads=_int(values, "torch_threads"),
        ),
        profile.name,
        provenance,
    )


def _watershed_factory(
    profile: SegmentationProfile,
    provenance: SegmentationSelectionProvenance | None,
) -> SegmentationEngine:
    values = profile.parameters
    return MarkerWatershedSegmentationEngine(
        MarkerWatershedConfig(
            gaussian_sigma_pixels=_float(values, "gaussian_sigma_pixels"),
            foreground_threshold_scale=_float(
                values, "foreground_threshold_scale"
            ),
            foreground_opening_disk_radius=_int(
                values, "foreground_opening_disk_radius"
            ),
            foreground_closing_disk_radius=_int(
                values, "foreground_closing_disk_radius"
            ),
            fill_holes=_bool(values, "fill_holes"),
            minimum_object_area_pixels=_int(values, "minimum_object_area_pixels"),
            marker_min_distance_pixels=_int(values, "marker_min_distance_pixels"),
            marker_exclude_border=_bool(values, "marker_exclude_border"),
            watershed_compactness=_float(values, "watershed_compactness"),
            connectivity=_int(values, "connectivity"),
        ),
        profile.name,
        provenance,
    )


def _otsu_factory(
    profile: SegmentationProfile,
    provenance: SegmentationSelectionProvenance | None,
) -> SegmentationEngine:
    values = profile.parameters
    return OtsuMorphologySegmentationEngine(
        OtsuMorphologyConfig(
            gaussian_sigma_pixels=_float(values, "gaussian_sigma_pixels"),
            threshold_scale=_float(values, "threshold_scale"),
            opening_disk_radius=_int(values, "opening_disk_radius"),
            closing_disk_radius=_int(values, "closing_disk_radius"),
            erosion_disk_radius=_int(values, "erosion_disk_radius"),
            dilation_disk_radius=_int(values, "dilation_disk_radius"),
            fill_holes=_bool(values, "fill_holes"),
            minimum_object_area_pixels=_int(values, "minimum_object_area_pixels"),
            connectivity=_int(values, "connectivity"),
        ),
        profile.name,
        provenance,
    )


def _p99_factory(
    profile: SegmentationProfile,
    provenance: SegmentationSelectionProvenance | None,
) -> SegmentationEngine:
    return PercentileThresholdSegmentationEngine(
        PercentileThresholdSegmentationConfig(
            threshold_percentile=_float(profile.parameters, "threshold_percentile"),
            connectivity=_int(profile.parameters, "connectivity"),
        ),
        profile=profile.name,
        selection=provenance,
    )


DEFAULT_SEGMENTATION_REGISTRY = SegmentationEngineRegistry(
    methods=(
        SegmentationMethodDescriptor(
            SegmentationMethodId.KMEANS,
            "K-means + morphological cleanup",
        ),
        SegmentationMethodDescriptor(
            SegmentationMethodId.CELLPOSE_CPSAM,
            "Cellpose CP-SAM",
            optional_dependency=True,
            note=CELLPOSE_CPU_WARNING,
        ),
        SegmentationMethodDescriptor(
            SegmentationMethodId.MARKER_WATERSHED,
            "Reproducible marker watershed",
        ),
        SegmentationMethodDescriptor(
            SegmentationMethodId.OTSU_GLOBAL,
            "Global Otsu + morphological cleanup",
        ),
        SegmentationMethodDescriptor(
            SegmentationMethodId.CONTROL_P99,
            "P99 + connected components (control/fallback)",
            note="Explicit control/fallback; not a recommended whole-cell method.",
        ),
    ),
    profiles=REGISTERED_SEGMENTATION_PROFILES,
    factories={
        SegmentationMethodId.KMEANS: _kmeans_factory,
        SegmentationMethodId.CELLPOSE_CPSAM: _cellpose_factory,
        SegmentationMethodId.MARKER_WATERSHED: _watershed_factory,
        SegmentationMethodId.OTSU_GLOBAL: _otsu_factory,
        SegmentationMethodId.CONTROL_P99: _p99_factory,
    },
)


def _int(values: Mapping[str, MetadataValue], name: str) -> int:
    value = values[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"profile parameter '{name}' must be an int")
    return value


def _float(values: Mapping[str, MetadataValue], name: str) -> float:
    value = values[name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"profile parameter '{name}' must be numeric")
    return float(value)


def _optional_float(values: Mapping[str, MetadataValue], name: str) -> float | None:
    value = values[name]
    return None if value is None else _float(values, name)


def _bool(values: Mapping[str, MetadataValue], name: str) -> bool:
    value = values[name]
    if not isinstance(value, bool):
        raise TypeError(f"profile parameter '{name}' must be a bool")
    return value


def _str(values: Mapping[str, MetadataValue], name: str) -> str:
    value = values[name]
    if not isinstance(value, str) or not value:
        raise TypeError(f"profile parameter '{name}' must be a non-empty string")
    return cast(str, value)
