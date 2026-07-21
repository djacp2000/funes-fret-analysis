import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.segmentation_benchmark import (
    PARAMETER_BENCHMARK_EXTENSION_VARIANTS,
    PARAMETER_BENCHMARK_VARIANTS,
)
from funes.segmentation_kmeans import (
    KMeansMorphologyConfig,
    KMeansMorphologySegmentationEngine,
)
from funes.segmentation_kmeans_causal import KMEANS_FOREGROUND_CAUSAL_EXTENSION_VARIANTS
from funes.segmentation_kmeans_local_background import (
    KMEANS_LOCAL_BACKGROUND_REFERENCE_PARAMETERS,
    KMEANS_LOCAL_BACKGROUND_VARIANTS,
    LOCAL_BACKGROUND_CONTROL_MODE,
    LOCAL_BACKGROUND_P20_MODE,
    classify_local_background_topology,
    local_background_window_side,
    run_kmeans_local_background_candidate,
)
from funes.segmentation_registry import DEFAULT_SEGMENTATION_REGISTRY
from funes.segmentation_selection import SegmentationMethodId


class KMeansLocalBackgroundCandidateTests(unittest.TestCase):
    def test_exact_single_mode_candidate_keeps_every_fixed_control(self) -> None:
        self.assertEqual(len(KMEANS_LOCAL_BACKGROUND_VARIANTS), 1)
        variant = KMEANS_LOCAL_BACKGROUND_VARIANTS[0]
        differences = tuple(
            name
            for name, value in KMEANS_LOCAL_BACKGROUND_REFERENCE_PARAMETERS.items()
            if variant.effective_parameters[name] != value
        )

        self.assertEqual(differences, ("foreground_spatial_conditioning",))
        self.assertEqual(variant.baseline_value, LOCAL_BACKGROUND_CONTROL_MODE)
        self.assertEqual(variant.candidate_value, LOCAL_BACKGROUND_P20_MODE)
        self.assertEqual(
            variant.effective_parameters["foreground_boundary_relaxation_fraction"],
            0.0,
        )
        self.assertEqual(variant.effective_parameters["minimum_object_area_pixels"], 32)
        self.assertEqual(variant.effective_parameters["clusters"], 3)
        self.assertEqual(variant.effective_parameters["foreground_cluster_count"], 2)
        self.assertNotIn(variant, PARAMETER_BENCHMARK_VARIANTS)
        self.assertNotIn(variant, PARAMETER_BENCHMARK_EXTENSION_VARIANTS)
        self.assertNotIn(variant, KMEANS_FOREGROUND_CAUSAL_EXTENSION_VARIANTS)
        self.assertNotIn(
            variant.variant_id,
            tuple(
                profile.name
                for profile in DEFAULT_SEGMENTATION_REGISTRY.profiles_for(
                    SegmentationMethodId.KMEANS
                )
            ),
        )

    def test_window_formula_and_exact_linear_numpy_reflection(self) -> None:
        self.assertEqual(local_background_window_side((600, 600)), 151)
        self.assertEqual(local_background_window_side((40, 24)), 7)
        self.assertEqual(local_background_window_side((7, 20)), 1)
        with self.assertRaisesRegex(ValueError, "two positive"):
            local_background_window_side((0, 20))

        frame = np.arange(400, dtype=np.float64).reshape(20, 20)
        reference = self._control_labels(frame)
        _, trace = run_kmeans_local_background_candidate(frame, reference)
        pad = trace.local_window_side // 2
        padded = np.pad(frame, pad, mode="reflect")
        expected = np.empty_like(frame)
        for row in range(frame.shape[0]):
            for column in range(frame.shape[1]):
                window = padded[
                    row : row + trace.local_window_side,
                    column : column + trace.local_window_side,
                ]
                expected[row, column] = np.percentile(window, 20.0, method="linear")

        np.testing.assert_array_equal(trace.local_p20, expected)
        self.assertEqual(trace.local_window_side, 5)
        self.assertEqual(trace.local_percentile, 20.0)
        self.assertEqual(trace.local_percentile_method, "linear")
        self.assertEqual(trace.padding_rule, "numpy_reflect_no_edge_repeat")

    def test_candidate_is_deterministic_uses_exact_arithmetic_and_preserves_support(self) -> None:
        frame = self._spatial_offset_frame()
        reference = self._control_labels(frame)

        first_result, first = run_kmeans_local_background_candidate(frame, reference)
        second_result, second = run_kmeans_local_background_candidate(frame, reference)

        np.testing.assert_array_equal(first_result.label_image, second_result.label_image)
        np.testing.assert_array_equal(first.local_p20, second.local_p20)
        np.testing.assert_allclose(
            first.local_threshold_map, second.local_threshold_map, rtol=0.0, atol=1e-12
        )
        np.testing.assert_array_equal(first.candidate_raw_foreground, second.candidate_raw_foreground)
        np.testing.assert_array_equal(first.control_final_labels, reference)
        np.testing.assert_array_equal(first.candidate_final_labels, first_result.label_image)
        np.testing.assert_array_equal(
            first.local_threshold_map,
            first.baseline_threshold + np.minimum(0.0, first.local_p20 - first.field_p20),
        )
        self.assertFalse(np.any(first.local_threshold_map > first.baseline_threshold))
        self.assertFalse(
            np.any(first.baseline_raw_foreground & ~first.candidate_raw_foreground)
        )
        np.testing.assert_array_equal(
            first.raw_added_support,
            first.candidate_raw_foreground & ~first.baseline_raw_foreground,
        )
        self.assertFalse(np.any(first.raw_added_support & ~(first.local_p20 < first.field_p20)))
        self.assertGreater(first.stage_change_counts["raw_added_pixels"], 0)
        self.assertEqual(first.stage_change_counts["raw_removed_pixels"], 0)
        self.assertEqual(first.stage_change_counts["post_morphology_removed_pixels"], 0)
        self.assertEqual(first.stage_change_counts["final_removed_pixels"], 0)
        self.assertFalse(first.local_p20.flags.writeable)
        self.assertFalse(first.fit_sample_indices.flags.writeable)
        self.assertEqual(
            first_result.engine.parameters["foreground_spatial_conditioning"],
            LOCAL_BACKGROUND_P20_MODE,
        )
        self.assertEqual(
            first_result.engine.parameters["foreground_boundary_relaxation_fraction"],
            0.0,
        )

    def test_topology_classes_are_geometric_only_and_cover_all_declared_relations(self) -> None:
        baseline_raw = np.zeros((20, 20), dtype=bool)
        baseline_raw[1:3, 1:3] = True
        baseline_raw[1:3, 7:9] = True
        baseline_raw[8:10, 1:3] = True
        candidate_raw = baseline_raw.copy()
        candidate_raw[1:3, 3:7] = True  # one component touching two anchors
        candidate_raw[10, 1] = True  # one component touching one anchor
        candidate_raw[16, 16] = True  # detached component

        reference = np.zeros((20, 20), dtype=np.int32)
        reference[1:3, 1:3] = 1
        reference[1:3, 5:7] = 2
        reference[6:8, 1:3] = 3
        reference[6:8, 5:7] = 4
        candidate_labels = np.zeros_like(reference)
        candidate_labels[1:3, 1:7] = 1  # bridge labels 1 and 2
        candidate_labels[6:8, 1:3] = 2  # unchanged/carried label 3
        candidate_labels[6:9, 5:7] = 3  # expansion of label 4
        candidate_labels[12:14, 12:14] = 4  # de novo geometric candidate

        records = classify_local_background_topology(
            baseline_raw, candidate_raw, candidate_labels, reference
        )
        raw = [item for item in records if item.stage == "raw_added_support"]
        final = [item for item in records if item.stage == "candidate_final_label"]

        self.assertEqual(
            {item.geometric_class for item in raw},
            {"detached_proposal", "single_anchor_proposal", "multi_anchor_proposal"},
        )
        self.assertEqual(
            {item.geometric_class for item in final},
            {
                "de_novo_final_candidate",
                "existing_object_expansion",
                "unchanged_or_carried_object",
                "bridge_candidate",
            },
        )
        bridge = next(item for item in final if item.geometric_class == "bridge_candidate")
        self.assertEqual(bridge.overlapped_reference_labels, (1, 2))
        de_novo = next(
            item for item in final if item.geometric_class == "de_novo_final_candidate"
        )
        self.assertEqual(de_novo.overlapped_reference_labels, ())

    def test_runner_rejects_unauthorized_variant_and_nonmatching_reference(self) -> None:
        frame = self._spatial_offset_frame()
        reference = self._control_labels(frame)
        unauthorized = replace(
            KMEANS_LOCAL_BACKGROUND_VARIANTS[0], variant_id="unauthorized_copy"
        )
        with self.assertRaisesRegex(ValueError, "unchanged D068"):
            run_kmeans_local_background_candidate(frame, reference, unauthorized)

        wrong_reference = np.zeros_like(reference)
        with self.assertRaisesRegex(ValueError, "exact unchanged K area-32 control"):
            run_kmeans_local_background_candidate(frame, wrong_reference)

    @staticmethod
    def _control_labels(frame: np.ndarray) -> np.ndarray:
        return KMeansMorphologySegmentationEngine(
            KMeansMorphologyConfig(minimum_object_area_pixels=32)
        ).segment(frame).label_image

    @staticmethod
    def _spatial_offset_frame() -> np.ndarray:
        frame = np.full((80, 80), 10.0, dtype=np.float64)
        frame[:30, :30] = 0.0
        frame[8:20, 8:20] = 8.0
        frame[45:60, 10:25] = 25.0
        frame[45:65, 45:65] = 50.0
        return frame


if __name__ == "__main__":
    unittest.main()
