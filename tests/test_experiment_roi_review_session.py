import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import PositionKey
from funes.experiment_roi_review import (
    ExperimentPositionReview,
    ExperimentPositionReviewMode,
    ExperimentRoiReviewOrchestrator,
)
from funes.experiment_roi_review_session import (
    ExperimentRoiReviewSession,
    PositionRoiReviewMaterial,
)
from funes.file_discovery import parse_tiff_filename
from funes.roi_geometry import RoiGeometryFilterConfig, filter_labeled_rois
from funes.roi_review import load_interactive_roi_review_decision
from funes.segmentation_selection import SegmentationReviewStatus
from funes.tiff_reader import TiffFrameSequence, TiffMetadata, TiffPair


class ExperimentRoiReviewSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.a1 = PositionKey("Capture 1", "Position 1", "Experiment A")
        self.a2 = PositionKey("Capture 1", "Position 2", "Experiment A")
        self.b1 = PositionKey("Capture 1", "Position 1", "Experiment B")
        review_a = ExperimentPositionReview(
            "Experiment A",
            (self.a1, self.a2),
            ExperimentPositionReviewMode.REVIEW_SELECTED,
            (self.a1,),
        )
        review_b = ExperimentPositionReview(
            "Experiment B",
            (self.b1,),
            ExperimentPositionReviewMode.REVIEW_ALL,
        )
        self.orchestrator = ExperimentRoiReviewOrchestrator((review_a, review_b))
        labels = np.zeros((6, 7), dtype=np.int32)
        labels[1:4, 1:4] = 1
        self.filtering = filter_labeled_rois(
            labels,
            RoiGeometryFilterConfig(min_area_pixels=1),
        )

    def test_snapshot_session_reports_available_and_missing_manual_targets(self) -> None:
        material = PositionRoiReviewMaterial(_pair(self.a1), self.filtering)
        original = ExperimentRoiReviewSession(self.orchestrator)

        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "review_state.json"
            original.export_snapshot(snapshot)
            opened = ExperimentRoiReviewSession.from_snapshot(snapshot, (material,))

        self.assertEqual(opened.pending_manual_positions, (self.a1, self.b1))
        self.assertEqual(opened.available_pending_positions, (self.a1,))
        self.assertEqual(opened.missing_pending_positions, (self.b1,))
        self.assertIsNone(
            opened.orchestrator.for_experiment("Experiment A")
            .review_state.global_approval
        )

    def test_one_position_viewer_decision_and_snapshot_remain_read_only(self) -> None:
        material = PositionRoiReviewMaterial(
            _pair(self.a1, frame_count=4), self.filtering
        )
        session = ExperimentRoiReviewSession(self.orchestrator, (material,))
        source_before = self.filtering.source_label_image.copy()
        filtered_before = self.filtering.filtered_label_image.copy()

        with tempfile.TemporaryDirectory() as tmp, patch(
            "funes.tiff_reader.read_tiff_sequence"
        ) as read_tiff, patch(
            "funes.segmentation_registry.segment_configured_first_frame"
        ) as segment:
            root = Path(tmp)
            viewer = session.export_position_viewer(
                self.a1, root / "position.html"
            )
            data = _viewer_data(viewer.path.read_text(encoding="utf-8"))
            data["review_record"]["inspection"] = {
                "inspector": "synthetic-reviewer",
                "inspected_at": None,
                "note": "Inspected existing fixed ROIs.",
            }
            decision_path = root / viewer.review_filename
            decision_path.write_text(
                json.dumps(data["review_record"]), encoding="utf-8"
            )
            decision = load_interactive_roi_review_decision(decision_path)
            updated = session.record_inspection(self.a1, decision)
            updated.export_snapshot(root / "updated.json")
            restored = ExperimentRoiReviewSession.from_snapshot(root / "updated.json")

        read_tiff.assert_not_called()
        segment.assert_not_called()
        self.assertEqual(viewer.frame_count, 4)
        self.assertEqual(
            restored.orchestrator.query(self.a1).status,
            SegmentationReviewStatus.MANUALLY_REVIEWED,
        )
        self.assertEqual(
            restored.orchestrator.query(self.a2).status,
            SegmentationReviewStatus.UNREVIEWED,
        )
        self.assertIsNone(
            restored.orchestrator.for_experiment("Experiment A")
            .review_state.global_approval
        )
        self.assertFalse(hasattr(session, "approve_remaining"))
        self.assertTrue(np.array_equal(self.filtering.source_label_image, source_before))
        self.assertTrue(
            np.array_equal(self.filtering.filtered_label_image, filtered_before)
        )

    def test_material_registry_rejects_duplicate_and_out_of_scope_positions(self) -> None:
        material = PositionRoiReviewMaterial(_pair(self.a1), self.filtering)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ExperimentRoiReviewSession(self.orchestrator, (material, material))

        outside = PositionKey("Capture 9", "Position 9", "Experiment A")
        with self.assertRaisesRegex(ValueError, "not registered"):
            ExperimentRoiReviewSession(
                self.orchestrator,
                (PositionRoiReviewMaterial(_pair(outside), self.filtering),),
            )

    def test_missing_material_and_cross_experiment_requests_fail_closed(self) -> None:
        session = ExperimentRoiReviewSession(
            self.orchestrator,
            (PositionRoiReviewMaterial(_pair(self.a1), self.filtering),),
        )
        with self.assertRaisesRegex(ValueError, "no review material"):
            session.material_for(self.b1)
        unknown_experiment = PositionKey("Capture 1", "Position 1", "Experiment C")
        with self.assertRaisesRegex(ValueError, "not registered"):
            session.material_for(unknown_experiment)

    def test_material_requires_typed_inputs_and_assigned_experiment(self) -> None:
        with self.assertRaisesRegex(TypeError, "TiffPair"):
            PositionRoiReviewMaterial(object(), self.filtering)
        unassigned = PositionKey("Capture 1", "Position 1")
        with self.assertRaisesRegex(ValueError, "assigned experiment"):
            PositionRoiReviewMaterial(_pair(unassigned), self.filtering)


def _pair(position_key: PositionKey, frame_count: int = 3) -> TiffPair:
    pixels = np.arange(frame_count * 42, dtype=np.uint16).reshape(
        frame_count, 6, 7
    )
    metadata = TiffMetadata(
        page_count=frame_count,
        series_axes="TYX",
        series_shape=tuple(pixels.shape),
        imagej_metadata=None,
        ome_metadata=None,
        page_descriptions=(),
        first_page_tags={},
    )
    parsed_c0 = parse_tiff_filename(
        f"{position_key.capture} - {position_key.position}_XY1_Z0_T00_C0.tif"
    )
    parsed_c1 = parse_tiff_filename(
        f"{position_key.capture} - {position_key.position}_XY1_Z0_T00_C1.tif"
    )
    assert parsed_c0 is not None and parsed_c1 is not None
    return TiffPair(
        position_key=position_key,
        c0=TiffFrameSequence(parsed_c0, pixels, metadata),
        c1=TiffFrameSequence(parsed_c1, pixels + 50, metadata),
    )


def _viewer_data(html: str) -> dict:
    match = re.search(
        r'<script id="viewer-data" type="application/json">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


if __name__ == "__main__":
    unittest.main()
