"""Seeded K-means plus morphology segmentation engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from .contracts import MetadataValue
from .segmentation_classical_common import (
    canonicalize_labels,
    remove_small_binary_objects,
    roi_count,
    scientific_image_dependencies,
    segmentation_result,
    validate_connectivity,
    validate_positive,
    validate_radius,
)
from .segmentation_engine import (
    SegmentationEngineRecord,
    SegmentationEngineUnavailableError,
    SegmentationResult,
    _installed_package_versions,
    _validated_float_frame,
)
from .segmentation_selection import SegmentationMethodId, SegmentationSelectionProvenance


@dataclass(frozen=True, slots=True)
class KMeansMorphologyConfig:
    clusters: int = 3
    foreground_cluster_count: int = 2
    foreground_boundary_relaxation_fraction: float = 0.0
    fit_max_pixels: int = 100_000
    n_init: int = 10
    random_state: int = 1729
    opening_disk_radius: int = 1
    closing_disk_radius: int = 3
    fill_holes: bool = True
    minimum_object_area_pixels: int = 64
    connectivity: int = 2

    def __post_init__(self) -> None:
        if self.clusters < 2:
            raise ValueError("clusters must be at least 2")
        if not 1 <= self.foreground_cluster_count < self.clusters:
            raise ValueError("foreground_cluster_count must be within 1..clusters-1")
        relaxation = self.foreground_boundary_relaxation_fraction
        if (
            isinstance(relaxation, bool)
            or not isinstance(relaxation, (int, float))
            or not np.isfinite(relaxation)
            or not 0.0 <= float(relaxation) < 1.0
        ):
            raise ValueError(
                "foreground_boundary_relaxation_fraction must be finite within 0.0..1.0, "
                "excluding 1.0"
            )
        validate_positive(self.fit_max_pixels, "fit_max_pixels")
        validate_positive(self.n_init, "n_init")
        validate_radius(self.opening_disk_radius, "opening_disk_radius")
        validate_radius(self.closing_disk_radius, "closing_disk_radius")
        validate_positive(self.minimum_object_area_pixels, "minimum_object_area_pixels")
        validate_connectivity(self.connectivity)


@dataclass(frozen=True, slots=True)
class KMeansForegroundDiagnosticTrace:
    """Immutable selection and morphology trace for the D062 diagnostic factor."""

    ordered_cluster_centers: tuple[float, ...]
    baseline_threshold: float
    candidate_threshold: float
    relaxation_fraction: float
    baseline_raw_foreground: NDArray[np.bool_]
    relaxed_raw_foreground: NDArray[np.bool_]
    raw_added_support: NDArray[np.bool_]
    baseline_post_morphology_pre_area: NDArray[np.bool_]
    post_morphology_pre_area: NDArray[np.bool_]
    stage_change_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        centers = tuple(float(value) for value in self.ordered_cluster_centers)
        if len(centers) < 2 or any(
            left > right for left, right in zip(centers, centers[1:])
        ):
            raise ValueError("ordered_cluster_centers must contain at least two ordered values")
        object.__setattr__(self, "ordered_cluster_centers", centers)
        masks = (
            "baseline_raw_foreground",
            "relaxed_raw_foreground",
            "raw_added_support",
            "baseline_post_morphology_pre_area",
            "post_morphology_pre_area",
        )
        shape: tuple[int, ...] | None = None
        for name in masks:
            mask = np.array(getattr(self, name), dtype=bool, copy=True)
            if mask.ndim != 2 or mask.size == 0:
                raise ValueError(f"{name} must be a non-empty 2D mask")
            if shape is not None and mask.shape != shape:
                raise ValueError("all diagnostic trace masks must have the same shape")
            shape = mask.shape
            mask.setflags(write=False)
            object.__setattr__(self, name, mask)
        if np.any(self.baseline_raw_foreground & ~self.relaxed_raw_foreground):
            raise ValueError("relaxed raw foreground must be a superset of baseline raw foreground")
        expected_added = self.relaxed_raw_foreground & ~self.baseline_raw_foreground
        if not np.array_equal(self.raw_added_support, expected_added):
            raise ValueError("raw_added_support must equal relaxed minus baseline raw support")
        counts = {str(name): int(value) for name, value in self.stage_change_counts.items()}
        if any(value < 0 for value in counts.values()):
            raise ValueError("stage_change_counts values must be zero or greater")
        object.__setattr__(self, "stage_change_counts", MappingProxyType(counts))


@dataclass(frozen=True, slots=True)
class _KMeansIntensityFit:
    """Shared deterministic fit state used by Module 7 diagnostic branches."""

    cluster_labels: NDArray[np.int32]
    original_cluster_centers: NDArray[np.float64]
    ordered_cluster_centers: NDArray[np.float64]
    foreground_cluster_ids: NDArray[np.int64]
    fit_sample_indices: NDArray[np.int64]
    baseline_raw_foreground: NDArray[np.bool_]
    baseline_threshold: float


@dataclass(frozen=True, slots=True)
class KMeansMorphologySegmentationEngine:
    config: KMeansMorphologyConfig = field(default_factory=KMeansMorphologyConfig)
    profile: str | None = None
    selection: SegmentationSelectionProvenance | None = None

    @property
    def record(self) -> SegmentationEngineRecord:
        return self._record()

    def _record(
        self,
        observed: Mapping[str, MetadataValue] | None = None,
    ) -> SegmentationEngineRecord:
        parameters: dict[str, MetadataValue] = {
            "clusters": self.config.clusters,
            "foreground_cluster_count": self.config.foreground_cluster_count,
            "foreground_clusters": f"{self.config.foreground_cluster_count}_highest_centers",
            "foreground_boundary_relaxation_fraction": (
                self.config.foreground_boundary_relaxation_fraction
            ),
            "fit_sampling": "evenly_spaced_flat_indices",
            "fit_max_pixels": self.config.fit_max_pixels,
            "n_init": self.config.n_init,
            "algorithm": "lloyd",
            "opening_disk_radius": self.config.opening_disk_radius,
            "closing_disk_radius": self.config.closing_disk_radius,
            "fill_holes": self.config.fill_holes,
            "minimum_object_area_pixels": self.config.minimum_object_area_pixels,
            "connectivity": self.config.connectivity,
            "postprocessing": "opening;closing;fill_holes;remove_small_objects;connected_components",
        }
        parameters.update(observed or {})
        return SegmentationEngineRecord(
            name="kmeans_morphology",
            version="1.0",
            model="scikit_learn_kmeans_intensity_clusters",
            method=SegmentationMethodId.KMEANS,
            profile=self.profile,
            selection=self.selection,
            parameters=parameters,
            seeds={"random_state": self.config.random_state},
            package_versions=_installed_package_versions(
                "funes", "numpy", "scipy", "scikit-image", "scikit-learn"
            ),
        )

    def segment(
        self,
        frame: NDArray[np.generic],
        context: Mapping[str, MetadataValue] | None = None,
    ) -> SegmentationResult:
        result, _ = self._segment(frame, context=context, include_trace=False)
        return result

    def segment_with_diagnostic_trace(
        self,
        frame: NDArray[np.generic],
        context: Mapping[str, MetadataValue] | None = None,
    ) -> tuple[SegmentationResult, KMeansForegroundDiagnosticTrace]:
        """Segment once and expose the D062-only diagnostic trace."""

        result, trace = self._segment(frame, context=context, include_trace=True)
        assert trace is not None
        return result, trace

    def _segment(
        self,
        frame: NDArray[np.generic],
        *,
        context: Mapping[str, MetadataValue] | None,
        include_trace: bool,
    ) -> tuple[SegmentationResult, KMeansForegroundDiagnosticTrace | None]:
        values = _validated_float_frame(frame)
        _, measure, morphology, ndi = scientific_image_dependencies(
            SegmentationMethodId.KMEANS
        )
        fit = _fit_kmeans_intensity(values, self.config)
        centers = fit.original_cluster_centers
        foreground_ids = fit.foreground_cluster_ids
        baseline_raw = fit.baseline_raw_foreground
        ordered_centers = fit.ordered_cluster_centers
        baseline_threshold = fit.baseline_threshold
        relaxation = float(self.config.foreground_boundary_relaxation_fraction)
        candidate_threshold = float(
            baseline_threshold - relaxation * (baseline_threshold - ordered_centers[0])
        )
        if relaxation == 0.0:
            relaxed_raw = baseline_raw.copy()
        else:
            relaxed_raw = baseline_raw | (values > candidate_threshold)

        post_morphology_pre_area, labels = _labels_from_raw_foreground(
            relaxed_raw, self.config, measure, morphology, ndi
        )
        baseline_post_morphology = (
            _apply_morphology(baseline_raw, self.config, morphology, ndi)
            if include_trace
            else None
        )
        record = self._record(
            {
                "cluster_centers": ",".join(f"{float(value):.17g}" for value in centers),
                "ordered_cluster_centers": ",".join(
                    f"{float(value):.17g}" for value in ordered_centers
                ),
                "selected_cluster_ids": ",".join(str(int(value)) for value in foreground_ids),
                "fit_pixel_count": int(fit.fit_sample_indices.size),
                "foreground_baseline_threshold": baseline_threshold,
                "foreground_candidate_threshold": candidate_threshold,
            }
        )
        result = segmentation_result(labels, roi_count(labels), record, context)
        if not include_trace:
            return result, None
        assert baseline_post_morphology is not None
        raw_added = relaxed_raw & ~baseline_raw
        trace = KMeansForegroundDiagnosticTrace(
            ordered_cluster_centers=tuple(float(value) for value in ordered_centers),
            baseline_threshold=baseline_threshold,
            candidate_threshold=candidate_threshold,
            relaxation_fraction=relaxation,
            baseline_raw_foreground=baseline_raw,
            relaxed_raw_foreground=relaxed_raw,
            raw_added_support=raw_added,
            baseline_post_morphology_pre_area=baseline_post_morphology,
            post_morphology_pre_area=post_morphology_pre_area,
            stage_change_counts={
                "raw_added_pixels": int(np.count_nonzero(raw_added)),
                "raw_removed_pixels": int(np.count_nonzero(baseline_raw & ~relaxed_raw)),
                "post_morphology_added_pixels": int(
                    np.count_nonzero(post_morphology_pre_area & ~baseline_post_morphology)
                ),
                "post_morphology_removed_pixels": int(
                    np.count_nonzero(baseline_post_morphology & ~post_morphology_pre_area)
                ),
            },
        )
        return result, trace


def _fit_kmeans_intensity(
    values: NDArray[np.float64],
    config: KMeansMorphologyConfig,
) -> _KMeansIntensityFit:
    """Fit the unchanged deterministic K-means intensity model once."""

    try:
        from sklearn.cluster import KMeans
    except ImportError as exc:
        raise SegmentationEngineUnavailableError(
            SegmentationMethodId.KMEANS,
            "scikit-learn is not installed",
            "Install the declared FUNES production dependencies (for example, 'pip install -e .').",
        ) from exc
    flattened = values.reshape(-1, 1)
    sample_count = min(flattened.shape[0], config.fit_max_pixels)
    sample_indices = np.linspace(
        0, flattened.shape[0] - 1, sample_count, dtype=np.int64
    )
    estimator = KMeans(
        n_clusters=config.clusters,
        n_init=config.n_init,
        random_state=config.random_state,
        algorithm="lloyd",
    )
    estimator.fit(flattened[sample_indices])
    cluster_labels = estimator.predict(flattened).reshape(values.shape).astype(np.int32)
    centers = estimator.cluster_centers_.reshape(-1).astype(np.float64)
    foreground_ids = np.argsort(centers)[-config.foreground_cluster_count :].astype(
        np.int64
    )
    baseline_raw = np.isin(cluster_labels, foreground_ids)
    ordered_centers = np.sort(centers)
    baseline_threshold = float(
        ordered_centers[0] + 0.5 * (ordered_centers[1] - ordered_centers[0])
    )
    return _KMeansIntensityFit(
        cluster_labels=cluster_labels,
        original_cluster_centers=centers,
        ordered_cluster_centers=ordered_centers,
        foreground_cluster_ids=foreground_ids,
        fit_sample_indices=sample_indices,
        baseline_raw_foreground=baseline_raw,
        baseline_threshold=baseline_threshold,
    )


def _labels_from_raw_foreground(
    raw_foreground: NDArray[np.bool_],
    config: KMeansMorphologyConfig,
    measure: object,
    morphology: object,
    ndi: object,
) -> tuple[NDArray[np.bool_], NDArray[np.int32]]:
    """Apply the unchanged morphology, area filter, and canonical labeling."""

    post_morphology_pre_area = _apply_morphology(
        raw_foreground, config, morphology, ndi
    )
    filtered = remove_small_binary_objects(
        post_morphology_pre_area,
        config.minimum_object_area_pixels,
        config.connectivity,
        measure,
    )
    labels = canonicalize_labels(
        measure.label(filtered, connectivity=config.connectivity).astype(np.int32)
    )
    return post_morphology_pre_area, labels


def _apply_morphology(
    mask: NDArray[np.bool_],
    config: KMeansMorphologyConfig,
    morphology: object,
    ndi: object,
) -> NDArray[np.bool_]:
    result = morphology.opening(mask, morphology.disk(config.opening_disk_radius))
    result = morphology.closing(result, morphology.disk(config.closing_disk_radius))
    if config.fill_holes:
        result = ndi.binary_fill_holes(result)
    return np.asarray(result, dtype=bool)
