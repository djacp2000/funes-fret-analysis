import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import Channel
from funes.segmentation_benchmark import (
    PARAMETER_BENCHMARK_EXTENSION_VARIANTS,
    PARAMETER_BENCHMARK_VARIANTS,
)
from funes.segmentation_benchmark_review import PreparedSegmentationBenchmarkField
from funes.segmentation_kmeans import (
    KMeansMorphologyConfig,
    KMeansMorphologySegmentationEngine,
)
from funes.segmentation_kmeans_causal import (
    KMEANS_AREA32_CAUSAL_REFERENCE_PARAMETERS,
    KMEANS_FOREGROUND_CAUSAL_EXTENSION_VARIANTS,
    run_kmeans_foreground_causal_variant,
)
from funes.segmentation_kmeans_causal_review import (
    KMeansForegroundCausalReviewInput,
    KMeansForegroundCausalReviewPlan,
    export_kmeans_foreground_causal_review,
)
from funes.segmentation_registry import DEFAULT_SEGMENTATION_REGISTRY
from funes.segmentation_selection import CapturePositionKey, SegmentationMethodId


class KMeansForegroundCausalTests(unittest.TestCase):
    def test_relaxation_validation_and_zero_preserve_exact_selection(self) -> None:
        for invalid in (-0.1, 1.0, float("nan"), True):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    ValueError, "foreground_boundary_relaxation_fraction"
                ):
                    KMeansMorphologyConfig(
                        foreground_boundary_relaxation_fraction=invalid
                    )

        frame = self._diagnostic_frame((90, 90))
        engine = KMeansMorphologySegmentationEngine(
            KMeansMorphologyConfig(
                foreground_boundary_relaxation_fraction=0.0,
                minimum_object_area_pixels=32,
            )
        )
        ordinary = engine.segment(frame)
        traced, trace = engine.segment_with_diagnostic_trace(frame)

        np.testing.assert_array_equal(ordinary.label_image, traced.label_image)
        np.testing.assert_array_equal(
            trace.baseline_raw_foreground, trace.relaxed_raw_foreground
        )
        self.assertEqual(trace.stage_change_counts["raw_added_pixels"], 0)
        self.assertEqual(trace.stage_change_counts["raw_removed_pixels"], 0)
        self.assertEqual(trace.baseline_threshold, trace.candidate_threshold)

    def test_relaxed_trace_is_deterministic_monotonic_and_uses_declared_boundary(self) -> None:
        frame = self._diagnostic_frame((120, 120))
        config = KMeansMorphologyConfig(
            foreground_boundary_relaxation_fraction=0.5,
            minimum_object_area_pixels=32,
        )
        first_result, first = KMeansMorphologySegmentationEngine(
            config
        ).segment_with_diagnostic_trace(frame)
        second_result, second = KMeansMorphologySegmentationEngine(
            config
        ).segment_with_diagnostic_trace(frame)

        np.testing.assert_array_equal(first_result.label_image, second_result.label_image)
        np.testing.assert_array_equal(first.relaxed_raw_foreground, second.relaxed_raw_foreground)
        self.assertFalse(np.any(first.baseline_raw_foreground & ~first.relaxed_raw_foreground))
        np.testing.assert_array_equal(
            first.raw_added_support,
            first.relaxed_raw_foreground & ~first.baseline_raw_foreground,
        )
        self.assertGreater(first.stage_change_counts["raw_added_pixels"], 0)
        c0, c1 = first.ordered_cluster_centers[:2]
        self.assertAlmostEqual(first.baseline_threshold, c0 + 0.5 * (c1 - c0))
        self.assertAlmostEqual(first.candidate_threshold, c0 + 0.25 * (c1 - c0))
        self.assertFalse(first.raw_added_support.flags.writeable)

    def test_catalog_is_one_factor_from_area32_and_is_not_registered_or_ofat(self) -> None:
        self.assertEqual(len(KMEANS_FOREGROUND_CAUSAL_EXTENSION_VARIANTS), 1)
        variant = KMEANS_FOREGROUND_CAUSAL_EXTENSION_VARIANTS[0]
        differences = tuple(
            name
            for name, value in KMEANS_AREA32_CAUSAL_REFERENCE_PARAMETERS.items()
            if variant.effective_parameters[name] != value
        )

        self.assertEqual(differences, ("foreground_boundary_relaxation_fraction",))
        self.assertEqual(variant.candidate_value, 0.5)
        self.assertEqual(variant.effective_parameters["minimum_object_area_pixels"], 32)
        self.assertNotIn(variant, PARAMETER_BENCHMARK_VARIANTS)
        self.assertNotIn(variant, PARAMETER_BENCHMARK_EXTENSION_VARIANTS)
        self.assertNotIn(
            variant.variant_id,
            tuple(
                profile.name
                for profile in DEFAULT_SEGMENTATION_REGISTRY.profiles_for(
                    SegmentationMethodId.KMEANS
                )
            ),
        )

    def test_runner_rejects_unauthorized_variant_and_keeps_area32(self) -> None:
        variant = KMEANS_FOREGROUND_CAUSAL_EXTENSION_VARIANTS[0]
        unauthorized = replace(variant, variant_id="unauthorized_copy")
        frame = self._diagnostic_frame((80, 80))
        key = CapturePositionKey("Capture 1", "Position 1")

        with self.assertRaisesRegex(ValueError, "unchanged D062"):
            run_kmeans_foreground_causal_variant(frame, key, unauthorized)
        run = run_kmeans_foreground_causal_variant(frame, key, variant)

        self.assertEqual(run.segmentation.engine.parameters["minimum_object_area_pixels"], 32)
        self.assertEqual(
            run.segmentation.engine.parameters[
                "foreground_boundary_relaxation_fraction"
            ],
            0.5,
        )

    @staticmethod
    def _diagnostic_frame(shape: tuple[int, int]) -> np.ndarray:
        frame = np.zeros(shape, dtype=np.float64)
        frame[5:25, 5:25] = 40.0
        frame[shape[0] - 30 : shape[0] - 10, shape[1] - 30 : shape[1] - 10] = 100.0
        frame[30:35, 10:20] = 15.0
        return frame


class KMeansForegroundCausalReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="funes_kmeans_causal_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir)

    def test_synthetic_exact_two_call_package_preserves_masks_and_hashes(self) -> None:
        inputs = (
            self._review_input(CapturePositionKey("Capture 1", "Position 1"), 1),
            self._review_input(CapturePositionKey("Capture 1", "Position 2"), 2),
        )
        original_sources = tuple(item.field.selected_source_path.read_bytes() for item in inputs)
        plan = KMeansForegroundCausalReviewPlan(
            selection_id="synthetic_d062_contract_test",
            inputs=inputs,
        )

        result = export_kmeans_foreground_causal_review(
            plan, self.tmpdir / "causal_review"
        )

        self.assertEqual(len(result.artifacts), 2)
        selection = json.loads(result.selection_path.read_text(encoding="utf-8"))
        self.assertEqual(selection["engine_call_count"], 2)
        self.assertFalse(selection["sample_sufficiency_assessed"])
        self.assertFalse(selection["final_acceptability_assessed"])
        self.assertFalse(selection["d046_review_ledger_used"])
        self.assertEqual(
            selection["variant"]["effective_parameters"]["minimum_object_area_pixels"],
            32,
        )
        for artifact in result.artifacts:
            baseline = np.load(
                artifact.run_dir / "baseline_raw_foreground.npy", allow_pickle=False
            )
            relaxed = np.load(
                artifact.run_dir / "relaxed_raw_foreground.npy", allow_pickle=False
            )
            added = np.load(
                artifact.run_dir / "raw_added_support.npy", allow_pickle=False
            )
            final_labels = np.load(
                artifact.run_dir / "final_labels.npy", allow_pickle=False
            )
            self.assertFalse(np.any(baseline & ~relaxed))
            np.testing.assert_array_equal(added, relaxed & ~baseline)
            np.testing.assert_array_equal(final_labels, artifact.run.segmentation.label_image)
            self.assertIn("UNCLASSIFIED CAUSAL REVIEW", artifact.focus_sheet_path.read_text(encoding="utf-8"))
            self.assertTrue(artifact.full_preview_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["engine_call_count"], 2)
        for item in manifest["artifacts"]:
            path = result.output_dir / item["path"]
            self.assertEqual(item["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(
            tuple(item.field.selected_source_path.read_bytes() for item in inputs),
            original_sources,
        )

    def test_review_plan_rejects_unauthorized_variant_or_field_set(self) -> None:
        first = self._review_input(CapturePositionKey("Capture 1", "Position 1"), 1)
        second = self._review_input(CapturePositionKey("Capture 1", "Position 2"), 2)
        variant = KMEANS_FOREGROUND_CAUSAL_EXTENSION_VARIANTS[0]
        with self.assertRaisesRegex(ValueError, "fixed order"):
            KMeansForegroundCausalReviewPlan("wrong_fields", (second, first))
        with self.assertRaisesRegex(ValueError, "one-variant catalog"):
            KMeansForegroundCausalReviewPlan(
                "wrong_variant",
                (first, second),
                replace(variant, variant_id="unauthorized_copy"),
            )

    def _review_input(
        self, key: CapturePositionKey, seed: int
    ) -> KMeansForegroundCausalReviewInput:
        rng = np.random.default_rng(seed)
        frame = rng.normal(0.0, 0.1, size=(600, 600))
        frame[90:190, 100:210] += 15.0
        frame[300:420, 300:430] += 45.0
        frame[500:590, 255:355] += 100.0
        source = self.tmpdir / f"source_{seed}.tif"
        source.write_bytes(f"immutable synthetic source {seed}".encode("ascii"))
        reference = self.tmpdir / f"reference_{seed}.npy"
        np.save(reference, np.zeros((600, 600), dtype=np.int32), allow_pickle=False)
        prepared = PreparedSegmentationBenchmarkField(
            field_key=key,
            prepared_frame=frame,
            selected_channel=Channel.C1,
            channel_selection_method="synthetic_test_selection",
            robust_contrast_by_channel={"C0": 1.0, "C1": 2.0},
            preprocessing_method="identity_segmentation_preprocessing",
            preprocessing_parameters={"preserves_pixel_values": True},
            selected_source_path=source,
            selected_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        return KMeansForegroundCausalReviewInput(
            field=prepared,
            reference_labels_path=reference,
            reference_labels_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
