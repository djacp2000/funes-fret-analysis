"""FRET ratio and baseline-normalized calculations from extracted intensities."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Protocol

import numpy as np

from .contracts import Channel, FrameReference, IssueSeverity, MetadataValue, PipelineIssue
from .intensity_qc import IntensityQcStatus
from .temporal_intensity import TemporalIntensityRecord, TemporalIntensityResult


class FretMeasurementMetric(str, Enum):
    """Background-corrected temporal intensity metric used for C0/C1 ratios."""

    CORRECTED_MEAN = "background_corrected_mean"
    CORRECTED_MEDIAN = "background_corrected_median"


class FretCalculationStatus(str, Enum):
    """Status for a calculated ratio or normalized value."""

    PASS = "pass"
    FLAGGED = "flagged"
    EXCLUDED = "excluded"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class FretChannelMapping:
    """Biological channel-role provenance, independent from the ratio formula."""

    donor_channel: Channel
    fret_channel: Channel

    def __post_init__(self) -> None:
        object.__setattr__(self, "donor_channel", Channel(self.donor_channel))
        object.__setattr__(self, "fret_channel", Channel(self.fret_channel))
        if self.donor_channel is self.fret_channel:
            raise ValueError("donor_channel and fret_channel must be different")


@dataclass(frozen=True, slots=True)
class FretCalculationConfig:
    """Configuration for fixed C0/C1 ratio and normalization calculations."""

    channel_mapping: FretChannelMapping
    baseline_frame_indices: tuple[int, ...]
    measurement_metric: FretMeasurementMetric = FretMeasurementMetric.CORRECTED_MEAN
    calculate_excluded_values: bool = False
    include_flagged_values_in_baseline: bool = True
    include_excluded_values_in_baseline: bool = False
    require_positive_c1_denominator: bool = True
    require_positive_baseline: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "measurement_metric", FretMeasurementMetric(self.measurement_metric))
        baseline_frames = tuple(self.baseline_frame_indices)
        if not baseline_frames:
            raise ValueError("baseline_frame_indices must contain at least one frame index")
        if any(frame_index < 0 for frame_index in baseline_frames):
            raise ValueError("baseline_frame_indices must be zero or greater")
        object.__setattr__(self, "baseline_frame_indices", baseline_frames)


@dataclass(frozen=True, slots=True)
class FretCalculationRecord:
    """C0/C1 values plus separate biological-role provenance for one ROI-frame."""

    frame: FrameReference
    roi_label: int
    c0_raw_mean: float
    c1_raw_mean: float | None
    c0_background_corrected_mean: float | None
    c1_background_corrected_mean: float | None
    c0_value: float | None
    c1_value: float | None
    donor_channel: Channel
    fret_channel: Channel
    ratio: float | None
    baseline_ratio: float | None
    normalized_ratio: float | None
    delta_ratio_over_baseline: float | None
    ratio_status: FretCalculationStatus
    ratio_reasons: tuple[str, ...] = ()
    normalization_status: FretCalculationStatus = FretCalculationStatus.MISSING
    normalization_reasons: tuple[str, ...] = ()
    c0_input_status: IntensityQcStatus | None = None
    c0_input_reasons: tuple[str, ...] = ()
    c1_input_status: IntensityQcStatus | None = None
    c1_input_reasons: tuple[str, ...] = ()
    metrics: Mapping[str, MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.roi_label < 1:
            raise ValueError("roi_label must be a positive integer")
        object.__setattr__(self, "donor_channel", Channel(self.donor_channel))
        object.__setattr__(self, "fret_channel", Channel(self.fret_channel))
        for field_name in (
            "c0_raw_mean",
            "c1_raw_mean",
            "c0_background_corrected_mean",
            "c1_background_corrected_mean",
            "c0_value",
            "c1_value",
            "ratio",
            "baseline_ratio",
            "normalized_ratio",
            "delta_ratio_over_baseline",
        ):
            value = getattr(self, field_name)
            if value is not None and not np.isfinite(value):
                raise ValueError(f"{field_name} must be finite when present")
        object.__setattr__(self, "ratio_status", FretCalculationStatus(self.ratio_status))
        object.__setattr__(
            self,
            "normalization_status",
            FretCalculationStatus(self.normalization_status),
        )
        if self.c0_input_status is not None:
            object.__setattr__(
                self,
                "c0_input_status",
                IntensityQcStatus(self.c0_input_status),
            )
        if self.c1_input_status is not None:
            object.__setattr__(
                self,
                "c1_input_status",
                IntensityQcStatus(self.c1_input_status),
            )
        object.__setattr__(self, "ratio_reasons", tuple(self.ratio_reasons))
        object.__setattr__(
            self,
            "normalization_reasons",
            tuple(self.normalization_reasons),
        )
        object.__setattr__(self, "c0_input_reasons", tuple(self.c0_input_reasons))
        object.__setattr__(self, "c1_input_reasons", tuple(self.c1_input_reasons))
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    @property
    def numerator_channel(self) -> Channel:
        """Return the fixed numerator channel for the scientific ratio."""

        return Channel.C0

    @property
    def denominator_channel(self) -> Channel:
        """Return the fixed denominator channel for the scientific ratio."""

        return Channel.C1

    @property
    def donor_value(self) -> float | None:
        """Return the selected value for the configured biological donor role."""

        return self.c0_value if self.donor_channel is Channel.C0 else self.c1_value

    @property
    def fret_value(self) -> float | None:
        """Return the selected value for the configured biological FRET role."""

        return self.c0_value if self.fret_channel is Channel.C0 else self.c1_value

    @property
    def donor_input_status(self) -> IntensityQcStatus | None:
        """Return QC status for the channel carrying the donor provenance role."""

        return self.c0_input_status if self.donor_channel is Channel.C0 else self.c1_input_status

    @property
    def donor_input_reasons(self) -> tuple[str, ...]:
        """Return QC reasons for the channel carrying the donor provenance role."""

        return self.c0_input_reasons if self.donor_channel is Channel.C0 else self.c1_input_reasons

    @property
    def fret_input_status(self) -> IntensityQcStatus | None:
        """Return QC status for the channel carrying the FRET provenance role."""

        return self.c0_input_status if self.fret_channel is Channel.C0 else self.c1_input_status

    @property
    def fret_input_reasons(self) -> tuple[str, ...]:
        """Return QC reasons for the channel carrying the FRET provenance role."""

        return self.c0_input_reasons if self.fret_channel is Channel.C0 else self.c1_input_reasons


@dataclass(frozen=True, slots=True)
class FretCalculationResult:
    """Calculated FRET records plus auditable parameters and issues."""

    records: tuple[FretCalculationRecord, ...]
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
        frame_index: int | None = None,
        roi_label: int | None = None,
    ) -> tuple[FretCalculationRecord, ...]:
        """Return FRET records matching the supplied identifiers."""

        return tuple(
            record
            for record in self.records
            if (
                frame_index is None
                or record.frame.frame_index == frame_index
            )
            and (roi_label is None or record.roi_label == roi_label)
        )


class FretCalculationStrategy(Protocol):
    """Replaceable interface for FRET ratio and normalization calculations."""

    @property
    def name(self) -> str:
        """Stable strategy name preserved in downstream audit records."""

    def calculate(
        self,
        measurements: TemporalIntensityResult,
        context: Mapping[str, MetadataValue] | None = None,
    ) -> FretCalculationResult:
        """Calculate FRET values from extracted temporal intensities."""


@dataclass(frozen=True, slots=True)
class ConfiguredFretCalculator:
    """Calculate FRET ratios using an explicit channel mapping and baseline."""

    config: FretCalculationConfig
    name: str = "configured_fret_calculation"

    def calculate(
        self,
        measurements: TemporalIntensityResult,
        context: Mapping[str, MetadataValue] | None = None,
    ) -> FretCalculationResult:
        measurements = _validated_temporal_intensity_result(measurements)
        context_values = dict(context or {})
        parameters = _parameters(self.config)
        issues: list[PipelineIssue] = []
        indexed_records = _index_measurements(measurements.records, issues, context_values)
        ratio_records = _build_ratio_records(
            indexed_records=indexed_records,
            config=self.config,
            issues=issues,
            context=context_values,
        )
        baselines = _baseline_by_roi(
            ratio_records,
            config=self.config,
            issues=issues,
            context=context_values,
        )
        records = tuple(
            _with_normalization(record, baselines.get(record.roi_label))
            for record in ratio_records
        )
        return FretCalculationResult(
            records=records,
            method=self.name,
            parameters=parameters,
            issues=tuple(issues),
        )


def calculate_fret(
    measurements: TemporalIntensityResult,
    config: FretCalculationConfig,
    strategy: FretCalculationStrategy | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> FretCalculationResult:
    """Calculate FRET ratios and baseline normalization from Module 12 output."""

    measurements = _validated_temporal_intensity_result(measurements)
    calculator = strategy or ConfiguredFretCalculator(config)
    return calculator.calculate(measurements, context=context)


def _validated_temporal_intensity_result(
    measurements: TemporalIntensityResult,
) -> TemporalIntensityResult:
    if not isinstance(measurements, TemporalIntensityResult):
        raise TypeError("measurements must be a TemporalIntensityResult")
    return measurements


def _parameters(config: FretCalculationConfig) -> Mapping[str, MetadataValue]:
    return MappingProxyType(
        {
            "ratio_formula": "C0/C1",
            "numerator_channel": Channel.C0.value,
            "denominator_channel": Channel.C1.value,
            "biological_donor_channel": config.channel_mapping.donor_channel.value,
            "biological_fret_channel": config.channel_mapping.fret_channel.value,
            "baseline_frame_indices": ",".join(
                str(frame_index) for frame_index in config.baseline_frame_indices
            ),
            "measurement_metric": config.measurement_metric.value,
            "manual_average_intensity_definition": "background_corrected_mean",
            "matches_manual_average_intensity_definition": (
                config.measurement_metric is FretMeasurementMetric.CORRECTED_MEAN
            ),
            "preserves_raw_and_background_corrected_means": True,
            "superseded_formula": "C1/C0",
            "superseded_results_status": "D039/D041 C1/C0 outputs superseded by D042",
            "calculate_excluded_values": config.calculate_excluded_values,
            "include_flagged_values_in_baseline": config.include_flagged_values_in_baseline,
            "include_excluded_values_in_baseline": config.include_excluded_values_in_baseline,
            "require_positive_c1_denominator": config.require_positive_c1_denominator,
            "require_positive_baseline": config.require_positive_baseline,
            "calculates_c0_over_c1_ratios": True,
            "method_status": "initial_replaceable_strategy",
        }
    )


def _index_measurements(
    records: tuple[TemporalIntensityRecord, ...],
    issues: list[PipelineIssue],
    context: Mapping[str, MetadataValue],
) -> dict[tuple[Channel, int, int], TemporalIntensityRecord]:
    indexed: dict[tuple[Channel, int, int], TemporalIntensityRecord] = {}
    for record in records:
        key = (record.channel, record.roi_label, record.frame.frame_index)
        if key in indexed:
            issues.append(
                PipelineIssue(
                    code="fret_duplicate_temporal_measurement",
                    message="FRET calculation found duplicate temporal intensity records.",
                    severity=IssueSeverity.ERROR,
                    context={
                        **dict(context),
                        "channel": record.channel.value,
                        "roi_label": record.roi_label,
                        "frame_index": record.frame.frame_index,
                    },
                )
            )
            continue
        indexed[key] = record
    return indexed


def _build_ratio_records(
    *,
    indexed_records: Mapping[tuple[Channel, int, int], TemporalIntensityRecord],
    config: FretCalculationConfig,
    issues: list[PipelineIssue],
    context: Mapping[str, MetadataValue],
) -> tuple[FretCalculationRecord, ...]:
    c0_keys = sorted(
        (roi_label, frame_index)
        for channel, roi_label, frame_index in indexed_records
        if channel is Channel.C0
    )
    records: list[FretCalculationRecord] = []
    for roi_label, frame_index in c0_keys:
        c0_record = indexed_records[(Channel.C0, roi_label, frame_index)]
        c1_record = indexed_records.get((Channel.C1, roi_label, frame_index))
        if c1_record is None:
            issues.append(
                PipelineIssue(
                    code="fret_missing_channel_measurement",
                    message="FRET calculation could not find the paired C1 denominator measurement.",
                    severity=IssueSeverity.ERROR,
                    context={
                        **dict(context),
                        "roi_label": roi_label,
                        "frame_index": frame_index,
                        "missing_channel": Channel.C1.value,
                    },
                )
            )
        elif c0_record.frame.time_seconds != c1_record.frame.time_seconds:
            issues.append(
                PipelineIssue(
                    code="fret_frame_time_mismatch",
                    message="FRET calculation found different frame times for paired C0/C1 measurements.",
                    severity=IssueSeverity.WARNING,
                    context={
                        **dict(context),
                        "roi_label": roi_label,
                        "frame_index": frame_index,
                        "c0_time_seconds": c0_record.frame.time_seconds,
                        "c1_time_seconds": c1_record.frame.time_seconds,
                    },
                )
            )
        records.append(
            _ratio_record(
                c0_record=c0_record,
                c1_record=c1_record,
                config=config,
            )
        )

    c1_only_keys = sorted(
        (roi_label, frame_index)
        for channel, roi_label, frame_index in indexed_records
        if channel is Channel.C1
        and (Channel.C0, roi_label, frame_index) not in indexed_records
    )
    for roi_label, frame_index in c1_only_keys:
        issues.append(
            PipelineIssue(
                code="fret_missing_channel_measurement",
                message="FRET calculation could not find the paired C0 numerator measurement.",
                severity=IssueSeverity.ERROR,
                context={
                    **dict(context),
                    "roi_label": roi_label,
                    "frame_index": frame_index,
                    "missing_channel": Channel.C0.value,
                },
            )
        )

    return tuple(records)


def _ratio_record(
    *,
    c0_record: TemporalIntensityRecord,
    c1_record: TemporalIntensityRecord | None,
    config: FretCalculationConfig,
) -> FretCalculationRecord:
    c0_status, c0_reasons = _input_qc_status(c0_record)
    c1_status, c1_reasons = (
        _input_qc_status(c1_record)
        if c1_record is not None
        else (None, ())
    )
    c0_value = _measurement_value(c0_record, config.measurement_metric)
    c1_value = (
        _measurement_value(c1_record, config.measurement_metric)
        if c1_record is not None
        else None
    )
    ratio, status, reasons = _calculate_ratio(
        c0_value=c0_value,
        c1_value=c1_value,
        c0_status=c0_status,
        c1_status=c1_status,
        config=config,
    )
    return FretCalculationRecord(
        frame=c0_record.frame,
        roi_label=c0_record.roi_label,
        c0_raw_mean=c0_record.raw_mean,
        c1_raw_mean=c1_record.raw_mean if c1_record is not None else None,
        c0_background_corrected_mean=c0_record.background_corrected_mean,
        c1_background_corrected_mean=(
            c1_record.background_corrected_mean if c1_record is not None else None
        ),
        c0_value=c0_value,
        c1_value=c1_value,
        donor_channel=config.channel_mapping.donor_channel,
        fret_channel=config.channel_mapping.fret_channel,
        ratio=ratio,
        baseline_ratio=None,
        normalized_ratio=None,
        delta_ratio_over_baseline=None,
        ratio_status=status,
        ratio_reasons=reasons,
        normalization_status=FretCalculationStatus.MISSING,
        normalization_reasons=("normalization_not_assessed_until_baseline_is_calculated",),
        c0_input_status=c0_status,
        c0_input_reasons=c0_reasons,
        c1_input_status=c1_status,
        c1_input_reasons=c1_reasons,
        metrics={
            "ratio_formula": "C0/C1",
            "measurement_metric": config.measurement_metric.value,
            "biological_roles_do_not_define_ratio_orientation": True,
        },
    )


def _measurement_value(
    record: TemporalIntensityRecord,
    metric: FretMeasurementMetric,
) -> float | None:
    if metric is FretMeasurementMetric.CORRECTED_MEAN:
        return record.background_corrected_mean
    if metric is FretMeasurementMetric.CORRECTED_MEDIAN:
        return record.background_corrected_median
    raise ValueError(f"unsupported FRET measurement metric: {metric}")


def _input_qc_status(
    record: TemporalIntensityRecord,
) -> tuple[IntensityQcStatus | None, tuple[str, ...]]:
    statuses = tuple(
        status
        for status in (
            record.roi_frame_qc_status,
            record.field_frame_qc_status,
            record.roi_qc_status,
            record.field_qc_status,
        )
        if status is not None
    )
    reasons = tuple(
        reason
        for group in (
            record.roi_frame_qc_reasons,
            record.field_frame_qc_reasons,
            record.roi_qc_reasons,
            record.field_qc_reasons,
        )
        for reason in group
    )
    if not statuses:
        return None, reasons
    if any(status is IntensityQcStatus.EXCLUDED for status in statuses):
        return IntensityQcStatus.EXCLUDED, reasons
    if any(status is IntensityQcStatus.FLAGGED for status in statuses):
        return IntensityQcStatus.FLAGGED, reasons
    return IntensityQcStatus.PASS, reasons


def _calculate_ratio(
    *,
    c0_value: float | None,
    c1_value: float | None,
    c0_status: IntensityQcStatus | None,
    c1_status: IntensityQcStatus | None,
    config: FretCalculationConfig,
) -> tuple[float | None, FretCalculationStatus, tuple[str, ...]]:
    reasons: list[str] = []
    if c0_value is None:
        reasons.append("c0_value_missing")
    if c1_value is None:
        reasons.append("c1_value_missing")
    if reasons:
        return None, FretCalculationStatus.MISSING, tuple(reasons)

    excluded = (
        c0_status is IntensityQcStatus.EXCLUDED
        or c1_status is IntensityQcStatus.EXCLUDED
    )
    if excluded and not config.calculate_excluded_values:
        return None, FretCalculationStatus.EXCLUDED, ("input_qc_excluded",)

    if config.require_positive_c1_denominator and c1_value <= 0:
        return None, FretCalculationStatus.MISSING, ("c1_denominator_not_positive",)
    if c1_value == 0:
        return None, FretCalculationStatus.MISSING, ("c1_denominator_zero",)

    ratio = c0_value / c1_value
    if excluded:
        return ratio, FretCalculationStatus.EXCLUDED, ("input_qc_excluded",)

    flagged = (
        c0_status is IntensityQcStatus.FLAGGED
        or c1_status is IntensityQcStatus.FLAGGED
    )
    if flagged:
        return ratio, FretCalculationStatus.FLAGGED, ("input_qc_flagged",)
    return ratio, FretCalculationStatus.PASS, ()


def _baseline_by_roi(
    records: tuple[FretCalculationRecord, ...],
    *,
    config: FretCalculationConfig,
    issues: list[PipelineIssue],
    context: Mapping[str, MetadataValue],
) -> dict[int, float]:
    baselines: dict[int, float] = {}
    roi_labels = sorted({record.roi_label for record in records})
    for roi_label in roi_labels:
        roi_records = {
            record.frame.frame_index: record
            for record in records
            if record.roi_label == roi_label
        }
        missing_baseline_frames = [
            frame_index
            for frame_index in config.baseline_frame_indices
            if frame_index not in roi_records
        ]
        for frame_index in missing_baseline_frames:
            issues.append(
                PipelineIssue(
                    code="fret_baseline_frame_missing",
                    message="FRET calculation could not find a configured baseline frame for this ROI.",
                    severity=IssueSeverity.WARNING,
                    context={
                        **dict(context),
                        "roi_label": roi_label,
                        "frame_index": frame_index,
                    },
                )
            )

        baseline_values = [
            record.ratio
            for frame_index, record in roi_records.items()
            if frame_index in config.baseline_frame_indices
            and _eligible_for_baseline(record, config)
        ]
        if not baseline_values:
            issues.append(
                PipelineIssue(
                    code="fret_baseline_unavailable",
                    message="FRET calculation could not calculate R0 for this ROI from the configured baseline frames.",
                    severity=IssueSeverity.ERROR,
                    context={
                        **dict(context),
                        "roi_label": roi_label,
                        "baseline_frame_indices": ",".join(
                            str(frame_index)
                            for frame_index in config.baseline_frame_indices
                        ),
                    },
                )
            )
            continue

        baseline = float(np.mean(baseline_values))
        if config.require_positive_baseline and baseline <= 0:
            issues.append(
                PipelineIssue(
                    code="fret_baseline_not_positive",
                    message="FRET calculation found a non-positive R0 baseline for this ROI.",
                    severity=IssueSeverity.ERROR,
                    context={
                        **dict(context),
                        "roi_label": roi_label,
                        "baseline_ratio": baseline,
                    },
                )
            )
            continue
        if baseline == 0:
            issues.append(
                PipelineIssue(
                    code="fret_baseline_zero",
                    message="FRET calculation cannot normalize by a zero R0 baseline.",
                    severity=IssueSeverity.ERROR,
                    context={
                        **dict(context),
                        "roi_label": roi_label,
                    },
                )
            )
            continue
        baselines[roi_label] = baseline
    return baselines


def _eligible_for_baseline(
    record: FretCalculationRecord,
    config: FretCalculationConfig,
) -> bool:
    if record.ratio is None:
        return False
    if record.ratio_status is FretCalculationStatus.MISSING:
        return False
    if (
        record.ratio_status is FretCalculationStatus.EXCLUDED
        and not config.include_excluded_values_in_baseline
    ):
        return False
    if (
        record.ratio_status is FretCalculationStatus.FLAGGED
        and not config.include_flagged_values_in_baseline
    ):
        return False
    return True


def _with_normalization(
    record: FretCalculationRecord,
    baseline: float | None,
) -> FretCalculationRecord:
    if baseline is None:
        return _replace_normalization(
            record,
            baseline_ratio=None,
            normalized_ratio=None,
            delta_ratio_over_baseline=None,
            normalization_status=FretCalculationStatus.MISSING,
            normalization_reasons=("baseline_ratio_missing",),
        )
    if record.ratio is None:
        return _replace_normalization(
            record,
            baseline_ratio=baseline,
            normalized_ratio=None,
            delta_ratio_over_baseline=None,
            normalization_status=record.ratio_status,
            normalization_reasons=record.ratio_reasons,
        )

    normalized = record.ratio / baseline
    return _replace_normalization(
        record,
        baseline_ratio=baseline,
        normalized_ratio=normalized,
        delta_ratio_over_baseline=normalized - 1.0,
        normalization_status=record.ratio_status,
        normalization_reasons=record.ratio_reasons,
    )


def _replace_normalization(
    record: FretCalculationRecord,
    *,
    baseline_ratio: float | None,
    normalized_ratio: float | None,
    delta_ratio_over_baseline: float | None,
    normalization_status: FretCalculationStatus,
    normalization_reasons: tuple[str, ...],
) -> FretCalculationRecord:
    return FretCalculationRecord(
        frame=record.frame,
        roi_label=record.roi_label,
        c0_raw_mean=record.c0_raw_mean,
        c1_raw_mean=record.c1_raw_mean,
        c0_background_corrected_mean=record.c0_background_corrected_mean,
        c1_background_corrected_mean=record.c1_background_corrected_mean,
        c0_value=record.c0_value,
        c1_value=record.c1_value,
        donor_channel=record.donor_channel,
        fret_channel=record.fret_channel,
        ratio=record.ratio,
        baseline_ratio=baseline_ratio,
        normalized_ratio=normalized_ratio,
        delta_ratio_over_baseline=delta_ratio_over_baseline,
        ratio_status=record.ratio_status,
        ratio_reasons=record.ratio_reasons,
        normalization_status=normalization_status,
        normalization_reasons=normalization_reasons,
        c0_input_status=record.c0_input_status,
        c0_input_reasons=record.c0_input_reasons,
        c1_input_status=record.c1_input_status,
        c1_input_reasons=record.c1_input_reasons,
        metrics=record.metrics,
    )
