import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import PositionKey
from funes.roi_geometry import (
    BorderTouchPolicy,
    RoiGeometryFilterConfig,
    filter_segmentation_rois,
)
from funes.roi_revision import (
    RoiMaskRevision,
    RoiRevisionOperation,
    RoiRevisionSourceIdentity,
    RoiRevisionFinalizationState,
)
from funes.roi_revision_finalization import (
    RoiRevisionHumanFinalizationError,
    finalize_human_roi_revision_artifact,
)
from funes.roi_revision_persistence import RoiRevisionArtifactError
from funes.segmentation_engine import SegmentationEngineRecord, SegmentationResult


class RoiRevisionHumanFinalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        labels = np.zeros((5, 6), dtype=np.int32)
        labels[1:3, 1:3] = 1
        labels[4, 4] = 2
        self.segmentation = SegmentationResult(
            labels, 2, SegmentationEngineRecord("synthetic", "test", None)
        )
        self.filtering = filter_segmentation_rois(
            self.segmentation,
            RoiGeometryFilterConfig(
                min_area_pixels=2, border_policy=BorderTouchPolicy.ACCEPT
            ),
        )
        self.position_key = PositionKey("Capture 4", "Position 2", "Experiment F")
        source = RoiRevisionSourceIdentity.from_automatic_results(
            self.position_key, self.segmentation, self.filtering
        )
        self.draft = RoiMaskRevision(
            source=source,
            operations=(
                RoiRevisionOperation.restore(
                    2, reason="Restore the synthetic filtered label."
                ),
            ),
            editor="human-reviewer",
        )

    def test_finalizes_and_revalidates_a_new_artifact_without_scientific_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "human-finalized-revision.json"
            completed = finalize_human_roi_revision_artifact(
                self.draft,
                self.segmentation,
                self.filtering,
                self.position_key,
                finalized_at="2026-07-21T21:00:00-04:00",
                output_path=path,
            )

            self.assertTrue(path.is_file())
            self.assertEqual(
                completed.revision_result.finalization_state,
                RoiRevisionFinalizationState.FINALIZED,
            )
            self.assertEqual(completed.artifact.path, path)
            self.assertEqual(
                completed.artifact.revision_sha256,
                completed.revision_result.revision_sha256,
            )
            self.assertEqual(
                self.draft.finalization_state, RoiRevisionFinalizationState.DRAFT
            )
            self.assertIs(completed.revision_result.original_segmentation, self.segmentation)
            self.assertIs(completed.revision_result.original_filtering, self.filtering)

    def test_refuses_to_replace_an_existing_artifact_before_finalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "existing.json"
            path.write_text("existing audit record", encoding="utf-8")
            with self.assertRaisesRegex(
                RoiRevisionHumanFinalizationError, "refusing to overwrite"
            ):
                finalize_human_roi_revision_artifact(
                    self.draft,
                    self.segmentation,
                    self.filtering,
                    self.position_key,
                    finalized_at="2026-07-21T21:00:00-04:00",
                    output_path=path,
                )
            self.assertEqual(path.read_text(encoding="utf-8"), "existing audit record")

    def test_replay_failure_creates_no_artifact(self) -> None:
        stale = RoiMaskRevision(
            source=RoiRevisionSourceIdentity(
                experiment=self.draft.source.experiment,
                capture=self.draft.source.capture,
                position=self.draft.source.position,
                image_shape=self.draft.source.image_shape,
                module7_source_label_sha256="0" * 64,
                module8_filtering_sha256=self.draft.source.module8_filtering_sha256,
            ),
            operations=self.draft.operations,
            editor=self.draft.editor,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stale.json"
            with self.assertRaisesRegex(Exception, "stale or does not match"):
                finalize_human_roi_revision_artifact(
                    stale,
                    self.segmentation,
                    self.filtering,
                    self.position_key,
                    finalized_at="2026-07-21T21:00:00-04:00",
                    output_path=path,
                )
            self.assertFalse(path.exists())

    def test_failed_postwrite_validation_removes_only_the_new_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unverified.json"
            with patch(
                "funes.roi_revision_finalization.load_roi_revision_artifact",
                side_effect=RoiRevisionArtifactError("synthetic verification failure"),
            ):
                with self.assertRaisesRegex(RoiRevisionArtifactError, "verification failure"):
                    finalize_human_roi_revision_artifact(
                        self.draft,
                        self.segmentation,
                        self.filtering,
                        self.position_key,
                        finalized_at="2026-07-21T21:00:00-04:00",
                        output_path=path,
                    )
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
