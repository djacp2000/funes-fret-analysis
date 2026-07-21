"""Stable segmentation engine contract and explicit P99 control engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from types import MappingProxyType
from typing import Mapping, Protocol

import numpy as np
from numpy.typing import NDArray

from .contracts import IssueSeverity, MetadataValue, PipelineIssue
from .segmentation_selection import (
    SegmentationMethodId,
    SegmentationSelectionProvenance,
)


class SegmentationEngineUnavailableError(RuntimeError):
    """Raised when a selected engine cannot run; callers must not substitute it."""

    def __init__(
        self,
        method: SegmentationMethodId,
        reason: str,
        install_hint: str,
    ) -> None:
        self.method = method
        self.reason = reason
        self.install_hint = install_hint
        super().__init__(
            f"Segmentation method '{method.value}' is blocked: {reason}. {install_hint}"
        )


@dataclass(frozen=True, slots=True)
class SegmentationEngineRecord:
    """Audit metadata describing the engine that produced ROI labels."""

    name: str
    version: str
    model: str | None
    parameters: Mapping[str, MetadataValue] = field(default_factory=dict)
    method: SegmentationMethodId | None = None
    profile: str | None = None
    selection: SegmentationSelectionProvenance | None = None
    seeds: Mapping[str, int] = field(default_factory=dict)
    package_versions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.name, "name")
        _require_text(self.version, "version")
        if self.model is not None:
            _require_text(self.model, "model")
        if self.profile is not None:
            _require_text(self.profile, "profile")
        if self.method is not None and not isinstance(self.method, SegmentationMethodId):
            raise TypeError("method must be a SegmentationMethodId when present")
        if self.selection is not None:
            if self.method is not self.selection.effective_method:
                raise ValueError("engine method must match selection provenance")
            if self.profile != self.selection.effective_profile:
                raise ValueError("engine profile must match selection provenance")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "seeds", MappingProxyType(dict(self.seeds)))
        object.__setattr__(
            self,
            "package_versions",
            MappingProxyType(dict(self.package_versions)),
        )


@dataclass(frozen=True, slots=True)
class SegmentationResult:
    """Stable Module 7 output: canonical ROI labels plus complete provenance.

    Zero is background and positive ROI labels are consecutive ``1..roi_count``.
    The read-only int32 label image retains the prepared first-frame shape and is
    the direct mask input expected by Module 8 and later fixed-ROI consumers.
    """

    label_image: NDArray[np.int32]
    roi_count: int
    engine: SegmentationEngineRecord
    issues: tuple[PipelineIssue, ...] = ()

    def __post_init__(self) -> None:
        labels = np.asarray(self.label_image)
        if labels.ndim != 2 or labels.size == 0:
            raise ValueError("segmentation result requires a non-empty 2D label image")
        if not np.issubdtype(labels.dtype, np.integer):
            raise ValueError("segmentation result labels must use an integer dtype")
        if np.any(labels < 0):
            raise ValueError("segmentation result labels must be zero or greater")
        if int(labels.max()) > np.iinfo(np.int32).max:
            raise ValueError("segmentation result labels must fit within int32")
        if self.roi_count < 0:
            raise ValueError("roi_count must be zero or greater")
        positive_labels = tuple(int(label) for label in np.unique(labels) if label > 0)
        if positive_labels != tuple(range(1, self.roi_count + 1)):
            raise ValueError(
                "positive labels must be canonical and consecutive from 1 through roi_count"
            )
        stable_labels = labels.astype(np.int32, copy=True)
        stable_labels.setflags(write=False)
        object.__setattr__(self, "label_image", stable_labels)
        object.__setattr__(self, "issues", tuple(self.issues))

    @property
    def roi_labels(self) -> tuple[int, ...]:
        """Stable positive label identifiers available to downstream modules."""

        return tuple(range(1, self.roi_count + 1))

    def require_frame_shape(self, frame: NDArray[np.generic]) -> SegmentationResult:
        """Validate that this output preserves the segmented frame's spatial shape."""

        if self.label_image.shape != np.asarray(frame).shape:
            raise ValueError(
                "segmentation result label_image shape must match the prepared first frame"
            )
        return self


class SegmentationEngine(Protocol):
    """Replaceable interface for first-frame cell segmentation engines."""

    @property
    def record(self) -> SegmentationEngineRecord:
        """Engine identity, model, version, and parameter provenance."""

    def segment(
        self,
        frame: NDArray[np.generic],
        context: Mapping[str, MetadataValue] | None = None,
    ) -> SegmentationResult:
        """Return canonical labels with the same shape as the prepared first frame."""


@dataclass(frozen=True, slots=True)
class PercentileThresholdSegmentationConfig:
    """Configuration for the deterministic initial segmentation engine."""

    threshold_percentile: float = 80.0
    connectivity: int = 8

    def __post_init__(self) -> None:
        if not 0 <= self.threshold_percentile <= 100:
            raise ValueError("threshold_percentile must be within 0..100")
        if self.connectivity not in (4, 8):
            raise ValueError("connectivity must be either 4 or 8")


@dataclass(frozen=True, slots=True)
class PercentileThresholdSegmentationEngine:
    """Deterministic P99-compatible control based on thresholded components."""

    config: PercentileThresholdSegmentationConfig = field(
        default_factory=PercentileThresholdSegmentationConfig
    )
    name: str = "percentile_threshold_connected_components"
    version: str = "0.1"
    model: str | None = "classical_percentile_threshold"
    profile: str | None = None
    selection: SegmentationSelectionProvenance | None = None

    @property
    def record(self) -> SegmentationEngineRecord:
        return SegmentationEngineRecord(
            name=self.name,
            version=self.version,
            model=self.model,
            method=SegmentationMethodId.CONTROL_P99,
            profile=self.profile,
            selection=self.selection,
            package_versions=_installed_package_versions("numpy", "funes"),
            parameters={
                "threshold_percentile": self.config.threshold_percentile,
                "connectivity": self.config.connectivity,
                "foreground_rule": "pixel_value_greater_than_threshold",
                "postprocessing": "none",
                "touching_cells": "not_split",
            },
        )

    def segment(
        self,
        frame: NDArray[np.generic],
        context: Mapping[str, MetadataValue] | None = None,
    ) -> SegmentationResult:
        values = _validated_float_frame(frame)
        threshold = float(np.percentile(values, self.config.threshold_percentile))
        foreground = values > threshold
        labels, roi_count = _label_connected_components(foreground, self.config.connectivity)

        issues: tuple[PipelineIssue, ...] = ()
        if roi_count == 0:
            issues = (
                PipelineIssue(
                    code="segmentation_no_foreground",
                    message="Segmentation produced no foreground ROIs.",
                    severity=IssueSeverity.WARNING,
                    context={
                        **dict(context or {}),
                        "threshold_percentile": self.config.threshold_percentile,
                        "threshold_value": threshold,
                    },
                ),
            )

        engine_record = self.record
        return SegmentationResult(
            label_image=labels,
            roi_count=roi_count,
            engine=SegmentationEngineRecord(
                name=engine_record.name,
                version=engine_record.version,
                model=engine_record.model,
                method=engine_record.method,
                profile=engine_record.profile,
                selection=engine_record.selection,
                seeds=engine_record.seeds,
                package_versions=engine_record.package_versions,
                parameters={
                    **dict(engine_record.parameters),
                    "threshold_value": threshold,
                },
            ),
            issues=issues,
        )


def segment_first_frame(
    frame: NDArray[np.generic],
    engine: SegmentationEngine | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> SegmentationResult:
    """Segment one prepared first frame; the configurable default is K-means."""

    if engine is None:
        from .segmentation_registry import create_default_segmentation_engine

        engine = create_default_segmentation_engine()
    return engine.segment(frame, context=context).require_frame_shape(frame)


def _validated_float_frame(frame: NDArray[np.generic]) -> NDArray[np.float64]:
    values = np.asarray(frame, dtype=np.float64)
    if values.ndim != 2 or values.size == 0:
        raise ValueError("segmentation engine requires a non-empty 2D frame")
    if not np.all(np.isfinite(values)):
        raise ValueError("segmentation engine requires finite pixel values")
    return values


def _label_connected_components(
    foreground: NDArray[np.bool_],
    connectivity: int,
) -> tuple[NDArray[np.int32], int]:
    labels = np.zeros(foreground.shape, dtype=np.int32)
    offsets = _neighbor_offsets(connectivity)
    height, width = foreground.shape
    current_label = 0

    for start_y in range(height):
        for start_x in range(width):
            if not foreground[start_y, start_x] or labels[start_y, start_x] != 0:
                continue

            current_label += 1
            labels[start_y, start_x] = current_label
            stack = [(start_y, start_x)]
            while stack:
                y, x = stack.pop()
                for dy, dx in offsets:
                    ny = y + dy
                    nx = x + dx
                    if ny < 0 or ny >= height or nx < 0 or nx >= width:
                        continue
                    if foreground[ny, nx] and labels[ny, nx] == 0:
                        labels[ny, nx] = current_label
                        stack.append((ny, nx))

    return labels, current_label


def _neighbor_offsets(connectivity: int) -> tuple[tuple[int, int], ...]:
    if connectivity == 4:
        return ((-1, 0), (0, -1), (0, 1), (1, 0))
    return (
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    )


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _installed_package_versions(*package_names: str) -> Mapping[str, str]:
    versions: dict[str, str] = {}
    for package_name in package_names:
        try:
            versions[package_name] = version(package_name)
        except PackageNotFoundError:
            versions[package_name] = "not_installed"
    return versions
