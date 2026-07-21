import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import PositionKey
from funes.experiment_roi_review import (
    ExperimentPositionReview,
    ExperimentPositionReviewMode,
    ExperimentRoiReviewOrchestrator,
)
from funes.experiment_roi_review_persistence import (
    EXPERIMENT_ROI_REVIEW_SNAPSHOT_SCHEMA,
    ExperimentRoiReviewSnapshotError,
    export_experiment_roi_review_snapshot,
    load_experiment_roi_review_snapshot,
)
from funes.segmentation_review import SegmentationReviewState
from funes.segmentation_selection import (
    CapturePositionKey,
    SegmentationConfiguration,
    SegmentationMethodId,
    SegmentationSelection,
    SegmentationSelectionSource,
)


class ExperimentRoiReviewPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.a1 = PositionKey("Capture 1", "Position 1", "Experiment A")
        self.a2 = PositionKey("Capture 1", "Position 2", "Experiment A")
        self.a3 = PositionKey("Capture 2", "Position 1", "Experiment A")
        self.b1 = PositionKey("Capture 1", "Position 1", "Experiment B")
        self.b2 = PositionKey("Capture 1", "Position 2", "Experiment B")

    def test_round_trip_preserves_isolated_d044_and_d046_provenance(self) -> None:
        configuration = SegmentationConfiguration(
            field_overrides={
                CapturePositionKey.from_position_key(self.a2): SegmentationSelection(
                    SegmentationMethodId.OTSU_GLOBAL, "benchmark_baseline"
                )
            }
        )
        state_a = SegmentationReviewState(configuration).record_inspection(
            self.a1,
            inspector="reviewer-a",
            inspected_at="2026-07-20T12:00:00Z",
            note="Reviewed every displayed timepoint.",
        )
        review_a = ExperimentPositionReview(
            "Experiment A",
            (self.a1, self.a2, self.a3),
            ExperimentPositionReviewMode.REVIEW_SELECTED,
            (self.a1,),
            state_a,
        ).approve_remaining(
            "approval-a",
            approved_by="scientific-user",
            approved_at="2026-07-20T12:30:00Z",
            note="Applies only to the uninspected remainder of Experiment A.",
        )
        state_b = SegmentationReviewState().record_inspection(
            self.b1, inspector="reviewer-b"
        )
        review_b = ExperimentPositionReview(
            "Experiment B",
            (self.b1, self.b2),
            ExperimentPositionReviewMode.REVIEW_ALL,
            review_state=state_b,
        )
        original = ExperimentRoiReviewOrchestrator((review_a, review_b))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review_state.json"
            result = export_experiment_roi_review_snapshot(original, path)
            restored = load_experiment_roi_review_snapshot(path)
            file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

        self.assertEqual(restored, original)
        self.assertEqual(result.sha256, file_sha256)
        self.assertEqual(result.experiment_count, 2)
        self.assertEqual(
            restored.query(self.a2).field_review.selection.source,
            SegmentationSelectionSource.CAPTURE_POSITION_OVERRIDE,
        )
        self.assertEqual(
            restored.for_experiment("Experiment A")
            .review_state.global_approval.inspections_before_approval,
            state_a.inspections,
        )
        self.assertIsNone(
            restored.for_experiment("Experiment B").review_state.global_approval
        )

    def test_export_does_not_create_an_approval(self) -> None:
        review = ExperimentPositionReview(
            "Experiment A",
            (self.a1, self.a2),
            ExperimentPositionReviewMode.REVIEW_SELECTED,
            (self.a1,),
        )
        original = ExperimentRoiReviewOrchestrator((review,))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unreviewed.json"
            export_experiment_roi_review_snapshot(original, path)
            restored = load_experiment_roi_review_snapshot(path)

        self.assertIsNone(restored.experiments[0].review_state.global_approval)
        self.assertEqual(restored.experiments[0].review_state.inspections, ())
        self.assertEqual(restored, original)

    def test_changed_payload_and_unknown_fields_fail_closed(self) -> None:
        original = ExperimentRoiReviewOrchestrator(
            (
                ExperimentPositionReview(
                    "Experiment A",
                    (self.a1, self.a2),
                    ExperimentPositionReviewMode.REVIEW_ALL,
                ),
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            export_experiment_roi_review_snapshot(original, path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["experiments"][0]["mode"] = "review_selected"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(
                ExperimentRoiReviewSnapshotError, "SHA-256 does not match"
            ):
                load_experiment_roi_review_snapshot(path)

            raw["payload_sha256"] = _payload_sha256(raw["experiments"])
            raw["unexpected"] = True
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(
                ExperimentRoiReviewSnapshotError, "unknown.*unexpected"
            ):
                load_experiment_roi_review_snapshot(path)

    def test_rehashed_incoherent_scope_and_approval_snapshot_are_rejected(self) -> None:
        state = SegmentationReviewState().record_inspection(self.a1)
        approved = ExperimentPositionReview(
            "Experiment A",
            (self.a1, self.a2),
            ExperimentPositionReviewMode.REVIEW_SELECTED,
            (self.a1,),
            state,
        ).approve_remaining("approval-a")
        original = ExperimentRoiReviewOrchestrator((approved,))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            export_experiment_roi_review_snapshot(original, path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            approval = raw["experiments"][0]["review_state"]["global_approval"]
            approval["inspections_before_approval"] = []
            raw["payload_sha256"] = _payload_sha256(raw["experiments"])
            path.write_text(json.dumps(raw), encoding="utf-8")

            with self.assertRaisesRegex(
                ExperimentRoiReviewSnapshotError, "every selected position"
            ):
                load_experiment_roi_review_snapshot(path)

    def test_invalid_json_schema_and_output_extension_are_actionable(self) -> None:
        review = ExperimentRoiReviewOrchestrator(
            (
                ExperimentPositionReview(
                    "Experiment A",
                    (self.a1,),
                    ExperimentPositionReviewMode.REVIEW_ALL,
                ),
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "require.*json"):
                export_experiment_roi_review_snapshot(review, root / "review.txt")

            invalid = root / "invalid.json"
            invalid.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(
                ExperimentRoiReviewSnapshotError, "invalid.*JSON"
            ):
                load_experiment_roi_review_snapshot(invalid)

            wrong_schema = root / "wrong_schema.json"
            wrong_schema.write_text(
                json.dumps(
                    {
                        "schema": "funes.module9.experiment_roi_review.v999",
                        "payload_sha256": "unused",
                        "experiments": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ExperimentRoiReviewSnapshotError, "unsupported.*schema"
            ):
                load_experiment_roi_review_snapshot(wrong_schema)


def _payload_sha256(experiments: object) -> str:
    canonical = json.dumps(
        {
            "schema": EXPERIMENT_ROI_REVIEW_SNAPSHOT_SCHEMA,
            "experiments": experiments,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(b"funes-module9-experiment-review-v1\0" + canonical).hexdigest()


if __name__ == "__main__":
    unittest.main()
