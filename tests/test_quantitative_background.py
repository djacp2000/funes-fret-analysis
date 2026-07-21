import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import Channel, IssueSeverity, PositionKey
from funes.file_discovery import parse_tiff_filename
from funes.quantitative_background import (
    BackgroundPixelSource,
    PercentileQuantitativeBackgroundEstimator,
    QuantitativeBackgroundConfig,
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
from funes.tiff_reader import TiffFrameSequence, TiffMetadata, TiffPair


class QuantitativeBackgroundTests(unittest.TestCase):
    def test_consumes_filtered_area32_roi_support_without_relabeling(self) -> None:
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
        strategy = PercentileQuantitativeBackgroundEstimator(
            QuantitativeBackgroundConfig(background_percentile=100)
        )

        result = estimate_quantitative_background(
            _synthetic_pair(c0=c0, c1=c1),
            roi_label_image=roi_filtering.filtered_label_image,
            strategy=strategy,
        )

        self.assertIs(roi_filtering.source_segmentation, segmentation)
        self.assertEqual(
            roi_filtering.source_segmentation.engine.profile,
            PROVISIONAL_WORKING_PROFILE,
        )
        self.assertEqual(
            roi_filtering.source_segmentation.engine.parameters[
                "minimum_object_area_pixels"
            ],
            32,
        )
        self.assertEqual(tuple(np.unique(roi_filtering.filtered_label_image)), (0, 2))
        self.assertEqual(result.estimate_for(Channel.C0, 0).pixel_count, 21)
        self.assertEqual(result.estimate_for(Channel.C0, 0).value, 50.0)
        self.assertEqual(result.estimate_for(Channel.C1, 0).value, 60.0)

    def test_estimates_non_roi_background_by_channel_and_frame(self) -> None:
        pair = _synthetic_pair(
            c0=np.array(
                [
                    [[10, 10, 10], [10, 100, 10], [10, 10, 10]],
                    [[20, 20, 20], [20, 200, 20], [20, 20, 20]],
                ],
                dtype=np.uint16,
            ),
            c1=np.array(
                [
                    [[30, 30, 30], [30, 300, 30], [30, 30, 30]],
                    [[40, 40, 40], [40, 400, 40], [40, 40, 40]],
                ],
                dtype=np.uint16,
            ),
        )
        labels = np.zeros((3, 3), dtype=np.int32)
        labels[1, 1] = 7
        config = QuantitativeBackgroundConfig(background_percentile=50)
        strategy = PercentileQuantitativeBackgroundEstimator(config)

        result = estimate_quantitative_background(
            pair,
            roi_label_image=labels,
            strategy=strategy,
            context={"capture": "Capture 1", "position": "Position 1"},
        )

        self.assertEqual(result.method, "percentile_quantitative_background")
        self.assertEqual(len(result.estimates), 4)
        self.assertEqual(result.issues, ())
        self.assertEqual(result.estimate_for(Channel.C0, 0).value, 10.0)
        self.assertEqual(result.estimate_for(Channel.C0, 1).value, 20.0)
        self.assertEqual(result.estimate_for(Channel.C1, 0).value, 30.0)
        self.assertEqual(result.estimate_for(Channel.C1, 1).value, 40.0)
        estimate = result.estimate_for(Channel.C1, 0)
        self.assertEqual(estimate.pixel_count, 8)
        self.assertAlmostEqual(estimate.pixel_fraction, 8 / 9)
        self.assertEqual(estimate.parameters["pixel_source"], "non_roi_pixels")
        self.assertEqual(estimate.parameters["purpose"], "quantitative_channel_correction")

    def test_full_frame_source_does_not_require_roi_labels(self) -> None:
        pair = _synthetic_pair(
            c0=np.array([[[0, 10], [20, 30]]], dtype=np.uint16),
            c1=np.array([[[5, 15], [25, 35]]], dtype=np.uint16),
        )
        strategy = PercentileQuantitativeBackgroundEstimator(
            QuantitativeBackgroundConfig(
                background_percentile=50,
                pixel_source=BackgroundPixelSource.FULL_FRAME,
            )
        )

        result = estimate_quantitative_background(pair, strategy=strategy)

        self.assertEqual(result.estimate_for(Channel.C0, 0).value, 15.0)
        self.assertEqual(result.estimate_for(Channel.C1, 0).value, 20.0)
        self.assertEqual(result.estimate_for(Channel.C0, 0).pixel_count, 4)
        self.assertEqual(result.parameters["pixel_source"], "full_frame")

    def test_reports_insufficient_background_pixels_without_crashing(self) -> None:
        pair = _synthetic_pair(
            c0=np.ones((1, 2, 2), dtype=np.uint16),
            c1=np.ones((1, 2, 2), dtype=np.uint16) * 2,
        )
        labels = np.ones((2, 2), dtype=np.int32)

        result = estimate_quantitative_background(
            pair,
            roi_label_image=labels,
            context={"capture": "Capture 9"},
        )

        self.assertEqual(len(result.issues), 2)
        self.assertEqual(
            {issue.code for issue in result.issues},
            {"quantitative_background_insufficient_pixels"},
        )
        self.assertTrue(all(issue.severity is IssueSeverity.ERROR for issue in result.issues))
        self.assertEqual(result.issues[0].context["capture"], "Capture 9")
        self.assertIsNone(result.estimate_for(Channel.C0, 0).value)
        self.assertEqual(result.estimate_for(Channel.C0, 0).pixel_count, 0)

    def test_non_roi_source_requires_compatible_integer_label_image(self) -> None:
        pair = _synthetic_pair(
            c0=np.zeros((1, 3, 3), dtype=np.uint16),
            c1=np.zeros((1, 3, 3), dtype=np.uint16),
        )

        with self.assertRaisesRegex(ValueError, "requires a ROI label image"):
            estimate_quantitative_background(pair)

        with self.assertRaisesRegex(ValueError, "shape"):
            estimate_quantitative_background(
                pair,
                roi_label_image=np.zeros((2, 2), dtype=np.int32),
            )

        with self.assertRaisesRegex(ValueError, "integer"):
            estimate_quantitative_background(
                pair,
                roi_label_image=np.zeros((3, 3), dtype=np.float64),
            )

        with self.assertRaisesRegex(ValueError, "zero or greater"):
            estimate_quantitative_background(
                pair,
                roi_label_image=np.array([[0, -1, 0], [0, 0, 0], [0, 0, 0]], dtype=np.int32),
            )

    def test_rejects_invalid_config_and_frame_stacks(self) -> None:
        with self.assertRaisesRegex(ValueError, "background_percentile"):
            QuantitativeBackgroundConfig(background_percentile=101)

        with self.assertRaisesRegex(ValueError, "minimum_background_pixels"):
            QuantitativeBackgroundConfig(minimum_background_pixels=0)

        pair = _synthetic_pair(
            c0=np.array([[[1.0, np.nan]]], dtype=np.float64),
            c1=np.ones((1, 1, 2), dtype=np.float64),
        )
        strategy = PercentileQuantitativeBackgroundEstimator(
            QuantitativeBackgroundConfig(pixel_source=BackgroundPixelSource.FULL_FRAME)
        )

        with self.assertRaisesRegex(ValueError, "finite pixel values"):
            estimate_quantitative_background(pair, strategy=strategy)

    def test_missing_estimate_lookup_is_actionable(self) -> None:
        pair = _synthetic_pair(
            c0=np.zeros((1, 2, 2), dtype=np.uint16),
            c1=np.zeros((1, 2, 2), dtype=np.uint16),
        )
        strategy = PercentileQuantitativeBackgroundEstimator(
            QuantitativeBackgroundConfig(pixel_source=BackgroundPixelSource.FULL_FRAME)
        )

        result = estimate_quantitative_background(pair, strategy=strategy)

        with self.assertRaisesRegex(KeyError, "C0 frame 99"):
            result.estimate_for(Channel.C0, 99)


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
