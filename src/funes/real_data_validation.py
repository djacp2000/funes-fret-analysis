"""Focused real-pair validation harness through the Module 14 exporter.

This is an integration aid, not a production scientific pipeline.  Its default
profile exists only to exercise the current module interfaces with one C0/C1
pair while preserving every provisional assumption in the exported issues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .auxiliary_metadata import (
    associate_auxiliary_metadata_files,
    discover_auxiliary_metadata_files,
)
from .contracts import Channel, IssueSeverity, MetadataValue, PipelineIssue
from .experiment_assignment import (
    ExperimentAssignmentRule,
    assign_experiments,
)
from .file_discovery import discover_tiff_files
from .fret_calculation import (
    FretCalculationConfig,
    FretChannelMapping,
    calculate_fret,
)
from .intensity_qc import (
    CameraSaturationProfile,
    FractionThresholds,
    IntensityQcConfig,
    evaluate_filtered_roi_intensity_qc,
)
from .module14_exporter import (
    Module14ExportResult,
    Module14PositionExport,
    export_module14_workbooks,
)
from .quantitative_background import (
    PercentileQuantitativeBackgroundEstimator,
    QuantitativeBackgroundConfig,
    QuantitativeBackgroundStrategy,
    estimate_quantitative_background,
)
from .roi_geometry import (
    BorderTouchPolicy,
    RoiFilteringResult,
    RoiGeometryFilterConfig,
    filter_segmentation_rois,
)
from .segmentation_channel import (
    SegmentationChannelSelection,
    SegmentationChannelSelectionConfig,
    select_segmentation_channel,
)
from .segmentation_engine import (
    PercentileThresholdSegmentationConfig,
    PercentileThresholdSegmentationEngine,
    SegmentationEngine,
    SegmentationResult,
    segment_first_frame,
)
from .segmentation_preprocessing import (
    IdentitySegmentationPreprocessor,
    SegmentationPreprocessingResult,
    SegmentationPreprocessingStrategy,
    preprocess_for_segmentation,
)
from .temporal_intensity import (
    TemporalIntensityExtractionConfig,
    extract_filtered_roi_temporal_intensities,
)
from .tiff_reader import validate_tiff_pairs


class RealPairValidationError(RuntimeError):
    """Raised when the selected real pair cannot reach the export boundary."""


def _default_segmentation_engine() -> SegmentationEngine:
    return PercentileThresholdSegmentationEngine(
        PercentileThresholdSegmentationConfig(
            threshold_percentile=99.0,
            connectivity=8,
        )
    )


def _default_background_strategy() -> QuantitativeBackgroundStrategy:
    return PercentileQuantitativeBackgroundEstimator(
        QuantitativeBackgroundConfig(
            background_percentile=20.0,
            minimum_background_pixels=1,
        )
    )


def _default_intensity_qc() -> IntensityQcConfig:
    return IntensityQcConfig(
        camera_profile=CameraSaturationProfile(
            name="validation_only_65535_ceiling",
            saturation_threshold=65535.0,
        ),
        roi_saturation=FractionThresholds(),
        field_saturation=FractionThresholds(),
        low_signal_by_channel={},
    )


def _default_fret() -> FretCalculationConfig:
    return FretCalculationConfig(
        channel_mapping=FretChannelMapping(
            donor_channel=Channel.C0,
            fret_channel=Channel.C1,
        ),
        baseline_frame_indices=(0,),
    )


@dataclass(frozen=True, slots=True)
class RealPairValidationConfig:
    """Explicit provisional profile for one real-data integration run."""

    experiment_label: str
    capture: str
    position: str
    channel_selection: SegmentationChannelSelectionConfig = field(
        default_factory=SegmentationChannelSelectionConfig
    )
    preprocessor: SegmentationPreprocessingStrategy = field(
        default_factory=IdentitySegmentationPreprocessor
    )
    segmentation_engine: SegmentationEngine = field(
        default_factory=_default_segmentation_engine
    )
    roi_geometry: RoiGeometryFilterConfig = field(
        default_factory=lambda: RoiGeometryFilterConfig(
            min_area_pixels=20,
            border_policy=BorderTouchPolicy.EXCLUDE,
        )
    )
    background_strategy: QuantitativeBackgroundStrategy = field(
        default_factory=_default_background_strategy
    )
    intensity_qc: IntensityQcConfig = field(default_factory=_default_intensity_qc)
    temporal_intensity: TemporalIntensityExtractionConfig = field(
        default_factory=TemporalIntensityExtractionConfig
    )
    fret: FretCalculationConfig = field(default_factory=_default_fret)

    def __post_init__(self) -> None:
        for name, value in (
            ("experiment_label", self.experiment_label),
            ("capture", self.capture),
            ("position", self.position),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class RealPairValidationResult:
    """Key intermediate evidence and the workbook from one validation run."""

    selected_channel: SegmentationChannelSelection
    preprocessing: SegmentationPreprocessingResult
    segmentation: SegmentationResult
    roi_filtering: RoiFilteringResult
    position_export: Module14PositionExport
    export: Module14ExportResult


def run_real_pair_validation(
    input_dir: Path | str,
    output_dir: Path | str,
    config: RealPairValidationConfig,
    *,
    export_workbook: bool = True,
) -> RealPairValidationResult:
    """Run one selected pair through Modules 1-13 and optionally Module 14."""

    input_path = Path(input_dir)
    if not input_path.is_dir():
        raise RealPairValidationError(
            f"Real-pair validation input directory does not exist: {input_path}"
        )

    discovery = discover_tiff_files(input_path)
    selected_files = tuple(
        parsed
        for parsed in discovery.files
        if parsed.capture.casefold() == config.capture.casefold()
        and parsed.position.casefold() == config.position.casefold()
    )
    if not selected_files:
        raise RealPairValidationError(
            "No parsed TIFF files matched the requested Capture + Position: "
            f"{config.capture} + {config.position}"
        )

    pair_validation = validate_tiff_pairs(selected_files)
    if len(pair_validation.pairs) != 1:
        codes = ", ".join(issue.code for issue in pair_validation.issues) or "none"
        raise RealPairValidationError(
            "The selected acquisition did not produce exactly one valid C0/C1 pair; "
            f"validation issue codes: {codes}"
        )

    auxiliary = discover_auxiliary_metadata_files(input_path)
    associations = associate_auxiliary_metadata_files(auxiliary.files, discovery.files)
    assignment = assign_experiments(
        pair_validation.pairs,
        (
            ExperimentAssignmentRule(
                experiment=config.experiment_label,
                captures=(config.capture,),
                positions=(config.position,),
                source="real_pair_validation_profile",
            ),
        ),
        auxiliary_metadata=auxiliary.files,
        auxiliary_metadata_associations=associations.associations,
    )
    if len(assignment.pairs) != 1:
        codes = ", ".join(issue.code for issue in assignment.issues) or "none"
        raise RealPairValidationError(
            "The selected pair could not be assigned to the validation experiment; "
            f"assignment issue codes: {codes}"
        )

    pair = assignment.pairs[0]
    context: dict[str, MetadataValue] = {
        "experiment": pair.position_key.experiment,
        "capture": pair.position_key.capture,
        "position": pair.position_key.position,
        "purpose": "real_data_integration_validation_only",
    }
    selection = select_segmentation_channel(pair, config.channel_selection)
    frame_stack = pair.c0.frames if selection.selected_channel is Channel.C0 else pair.c1.frames
    preprocessing = preprocess_for_segmentation(
        frame_stack[0],
        strategy=config.preprocessor,
        context=context,
    )
    segmentation = segment_first_frame(
        preprocessing.processed_frame,
        engine=config.segmentation_engine,
        context=context,
    )
    roi_filtering = filter_segmentation_rois(
        segmentation,
        config=config.roi_geometry,
        context=context,
    )
    if roi_filtering.accepted_count == 0:
        raise RealPairValidationError(
            "The validation profile produced no retained ROIs. Adjust the explicit "
            "segmentation or geometry configuration before exporting."
        )

    background = estimate_quantitative_background(
        pair,
        roi_label_image=roi_filtering.filtered_label_image,
        strategy=config.background_strategy,
        context=context,
    )
    intensity_qc = evaluate_filtered_roi_intensity_qc(
        pair,
        roi_filtering,
        background,
        config.intensity_qc,
        context=context,
    )
    temporal_intensity = extract_filtered_roi_temporal_intensities(
        pair,
        roi_filtering,
        background,
        intensity_qc,
        config=config.temporal_intensity,
        context=context,
    )
    fret = calculate_fret(
        temporal_intensity,
        config.fret,
        context=context,
    )

    orchestration_issues = (
        *discovery.issues,
        *pair_validation.issues,
        *auxiliary.issues,
        *associations.issues,
        *assignment.issues,
        *selection.issues,
        *preprocessing.issues,
        *segmentation.issues,
        _validation_profile_issue(config, selection, preprocessing, segmentation),
    )
    position_export = Module14PositionExport(
        position_key=pair.position_key,
        temporal_intensity=temporal_intensity,
        fret=fret,
        roi_filtering=roi_filtering,
        background=background,
        intensity_qc=intensity_qc,
        pair=pair,
        issues=orchestration_issues,
    )
    export = (
        export_module14_workbooks((position_export,), output_dir)
        if export_workbook
        else Module14ExportResult(workbook_paths=())
    )
    return RealPairValidationResult(
        selected_channel=selection,
        preprocessing=preprocessing,
        segmentation=segmentation,
        roi_filtering=roi_filtering,
        position_export=position_export,
        export=export,
    )


def _validation_profile_issue(
    config: RealPairValidationConfig,
    selection: SegmentationChannelSelection,
    preprocessing: SegmentationPreprocessingResult,
    segmentation: SegmentationResult,
) -> PipelineIssue:
    engine = segmentation.engine
    return PipelineIssue(
        code="real_data_validation_profile_not_production",
        message=(
            "This workbook validates module integration only. Its segmentation, camera, "
            "QC, channel-role, and baseline settings are not approved production science."
        ),
        severity=IssueSeverity.WARNING,
        context={
            "production_ready": False,
            "selected_segmentation_channel": selection.selected_channel.value,
            "segmentation_channel_method": selection.method,
            "preprocessing_method": preprocessing.method,
            "segmentation_engine": engine.name,
            "segmentation_engine_version": engine.version,
            "segmentation_engine_parameters": _mapping_text(engine.parameters),
            "retained_roi_min_area_pixels": config.roi_geometry.min_area_pixels,
            "retained_roi_max_area_pixels": config.roi_geometry.max_area_pixels,
            "border_policy": config.roi_geometry.border_policy.value,
            "camera_profile": config.intensity_qc.camera_profile.name,
            "camera_saturation_threshold": config.intensity_qc.camera_profile.saturation_threshold,
            "saturation_decisions": _saturation_decision_text(config.intensity_qc),
            "low_signal_decisions": _low_signal_decision_text(config.intensity_qc),
            "donor_channel": config.fret.channel_mapping.donor_channel.value,
            "fret_channel": config.fret.channel_mapping.fret_channel.value,
            "baseline_frame_indices": ",".join(
                str(index) for index in config.fret.baseline_frame_indices
            ),
        },
    )


def _mapping_text(values: Mapping[str, MetadataValue]) -> str:
    return "; ".join(
        f"{key}={value}"
        for key, value in sorted(values.items())
    )


def _saturation_decision_text(config: IntensityQcConfig) -> str:
    thresholds = (
        config.roi_saturation.flag_at_or_above,
        config.roi_saturation.exclude_at_or_above,
        config.field_saturation.flag_at_or_above,
        config.field_saturation.exclude_at_or_above,
    )
    if all(value is None for value in thresholds):
        return "disabled; metrics only"
    return (
        f"roi_flag={thresholds[0]}; roi_exclude={thresholds[1]}; "
        f"field_flag={thresholds[2]}; field_exclude={thresholds[3]}"
    )


def _low_signal_decision_text(config: IntensityQcConfig) -> str:
    if not config.low_signal_by_channel:
        return "disabled; no thresholds configured"
    return "; ".join(
        f"{channel.value}:flag_below={thresholds.flag_below_snr},"
        f"exclude_below={thresholds.exclude_below_snr}"
        for channel, thresholds in sorted(
            config.low_signal_by_channel.items(),
            key=lambda item: item[0].value,
        )
    )
