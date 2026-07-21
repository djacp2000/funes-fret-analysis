import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import PositionKey
from funes.roi_geometry import (
    BorderTouchPolicy,
    RoiFilterStatus,
    RoiGeometryFilterConfig,
    filter_segmentation_rois,
)
from funes.roi_revision import (
    RoiMaskRevision,
    RoiPixel,
    RoiRevisionError,
    RoiRevisionFinalizationState,
    RoiRevisionOperation,
    RoiRevisionSourceIdentity,
    finalize_roi_revision,
)
from funes.roi_revision_replay import replay_roi_revision
from funes.segmentation_engine import SegmentationEngineRecord, SegmentationResult


class RoiRevisionTests(unittest.TestCase):
    def setUp(self) -> None:
        labels = np.zeros((8, 8), dtype=np.int32)
        labels[1:3, 1:3] = 1
        labels[4, 4] = 2
        labels[5:7, 5:7] = 3
        self.segmentation = SegmentationResult(
            label_image=labels,
            roi_count=3,
            engine=SegmentationEngineRecord(
                name="synthetic",
                version="test",
                model=None,
            ),
        )
        self.filtering = filter_segmentation_rois(
            self.segmentation,
            RoiGeometryFilterConfig(
                min_area_pixels=2,
                border_policy=BorderTouchPolicy.ACCEPT,
            ),
        )
        self.position_key = PositionKey(
            "Capture 1", "Position 1", "Experiment Synthetic"
        )
        self.source = RoiRevisionSourceIdentity.from_automatic_results(
            self.position_key,
            self.segmentation,
            self.filtering,
        )

    def _draft(
        self,
        operations: tuple[RoiRevisionOperation, ...],
        *,
        parent_revision_sha256: str | None = None,
    ) -> RoiMaskRevision:
        return RoiMaskRevision(
            source=self.source,
            operations=operations,
            editor="synthetic-reviewer",
            parent_revision_sha256=parent_revision_sha256,
        )

    def _finalize(self, draft: RoiMaskRevision) -> RoiMaskRevision:
        return finalize_roi_revision(
            draft,
            finalized_at="2026-07-21T15:00:00-04:00",
        )

    def _all_operations(self) -> tuple[RoiRevisionOperation, ...]:
        return (
            RoiRevisionOperation.replace(
                1,
                ((1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)),
                reason="Extend the retained cell support.",
            ),
            RoiRevisionOperation.delete(
                3,
                reason="Remove an aberrant retained support.",
            ),
            RoiRevisionOperation.restore(
                2,
                reason="Restore the explicitly rejected original label.",
            ),
            RoiRevisionOperation.add(
                4,
                ((3, 6), (4, 6)),
                reason="Add one omitted synthetic ROI.",
            ),
        )

    def test_finalized_add_delete_replace_restore_replay_and_geometry(self) -> None:
        original_module7 = self.segmentation.label_image.copy()
        original_module8 = self.filtering.filtered_label_image.copy()
        draft = self._draft(self._all_operations())
        revision = self._finalize(draft)

        result = replay_roi_revision(
            revision,
            self.segmentation,
            self.filtering,
            self.position_key,
        )

        self.assertEqual(draft.finalization_state, RoiRevisionFinalizationState.DRAFT)
        self.assertEqual(
            revision.finalization_state, RoiRevisionFinalizationState.FINALIZED
        )
        self.assertNotEqual(draft.sha256, revision.sha256)
        self.assertIs(result.original_segmentation, self.segmentation)
        self.assertIs(result.original_filtering, self.filtering)
        self.assertEqual(result.revision_sha256, revision.sha256)
        self.assertEqual(len(result.operation_trace), 4)
        self.assertEqual(
            [entry.operation_index for entry in result.operation_trace],
            [0, 1, 2, 3],
        )
        self.assertTrue(np.any(result.edited_label_image == 1))
        self.assertTrue(np.any(result.edited_label_image == 2))
        self.assertFalse(np.any(result.edited_label_image == 3))
        self.assertTrue(np.any(result.edited_label_image == 4))
        self.assertEqual(
            [record.geometry.label for record in result.geometry_audit.records],
            [1, 2, 4],
        )
        self.assertEqual(
            result.geometry_audit.records[1].status,
            RoiFilterStatus.REJECTED,
        )
        self.assertFalse(np.any(result.measurement_label_image == 2))
        self.assertEqual(tuple(np.unique(result.measurement_label_image)), (0, 1, 4))
        self.assertFalse(result.edited_label_image.flags.writeable)
        self.assertFalse(result.measurement_label_image.flags.writeable)
        np.testing.assert_array_equal(self.segmentation.label_image, original_module7)
        np.testing.assert_array_equal(self.filtering.filtered_label_image, original_module8)

    def test_replay_is_deterministic_and_does_not_call_module9_review_apis(self) -> None:
        revision = self._finalize(self._draft(self._all_operations()))
        forbidden = (
            "funes.segmentation_review.SegmentationReviewState.record_inspection",
            "funes.segmentation_review.SegmentationReviewState.approve_global",
            "funes.experiment_roi_review.ExperimentPositionReview.approve_remaining",
            "funes.roi_review.apply_interactive_roi_review_decision",
        )
        patchers = [patch(target) for target in forbidden]
        spies = [patcher.start() for patcher in patchers]
        self.addCleanup(lambda: [patcher.stop() for patcher in patchers])

        first = replay_roi_revision(
            revision, self.segmentation, self.filtering, self.position_key
        )
        second = replay_roi_revision(
            revision, self.segmentation, self.filtering, self.position_key
        )

        np.testing.assert_array_equal(first.edited_label_image, second.edited_label_image)
        np.testing.assert_array_equal(
            first.measurement_label_image, second.measurement_label_image
        )
        self.assertEqual(first.operation_trace, second.operation_trace)
        self.assertEqual(first.edited_label_sha256, second.edited_label_sha256)
        self.assertEqual(
            first.measurement_label_sha256, second.measurement_label_sha256
        )
        for spy in spies:
            spy.assert_not_called()

    def test_unfinalized_revision_cannot_replay_or_be_finalized_twice(self) -> None:
        draft = self._draft(
            (RoiRevisionOperation.delete(3, reason="Synthetic deletion."),)
        )
        with self.assertRaisesRegex(RoiRevisionError, "only a finalized"):
            replay_roi_revision(
                draft, self.segmentation, self.filtering, self.position_key
            )

        finalized = self._finalize(draft)
        with self.assertRaisesRegex(RoiRevisionError, "already finalized"):
            finalize_roi_revision(
                finalized,
                finalized_at="2026-07-21T16:00:00-04:00",
            )
        with self.assertRaisesRegex(RoiRevisionError, "timezone"):
            finalize_roi_revision(draft, finalized_at="2026-07-21T16:00:00")

    def test_stale_hash_wrong_position_and_wrong_shape_fail_closed(self) -> None:
        operation = RoiRevisionOperation.delete(3, reason="Synthetic deletion.")
        stale_source = replace(
            self.source,
            module8_filtering_sha256="0" * 64,
        )
        stale = self._finalize(
            RoiMaskRevision(stale_source, (operation,), "synthetic-reviewer")
        )
        with self.assertRaisesRegex(RoiRevisionError, "stale or does not match"):
            replay_roi_revision(
                stale, self.segmentation, self.filtering, self.position_key
            )

        revision = self._finalize(self._draft((operation,)))
        with self.assertRaisesRegex(RoiRevisionError, "stale or does not match"):
            replay_roi_revision(
                revision,
                self.segmentation,
                self.filtering,
                PositionKey("Capture 1", "Position 2", "Experiment Synthetic"),
            )

        wrong_shape = replace(self.source, image_shape=(7, 8))
        wrong = self._finalize(
            RoiMaskRevision(wrong_shape, (operation,), "synthetic-reviewer")
        )
        with self.assertRaisesRegex(RoiRevisionError, "stale or does not match"):
            replay_roi_revision(
                wrong, self.segmentation, self.filtering, self.position_key
            )

    def test_overlap_empty_out_of_bounds_and_duplicate_pixels_are_rejected(self) -> None:
        with self.assertRaisesRegex(RoiRevisionError, "non-empty pixel support"):
            RoiRevisionOperation.add(4, (), reason="Invalid empty add.")
        with self.assertRaisesRegex(RoiRevisionError, "duplicates"):
            RoiRevisionOperation.add(
                4,
                ((3, 6), (3, 6)),
                reason="Invalid duplicate support.",
            )

        overlap = self._finalize(
            self._draft(
                (
                    RoiRevisionOperation.replace(
                        1,
                        ((1, 1), (5, 5)),
                        reason="Invalid overlap with label 3.",
                    ),
                )
            )
        )
        with self.assertRaisesRegex(RoiRevisionError, "overlaps existing labels"):
            replay_roi_revision(
                overlap, self.segmentation, self.filtering, self.position_key
            )

        outside = self._finalize(
            self._draft(
                (
                    RoiRevisionOperation.add(
                        4,
                        ((8, 0),),
                        reason="Invalid out-of-bounds support.",
                    ),
                )
            )
        )
        with self.assertRaisesRegex(RoiRevisionError, "outside image shape"):
            replay_roi_revision(
                outside, self.segmentation, self.filtering, self.position_key
            )

    def test_invalid_reused_unknown_and_noop_labels_are_rejected(self) -> None:
        invalid_new_label = self._finalize(
            self._draft(
                (
                    RoiRevisionOperation.add(
                        3,
                        ((3, 6),),
                        reason="Invalid reused original label.",
                    ),
                )
            )
        )
        with self.assertRaisesRegex(RoiRevisionError, "greater than every"):
            replay_roi_revision(
                invalid_new_label,
                self.segmentation,
                self.filtering,
                self.position_key,
            )

        unknown_delete = self._finalize(
            self._draft(
                (RoiRevisionOperation.delete(9, reason="Unknown label."),)
            )
        )
        with self.assertRaisesRegex(RoiRevisionError, "unknown or already deleted"):
            replay_roi_revision(
                unknown_delete, self.segmentation, self.filtering, self.position_key
            )

        unchanged = self._finalize(
            self._draft(
                (
                    RoiRevisionOperation.replace(
                        1,
                        ((1, 1), (1, 2), (2, 1), (2, 2)),
                        reason="Invalid unchanged replacement.",
                    ),
                )
            )
        )
        with self.assertRaisesRegex(RoiRevisionError, "unchanged"):
            replay_roi_revision(
                unchanged, self.segmentation, self.filtering, self.position_key
            )

        net_noop = self._finalize(
            self._draft(
                (
                    RoiRevisionOperation.add(
                        4,
                        ((3, 6),),
                        reason="Temporary addition.",
                    ),
                    RoiRevisionOperation.delete(4, reason="Undo temporary addition."),
                )
            )
        )
        with self.assertRaisesRegex(RoiRevisionError, "no-op after all operations"):
            replay_roi_revision(
                net_noop, self.segmentation, self.filtering, self.position_key
            )

    def test_restore_is_limited_to_module8_rejected_original_labels(self) -> None:
        retained = self._finalize(
            self._draft((RoiRevisionOperation.restore(1, reason="Invalid restore."),))
        )
        with self.assertRaisesRegex(RoiRevisionError, "retained by Module 8"):
            replay_roi_revision(
                retained, self.segmentation, self.filtering, self.position_key
            )

        unknown = self._finalize(
            self._draft((RoiRevisionOperation.restore(9, reason="Unknown restore."),))
        )
        with self.assertRaisesRegex(RoiRevisionError, "unknown original"):
            replay_roi_revision(
                unknown, self.segmentation, self.filtering, self.position_key
            )

    def test_parent_hash_and_monotonic_labels_are_enforced_across_revisions(self) -> None:
        parent_revision = self._finalize(
            self._draft(
                (
                    RoiRevisionOperation.add(
                        4,
                        ((3, 6),),
                        reason="Parent addition.",
                    ),
                )
            )
        )
        parent = replay_roi_revision(
            parent_revision, self.segmentation, self.filtering, self.position_key
        )
        child_revision = self._finalize(
            self._draft(
                (
                    RoiRevisionOperation.delete(4, reason="Delete parent addition."),
                    RoiRevisionOperation.add(
                        5,
                        ((4, 6),),
                        reason="Allocate next monotonic label.",
                    ),
                ),
                parent_revision_sha256=parent.revision_sha256,
            )
        )
        with self.assertRaisesRegex(RoiRevisionError, "no parent_result"):
            replay_roi_revision(
                child_revision, self.segmentation, self.filtering, self.position_key
            )
        child = replay_roi_revision(
            child_revision,
            self.segmentation,
            self.filtering,
            self.position_key,
            parent_result=parent,
        )
        self.assertFalse(np.any(child.edited_label_image == 4))
        self.assertTrue(np.any(child.edited_label_image == 5))
        self.assertEqual(len(child.operation_trace), 3)

        reused = self._finalize(
            self._draft(
                (
                    RoiRevisionOperation.delete(4, reason="Delete parent addition."),
                    RoiRevisionOperation.add(
                        4,
                        ((4, 6),),
                        reason="Invalid reuse.",
                    ),
                ),
                parent_revision_sha256=parent.revision_sha256,
            )
        )
        with self.assertRaisesRegex(RoiRevisionError, "greater than every"):
            replay_roi_revision(
                reused,
                self.segmentation,
                self.filtering,
                self.position_key,
                parent_result=parent,
            )

    def test_contracts_reject_invalid_metadata(self) -> None:
        with self.assertRaisesRegex(RoiRevisionError, "at least one operation"):
            RoiMaskRevision(self.source, (), "synthetic-reviewer")
        with self.assertRaisesRegex(RoiRevisionError, "operation reason"):
            RoiRevisionOperation.delete(3, reason=" ")
        with self.assertRaisesRegex(RoiRevisionError, "operation label"):
            RoiRevisionOperation.delete(-1, reason="Invalid negative label.")
        with self.assertRaisesRegex(RoiRevisionError, "operation label"):
            RoiRevisionOperation.delete(
                int(np.iinfo(np.int32).max) + 1,
                reason="Invalid label outside int32.",
            )
        with self.assertRaisesRegex(RoiRevisionError, "pixel row"):
            RoiPixel(-1, 0)
        with self.assertRaisesRegex(RoiRevisionError, "explicit experiment"):
            RoiRevisionSourceIdentity.from_automatic_results(
                PositionKey("Capture 1", "Position 1"),
                self.segmentation,
                self.filtering,
            )


if __name__ == "__main__":
    unittest.main()
