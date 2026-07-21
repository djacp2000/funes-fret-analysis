import unittest
from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.segmentation_preprocessing import (
    IdentitySegmentationPreprocessor,
    PercentileBackgroundSubtractionConfig,
    PercentileBackgroundSubtractionPreprocessor,
    preprocess_for_segmentation,
)


class SegmentationPreprocessingTests(unittest.TestCase):
    def test_default_identity_preprocessor_preserves_pixels_as_float(self) -> None:
        frame = np.array([[1, 2], [3, 4]], dtype=np.uint16)

        result = preprocess_for_segmentation(frame)

        np.testing.assert_array_equal(result.processed_frame, frame.astype(np.float64))
        self.assertEqual(result.method, "identity_segmentation_preprocessing")
        self.assertIsNone(result.background_estimate)
        self.assertTrue(result.parameters["preserves_pixel_values"])
        self.assertEqual(result.issues, ())

    def test_percentile_background_subtraction_clips_negative_values(self) -> None:
        frame = np.array(
            [
                [10, 10, 10, 10],
                [10, 50, 60, 10],
                [10, 80, 90, 10],
                [10, 10, 10, 10],
            ],
            dtype=np.uint16,
        )
        strategy = PercentileBackgroundSubtractionPreprocessor(
            PercentileBackgroundSubtractionConfig(background_percentile=25)
        )

        result = preprocess_for_segmentation(frame, strategy=strategy)

        self.assertEqual(result.background_estimate.value, 10.0)
        self.assertEqual(
            result.background_estimate.parameters["purpose"],
            "segmentation_preprocessing_only",
        )
        self.assertEqual(result.processed_frame.dtype, np.float64)
        self.assertEqual(float(result.processed_frame.min()), 0.0)
        self.assertEqual(float(result.processed_frame[2, 2]), 80.0)

    def test_percentile_background_subtraction_can_preserve_negative_values(self) -> None:
        frame = np.array([[0, 10], [20, 30]], dtype=np.uint16)
        strategy = PercentileBackgroundSubtractionPreprocessor(
            PercentileBackgroundSubtractionConfig(
                background_percentile=50,
                clip_negative=False,
            )
        )

        result = strategy.preprocess(frame)

        self.assertEqual(result.background_estimate.value, 15.0)
        self.assertEqual(float(result.processed_frame[0, 0]), -15.0)

    def test_low_dynamic_range_warning_preserves_context(self) -> None:
        frame = np.full((3, 3), 42, dtype=np.uint16)
        strategy = PercentileBackgroundSubtractionPreprocessor(
            PercentileBackgroundSubtractionConfig(low_dynamic_range_threshold=1.0)
        )

        result = strategy.preprocess(
            frame,
            context={"capture": "Capture 1", "position": "Position 2"},
        )

        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].code, "segmentation_preprocessing_low_dynamic_range")
        self.assertEqual(result.issues[0].context["capture"], "Capture 1")
        self.assertEqual(result.issues[0].context["observed_dynamic_range"], 0.0)

    def test_rejects_invalid_percentile_config(self) -> None:
        with self.assertRaisesRegex(ValueError, "background_percentile"):
            PercentileBackgroundSubtractionConfig(background_percentile=101)

    def test_rejects_non_2d_or_non_finite_frames(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty 2D"):
            IdentitySegmentationPreprocessor().preprocess(
                np.zeros((1, 2, 2), dtype=np.uint16)
            )

        with self.assertRaisesRegex(ValueError, "finite"):
            IdentitySegmentationPreprocessor().preprocess(np.array([[1.0, np.nan]]))


if __name__ == "__main__":
    unittest.main()
