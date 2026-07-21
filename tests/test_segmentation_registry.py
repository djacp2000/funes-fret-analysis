import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.segmentation_engine import SegmentationEngineUnavailableError
from funes.segmentation_registry import (
    BENCHMARK_BASELINE_PROFILES,
    DEFAULT_SEGMENTATION_CONFIGURATION,
    DEFAULT_SEGMENTATION_REGISTRY,
    PROVISIONAL_WORKING_KMEANS_PROFILE,
    segment_configured_first_frame,
)
from funes.segmentation_selection import (
    BENCHMARK_BASELINE_PROFILE,
    PROVISIONAL_WORKING_PROFILE,
    SEGMENTATION_METHOD_ORDER,
    CapturePositionKey,
    SegmentationConfiguration,
    SegmentationMethodId,
    SegmentationSelection,
    SegmentationSelectionSource,
)


class SegmentationRegistryTests(unittest.TestCase):
    def test_confirmed_order_and_default_are_stable_typed_values(self) -> None:
        self.assertEqual(
            SEGMENTATION_METHOD_ORDER,
            (
                SegmentationMethodId.KMEANS,
                SegmentationMethodId.CELLPOSE_CPSAM,
                SegmentationMethodId.MARKER_WATERSHED,
                SegmentationMethodId.OTSU_GLOBAL,
                SegmentationMethodId.CONTROL_P99,
            ),
        )
        self.assertEqual(
            tuple(item.method for item in DEFAULT_SEGMENTATION_REGISTRY.methods),
            SEGMENTATION_METHOD_ORDER,
        )
        resolved = DEFAULT_SEGMENTATION_CONFIGURATION.resolve()
        self.assertEqual(resolved.method, SegmentationMethodId.KMEANS)
        self.assertEqual(resolved.profile, PROVISIONAL_WORKING_PROFILE)
        self.assertEqual(resolved.source, SegmentationSelectionSource.GLOBAL)

    def test_baselines_and_only_the_explicit_provisional_profile_are_registered(self) -> None:
        self.assertEqual(len(BENCHMARK_BASELINE_PROFILES), 5)
        for method in SEGMENTATION_METHOD_ORDER:
            profiles = DEFAULT_SEGMENTATION_REGISTRY.profiles_for(method)
            expected = (
                (BENCHMARK_BASELINE_PROFILE, PROVISIONAL_WORKING_PROFILE)
                if method is SegmentationMethodId.KMEANS
                else (BENCHMARK_BASELINE_PROFILE,)
            )
            self.assertEqual(tuple(profile.name for profile in profiles), expected)
            self.assertEqual(
                profiles[0].status,
                "diagnostic_baseline_not_accuracy_validated",
            )
        names = {profile.name for profile in BENCHMARK_BASELINE_PROFILES}
        self.assertNotIn("strict", names)
        self.assertNotIn("medium", names)
        self.assertNotIn("permissive", names)
        self.assertEqual(
            PROVISIONAL_WORKING_KMEANS_PROFILE.parameters[
                "minimum_object_area_pixels"
            ],
            32,
        )
        self.assertEqual(
            PROVISIONAL_WORKING_KMEANS_PROFILE.status,
            "provisional_working_profile_not_universally_validated",
        )
        self.assertEqual(
            PROVISIONAL_WORKING_KMEANS_PROFILE.known_limitations,
            (
                "faint_cells_may_be_omitted",
                "some_cells_may_have_partial_coverage",
                "touching_cells_may_be_combined_in_one_roi",
            ),
        )

    def test_capture_position_override_does_not_change_other_fields(self) -> None:
        first = CapturePositionKey("Capture 1", "Position 1")
        second = CapturePositionKey("Capture 1", "Position 2")
        configuration = SegmentationConfiguration(
            field_overrides={
                first: SegmentationSelection(
                    SegmentationMethodId.CONTROL_P99,
                    BENCHMARK_BASELINE_PROFILE,
                )
            }
        )

        overridden = configuration.resolve(first)
        untouched = configuration.resolve(second)

        self.assertEqual(overridden.method, SegmentationMethodId.CONTROL_P99)
        self.assertEqual(overridden.source, SegmentationSelectionSource.CAPTURE_POSITION_OVERRIDE)
        self.assertTrue(overridden.override_applied)
        self.assertEqual(overridden.global_method, SegmentationMethodId.KMEANS)
        self.assertEqual(untouched.method, SegmentationMethodId.KMEANS)
        self.assertEqual(untouched.source, SegmentationSelectionSource.GLOBAL)
        self.assertFalse(untouched.override_applied)

    def test_configured_result_preserves_global_and_override_provenance(self) -> None:
        key = CapturePositionKey("Capture 2", "Position 3")
        configuration = SegmentationConfiguration(
            field_overrides={
                key: SegmentationSelection(SegmentationMethodId.CONTROL_P99)
            }
        )
        frame = np.zeros((30, 30), dtype=np.float64)
        frame[10:20, 10:20] = 100.0

        result = segment_configured_first_frame(frame, configuration, key)

        record = result.engine
        provenance = record.selection
        self.assertEqual(record.method, SegmentationMethodId.CONTROL_P99)
        self.assertEqual(record.profile, BENCHMARK_BASELINE_PROFILE)
        self.assertIsNotNone(provenance)
        self.assertEqual(provenance.effective_method, SegmentationMethodId.CONTROL_P99)
        self.assertEqual(provenance.global_method, SegmentationMethodId.KMEANS)
        self.assertEqual(provenance.global_profile, PROVISIONAL_WORKING_PROFILE)
        self.assertEqual(provenance.source, SegmentationSelectionSource.CAPTURE_POSITION_OVERRIDE)
        self.assertEqual(provenance.capture, "Capture 2")
        self.assertEqual(provenance.position, "Position 3")
        self.assertEqual(record.parameters["threshold_percentile"], 99.0)
        self.assertEqual(record.parameters["postprocessing"], "none")
        self.assertIn("numpy", record.package_versions)

    def test_seeded_kmeans_baseline_is_deterministic_and_auditable(self) -> None:
        rows, columns = np.indices((100, 100))
        frame = (rows + columns).astype(np.float64)
        frame[15:45, 10:40] += 200.0
        frame[55:90, 55:90] += 400.0
        key = CapturePositionKey("Capture 1", "Position 1")

        first = segment_configured_first_frame(
            frame,
            DEFAULT_SEGMENTATION_CONFIGURATION,
            key,
        )
        second = segment_configured_first_frame(
            frame,
            DEFAULT_SEGMENTATION_CONFIGURATION,
            key,
        )

        np.testing.assert_array_equal(first.label_image, second.label_image)
        self.assertEqual(first.engine.parameters, second.engine.parameters)
        self.assertEqual(first.engine.seeds, {"random_state": 1729})
        self.assertEqual(first.engine.method, SegmentationMethodId.KMEANS)
        self.assertEqual(first.engine.profile, PROVISIONAL_WORKING_PROFILE)
        self.assertEqual(first.engine.parameters["minimum_object_area_pixels"], 32)
        for package in ("numpy", "scipy", "scikit-image", "scikit-learn"):
            self.assertIn(package, first.engine.package_versions)

    def test_all_classical_baselines_execute_on_synthetic_frame(self) -> None:
        rows, columns = np.indices((120, 120))
        frame = np.zeros((120, 120), dtype=np.float64)
        frame[(rows - 35) ** 2 + (columns - 35) ** 2 <= 13**2] = 100.0
        frame[(rows - 82) ** 2 + (columns - 82) ** 2 <= 16**2] = 220.0
        frame += (rows + columns) * 0.01
        key = CapturePositionKey("Capture 1", "Position 1")

        for method in (
            SegmentationMethodId.KMEANS,
            SegmentationMethodId.MARKER_WATERSHED,
            SegmentationMethodId.OTSU_GLOBAL,
            SegmentationMethodId.CONTROL_P99,
        ):
            with self.subTest(method=method.value):
                result = segment_configured_first_frame(
                    frame,
                    SegmentationConfiguration(
                        global_selection=SegmentationSelection(method)
                    ),
                    key,
                )
                self.assertGreaterEqual(result.roi_count, 1)
                self.assertEqual(result.engine.method, method)
                self.assertIn("postprocessing", result.engine.parameters)
                self.assertTrue(result.engine.package_versions)

    def test_cellpose_dependency_failure_is_actionable_and_never_falls_back(self) -> None:
        configuration = SegmentationConfiguration(
            global_selection=SegmentationSelection(SegmentationMethodId.CELLPOSE_CPSAM)
        )
        key = CapturePositionKey("Capture 1", "Position 1")
        with patch(
            "funes.segmentation_cellpose.import_module",
            side_effect=ModuleNotFoundError("cellpose unavailable for test"),
        ):
            with self.assertRaises(SegmentationEngineUnavailableError) as raised:
                segment_configured_first_frame(
                    np.zeros((20, 20), dtype=np.float64),
                    configuration,
                    key,
                )

        self.assertEqual(raised.exception.method, SegmentationMethodId.CELLPOSE_CPSAM)
        self.assertIn("pip install -e .[cellpose]", str(raised.exception))
        self.assertIn("46-55 minutes", str(raised.exception))
        self.assertNotIn("kmeans_morphology", str(raised.exception))

    def test_unknown_profile_lists_available_profile(self) -> None:
        configuration = SegmentationConfiguration(
            global_selection=SegmentationSelection(
                SegmentationMethodId.KMEANS,
                "medium",
            )
        )
        with self.assertRaisesRegex(
            ValueError,
            "available profiles: benchmark_baseline, provisional_working_kmeans_area32",
        ):
            DEFAULT_SEGMENTATION_REGISTRY.create_engine(configuration.resolve())


if __name__ == "__main__":
    unittest.main()
