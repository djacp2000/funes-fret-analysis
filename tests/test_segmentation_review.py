import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.segmentation_registry import segment_configured_first_frame
from funes.segmentation_review import (
    GlobalSegmentationApproval,
    SegmentationFieldInspection,
    SegmentationReviewState,
)
from funes.segmentation_selection import (
    BENCHMARK_BASELINE_PROFILE,
    PROVISIONAL_WORKING_PROFILE,
    CapturePositionKey,
    SegmentationConfiguration,
    SegmentationMethodId,
    SegmentationReviewStatus,
    SegmentationSelection,
    SegmentationSelectionSource,
)


class SegmentationReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = CapturePositionKey("Capture 1", "Position 1")
        self.second = CapturePositionKey("Capture 1", "Position 2")
        self.third = CapturePositionKey("Capture 2", "Position 1")

    def test_fields_start_unreviewed_with_confirmed_global_default(self) -> None:
        state = SegmentationReviewState()

        decision = state.query(self.first)

        self.assertEqual(decision.status, SegmentationReviewStatus.UNREVIEWED)
        self.assertFalse(decision.manually_inspected)
        self.assertFalse(decision.covered)
        self.assertEqual(decision.selection.method, SegmentationMethodId.KMEANS)
        self.assertEqual(
            decision.selection.profile,
            PROVISIONAL_WORKING_PROFILE,
        )

    def test_record_inspection_returns_new_immutable_manual_decision(self) -> None:
        original = SegmentationReviewState()
        reviewed = original.record_inspection(
            self.first,
            inspector="reviewer-a",
            inspected_at="2026-07-14T10:30:00-04:00",
            note="Representative field.",
        )

        self.assertEqual(original.query(self.first).status, SegmentationReviewStatus.UNREVIEWED)
        decision = reviewed.query(self.first)
        self.assertEqual(decision.status, SegmentationReviewStatus.MANUALLY_REVIEWED)
        self.assertTrue(decision.manually_inspected)
        self.assertTrue(decision.covered)
        self.assertEqual(decision.inspection.inspector, "reviewer-a")
        self.assertEqual(
            decision.inspection.selection,
            SegmentationSelection(
                SegmentationMethodId.KMEANS,
                PROVISIONAL_WORKING_PROFILE,
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            reviewed.global_approval = None

    def test_explicit_approval_snapshots_inspections_and_covers_remaining_fields(self) -> None:
        inspected = (
            SegmentationReviewState()
            .record_inspection(self.first)
            .record_inspection(self.second)
        )
        approved = inspected.approve_global(
            "approval-20260714-001",
            approved_by="reviewer-a",
            approved_at="2026-07-14T11:00:00-04:00",
        )

        approval = approved.global_approval
        self.assertEqual(approval.inspected_fields, (self.first, self.second))
        self.assertEqual(
            approval.approved_selection,
            SegmentationSelection(
                SegmentationMethodId.KMEANS,
                PROVISIONAL_WORKING_PROFILE,
            ),
        )
        self.assertEqual(
            approved.query(self.first).status,
            SegmentationReviewStatus.MANUALLY_REVIEWED,
        )
        remaining = approved.query(self.third)
        self.assertEqual(
            remaining.status,
            SegmentationReviewStatus.GLOBAL_POLICY_ACCEPTED,
        )
        self.assertTrue(remaining.accepted_by_global_policy)
        self.assertTrue(remaining.covered)
        self.assertFalse(remaining.manually_inspected)
        self.assertIsNone(remaining.inspection)

    def test_inspection_after_approval_is_not_added_to_prior_snapshot(self) -> None:
        approved = (
            SegmentationReviewState()
            .record_inspection(self.first)
            .approve_global("approval-before-later-review")
        )
        later_reviewed = approved.record_inspection(self.second)

        self.assertEqual(
            later_reviewed.global_approval.inspected_fields,
            (self.first,),
        )
        self.assertEqual(
            later_reviewed.query(self.second).status,
            SegmentationReviewStatus.MANUALLY_REVIEWED,
        )
        self.assertEqual(
            later_reviewed.query(self.third).status,
            SegmentationReviewStatus.GLOBAL_POLICY_ACCEPTED,
        )

    def test_global_approval_has_no_automatic_sample_minimum(self) -> None:
        approved = SegmentationReviewState().approve_global("explicit-zero-sample")

        self.assertEqual(approved.global_approval.inspected_fields, ())
        self.assertEqual(
            approved.query(self.first).status,
            SegmentationReviewStatus.GLOBAL_POLICY_ACCEPTED,
        )

    def test_override_has_precedence_and_keeps_manual_inspection_separate(self) -> None:
        configuration = SegmentationConfiguration(
            field_overrides={
                self.first: SegmentationSelection(
                    SegmentationMethodId.CONTROL_P99,
                    BENCHMARK_BASELINE_PROFILE,
                ),
                self.second: SegmentationSelection(
                    SegmentationMethodId.OTSU_GLOBAL,
                    BENCHMARK_BASELINE_PROFILE,
                ),
            }
        )
        state = (
            SegmentationReviewState(configuration)
            .record_inspection(self.first)
            .approve_global("approval-with-exceptions")
        )

        reviewed_override = state.query(self.first)
        uninspected_override = state.query(self.second)
        global_field = state.query(self.third)

        self.assertEqual(
            reviewed_override.status,
            SegmentationReviewStatus.EXPLICIT_OVERRIDE,
        )
        self.assertEqual(
            reviewed_override.selection.source,
            SegmentationSelectionSource.CAPTURE_POSITION_OVERRIDE,
        )
        self.assertEqual(
            reviewed_override.selection.method,
            SegmentationMethodId.CONTROL_P99,
        )
        self.assertTrue(reviewed_override.manually_inspected)
        self.assertEqual(
            uninspected_override.status,
            SegmentationReviewStatus.EXPLICIT_OVERRIDE,
        )
        self.assertFalse(uninspected_override.manually_inspected)
        self.assertEqual(
            global_field.status,
            SegmentationReviewStatus.GLOBAL_POLICY_ACCEPTED,
        )

    def test_engine_result_preserves_global_approval_without_false_manual_review(self) -> None:
        state = (
            SegmentationReviewState()
            .record_inspection(self.first)
            .approve_global("approval-provenance")
        )
        rows, columns = np.indices((30, 30))
        frame = (rows + columns).astype(np.float64)
        frame[8:22, 8:22] += 100.0

        result = segment_configured_first_frame(
            frame,
            state.configuration,
            self.second,
            review_state=state,
        )

        provenance = result.engine.selection
        self.assertEqual(
            provenance.review_status,
            SegmentationReviewStatus.GLOBAL_POLICY_ACCEPTED,
        )
        self.assertFalse(provenance.manually_inspected)
        self.assertIsNone(provenance.inspected_method)
        self.assertEqual(provenance.global_approval_id, "approval-provenance")
        self.assertEqual(provenance.approved_global_method, SegmentationMethodId.KMEANS)
        self.assertEqual(
            provenance.approved_global_profile,
            PROVISIONAL_WORKING_PROFILE,
        )
        self.assertEqual(
            provenance.inspected_before_global_approval,
            (self.first,),
        )

    def test_engine_result_preserves_override_and_inspection_provenance(self) -> None:
        configuration = SegmentationConfiguration(
            field_overrides={
                self.first: SegmentationSelection(SegmentationMethodId.CONTROL_P99)
            }
        )
        state = SegmentationReviewState(configuration).record_inspection(self.first)
        frame = np.zeros((30, 30), dtype=np.float64)
        frame[8:22, 8:22] = 100.0

        result = segment_configured_first_frame(
            frame,
            configuration,
            self.first,
            review_state=state,
        )

        provenance = result.engine.selection
        self.assertEqual(
            provenance.review_status,
            SegmentationReviewStatus.EXPLICIT_OVERRIDE,
        )
        self.assertTrue(provenance.override_applied)
        self.assertTrue(provenance.manually_inspected)
        self.assertEqual(
            provenance.inspected_method,
            SegmentationMethodId.CONTROL_P99,
        )

    def test_stale_approval_and_stale_inspection_have_actionable_errors(self) -> None:
        stale_approval = GlobalSegmentationApproval(
            approval_id="stale",
            approved_selection=SegmentationSelection(
                SegmentationMethodId.OTSU_GLOBAL
            ),
        )
        with self.assertRaisesRegex(ValueError, "global approval is stale.*new explicit approval"):
            SegmentationReviewState(global_approval=stale_approval)

        stale_inspection = SegmentationFieldInspection(
            field_key=self.first,
            selection=SegmentationSelection(SegmentationMethodId.OTSU_GLOBAL),
            selection_source=SegmentationSelectionSource.GLOBAL,
        )
        with self.assertRaisesRegex(ValueError, "re-inspect.*current configuration"):
            SegmentationReviewState(inspections=(stale_inspection,))

    def test_duplicate_inspection_and_mismatched_execution_state_are_rejected(self) -> None:
        state = SegmentationReviewState().record_inspection(self.first)
        with self.assertRaisesRegex(ValueError, "inspection already recorded"):
            state.record_inspection(self.first)

        other_configuration = SegmentationConfiguration(
            global_selection=SegmentationSelection(SegmentationMethodId.OTSU_GLOBAL)
        )
        with self.assertRaisesRegex(ValueError, "same immutable configuration"):
            segment_configured_first_frame(
                np.zeros((10, 10), dtype=np.float64),
                other_configuration,
                self.first,
                review_state=state,
            )


if __name__ == "__main__":
    unittest.main()
