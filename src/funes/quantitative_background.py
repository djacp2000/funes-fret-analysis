"""Quantitative background estimation for paired channel time series."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Protocol

import numpy as np
from numpy.typing import NDArray

from .contracts import Channel, FrameReference, IssueSeverity, MetadataValue, PipelineIssue
from .tiff_reader import TiffPair


class BackgroundPixelSource(str, Enum):
    """Pixel source used by a quantitative background estimator."""

    NON_ROI_PIXELS = "non_roi_pixels"
    FULL_FRAME = "full_frame"


@dataclass(frozen=True, slots=True)
class QuantitativeBackgroundConfig:
    """Configuration for the initial percentile background estimator."""

    background_percentile: float = 20.0
    pixel_source: BackgroundPixelSource = BackgroundPixelSource.NON_ROI_PIXELS
    minimum_background_pixels: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.background_percentile <= 100:
            raise ValueError("background_percentile must be within 0..100")
        object.__setattr__(self, "pixel_source", BackgroundPixelSource(self.pixel_source))
        if self.minimum_background_pixels < 1:
            raise ValueError("minimum_background_pixels must be at least 1")


@dataclass(frozen=True, slots=True)
class FrameBackgroundEstimate:
    """Quantitative background and diagnostics for one channel frame."""

    channel: Channel
    frame: FrameReference
    value: float | None
    pixel_count: int
    pixel_fraction: float
    mean: float | None
    median: float | None
    standard_deviation: float | None
    method: str
    parameters: Mapping[str, MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "channel", Channel(self.channel))
        if self.pixel_count < 0:
            raise ValueError("pixel_count must be zero or greater")
        if not 0 <= self.pixel_fraction <= 1:
            raise ValueError("pixel_fraction must be within 0..1")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True, slots=True)
class QuantitativeBackgroundResult:
    """Per-channel, per-frame background estimates plus audit issues."""

    estimates: tuple[FrameBackgroundEstimate, ...]
    method: str
    parameters: Mapping[str, MetadataValue] = field(default_factory=dict)
    issues: tuple[PipelineIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "estimates", tuple(self.estimates))
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "issues", tuple(self.issues))

    def estimate_for(self, channel: Channel, frame_index: int) -> FrameBackgroundEstimate:
        """Return the estimate for a channel/frame pair."""

        requested_channel = Channel(channel)
        for estimate in self.estimates:
            if (
                estimate.channel is requested_channel
                and estimate.frame.frame_index == frame_index
            ):
                return estimate
        raise KeyError(f"no background estimate for {requested_channel.value} frame {frame_index}")


class QuantitativeBackgroundStrategy(Protocol):
    """Replaceable interface for quantitative background estimation."""

    @property
    def name(self) -> str:
        """Stable strategy name preserved in downstream audit records."""

    def estimate(
        self,
        pair: TiffPair,
        roi_label_image: NDArray[np.generic] | None = None,
        context: Mapping[str, MetadataValue] | None = None,
    ) -> QuantitativeBackgroundResult:
        """Estimate background for each channel and temporal frame."""


@dataclass(frozen=True, slots=True)
class PercentileQuantitativeBackgroundEstimator:
    """Estimate channel/frame background with a configurable pixel percentile."""

    config: QuantitativeBackgroundConfig = field(default_factory=QuantitativeBackgroundConfig)
    name: str = "percentile_quantitative_background"

    def estimate(
        self,
        pair: TiffPair,
        roi_label_image: NDArray[np.generic] | None = None,
        context: Mapping[str, MetadataValue] | None = None,
    ) -> QuantitativeBackgroundResult:
        c0_frames = _validated_frame_stack(pair.c0.frames, Channel.C0)
        c1_frames = _validated_frame_stack(pair.c1.frames, Channel.C1)
        if c0_frames.shape != c1_frames.shape:
            raise ValueError("quantitative background requires matching C0/C1 frame shapes")

        background_mask = _background_mask(
            self.config.pixel_source,
            roi_label_image,
            image_shape=c0_frames.shape[1:],
        )
        parameters = _parameters(self.config)
        estimates: list[FrameBackgroundEstimate] = []
        issues: list[PipelineIssue] = []
        context_values = dict(context or {})

        for channel, frames in ((Channel.C0, c0_frames), (Channel.C1, c1_frames)):
            for frame_index, frame in enumerate(frames):
                estimate, issue = _estimate_frame_background(
                    frame=frame,
                    mask=background_mask,
                    channel=channel,
                    frame_index=frame_index,
                    method=self.name,
                    parameters=parameters,
                    config=self.config,
                    context=context_values,
                )
                estimates.append(estimate)
                if issue is not None:
                    issues.append(issue)

        return QuantitativeBackgroundResult(
            estimates=tuple(estimates),
            method=self.name,
            parameters=parameters,
            issues=tuple(issues),
        )


def estimate_quantitative_background(
    pair: TiffPair,
    roi_label_image: NDArray[np.generic] | None = None,
    strategy: QuantitativeBackgroundStrategy | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> QuantitativeBackgroundResult:
    """Apply a replaceable quantitative background strategy to a TIFF pair."""

    strategy = strategy or PercentileQuantitativeBackgroundEstimator()
    return strategy.estimate(pair, roi_label_image=roi_label_image, context=context)


def _validated_frame_stack(
    frames: NDArray[np.generic],
    channel: Channel,
) -> NDArray[np.float64]:
    values = np.asarray(frames, dtype=np.float64)
    if values.ndim != 3 or values.size == 0:
        raise ValueError(
            f"quantitative background requires a non-empty 3D frame stack for {channel.value}"
        )
    if 0 in values.shape:
        raise ValueError(
            f"quantitative background requires non-empty frame dimensions for {channel.value}"
        )
    if not np.all(np.isfinite(values)):
        raise ValueError(
            f"quantitative background requires finite pixel values for {channel.value}"
        )
    return values


def _background_mask(
    pixel_source: BackgroundPixelSource,
    roi_label_image: NDArray[np.generic] | None,
    image_shape: tuple[int, int],
) -> NDArray[np.bool_]:
    if pixel_source is BackgroundPixelSource.FULL_FRAME:
        return np.ones(image_shape, dtype=np.bool_)

    if roi_label_image is None:
        raise ValueError(
            "non_roi_pixels quantitative background requires a ROI label image"
        )

    labels = np.asarray(roi_label_image)
    if labels.shape != image_shape:
        raise ValueError("ROI label image shape must match the channel frame shape")
    if labels.ndim != 2 or labels.size == 0:
        raise ValueError("ROI label image must be a non-empty 2D image")
    if not np.issubdtype(labels.dtype, np.integer):
        raise ValueError("ROI label image must use an integer dtype")
    if np.any(labels < 0):
        raise ValueError("ROI label image labels must be zero or greater")
    return labels == 0


def _parameters(config: QuantitativeBackgroundConfig) -> Mapping[str, MetadataValue]:
    return MappingProxyType(
        {
            "background_percentile": config.background_percentile,
            "pixel_source": config.pixel_source.value,
            "minimum_background_pixels": config.minimum_background_pixels,
            "purpose": "quantitative_channel_correction",
            "method_status": "initial_replaceable_strategy",
        }
    )


def _estimate_frame_background(
    frame: NDArray[np.float64],
    mask: NDArray[np.bool_],
    channel: Channel,
    frame_index: int,
    method: str,
    parameters: Mapping[str, MetadataValue],
    config: QuantitativeBackgroundConfig,
    context: Mapping[str, MetadataValue],
) -> tuple[FrameBackgroundEstimate, PipelineIssue | None]:
    pixels = frame[mask]
    pixel_count = int(pixels.size)
    pixel_fraction = pixel_count / float(frame.size)
    if pixel_count < config.minimum_background_pixels:
        return (
            FrameBackgroundEstimate(
                channel=channel,
                frame=FrameReference(frame_index=frame_index),
                value=None,
                pixel_count=pixel_count,
                pixel_fraction=pixel_fraction,
                mean=None,
                median=None,
                standard_deviation=None,
                method=method,
                parameters=parameters,
            ),
            PipelineIssue(
                code="quantitative_background_insufficient_pixels",
                message="Not enough background pixels were available for quantitative estimation.",
                severity=IssueSeverity.ERROR,
                context={
                    **dict(context),
                    "channel": channel.value,
                    "frame_index": frame_index,
                    "pixel_source": config.pixel_source.value,
                    "background_pixel_count": pixel_count,
                    "minimum_background_pixels": config.minimum_background_pixels,
                },
            ),
        )

    return (
        FrameBackgroundEstimate(
            channel=channel,
            frame=FrameReference(frame_index=frame_index),
            value=float(np.percentile(pixels, config.background_percentile)),
            pixel_count=pixel_count,
            pixel_fraction=pixel_fraction,
            mean=float(np.mean(pixels)),
            median=float(np.median(pixels)),
            standard_deviation=float(np.std(pixels)),
            method=method,
            parameters=parameters,
        ),
        None,
    )
