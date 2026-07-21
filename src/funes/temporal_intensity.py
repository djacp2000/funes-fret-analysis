"""Temporal raw and background-corrected ROI intensity extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Protocol

import numpy as np
from numpy.typing import NDArray

from .contracts import Channel, FrameReference, IssueSeverity, MetadataValue, PipelineIssue
from .intensity_qc import (
    IntensityQcRecord,
    IntensityQcResult,
    IntensityQcScope,
    IntensityQcStatus,
)
from .quantitative_background import FrameBackgroundEstimate, QuantitativeBackgroundResult
from .roi_geometry import RoiFilteringResult
from .tiff_reader import TiffPair


@dataclass(frozen=True, slots=True)
class TemporalIntensityExtractionConfig:
    """Optional frame timing supplied by acquisition metadata or user config."""

    frame_times_seconds: tuple[float | None, ...] | None = None

    def __post_init__(self) -> None:
        if self.frame_times_seconds is None:
            return
        times = tuple(self.frame_times_seconds)
        for time_seconds in times:
            if time_seconds is not None and (
                not np.isfinite(time_seconds) or time_seconds < 0
            ):
                raise ValueError("frame_times_seconds must contain non-negative finite values")
        object.__setattr__(self, "frame_times_seconds", times)


@dataclass(frozen=True, slots=True)
class TemporalIntensityRecord:
    """Measurements for one ROI, channel, and temporal frame."""

    channel: Channel
    frame: FrameReference
    roi_label: int
    roi_area_pixels: int
    raw_mean: float
    raw_median: float
    background_value: float | None
    background_corrected_mean: float | None
    background_corrected_median: float | None
    roi_frame_qc_status: IntensityQcStatus | None
    roi_frame_qc_reasons: tuple[str, ...] = ()
    field_frame_qc_status: IntensityQcStatus | None = None
    field_frame_qc_reasons: tuple[str, ...] = ()
    roi_qc_status: IntensityQcStatus | None = None
    roi_qc_reasons: tuple[str, ...] = ()
    field_qc_status: IntensityQcStatus | None = None
    field_qc_reasons: tuple[str, ...] = ()
    metrics: Mapping[str, MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "channel", Channel(self.channel))
        if self.roi_label < 1:
            raise ValueError("roi_label must be a positive integer")
        if self.roi_area_pixels < 1:
            raise ValueError("roi_area_pixels must be at least 1")
        for field_name in (
            "raw_mean",
            "raw_median",
        ):
            if not np.isfinite(getattr(self, field_name)):
                raise ValueError(f"{field_name} must be finite")
        for field_name in (
            "background_value",
            "background_corrected_mean",
            "background_corrected_median",
        ):
            value = getattr(self, field_name)
            if value is not None and not np.isfinite(value):
                raise ValueError(f"{field_name} must be finite when present")
        for status_field in (
            "roi_frame_qc_status",
            "field_frame_qc_status",
            "roi_qc_status",
            "field_qc_status",
        ):
            status = getattr(self, status_field)
            if status is not None:
                object.__setattr__(self, status_field, IntensityQcStatus(status))
        object.__setattr__(self, "roi_frame_qc_reasons", tuple(self.roi_frame_qc_reasons))
        object.__setattr__(self, "field_frame_qc_reasons", tuple(self.field_frame_qc_reasons))
        object.__setattr__(self, "roi_qc_reasons", tuple(self.roi_qc_reasons))
        object.__setattr__(self, "field_qc_reasons", tuple(self.field_qc_reasons))
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))


@dataclass(frozen=True, slots=True)
class TemporalIntensityResult:
    """Extracted temporal ROI intensities plus audit issues."""

    records: tuple[TemporalIntensityRecord, ...]
    method: str
    parameters: Mapping[str, MetadataValue] = field(default_factory=dict)
    issues: tuple[PipelineIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "issues", tuple(self.issues))

    def records_for(
        self,
        *,
        channel: Channel | None = None,
        frame_index: int | None = None,
        roi_label: int | None = None,
    ) -> tuple[TemporalIntensityRecord, ...]:
        """Return measurements matching the supplied identifiers."""

        requested_channel = Channel(channel) if channel is not None else None
        return tuple(
            record
            for record in self.records
            if (requested_channel is None or record.channel is requested_channel)
            and (
                frame_index is None
                or record.frame.frame_index == frame_index
            )
            and (roi_label is None or record.roi_label == roi_label)
        )


class TemporalIntensityExtractionStrategy(Protocol):
    """Replaceable interface for temporal intensity extraction."""

    @property
    def name(self) -> str:
        """Stable strategy name preserved in downstream audit records."""

    def extract(
        self,
        pair: TiffPair,
        roi_label_image: NDArray[np.generic],
        background: QuantitativeBackgroundResult,
        intensity_qc: IntensityQcResult,
        context: Mapping[str, MetadataValue] | None = None,
    ) -> TemporalIntensityResult:
        """Extract per-ROI temporal intensities."""


@dataclass(frozen=True, slots=True)
class FixedRoiTemporalIntensityExtractor:
    """Apply fixed ROIs to every frame in C0 and C1."""

    config: TemporalIntensityExtractionConfig = field(
        default_factory=TemporalIntensityExtractionConfig
    )
    name: str = "fixed_roi_temporal_intensity"

    def extract(
        self,
        pair: TiffPair,
        roi_label_image: NDArray[np.generic],
        background: QuantitativeBackgroundResult,
        intensity_qc: IntensityQcResult,
        context: Mapping[str, MetadataValue] | None = None,
    ) -> TemporalIntensityResult:
        c0_frames = _validated_frame_stack(pair.c0.frames, Channel.C0)
        c1_frames = _validated_frame_stack(pair.c1.frames, Channel.C1)
        if c0_frames.shape != c1_frames.shape:
            raise ValueError("temporal intensity extraction requires matching C0/C1 frame shapes")

        labels = _validated_label_image(roi_label_image, c0_frames.shape[1:])
        label_values = _positive_labels(labels)
        frame_times = _validated_frame_times(self.config.frame_times_seconds, c0_frames.shape[0])
        context_values = dict(context or {})
        parameters = _parameters(self.config, background, intensity_qc)
        records: list[TemporalIntensityRecord] = []
        issues: list[PipelineIssue] = []

        for channel, frames in ((Channel.C0, c0_frames), (Channel.C1, c1_frames)):
            for frame_index, frame in enumerate(frames):
                frame_reference = FrameReference(
                    frame_index=frame_index,
                    time_seconds=frame_times[frame_index],
                )
                background_estimate = _background_for(
                    background,
                    channel=channel,
                    frame_index=frame_index,
                    issues=issues,
                    context=context_values,
                )
                field_frame_qc = _qc_record_for(
                    intensity_qc,
                    scope=IntensityQcScope.FIELD_FRAME,
                    channel=channel,
                    frame_index=frame_index,
                    roi_label=None,
                    issues=issues,
                    context=context_values,
                )
                for label in label_values:
                    roi_mask = labels == label
                    roi_frame_qc = _qc_record_for(
                        intensity_qc,
                        scope=IntensityQcScope.ROI_FRAME,
                        channel=channel,
                        frame_index=frame_index,
                        roi_label=label,
                        issues=issues,
                        context=context_values,
                    )
                    roi_qc = _qc_record_for(
                        intensity_qc,
                        scope=IntensityQcScope.ROI,
                        channel=None,
                        frame_index=None,
                        roi_label=label,
                        issues=issues,
                        context=context_values,
                    )
                    field_qc = _qc_record_for(
                        intensity_qc,
                        scope=IntensityQcScope.FIELD,
                        channel=None,
                        frame_index=None,
                        roi_label=None,
                        issues=issues,
                        context=context_values,
                    )
                    records.append(
                        _extract_record(
                            frame=frame,
                            frame_reference=frame_reference,
                            roi_mask=roi_mask,
                            label=label,
                            channel=channel,
                            background_estimate=background_estimate,
                            roi_frame_qc=roi_frame_qc,
                            field_frame_qc=field_frame_qc,
                            roi_qc=roi_qc,
                            field_qc=field_qc,
                        )
                    )

        return TemporalIntensityResult(
            records=tuple(records),
            method=self.name,
            parameters=parameters,
            issues=tuple(issues),
        )


def extract_temporal_intensities(
    pair: TiffPair,
    roi_label_image: NDArray[np.generic],
    background: QuantitativeBackgroundResult,
    intensity_qc: IntensityQcResult,
    config: TemporalIntensityExtractionConfig | None = None,
    strategy: TemporalIntensityExtractionStrategy | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> TemporalIntensityResult:
    """Extract temporal ROI intensities without calculating FRET ratios."""

    extractor = strategy or FixedRoiTemporalIntensityExtractor(
        config or TemporalIntensityExtractionConfig()
    )
    return extractor.extract(
        pair,
        roi_label_image=roi_label_image,
        background=background,
        intensity_qc=intensity_qc,
        context=context,
    )


def extract_filtered_roi_temporal_intensities(
    pair: TiffPair,
    roi_filtering: RoiFilteringResult,
    background: QuantitativeBackgroundResult,
    intensity_qc: IntensityQcResult,
    config: TemporalIntensityExtractionConfig | None = None,
    strategy: TemporalIntensityExtractionStrategy | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> TemporalIntensityResult:
    """Extract intensities from the exact geometrically filtered Module 8 ROI mask."""

    if not isinstance(roi_filtering, RoiFilteringResult):
        raise TypeError("roi_filtering must be a RoiFilteringResult")
    return extract_temporal_intensities(
        pair,
        roi_filtering.filtered_label_image,
        background,
        intensity_qc,
        config=config,
        strategy=strategy,
        context=context,
    )


def _validated_frame_stack(
    frames: NDArray[np.generic],
    channel: Channel,
) -> NDArray[np.float64]:
    values = np.asarray(frames, dtype=np.float64)
    if values.ndim != 3 or values.size == 0:
        raise ValueError(
            f"temporal intensity extraction requires a non-empty 3D frame stack for {channel.value}"
        )
    if 0 in values.shape:
        raise ValueError(
            f"temporal intensity extraction requires non-empty frame dimensions for {channel.value}"
        )
    if not np.all(np.isfinite(values)):
        raise ValueError(
            f"temporal intensity extraction requires finite pixel values for {channel.value}"
        )
    return values


def _validated_label_image(
    roi_label_image: NDArray[np.generic],
    image_shape: tuple[int, int],
) -> NDArray[np.int32]:
    labels = np.asarray(roi_label_image)
    if labels.shape != image_shape:
        raise ValueError("ROI label image shape must match the channel frame shape")
    if labels.ndim != 2 or labels.size == 0:
        raise ValueError("ROI label image must be a non-empty 2D image")
    if not np.issubdtype(labels.dtype, np.integer):
        raise ValueError("ROI label image must use an integer dtype")
    if np.any(labels < 0):
        raise ValueError("ROI label image labels must be zero or greater")
    if int(labels.max()) > np.iinfo(np.int32).max:
        raise ValueError("ROI label image labels must fit within int32")
    return labels.astype(np.int32, copy=False)


def _positive_labels(labels: NDArray[np.int32]) -> tuple[int, ...]:
    return tuple(sorted(int(label) for label in np.unique(labels) if label > 0))


def _validated_frame_times(
    frame_times_seconds: tuple[float | None, ...] | None,
    frame_count: int,
) -> tuple[float | None, ...]:
    if frame_times_seconds is None:
        return tuple(None for _ in range(frame_count))
    if len(frame_times_seconds) != frame_count:
        raise ValueError("frame_times_seconds length must match the TIFF frame count")
    return frame_times_seconds


def _parameters(
    config: TemporalIntensityExtractionConfig,
    background: QuantitativeBackgroundResult,
    intensity_qc: IntensityQcResult,
) -> Mapping[str, MetadataValue]:
    return MappingProxyType(
        {
            "uses_fixed_rois": True,
            "calculates_fret_ratios": False,
            "frame_times_supplied": config.frame_times_seconds is not None,
            "quantitative_background_method": background.method,
            "intensity_qc_method": intensity_qc.method,
            "method_status": "initial_replaceable_strategy",
        }
    )


def _background_for(
    background: QuantitativeBackgroundResult,
    *,
    channel: Channel,
    frame_index: int,
    issues: list[PipelineIssue],
    context: Mapping[str, MetadataValue],
) -> FrameBackgroundEstimate | None:
    try:
        return background.estimate_for(channel, frame_index)
    except KeyError:
        issues.append(
            PipelineIssue(
                code="temporal_intensity_missing_background_estimate",
                message="Temporal intensity extraction could not find a background estimate for this channel frame.",
                severity=IssueSeverity.ERROR,
                context={
                    **dict(context),
                    "channel": channel.value,
                    "frame_index": frame_index,
                },
            )
        )
        return None


def _qc_record_for(
    intensity_qc: IntensityQcResult,
    *,
    scope: IntensityQcScope,
    channel: Channel | None,
    frame_index: int | None,
    roi_label: int | None,
    issues: list[PipelineIssue],
    context: Mapping[str, MetadataValue],
) -> IntensityQcRecord | None:
    records = intensity_qc.records_for(
        scope=scope,
        channel=channel,
        frame_index=frame_index,
        roi_label=roi_label,
    )
    if not records:
        issues.append(
            PipelineIssue(
                code="temporal_intensity_missing_qc_record",
                message="Temporal intensity extraction could not find a matching intensity QC record.",
                severity=IssueSeverity.WARNING,
                context={
                    **dict(context),
                    "scope": scope.value,
                    "channel": channel.value if channel is not None else None,
                    "frame_index": frame_index,
                    "roi_label": roi_label,
                },
            )
        )
        return None
    if len(records) > 1:
        issues.append(
            PipelineIssue(
                code="temporal_intensity_duplicate_qc_records",
                message="Temporal intensity extraction found multiple matching intensity QC records.",
                severity=IssueSeverity.ERROR,
                context={
                    **dict(context),
                    "scope": scope.value,
                    "channel": channel.value if channel is not None else None,
                    "frame_index": frame_index,
                    "roi_label": roi_label,
                    "record_count": len(records),
                },
            )
        )
    return _worst_qc_record(records)


def _extract_record(
    *,
    frame: NDArray[np.float64],
    frame_reference: FrameReference,
    roi_mask: NDArray[np.bool_],
    label: int,
    channel: Channel,
    background_estimate: FrameBackgroundEstimate | None,
    roi_frame_qc: IntensityQcRecord | None,
    field_frame_qc: IntensityQcRecord | None,
    roi_qc: IntensityQcRecord | None,
    field_qc: IntensityQcRecord | None,
) -> TemporalIntensityRecord:
    pixels = frame[roi_mask]
    raw_mean = float(np.mean(pixels))
    raw_median = float(np.median(pixels))
    background_value = background_estimate.value if background_estimate is not None else None
    corrected_mean = raw_mean - background_value if background_value is not None else None
    corrected_median = raw_median - background_value if background_value is not None else None
    return TemporalIntensityRecord(
        channel=channel,
        frame=frame_reference,
        roi_label=label,
        roi_area_pixels=int(pixels.size),
        raw_mean=raw_mean,
        raw_median=raw_median,
        background_value=background_value,
        background_corrected_mean=corrected_mean,
        background_corrected_median=corrected_median,
        roi_frame_qc_status=_qc_status(roi_frame_qc),
        roi_frame_qc_reasons=_qc_reasons(roi_frame_qc),
        field_frame_qc_status=_qc_status(field_frame_qc),
        field_frame_qc_reasons=_qc_reasons(field_frame_qc),
        roi_qc_status=_qc_status(roi_qc),
        roi_qc_reasons=_qc_reasons(roi_qc),
        field_qc_status=_qc_status(field_qc),
        field_qc_reasons=_qc_reasons(field_qc),
        metrics={
            "background_method": background_estimate.method if background_estimate else None,
            "background_pixel_count": background_estimate.pixel_count if background_estimate else None,
            "background_standard_deviation": (
                background_estimate.standard_deviation if background_estimate else None
            ),
        },
    )


def _qc_status(record: IntensityQcRecord | None) -> IntensityQcStatus | None:
    return record.status if record is not None else None


def _qc_reasons(record: IntensityQcRecord | None) -> tuple[str, ...]:
    return record.reasons if record is not None else ()


def _worst_qc_record(records: tuple[IntensityQcRecord, ...]) -> IntensityQcRecord:
    def rank(record: IntensityQcRecord) -> int:
        if record.status is IntensityQcStatus.EXCLUDED:
            return 2
        if record.status is IntensityQcStatus.FLAGGED:
            return 1
        return 0

    return max(records, key=rank)
