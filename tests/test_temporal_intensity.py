import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import Channel, FrameReference, IssueSeverity, PositionKey
from funes.file_discovery import parse_tiff_filename
from funes.intensity_qc import (
    CameraSaturationProfile,
    FractionThresholds,
    IntensityQcConfig,
    IntensityQcResult,
    IntensityQcScope,
    IntensityQcStatus,
    evaluate_filtered_roi_intensity_qc,
    evaluate_intensity_qc,
)
from funes.quantitative_background import (
    FrameBackgroundEstimate,
    PercentileQuantitativeBackgroundEstimator,
    QuantitativeBackgroundConfig,
    QuantitativeBackgroundResult,
    estimate_quantitative_background,
)
from funes.roi_geometry import (
    BorderTouchPolicy,
    RoiGeometryFilterConfig,
    filter_segmentation_rois,
)
from funes.segmentation_engine import SegmentationEngineRecord, SegmentationResult
from funes.segmentation_selection import (
    PROVISIONAL_WORKING_PROFILE,
    SegmentationMethodId,
)
from funes.temporal_intensity import (
    FixedRoiTemporalIntensityExtractor,
    TemporalIntensityExtractionConfig,
    extract_filtered_roi_temporal_intensities,
    extract_temporal_intensities,
)
from funes.tiff_reader import TiffFrameSequence, TiffMetadata, TiffPair


class TemporalIntensityTests(unittest.TestCase):
    def test_consumes_filtered_rois_and_reuses_background_and_qc_without_relabeling(self) -> None:
        labels = np.zeros((5, 5), dtype=np.int32)
        labels[1, 1] = 1
        labels[2:4, 2:4] = 2
        segmentation = SegmentationResult(
            label_image=labels,
            roi_count=2,
            engine=SegmentationEngineRecord(
                name="kmeans_morphology",
                version="synthetic-test",
                model="classical_kmeans",
                method=SegmentationMethodId.KMEANS,
                profile=PROVISIONAL_WORKING_PROFILE,
                parameters={"minimum_object_area_pixels": 32},
                seeds={"random_state": 1729},
                package_versions={"numpy": np.__version__},
            ),
        )
        roi_filtering = filter_segmentation_rois(
            segmentation,
            RoiGeometryFilterConfig(
                min_area_pixels=2,
                border_policy=BorderTouchPolicy.ACCEPT,
            ),
        )
        c0 = np.full((1, 5, 5), 10, dtype=np.uint16)
        c1 = np.full((1, 5, 5), 20, dtype=np.uint16)
        c0[0, 1, 1] = 50
        c1[0, 1, 1] = 60
        c0[0, 2:4, 2:4] = 200
        c1[0, 2:4, 2:4] = 220
        pair = _synthetic_pair(c0=c0, c1=c1)
        background = estimate_quantitative_background(
            pair,
            roi_label_image=roi_filtering.filtered_label_image,
            strategy=PercentileQuantitativeBackgroundEstimator(
                QuantitativeBackgroundConfig(background_percentile=100)
            ),
        )
        qc_config = _config()
        intensity_qc = evaluate_filtered_roi_intensity_qc(
            pair,
            roi_filtering,
            background,
            qc_config,
        )
        tracking_strategy = _IdentityCheckingTemporalIntensityStrategy(
            expected_labels=roi_filtering.filtered_label_image,
            expected_background=background,
            expected_intensity_qc=intensity_qc,
            delegate=FixedRoiTemporalIntensityExtractor(),
        )

        result = extract_filtered_roi_temporal_intensities(
            pair,
            roi_filtering,
            background,
            intensity_qc,
            strategy=tracking_strategy,
        )

        self.assertTrue(tracking_strategy.received_exact_labels)
        self.assertTrue(tracking_strategy.received_exact_background)
        self.assertTrue(tracking_strategy.received_exact_intensity_qc)
        self.assertIs(roi_filtering.source_segmentation, segmentation)
        self.assertEqual(tuple(np.unique(roi_filtering.filtered_label_image)), (0, 2))
        self.assertEqual({record.roi_label for record in result.records}, {2})
        self.assertEqual(result.records_for(roi_label=1), ())
        self.assertEqual(
            result.parameters["quantitative_background_method"],
            background.method,
        )
        self.assertEqual(result.parameters["intensity_qc_method"], intensity_qc.method)
        c0_record = result.records_for(
            channel=Channel.C0,
            frame_index=0,
            roi_label=2,
        )[0]
        source_qc = intensity_qc.records_for(
            scope=IntensityQcScope.ROI_FRAME,
            channel=Channel.C0,
            frame_index=0,
            roi_label=2,
        )[0]
        self.assertEqual(c0_record.background_value, 50.0)
        self.assertEqual(c0_record.background_corrected_mean, 150.0)
        self.assertIs(c0_record.roi_frame_qc_status, source_qc.status)
        self.assertEqual(c0_record.roi_frame_qc_reasons, source_qc.reasons)

    def test_extracts_raw_and_corrected_measurements_with_qc_records(self) -> None:
        pair = _synthetic_pair(
            c0=np.array(
                [
                    [[0, 10, 14], [0, 0, 0]],
                    [[0, 20, 24], [0, 0, 0]],
                ],
                dtype=np.uint16,
            ),
            c1=np.array(
                [
                    [[0, 30, 34], [0, 0, 0]],
                    [[0, 4095, 44], [0, 0, 0]],
                ],
                dtype=np.uint16,
            ),
        )
        labels = np.array([[0, 1, 1], [0, 0, 0]], dtype=np.int32)
        background = _background_result(
            frame_count=2,
            c0_values=(2.0, 3.0),
            c1_values=(5.0, 7.0),
        )
        qc = evaluate_intensity_qc(pair, labels, background, _config())

        result = extract_temporal_intensities(
            pair,
            labels,
            background,
            qc,
            config=TemporalIntensityExtractionConfig(frame_times_seconds=(0.0, 12.5)),
        )

        self.assertEqual(result.method, "fixed_roi_temporal_intensity")
        self.assertEqual(len(result.records), 4)
        self.assertFalse(result.parameters["calculates_fret_ratios"])
        c0_frame0 = result.records_for(
            channel=Channel.C0,
            frame_index=0,
            roi_label=1,
        )[0]
        c1_frame1 = result.records_for(
            channel=Channel.C1,
            frame_index=1,
            roi_label=1,
        )[0]

        self.assertEqual(c0_frame0.roi_area_pixels, 2)
        self.assertEqual(c0_frame0.frame.time_seconds, 0.0)
        self.assertAlmostEqual(c0_frame0.raw_mean, 12.0)
        self.assertAlmostEqual(c0_frame0.raw_median, 12.0)
        self.assertAlmostEqual(c0_frame0.background_value, 2.0)
        self.assertAlmostEqual(c0_frame0.background_corrected_mean, 10.0)
        self.assertAlmostEqual(c0_frame0.background_corrected_median, 10.0)
        self.assertEqual(c0_frame0.roi_frame_qc_status, IntensityQcStatus.PASS)
        self.assertEqual(c0_frame0.field_qc_status, IntensityQcStatus.FLAGGED)
        self.assertEqual(c1_frame1.frame.time_seconds, 12.5)
        self.assertEqual(c1_frame1.roi_frame_qc_status, IntensityQcStatus.FLAGGED)
        self.assertEqual(
            c1_frame1.roi_frame_qc_reasons,
            ("roi_saturation_fraction_flagged",),
        )
        self.assertEqual(c1_frame1.field_frame_qc_status, IntensityQcStatus.FLAGGED)

    def test_preserves_missing_background_and_qc_as_issues(self) -> None:
        pair = _synthetic_pair(
            c0=np.array([[[10, 14]]], dtype=np.uint16),
            c1=np.array([[[20, 24]]], dtype=np.uint16),
        )
        labels = np.array([[1, 1]], dtype=np.int32)
        background = QuantitativeBackgroundResult(
            estimates=(
                FrameBackgroundEstimate(
                    channel=Channel.C0,
                    frame=FrameReference(frame_index=0),
                    value=None,
                    pixel_count=0,
                    pixel_fraction=0.0,
                    mean=None,
                    median=None,
                    standard_deviation=None,
                    method="synthetic_background",
                ),
            ),
            method="synthetic_background",
        )

        result = extract_temporal_intensities(
            pair,
            labels,
            background,
            IntensityQcResult(records=(), method="synthetic_qc"),
            context={"capture": "Capture 1"},
        )

        c0_record = result.records_for(channel=Channel.C0, frame_index=0, roi_label=1)[0]
        c1_record = result.records_for(channel=Channel.C1, frame_index=0, roi_label=1)[0]
        self.assertIsNone(c0_record.background_corrected_mean)
        self.assertIsNone(c1_record.background_value)
        self.assertIsNone(c1_record.roi_frame_qc_status)
        self.assertIn(
            "temporal_intensity_missing_background_estimate",
            {issue.code for issue in result.issues},
        )
        self.assertIn(
            "temporal_intensity_missing_qc_record",
            {issue.code for issue in result.issues},
        )
        self.assertTrue(
            any(issue.severity is IssueSeverity.ERROR for issue in result.issues)
        )
        self.assertEqual(result.issues[0].context["capture"], "Capture 1")

    def test_rejects_invalid_inputs(self) -> None:
        pair = _synthetic_pair(
            c0=np.zeros((1, 2, 2), dtype=np.uint16),
            c1=np.zeros((1, 2, 2), dtype=np.uint16),
        )
        labels = np.ones((2, 2), dtype=np.int32)
        background = _background_result(
            frame_count=1,
            c0_values=(0.0, 1.0),
            c1_values=(0.0, 1.0),
        )
        qc = evaluate_intensity_qc(pair, labels, background, _config())

        with self.assertRaisesRegex(ValueError, "shape"):
            extract_temporal_intensities(
                pair,
                np.ones((3, 3), dtype=np.int32),
                background,
                qc,
            )

        with self.assertRaisesRegex(ValueError, "integer"):
            extract_temporal_intensities(
                pair,
                np.ones((2, 2), dtype=np.float64),
                background,
                qc,
            )

        with self.assertRaisesRegex(ValueError, "frame_times_seconds length"):
            extract_temporal_intensities(
                pair,
                labels,
                background,
                qc,
                config=TemporalIntensityExtractionConfig(frame_times_seconds=(0.0, 1.0)),
            )

        with self.assertRaisesRegex(TypeError, "RoiFilteringResult"):
            extract_filtered_roi_temporal_intensities(
                pair,
                labels,  # type: ignore[arg-type]
                background,
                qc,
            )


class _IdentityCheckingTemporalIntensityStrategy:
    def __init__(
        self,
        *,
        expected_labels: np.ndarray,
        expected_background: QuantitativeBackgroundResult,
        expected_intensity_qc: IntensityQcResult,
        delegate: FixedRoiTemporalIntensityExtractor,
    ) -> None:
        self.expected_labels = expected_labels
        self.expected_background = expected_background
        self.expected_intensity_qc = expected_intensity_qc
        self.delegate = delegate
        self.received_exact_labels = False
        self.received_exact_background = False
        self.received_exact_intensity_qc = False

    @property
    def name(self) -> str:
        return "identity_checking_temporal_intensity"

    def extract(
        self,
        pair: TiffPair,
        roi_label_image: np.ndarray,
        background: QuantitativeBackgroundResult,
        intensity_qc: IntensityQcResult,
        context: dict[str, object] | None = None,
    ):
        self.received_exact_labels = roi_label_image is self.expected_labels
        self.received_exact_background = background is self.expected_background
        self.received_exact_intensity_qc = intensity_qc is self.expected_intensity_qc
        return self.delegate.extract(
            pair,
            roi_label_image,
            background,
            intensity_qc,
            context=context,
        )


def _config() -> IntensityQcConfig:
    return IntensityQcConfig(
        camera_profile=CameraSaturationProfile(
            name="synthetic_12_bit",
            saturation_threshold=4095,
        ),
        roi_saturation=FractionThresholds(flag_at_or_above=0.5),
        field_saturation=FractionThresholds(flag_at_or_above=1 / 6),
        low_signal_by_channel={},
    )


def _background_result(
    *,
    frame_count: int,
    c0_values: tuple[float | None, float | None],
    c1_values: tuple[float | None, float | None],
) -> QuantitativeBackgroundResult:
    estimates = []
    for channel, (value, standard_deviation) in (
        (Channel.C0, c0_values),
        (Channel.C1, c1_values),
    ):
        for frame_index in range(frame_count):
            estimates.append(
                FrameBackgroundEstimate(
                    channel=channel,
                    frame=FrameReference(frame_index=frame_index),
                    value=value,
                    pixel_count=4,
                    pixel_fraction=1.0,
                    mean=value,
                    median=value,
                    standard_deviation=standard_deviation,
                    method="synthetic_background",
                )
            )
    return QuantitativeBackgroundResult(
        estimates=tuple(estimates),
        method="synthetic_background",
    )


def _synthetic_pair(c0: np.ndarray, c1: np.ndarray) -> TiffPair:
    return TiffPair(
        position_key=PositionKey(capture="Capture 1", position="Position 1"),
        c0=_sequence(c0, Channel.C0),
        c1=_sequence(c1, Channel.C1),
    )


def _sequence(frames: np.ndarray, channel: Channel) -> TiffFrameSequence:
    suffix = channel.value
    parsed = parse_tiff_filename(
        Path(f"Capture 1 - Position 1_XY1782521382_Z0_T00_{suffix}.tif")
    )
    assert parsed is not None
    return TiffFrameSequence(
        parsed_file=parsed,
        frames=frames,
        metadata=TiffMetadata(
            page_count=int(frames.shape[0]) if frames.ndim > 0 else 0,
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
