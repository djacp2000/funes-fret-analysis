"""Preliminary background/preprocessing strategies for segmentation inputs.

This module prepares a first-frame image for a future segmentation engine. It
does not implement quantitative channel background correction for measurements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Protocol

import numpy as np
from numpy.typing import NDArray

from .contracts import IssueSeverity, MetadataValue, PipelineIssue


@dataclass(frozen=True, slots=True)
class PreliminaryBackgroundEstimate:
    """Background estimate used only to prepare a segmentation image."""

    method: str
    value: float | None
    parameters: Mapping[str, MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True, slots=True)
class SegmentationPreprocessingResult:
    """Auditable output from a segmentation preprocessing strategy."""

    processed_frame: NDArray[np.float64]
    method: str
    background_estimate: PreliminaryBackgroundEstimate | None = None
    parameters: Mapping[str, MetadataValue] = field(default_factory=dict)
    issues: tuple[PipelineIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


class SegmentationPreprocessingStrategy(Protocol):
    """Replaceable strategy interface for segmentation-only preprocessing."""

    @property
    def name(self) -> str:
        """Stable strategy name preserved in downstream audit records."""

    def preprocess(
        self,
        frame: NDArray[np.generic],
        context: Mapping[str, MetadataValue] | None = None,
    ) -> SegmentationPreprocessingResult:
        """Return a processed first frame suitable for segmentation."""


@dataclass(frozen=True, slots=True)
class IdentitySegmentationPreprocessor:
    """Convert the input frame to float without changing pixel values."""

    name: str = "identity_segmentation_preprocessing"

    def preprocess(
        self,
        frame: NDArray[np.generic],
        context: Mapping[str, MetadataValue] | None = None,
    ) -> SegmentationPreprocessingResult:
        values = _validated_float_frame(frame)
        return SegmentationPreprocessingResult(
            processed_frame=values,
            method=self.name,
            background_estimate=None,
            parameters={"preserves_pixel_values": True},
            issues=(),
        )


@dataclass(frozen=True, slots=True)
class PercentileBackgroundSubtractionConfig:
    """Configuration for a preliminary percentile background subtraction."""

    background_percentile: float = 20.0
    clip_negative: bool = True
    low_dynamic_range_threshold: float = 0.0

    def __post_init__(self) -> None:
        if not 0 <= self.background_percentile <= 100:
            raise ValueError("background_percentile must be within 0..100")
        if self.low_dynamic_range_threshold < 0:
            raise ValueError("low_dynamic_range_threshold must be zero or greater")


@dataclass(frozen=True, slots=True)
class PercentileBackgroundSubtractionPreprocessor:
    """Subtract a robust percentile background for segmentation only."""

    config: PercentileBackgroundSubtractionConfig = field(
        default_factory=PercentileBackgroundSubtractionConfig
    )
    name: str = "percentile_background_subtraction_segmentation_preprocessing"

    def preprocess(
        self,
        frame: NDArray[np.generic],
        context: Mapping[str, MetadataValue] | None = None,
    ) -> SegmentationPreprocessingResult:
        values = _validated_float_frame(frame)
        background = float(np.percentile(values, self.config.background_percentile))
        processed = values - background
        if self.config.clip_negative:
            processed = np.maximum(processed, 0.0)

        parameters = {
            "background_percentile": self.config.background_percentile,
            "clip_negative": self.config.clip_negative,
            "low_dynamic_range_threshold": self.config.low_dynamic_range_threshold,
            "purpose": "segmentation_preprocessing_only",
        }
        issues = _dynamic_range_issues(values, self.config.low_dynamic_range_threshold, context)
        return SegmentationPreprocessingResult(
            processed_frame=np.asarray(processed, dtype=np.float64),
            method=self.name,
            background_estimate=PreliminaryBackgroundEstimate(
                method="percentile",
                value=background,
                parameters={
                    "percentile": self.config.background_percentile,
                    "purpose": "segmentation_preprocessing_only",
                },
            ),
            parameters=parameters,
            issues=issues,
        )


def preprocess_for_segmentation(
    frame: NDArray[np.generic],
    strategy: SegmentationPreprocessingStrategy | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> SegmentationPreprocessingResult:
    """Apply a replaceable preprocessing strategy to a segmentation input frame."""

    strategy = strategy or IdentitySegmentationPreprocessor()
    return strategy.preprocess(frame, context=context)


def _validated_float_frame(frame: NDArray[np.generic]) -> NDArray[np.float64]:
    values = np.asarray(frame, dtype=np.float64)
    if values.ndim != 2 or values.size == 0:
        raise ValueError("segmentation preprocessing requires a non-empty 2D frame")
    if not np.all(np.isfinite(values)):
        raise ValueError("segmentation preprocessing requires finite pixel values")
    return values


def _dynamic_range_issues(
    values: NDArray[np.float64],
    threshold: float,
    context: Mapping[str, MetadataValue] | None,
) -> tuple[PipelineIssue, ...]:
    observed = float(np.max(values) - np.min(values))
    if observed > threshold:
        return ()
    return (
        PipelineIssue(
            code="segmentation_preprocessing_low_dynamic_range",
            message="The segmentation preprocessing input has low dynamic range.",
            severity=IssueSeverity.WARNING,
            context={
                **dict(context or {}),
                "observed_dynamic_range": observed,
                "low_dynamic_range_threshold": threshold,
            },
        ),
    )
