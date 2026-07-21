"""D068 local-P20 K-means candidate and immutable synthetic audit trace."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math
from types import MappingProxyType
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from .contracts import MetadataValue
from .segmentation_benchmark import SegmentationBenchmarkVariant
from .segmentation_classical_common import (
    roi_count,
    scientific_image_dependencies,
    segmentation_result,
)
from .segmentation_engine import SegmentationResult, _validated_float_frame
from .segmentation_kmeans import (
    KMeansMorphologyConfig,
    KMeansMorphologySegmentationEngine,
    _fit_kmeans_intensity,
    _labels_from_raw_foreground,
)
from .segmentation_profile_catalog import BENCHMARK_BASELINE_PROFILES
from .segmentation_selection import SegmentationMethodId


LOCAL_BACKGROUND_CONTROL_MODE = "none"
LOCAL_BACKGROUND_P20_MODE = "local_background_p20"
KMEANS_LOCAL_BACKGROUND_ORIGIN = (
    "module7_kmeans_local_background_causal_candidate_20260719"
)
KMEANS_LOCAL_BACKGROUND_STATUS = (
    "implemented_synthetic_only_not_real_data_or_accuracy_validated"
)
LOCAL_BACKGROUND_PERCENTILE = 20.0
LOCAL_BACKGROUND_PERCENTILE_METHOD = "linear"
LOCAL_BACKGROUND_PADDING = "numpy_reflect_no_edge_repeat"
LOCAL_BACKGROUND_WINDOW_RULE = "2 * floor(min(height, width) / 8) + 1"


class _LocalBackgroundExecutionScope(str, Enum):
    """Internal provenance scopes; the public D069 runner exposes only DIRECT."""

    DIRECT_D069_SYNTHETIC = "direct_d069_synthetic_verification"
    D071_PACKAGE_SYNTHETIC = "d071_package_boundary_synthetic_verification"
    D071_AUTHORIZED_REAL_REVIEW = "d071_authorized_real_review"


@dataclass(frozen=True, slots=True)
class _D071PackageRunnerContext:
    """Typed package-only provenance that cannot be passed to the public runner."""

    execution_scope: _LocalBackgroundExecutionScope
    authorization_id: str
    authorization_scope: str

    def __post_init__(self) -> None:
        if self.execution_scope not in (
            _LocalBackgroundExecutionScope.D071_PACKAGE_SYNTHETIC,
            _LocalBackgroundExecutionScope.D071_AUTHORIZED_REAL_REVIEW,
        ):
            raise ValueError("D071 package context requires a package execution scope")
        if not self.authorization_id.strip() or not self.authorization_scope.strip():
            raise ValueError("D071 package authorization provenance must be non-empty")


def _reference_parameters() -> Mapping[str, MetadataValue]:
    baseline = next(
        profile
        for profile in BENCHMARK_BASELINE_PROFILES
        if profile.method is SegmentationMethodId.KMEANS
    )
    parameters = dict(baseline.parameters)
    parameters["minimum_object_area_pixels"] = 32
    parameters["foreground_boundary_relaxation_fraction"] = 0.0
    parameters["foreground_spatial_conditioning"] = LOCAL_BACKGROUND_CONTROL_MODE
    return MappingProxyType(parameters)


KMEANS_LOCAL_BACKGROUND_REFERENCE_PARAMETERS = _reference_parameters()


def build_kmeans_local_background_variants(
) -> tuple[SegmentationBenchmarkVariant, ...]:
    """Return exactly the single D068 mode switch relative to K area 32."""

    effective = dict(KMEANS_LOCAL_BACKGROUND_REFERENCE_PARAMETERS)
    effective["foreground_spatial_conditioning"] = LOCAL_BACKGROUND_P20_MODE
    return (
        SegmentationBenchmarkVariant(
            method=SegmentationMethodId.KMEANS,
            variant_id="causal_candidate__foreground_spatial_conditioning__local_background_p20",
            effective_parameters=effective,
            changed_parameter="foreground_spatial_conditioning",
            baseline_value=LOCAL_BACKGROUND_CONTROL_MODE,
            candidate_value=LOCAL_BACKGROUND_P20_MODE,
            origin=KMEANS_LOCAL_BACKGROUND_ORIGIN,
            status=KMEANS_LOCAL_BACKGROUND_STATUS,
        ),
    )


KMEANS_LOCAL_BACKGROUND_VARIANTS = build_kmeans_local_background_variants()


RAW_TOPOLOGY_CLASSES = frozenset(
    {"detached_proposal", "single_anchor_proposal", "multi_anchor_proposal"}
)
FINAL_TOPOLOGY_CLASSES = frozenset(
    {
        "de_novo_final_candidate",
        "existing_object_expansion",
        "unchanged_or_carried_object",
        "bridge_candidate",
    }
)


@dataclass(frozen=True, slots=True)
class KMeansLocalBackgroundComponent:
    """One geometric raw-proposal or final-label relation; never a cell call."""

    stage: str
    component_id: int
    area_pixels: int
    bounding_box_yx_half_open: tuple[int, int, int, int]
    touched_raw_anchor_labels: tuple[int, ...] = ()
    overlapped_reference_labels: tuple[int, ...] = ()
    geometric_class: str = ""

    def __post_init__(self) -> None:
        if self.stage not in ("raw_added_support", "candidate_final_label"):
            raise ValueError("component stage must be raw_added_support or candidate_final_label")
        if self.component_id <= 0 or self.area_pixels <= 0:
            raise ValueError("component identifiers and areas must be positive")
        y0, x0, y1, x1 = self.bounding_box_yx_half_open
        if min(y0, x0) < 0 or y1 <= y0 or x1 <= x0:
            raise ValueError("component bounding box must be a valid half-open 2D box")
        raw_anchors = tuple(sorted({int(value) for value in self.touched_raw_anchor_labels}))
        overlaps = tuple(sorted({int(value) for value in self.overlapped_reference_labels}))
        if any(value <= 0 for value in (*raw_anchors, *overlaps)):
            raise ValueError("topology label identifiers must be positive")
        allowed = RAW_TOPOLOGY_CLASSES if self.stage == "raw_added_support" else FINAL_TOPOLOGY_CLASSES
        if self.geometric_class not in allowed:
            raise ValueError("geometric_class does not match the component stage")
        if self.stage == "raw_added_support" and overlaps:
            raise ValueError("raw proposal records cannot declare final-label overlaps")
        if self.stage == "candidate_final_label" and raw_anchors:
            raise ValueError("final-label records cannot declare raw anchors")
        object.__setattr__(self, "touched_raw_anchor_labels", raw_anchors)
        object.__setattr__(self, "overlapped_reference_labels", overlaps)


@dataclass(frozen=True, slots=True)
class KMeansLocalBackgroundTrace:
    """Immutable D068 fit, local-threshold, mask, and topology trace."""

    prepared_frame_sha256: str
    fit_sample_indices: NDArray[np.int64]
    original_cluster_centers: tuple[float, ...]
    ordered_cluster_centers: tuple[float, ...]
    selected_cluster_ids: tuple[int, ...]
    baseline_threshold: float
    field_p20: float
    local_percentile: float
    local_percentile_method: str
    local_window_side: int
    local_window_rule: str
    padding_rule: str
    local_p20: NDArray[np.float64]
    local_threshold_map: NDArray[np.float64]
    baseline_raw_foreground: NDArray[np.bool_]
    candidate_raw_foreground: NDArray[np.bool_]
    raw_added_support: NDArray[np.bool_]
    control_post_morphology_pre_area: NDArray[np.bool_]
    candidate_post_morphology_pre_area: NDArray[np.bool_]
    control_final_labels: NDArray[np.int32]
    candidate_final_labels: NDArray[np.int32]
    immutable_reference_labels: NDArray[np.int32]
    components: tuple[KMeansLocalBackgroundComponent, ...]
    stage_change_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        if len(self.prepared_frame_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.prepared_frame_sha256
        ):
            raise ValueError("prepared_frame_sha256 must be a SHA-256 hex digest")
        original_centers = tuple(float(value) for value in self.original_cluster_centers)
        ordered_centers = tuple(float(value) for value in self.ordered_cluster_centers)
        selected_ids = tuple(int(value) for value in self.selected_cluster_ids)
        if len(original_centers) != 3 or len(ordered_centers) != 3:
            raise ValueError("D068 requires exactly three K-means centers")
        if tuple(sorted(original_centers)) != ordered_centers:
            raise ValueError("ordered_cluster_centers must sort the original centers")
        if len(selected_ids) != 2 or len(set(selected_ids)) != 2 or any(
            value not in (0, 1, 2) for value in selected_ids
        ):
            raise ValueError("D068 requires two distinct highest-center cluster identifiers")
        expected_boundary = ordered_centers[0] + 0.5 * (
            ordered_centers[1] - ordered_centers[0]
        )
        if self.baseline_threshold != expected_boundary:
            raise ValueError("baseline_threshold must use the unchanged lowest-middle boundary")
        object.__setattr__(self, "original_cluster_centers", original_centers)
        object.__setattr__(self, "ordered_cluster_centers", ordered_centers)
        object.__setattr__(self, "selected_cluster_ids", selected_ids)
        if self.local_percentile != LOCAL_BACKGROUND_PERCENTILE:
            raise ValueError("D068 local percentile must remain exactly P20")
        if self.local_percentile_method != LOCAL_BACKGROUND_PERCENTILE_METHOD:
            raise ValueError("D068 percentile method must remain linear")
        if self.local_window_rule != LOCAL_BACKGROUND_WINDOW_RULE:
            raise ValueError("D068 local-window rule must remain unchanged")
        if self.padding_rule != LOCAL_BACKGROUND_PADDING:
            raise ValueError("D068 padding must remain NumPy-style reflection")
        if self.local_window_side <= 0 or self.local_window_side % 2 != 1:
            raise ValueError("local_window_side must be a positive odd integer")

        indices = np.array(self.fit_sample_indices, dtype=np.int64, copy=True)
        if indices.ndim != 1 or indices.size == 0 or np.any(indices < 0):
            raise ValueError("fit_sample_indices must be a non-empty nonnegative vector")
        indices.setflags(write=False)
        object.__setattr__(self, "fit_sample_indices", indices)

        shape: tuple[int, int] | None = None
        float_arrays = ("local_p20", "local_threshold_map")
        bool_arrays = (
            "baseline_raw_foreground",
            "candidate_raw_foreground",
            "raw_added_support",
            "control_post_morphology_pre_area",
            "candidate_post_morphology_pre_area",
        )
        int_arrays = (
            "control_final_labels",
            "candidate_final_labels",
            "immutable_reference_labels",
        )
        for name, dtype in (
            *((name, np.float64) for name in float_arrays),
            *((name, np.bool_) for name in bool_arrays),
            *((name, np.int32) for name in int_arrays),
        ):
            array = np.array(getattr(self, name), dtype=dtype, copy=True)
            if array.ndim != 2 or array.size == 0:
                raise ValueError(f"{name} must be a non-empty 2D array")
            if shape is None:
                shape = array.shape
            elif array.shape != shape:
                raise ValueError("all local-background trace arrays must share one shape")
            if np.issubdtype(array.dtype, np.integer) and np.any(array < 0):
                raise ValueError(f"{name} cannot contain negative labels")
            array.setflags(write=False)
            object.__setattr__(self, name, array)

        assert shape is not None
        if self.local_window_side != local_background_window_side(shape):
            raise ValueError("local_window_side does not match the D068 field-relative rule")
        if np.any(self.local_threshold_map > self.baseline_threshold):
            raise ValueError("local threshold cannot exceed the global baseline threshold")
        expected_threshold = self.baseline_threshold + np.minimum(
            0.0, self.local_p20 - self.field_p20
        )
        if not np.allclose(self.local_threshold_map, expected_threshold, rtol=0.0, atol=0.0):
            raise ValueError("local threshold map does not match the exact D068 arithmetic")
        if np.any(self.baseline_raw_foreground & ~self.candidate_raw_foreground):
            raise ValueError("candidate raw foreground must preserve all baseline support")
        expected_added = self.candidate_raw_foreground & ~self.baseline_raw_foreground
        if not np.array_equal(self.raw_added_support, expected_added):
            raise ValueError("raw_added_support must equal candidate minus baseline raw support")
        if np.any(self.raw_added_support & ~(self.local_p20 < self.field_p20)):
            raise ValueError("raw additions require local P20 strictly below field P20")
        if not np.array_equal(self.control_final_labels, self.immutable_reference_labels):
            raise ValueError("immutable reference labels must equal the exact area-32 control")
        if np.any((self.immutable_reference_labels > 0) & ~(self.candidate_final_labels > 0)):
            raise ValueError("candidate final support cannot remove immutable reference support")

        counts = {str(name): int(value) for name, value in self.stage_change_counts.items()}
        if any(value < 0 for value in counts.values()):
            raise ValueError("stage_change_counts values must be zero or greater")
        expected_counts = {
            "raw_added_pixels": int(np.count_nonzero(self.raw_added_support)),
            "raw_removed_pixels": int(
                np.count_nonzero(
                    self.baseline_raw_foreground & ~self.candidate_raw_foreground
                )
            ),
            "post_morphology_added_pixels": int(
                np.count_nonzero(
                    self.candidate_post_morphology_pre_area
                    & ~self.control_post_morphology_pre_area
                )
            ),
            "post_morphology_removed_pixels": int(
                np.count_nonzero(
                    self.control_post_morphology_pre_area
                    & ~self.candidate_post_morphology_pre_area
                )
            ),
            "final_added_pixels": int(
                np.count_nonzero(
                    (self.candidate_final_labels > 0)
                    & ~(self.immutable_reference_labels > 0)
                )
            ),
            "final_removed_pixels": int(
                np.count_nonzero(
                    (self.immutable_reference_labels > 0)
                    & ~(self.candidate_final_labels > 0)
                )
            ),
        }
        if counts != expected_counts:
            raise ValueError("stage_change_counts do not match the preserved trace arrays")
        for name in ("raw_removed_pixels", "post_morphology_removed_pixels", "final_removed_pixels"):
            if counts.get(name) != 0:
                raise ValueError(f"{name} must remain zero for the D068 union candidate")
        object.__setattr__(self, "stage_change_counts", MappingProxyType(counts))
        object.__setattr__(self, "components", tuple(self.components))


def local_background_window_side(shape: tuple[int, int]) -> int:
    """Return the exact D068 odd window side from a non-empty 2D shape."""

    if len(shape) != 2 or min(shape) <= 0:
        raise ValueError("shape must contain two positive dimensions")
    return 2 * math.floor(min(shape) / 8) + 1


def classify_local_background_topology(
    baseline_raw_foreground: NDArray[np.generic],
    candidate_raw_foreground: NDArray[np.generic],
    candidate_final_labels: NDArray[np.generic],
    immutable_reference_labels: NDArray[np.generic],
) -> tuple[KMeansLocalBackgroundComponent, ...]:
    """Classify D068 geometric relations without biological interpretation."""

    baseline = np.asarray(baseline_raw_foreground, dtype=bool)
    candidate = np.asarray(candidate_raw_foreground, dtype=bool)
    candidate_labels = _validated_label_image(candidate_final_labels, "candidate_final_labels")
    reference_labels = _validated_label_image(
        immutable_reference_labels, "immutable_reference_labels"
    )
    if baseline.ndim != 2 or baseline.size == 0:
        raise ValueError("baseline_raw_foreground must be a non-empty 2D mask")
    if candidate.shape != baseline.shape or candidate_labels.shape != baseline.shape or reference_labels.shape != baseline.shape:
        raise ValueError("all topology arrays must share one shape")
    if np.any(baseline & ~candidate):
        raise ValueError("candidate raw foreground must be a superset of baseline")

    _, measure, _, ndi = scientific_image_dependencies(SegmentationMethodId.KMEANS)
    structure = np.ones((3, 3), dtype=bool)
    baseline_components = measure.label(baseline, connectivity=2).astype(np.int32)
    added_components = measure.label(candidate & ~baseline, connectivity=2).astype(np.int32)
    records: list[KMeansLocalBackgroundComponent] = []

    for component_id in range(1, int(added_components.max()) + 1):
        component_mask = added_components == component_id
        touched = tuple(
            int(value)
            for value in np.unique(
                baseline_components[ndi.binary_dilation(component_mask, structure=structure)]
            )
            if value > 0
        )
        if not touched:
            geometric_class = "detached_proposal"
        elif len(touched) == 1:
            geometric_class = "single_anchor_proposal"
        else:
            geometric_class = "multi_anchor_proposal"
        records.append(
            _component_record(
                "raw_added_support",
                component_id,
                component_mask,
                touched_raw_anchor_labels=touched,
                geometric_class=geometric_class,
            )
        )

    for component_id in tuple(int(value) for value in np.unique(candidate_labels) if value > 0):
        component_mask = candidate_labels == component_id
        overlaps = tuple(
            int(value)
            for value in np.unique(reference_labels[component_mask])
            if value > 0
        )
        if not overlaps:
            geometric_class = "de_novo_final_candidate"
        elif len(overlaps) >= 2:
            geometric_class = "bridge_candidate"
        elif np.any(component_mask & ~(reference_labels == overlaps[0])):
            geometric_class = "existing_object_expansion"
        else:
            geometric_class = "unchanged_or_carried_object"
        records.append(
            _component_record(
                "candidate_final_label",
                component_id,
                component_mask,
                overlapped_reference_labels=overlaps,
                geometric_class=geometric_class,
            )
        )
    return tuple(records)


def run_kmeans_local_background_candidate(
    frame: NDArray[np.generic],
    immutable_reference_labels: NDArray[np.generic],
    variant: SegmentationBenchmarkVariant = KMEANS_LOCAL_BACKGROUND_VARIANTS[0],
    *,
    context: Mapping[str, MetadataValue] | None = None,
) -> tuple[SegmentationResult, KMeansLocalBackgroundTrace]:
    """Run D069 synthetically; real-review scope exists only at the D071 boundary."""

    return _run_kmeans_local_background_candidate(
        frame,
        immutable_reference_labels,
        variant,
        context=context,
        package_context=None,
    )


def _run_kmeans_local_background_candidate_for_d071(
    frame: NDArray[np.generic],
    immutable_reference_labels: NDArray[np.generic],
    variant: SegmentationBenchmarkVariant,
    *,
    package_context: _D071PackageRunnerContext,
    context: Mapping[str, MetadataValue] | None = None,
) -> tuple[SegmentationResult, KMeansLocalBackgroundTrace]:
    """Package-only D071 entry to the unchanged numerical D069 implementation."""

    if not isinstance(package_context, _D071PackageRunnerContext):
        raise TypeError("package_context must be a typed D071 package context")
    return _run_kmeans_local_background_candidate(
        frame,
        immutable_reference_labels,
        variant,
        context=context,
        package_context=package_context,
    )


def _run_kmeans_local_background_candidate(
    frame: NDArray[np.generic],
    immutable_reference_labels: NDArray[np.generic],
    variant: SegmentationBenchmarkVariant,
    *,
    context: Mapping[str, MetadataValue] | None,
    package_context: _D071PackageRunnerContext | None,
) -> tuple[SegmentationResult, KMeansLocalBackgroundTrace]:
    """Shared exact D069 calculation with explicit, closed provenance."""

    if variant not in KMEANS_LOCAL_BACKGROUND_VARIANTS:
        raise ValueError("local-background execution requires the unchanged D068 candidate")
    values = _validated_float_frame(frame)
    reference_labels = _validated_label_image(
        immutable_reference_labels, "immutable_reference_labels"
    )
    if reference_labels.shape != values.shape:
        raise ValueError("immutable_reference_labels must match the prepared frame shape")

    config = KMeansMorphologyConfig(
        clusters=3,
        foreground_cluster_count=2,
        foreground_boundary_relaxation_fraction=0.0,
        fit_max_pixels=100_000,
        n_init=10,
        random_state=1729,
        opening_disk_radius=1,
        closing_disk_radius=3,
        fill_holes=True,
        minimum_object_area_pixels=32,
        connectivity=2,
    )
    _, measure, morphology, ndi = scientific_image_dependencies(
        SegmentationMethodId.KMEANS
    )
    fit = _fit_kmeans_intensity(values, config)
    window_side = local_background_window_side(values.shape)
    field_p20 = float(np.percentile(values, LOCAL_BACKGROUND_PERCENTILE, method="linear"))
    local_p20 = _local_percentile_linear_reflect(
        values, LOCAL_BACKGROUND_PERCENTILE, window_side, ndi
    )
    local_threshold = fit.baseline_threshold + np.minimum(0.0, local_p20 - field_p20)
    negative_offset = local_p20 < field_p20
    candidate_raw = fit.baseline_raw_foreground | (
        negative_offset & (values > local_threshold)
    )
    raw_added = candidate_raw & ~fit.baseline_raw_foreground

    control_post, control_labels = _labels_from_raw_foreground(
        fit.baseline_raw_foreground, config, measure, morphology, ndi
    )
    candidate_post, candidate_labels = _labels_from_raw_foreground(
        candidate_raw, config, measure, morphology, ndi
    )
    if not np.array_equal(control_labels, reference_labels):
        raise ValueError(
            "immutable_reference_labels do not match the exact unchanged K area-32 control"
        )

    stage_counts = {
        "raw_added_pixels": int(np.count_nonzero(raw_added)),
        "raw_removed_pixels": int(
            np.count_nonzero(fit.baseline_raw_foreground & ~candidate_raw)
        ),
        "post_morphology_added_pixels": int(
            np.count_nonzero(candidate_post & ~control_post)
        ),
        "post_morphology_removed_pixels": int(
            np.count_nonzero(control_post & ~candidate_post)
        ),
        "final_added_pixels": int(
            np.count_nonzero((candidate_labels > 0) & ~(reference_labels > 0))
        ),
        "final_removed_pixels": int(
            np.count_nonzero((reference_labels > 0) & ~(candidate_labels > 0))
        ),
    }
    if any(
        stage_counts[name] != 0
        for name in (
            "raw_removed_pixels",
            "post_morphology_removed_pixels",
            "final_removed_pixels",
        )
    ):
        raise RuntimeError("D068 union candidate violated a no-removal invariant")

    components = classify_local_background_topology(
        fit.baseline_raw_foreground,
        candidate_raw,
        candidate_labels,
        reference_labels,
    )
    engine = KMeansMorphologySegmentationEngine(config, profile=variant.variant_id)
    execution_scope = (
        _LocalBackgroundExecutionScope.DIRECT_D069_SYNTHETIC
        if package_context is None
        else package_context.execution_scope
    )
    synthetic_only = execution_scope is not _LocalBackgroundExecutionScope.D071_AUTHORIZED_REAL_REVIEW
    record_parameters: dict[str, MetadataValue] = {
        "foreground_spatial_conditioning": LOCAL_BACKGROUND_P20_MODE,
        "local_background_percentile": LOCAL_BACKGROUND_PERCENTILE,
        "local_background_percentile_method": LOCAL_BACKGROUND_PERCENTILE_METHOD,
        "local_background_window_rule": LOCAL_BACKGROUND_WINDOW_RULE,
        "local_background_window_side": window_side,
        "local_background_padding": LOCAL_BACKGROUND_PADDING,
        "field_background_p20": field_p20,
        "cluster_centers": ",".join(
            f"{float(value):.17g}" for value in fit.original_cluster_centers
        ),
        "ordered_cluster_centers": ",".join(
            f"{float(value):.17g}" for value in fit.ordered_cluster_centers
        ),
        "selected_cluster_ids": ",".join(
            str(int(value)) for value in fit.foreground_cluster_ids
        ),
        "fit_pixel_count": int(fit.fit_sample_indices.size),
        "foreground_baseline_threshold": fit.baseline_threshold,
        "execution_scope": execution_scope.value,
        "synthetic_verification_only": synthetic_only,
    }
    if package_context is not None:
        record_parameters.update(
            {
                "d071_authorization_id": package_context.authorization_id,
                "d071_authorization_scope": package_context.authorization_scope,
            }
        )
    record = engine._record(
        record_parameters
    )
    result = segmentation_result(
        candidate_labels,
        roi_count(candidate_labels),
        record,
        {
            **dict(context or {}),
            "segmentation_causal_variant": variant.variant_id,
            "segmentation_causal_origin": variant.origin,
            "synthetic_verification_only": synthetic_only,
            "execution_scope": execution_scope.value,
            **(
                {}
                if package_context is None
                else {
                    "d071_authorization_id": package_context.authorization_id,
                    "d071_authorization_scope": package_context.authorization_scope,
                }
            ),
        },
    )
    trace = KMeansLocalBackgroundTrace(
        prepared_frame_sha256=hashlib.sha256(values.tobytes(order="C")).hexdigest(),
        fit_sample_indices=fit.fit_sample_indices,
        original_cluster_centers=tuple(float(value) for value in fit.original_cluster_centers),
        ordered_cluster_centers=tuple(float(value) for value in fit.ordered_cluster_centers),
        selected_cluster_ids=tuple(int(value) for value in fit.foreground_cluster_ids),
        baseline_threshold=fit.baseline_threshold,
        field_p20=field_p20,
        local_percentile=LOCAL_BACKGROUND_PERCENTILE,
        local_percentile_method=LOCAL_BACKGROUND_PERCENTILE_METHOD,
        local_window_side=window_side,
        local_window_rule=LOCAL_BACKGROUND_WINDOW_RULE,
        padding_rule=LOCAL_BACKGROUND_PADDING,
        local_p20=local_p20,
        local_threshold_map=local_threshold,
        baseline_raw_foreground=fit.baseline_raw_foreground,
        candidate_raw_foreground=candidate_raw,
        raw_added_support=raw_added,
        control_post_morphology_pre_area=control_post,
        candidate_post_morphology_pre_area=candidate_post,
        control_final_labels=control_labels,
        candidate_final_labels=candidate_labels,
        immutable_reference_labels=reference_labels,
        components=components,
        stage_change_counts=stage_counts,
    )
    return result, trace


def _local_percentile_linear_reflect(
    values: NDArray[np.float64],
    percentile: float,
    window_side: int,
    ndi: object,
) -> NDArray[np.float64]:
    """Exact NumPy-linear local percentile via interpolated rank filters."""

    sample_count = window_side * window_side
    # Match NumPy's type-7/``linear`` virtual-index arithmetic exactly.
    rank_position = (sample_count - 1) * (percentile / 100.0)
    lower_rank = math.floor(rank_position)
    upper_rank = math.ceil(rank_position)
    lower = np.asarray(
        ndi.rank_filter(values, lower_rank, size=window_side, mode="mirror"),
        dtype=np.float64,
    )
    if upper_rank == lower_rank:
        return lower
    upper = np.asarray(
        ndi.rank_filter(values, upper_rank, size=window_side, mode="mirror"),
        dtype=np.float64,
    )
    fraction = rank_position - lower_rank
    difference = upper - lower
    if fraction < 0.5:
        return lower + difference * fraction
    return upper - difference * (1.0 - fraction)


def _validated_label_image(
    labels: NDArray[np.generic], field_name: str
) -> NDArray[np.int32]:
    source = np.asarray(labels)
    if source.ndim != 2 or source.size == 0:
        raise ValueError(f"{field_name} must be a non-empty 2D label image")
    if not np.issubdtype(source.dtype, np.integer):
        raise TypeError(f"{field_name} must use an integer dtype")
    if np.any(source < 0):
        raise ValueError(f"{field_name} cannot contain negative labels")
    return np.asarray(source, dtype=np.int32)


def _component_record(
    stage: str,
    component_id: int,
    component_mask: NDArray[np.bool_],
    *,
    touched_raw_anchor_labels: tuple[int, ...] = (),
    overlapped_reference_labels: tuple[int, ...] = (),
    geometric_class: str,
) -> KMeansLocalBackgroundComponent:
    rows, columns = np.nonzero(component_mask)
    return KMeansLocalBackgroundComponent(
        stage=stage,
        component_id=component_id,
        area_pixels=int(rows.size),
        bounding_box_yx_half_open=(
            int(rows.min()),
            int(columns.min()),
            int(rows.max()) + 1,
            int(columns.max()) + 1,
        ),
        touched_raw_anchor_labels=touched_raw_anchor_labels,
        overlapped_reference_labels=overlapped_reference_labels,
        geometric_class=geometric_class,
    )
