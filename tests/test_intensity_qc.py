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
    ConfiguredIntensityQcEvaluator,
    FractionThresholds,
    IntensityQcConfig,
    IntensityQcScope,
    IntensityQcStatus,
    LowSignalThresholds,
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
from funes.segmentation_selection import PROVISIONAL_WORKING_PROFILE, SegmentationMethodId
from funes.tiff_reader import TiffFrameSequence, TiffMetadata, TiffPair


class IntensityQcTests(unittest.TestCase):
    def test_consumes_filtered_roi_result_and_module10_background_without_relabeling(self) -> None:
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

        config = _config()
        tracking_strategy = _IdentityCheckingIntensityQcStrategy(
            expected_labels=roi_filtering.filtered_label_image,
            expected_background=background,
            delegate=ConfiguredIntensityQcEvaluator(config),
        )
        result = evaluate_filtered_roi_intensity_qc(
            pair,
            roi_filtering,
            background,
            config,
            strategy=tracking_strategy,
        )

        self.assertTrue(tracking_strategy.received_exact_labels)
        self.assertTrue(tracking_strategy.received_exact_background)
        self.assertIs(roi_filtering.source_segmentation, segmentation)
        self.assertEqual(tuple(np.unique(roi_filtering.filtered_label_image)), (0, 2))
        self.assertEqual(
            {
                record.roi_label
                for record in result.records
                if record.scope in (IntensityQcScope.ROI_FRAME, IntensityQcScope.ROI)
            },
            {2},
        )
        self.assertEqual(result.records_for(roi_label=1), ())
        c0_roi = result.records_for(
            scope=IntensityQcScope.ROI_FRAME,
            channel=Channel.C0,
            frame_index=0,
            roi_label=2,
        )[0]
        c1_roi = result.records_for(
            scope=IntensityQcScope.ROI_FRAME,
            channel=Channel.C1,
            frame_index=0,
            roi_label=2,
        )[0]
        self.assertEqual(
            result.parameters["quantitative_background_method"],
            background.method,
        )
        self.assertEqual(c0_roi.metrics["background_method"], background.method)
        self.assertEqual(c0_roi.metrics["background_value"], 50.0)
        self.assertEqual(c0_roi.metrics["background_corrected_mean"], 150.0)
        self.assertEqual(c1_roi.metrics["background_value"], 60.0)
        self.assertEqual(c1_roi.metrics["background_corrected_mean"], 160.0)

    def test_flags_saturation_with_explicit_camera_profile(self) -> None:
        pair = _synthetic_pair(
            c0=np.array([[[0, 100, 100], [0, 4095, 10]]], dtype=np.uint16),
            c1=np.array([[[0, 100, 100], [0, 100, 10]]], dtype=np.uint16),
        )
        labels = np.array([[0, 1, 1], [0, 1, 1]], dtype=np.int32)
        background = _background_result(
            frame_count=1,
            c0_values=(10.0, 2.0),
            c1_values=(10.0, 2.0),
        )
        config = _config(
            roi_saturation=FractionThresholds(flag_at_or_above=0.25, exclude_at_or_above=0.75),
            field_saturation=FractionThresholds(flag_at_or_above=0.10),
        )

        result = evaluate_intensity_qc(pair, labels, background, config)

        c0_roi = result.records_for(
            scope=IntensityQcScope.ROI_FRAME,
            channel=Channel.C0,
            frame_index=0,
            roi_label=1,
        )[0]
        c0_field = result.records_for(
            scope=IntensityQcScope.FIELD_FRAME,
            channel=Channel.C0,
            frame_index=0,
        )[0]
        roi = result.records_for(scope=IntensityQcScope.ROI, roi_label=1)[0]
        field = result.records_for(scope=IntensityQcScope.FIELD)[0]

        self.assertEqual(c0_roi.status, IntensityQcStatus.FLAGGED)
        self.assertEqual(c0_roi.reasons, ("roi_saturation_fraction_flagged",))
        self.assertEqual(c0_roi.metrics["saturated_pixel_count"], 1)
        self.assertAlmostEqual(c0_roi.metrics["saturated_pixel_fraction"], 0.25)
        self.assertEqual(c0_roi.metrics["camera_profile"], "synthetic_12_bit")
        self.assertEqual(c0_field.status, IntensityQcStatus.FLAGGED)
        self.assertEqual(c0_field.reasons, ("field_saturation_fraction_flagged",))
        self.assertEqual(roi.status, IntensityQcStatus.FLAGGED)
        self.assertEqual(field.status, IntensityQcStatus.FLAGGED)
        self.assertFalse(result.has_exclusions)

    def test_excludes_low_signal_using_background_noise(self) -> None:
        pair = _synthetic_pair(
            c0=np.array([[[8, 10], [10, 8]]], dtype=np.uint16),
            c1=np.array([[[40, 50], [50, 40]]], dtype=np.uint16),
        )
        labels = np.array([[1, 1], [0, 0]], dtype=np.int32)
        background = _background_result(
            frame_count=1,
            c0_values=(8.0, 2.0),
            c1_values=(8.0, 2.0),
        )
        config = _config(
            low_signal_by_channel={
                Channel.C0: LowSignalThresholds(
                    flag_below_snr=3.0,
                    exclude_below_snr=1.5,
                )
            }
        )

        result = evaluate_intensity_qc(pair, labels, background, config)

        c0_roi = result.records_for(
            scope=IntensityQcScope.ROI_FRAME,
            channel=Channel.C0,
            frame_index=0,
            roi_label=1,
        )[0]
        c1_roi = result.records_for(
            scope=IntensityQcScope.ROI_FRAME,
            channel=Channel.C1,
            frame_index=0,
            roi_label=1,
        )[0]

        self.assertEqual(c0_roi.status, IntensityQcStatus.EXCLUDED)
        self.assertEqual(c0_roi.reasons, ("low_signal_snr_excluded",))
        self.assertAlmostEqual(c0_roi.metrics["background_corrected_mean"], 1.0)
        self.assertAlmostEqual(c0_roi.metrics["signal_to_background_noise"], 0.5)
        self.assertEqual(c1_roi.status, IntensityQcStatus.PASS)
        self.assertEqual(
            result.records_for(scope=IntensityQcScope.FIELD)[0].status,
            IntensityQcStatus.PASS,
        )
        self.assertTrue(result.has_exclusions)

    def test_reports_low_signal_that_cannot_be_assessed(self) -> None:
        pair = _synthetic_pair(
            c0=np.array([[[10, 10], [0, 0]]], dtype=np.uint16),
            c1=np.array([[[20, 20], [0, 0]]], dtype=np.uint16),
        )
        labels = np.array([[1, 1], [0, 0]], dtype=np.int32)
        background = QuantitativeBackgroundResult(
            estimates=(
                FrameBackgroundEstimate(
                    channel=Channel.C0,
                    frame=FrameReference(frame_index=0),
                    value=10.0,
                    pixel_count=2,
                    pixel_fraction=0.5,
                    mean=10.0,
                    median=10.0,
                    standard_deviation=0.0,
                    method="synthetic_background",
                ),
            ),
            method="synthetic_background",
        )
        config = _config(
            low_signal_by_channel={
                Channel.C0: LowSignalThresholds(flag_below_snr=3.0),
                Channel.C1: LowSignalThresholds(flag_below_snr=3.0),
            }
        )

        result = evaluate_intensity_qc(
            pair,
            labels,
            background,
            config,
            context={"capture": "Capture 1"},
        )

        self.assertEqual(
            [issue.code for issue in result.issues],
            [
                "intensity_qc_low_signal_not_assessed",
                "intensity_qc_missing_background_estimate",
            ],
        )
        self.assertTrue(all(issue.severity in (IssueSeverity.WARNING, IssueSeverity.ERROR) for issue in result.issues))
        self.assertEqual(result.issues[0].context["reason"], "background_noise_not_positive")
        self.assertEqual(result.issues[0].context["capture"], "Capture 1")

    def test_rejects_invalid_config_and_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "saturation_threshold"):
            CameraSaturationProfile(name="bad", saturation_threshold=0)

        with self.assertRaisesRegex(ValueError, "exclude_at_or_above"):
            FractionThresholds(flag_at_or_above=0.5, exclude_at_or_above=0.25)

        with self.assertRaisesRegex(ValueError, "exclude_below_snr"):
            LowSignalThresholds(flag_below_snr=2.0, exclude_below_snr=3.0)

        pair = _synthetic_pair(
            c0=np.zeros((1, 2, 2), dtype=np.uint16),
            c1=np.zeros((1, 2, 2), dtype=np.uint16),
        )
        background = _background_result(frame_count=1, c0_values=(0.0, 1.0), c1_values=(0.0, 1.0))
        config = _config()

        with self.assertRaisesRegex(ValueError, "shape"):
            evaluate_intensity_qc(pair, np.zeros((3, 3), dtype=np.int32), background, config)

        with self.assertRaisesRegex(ValueError, "integer"):
            evaluate_intensity_qc(pair, np.zeros((2, 2), dtype=np.float64), background, config)

        bad_pair = _synthetic_pair(
            c0=np.array([[[np.nan]]], dtype=np.float64),
            c1=np.zeros((1, 1, 1), dtype=np.float64),
        )
        with self.assertRaisesRegex(ValueError, "finite pixel values"):
            evaluate_intensity_qc(
                bad_pair,
                np.array([[1]], dtype=np.int32),
                background,
                config,
            )


class _IdentityCheckingIntensityQcStrategy:
    name = "identity_checking_intensity_qc"

    def __init__(
        self,
        *,
        expected_labels: np.ndarray,
        expected_background: QuantitativeBackgroundResult,
        delegate: ConfiguredIntensityQcEvaluator,
    ) -> None:
        self.expected_labels = expected_labels
        self.expected_background = expected_background
        self.delegate = delegate
        self.received_exact_labels = False
        self.received_exact_background = False

    def evaluate(
        self,
        pair: TiffPair,
        roi_label_image: np.ndarray,
        background: QuantitativeBackgroundResult,
        context: dict[str, object] | None = None,
    ):
        self.received_exact_labels = roi_label_image is self.expected_labels
        self.received_exact_background = background is self.expected_background
        return self.delegate.evaluate(
            pair,
            roi_label_image,
            background,
            context=context,
        )


def _config(
    roi_saturation: FractionThresholds | None = None,
    field_saturation: FractionThresholds | None = None,
    low_signal_by_channel: dict[Channel, LowSignalThresholds] | None = None,
) -> IntensityQcConfig:
    return IntensityQcConfig(
        camera_profile=CameraSaturationProfile(
            name="synthetic_12_bit",
            saturation_threshold=4095,
        ),
        roi_saturation=roi_saturation or FractionThresholds(exclude_at_or_above=1.0),
        field_saturation=field_saturation or FractionThresholds(exclude_at_or_above=1.0),
        low_signal_by_channel=low_signal_by_channel or {},
    )


def _background_result(
    *,
    frame_count: int,
    c0_values: tuple[float, float],
    c1_values: tuple[float, float],
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
