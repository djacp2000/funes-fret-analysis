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
from funes.experiment_roi_review import (
    ExperimentPositionReview,
    ExperimentPositionReviewMode,
    ExperimentRoiReviewOrchestrator,
)
from funes.file_discovery import parse_tiff_filename
from funes.roi_geometry import RoiGeometryFilterConfig, filter_labeled_rois
from funes.roi_review import (
    InteractiveRoiReviewDecision,
    load_interactive_roi_review_decision,
    roi_filtering_sha256,
    roi_label_sha256,
)
from funes.segmentation_review import SegmentationReviewState
from funes.segmentation_selection import (
    CapturePositionKey,
    SegmentationConfiguration,
    SegmentationMethodId,
    SegmentationReviewStatus,
    SegmentationSelection,
)
from funes.tiff_reader import TiffFrameSequence, TiffMetadata, TiffPair


class ExperimentRoiReviewOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.a1 = PositionKey("Capture 1", "Position 1", "Experiment A")
        self.a2 = PositionKey("Capture 1", "Position 2", "Experiment A")
        self.b1 = PositionKey("Capture 1", "Position 1", "Experiment B")
        self.b2 = PositionKey("Capture 1", "Position 2", "Experiment B")
        labels = np.zeros((6, 7), dtype=np.int32)
        labels[1:4, 1:4] = 1
        labels[4:6, 4:6] = 2
        self.filtering = filter_labeled_rois(
            labels, RoiGeometryFilterConfig(min_area_pixels=2)
        )

    def test_sample_completion_never_approves_and_explicit_approval_is_isolated(self) -> None:
        orchestrator = ExperimentRoiReviewOrchestrator(
            (
                _selected_review("Experiment A", (self.a1, self.a2), self.a1),
                _selected_review("Experiment B", (self.b1, self.b2), self.b1),
            )
        )
        pair = _pair(self.a1, frame_count=3)
        scoped = orchestrator.for_experiment("Experiment A")
        reviewed = orchestrator.record_inspection(
            pair, self.filtering, _decision(scoped, pair, self.filtering)
        )

        self.assertEqual(
            reviewed.query(self.a1).status,
            SegmentationReviewStatus.MANUALLY_REVIEWED,
        )
        self.assertEqual(
            reviewed.query(self.a2).status, SegmentationReviewStatus.UNREVIEWED
        )
        self.assertEqual(
            reviewed.query(self.b1).status, SegmentationReviewStatus.UNREVIEWED
        )
        self.assertIsNone(
            reviewed.for_experiment("Experiment A").review_state.global_approval
        )

        approved = reviewed.approve_remaining(
            "Experiment A", "exp-a-approval", approved_by="reviewer-a"
        )
        self.assertEqual(
            approved.query(self.a2).status,
            SegmentationReviewStatus.GLOBAL_POLICY_ACCEPTED,
        )
        self.assertEqual(
            approved.query(self.b1).status, SegmentationReviewStatus.UNREVIEWED
        )
        self.assertIsNone(
            approved.for_experiment("Experiment B").review_state.global_approval
        )

    def test_review_all_keeps_uninspected_positions_unreviewed_and_forbids_approval(self) -> None:
        scoped = ExperimentPositionReview(
            experiment="Experiment A",
            positions=(self.a1, self.a2),
            mode=ExperimentPositionReviewMode.REVIEW_ALL,
        )
        pair1 = _pair(self.a1)
        reviewed = scoped.record_inspection(
            pair1, self.filtering, _decision(scoped, pair1, self.filtering)
        )

        self.assertEqual(reviewed.pending_manual_positions, (self.a2,))
        self.assertEqual(reviewed.unreviewed_positions, (self.a2,))
        with self.assertRaisesRegex(ValueError, "only in review_selected"):
            reviewed.approve_remaining("not-allowed")

        pair2 = _pair(self.a2)
        complete = reviewed.record_inspection(
            pair2, self.filtering, _decision(reviewed, pair2, self.filtering)
        )
        self.assertEqual(complete.pending_manual_positions, ())
        self.assertEqual(complete.unreviewed_positions, ())
        self.assertIsNone(complete.review_state.global_approval)

    def test_sample_approval_requires_a_completed_selected_subset(self) -> None:
        scoped = ExperimentPositionReview(
            experiment="Experiment A",
            positions=(self.a1, self.a2, PositionKey("Capture 2", "Position 1", "Experiment A")),
            mode=ExperimentPositionReviewMode.REVIEW_SELECTED,
            selected_positions=(self.a1, self.a2),
        )

        with self.assertRaisesRegex(ValueError, "every selected position"):
            scoped.approve_remaining("too-early")
        pair1 = _pair(self.a1)
        one = scoped.record_inspection(
            pair1, self.filtering, _decision(scoped, pair1, self.filtering)
        )
        with self.assertRaisesRegex(ValueError, "every selected position"):
            one.approve_remaining("still-too-early")

    def test_d044_override_and_d046_inspection_provenance_are_preserved(self) -> None:
        a3 = PositionKey("Capture 2", "Position 1", "Experiment A")
        configuration = SegmentationConfiguration(
            field_overrides={
                CapturePositionKey.from_position_key(self.a2): SegmentationSelection(
                    SegmentationMethodId.OTSU_GLOBAL
                )
            }
        )
        scoped = ExperimentPositionReview(
            experiment="Experiment A",
            positions=(self.a1, self.a2, a3),
            mode=ExperimentPositionReviewMode.REVIEW_SELECTED,
            selected_positions=(self.a1,),
            review_state=SegmentationReviewState(configuration),
        )
        pair = _pair(self.a1)
        inspected = scoped.record_inspection(
            pair,
            self.filtering,
            _decision(
                scoped,
                pair,
                self.filtering,
                inspector="reviewer-a",
                note="Synthetic fixed-ROI inspection.",
            ),
        )
        approved = inspected.approve_remaining("approval-with-d044-exception")

        first = approved.query(self.a1).field_review
        second = approved.query(self.a2).field_review
        self.assertEqual(first.inspection.inspector, "reviewer-a")
        self.assertEqual(first.inspection.note, "Synthetic fixed-ROI inspection.")
        self.assertEqual(
            approved.review_state.global_approval.inspected_fields,
            (CapturePositionKey.from_position_key(self.a1),),
        )
        self.assertEqual(second.status, SegmentationReviewStatus.EXPLICIT_OVERRIDE)
        self.assertEqual(second.selection.method, SegmentationMethodId.OTSU_GLOBAL)
        self.assertTrue(second.selection.override_applied)
        self.assertEqual(
            approved.query(a3).status,
            SegmentationReviewStatus.GLOBAL_POLICY_ACCEPTED,
        )

    def test_cross_experiment_position_and_decision_are_rejected(self) -> None:
        scoped_a = _selected_review("Experiment A", (self.a1, self.a2), self.a1)
        pair_a = _pair(self.a1)
        pair_b = _pair(self.b1)

        with self.assertRaisesRegex(ValueError, "not the isolated"):
            scoped_a.export_position_viewer(
                pair_b, self.filtering, Path("unused.html")
            )
        wrong_decision = _decision(scoped_a, pair_a, self.filtering)
        wrong_decision = InteractiveRoiReviewDecision(
            field_key=wrong_decision.field_key,
            source_label_sha256=wrong_decision.source_label_sha256,
            roi_filtering_sha256=wrong_decision.roi_filtering_sha256,
            selection=wrong_decision.selection,
            selection_source=wrong_decision.selection_source,
            experiment="Experiment B",
        )
        with self.assertRaisesRegex(ValueError, "exact experiment identity"):
            scoped_a.record_inspection(pair_a, self.filtering, wrong_decision)

    def test_on_demand_viewer_has_every_c0_c1_timepoint_without_roi_editing(self) -> None:
        scoped = _selected_review("Experiment A", (self.a1, self.a2), self.a1)
        pair = _pair(self.a1, frame_count=5)
        source_before = self.filtering.source_label_image.copy()
        filtered_before = self.filtering.filtered_label_image.copy()

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "experiment_a_position_1.html"
            result = scoped.export_position_viewer(pair, self.filtering, output)
            html = output.read_text(encoding="utf-8")
            data = _viewer_data(html)
            review_record = data["review_record"]
            review_record["inspection"] = {
                "inspector": "synthetic-reviewer",
                "inspected_at": None,
                "note": None,
            }
            decision_path = Path(tmp) / result.review_filename
            decision_path.write_text(json.dumps(review_record), encoding="utf-8")
            loaded = load_interactive_roi_review_decision(decision_path)

        self.assertEqual(result.frame_count, 5)
        self.assertEqual(len(data["channels"]["C0"]), 5)
        self.assertEqual(len(data["channels"]["C1"]), 5)
        self.assertEqual(data["field"]["experiment"], "Experiment A")
        self.assertEqual(loaded.experiment, "Experiment A")
        self.assertEqual(
            scoped.record_inspection(pair, self.filtering, loaded).query(self.a1).status,
            SegmentationReviewStatus.MANUALLY_REVIEWED,
        )
        self.assertIn("Experiment_A_Capture_1_Position_1", result.review_filename)
        self.assertEqual(html.count('data-static-channel="C0"'), 5)
        self.assertEqual(html.count('data-static-channel="C1"'), 5)
        self.assertNotIn("delete ROI", html.casefold())
        self.assertNotIn("draw ROI", html.casefold())
        self.assertTrue(
            np.array_equal(self.filtering.source_label_image, source_before)
        )
        self.assertTrue(
            np.array_equal(self.filtering.filtered_label_image, filtered_before)
        )

    def test_scope_contract_rejects_ambiguous_or_unsafe_construction(self) -> None:
        with self.assertRaisesRegex(ValueError, "proper subset"):
            ExperimentPositionReview(
                "Experiment A",
                (self.a1, self.a2),
                ExperimentPositionReviewMode.REVIEW_SELECTED,
                (self.a1, self.a2),
            )
        with self.assertRaisesRegex(ValueError, "only positions from experiment"):
            ExperimentPositionReview(
                "Experiment A",
                (self.a1, self.b1),
                ExperimentPositionReviewMode.REVIEW_ALL,
            )
        with self.assertRaisesRegex(ValueError, "one isolated ledger per experiment"):
            ExperimentRoiReviewOrchestrator(
                (
                    _selected_review("Experiment A", (self.a1, self.a2), self.a1),
                    _selected_review("Experiment A", (self.a1, self.a2), self.a1),
                )
            )


def _selected_review(
    experiment: str,
    positions: tuple[PositionKey, ...],
    selected: PositionKey,
) -> ExperimentPositionReview:
    return ExperimentPositionReview(
        experiment=experiment,
        positions=positions,
        mode=ExperimentPositionReviewMode.REVIEW_SELECTED,
        selected_positions=(selected,),
    )


def _decision(
    scoped: ExperimentPositionReview,
    pair: TiffPair,
    filtering,
    *,
    inspector: str | None = None,
    note: str | None = None,
) -> InteractiveRoiReviewDecision:
    resolved = scoped.review_state.configuration.resolve(pair.position_key)
    return InteractiveRoiReviewDecision(
        field_key=CapturePositionKey.from_position_key(pair.position_key),
        source_label_sha256=roi_label_sha256(filtering.source_label_image),
        roi_filtering_sha256=roi_filtering_sha256(filtering),
        selection=SegmentationSelection(resolved.method, resolved.profile),
        selection_source=resolved.source,
        experiment=pair.position_key.experiment,
        inspector=inspector,
        note=note,
    )


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
