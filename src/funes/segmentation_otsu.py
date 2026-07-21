"""Global Otsu plus morphology segmentation engine."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    SegmentationResult,
    _installed_package_versions,
    _validated_float_frame,
)
from .segmentation_selection import SegmentationMethodId, SegmentationSelectionProvenance


@dataclass(frozen=True, slots=True)
class OtsuMorphologyConfig:
    gaussian_sigma_pixels: float = 1.5
    threshold_scale: float = 1.0
    opening_disk_radius: int = 1
    closing_disk_radius: int = 3
    erosion_disk_radius: int = 1
    dilation_disk_radius: int = 1
    fill_holes: bool = True
    minimum_object_area_pixels: int = 64
    connectivity: int = 2

    def __post_init__(self) -> None:
        if self.gaussian_sigma_pixels < 0:
            raise ValueError("gaussian_sigma_pixels must be zero or greater")
        if self.threshold_scale <= 0:
            raise ValueError("threshold_scale must be greater than zero")
        for name in (
            "opening_disk_radius",
            "closing_disk_radius",
            "erosion_disk_radius",
            "dilation_disk_radius",
        ):
            validate_radius(getattr(self, name), name)
        validate_positive(self.minimum_object_area_pixels, "minimum_object_area_pixels")
        validate_connectivity(self.connectivity)


@dataclass(frozen=True, slots=True)
class OtsuMorphologySegmentationEngine:
    config: OtsuMorphologyConfig = field(default_factory=OtsuMorphologyConfig)
    profile: str | None = None
    selection: SegmentationSelectionProvenance | None = None

    @property
    def record(self) -> SegmentationEngineRecord:
        return self._record()

    def _record(
        self,
        threshold: float | None = None,
        base_otsu_threshold: float | None = None,
    ) -> SegmentationEngineRecord:
        parameters: dict[str, MetadataValue] = {
            "gaussian_sigma_pixels": self.config.gaussian_sigma_pixels,
            "threshold": "global_otsu",
            "threshold_scale": self.config.threshold_scale,
            "opening_disk_radius": self.config.opening_disk_radius,
            "closing_disk_radius": self.config.closing_disk_radius,
            "erosion_disk_radius": self.config.erosion_disk_radius,
            "dilation_disk_radius": self.config.dilation_disk_radius,
            "fill_holes": self.config.fill_holes,
            "minimum_object_area_pixels": self.config.minimum_object_area_pixels,
            "connectivity": self.config.connectivity,
            "postprocessing": "opening;closing;erosion;dilation;fill_holes;remove_small_objects;connected_components",
        }
        if threshold is not None:
            parameters["threshold_value"] = threshold
        if base_otsu_threshold is not None:
            parameters["base_otsu_threshold_value"] = base_otsu_threshold
        return SegmentationEngineRecord(
            name="otsu_global_morphology",
            version="1.0",
            model="global_otsu_threshold",
            method=SegmentationMethodId.OTSU_GLOBAL,
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
            SegmentationMethodId.OTSU_GLOBAL
        )
        smooth = filters.gaussian(
            values, sigma=self.config.gaussian_sigma_pixels, preserve_range=True
        )
        base_otsu_threshold = float(filters.threshold_otsu(smooth))
        threshold = base_otsu_threshold * self.config.threshold_scale
        mask = smooth > threshold
        mask = morphology.opening(mask, morphology.disk(self.config.opening_disk_radius))
        mask = morphology.closing(mask, morphology.disk(self.config.closing_disk_radius))
        mask = morphology.erosion(mask, morphology.disk(self.config.erosion_disk_radius))
        mask = morphology.dilation(mask, morphology.disk(self.config.dilation_disk_radius))
        if self.config.fill_holes:
            mask = ndi.binary_fill_holes(mask)
        mask = remove_small_binary_objects(
            mask,
            self.config.minimum_object_area_pixels,
            self.config.connectivity,
            measure,
        )
        labels = canonicalize_labels(
            measure.label(mask, connectivity=self.config.connectivity).astype(np.int32)
        )
        return segmentation_result(
            labels,
            roi_count(labels),
            self._record(threshold, base_otsu_threshold),
            context,
        )
