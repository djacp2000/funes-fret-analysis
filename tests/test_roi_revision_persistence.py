import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

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
    finalize_roi_revision,
)
from funes.roi_revision_replay import replay_roi_revision
from funes.roi_revision_persistence import (
    RoiRevisionArtifactError,
    export_roi_revision_artifact,
    load_roi_revision_artifact,
    roi_revision_artifact_payload_sha256,
)
from funes.segmentation_engine import SegmentationEngineRecord, SegmentationResult


class RoiRevisionPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        labels = np.zeros((6, 7), dtype=np.int32)
        labels[1:3, 1:3] = 1
        labels[4, 3] = 2
        self.segmentation = SegmentationResult(
            labels,
            2,
            SegmentationEngineRecord("synthetic", "test", None),
        )
        self.filtering = filter_segmentation_rois(
            self.segmentation,
            RoiGeometryFilterConfig(
                min_area_pixels=2,
                border_policy=BorderTouchPolicy.ACCEPT,
            ),
        )
        self.position_key = PositionKey(
            "Capture 2", "Position 3", "Experiment JSON"
        )
        self.source = RoiRevisionSourceIdentity.from_automatic_results(
            self.position_key,
            self.segmentation,
            self.filtering,
        )
        self.draft = RoiMaskRevision(
            source=self.source,
            operations=(
                RoiRevisionOperation.replace(
                    1,
                    ((1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)),
                    reason="Expand the retained synthetic support.",
                ),
                RoiRevisionOperation.restore(
                    2,
                    reason="Restore a Module 8-rejected synthetic label.",
                ),
                RoiRevisionOperation.add(
                    3,
                    ((3, 5), (4, 5)),
                    reason="Add one omitted synthetic label.",
                ),
            ),
            editor="json-reviewer",
        )
        self.revision = finalize_roi_revision(
            self.draft,
            finalized_at="2026-07-21T19:00:00Z",
        )
        self.result = replay_roi_revision(
            self.revision,
            self.segmentation,
            self.filtering,
            self.position_key,
        )

    def test_strict_round_trip_replays_masks_and_retains_exact_original_objects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "revision.json"
            written = export_roi_revision_artifact(self.result, path)
            restored = load_roi_revision_artifact(
                path,
                self.segmentation,
                self.filtering,
                self.position_key,
            )
            file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

        self.assertEqual(written.sha256, file_sha256)
        self.assertEqual(written.revision_sha256, self.result.revision_sha256)
        self.assertIs(restored.original_segmentation, self.segmentation)
        self.assertIs(restored.original_filtering, self.filtering)
        self.assertEqual(restored.revision, self.revision)
        self.assertEqual(restored.operation_trace, self.result.operation_trace)
        np.testing.assert_array_equal(
            restored.edited_label_image, self.result.edited_label_image
        )
        np.testing.assert_array_equal(
            restored.measurement_label_image,
            self.result.measurement_label_image,
        )
        self.assertFalse(restored.edited_label_image.flags.writeable)
        self.assertFalse(restored.measurement_label_image.flags.writeable)

    def test_changed_payload_unknown_fields_and_duplicate_fields_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "revision.json"
            export_roi_revision_artifact(self.result, path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["result"]["edited_label_image"][0][0] = 3
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(
                RoiRevisionArtifactError, "payload SHA-256 does not match"
            ):
                load_roi_revision_artifact(
                    path, self.segmentation, self.filtering, self.position_key
                )

            export_roi_revision_artifact(self.result, path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["unexpected"] = True
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(RoiRevisionArtifactError, "unknown.*unexpected"):
                load_roi_revision_artifact(
                    path, self.segmentation, self.filtering, self.position_key
                )

            export_roi_revision_artifact(self.result, path)
            rendered = path.read_text(encoding="utf-8")
            rendered = rendered.replace(
                "{\n",
                '{\n  "schema": "funes.module24.roi_revision_artifact.v1",\n',
                1,
            )
            path.write_text(rendered, encoding="utf-8")
            with self.assertRaisesRegex(RoiRevisionArtifactError, "duplicate JSON field"):
                load_roi_revision_artifact(
                    path, self.segmentation, self.filtering, self.position_key
                )

    def test_rehashed_mask_or_audit_tampering_fails_deterministic_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "revision.json"
            export_roi_revision_artifact(self.result, path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["result"]["measurement_label_image"][3][5] = 0
            raw["result"]["geometry_audit"]["records"][0]["area_pixels"] = 999
            raw["payload_sha256"] = roi_revision_artifact_payload_sha256(
                {"revision": raw["revision"], "result": raw["result"]}
            )
            path.write_text(json.dumps(raw), encoding="utf-8")

            with self.assertRaisesRegex(
                RoiRevisionArtifactError, "masks or audit.*deterministic replay"
            ):
                load_roi_revision_artifact(
                    path, self.segmentation, self.filtering, self.position_key
                )

    def test_rehashed_revision_tampering_and_unfinalized_revision_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "revision.json"
            export_roi_revision_artifact(self.result, path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["revision"]["operations"][0]["reason"] = "Changed after finalization."
            raw["payload_sha256"] = roi_revision_artifact_payload_sha256(
                {"revision": raw["revision"], "result": raw["result"]}
            )
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(RoiRevisionArtifactError, "revision SHA-256"):
                load_roi_revision_artifact(
                    path, self.segmentation, self.filtering, self.position_key
                )

            export_roi_revision_artifact(self.result, path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["revision"]["finalized_at"] = None
            raw["revision"]["revision_sha256"] = self.draft.sha256
            raw["payload_sha256"] = roi_revision_artifact_payload_sha256(
                {"revision": raw["revision"], "result": raw["result"]}
            )
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(RoiRevisionArtifactError, "only a finalized"):
                load_roi_revision_artifact(
                    path, self.segmentation, self.filtering, self.position_key
                )

    def test_wrong_scope_stale_automatic_results_and_extension_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "require.*json"):
                export_roi_revision_artifact(self.result, root / "revision.txt")

            path = root / "revision.json"
            export_roi_revision_artifact(self.result, path)
            with self.assertRaisesRegex(RoiRevisionArtifactError, "stale or does not match"):
                load_roi_revision_artifact(
                    path,
                    self.segmentation,
                    self.filtering,
                    PositionKey("Capture 2", "Position 4", "Experiment JSON"),
                )

            changed_filtering = filter_segmentation_rois(
                self.segmentation,
                RoiGeometryFilterConfig(
                    min_area_pixels=1,
                    border_policy=BorderTouchPolicy.ACCEPT,
                ),
            )
            with self.assertRaisesRegex(RoiRevisionArtifactError, "stale or does not match"):
                load_roi_revision_artifact(
                    path,
                    self.segmentation,
                    changed_filtering,
                    self.position_key,
                )

    def test_invalid_json_nonstandard_number_and_unknown_nested_field_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid = root / "invalid.json"
            invalid.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(RoiRevisionArtifactError, "invalid.*JSON"):
                load_roi_revision_artifact(
                    invalid, self.segmentation, self.filtering, self.position_key
                )

            nonstandard = root / "nan.json"
            nonstandard.write_text('{"value": NaN}', encoding="utf-8")
            with self.assertRaisesRegex(RoiRevisionArtifactError, "non-standard JSON"):
                load_roi_revision_artifact(
                    nonstandard, self.segmentation, self.filtering, self.position_key
                )

            path = root / "revision.json"
            export_roi_revision_artifact(self.result, path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["revision"]["operations"][0]["unexpected"] = 1
            raw["payload_sha256"] = roi_revision_artifact_payload_sha256(
                {"revision": raw["revision"], "result": raw["result"]}
            )
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(RoiRevisionArtifactError, "unknown.*unexpected"):
                load_roi_revision_artifact(
                    path, self.segmentation, self.filtering, self.position_key
                )


if __name__ == "__main__":
    unittest.main()
