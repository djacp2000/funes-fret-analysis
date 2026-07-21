import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import tifffile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.acquisition_analysis import (
    AcquisitionAnalysisError,
    run_reviewed_acquisition_analysis,
)
from funes.acquisition_loading import load_assigned_acquisition
from funes.acquisition_review_setup import (
    AcquisitionReviewExperimentConfig,
    initialize_acquisition_review,
)
from funes.contracts import PositionKey
from funes.experiment_assignment import ExperimentAssignmentRule
from funes.experiment_roi_review import (
    ExperimentPositionReviewMode,
    ExperimentRoiReviewOrchestrator,
)
from funes.position_analysis import PositionAnalysisConfig
from funes.roi_revision import finalize_roi_revision
from funes.segmentation_review import SegmentationReviewState
from funes.segmentation_selection import (
    BENCHMARK_BASELINE_PROFILE,
    SegmentationConfiguration,
    SegmentationMethodId,
    SegmentationSelection,
)

from tests.test_position_analysis import _analysis_config, _revision_for


class AcquisitionAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="funes_module20_"))
        self.selection = SegmentationSelection(
            SegmentationMethodId.CONTROL_P99,
            BENCHMARK_BASELINE_PROFILE,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def test_runs_every_experiment_in_d096_order_with_exact_objects(self) -> None:
        setup = self._setup_two_experiments()
        reviewed = self._inspect_all(setup.review_orchestrator)
        configs = {
            pair.position_key: _analysis_config()
            for pair in reversed(setup.assigned_pairs)
        }

        result = run_reviewed_acquisition_analysis(setup, reviewed, configs)

        self.assertIs(result.review_setup, setup)
        self.assertIs(result.review_orchestrator, reviewed)
        self.assertEqual(
            tuple(item.experiment for item in result.experiment_results),
            ("Experiment B", "Experiment A"),
        )
        self.assertTrue(
            all(
                position_result.pair is source_pair
                for experiment_result, source_pair in zip(
                    result.experiment_results, setup.assigned_pairs
                )
                for position_result in experiment_result.position_results
            )
        )
        expected_issues = tuple(
            issue
            for experiment_result in result.experiment_results
            for issue in experiment_result.issues
        )
        self.assertEqual(result.issues, expected_issues)
        self.assertIs(
            result.result_for_experiment("Experiment A"),
            result.experiment_results[1],
        )

    def test_preflights_all_experiments_before_first_analysis_call(self) -> None:
        setup = self._setup_two_experiments()
        first_only = self._inspect_experiments(
            setup.review_orchestrator, ("Experiment B",)
        )
        configs = self._configs(setup)

        with patch(
            "funes.acquisition_analysis.run_reviewed_experiment_analysis"
        ) as analysis_spy:
            with self.assertRaisesRegex(
                AcquisitionAnalysisError, "required D088 manual-review target"
            ):
                run_reviewed_acquisition_analysis(setup, first_only, configs)

        analysis_spy.assert_not_called()

    def test_propagates_optional_finalized_revisions_across_acquisition(self) -> None:
        setup = self._setup_two_experiments()
        reviewed = self._inspect_all(setup.review_orchestrator)
        configs = self._configs(setup)
        automatic = run_reviewed_acquisition_analysis(setup, reviewed, configs)
        revised_key = setup.assigned_pairs[-1].position_key
        automatic_position = automatic.result_for_experiment(
            revised_key.experiment
        ).position_results[0]
        revision = finalize_roi_revision(
            _revision_for(automatic_position),
            finalized_at="2026-07-21T20:00:00-04:00",
        )

        result = run_reviewed_acquisition_analysis(
            setup,
            reviewed,
            configs,
            roi_revisions={revised_key: revision},
        )

        unchanged = result.experiment_results[0].position_results[0]
        revised = result.experiment_results[1].position_results[0]
        self.assertEqual(unchanged.mask_source, "automatic")
        self.assertIsNone(unchanged.roi_revision)
        self.assertEqual(revised.mask_source, "manual_revision")
        self.assertIsNotNone(revised.roi_revision)
        assert revised.roi_revision is not None
        self.assertIs(revised.roi_revision.revision, revision)
        self.assertEqual(revised.revision_sha256, revision.sha256)
        self.assertIs(
            revised.measurement_roi_filtering,
            revised.roi_revision.geometry_audit,
        )
        self.assertEqual(
            {record.roi_label for record in revised.temporal_intensity.records},
            {1, 2},
        )
        self.assertTrue(
            all(
                item.review_state.global_approval is None
                for item in reviewed.experiments
            )
        )

    def test_preflights_all_revisions_before_any_experiment_analysis(self) -> None:
        setup = self._setup_two_experiments()
        reviewed = self._inspect_all(setup.review_orchestrator)
        configs = self._configs(setup)
        automatic = run_reviewed_acquisition_analysis(setup, reviewed, configs)
        source_key = setup.assigned_pairs[-1].position_key
        automatic_position = automatic.result_for_experiment(
            source_key.experiment
        ).position_results[0]
        draft = _revision_for(automatic_position)
        finalized = finalize_roi_revision(
            draft,
            finalized_at="2026-07-21T20:05:00-04:00",
        )
        child = finalize_roi_revision(
            replace(draft, parent_revision_sha256="0" * 64),
            finalized_at="2026-07-21T20:10:00-04:00",
        )
        wrong_key = setup.assigned_pairs[0].position_key
        outside_key = PositionKey("Capture 99", "Position 1", "Experiment Z")
        cases = (
            ({source_key: draft}, "must be finalized"),
            ({outside_key: finalized}, "complete D096 acquisition scope"),
            ({wrong_key: finalized}, "source identity does not match"),
            ({source_key: child}, "must be a root revision"),
        )

        for revisions, message in cases:
            with self.subTest(message=message):
                with patch(
                    "funes.acquisition_analysis.run_reviewed_experiment_analysis"
                ) as analysis_spy:
                    with self.assertRaisesRegex(AcquisitionAnalysisError, message):
                        run_reviewed_acquisition_analysis(
                            setup,
                            reviewed,
                            configs,
                            roi_revisions=revisions,
                        )
                analysis_spy.assert_not_called()

    def test_rejects_changed_scope_and_d044_configuration_before_analysis(self) -> None:
        setup = self._setup_two_experiments()
        reviewed = self._inspect_all(setup.review_orchestrator)
        reordered = ExperimentRoiReviewOrchestrator(
            tuple(reversed(reviewed.experiments))
        )

        with patch(
            "funes.acquisition_analysis.run_reviewed_experiment_analysis"
        ) as analysis_spy:
            with self.assertRaisesRegex(AcquisitionAnalysisError, "unchanged order"):
                run_reviewed_acquisition_analysis(
                    setup, reordered, self._configs(setup)
                )

            changed_config = SegmentationConfiguration(
                global_selection=self.selection
            )
            changed_review = replace(
                reviewed.experiments[0],
                review_state=SegmentationReviewState(changed_config).record_inspection(
                    reviewed.experiments[0].positions[0]
                ),
            )
            changed = ExperimentRoiReviewOrchestrator(
                (changed_review, reviewed.experiments[1])
            )
            with self.assertRaisesRegex(AcquisitionAnalysisError, "exact D044"):
                run_reviewed_acquisition_analysis(
                    setup, changed, self._configs(setup)
                )

        analysis_spy.assert_not_called()

    def test_requires_exact_position_configs_and_acquisition_level_context(self) -> None:
        setup = self._setup_two_experiments()
        reviewed = self._inspect_all(setup.review_orchestrator)
        configs = self._configs(setup)
        missing_key = setup.assigned_pairs[-1].position_key

        with self.assertRaisesRegex(AcquisitionAnalysisError, "configs.*missing"):
            run_reviewed_acquisition_analysis(
                setup,
                reviewed,
                {key: value for key, value in configs.items() if key != missing_key},
            )
        with self.assertRaisesRegex(ValueError, "scoped identity"):
            run_reviewed_acquisition_analysis(
                setup, reviewed, configs, context={"experiment": "Experiment A"}
            )

    def test_calls_only_module16_without_review_export_or_persistence(self) -> None:
        setup = self._setup_two_experiments()
        reviewed = self._inspect_all(setup.review_orchestrator)
        configs = self._configs(setup)
        forbidden = (
            "funes.segmentation_review.SegmentationReviewState.approve_global",
            "funes.experiment_roi_review_persistence.export_experiment_roi_review_snapshot",
            "funes.reviewed_experiment_export.export_reviewed_experiment_workbook",
            "funes.acquisition_loading.load_assigned_acquisition",
        )
        patchers = [patch(target) for target in forbidden]
        spies = [patcher.start() for patcher in patchers]
        for patcher in patchers:
            self.addCleanup(patcher.stop)

        with patch(
            "funes.acquisition_analysis.run_reviewed_experiment_analysis",
            wraps=__import__(
                "funes.experiment_analysis", fromlist=["run_reviewed_experiment_analysis"]
            ).run_reviewed_experiment_analysis,
        ) as analysis_spy:
            result = run_reviewed_acquisition_analysis(setup, reviewed, configs)

        self.assertEqual(analysis_spy.call_count, 2)
        self.assertEqual(
            tuple(call.args[0] for call in analysis_spy.call_args_list),
            ("Experiment B", "Experiment A"),
        )
        self.assertEqual(len(result.experiment_results), 2)
        for spy in spies:
            spy.assert_not_called()

    def _setup_two_experiments(self):
        self._write_pair("Capture 1", "Position 1")
        self._write_pair("Capture 2", "Position 1")
        load = load_assigned_acquisition(
            self.root,
            (
                ExperimentAssignmentRule("Experiment B", ("Capture 1",)),
                ExperimentAssignmentRule("Experiment A", ("Capture 2",)),
            ),
        )
        configs = tuple(
            AcquisitionReviewExperimentConfig(
                experiment=name,
                mode=ExperimentPositionReviewMode.REVIEW_ALL,
                segmentation_configuration=SegmentationConfiguration(
                    global_selection=self.selection
                ),
            )
            for name in ("Experiment A", "Experiment B")
        )
        return initialize_acquisition_review(load, configs)

    def _inspect_all(
        self, orchestrator: ExperimentRoiReviewOrchestrator
    ) -> ExperimentRoiReviewOrchestrator:
        return self._inspect_experiments(
            orchestrator, tuple(item.experiment for item in orchestrator.experiments)
        )

    @staticmethod
    def _inspect_experiments(
        orchestrator: ExperimentRoiReviewOrchestrator,
        experiments: tuple[str, ...],
    ) -> ExperimentRoiReviewOrchestrator:
        updated = []
        for review in orchestrator.experiments:
            state = review.review_state
            if review.experiment in experiments:
                for key in review.positions:
                    state = state.record_inspection(key)
            updated.append(replace(review, review_state=state))
        return ExperimentRoiReviewOrchestrator(tuple(updated))

    @staticmethod
    def _configs(setup) -> dict[PositionKey, PositionAnalysisConfig]:
        return {pair.position_key: _analysis_config() for pair in setup.assigned_pairs}

    def _write_pair(self, capture: str, position: str) -> None:
        stem = f"{capture} - {position}_XY1_Z0_T00"
        c0 = np.full((2, 10, 10), 10, dtype=np.uint16)
        c1 = np.full((2, 10, 10), 20, dtype=np.uint16)
        c0[:, 4, 4] = (110, 130)
        c1[:, 4, 4] = (70, 80)
        tifffile.imwrite(self.root / f"{stem}_C0.tif", c0)
        tifffile.imwrite(self.root / f"{stem}_C1.tif", c1)


if __name__ == "__main__":
    unittest.main()
