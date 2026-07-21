import shutil
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import PositionKey
from funes.experiment_analysis import run_reviewed_experiment_analysis
from funes.experiment_roi_review import (
    ExperimentPositionReview,
    ExperimentPositionReviewMode,
    ExperimentRoiReviewOrchestrator,
)
from funes.module14_exporter import Module14ExportResult
from funes.reviewed_experiment_export import (
    ReviewedExperimentExportError,
    export_reviewed_experiment_workbook,
)
from funes.segmentation_review import SegmentationReviewState
from funes.segmentation_selection import (
    BENCHMARK_BASELINE_PROFILE,
    SegmentationConfiguration,
    SegmentationMethodId,
    SegmentationSelection,
)

from tests.test_position_analysis import _analysis_config, _pair


class ReviewedExperimentExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="funes_module17_"))
        self.a1 = PositionKey("Capture 1", "Position 1", "Experiment A")
        self.a2 = PositionKey("Capture 1", "Position 2", "Experiment A")
        selection = SegmentationSelection(
            SegmentationMethodId.CONTROL_P99,
            BENCHMARK_BASELINE_PROFILE,
        )
        configuration = SegmentationConfiguration(global_selection=selection)
        state = SegmentationReviewState(configuration)
        for key in (self.a1, self.a2):
            state = state.record_inspection(key)
        orchestrator = ExperimentRoiReviewOrchestrator(
            (
                ExperimentPositionReview(
                    experiment="Experiment A",
                    positions=(self.a1, self.a2),
                    mode=ExperimentPositionReviewMode.REVIEW_ALL,
                    review_state=state,
                ),
            )
        )
        self.analysis = run_reviewed_experiment_analysis(
            "Experiment A",
            (_pair(self.a2), _pair(self.a1)),
            orchestrator,
            {self.a2: _analysis_config(), self.a1: _analysis_config()},
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir)

    def test_exports_one_workbook_from_exact_ordered_module16_results(self) -> None:
        result = export_reviewed_experiment_workbook(self.analysis, self.tmpdir)

        self.assertIs(result.analysis, self.analysis)
        self.assertEqual(result.workbook_path, self.tmpdir / "experiment_a.xlsx")
        self.assertTrue(result.workbook_path.exists())
        self.assertEqual(
            tuple(item.position_key for item in result.position_exports),
            (self.a1, self.a2),
        )
        for analyzed, exported in zip(
            self.analysis.position_results, result.position_exports
        ):
            with self.subTest(position=analyzed.pair.position_key):
                self.assertIs(exported.pair, analyzed.pair)
                self.assertIs(exported.roi_filtering, analyzed.roi_filtering)
                self.assertIs(exported.background, analyzed.background)
                self.assertIs(exported.intensity_qc, analyzed.intensity_qc)
                self.assertIs(
                    exported.temporal_intensity, analyzed.temporal_intensity
                )
                self.assertIs(exported.fret, analyzed.fret)
                self.assertEqual(exported.issues, analyzed.issues)

    def test_calls_only_module14_and_does_not_rerun_or_mutate_upstream(self) -> None:
        upstream_calls = (
            "funes.position_analysis.run_reviewed_position_analysis",
            "funes.experiment_analysis.run_reviewed_experiment_analysis",
            "funes.segmentation_registry.segment_configured_first_frame",
            "funes.quantitative_background.estimate_quantitative_background",
            "funes.intensity_qc.evaluate_filtered_roi_intensity_qc",
            "funes.temporal_intensity.extract_filtered_roi_temporal_intensities",
            "funes.fret_calculation.calculate_fret",
            "funes.experiment_roi_review_persistence.export_experiment_roi_review_snapshot",
        )
        expected_path = self.tmpdir / "experiment_a.xlsx"

        with ExitStack() as stack:
            spies = [stack.enter_context(patch(target)) for target in upstream_calls]
            exporter = stack.enter_context(
                patch(
                    "funes.reviewed_experiment_export.export_module14_workbooks",
                    return_value=Module14ExportResult((expected_path,)),
                )
            )
            result = export_reviewed_experiment_workbook(self.analysis, self.tmpdir)

        for target, spy in zip(upstream_calls, spies):
            with self.subTest(target=target):
                spy.assert_not_called()
        exporter.assert_called_once()
        passed_positions, passed_output = exporter.call_args.args
        self.assertEqual(passed_output, self.tmpdir)
        self.assertEqual(passed_positions, result.position_exports)

    def test_rejects_non_module16_input_before_export(self) -> None:
        with patch(
            "funes.reviewed_experiment_export.export_module14_workbooks"
        ) as exporter:
            with self.assertRaisesRegex(TypeError, "ExperimentAnalysisResult"):
                export_reviewed_experiment_workbook(object(), self.tmpdir)
        exporter.assert_not_called()

    def test_wraps_module14_failure_with_experiment_context(self) -> None:
        with patch(
            "funes.reviewed_experiment_export.export_module14_workbooks",
            side_effect=OSError("synthetic write failure"),
        ):
            with self.assertRaisesRegex(
                ReviewedExperimentExportError,
                "Experiment A.*synthetic write failure",
            ):
                export_reviewed_experiment_workbook(self.analysis, self.tmpdir)


if __name__ == "__main__":
    unittest.main()
