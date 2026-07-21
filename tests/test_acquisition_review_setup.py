import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import tifffile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.acquisition_loading import load_assigned_acquisition
from funes.acquisition_review_setup import (
    AcquisitionReviewExperimentConfig,
    AcquisitionReviewSetupError,
    initialize_acquisition_review,
)
from funes.contracts import PositionKey
from funes.experiment_assignment import ExperimentAssignmentRule
from funes.experiment_roi_review import ExperimentPositionReviewMode
from funes.segmentation_selection import (
    BENCHMARK_BASELINE_PROFILE,
    CapturePositionKey,
    SegmentationConfiguration,
    SegmentationMethodId,
    SegmentationReviewStatus,
    SegmentationSelection,
)


class AcquisitionReviewSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="funes_module19_"))
        self.selection = SegmentationSelection(
            SegmentationMethodId.CONTROL_P99,
            BENCHMARK_BASELINE_PROFILE,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def test_builds_fresh_scopes_in_d095_order_with_exact_inputs(self) -> None:
        self._write_pair("Capture 1", "Position 1")
        self._write_pair("Capture 2", "Position 1")
        load = load_assigned_acquisition(
            self.root,
            (
                ExperimentAssignmentRule("Experiment B", ("Capture 1",)),
                ExperimentAssignmentRule("Experiment A", ("Capture 2",)),
            ),
        )
        config_b = self._config("Experiment B")
        config_a = self._config("Experiment A")

        result = initialize_acquisition_review(load, (config_a, config_b))

        self.assertIs(result.acquisition, load)
        self.assertEqual(
            tuple(pair.position_key.experiment for pair in result.assigned_pairs),
            ("Experiment B", "Experiment A"),
        )
        self.assertTrue(
            all(
                actual is expected
                for actual, expected in zip(result.assigned_pairs, load.assigned_pairs)
            )
        )
        self.assertIs(result.experiment_configs[0], config_b)
        self.assertIs(result.experiment_configs[1], config_a)
        self.assertEqual(
            tuple(
                review.experiment
                for review in result.review_orchestrator.experiments
            ),
            ("Experiment B", "Experiment A"),
        )
        for config, review in zip(
            result.experiment_configs, result.review_orchestrator.experiments
        ):
            self.assertIs(
                review.review_state.configuration,
                config.segmentation_configuration,
            )
            self.assertEqual(review.review_state.inspections, ())
            self.assertIsNone(review.review_state.global_approval)
            self.assertTrue(
                all(
                    review.query(key).status is SegmentationReviewStatus.UNREVIEWED
                    for key in review.positions
                )
            )
        self.assertIs(result.pairs_for_experiment("Experiment A")[0], load.assigned_pairs[1])

    def test_review_selected_remains_pending_and_never_auto_approves(self) -> None:
        self._write_pair("Capture 1", "Position 1")
        self._write_pair("Capture 1", "Position 2")
        load = self._single_experiment_load()
        selected = (PositionKey("Capture 1", "Position 1", "Experiment A"),)

        result = initialize_acquisition_review(
            load,
            (
                AcquisitionReviewExperimentConfig(
                    experiment="Experiment A",
                    mode=ExperimentPositionReviewMode.REVIEW_SELECTED,
                    segmentation_configuration=SegmentationConfiguration(
                        global_selection=self.selection
                    ),
                    selected_positions=selected,
                ),
            ),
        )

        review = result.review_orchestrator.for_experiment("Experiment A")
        self.assertEqual(review.manual_review_targets, selected)
        self.assertEqual(review.pending_manual_positions, selected)
        self.assertEqual(review.unreviewed_positions, review.positions)
        self.assertIsNone(review.review_state.global_approval)

    def test_preserves_d044_override_without_satisfying_manual_target(self) -> None:
        self._write_pair("Capture 1", "Position 1")
        self._write_pair("Capture 1", "Position 2")
        load = self._single_experiment_load()
        key = PositionKey("Capture 1", "Position 1", "Experiment A")
        override = SegmentationSelection(
            SegmentationMethodId.KMEANS, "provisional_working_kmeans_area32"
        )
        configuration = SegmentationConfiguration(
            global_selection=self.selection,
            field_overrides={CapturePositionKey("Capture 1", "Position 1"): override},
        )

        result = initialize_acquisition_review(
            load,
            (
                AcquisitionReviewExperimentConfig(
                    "Experiment A",
                    ExperimentPositionReviewMode.REVIEW_ALL,
                    configuration,
                ),
            ),
        )

        review = result.review_orchestrator.for_experiment("Experiment A")
        self.assertIs(review.review_state.configuration, configuration)
        self.assertEqual(
            review.query(key).status, SegmentationReviewStatus.EXPLICIT_OVERRIDE
        )
        self.assertFalse(review.query(key).manually_inspected)
        self.assertIn(key, review.pending_manual_positions)
        self.assertIsNone(review.review_state.global_approval)

    def test_requires_exactly_one_explicit_config_per_loaded_experiment(self) -> None:
        self._write_pair("Capture 1", "Position 1")
        load = self._single_experiment_load()
        config_a = self._config("Experiment A")
        config_b = self._config("Experiment B")

        with self.assertRaisesRegex(AcquisitionReviewSetupError, "missing"):
            initialize_acquisition_review(load, ())
        with self.assertRaisesRegex(AcquisitionReviewSetupError, "unexpected"):
            initialize_acquisition_review(load, (config_a, config_b))
        with self.assertRaisesRegex(AcquisitionReviewSetupError, "duplicate"):
            initialize_acquisition_review(load, (config_a, config_a))

    def test_refuses_error_bearing_load_without_downstream_side_effects(self) -> None:
        self._write_pair("Capture 1", "Position 1")
        tifffile.imwrite(
            self.root / "unrecognized.tif",
            np.zeros((2, 3, 3), dtype=np.uint16),
        )
        load = self._single_experiment_load()
        forbidden = (
            "funes.acquisition_loading.load_assigned_acquisition",
            "funes.segmentation_review.SegmentationReviewState.approve_global",
            "funes.position_analysis.run_reviewed_position_analysis",
            "funes.experiment_analysis.run_reviewed_experiment_analysis",
            "funes.reviewed_experiment_export.export_reviewed_experiment_workbook",
            "funes.experiment_roi_review_persistence.export_experiment_roi_review_snapshot",
        )
        patchers = [patch(target) for target in forbidden]
        spies = [patcher.start() for patcher in patchers]
        for patcher in patchers:
            self.addCleanup(patcher.stop)

        with self.assertRaisesRegex(AcquisitionReviewSetupError, "error-bearing"):
            initialize_acquisition_review(load, (self._config("Experiment A"),))

        for target, spy in zip(forbidden, spies):
            with self.subTest(forbidden=target):
                spy.assert_not_called()

    def _config(self, experiment: str) -> AcquisitionReviewExperimentConfig:
        return AcquisitionReviewExperimentConfig(
            experiment=experiment,
            mode=ExperimentPositionReviewMode.REVIEW_ALL,
            segmentation_configuration=SegmentationConfiguration(
                global_selection=self.selection
            ),
        )

    def _single_experiment_load(self):
        return load_assigned_acquisition(
            self.root,
            (ExperimentAssignmentRule("Experiment A", ("Capture 1",)),),
        )

    def _write_pair(self, capture: str, position: str) -> None:
        stem = f"{capture} - {position}_XY1_Z0_T00"
        values = np.arange(18, dtype=np.uint16).reshape(2, 3, 3)
        tifffile.imwrite(self.root / f"{stem}_C0.tif", values)
        tifffile.imwrite(self.root / f"{stem}_C1.tif", values + 1)


if __name__ == "__main__":
    unittest.main()
