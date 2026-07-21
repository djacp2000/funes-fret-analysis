import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.experiment_assignment import ExperimentAssignmentRule
from funes.acquisition_analysis import run_reviewed_acquisition_analysis
from funes.experiment_roi_review import ExperimentRoiReviewOrchestrator
from funes.experiment_roi_review_persistence import (
    export_experiment_roi_review_snapshot,
)
from funes.reviewed_analysis_persistence import load_reviewed_analysis_package
from funes.roi_revision import finalize_roi_revision
from funes.roi_revision_persistence import export_roi_revision_artifact
from funes.roi_revision_replay import replay_roi_revision
from funes.reviewed_application import (
    APPLICATION_ANALYSIS_PACKAGE_NAME,
    APPLICATION_WORKBOOK_DIRECTORY,
    ReviewedApplicationRunError,
    run_reviewed_application,
)

from tests import test_acquisition_analysis as acquisition_test_support
from tests.test_position_analysis import _revision_for


class ReviewedApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.upstream = acquisition_test_support.AcquisitionAnalysisTests()
        self.upstream.setUp()
        self.addCleanup(self.upstream.tearDown)
        self.setup = self.upstream._setup_two_experiments()
        self.reviewed = self.upstream._inspect_all(
            self.setup.review_orchestrator
        )
        self.configs = self.upstream._configs(self.setup)
        self.rules = (
            ExperimentAssignmentRule("Experiment B", ("Capture 1",)),
            ExperimentAssignmentRule("Experiment A", ("Capture 2",)),
        )
        self.artifact_root = Path(
            tempfile.mkdtemp(prefix="funes_module22_")
        )
        self.addCleanup(shutil.rmtree, self.artifact_root)
        self.snapshot = self.artifact_root / "review.json"
        export_experiment_roi_review_snapshot(self.reviewed, self.snapshot)
        self.output = self.artifact_root / "application_run"

    def test_runs_complete_reviewed_application_and_publishes_exact_evidence(self) -> None:
        snapshot_bytes = self.snapshot.read_bytes()

        result = run_reviewed_application(
            self.upstream.root,
            self.rules,
            self.snapshot,
            self.configs,
            self.output,
        )

        self.assertEqual(result.output_directory, self.output.resolve())
        self.assertEqual(
            result.review_snapshot_sha256,
            hashlib.sha256(snapshot_bytes).hexdigest(),
        )
        self.assertEqual(self.snapshot.read_bytes(), snapshot_bytes)
        self.assertIs(result.review_setup.acquisition, result.acquisition)
        self.assertIs(result.analysis.review_setup, result.review_setup)
        self.assertIs(
            result.analysis.review_orchestrator, result.review_orchestrator
        )
        self.assertEqual(
            tuple(item.experiment for item in result.analysis.experiment_results),
            ("Experiment B", "Experiment A"),
        )
        self.assertEqual(
            tuple(path.name for path in result.workbook_paths),
            ("experiment_b.xlsx", "experiment_a.xlsx"),
        )
        self.assertTrue(all(path.is_file() for path in result.workbook_paths))
        self.assertTrue(
            all(
                path.parent
                == self.output.resolve() / APPLICATION_WORKBOOK_DIRECTORY
                for path in result.workbook_paths
            )
        )
        package_path = self.output.resolve() / APPLICATION_ANALYSIS_PACKAGE_NAME
        self.assertEqual(result.analysis_package.path, package_path)
        self.assertTrue(package_path.is_file())
        restored = load_reviewed_analysis_package(package_path)
        self.assertEqual(
            tuple(item.experiment for item in restored.analysis.experiment_results),
            ("Experiment B", "Experiment A"),
        )

    def test_never_records_an_inspection_or_grants_approval(self) -> None:
        forbidden = (
            "funes.segmentation_review.SegmentationReviewState.record_inspection",
            "funes.segmentation_review.SegmentationReviewState.approve_global",
            "funes.experiment_roi_review.ExperimentPositionReview.approve_remaining",
            "funes.experiment_roi_review_persistence.export_experiment_roi_review_snapshot",
        )
        patchers = [patch(target) for target in forbidden]
        spies = [patcher.start() for patcher in patchers]
        for patcher in patchers:
            self.addCleanup(patcher.stop)

        result = run_reviewed_application(
            self.upstream.root,
            self.rules,
            self.snapshot,
            self.configs,
            self.output,
        )

        self.assertTrue(result.analysis_package.path.is_file())
        self.assertTrue(
            all(
                review.review_state.global_approval is None
                for review in result.review_orchestrator.experiments
            )
        )
        for spy in spies:
            spy.assert_not_called()

    def test_propagates_optional_module24_revision_through_module22_and_v2_package(self) -> None:
        automatic = run_reviewed_acquisition_analysis(
            self.setup,
            self.reviewed,
            self.configs,
        )
        revised_key = self.setup.assigned_pairs[-1].position_key
        automatic_position = automatic.result_for_experiment(
            revised_key.experiment
        ).position_results[0]
        revision = finalize_roi_revision(
            _revision_for(automatic_position),
            finalized_at="2026-07-21T22:00:00-04:00",
        )

        with patch(
            "funes.roi_revision_persistence.load_roi_revision_artifact"
        ) as load_revision_spy, patch(
            "funes.roi_revision_persistence.export_roi_revision_artifact"
        ) as export_revision_spy:
            result = run_reviewed_application(
                self.upstream.root,
                self.rules,
                self.snapshot,
                self.configs,
                self.output,
                roi_revisions={revised_key: revision},
            )

        unchanged = result.analysis.experiment_results[0].position_results[0]
        revised = result.analysis.experiment_results[1].position_results[0]
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
                review.review_state.global_approval is None
                for review in result.review_orchestrator.experiments
            )
        )

        restored = load_reviewed_analysis_package(result.analysis_package.path)
        restored_unchanged = (
            restored.analysis.experiment_results[0].position_results[0]
        )
        restored_revised = (
            restored.analysis.experiment_results[1].position_results[0]
        )
        self.assertEqual(restored_unchanged.mask_source, "automatic")
        self.assertIsNone(restored_unchanged.roi_revision)
        self.assertEqual(restored_revised.mask_source, "manual_revision")
        self.assertEqual(restored_revised.revision_sha256, revision.sha256)
        self.assertIsNotNone(restored_revised.roi_revision)
        load_revision_spy.assert_not_called()
        export_revision_spy.assert_not_called()

    def test_invalid_module24_revision_fails_before_experiment_analysis(self) -> None:
        automatic = run_reviewed_acquisition_analysis(
            self.setup,
            self.reviewed,
            self.configs,
        )
        revised_key = self.setup.assigned_pairs[-1].position_key
        automatic_position = automatic.result_for_experiment(
            revised_key.experiment
        ).position_results[0]
        draft = _revision_for(automatic_position)

        with patch(
            "funes.acquisition_analysis.run_reviewed_experiment_analysis"
        ) as analysis_spy:
            with self.assertRaisesRegex(
                ReviewedApplicationRunError,
                "must be finalized",
            ):
                run_reviewed_application(
                    self.upstream.root,
                    self.rules,
                    self.snapshot,
                    self.configs,
                    self.output,
                    roi_revisions={revised_key: draft},
                )

        analysis_spy.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_resolves_verified_finalized_artifact_path_without_replacing_memory_route(self) -> None:
        automatic = run_reviewed_acquisition_analysis(
            self.setup,
            self.reviewed,
            self.configs,
        )
        artifact_key = self.setup.assigned_pairs[-1].position_key
        automatic_position = automatic.result_for_experiment(
            artifact_key.experiment
        ).position_results[0]
        artifact_revision = finalize_roi_revision(
            _revision_for(automatic_position),
            finalized_at="2026-07-21T22:30:00-04:00",
        )
        artifact_result = replay_roi_revision(
            artifact_revision,
            automatic_position.segmentation,
            automatic_position.roi_filtering,
            artifact_key,
        )
        artifact_path = self.artifact_root / "finalized-revision.json"
        written = export_roi_revision_artifact(artifact_result, artifact_path)

        result = run_reviewed_application(
            self.upstream.root,
            self.rules,
            self.snapshot,
            self.configs,
            self.output,
            roi_revision_artifact_paths={artifact_key: artifact_path},
        )

        self.assertEqual(len(result.resolved_roi_revision_artifacts), 1)
        resolved = result.resolved_roi_revision_artifacts[0]
        self.assertEqual(resolved.position_key, artifact_key)
        self.assertEqual(resolved.path, artifact_path.resolve())
        self.assertEqual(resolved.sha256, written.sha256)
        self.assertEqual(resolved.revision_sha256, artifact_revision.sha256)
        revised = result.analysis.experiment_results[1].position_results[0]
        self.assertEqual(revised.mask_source, "manual_revision")
        self.assertEqual(revised.revision_sha256, artifact_revision.sha256)
        restored = load_reviewed_analysis_package(result.analysis_package.path)
        self.assertEqual(
            restored.analysis.experiment_results[1].position_results[0].revision_sha256,
            artifact_revision.sha256,
        )

    def test_rejects_overlapping_in_memory_and_artifact_routes(self) -> None:
        automatic = run_reviewed_acquisition_analysis(
            self.setup,
            self.reviewed,
            self.configs,
        )
        key = self.setup.assigned_pairs[-1].position_key
        position = automatic.result_for_experiment(key.experiment).position_results[0]
        revision = finalize_roi_revision(
            _revision_for(position),
            finalized_at="2026-07-21T22:35:00-04:00",
        )
        artifact_path = self.artifact_root / "overlap.json"
        export_roi_revision_artifact(
            replay_roi_revision(revision, position.segmentation, position.roi_filtering, key),
            artifact_path,
        )

        with self.assertRaisesRegex(ReviewedApplicationRunError, "both in-memory"):
            run_reviewed_application(
                self.upstream.root,
                self.rules,
                self.snapshot,
                self.configs,
                self.output,
                roi_revisions={key: revision},
                roi_revision_artifact_paths={key: artifact_path},
            )
        self.assertFalse(self.output.exists())

    def test_unreviewed_snapshot_fails_before_any_experiment_analysis_or_output(self) -> None:
        export_experiment_roi_review_snapshot(
            self.setup.review_orchestrator,
            self.artifact_root / "unreviewed.json",
        )
        unreviewed = self.artifact_root / "unreviewed.json"

        with patch(
            "funes.acquisition_analysis.run_reviewed_experiment_analysis"
        ) as analysis_spy:
            with self.assertRaisesRegex(
                ReviewedApplicationRunError,
                "required D088 manual-review target",
            ):
                run_reviewed_application(
                    self.upstream.root,
                    self.rules,
                    unreviewed,
                    self.configs,
                    self.output,
                )

        analysis_spy.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_changed_experiment_order_fails_closed_before_analysis(self) -> None:
        reordered_path = self.artifact_root / "reordered.json"
        export_experiment_roi_review_snapshot(
            ExperimentRoiReviewOrchestrator(
                tuple(reversed(self.reviewed.experiments))
            ),
            reordered_path,
        )

        with patch(
            "funes.acquisition_analysis.run_reviewed_experiment_analysis"
        ) as analysis_spy:
            with self.assertRaisesRegex(
                ReviewedApplicationRunError, "unchanged order"
            ):
                run_reviewed_application(
                    self.upstream.root,
                    self.rules,
                    reordered_path,
                    self.configs,
                    self.output,
                )

        analysis_spy.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_existing_output_is_rejected_before_loading_or_mutation(self) -> None:
        self.output.mkdir()
        marker = self.output / "belongs_to_user.txt"
        marker.write_text("preserve", encoding="utf-8")
        snapshot_bytes = self.snapshot.read_bytes()

        with patch(
            "funes.reviewed_application.load_assigned_acquisition"
        ) as load_spy:
            with self.assertRaisesRegex(
                ReviewedApplicationRunError, "already exists"
            ):
                run_reviewed_application(
                    self.upstream.root,
                    self.rules,
                    self.snapshot,
                    self.configs,
                    self.output,
                )

        load_spy.assert_not_called()
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")
        self.assertEqual(self.snapshot.read_bytes(), snapshot_bytes)


if __name__ == "__main__":
    unittest.main()
