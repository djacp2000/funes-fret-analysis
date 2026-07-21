import sys
import unittest
from collections import Counter
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.segmentation_benchmark import (
    PARAMETER_BENCHMARK_EXTENSION_ORIGIN,
    PARAMETER_BENCHMARK_EXTENSION_VARIANTS,
    PARAMETER_BENCHMARK_VARIANTS,
    SegmentationBenchmarkVariant,
    run_segmentation_benchmark_variant,
    variants_for_method,
)
from funes.segmentation_classical import MarkerWatershedConfig, OtsuMorphologyConfig
from funes.segmentation_engine import SegmentationEngineUnavailableError
from funes.segmentation_profile_catalog import BENCHMARK_BASELINE_PROFILES
from funes.segmentation_registry import DEFAULT_SEGMENTATION_REGISTRY
from funes.segmentation_selection import (
    BENCHMARK_BASELINE_PROFILE,
    PROVISIONAL_WORKING_PROFILE,
    SEGMENTATION_METHOD_ORDER,
    CapturePositionKey,
    SegmentationMethodId,
)


class SegmentationParameterBenchmarkTests(unittest.TestCase):
    def test_minimum_extension_is_separate_exactly_ofat_and_unregistered(self) -> None:
        self.assertEqual(len(PARAMETER_BENCHMARK_EXTENSION_VARIANTS), 3)
        self.assertEqual(
            tuple(
                (item.method, item.changed_parameter, item.candidate_value)
                for item in PARAMETER_BENCHMARK_EXTENSION_VARIANTS
            ),
            (
                (SegmentationMethodId.KMEANS, "minimum_object_area_pixels", 16),
                (SegmentationMethodId.MARKER_WATERSHED, "minimum_object_area_pixels", 16),
                (SegmentationMethodId.MARKER_WATERSHED, "foreground_threshold_scale", 0.8),
            ),
        )
        baselines = {profile.method: profile for profile in BENCHMARK_BASELINE_PROFILES}
        for variant in PARAMETER_BENCHMARK_EXTENSION_VARIANTS:
            baseline = baselines[variant.method]
            differences = tuple(
                name
                for name, value in baseline.parameters.items()
                if variant.effective_parameters[name] != value
            )
            self.assertEqual(differences, (variant.changed_parameter,))
            self.assertEqual(variant.origin, PARAMETER_BENCHMARK_EXTENSION_ORIGIN)
            self.assertNotIn(
                variant.variant_id,
                tuple(
                    profile.name
                    for profile in DEFAULT_SEGMENTATION_REGISTRY.profiles_for(variant.method)
                ),
            )

    def test_fixed_grid_has_confirmed_order_and_ofat_counts(self) -> None:
        counts = Counter(variant.method for variant in PARAMETER_BENCHMARK_VARIANTS)

        self.assertEqual(
            counts,
            {
                SegmentationMethodId.KMEANS: 8,
                SegmentationMethodId.CELLPOSE_CPSAM: 7,
                SegmentationMethodId.MARKER_WATERSHED: 9,
                SegmentationMethodId.OTSU_GLOBAL: 9,
                SegmentationMethodId.CONTROL_P99: 3,
            },
        )
        observed_order = tuple(
            dict.fromkeys(variant.method for variant in PARAMETER_BENCHMARK_VARIANTS)
        )
        self.assertEqual(observed_order, SEGMENTATION_METHOD_ORDER)
        for method in SEGMENTATION_METHOD_ORDER:
            variants = variants_for_method(method)
            self.assertTrue(variants[0].is_baseline)
            self.assertEqual(variants[0].variant_id, BENCHMARK_BASELINE_PROFILE)
            self.assertEqual(sum(variant.is_baseline for variant in variants), 1)

    def test_every_candidate_changes_exactly_one_baseline_parameter(self) -> None:
        baselines = {
            profile.method: profile.parameters
            for profile in BENCHMARK_BASELINE_PROFILES
        }

        for variant in PARAMETER_BENCHMARK_VARIANTS:
            baseline = baselines[variant.method]
            differences = [
                name
                for name, value in baseline.items()
                if variant.effective_parameters[name] != value
            ]
            if variant.is_baseline:
                self.assertEqual(differences, [])
            else:
                self.assertEqual(differences, [variant.changed_parameter])
                self.assertEqual(
                    baseline[variant.changed_parameter],
                    variant.baseline_value,
                )
                self.assertEqual(
                    variant.effective_parameters[variant.changed_parameter],
                    variant.candidate_value,
                )

    def test_grid_holds_non_varied_controls_and_registers_no_new_profiles(self) -> None:
        cellpose = variants_for_method(SegmentationMethodId.CELLPOSE_CPSAM)
        p99 = variants_for_method(SegmentationMethodId.CONTROL_P99)

        self.assertTrue(
            all(variant.effective_parameters["flow_threshold"] == 0.4 for variant in cellpose)
        )
        self.assertTrue(
            all(variant.effective_parameters["connectivity"] == 8 for variant in p99)
        )
        for method in SEGMENTATION_METHOD_ORDER:
            registered = DEFAULT_SEGMENTATION_REGISTRY.profiles_for(method)
            expected = (
                (BENCHMARK_BASELINE_PROFILE, PROVISIONAL_WORKING_PROFILE)
                if method is SegmentationMethodId.KMEANS
                else (BENCHMARK_BASELINE_PROFILE,)
            )
            self.assertEqual(
                tuple(profile.name for profile in registered),
                expected,
            )

    def test_variant_is_immutable_and_rejects_incoherent_change(self) -> None:
        variant = variants_for_method(SegmentationMethodId.KMEANS)[1]
        with self.assertRaises(TypeError):
            variant.effective_parameters["minimum_object_area_pixels"] = 999
        with self.assertRaises(FrozenInstanceError):
            variant.variant_id = "changed"
        with self.assertRaisesRegex(ValueError, "candidate_value must match"):
            SegmentationBenchmarkVariant(
                method=SegmentationMethodId.CONTROL_P99,
                variant_id="invalid",
                effective_parameters={"threshold_percentile": 98.0},
                changed_parameter="threshold_percentile",
                baseline_value=99.0,
                candidate_value=99.5,
            )

    def test_explicit_variant_run_preserves_field_parameters_and_summary(self) -> None:
        variant = next(
            item
            for item in variants_for_method(SegmentationMethodId.CONTROL_P99)
            if item.candidate_value == 98.0
        )
        frame = np.arange(10_000, dtype=np.float64).reshape(100, 100)
        key = CapturePositionKey("Capture 3", "Position 4")

        run = run_segmentation_benchmark_variant(frame, key, variant)

        self.assertEqual(run.field_key, key)
        self.assertEqual(run.segmentation.engine.method, SegmentationMethodId.CONTROL_P99)
        self.assertEqual(run.segmentation.engine.profile, variant.variant_id)
        self.assertIsNone(run.segmentation.engine.selection)
        self.assertEqual(run.segmentation.engine.parameters["threshold_percentile"], 98.0)
        self.assertEqual(run.summary.roi_count, 1)
        self.assertEqual(run.summary.foreground_pixel_count, 200)
        self.assertAlmostEqual(run.summary.foreground_fraction, 0.02)
        self.assertEqual(run.summary.roi_area_median_pixels, 200.0)

    def test_otsu_scale_records_base_and_effective_threshold(self) -> None:
        variant = next(
            item
            for item in variants_for_method(SegmentationMethodId.OTSU_GLOBAL)
            if item.changed_parameter == "threshold_scale" and item.candidate_value == 0.9
        )
        rows, columns = np.indices((80, 80))
        frame = (rows + columns).astype(np.float64)
        frame[20:55, 20:55] += 100.0

        run = run_segmentation_benchmark_variant(
            frame,
            CapturePositionKey("Capture 1", "Position 1"),
            variant,
        )

        parameters = run.segmentation.engine.parameters
        self.assertEqual(parameters["threshold_scale"], 0.9)
        self.assertAlmostEqual(
            parameters["threshold_value"],
            parameters["base_otsu_threshold_value"] * 0.9,
        )

    def test_threshold_scale_controls_reject_non_positive_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "threshold_scale must be greater"):
            OtsuMorphologyConfig(threshold_scale=0.0)
        with self.assertRaisesRegex(
            ValueError,
            "foreground_threshold_scale must be greater",
        ):
            MarkerWatershedConfig(foreground_threshold_scale=-0.1)

    def test_cellpose_candidate_is_only_run_explicitly_and_never_falls_back(self) -> None:
        candidate = variants_for_method(SegmentationMethodId.CELLPOSE_CPSAM)[1]
        with patch(
            "funes.segmentation_cellpose.import_module",
            side_effect=ModuleNotFoundError("cellpose unavailable for test"),
        ):
            with self.assertRaises(SegmentationEngineUnavailableError) as raised:
                run_segmentation_benchmark_variant(
                    np.zeros((20, 20), dtype=np.float64),
                    CapturePositionKey("Capture 1", "Position 1"),
                    candidate,
                )

        self.assertEqual(raised.exception.method, SegmentationMethodId.CELLPOSE_CPSAM)
        self.assertNotIn("kmeans_morphology", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
