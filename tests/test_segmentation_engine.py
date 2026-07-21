import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import IssueSeverity
from funes.segmentation_engine import (
    PercentileThresholdSegmentationConfig,
    PercentileThresholdSegmentationEngine,
    SegmentationEngineRecord,
    SegmentationResult,
    segment_first_frame,
)
from funes.segmentation_selection import PROVISIONAL_WORKING_PROFILE


class SegmentationEngineTests(unittest.TestCase):
    def test_default_engine_is_provisional_kmeans_area32_and_segments_components(self) -> None:
        frame = np.zeros((50, 50), dtype=np.float64)
        frame[5:15, 5:15] = 20.0
        frame[30:40, 30:40] = 40.0

        result = segment_first_frame(frame)

        self.assertEqual(result.roi_count, 2)
        self.assertEqual(result.label_image.dtype, np.int32)
        self.assertEqual(set(np.unique(result.label_image)), {0, 1, 2})
        self.assertEqual(result.engine.method.value, "kmeans")
        self.assertEqual(result.engine.profile, PROVISIONAL_WORKING_PROFILE)
        self.assertEqual(result.engine.parameters["minimum_object_area_pixels"], 32)
        self.assertEqual(result.engine.seeds["random_state"], 1729)
        self.assertEqual(result.issues, ())

    def test_engine_record_preserves_version_model_and_parameters(self) -> None:
        engine = PercentileThresholdSegmentationEngine(
            config=PercentileThresholdSegmentationConfig(
                threshold_percentile=75.0,
                connectivity=4,
            )
        )
        frame = np.zeros((5, 5), dtype=np.uint16)
        frame[2, 2] = 100

        result = segment_first_frame(frame, engine=engine)

        self.assertEqual(result.engine.name, "percentile_threshold_connected_components")
        self.assertEqual(result.engine.version, "0.1")
        self.assertEqual(result.engine.model, "classical_percentile_threshold")
        self.assertEqual(result.engine.parameters["threshold_percentile"], 75.0)
        self.assertEqual(result.engine.parameters["connectivity"], 4)
        self.assertEqual(result.engine.parameters["threshold_value"], 0.0)

    def test_connectivity_controls_diagonal_component_merging(self) -> None:
        frame = np.zeros((3, 3), dtype=np.uint16)
        frame[0, 0] = 10
        frame[1, 1] = 10
        config = PercentileThresholdSegmentationConfig(threshold_percentile=50.0)

        four_connected = segment_first_frame(
            frame,
            engine=PercentileThresholdSegmentationEngine(
                config=PercentileThresholdSegmentationConfig(
                    threshold_percentile=config.threshold_percentile,
                    connectivity=4,
                )
            ),
        )
        eight_connected = segment_first_frame(
            frame,
            engine=PercentileThresholdSegmentationEngine(
                config=PercentileThresholdSegmentationConfig(
                    threshold_percentile=config.threshold_percentile,
                    connectivity=8,
                )
            ),
        )

        self.assertEqual(four_connected.roi_count, 2)
        self.assertEqual(eight_connected.roi_count, 1)

    def test_no_foreground_warning_preserves_context(self) -> None:
        result = segment_first_frame(
            np.zeros((4, 4), dtype=np.uint16),
            engine=PercentileThresholdSegmentationEngine(),
            context={"capture": "Capture 1", "position": "Position 2"},
        )

        self.assertEqual(result.roi_count, 0)
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].code, "segmentation_no_foreground")
        self.assertEqual(result.issues[0].severity, IssueSeverity.WARNING)
        self.assertEqual(result.issues[0].context["capture"], "Capture 1")
        self.assertEqual(result.issues[0].context["threshold_value"], 0.0)

    def test_segment_first_frame_accepts_replaceable_engine(self) -> None:
        engine = _ConstantEngine()

        result = segment_first_frame(np.zeros((2, 2), dtype=np.uint16), engine=engine)

        self.assertEqual(result.engine.name, "constant_test_engine")
        self.assertEqual(result.roi_count, 1)
        self.assertEqual(int(result.label_image[0, 0]), 1)

    def test_config_rejects_invalid_threshold_and_connectivity(self) -> None:
        with self.assertRaisesRegex(ValueError, "threshold_percentile"):
            PercentileThresholdSegmentationConfig(threshold_percentile=101)

        with self.assertRaisesRegex(ValueError, "connectivity"):
            PercentileThresholdSegmentationConfig(connectivity=6)

    def test_engine_rejects_non_2d_or_non_finite_frames(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty 2D"):
            segment_first_frame(np.zeros((1, 2, 2), dtype=np.uint16))

        with self.assertRaisesRegex(ValueError, "finite"):
            segment_first_frame(np.array([[1.0, np.inf]]))

    def test_result_rejects_invalid_label_images(self) -> None:
        record = SegmentationEngineRecord(
            name="test",
            version="0",
            model=None,
        )
        with self.assertRaisesRegex(ValueError, "integer"):
            SegmentationResult(
                label_image=np.zeros((2, 2), dtype=np.float64),
                roi_count=0,
                engine=record,
            )

        with self.assertRaisesRegex(ValueError, "zero or greater"):
            SegmentationResult(
                label_image=np.array([[0, -1]], dtype=np.int32),
                roi_count=0,
                engine=record,
            )

        with self.assertRaisesRegex(ValueError, "canonical and consecutive"):
            SegmentationResult(
                label_image=np.array([[0, 3]], dtype=np.int32),
                roi_count=0,
                engine=record,
            )

    def test_result_is_canonical_read_only_int32_for_downstream_consumers(self) -> None:
        source = np.array([[0, 1], [2, 2]], dtype=np.int64)
        result = SegmentationResult(
            label_image=source,
            roi_count=2,
            engine=SegmentationEngineRecord(name="test", version="1", model=None),
        )

        source[0, 1] = 0
        self.assertEqual(result.label_image.dtype, np.int32)
        self.assertEqual(result.roi_labels, (1, 2))
        self.assertEqual(int(result.label_image[0, 1]), 1)
        self.assertFalse(result.label_image.flags.writeable)
        with self.assertRaises(ValueError):
            result.label_image[0, 1] = 0

    def test_segment_first_frame_rejects_output_with_wrong_spatial_shape(self) -> None:
        with self.assertRaisesRegex(ValueError, "shape must match"):
            segment_first_frame(
                np.zeros((3, 3), dtype=np.uint16),
                engine=_WrongShapeEngine(),
            )


class _ConstantEngine:
    @property
    def record(self) -> SegmentationEngineRecord:
        return SegmentationEngineRecord(
            name="constant_test_engine",
            version="1",
            model="constant",
        )

    def segment(
        self,
        frame: np.ndarray,
        context: dict[str, object] | None = None,
    ) -> SegmentationResult:
        labels = np.zeros(np.asarray(frame).shape, dtype=np.int32)
        labels[0, 0] = 1
        return SegmentationResult(
            label_image=labels,
            roi_count=1,
            engine=self.record,
        )


class _WrongShapeEngine(_ConstantEngine):
    def segment(
        self,
        frame: np.ndarray,
        context: dict[str, object] | None = None,
    ) -> SegmentationResult:
        return SegmentationResult(
            label_image=np.array([[1]], dtype=np.int32),
            roi_count=1,
            engine=self.record,
        )


if __name__ == "__main__":
    unittest.main()
