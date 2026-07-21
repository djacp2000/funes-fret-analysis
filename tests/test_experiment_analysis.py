import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import PositionKey
from funes.experiment_analysis import (
    ExperimentAnalysisError,
    run_reviewed_experiment_analysis,
)
from funes.experiment_roi_review import (
    ExperimentPositionReview,
    ExperimentPositionReviewMode,
    ExperimentRoiReviewOrchestrator,
)
from funes.position_analysis import run_reviewed_position_analysis
from funes.roi_revision import finalize_roi_revision
from funes.segmentation_review import SegmentationReviewState
from funes.segmentation_selection import (
    BENCHMARK_BASELINE_PROFILE,
    SegmentationConfiguration,
    SegmentationMethodId,
    SegmentationSelection,
)

from tests.test_position_analysis import _analysis_config, _pair, _revision_for


class ExperimentAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.a1 = PositionKey("Capture 1", "Position 1", "Experiment A")
        self.a2 = PositionKey("Capture 1", "Position 2", "Experiment A")
        self.b1 = PositionKey("Capture 1", "Position 1", "Experiment B")
        selection = SegmentationSelection(
            SegmentationMethodId.CONTROL_P99,
            BENCHMARK_BASELINE_PROFILE,
        )
        self.configuration = SegmentationConfiguration(global_selection=selection)

    def test_runs_complete_scope_in_declared_d089_order(self) -> None:
        orchestrator = self._orchestrator(inspected=(self.a1, self.a2))
        configs = {self.a2: _analysis_config(), self.a1: _analysis_config()}

        result = run_reviewed_experiment_analysis(
            "Experiment A",
            (_pair(self.a2), _pair(self.a1)),
            orchestrator,
            configs,
        )

        self.assertEqual(result.experiment, "Experiment A")
        self.assertEqual(
            tuple(item.pair.position_key for item in result.position_results),
            (self.a1, self.a2),
        )
        self.assertEqual(
            tuple(len(item.fret.records) for item in result.position_results),
            (2, 2),
        )
        expected_issues = tuple(
            issue for item in result.position_results for issue in item.issues
        )
        self.assertTrue(expected_issues)
        self.assertEqual(result.issues, expected_issues)

    def test_preflights_entire_review_scope_before_analysis(self) -> None:
        orchestrator = self._orchestrator(inspected=(self.a1,))
        configs = {
            self.a1: _analysis_config(preprocessor=_BombPreprocessor()),
            self.a2: _analysis_config(),
        }

        with self.assertRaisesRegex(
            ExperimentAnalysisError, "required D088 manual-review target"
        ):
            run_reviewed_experiment_analysis(
                "Experiment A",
                (_pair(self.a1), _pair(self.a2)),
                orchestrator,
                configs,
            )

    def test_propagates_optional_finalized_revisions_by_position(self) -> None:
        orchestrator = self._orchestrator(inspected=(self.a1, self.a2))
        automatic_a2 = run_reviewed_position_analysis(
            _pair(self.a2),
            orchestrator,
            _analysis_config(),
        )
        revision = finalize_roi_revision(
            _revision_for(automatic_a2),
            finalized_at="2026-07-21T19:00:00-04:00",
        )

        result = run_reviewed_experiment_analysis(
            "Experiment A",
            (_pair(self.a2), _pair(self.a1)),
            orchestrator,
            {self.a2: _analysis_config(), self.a1: _analysis_config()},
            roi_revisions={self.a2: revision},
        )

        automatic, revised = result.position_results
        self.assertEqual(
            tuple(item.pair.position_key for item in result.position_results),
            (self.a1, self.a2),
        )
        self.assertEqual(automatic.mask_source, "automatic")
        self.assertIsNone(automatic.roi_revision)
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
        self.assertIsNone(orchestrator.experiments[0].review_state.global_approval)

    def test_preflights_revision_mapping_before_any_position_analysis(self) -> None:
        orchestrator = self._orchestrator(inspected=(self.a1, self.a2))
        automatic_a2 = run_reviewed_position_analysis(
            _pair(self.a2),
            orchestrator,
            _analysis_config(),
        )
        draft = _revision_for(automatic_a2)
        finalized = finalize_roi_revision(
            draft,
            finalized_at="2026-07-21T19:05:00-04:00",
        )
        child = finalize_roi_revision(
            replace(draft, parent_revision_sha256="0" * 64),
            finalized_at="2026-07-21T19:10:00-04:00",
        )
        pairs = (_pair(self.a1), _pair(self.a2))
        configs = {
            self.a1: _analysis_config(preprocessor=_BombPreprocessor()),
            self.a2: _analysis_config(),
        }
        cases = (
            ({self.a2: draft}, "must be finalized"),
            ({self.b1: finalized}, "complete D089 experiment scope"),
            ({self.a1: finalized}, "source identity does not match"),
            ({self.a2: child}, "must be a root revision"),
        )

        for revisions, message in cases:
            with self.subTest(message=message):
                with patch(
                    "funes.experiment_analysis.run_reviewed_position_analysis"
                ) as position_spy:
                    with self.assertRaisesRegex(ExperimentAnalysisError, message):
                        run_reviewed_experiment_analysis(
                            "Experiment A",
                            pairs,
                            orchestrator,
                            configs,
                            roi_revisions=revisions,
                        )
                position_spy.assert_not_called()

    def test_requires_complete_pair_and_config_scopes(self) -> None:
        orchestrator = self._orchestrator(inspected=(self.a1, self.a2))
        configs = {self.a1: _analysis_config(), self.a2: _analysis_config()}

        with self.assertRaisesRegex(ExperimentAnalysisError, "pairs.*missing"):
            run_reviewed_experiment_analysis(
                "Experiment A", (_pair(self.a1),), orchestrator, configs
            )
        with self.assertRaisesRegex(ExperimentAnalysisError, "configs.*missing"):
            run_reviewed_experiment_analysis(
                "Experiment A",
                (_pair(self.a1), _pair(self.a2)),
                orchestrator,
                {self.a1: _analysis_config()},
            )

    def test_rejects_duplicate_and_cross_experiment_pairs(self) -> None:
        orchestrator = self._orchestrator(inspected=(self.a1, self.a2))
        configs = {self.a1: _analysis_config(), self.a2: _analysis_config()}

        with self.assertRaisesRegex(ExperimentAnalysisError, "duplicate"):
            run_reviewed_experiment_analysis(
                "Experiment A",
                (_pair(self.a1), _pair(self.a1)),
                orchestrator,
                configs,
            )
        with self.assertRaisesRegex(ExperimentAnalysisError, "isolated experiment"):
            run_reviewed_experiment_analysis(
                "Experiment A",
                (_pair(self.a1), _pair(self.b1)),
                orchestrator,
                configs,
            )

    def test_rejects_position_specific_or_conflicting_batch_context(self) -> None:
        orchestrator = self._orchestrator(inspected=(self.a1, self.a2))
        pairs = (_pair(self.a1), _pair(self.a2))
        configs = {self.a1: _analysis_config(), self.a2: _analysis_config()}

        with self.assertRaisesRegex(ValueError, "conflicts"):
            run_reviewed_experiment_analysis(
                "Experiment A",
                pairs,
                orchestrator,
                configs,
                context={"experiment": "Experiment B"},
            )
        with self.assertRaisesRegex(ValueError, "position-specific"):
            run_reviewed_experiment_analysis(
                "Experiment A",
                pairs,
                orchestrator,
                configs,
                context={"capture": "Capture 1"},
            )

    def _orchestrator(
        self, *, inspected: tuple[PositionKey, ...]
    ) -> ExperimentRoiReviewOrchestrator:
        state = SegmentationReviewState(self.configuration)
        for key in inspected:
            state = state.record_inspection(key)
        return ExperimentRoiReviewOrchestrator(
            (
                ExperimentPositionReview(
                    experiment="Experiment A",
                    positions=(self.a1, self.a2),
                    mode=ExperimentPositionReviewMode.REVIEW_ALL,
                    review_state=state,
                ),
            )
        )


class _BombPreprocessor:
    name = "bomb_preprocessor"

    def preprocess(self, frame, context=None):
        raise AssertionError("no position analysis may start before batch preflight")


if __name__ == "__main__":
    unittest.main()
