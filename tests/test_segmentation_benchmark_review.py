import csv
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import tifffile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import Channel
from funes.segmentation_benchmark import (
    PARAMETER_BENCHMARK_EXTENSION_VARIANTS,
    SegmentationBenchmarkVariant,
    variants_for_method,
)
from funes.segmentation_benchmark_review import (
    PreparedSegmentationBenchmarkField,
    SegmentationBenchmarkReviewError,
    SegmentationBenchmarkReviewPlan,
    export_segmentation_benchmark_review,
    prepare_explicit_benchmark_review_fields,
)
from funes.segmentation_selection import CapturePositionKey, SegmentationMethodId


class SegmentationBenchmarkReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="funes_benchmark_review_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir)

    def test_prepares_only_explicit_fields_with_channel_and_source_provenance(self) -> None:
        raw = self.tmpdir / "raw"
        raw.mkdir()
        self._write_pair(raw, "Capture 1", "Position 1", 101, 401)
        self._write_pair(raw, "Capture 1", "Position 2", 201, 501)

        selected = prepare_explicit_benchmark_review_fields(
            raw,
            (CapturePositionKey("Capture 1", "Position 2"),),
        )

        self.assertEqual(len(selected), 1)
        field = selected[0]
        self.assertEqual(field.field_key.position, "Position 2")
        self.assertEqual(field.selected_channel, Channel.C1)
        self.assertEqual(field.preprocessing_method, "identity_segmentation_preprocessing")
        self.assertIn("Position 2", field.selected_source_path.name)
        self.assertEqual(
            field.selected_source_sha256,
            hashlib.sha256(field.selected_source_path.read_bytes()).hexdigest(),
        )
        self.assertFalse(field.prepared_frame.flags.writeable)

    def test_exports_exact_raw_labels_visual_index_and_hash_manifest(self) -> None:
        source = self.tmpdir / "selected_source.tif"
        source.write_bytes(b"immutable synthetic source")
        frame = np.arange(400, dtype=np.float64).reshape(20, 20)
        field = PreparedSegmentationBenchmarkField(
            field_key=CapturePositionKey("Capture 3", "Position 4"),
            prepared_frame=frame,
            selected_channel=Channel.C1,
            channel_selection_method="explicit_test_selection",
            robust_contrast_by_channel={"C0": 10.0, "C1": 20.0},
            preprocessing_method="identity_segmentation_preprocessing",
            preprocessing_parameters={"preserves_pixel_values": True},
            selected_source_path=source,
            selected_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        p99 = variants_for_method(SegmentationMethodId.CONTROL_P99)
        plan = SegmentationBenchmarkReviewPlan(
            selection_id="synthetic_explicit_review",
            fields=(field,),
            variants=(p99[0], p99[1]),
            selection_note="Chosen for artifact contract testing only.",
        )

        result = export_segmentation_benchmark_review(plan, self.tmpdir / "review")

        self.assertEqual(len(result.artifacts), 2)
        selection = json.loads(result.selection_path.read_text(encoding="utf-8"))
        self.assertFalse(selection["sample_sufficiency_assessed"])
        self.assertFalse(selection["method_ranking_performed"])
        self.assertFalse(selection["profile_approval_performed"])
        self.assertFalse(selection["d046_review_ledger_used"])
        self.assertEqual(
            selection["execution_timing_purpose"],
            "operational_only_not_scientific_comparison",
        )
        self.assertEqual(len(selection["fields"]), 1)
        self.assertEqual(len(selection["variants"]), 2)

        for artifact in result.artifacts:
            saved = np.load(artifact.label_image_path, allow_pickle=False)
            np.testing.assert_array_equal(saved, artifact.run.segmentation.label_image)
            self.assertTrue(artifact.preview_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            overlay = artifact.overlay_path.read_text(encoding="utf-8")
            self.assertIn("Unclassified contour", overlay)
            self.assertIn("No ranking or approval", overlay)

        html = result.index_path.read_text(encoding="utf-8")
        self.assertIn("sample sufficiency was not assessed", html)
        self.assertIn("do not rank methods, classify variants, or approve a profile", html)
        with result.observations_path.open(encoding="utf-8", newline="") as handle:
            observations = list(csv.DictReader(handle))
        self.assertEqual(len(observations), 2)
        self.assertTrue(all(row["whole_cell_shape_notes"] == "" for row in observations))

        with result.runs_path.open(encoding="utf-8", newline="") as handle:
            runs = list(csv.DictReader(handle))
        self.assertEqual(len(runs), 2)
        self.assertTrue(
            all(float(row["segmentation_execution_seconds"]) >= 0.0 for row in runs)
        )
        self.assertTrue(
            all(
                row["execution_timing_scope"]
                == "segmentation_engine_only_operational"
                for row in runs
            )
        )

        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["operational_timing"]["purpose"],
            "operational_only_not_scientific_comparison",
        )
        self.assertEqual(manifest["operational_timing"]["run_count"], 2)
        for item in manifest["artifacts"]:
            path = result.output_dir / item["path"]
            self.assertEqual(item["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_accepts_authorized_extension_and_preserves_origin(self) -> None:
        field = self._prepared_field()
        variant = PARAMETER_BENCHMARK_EXTENSION_VARIANTS[0]
        plan = SegmentationBenchmarkReviewPlan(
            selection_id="authorized_extension",
            fields=(field,),
            variants=(variant,),
        )

        result = export_segmentation_benchmark_review(plan, self.tmpdir / "extension")

        selection = json.loads(result.selection_path.read_text(encoding="utf-8"))
        self.assertEqual(selection["variants"][0]["origin"], variant.origin)
        with result.runs_path.open(encoding="utf-8", newline="") as handle:
            run = next(csv.DictReader(handle))
        self.assertEqual(run["variant_origin"], variant.origin)

    def test_rejects_duplicates_non_grid_variants_and_nonempty_output(self) -> None:
        field = self._prepared_field()
        baseline = variants_for_method(SegmentationMethodId.CONTROL_P99)[0]
        with self.assertRaisesRegex(ValueError, "fields must be unique"):
            SegmentationBenchmarkReviewPlan(
                selection_id="duplicate_fields",
                fields=(field, field),
                variants=(baseline,),
            )
        altered = SegmentationBenchmarkVariant(
            method=SegmentationMethodId.CONTROL_P99,
            variant_id="unregistered_test_variant",
            effective_parameters={
                "threshold_percentile": 97.0,
                "foreground_rule": "pixel_value_greater_than_threshold",
                "connectivity": 8,
                "postprocessing": "none",
                "touching_cells": "not_split",
            },
            changed_parameter="threshold_percentile",
            baseline_value=99.0,
            candidate_value=97.0,
        )
        with self.assertRaisesRegex(ValueError, "unchanged members"):
            SegmentationBenchmarkReviewPlan(
                selection_id="outside_grid",
                fields=(field,),
                variants=(altered,),
            )

        output = self.tmpdir / "occupied"
        output.mkdir()
        (output / "existing.txt").write_text("preserve", encoding="utf-8")
        plan = SegmentationBenchmarkReviewPlan(
            selection_id="occupied_output",
            fields=(field,),
            variants=(baseline,),
        )
        with self.assertRaises(SegmentationBenchmarkReviewError):
            export_segmentation_benchmark_review(plan, output)
        self.assertEqual((output / "existing.txt").read_text(encoding="utf-8"), "preserve")

    def test_missing_explicit_field_has_actionable_context(self) -> None:
        raw = self.tmpdir / "empty_raw"
        raw.mkdir()
        with self.assertRaisesRegex(
            SegmentationBenchmarkReviewError,
            r"Capture 9 \+ Position 8",
        ):
            prepare_explicit_benchmark_review_fields(
                raw,
                (CapturePositionKey("Capture 9", "Position 8"),),
            )

    def _prepared_field(self) -> PreparedSegmentationBenchmarkField:
        source = self.tmpdir / "source.tif"
        source.write_bytes(b"source")
        return PreparedSegmentationBenchmarkField(
            field_key=CapturePositionKey("Capture 1", "Position 1"),
            prepared_frame=np.arange(100, dtype=np.float64).reshape(10, 10),
            selected_channel=Channel.C1,
            channel_selection_method="test",
            robust_contrast_by_channel={"C0": 1.0, "C1": 2.0},
            preprocessing_method="identity",
            preprocessing_parameters={},
            selected_source_path=source,
            selected_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        )

    @staticmethod
    def _write_pair(
        directory: Path,
        capture: str,
        position: str,
        c0_signal: int,
        c1_signal: int,
    ) -> None:
        for channel, signal in (("C0", c0_signal), ("C1", c1_signal)):
            frames = np.zeros((2, 12, 12), dtype=np.uint16)
            frames[:, 3:9, 3:9] = signal
            path = directory / f"{capture} - {position}_XY123_Z0_T00_{channel}.tif"
            tifffile.imwrite(path, frames)


if __name__ == "__main__":
    unittest.main()
