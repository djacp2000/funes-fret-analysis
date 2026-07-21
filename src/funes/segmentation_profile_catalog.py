"""Auditable built-in profile catalog for Module 7."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .contracts import MetadataValue
from .segmentation_cellpose import CELLPOSE_CPU_WARNING
from .segmentation_selection import (
    BENCHMARK_BASELINE_PROFILE,
    PROVISIONAL_WORKING_PROFILE,
    SegmentationMethodId,
)


@dataclass(frozen=True, slots=True)
class SegmentationProfile:
    """Named, immutable effective parameters for one engine."""

    method: SegmentationMethodId
    name: str
    parameters: Mapping[str, MetadataValue]
    status: str = "diagnostic_baseline_not_accuracy_validated"
    origin: str = "segmentation_method_benchmark_20260713"
    known_limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("profile name must be a non-empty string")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        limitations = tuple(self.known_limitations)
        if any(not isinstance(item, str) or not item.strip() for item in limitations):
            raise ValueError("known limitations must be non-empty strings")
        object.__setattr__(self, "known_limitations", limitations)


def _profile(
    method: SegmentationMethodId,
    parameters: Mapping[str, MetadataValue],
) -> SegmentationProfile:
    return SegmentationProfile(
        method=method,
        name=BENCHMARK_BASELINE_PROFILE,
        parameters=parameters,
    )


BENCHMARK_BASELINE_PROFILES = (
    _profile(
        SegmentationMethodId.KMEANS,
        {
            "clusters": 3,
            "foreground_cluster_count": 2,
            "foreground_clusters": "two_highest_centers",
            "fit_sampling": "evenly_spaced_flat_indices",
            "fit_max_pixels": 100_000,
            "n_init": 10,
            "algorithm": "lloyd",
            "random_state": 1729,
            "opening_disk_radius": 1,
            "closing_disk_radius": 3,
            "fill_holes": True,
            "minimum_object_area_pixels": 64,
            "connectivity": 2,
            "postprocessing": "opening;closing;fill_holes;remove_small_objects;connected_components",
        },
    ),
    _profile(
        SegmentationMethodId.CELLPOSE_CPSAM,
        {
            "pretrained_model": "cpsam_v2",
            "gpu": False,
            "channels": "single_selected_grayscale_channel_[0,0]",
            "diameter": None,
            "normalize": True,
            "augment": False,
            "batch_size": 1,
            "resample": True,
            "flow_threshold": 0.4,
            "cellprob_threshold": 0.0,
            "minimum_object_area_pixels": 15,
            "max_size_fraction": 0.4,
            "tile_overlap": 0.1,
            "random_seed": 1729,
            "torch_threads": 1,
            "torch_deterministic_algorithms": "enabled_warn_only",
            "postprocessing": "none;canonicalize_positive_labels_only",
            "resource_warning": CELLPOSE_CPU_WARNING,
        },
    ),
    _profile(
        SegmentationMethodId.MARKER_WATERSHED,
        {
            "gaussian_sigma_pixels": 1.5,
            "foreground_threshold": "global_otsu",
            "foreground_threshold_scale": 1.0,
            "foreground_opening_disk_radius": 1,
            "foreground_closing_disk_radius": 3,
            "fill_holes": True,
            "minimum_object_area_pixels": 64,
            "distance_transform": "euclidean",
            "marker_strategy": "local_maxima_of_distance_transform",
            "marker_min_distance_pixels": 12,
            "marker_exclude_border": False,
            "watershed_surface": "negative_distance",
            "watershed_mask": "cleaned_otsu_foreground",
            "watershed_compactness": 0.0,
            "connectivity": 2,
            "postprocessing": "remove_small_labels;canonicalize_labels",
        },
    ),
    _profile(
        SegmentationMethodId.OTSU_GLOBAL,
        {
            "gaussian_sigma_pixels": 1.5,
            "threshold": "global_otsu",
            "threshold_scale": 1.0,
            "opening_disk_radius": 1,
            "closing_disk_radius": 3,
            "erosion_disk_radius": 1,
            "dilation_disk_radius": 1,
            "fill_holes": True,
            "minimum_object_area_pixels": 64,
            "connectivity": 2,
            "postprocessing": "opening;closing;erosion;dilation;fill_holes;remove_small_objects;connected_components",
        },
    ),
    _profile(
        SegmentationMethodId.CONTROL_P99,
        {
            "threshold_percentile": 99.0,
            "foreground_rule": "pixel_value_greater_than_threshold",
            "connectivity": 8,
            "postprocessing": "none",
            "touching_cells": "not_split",
        },
    ),
)


PROVISIONAL_WORKING_KMEANS_PROFILE = SegmentationProfile(
    method=SegmentationMethodId.KMEANS,
    name=PROVISIONAL_WORKING_PROFILE,
    parameters={
        **dict(BENCHMARK_BASELINE_PROFILES[0].parameters),
        "minimum_object_area_pixels": 32,
    },
    status="provisional_working_profile_not_universally_validated",
    origin="scientific_user_working_decision_20260720",
    known_limitations=(
        "faint_cells_may_be_omitted",
        "some_cells_may_have_partial_coverage",
        "touching_cells_may_be_combined_in_one_roi",
    ),
)


REGISTERED_SEGMENTATION_PROFILES = (
    *BENCHMARK_BASELINE_PROFILES,
    PROVISIONAL_WORKING_KMEANS_PROFILE,
)
