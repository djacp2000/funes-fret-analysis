"""Choose the C0 or C1 first-frame channel for downstream segmentation."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from .contracts import Channel, IssueSeverity, MetadataValue, PipelineIssue
from .tiff_reader import TiffPair


@dataclass(frozen=True, slots=True)
class SegmentationChannelSelectionConfig:
    """Configurable thresholds for robust first-frame channel comparison."""

    background_percentile: float = 20.0
    signal_percentile: float = 95.0
    min_relative_margin: float = 0.05
    low_contrast_threshold: float = 0.0
    tie_breaker: Channel = Channel.C0
    manual_channel_override: Channel | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.background_percentile < self.signal_percentile <= 100:
            raise ValueError(
                "background_percentile must be lower than signal_percentile within 0..100"
            )
        if self.min_relative_margin < 0:
            raise ValueError("min_relative_margin must be zero or greater")
        if self.low_contrast_threshold < 0:
            raise ValueError("low_contrast_threshold must be zero or greater")


@dataclass(frozen=True, slots=True)
class FirstFrameSignalMetrics:
    """Robust first-frame signal measurements for one channel."""

    channel: Channel
    background_percentile: float
    signal_percentile: float
    robust_background: float
    robust_signal: float
    robust_contrast: float
    mean: float
    median: float
    minimum: float
    maximum: float

    @property
    def score(self) -> float:
        """Selection score; larger values indicate stronger usable signal."""

        return self.robust_contrast


@dataclass(frozen=True, slots=True)
class SegmentationChannelSelection:
    """Audit record for a segmentation-channel decision."""

    selected_channel: Channel
    method: str
    metrics: Mapping[Channel, FirstFrameSignalMetrics]
    issues: tuple[PipelineIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))


def select_segmentation_channel(
    pair: TiffPair,
    config: SegmentationChannelSelectionConfig | None = None,
) -> SegmentationChannelSelection:
    """Select the more suitable channel for segmentation from first-frame C0/C1 metrics."""

    config = config or SegmentationChannelSelectionConfig()
    metrics = {
        Channel.C0: calculate_first_frame_signal_metrics(pair.c0.frames[0], Channel.C0, config),
        Channel.C1: calculate_first_frame_signal_metrics(pair.c1.frames[0], Channel.C1, config),
    }
    issues: list[PipelineIssue] = []

    if config.manual_channel_override is not None:
        issues.append(
            PipelineIssue(
                code="segmentation_channel_manual_override",
                message="Segmentation channel was selected from a manual override.",
                severity=IssueSeverity.INFO,
                context=_selection_context(pair, metrics),
            )
        )
        return SegmentationChannelSelection(
            selected_channel=config.manual_channel_override,
            method="manual_override",
            metrics=metrics,
            issues=tuple(issues),
        )

    selected = _choose_by_score(metrics, config, issues, pair)
    return SegmentationChannelSelection(
        selected_channel=selected,
        method="robust_first_frame_contrast",
        metrics=metrics,
        issues=tuple(issues),
    )


def calculate_first_frame_signal_metrics(
    frame: NDArray[np.generic],
    channel: Channel,
    config: SegmentationChannelSelectionConfig | None = None,
) -> FirstFrameSignalMetrics:
    """Calculate robust first-frame intensity metrics for one channel."""

    config = config or SegmentationChannelSelectionConfig()
    values = np.asarray(frame, dtype=np.float64)
    if values.size == 0:
        raise ValueError("first-frame signal metrics require at least one pixel")

    background = float(np.percentile(values, config.background_percentile))
    signal = float(np.percentile(values, config.signal_percentile))
    return FirstFrameSignalMetrics(
        channel=channel,
        background_percentile=config.background_percentile,
        signal_percentile=config.signal_percentile,
        robust_background=background,
        robust_signal=signal,
        robust_contrast=max(0.0, signal - background),
        mean=float(np.mean(values)),
        median=float(np.median(values)),
        minimum=float(np.min(values)),
        maximum=float(np.max(values)),
    )


def _choose_by_score(
    metrics: Mapping[Channel, FirstFrameSignalMetrics],
    config: SegmentationChannelSelectionConfig,
    issues: list[PipelineIssue],
    pair: TiffPair,
) -> Channel:
    c0_score = metrics[Channel.C0].score
    c1_score = metrics[Channel.C1].score
    best_score = max(c0_score, c1_score)

    if best_score <= config.low_contrast_threshold:
        issues.append(
            PipelineIssue(
                code="segmentation_channel_low_contrast",
                message="Both first-frame channels have low robust contrast for segmentation.",
                severity=IssueSeverity.WARNING,
                context=_selection_context(pair, metrics),
            )
        )
        return config.tie_breaker

    margin = abs(c0_score - c1_score) / best_score
    if margin < config.min_relative_margin:
        issues.append(
            PipelineIssue(
                code="segmentation_channel_close_scores",
                message="First-frame C0 and C1 robust contrast scores are close.",
                severity=IssueSeverity.WARNING,
                context={
                    **_selection_context(pair, metrics),
                    "min_relative_margin": config.min_relative_margin,
                    "observed_relative_margin": margin,
                },
            )
        )
        return config.tie_breaker

    return Channel.C0 if c0_score > c1_score else Channel.C1


def _selection_context(
    pair: TiffPair,
    metrics: Mapping[Channel, FirstFrameSignalMetrics],
) -> Mapping[str, MetadataValue]:
    return {
        "capture": pair.position_key.capture,
        "position": pair.position_key.position,
        "experiment": pair.position_key.experiment,
        "c0_score": metrics[Channel.C0].score,
        "c1_score": metrics[Channel.C1].score,
    }
