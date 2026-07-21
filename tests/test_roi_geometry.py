import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import IssueSeverity
from funes.roi_geometry import (
    BorderTouchPolicy,
    RoiFilterStatus,
    RoiGeometryFilterConfig,
    filter_labeled_rois,
    filter_segmentation_rois,
)
from funes.segmentation_engine import SegmentationEngineRecord, SegmentationResult
from funes.segmentation_selection import (
    PROVISIONAL_WORKING_PROFILE,
    SegmentationMethodId,
)


class RoiGeometryFilteringTests(unittest.TestCase):
    def test_consumes_area32_segmentation_labels_and_preserves_provenance(self) -> None:
        labels = np.zeros((7, 7), dtype=np.int32)
        labels[1, 1] = 1
        labels[3:5, 3:6] = 2
        engine = SegmentationEngineRecord(
            name="kmeans_morphology",
            version="synthetic-test",
            model="classical_kmeans",
            method=SegmentationMethodId.KMEANS,
            profile=PROVISIONAL_WORKING_PROFILE,
            parameters={"minimum_object_area_pixels": 32},
            seeds={"random_state": 1729},
            package_versions={"numpy": np.__version__},
        )
        segmentation = SegmentationResult(
            label_image=labels,
            roi_count=2,
            engine=engine,
        )

        result = filter_segmentation_rois(
            segmentation,
            RoiGeometryFilterConfig(
                min_area_pixels=2,
                border_policy=BorderTouchPolicy.ACCEPT,
            ),
        )

        self.assertIs(result.source_segmentation, segmentation)
        self.assertIs(result.source_label_image, segmentation.label_image)
        self.assertIs(result.source_segmentation.engine, engine)
        self.assertEqual(
            result.source_segmentation.engine.profile,
            PROVISIONAL_WORKING_PROFILE,
        )
        self.assertEqual(
            result.source_segmentation.engine.parameters["minimum_object_area_pixels"],
            32,
        )
        self.assertEqual([record.geometry.label for record in result.records], [1, 2])
        self.assertFalse(np.any(result.filtered_label_image == 1))
        self.assertTrue(np.any(result.filtered_label_image == 2))
        self.assertEqual(tuple(np.unique(result.filtered_label_image)), (0, 2))

    def test_measures_geometry_for_accepted_labels_without_renumbering(self) -> None:
        labels = np.zeros((6, 7), dtype=np.int32)
        labels[1:3, 2:5] = 4

        result = filter_labeled_rois(labels)

        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(result.rejected_count, 0)
        np.testing.assert_array_equal(result.filtered_label_image, labels)
        record = result.records[0]
        self.assertEqual(record.status, RoiFilterStatus.ACCEPTED)
        self.assertEqual(record.geometry.label, 4)
        self.assertEqual(record.geometry.area_pixels, 6)
        self.assertEqual(record.geometry.bounding_box.min_row, 1)
        self.assertEqual(record.geometry.bounding_box.min_col, 2)
        self.assertEqual(record.geometry.bounding_box.max_row, 2)
        self.assertEqual(record.geometry.bounding_box.max_col, 4)
        self.assertAlmostEqual(record.geometry.centroid_row, 1.5)
        self.assertAlmostEqual(record.geometry.centroid_col, 3.0)
        self.assertFalse(record.geometry.touches_border)
        self.assertEqual(result.issues, ())

    def test_rejects_labels_outside_configured_area_limits(self) -> None:
        labels = np.zeros((8, 8), dtype=np.int32)
        labels[1, 1] = 1
        labels[2:4, 2:4] = 2
        labels[5:8, 4:8] = 3
        config = RoiGeometryFilterConfig(min_area_pixels=2, max_area_pixels=10)

        result = filter_labeled_rois(labels, config=config)

        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(result.rejected_count, 2)
        self.assertEqual(result.records[0].reasons, ("roi_area_below_minimum",))
        self.assertEqual(result.records[1].status, RoiFilterStatus.ACCEPTED)
        self.assertEqual(result.records[2].reasons, ("roi_area_above_maximum",))
        self.assertFalse(np.any(result.filtered_label_image == 1))
        self.assertTrue(np.any(result.filtered_label_image == 2))
        self.assertFalse(np.any(result.filtered_label_image == 3))
        self.assertEqual([issue.code for issue in result.issues], ["geometry_filter_rejected"] * 2)

    def test_border_touching_rois_can_be_flagged_without_removal(self) -> None:
        labels = np.zeros((4, 4), dtype=np.int32)
        labels[0:2, 1:3] = 1

        result = filter_labeled_rois(labels)

        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(result.rejected_count, 0)
        self.assertEqual(result.records[0].status, RoiFilterStatus.FLAGGED)
        self.assertEqual(result.records[0].reasons, ("roi_touches_border",))
        np.testing.assert_array_equal(result.filtered_label_image, labels)
        self.assertEqual(result.issues[0].code, "geometry_filter_flagged")

    def test_border_touching_rois_can_be_excluded_with_context(self) -> None:
        labels = np.zeros((4, 4), dtype=np.int32)
        labels[1:3, 0:2] = 1
        config = RoiGeometryFilterConfig(border_policy=BorderTouchPolicy.EXCLUDE)

        result = filter_labeled_rois(
            labels,
            config=config,
            context={"capture": "Capture 1", "position": "Position 2"},
        )

        self.assertEqual(result.accepted_count, 0)
        self.assertEqual(result.rejected_count, 1)
        self.assertEqual(result.records[0].status, RoiFilterStatus.REJECTED)
        self.assertEqual(result.records[0].reasons, ("roi_touches_border",))
        self.assertFalse(np.any(result.filtered_label_image == 1))
        self.assertEqual(result.issues[0].severity, IssueSeverity.WARNING)
        self.assertEqual(result.issues[0].context["capture"], "Capture 1")
        self.assertEqual(result.issues[0].context["border_policy"], "exclude")
        self.assertTrue(result.issues[0].context["touches_border"])

    def test_border_touching_rois_can_be_accepted_without_issue(self) -> None:
        labels = np.zeros((4, 4), dtype=np.int32)
        labels[0:2, 1:3] = 1
        config = RoiGeometryFilterConfig(border_policy=BorderTouchPolicy.ACCEPT)

        result = filter_labeled_rois(labels, config=config)

        self.assertEqual(result.records[0].status, RoiFilterStatus.ACCEPTED)
        self.assertEqual(result.issues, ())
        np.testing.assert_array_equal(result.filtered_label_image, labels)

    def test_config_rejects_invalid_limits(self) -> None:
        with self.assertRaisesRegex(ValueError, "min_area_pixels"):
            RoiGeometryFilterConfig(min_area_pixels=0)

        with self.assertRaisesRegex(ValueError, "max_area_pixels"):
            RoiGeometryFilterConfig(max_area_pixels=0)

        with self.assertRaisesRegex(ValueError, "less than or equal"):
            RoiGeometryFilterConfig(min_area_pixels=5, max_area_pixels=4)

    def test_rejects_invalid_label_images(self) -> None:
        with self.assertRaisesRegex(TypeError, "SegmentationResult"):
            filter_segmentation_rois(np.zeros((2, 2), dtype=np.int32))  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "non-empty 2D"):
            filter_labeled_rois(np.zeros((1, 2, 2), dtype=np.int32))

        with self.assertRaisesRegex(ValueError, "integer"):
            filter_labeled_rois(np.zeros((2, 2), dtype=np.float64))

        with self.assertRaisesRegex(ValueError, "zero or greater"):
            filter_labeled_rois(np.array([[0, -1]], dtype=np.int32))


if __name__ == "__main__":
    unittest.main()
