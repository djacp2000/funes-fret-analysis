"""Intensity quality-control flags for saturation and low signal."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Protocol

import numpy as np
from numpy.typing import NDArray

from .contracts import Channel, FrameReference, IssueSeverity, MetadataValue, PipelineIssue
from .quantitative_background import FrameBackgroundEstimate, QuantitativeBackgroundResult
from .roi_geometry import RoiFilteringResult
from .tiff_reader import TiffPair


class IntensityQcScope(str, Enum):
    """Decision scope for one intensity QC record."""

    FIELD_FRAME = "field_frame"
    ROI_FRAME = "roi_frame"
    ROI = "roi"
    FIELD = "field"


class IntensityQcStatus(str, Enum):
    """Status assigned by intensity QC."""

    PASS = "pass"
    FLAGGED = "flagged"
    EXCLUDED = "excluded"


@dataclass(frozen=True, slots=True)
class CameraSaturationProfile:
    """Explicit camera saturation threshold for one acquisition profile."""

    name: str
    saturation_threshold: float
    inclusive: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("camera profile name must be a non-empty string")
        if not np.isfinite(self.saturation_threshold) or self.saturation_threshold <= 0:
            raise ValueError("saturation_threshold must be a positive finite value")


@dataclass(frozen=True, slots=True)
class FractionThresholds:
    """Flag/exclude thresholds for a fraction where larger values are worse."""

    flag_at_or_above: float | None = None
    exclude_at_or_above: float | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("flag_at_or_above", self.flag_at_or_above),
            ("exclude_at_or_above", self.exclude_at_or_above),
        ):
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be within 0..1 when provided")
        if (
            self.flag_at_or_above is not None
            and self.exclude_at_or_above is not None
            and self.exclude_at_or_above < self.flag_at_or_above
        ):
            raise ValueError("exclude_at_or_above must be greater than or equal to flag_at_or_above")


@dataclass(frozen=True, slots=True)
class LowSignalThresholds:
    """Flag/exclude thresholds for SNR where smaller values are worse."""

    flag_below_snr: float | None = None
    exclude_below_snr: float | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("flag_below_snr", self.flag_below_snr),
            ("exclude_below_snr", self.exclude_below_snr),
        ):
            if value is not None and (not np.isfinite(value) or value < 0):
                raise ValueError(f"{field_name} must be a non-negative finite value when provided")
        if (
            self.flag_below_snr is not None
            and self.exclude_below_snr is not None
            and self.exclude_below_snr > self.flag_below_snr
        ):
            raise ValueError("exclude_below_snr must be less than or equal to flag_below_snr")


@dataclass(frozen=True, slots=True)
class IntensityQcConfig:
    """Configuration for the initial intensity QC evaluator."""

    camera_profile: CameraSaturationProfile
    roi_saturation: FractionThresholds
    field_saturation: FractionThresholds
    low_signal_by_channel: Mapping[Channel, LowSignalThresholds] = field(default_factory=dict)

    def __post_init__(self) -> None:
        low_signal = {
            Channel(channel): thresholds
            for channel, thresholds in self.low_signal_by_channel.items()
        }
        object.__setattr__(self, "low_signal_by_channel", MappingProxyType(low_signal))


@dataclass(frozen=True, slots=True)
class IntensityQcRecord:
    """Auditable intensity QC measurement and decision."""

    scope: IntensityQcScope
    status: IntensityQcStatus
    reasons: tuple[str, ...] = ()
    channel: Channel | None = None
    frame: FrameReference | None = None
    roi_label: int | None = None
    metrics: Mapping[str, MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", IntensityQcScope(self.scope))
        object.__setattr__(self, "status", IntensityQcStatus(self.status))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        if self.channel is not None:
            object.__setattr__(self, "channel", Channel(self.channel))
        if self.roi_label is not None and self.roi_label < 1:
            raise ValueError("roi_label must be a positive integer when present")
        if self.status is not IntensityQcStatus.PASS and not self.reasons:
            raise ValueError("flagged or excluded intensity QC records require a reason")
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))


@dataclass(frozen=True, slots=True)
class IntensityQcResult:
    """Intensity QC records and audit issues for one paired acquisition."""

    records: tuple[IntensityQcRecord, ...]
    method: str
    parameters: Mapping[str, MetadataValue] = field(default_factory=dict)
    issues: tuple[PipelineIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "issues", tuple(self.issues))

    @property
    def has_exclusions(self) -> bool:
        """Whether any intensity QC record is excluded."""

        return any(record.status is IntensityQcStatus.EXCLUDED for record in self.records)

    def records_for(
        self,
        *,
        scope: IntensityQcScope | None = None,
        channel: Channel | None = None,
        frame_index: int | None = None,
        roi_label: int | None = None,
    ) -> tuple[IntensityQcRecord, ...]:
        """Return records matching the supplied identifiers."""

        requested_scope = IntensityQcScope(scope) if scope is not None else None
        requested_channel = Channel(channel) if channel is not None else None
        return tuple(
            record
            for record in self.records
            if (requested_scope is None or record.scope is requested_scope)
            and (requested_channel is None or record.channel is requested_channel)
            and (
                frame_index is None
                or (record.frame is not None and record.frame.frame_index == frame_index)
            )
            and (roi_label is None or record.roi_label == roi_label)
        )


class IntensityQcStrategy(Protocol):
    """Replaceable interface for intensity quality control."""

    @property
    def name(self) -> str:
        """Stable strategy name preserved in downstream audit records."""

    def evaluate(
        self,
        pair: TiffPair,
        roi_label_image: NDArray[np.generic],
        background: QuantitativeBackgroundResult,
        context: Mapping[str, MetadataValue] | None = None,
    ) -> IntensityQcResult:
        """Evaluate intensity QC for one C0/C1 pair."""


@dataclass(frozen=True, slots=True)
class ConfiguredIntensityQcEvaluator:
    """Evaluate saturation and background-aware low-signal QC."""

    config: IntensityQcConfig
    name: str = "configured_intensity_qc"

    def evaluate(
        self,
        pair: TiffPair,
        roi_label_image: NDArray[np.generic],
        background: QuantitativeBackgroundResult,
        context: Mapping[str, MetadataValue] | None = None,
    ) -> IntensityQcResult:
        c0_frames = _validated_frame_stack(pair.c0.frames, Channel.C0)
        c1_frames = _validated_frame_stack(pair.c1.frames, Channel.C1)
        if c0_frames.shape != c1_frames.shape:
            raise ValueError("intensity QC requires matching C0/C1 frame shapes")

        labels = _validated_label_image(roi_label_image, c0_frames.shape[1:])
        label_values = _positive_labels(labels)
        parameters = _parameters(self.config, background)
        context_values = dict(context or {})
        records: list[IntensityQcRecord] = []
        issues: list[PipelineIssue] = []

        for channel, frames in ((Channel.C0, c0_frames), (Channel.C1, c1_frames)):
            for frame_index, frame in enumerate(frames):
                background_estimate = _background_for(
                    background,
                    channel=channel,
                    frame_index=frame_index,
                    issues=issues,
                    context=context_values,
                )
                records.append(
                    _field_frame_record(
                        frame=frame,
                        channel=channel,
                        frame_index=frame_index,
                        config=self.config,
                    )
                )
                for label in label_values:
                    records.append(
                        _roi_frame_record(
                            frame=frame,
                            roi_mask=labels == label,
                            label=label,
                            channel=channel,
                            frame_index=frame_index,
                            background_estimate=background_estimate,
                            config=self.config,
                            issues=issues,
                            context=context_values,
                        )
                    )

        records.extend(_aggregate_roi_records(records))
        records.append(_aggregate_field_record(records))
        return IntensityQcResult(
            records=tuple(records),
            method=self.name,
            parameters=parameters,
            issues=tuple(issues),
        )


def evaluate_intensity_qc(
    pair: TiffPair,
    roi_label_image: NDArray[np.generic],
    background: QuantitativeBackgroundResult,
    config: IntensityQcConfig,
    strategy: IntensityQcStrategy | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> IntensityQcResult:
    """Apply a replaceable intensity QC strategy to a TIFF pair."""

    evaluator = strategy or ConfiguredIntensityQcEvaluator(config)
    return evaluator.evaluate(
        pair,
        roi_label_image=roi_label_image,
        background=background,
        context=context,
    )


def evaluate_filtered_roi_intensity_qc(
    pair: TiffPair,
    roi_filtering: RoiFilteringResult,
    background: QuantitativeBackgroundResult,
    config: IntensityQcConfig,
    strategy: IntensityQcStrategy | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> IntensityQcResult:
    """Evaluate QC on the exact geometrically filtered Module 8 ROI mask."""

    if not isinstance(roi_filtering, RoiFilteringResult):
        raise TypeError("roi_filtering must be a RoiFilteringResult")
    return evaluate_intensity_qc(
        pair,
        roi_filtering.filtered_label_image,
        background,
        config,
        strategy=strategy,
        context=context,
    )


def _validated_frame_stack(
    frames: NDArray[np.generic],
    channel: Channel,
) -> NDArray[np.float64]:
    values = np.asarray(frames, dtype=np.float64)
    if values.ndim != 3 or values.size == 0:
        raise ValueError(f"intensity QC requires a non-empty 3D frame stack for {channel.value}")
    if 0 in values.shape:
        raise ValueError(f"intensity QC requires non-empty frame dimensions for {channel.value}")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"intensity QC requires finite pixel values for {channel.value}")
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


def _parameters(
    config: IntensityQcConfig,
    background: QuantitativeBackgroundResult,
) -> Mapping[str, MetadataValue]:
    return MappingProxyType(
        {
            "camera_profile": config.camera_profile.name,
            "saturation_threshold": config.camera_profile.saturation_threshold,
            "saturation_inclusive": config.camera_profile.inclusive,
            "roi_saturation_flag_at_or_above": config.roi_saturation.flag_at_or_above,
            "roi_saturation_exclude_at_or_above": config.roi_saturation.exclude_at_or_above,
            "field_saturation_flag_at_or_above": config.field_saturation.flag_at_or_above,
            "field_saturation_exclude_at_or_above": config.field_saturation.exclude_at_or_above,
            "low_signal_channels": ",".join(
                channel.value for channel in sorted(config.low_signal_by_channel, key=lambda c: c.value)
            ),
            "quantitative_background_method": background.method,
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
):
    try:
        return background.estimate_for(channel, frame_index)
    except KeyError:
        issues.append(
            PipelineIssue(
                code="intensity_qc_missing_background_estimate",
                message="Low-signal QC could not find a background estimate for this channel frame.",
                severity=IssueSeverity.ERROR,
                context={
                    **dict(context),
                    "channel": channel.value,
                    "frame_index": frame_index,
                },
            )
        )
        return None


def _field_frame_record(
    *,
    frame: NDArray[np.float64],
    channel: Channel,
    frame_index: int,
    config: IntensityQcConfig,
) -> IntensityQcRecord:
    saturation = _saturation_metrics(frame, config.camera_profile)
    status, reasons = _status_from_fraction(
        saturation["saturated_pixel_fraction"],
        config.field_saturation,
        flag_reason="field_saturation_fraction_flagged",
        exclude_reason="field_saturation_fraction_excluded",
    )
    return IntensityQcRecord(
        scope=IntensityQcScope.FIELD_FRAME,
        channel=channel,
        frame=FrameReference(frame_index=frame_index),
        status=status,
        reasons=reasons,
        metrics=saturation,
    )


def _roi_frame_record(
    *,
    frame: NDArray[np.float64],
    roi_mask: NDArray[np.bool_],
    label: int,
    channel: Channel,
    frame_index: int,
    background_estimate: FrameBackgroundEstimate | None,
    config: IntensityQcConfig,
    issues: list[PipelineIssue],
    context: Mapping[str, MetadataValue],
) -> IntensityQcRecord:
    pixels = frame[roi_mask]
    metrics: dict[str, MetadataValue] = {
        **_saturation_metrics(pixels, config.camera_profile),
        "raw_mean": float(np.mean(pixels)),
        "raw_median": float(np.median(pixels)),
    }
    if background_estimate is not None:
        background_value = getattr(background_estimate, "value")
        background_std = getattr(background_estimate, "standard_deviation")
        metrics["background_method"] = background_estimate.method
        metrics["background_value"] = background_value
        metrics["background_standard_deviation"] = background_std
        if background_value is not None:
            metrics["background_corrected_mean"] = metrics["raw_mean"] - background_value
        snr = _signal_to_noise(
            raw_mean=metrics["raw_mean"],
            background_value=background_value,
            background_std=background_std,
            channel=channel,
            frame_index=frame_index,
            label=label,
            issues=issues,
            context=context,
        )
        metrics["signal_to_background_noise"] = snr

    saturation_status, saturation_reasons = _status_from_fraction(
        metrics["saturated_pixel_fraction"],
        config.roi_saturation,
        flag_reason="roi_saturation_fraction_flagged",
        exclude_reason="roi_saturation_fraction_excluded",
    )
    low_status, low_reasons = _low_signal_status(
        metrics.get("signal_to_background_noise"),
        config.low_signal_by_channel.get(channel),
    )
    return IntensityQcRecord(
        scope=IntensityQcScope.ROI_FRAME,
        channel=channel,
        frame=FrameReference(frame_index=frame_index),
        roi_label=label,
        status=_worst_status((saturation_status, low_status)),
        reasons=tuple(saturation_reasons + low_reasons),
        metrics=metrics,
    )


def _saturation_metrics(
    pixels: NDArray[np.float64],
    profile: CameraSaturationProfile,
) -> dict[str, MetadataValue]:
    saturated = (
        pixels >= profile.saturation_threshold
        if profile.inclusive
        else pixels > profile.saturation_threshold
    )
    pixel_count = int(pixels.size)
    saturated_count = int(np.count_nonzero(saturated))
    return {
        "pixel_count": pixel_count,
        "saturated_pixel_count": saturated_count,
        "saturated_pixel_fraction": saturated_count / float(pixel_count),
        "saturation_threshold": profile.saturation_threshold,
        "camera_profile": profile.name,
    }


def _signal_to_noise(
    *,
    raw_mean: float,
    background_value: float | None,
    background_std: float | None,
    channel: Channel,
    frame_index: int,
    label: int,
    issues: list[PipelineIssue],
    context: Mapping[str, MetadataValue],
) -> float | None:
    if background_value is None or background_std is None:
        issues.append(
            _low_signal_not_assessed_issue(
                channel=channel,
                frame_index=frame_index,
                label=label,
                reason="background_value_or_noise_missing",
                context=context,
            )
        )
        return None
    if background_std <= 0:
        issues.append(
            _low_signal_not_assessed_issue(
                channel=channel,
                frame_index=frame_index,
                label=label,
                reason="background_noise_not_positive",
                context=context,
            )
        )
        return None
    return (raw_mean - background_value) / background_std


def _low_signal_not_assessed_issue(
    *,
    channel: Channel,
    frame_index: int,
    label: int,
    reason: str,
    context: Mapping[str, MetadataValue],
) -> PipelineIssue:
    return PipelineIssue(
        code="intensity_qc_low_signal_not_assessed",
        message="Low-signal QC could not be assessed for this ROI frame.",
        severity=IssueSeverity.WARNING,
        context={
            **dict(context),
            "channel": channel.value,
            "frame_index": frame_index,
            "label": label,
            "reason": reason,
        },
    )


def _status_from_fraction(
    fraction: MetadataValue,
    thresholds: FractionThresholds,
    *,
    flag_reason: str,
    exclude_reason: str,
) -> tuple[IntensityQcStatus, list[str]]:
    value = float(fraction)
    if thresholds.exclude_at_or_above is not None and value >= thresholds.exclude_at_or_above:
        return IntensityQcStatus.EXCLUDED, [exclude_reason]
    if thresholds.flag_at_or_above is not None and value >= thresholds.flag_at_or_above:
        return IntensityQcStatus.FLAGGED, [flag_reason]
    return IntensityQcStatus.PASS, []


def _low_signal_status(
    snr: MetadataValue,
    thresholds: LowSignalThresholds | None,
) -> tuple[IntensityQcStatus, list[str]]:
    if thresholds is None or snr is None:
        return IntensityQcStatus.PASS, []
    value = float(snr)
    if thresholds.exclude_below_snr is not None and value < thresholds.exclude_below_snr:
        return IntensityQcStatus.EXCLUDED, ["low_signal_snr_excluded"]
    if thresholds.flag_below_snr is not None and value < thresholds.flag_below_snr:
        return IntensityQcStatus.FLAGGED, ["low_signal_snr_flagged"]
    return IntensityQcStatus.PASS, []


def _aggregate_roi_records(records: list[IntensityQcRecord]) -> tuple[IntensityQcRecord, ...]:
    labels = sorted(
        {
            record.roi_label
            for record in records
            if record.scope is IntensityQcScope.ROI_FRAME and record.roi_label is not None
        }
    )
    aggregates: list[IntensityQcRecord] = []
    for label in labels:
        children = [
            record
            for record in records
            if record.scope is IntensityQcScope.ROI_FRAME and record.roi_label == label
        ]
        aggregates.append(
            _aggregate_record(
                scope=IntensityQcScope.ROI,
                children=children,
                roi_label=label,
                excluded_reason="roi_has_excluded_frame",
                flagged_reason="roi_has_flagged_frame",
            )
        )
    return tuple(aggregates)


def _aggregate_field_record(records: list[IntensityQcRecord]) -> IntensityQcRecord:
    children = [
        record
        for record in records
        if record.scope is IntensityQcScope.FIELD_FRAME
    ]
    return _aggregate_record(
        scope=IntensityQcScope.FIELD,
        children=children,
        roi_label=None,
        excluded_reason="field_has_excluded_frame",
        flagged_reason="field_has_flagged_frame",
    )


def _aggregate_record(
    *,
    scope: IntensityQcScope,
    children: list[IntensityQcRecord],
    roi_label: int | None,
    excluded_reason: str,
    flagged_reason: str,
) -> IntensityQcRecord:
    excluded_count = sum(child.status is IntensityQcStatus.EXCLUDED for child in children)
    flagged_count = sum(child.status is IntensityQcStatus.FLAGGED for child in children)
    if excluded_count:
        status = IntensityQcStatus.EXCLUDED
        reasons = (excluded_reason,)
    elif flagged_count:
        status = IntensityQcStatus.FLAGGED
        reasons = (flagged_reason,)
    else:
        status = IntensityQcStatus.PASS
        reasons = ()
    return IntensityQcRecord(
        scope=scope,
        status=status,
        reasons=reasons,
        roi_label=roi_label,
        metrics={
            "child_record_count": len(children),
            "excluded_child_record_count": excluded_count,
            "flagged_child_record_count": flagged_count,
        },
    )


def _worst_status(statuses: tuple[IntensityQcStatus, ...]) -> IntensityQcStatus:
    if any(status is IntensityQcStatus.EXCLUDED for status in statuses):
        return IntensityQcStatus.EXCLUDED
    if any(status is IntensityQcStatus.FLAGGED for status in statuses):
        return IntensityQcStatus.FLAGGED
    return IntensityQcStatus.PASS
