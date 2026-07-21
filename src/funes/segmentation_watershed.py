"""Reproducible marker-watershed segmentation engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from .contracts import MetadataValue
from .segmentation_classical_common import (
    classical_unavailable,
    remove_small_binary_objects,
    remove_small_labels,
    roi_count,
    scientific_image_dependencies,
    segmentation_result,
    validate_connectivity,
    validate_positive,
    validate_radius,
)
from .segmentation_engine import (
    SegmentationEngineRecord,
    SegmentationResult,
    _installed_package_versions,
    _validated_float_frame,
)
from .segmentation_selection import SegmentationMethodId, SegmentationSelectionProvenance


@dataclass(frozen=True, slots=True)
class MarkerWatershedConfig:
    gaussian_sigma_pixels: float = 1.5
    foreground_threshold_scale: float = 1.0
    foreground_opening_disk_radius: int = 1
    foreground_closing_disk_radius: int = 3
    fill_holes: bool = True
    minimum_object_area_pixels: int = 64
    marker_min_distance_pixels: int = 12
    marker_exclude_border: bool = False
    watershed_compactness: float = 0.0
    connectivity: int = 2

    def __post_init__(self) -> None:
        if self.gaussian_sigma_pixels < 0:
            raise ValueError("gaussian_sigma_pixels must be zero or greater")
        if self.foreground_threshold_scale <= 0:
            raise ValueError("foreground_threshold_scale must be greater than zero")
        validate_radius(
            self.foreground_opening_disk_radius, "foreground_opening_disk_radius"
        )
        validate_radius(
            self.foreground_closing_disk_radius, "foreground_closing_disk_radius"
        )
        validate_positive(self.minimum_object_area_pixels, "minimum_object_area_pixels")
        validate_positive(self.marker_min_distance_pixels, "marker_min_distance_pixels")
        if self.watershed_compactness < 0:
            raise ValueError("watershed_compactness must be zero or greater")
        validate_connectivity(self.connectivity)


@dataclass(frozen=True, slots=True)
class MarkerWatershedSegmentationEngine:
    config: MarkerWatershedConfig = field(default_factory=MarkerWatershedConfig)
    profile: str | None = None
    selection: SegmentationSelectionProvenance | None = None

    @property
    def record(self) -> SegmentationEngineRecord:
        return self._record()

    def _record(
        self,
        threshold: float | None = None,
        base_otsu_threshold: float | None = None,
        marker_count: int | None = None,
    ) -> SegmentationEngineRecord:
        parameters: dict[str, MetadataValue] = {
            "gaussian_sigma_pixels": self.config.gaussian_sigma_pixels,
            "foreground_threshold": "global_otsu",
            "foreground_threshold_scale": self.config.foreground_threshold_scale,
            "foreground_opening_disk_radius": self.config.foreground_opening_disk_radius,
            "foreground_closing_disk_radius": self.config.foreground_closing_disk_radius,
            "fill_holes": self.config.fill_holes,
            "minimum_object_area_pixels": self.config.minimum_object_area_pixels,
            "distance_transform": "euclidean",
            "marker_strategy": "local_maxima_of_distance_transform",
            "marker_min_distance_pixels": self.config.marker_min_distance_pixels,
            "marker_exclude_border": self.config.marker_exclude_border,
            "watershed_surface": "negative_distance",
            "watershed_mask": "cleaned_otsu_foreground",
            "watershed_compactness": self.config.watershed_compactness,
            "connectivity": self.config.connectivity,
            "postprocessing": "remove_small_labels;canonicalize_labels",
        }
        if threshold is not None:
            parameters["threshold_value"] = threshold
        if base_otsu_threshold is not None:
            parameters["base_otsu_threshold_value"] = base_otsu_threshold
        if marker_count is not None:
            parameters["marker_count"] = marker_count
        return SegmentationEngineRecord(
            name="marker_watershed",
            version="1.0",
            model="distance_transform_marker_watershed",
            method=SegmentationMethodId.MARKER_WATERSHED,
            profile=self.profile,
            selection=self.selection,
            parameters=parameters,
            package_versions=_installed_package_versions(
                "funes", "numpy", "scipy", "scikit-image"
            ),
        )

    def segment(
        self,
        frame: NDArray[np.generic],
        context: Mapping[str, MetadataValue] | None = None,
    ) -> SegmentationResult:
        values = _validated_float_frame(frame)
        filters, measure, morphology, ndi = scientific_image_dependencies(
            SegmentationMethodId.MARKER_WATERSHED
        )
        try:
            from skimage import feature, segmentation
        except ImportError as exc:
            raise classical_unavailable(SegmentationMethodId.MARKER_WATERSHED) from exc
        smooth = filters.gaussian(
            values, sigma=self.config.gaussian_sigma_pixels, preserve_range=True
        )
        base_otsu_threshold = float(filters.threshold_otsu(smooth))
        threshold = base_otsu_threshold * self.config.foreground_threshold_scale
        mask = smooth > threshold
        mask = morphology.opening(
            mask, morphology.disk(self.config.foreground_opening_disk_radius)
        )
        mask = morphology.closing(
            mask, morphology.disk(self.config.foreground_closing_disk_radius)
        )
        if self.config.fill_holes:
            mask = ndi.binary_fill_holes(mask)
        mask = remove_small_binary_objects(
            mask,
            self.config.minimum_object_area_pixels,
            self.config.connectivity,
            measure,
        )
        distance = ndi.distance_transform_edt(mask)
        coordinates = feature.peak_local_max(
            distance,
            min_distance=self.config.marker_min_distance_pixels,
            labels=mask,
            exclude_border=self.config.marker_exclude_border,
        )
        markers = np.zeros(mask.shape, dtype=np.int32)
        for marker_id, (row, column) in enumerate(coordinates, start=1):
            markers[int(row), int(column)] = marker_id
        if len(coordinates) == 0 and np.any(mask):
            markers = measure.label(mask, connectivity=self.config.connectivity).astype(np.int32)
        labels = segmentation.watershed(
            -distance,
            markers=markers,
            mask=mask,
            compactness=self.config.watershed_compactness,
        ).astype(np.int32)
        labels = remove_small_labels(labels, self.config.minimum_object_area_pixels)
        return segmentation_result(
            labels,
            roi_count(labels),
            self._record(threshold, base_otsu_threshold, int(np.max(markers))),
            context,
        )
