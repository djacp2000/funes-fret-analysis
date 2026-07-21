import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import Channel, FrameReference, IssueSeverity, PositionKey
from funes.fret_calculation import (
    ConfiguredFretCalculator,
    FretCalculationConfig,
    FretCalculationStatus,
    FretChannelMapping,
    FretMeasurementMetric,
    calculate_fret,
)
from funes.file_discovery import parse_tiff_filename
from funes.intensity_qc import IntensityQcResult, IntensityQcStatus
from funes.quantitative_background import (
    FrameBackgroundEstimate,
    QuantitativeBackgroundResult,
)
from funes.roi_geometry import (
    BorderTouchPolicy,
    RoiGeometryFilterConfig,
    filter_labeled_rois,
)
from funes.temporal_intensity import (
    TemporalIntensityRecord,
    TemporalIntensityResult,
    extract_filtered_roi_temporal_intensities,
)
from funes.tiff_reader import TiffFrameSequence, TiffMetadata, TiffPair


class FretCalculationTests(unittest.TestCase):
    def test_consumes_exact_d078_result_without_relabeling_or_upstream_recalculation(self) -> None:
        source_labels = np.array(
            [
                [1, 0, 0, 3],
                [0, 2, 2, 0],
                [0, 2, 2, 0],
                [0, 4, 4, 0],
                [0, 4, 4, 0],
            ],
            dtype=np.int32,
        )
        roi_filtering = filter_labeled_rois(
            source_labels,
            RoiGeometryFilterConfig(
                min_area_pixels=2,
                border_policy=BorderTouchPolicy.ACCEPT,
            ),
        )
        c0 = np.full((1, 5, 4), 10, dtype=np.uint16)
        c1 = np.full((1, 5, 4), 5, dtype=np.uint16)
        c0[0][roi_filtering.filtered_label_image == 2] = 30
        c1[0][roi_filtering.filtered_label_image == 2] = 15
        c0[0][roi_filtering.filtered_label_image == 4] = 50
        c1[0][roi_filtering.filtered_label_image == 4] = 25
        pair = _synthetic_pair(c0, c1)
        background = QuantitativeBackgroundResult(
            estimates=(
                _background_estimate(Channel.C0, 10.0),
                _background_estimate(Channel.C1, 5.0),
            ),
            method="precalculated_synthetic_background",
        )
        intensity_qc = IntensityQcResult(
            records=(),
            method="precalculated_synthetic_qc",
        )

        d078_result = extract_filtered_roi_temporal_intensities(
            pair,
            roi_filtering,
            background,
            intensity_qc,
        )
        config = FretCalculationConfig(
            channel_mapping=FretChannelMapping(Channel.C0, Channel.C1),
            baseline_frame_indices=(0,),
        )
        tracking_strategy = _IdentityCheckingFretStrategy(
            expected_measurements=d078_result,
            delegate=ConfiguredFretCalculator(config),
        )

        forbidden_calls = (
            patch("funes.tiff_reader.read_tiff_sequence"),
            patch("funes.quantitative_background.estimate_quantitative_background"),
            patch("funes.intensity_qc.evaluate_intensity_qc"),
            patch("funes.intensity_qc.evaluate_filtered_roi_intensity_qc"),
            patch("funes.temporal_intensity.extract_temporal_intensities"),
            patch("funes.temporal_intensity.extract_filtered_roi_temporal_intensities"),
        )
        mocks = [patcher.start() for patcher in forbidden_calls]
        self.addCleanup(lambda: [patcher.stop() for patcher in reversed(forbidden_calls)])
        result = calculate_fret(
            d078_result,
            config,
            strategy=tracking_strategy,
        )

        self.assertTrue(tracking_strategy.received_exact_measurements)
        self.assertEqual(tuple(np.unique(roi_filtering.filtered_label_image)), (0, 2, 4))
        self.assertEqual({record.roi_label for record in d078_result.records}, {2, 4})
        self.assertEqual({record.roi_label for record in result.records}, {2, 4})
        self.assertEqual(result.records_for(roi_label=1), ())
        self.assertEqual(result.records_for(roi_label=3), ())
        self.assertEqual(
            {record.roi_label: record.ratio for record in result.records},
            {2: 2.0, 4: 2.0},
        )
        for mocked_call in mocks:
            mocked_call.assert_not_called()

    def test_calculates_ratio_and_baseline_normalization(self) -> None:
        measurements = TemporalIntensityResult(
            records=(
                _measurement(Channel.C0, 1, 0, corrected_mean=10.0),
                _measurement(Channel.C1, 1, 0, corrected_mean=30.0),
                _measurement(Channel.C0, 1, 1, corrected_mean=20.0),
                _measurement(Channel.C1, 1, 1, corrected_mean=50.0),
            ),
            method="synthetic_temporal_intensity",
        )

        result = calculate_fret(
            measurements,
            FretCalculationConfig(
                channel_mapping=FretChannelMapping(
                    donor_channel=Channel.C0,
                    fret_channel=Channel.C1,
                ),
                baseline_frame_indices=(0,),
            ),
        )

        self.assertEqual(result.method, "configured_fret_calculation")
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.parameters["ratio_formula"], "C0/C1")
        self.assertEqual(result.parameters["numerator_channel"], "C0")
        self.assertEqual(result.parameters["denominator_channel"], "C1")
        self.assertEqual(result.parameters["biological_donor_channel"], "C0")
        self.assertEqual(result.parameters["biological_fret_channel"], "C1")
        self.assertEqual(result.parameters["measurement_metric"], "background_corrected_mean")
        self.assertEqual(
            result.parameters["manual_average_intensity_definition"],
            "background_corrected_mean",
        )

        frame0 = result.records_for(roi_label=1, frame_index=0)[0]
        frame1 = result.records_for(roi_label=1, frame_index=1)[0]
        self.assertAlmostEqual(frame0.ratio, 10.0 / 30.0)
        self.assertAlmostEqual(frame0.baseline_ratio, 10.0 / 30.0)
        self.assertAlmostEqual(frame0.normalized_ratio, 1.0)
        self.assertAlmostEqual(frame0.delta_ratio_over_baseline, 0.0)
        self.assertEqual(frame0.ratio_status, FretCalculationStatus.PASS)
        self.assertAlmostEqual(frame1.ratio, 20.0 / 50.0)
        self.assertAlmostEqual(frame1.normalized_ratio, (20.0 / 50.0) / (10.0 / 30.0))
        self.assertAlmostEqual(
            frame1.delta_ratio_over_baseline,
            ((20.0 / 50.0) / (10.0 / 30.0)) - 1.0,
        )

    def test_biological_roles_do_not_change_c0_over_c1_formula(self) -> None:
        measurements = TemporalIntensityResult(
            records=(
                _measurement(
                    Channel.C0,
                    1,
                    0,
                    corrected_mean=100.0,
                    corrected_median=5.0,
                ),
                _measurement(
                    Channel.C1,
                    1,
                    0,
                    corrected_mean=10.0,
                    corrected_median=20.0,
                ),
            ),
            method="synthetic_temporal_intensity",
        )

        result = calculate_fret(
            measurements,
            FretCalculationConfig(
                channel_mapping=FretChannelMapping(
                    donor_channel=Channel.C1,
                    fret_channel=Channel.C0,
                ),
                baseline_frame_indices=(0,),
                measurement_metric=FretMeasurementMetric.CORRECTED_MEDIAN,
            ),
        )

        record = result.records_for(roi_label=1, frame_index=0)[0]
        self.assertEqual(record.donor_channel, Channel.C1)
        self.assertEqual(record.fret_channel, Channel.C0)
        self.assertEqual(record.numerator_channel, Channel.C0)
        self.assertEqual(record.denominator_channel, Channel.C1)
        self.assertAlmostEqual(record.c0_value, 5.0)
        self.assertAlmostEqual(record.c1_value, 20.0)
        self.assertAlmostEqual(record.donor_value, 20.0)
        self.assertAlmostEqual(record.fret_value, 5.0)
        self.assertAlmostEqual(record.ratio, 0.25)

    def test_preserves_raw_and_background_corrected_means_separately(self) -> None:
        measurements = TemporalIntensityResult(
            records=(
                _measurement(Channel.C0, 1, 0, raw_mean=110.0, corrected_mean=10.0),
                _measurement(Channel.C1, 1, 0, raw_mean=220.0, corrected_mean=20.0),
            ),
            method="synthetic_temporal_intensity",
        )

        result = calculate_fret(
            measurements,
            FretCalculationConfig(
                channel_mapping=FretChannelMapping(Channel.C0, Channel.C1),
                baseline_frame_indices=(0,),
            ),
        )

        record = result.records[0]
        self.assertEqual(record.c0_raw_mean, 110.0)
        self.assertEqual(record.c1_raw_mean, 220.0)
        self.assertEqual(record.c0_background_corrected_mean, 10.0)
        self.assertEqual(record.c1_background_corrected_mean, 20.0)
        self.assertEqual(record.c0_value, 10.0)
        self.assertEqual(record.c1_value, 20.0)
        self.assertEqual(record.ratio, 0.5)

    def test_preserves_excluded_and_missing_values(self) -> None:
        measurements = TemporalIntensityResult(
            records=(
                _measurement(Channel.C0, 1, 0, corrected_mean=10.0),
                _measurement(Channel.C1, 1, 0, corrected_mean=30.0),
                _measurement(Channel.C0, 1, 1, corrected_mean=12.0),
                _measurement(
                    Channel.C1,
                    1,
                    1,
                    corrected_mean=36.0,
                    roi_frame_qc_status=IntensityQcStatus.EXCLUDED,
                    roi_frame_qc_reasons=("synthetic_exclusion",),
                ),
                _measurement(Channel.C0, 1, 2, corrected_mean=None),
                _measurement(Channel.C1, 1, 2, corrected_mean=40.0),
            ),
            method="synthetic_temporal_intensity",
        )

        result = calculate_fret(
            measurements,
            FretCalculationConfig(
                channel_mapping=FretChannelMapping(
                    donor_channel=Channel.C0,
                    fret_channel=Channel.C1,
                ),
                baseline_frame_indices=(0,),
            ),
        )

        excluded = result.records_for(roi_label=1, frame_index=1)[0]
        missing = result.records_for(roi_label=1, frame_index=2)[0]
        self.assertIsNone(excluded.ratio)
        self.assertEqual(excluded.ratio_status, FretCalculationStatus.EXCLUDED)
        self.assertEqual(excluded.normalization_status, FretCalculationStatus.EXCLUDED)
        self.assertIn("synthetic_exclusion", excluded.fret_input_reasons)
        self.assertIsNone(missing.ratio)
        self.assertEqual(missing.ratio_status, FretCalculationStatus.MISSING)
        self.assertEqual(missing.ratio_reasons, ("c0_value_missing",))

    def test_reports_unavailable_baseline(self) -> None:
        measurements = TemporalIntensityResult(
            records=(
                _measurement(
                    Channel.C0,
                    1,
                    0,
                    corrected_mean=10.0,
                    roi_frame_qc_status=IntensityQcStatus.EXCLUDED,
                    roi_frame_qc_reasons=("baseline_excluded",),
                ),
                _measurement(Channel.C1, 1, 0, corrected_mean=30.0),
            ),
            method="synthetic_temporal_intensity",
        )

        result = calculate_fret(
            measurements,
            FretCalculationConfig(
                channel_mapping=FretChannelMapping(
                    donor_channel=Channel.C0,
                    fret_channel=Channel.C1,
                ),
                baseline_frame_indices=(0,),
            ),
            context={"capture": "Capture 1"},
        )

        record = result.records_for(roi_label=1, frame_index=0)[0]
        self.assertIsNone(record.baseline_ratio)
        self.assertEqual(record.normalization_status, FretCalculationStatus.MISSING)
        self.assertIn(
            "fret_baseline_unavailable",
            {issue.code for issue in result.issues},
        )
        self.assertTrue(any(issue.severity is IssueSeverity.ERROR for issue in result.issues))
        self.assertEqual(result.issues[0].context["capture"], "Capture 1")

    def test_reports_missing_c0_numerator_measurement(self) -> None:
        measurements = TemporalIntensityResult(
            records=(
                _measurement(Channel.C1, 1, 0, corrected_mean=30.0),
            ),
            method="synthetic_temporal_intensity",
        )

        result = calculate_fret(
            measurements,
            FretCalculationConfig(
                channel_mapping=FretChannelMapping(
                    donor_channel=Channel.C0,
                    fret_channel=Channel.C1,
                ),
                baseline_frame_indices=(0,),
            ),
        )

        self.assertEqual(result.records, ())
        self.assertIn(
            "fret_missing_channel_measurement",
            {issue.code for issue in result.issues},
        )
        self.assertEqual(result.issues[0].context["missing_channel"], "C0")

    def test_rejects_invalid_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "different"):
            FretChannelMapping(donor_channel=Channel.C0, fret_channel=Channel.C0)

        with self.assertRaisesRegex(ValueError, "baseline_frame_indices"):
            FretCalculationConfig(
                channel_mapping=FretChannelMapping(
                    donor_channel=Channel.C0,
                    fret_channel=Channel.C1,
                ),
                baseline_frame_indices=(),
            )

    def test_rejects_non_temporal_intensity_result_at_public_boundaries(self) -> None:
        config = FretCalculationConfig(
            channel_mapping=FretChannelMapping(Channel.C0, Channel.C1),
            baseline_frame_indices=(0,),
        )

        with self.assertRaisesRegex(TypeError, "TemporalIntensityResult"):
            calculate_fret((), config)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "TemporalIntensityResult"):
            ConfiguredFretCalculator(config).calculate(())  # type: ignore[arg-type]


def _measurement(
    channel: Channel,
    roi_label: int,
    frame_index: int,
    *,
    raw_mean: float = 100.0,
    corrected_mean: float | None,
    corrected_median: float | None = None,
    roi_frame_qc_status: IntensityQcStatus = IntensityQcStatus.PASS,
    roi_frame_qc_reasons: tuple[str, ...] = (),
) -> TemporalIntensityRecord:
    return TemporalIntensityRecord(
        channel=channel,
        frame=FrameReference(frame_index=frame_index),
        roi_label=roi_label,
        roi_area_pixels=2,
        raw_mean=raw_mean,
        raw_median=100.0,
        background_value=1.0,
        background_corrected_mean=corrected_mean,
        background_corrected_median=(
            corrected_mean
            if corrected_median is None
            else corrected_median
        ),
        roi_frame_qc_status=roi_frame_qc_status,
        roi_frame_qc_reasons=roi_frame_qc_reasons,
        field_frame_qc_status=IntensityQcStatus.PASS,
        roi_qc_status=IntensityQcStatus.PASS,
        field_qc_status=IntensityQcStatus.PASS,
    )


class _IdentityCheckingFretStrategy:
    def __init__(
        self,
        *,
        expected_measurements: TemporalIntensityResult,
        delegate: ConfiguredFretCalculator,
    ) -> None:
        self.expected_measurements = expected_measurements
        self.delegate = delegate
        self.received_exact_measurements = False

    @property
    def name(self) -> str:
        return "identity_checking_fret_calculation"

    def calculate(
        self,
        measurements: TemporalIntensityResult,
        context: dict[str, object] | None = None,
    ):
        self.received_exact_measurements = measurements is self.expected_measurements
        return self.delegate.calculate(measurements, context=context)


def _background_estimate(channel: Channel, value: float) -> FrameBackgroundEstimate:
    return FrameBackgroundEstimate(
        channel=channel,
        frame=FrameReference(frame_index=0),
        value=value,
        pixel_count=12,
        pixel_fraction=0.6,
        mean=value,
        median=value,
        standard_deviation=1.0,
        method="precalculated_synthetic_background",
    )


def _synthetic_pair(c0: np.ndarray, c1: np.ndarray) -> TiffPair:
    return TiffPair(
        position_key=PositionKey(capture="Capture 1", position="Position 1"),
        c0=_sequence(c0, Channel.C0),
        c1=_sequence(c1, Channel.C1),
    )


def _sequence(frames: np.ndarray, channel: Channel) -> TiffFrameSequence:
    parsed = parse_tiff_filename(
        Path(
            "Capture 1 - Position 1_XY1782521382_Z0_T00_"
            f"{channel.value}.tif"
        )
    )
    assert parsed is not None
    return TiffFrameSequence(
        parsed_file=parsed,
        frames=frames,
        metadata=TiffMetadata(
            page_count=int(frames.shape[0]),
            series_axes="TYX",
            series_shape=tuple(int(size) for size in frames.shape),
            imagej_metadata=None,
            ome_metadata=None,
            page_descriptions=(),
            first_page_tags={},
        ),
    )


if __name__ == "__main__":
    unittest.main()
