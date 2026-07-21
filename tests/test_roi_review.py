import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import PositionKey
from funes.file_discovery import parse_tiff_filename
from funes.roi_geometry import (
    BorderTouchPolicy,
    RoiGeometryFilterConfig,
    filter_labeled_rois,
)
from funes.roi_review import (
    InteractiveRoiReviewConfig,
    apply_interactive_roi_review_decision,
    export_interactive_roi_review_html,
    load_interactive_roi_review_decision,
)
from funes.segmentation_review import SegmentationReviewState
from funes.segmentation_selection import (
    SegmentationConfiguration,
    SegmentationMethodId,
    SegmentationReviewStatus,
    SegmentationSelection,
)
from funes.tiff_reader import TiffFrameSequence, TiffMetadata, TiffPair


class InteractiveRoiReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.labels = np.zeros((6, 7), dtype=np.int32)
        self.labels[2:4, 2:4] = 1
        self.labels[4, 4] = 2
        self.labels[0, 5:7] = 4
        self.filtering = filter_labeled_rois(
            self.labels,
            RoiGeometryFilterConfig(
                min_area_pixels=2,
                border_policy=BorderTouchPolicy.FLAG,
            ),
        )
        self.c0 = np.stack(
            (
                np.arange(42, dtype=np.uint16).reshape(6, 7),
                np.arange(42, 84, dtype=np.uint16).reshape(6, 7),
                np.arange(84, 126, dtype=np.uint16).reshape(6, 7),
            )
        )
        self.c1 = self.c0 + 50
        self.pair = _pair(self.c0, self.c1)
        self.review_state = SegmentationReviewState()

    def test_export_creates_self_contained_temporal_two_channel_viewer(self) -> None:
        source_before = self.filtering.source_label_image.copy()
        filtered_before = self.filtering.filtered_label_image.copy()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "review.html"
            result = export_interactive_roi_review_html(
                self.pair,
                self.filtering,
                self.review_state,
                output,
                title="Synthetic ROI review",
            )
            html = output.read_text(encoding="utf-8")

        data = _viewer_data(html)
        self.assertEqual(result.frame_count, 3)
        self.assertEqual(result.roi_labels, (1, 2, 4))
        self.assertEqual(
            result.roi_filtering_sha256, data["roi_filtering_sha256"]
        )
        self.assertEqual(set(data["channels"]), {"C0", "C1"})
        self.assertEqual(len(data["channels"]["C0"]), 3)
        self.assertTrue(all(item.startswith("data:image/png;base64,") for item in data["channels"]["C1"]))
        self.assertEqual(set(data["rois"]), {"1", "2", "4"})
        self.assertEqual(data["rois"]["1"]["status"], "accepted")
        self.assertEqual(data["rois"]["2"]["status"], "rejected")
        self.assertEqual(data["rois"]["4"]["status"], "flagged")
        self.assertIn('id="channel"', html)
        self.assertIn('id="frame"', html)
        self.assertIn('class="roi accepted" data-label="1"', html)
        self.assertIn('class="roi rejected" data-label="2"', html)
        self.assertIn('class="roi flagged" data-label="4"', html)
        self.assertEqual(html.count('data-static-channel="C0"'), 3)
        self.assertEqual(html.count('data-static-channel="C1"'), 3)
        self.assertIn('data-static-frame="1"', html)
        self.assertIn("All embedded frames — static fallback", html)
        self.assertIn("function loadState()", html)
        self.assertIn("localStorage.setItem", html)
        self.assertIn("viewer controls still work", html)
        self.assertIn("Export review JSON", html)
        self.assertNotIn("__FUNES_", html)
        self.assertTrue(np.array_equal(self.filtering.source_label_image, source_before))
        self.assertTrue(np.array_equal(self.filtering.filtered_label_image, filtered_before))

    def test_exported_decision_loads_and_records_exact_d046_inspection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            viewer = root / "review.html"
            export_interactive_roi_review_html(
                self.pair, self.filtering, self.review_state, viewer
            )
            raw = _viewer_data(viewer.read_text(encoding="utf-8"))["review_record"]
            raw["inspection"] = {
                "inspector": "reviewer-a",
                "inspected_at": "2026-07-20T15:30:00-04:00",
                "note": "Contours inspected without editing masks.",
            }
            decision_path = root / "decision.json"
            decision_path.write_text(json.dumps(raw), encoding="utf-8")

            decision = load_interactive_roi_review_decision(decision_path)
            reviewed = apply_interactive_roi_review_decision(
                self.review_state, self.pair, self.filtering, decision
            )

        field = reviewed.query(self.pair.position_key)
        self.assertEqual(field.status, SegmentationReviewStatus.MANUALLY_REVIEWED)
        self.assertEqual(field.inspection.inspector, "reviewer-a")
        self.assertEqual(
            field.inspection.note, "Contours inspected without editing masks."
        )
        self.assertEqual(self.review_state.query(self.pair.position_key).status, SegmentationReviewStatus.UNREVIEWED)

    def test_apply_rejects_changed_labels_and_stale_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            viewer = Path(tmp) / "review.html"
            export_interactive_roi_review_html(
                self.pair, self.filtering, self.review_state, viewer
            )
            raw = _viewer_data(viewer.read_text(encoding="utf-8"))["review_record"]
            raw["inspection"] = {"inspector": None, "inspected_at": None, "note": None}
            decision_path = Path(tmp) / "decision.json"
            decision_path.write_text(json.dumps(raw), encoding="utf-8")
            decision = load_interactive_roi_review_decision(decision_path)

            changed_labels = self.labels.copy()
            changed_labels[5, 6] = 5
            changed = filter_labeled_rois(changed_labels)
            with self.assertRaisesRegex(ValueError, "source-label hash"):
                apply_interactive_roi_review_decision(
                    self.review_state, self.pair, changed, decision
                )

            changed_statuses = filter_labeled_rois(
                self.labels,
                RoiGeometryFilterConfig(
                    min_area_pixels=1,
                    border_policy=BorderTouchPolicy.FLAG,
                ),
            )
            with self.assertRaisesRegex(ValueError, "filtering hash"):
                apply_interactive_roi_review_decision(
                    self.review_state, self.pair, changed_statuses, decision
                )

            other_state = SegmentationReviewState(
                SegmentationConfiguration(
                    global_selection=SegmentationSelection(
                        SegmentationMethodId.OTSU_GLOBAL
                    )
                )
            )
            with self.assertRaisesRegex(ValueError, "selection is stale"):
                apply_interactive_roi_review_decision(
                    other_state, self.pair, self.filtering, decision
                )

    def test_decision_loader_rejects_noninspection_and_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decision.json"
            path.write_text(json.dumps({"decision": "inspected"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid schema"):
                load_interactive_roi_review_decision(path)

    def test_export_rejects_frame_label_shape_mismatch_and_wrong_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "frame and ROI label shapes"):
                export_interactive_roi_review_html(
                    _pair(np.zeros((2, 5, 7)), np.zeros((2, 5, 7))),
                    self.filtering,
                    self.review_state,
                    Path(tmp) / "review.html",
                )
            with self.assertRaisesRegex(ValueError, r"\.html or \.htm"):
                export_interactive_roi_review_html(
                    self.pair,
                    self.filtering,
                    self.review_state,
                    Path(tmp) / "review.svg",
                )

    def test_display_config_validates_percentile_order(self) -> None:
        with self.assertRaisesRegex(ValueError, "lower_percentile"):
            InteractiveRoiReviewConfig(lower_percentile=99.5, upper_percentile=1)


def _pair(c0_frames: np.ndarray, c1_frames: np.ndarray) -> TiffPair:
    metadata = TiffMetadata(
        page_count=int(c0_frames.shape[0]),
        series_axes="TYX",
        series_shape=tuple(c0_frames.shape),
        imagej_metadata=None,
        ome_metadata=None,
        page_descriptions=(),
        first_page_tags={},
    )
    parsed_c0 = parse_tiff_filename(
        "Capture 1 - Position 2_XY1_Z0_T00_C0.tif"
    )
    parsed_c1 = parse_tiff_filename(
        "Capture 1 - Position 2_XY1_Z0_T00_C1.tif"
    )
    assert parsed_c0 is not None and parsed_c1 is not None
    return TiffPair(
        position_key=PositionKey("Capture 1", "Position 2"),
        c0=TiffFrameSequence(parsed_c0, c0_frames, metadata),
        c1=TiffFrameSequence(parsed_c1, c1_frames, metadata),
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
