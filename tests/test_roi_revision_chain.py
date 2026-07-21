import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import PositionKey
from funes.roi_geometry import BorderTouchPolicy, RoiGeometryFilterConfig, filter_segmentation_rois
from funes.roi_revision import RoiMaskRevision, RoiRevisionOperation, RoiRevisionSourceIdentity, finalize_roi_revision
from funes.roi_revision_chain import RoiRevisionChainError, load_finalized_roi_revision_chain
from funes.roi_revision_persistence import export_roi_revision_artifact
from funes.roi_revision_replay import replay_roi_revision
from funes.segmentation_engine import SegmentationEngineRecord, SegmentationResult


class RoiRevisionChainTests(unittest.TestCase):
    def setUp(self) -> None:
        labels = np.zeros((6, 7), dtype=np.int32)
        labels[1:3, 1:3] = 1
        labels[4, 3] = 2
        self.segmentation = SegmentationResult(labels, 2, SegmentationEngineRecord("synthetic", "test", None))
        self.filtering = filter_segmentation_rois(self.segmentation, RoiGeometryFilterConfig(min_area_pixels=2, border_policy=BorderTouchPolicy.ACCEPT))
        self.position_key = PositionKey("Capture 2", "Position 3", "Experiment JSON")
        self.source = RoiRevisionSourceIdentity.from_automatic_results(self.position_key, self.segmentation, self.filtering)
        self.root = finalize_roi_revision(RoiMaskRevision(source=self.source, operations=(RoiRevisionOperation.replace(1, ((1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)), reason="Expand retained synthetic support."),), editor="chain-reviewer"), finalized_at="2026-07-21T23:00:00Z")
        self.root_result = replay_roi_revision(self.root, self.segmentation, self.filtering, self.position_key)
        self.child = finalize_roi_revision(RoiMaskRevision(source=self.source, operations=(RoiRevisionOperation.add(3, ((3, 5), (4, 5)), reason="Add omitted synthetic support."),), editor="chain-reviewer", parent_revision_sha256=self.root.sha256), finalized_at="2026-07-21T23:05:00Z")
        self.root_directory = Path(tempfile.mkdtemp(prefix="funes_module24_chain_"))
        self.addCleanup(shutil.rmtree, self.root_directory)
        self.root_path = self.root_directory / "root.json"
        self.child_path = self.root_directory / "child.json"
        export_roi_revision_artifact(self.root_result, self.root_path)
        export_roi_revision_artifact(replay_roi_revision(self.child, self.segmentation, self.filtering, self.position_key, parent_result=self.root_result), self.child_path)

    def test_loads_ordered_finalized_chain_and_returns_terminal_result(self) -> None:
        chain = load_finalized_roi_revision_chain((self.root_path, self.child_path), self.segmentation, self.filtering, self.position_key)
        self.assertEqual(tuple(entry.path for entry in chain.entries), (self.root_path.resolve(), self.child_path.resolve()))
        self.assertEqual(chain.terminal_result.revision, self.child)
        self.assertEqual(chain.terminal_result.revision_sha256, self.child.sha256)
        self.assertEqual(len(chain.terminal_result.operation_trace), 2)
        self.assertEqual(set(np.unique(chain.terminal_result.edited_label_image)), {0, 1, 3})
        self.assertIs(chain.terminal_result.original_segmentation, self.segmentation)
        self.assertIs(chain.terminal_result.original_filtering, self.filtering)

    def test_rejects_a_child_before_its_root(self) -> None:
        with self.assertRaisesRegex(RoiRevisionChainError, "no parent_result"):
            load_finalized_roi_revision_chain((self.child_path, self.root_path), self.segmentation, self.filtering, self.position_key)

    def test_rejects_a_child_that_does_not_name_the_immediately_prior_revision(self) -> None:
        sibling = finalize_roi_revision(RoiMaskRevision(source=self.source, operations=(RoiRevisionOperation.restore(2, reason="Restore synthetic label."),), editor="chain-reviewer", parent_revision_sha256=self.root.sha256), finalized_at="2026-07-21T23:10:00Z")
        sibling_path = self.root_directory / "sibling.json"
        export_roi_revision_artifact(replay_roi_revision(sibling, self.segmentation, self.filtering, self.position_key, parent_result=self.root_result), sibling_path)
        with self.assertRaisesRegex(RoiRevisionChainError, "parent revision hash"):
            load_finalized_roi_revision_chain((self.root_path, self.child_path, sibling_path), self.segmentation, self.filtering, self.position_key)

    def test_rejects_duplicate_paths_before_replaying_the_same_artifact_twice(self) -> None:
        with patch("funes.roi_revision_chain.load_roi_revision_artifact") as loader:
            with self.assertRaisesRegex(RoiRevisionChainError, "repeats artifact path"):
                load_finalized_roi_revision_chain((self.root_path, self.root_path), self.segmentation, self.filtering, self.position_key)
        loader.assert_not_called()

    def test_rejects_an_artifact_changed_during_strict_validation(self) -> None:
        with patch("funes.roi_revision_chain._file_sha256", side_effect=("a" * 64, "b" * 64)):
            with self.assertRaisesRegex(RoiRevisionChainError, "changed while loading"):
                load_finalized_roi_revision_chain((self.root_path,), self.segmentation, self.filtering, self.position_key)


if __name__ == "__main__":
    unittest.main()
