import hashlib
import json
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

from funes.experiment_assignment import ExperimentAssignmentRule
from funes.experiment_roi_review_persistence import (
    export_experiment_roi_review_snapshot,
)
from funes.real_data_activation import (
    ACTIVATION_COMPLETED_RECEIPT_NAME,
    ACTIVATION_FAILED_RECEIPT_NAME,
    ACTIVATION_STARTED_RECEIPT_NAME,
    RealDataActivationError,
    run_explicit_real_data_activation,
)
from funes.real_data_activation_contracts import (
    ACTIVATION_PURPOSE,
    ACTIVATION_SCIENTIFIC_STATUS,
    ActivationPositionScope,
    PositionConfigurationBundle,
    RealDataActivationAuthorization,
    RealDataActivationPlan,
    position_configuration_bundle_sha256,
    real_data_activation_plan_sha256,
    required_activation_statement,
)
from funes.reviewed_analysis_persistence import (
    PositionAnalysisConfigEntry,
    load_reviewed_analysis_package,
)

from tests import test_acquisition_analysis as acquisition_test_support


class RealDataActivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.upstream = acquisition_test_support.AcquisitionAnalysisTests()
        self.upstream.setUp()
        self.addCleanup(self.upstream.tearDown)
        self.setup = self.upstream._setup_two_experiments()
        self.reviewed = self.upstream._inspect_all(self.setup.review_orchestrator)
        self.configs = self.upstream._configs(self.setup)
        self.rules = (
            ExperimentAssignmentRule("Experiment B", ("Capture 1",)),
            ExperimentAssignmentRule("Experiment A", ("Capture 2",)),
        )
        self.artifact_root = Path(tempfile.mkdtemp(prefix="funes_module23_"))
        self.addCleanup(shutil.rmtree, self.artifact_root)
        self.snapshot = self.artifact_root / "review.json"
        export_experiment_roi_review_snapshot(self.reviewed, self.snapshot)
        self.output = self.artifact_root / "activation_output"
        self.audit = self.artifact_root / "activation_attempt_audit"
        self.plan = self._plan()
        self.authorization = self._authorization(self.plan)

    def test_publishes_one_verified_application_and_nonapproving_receipts(self) -> None:
        forbidden = (
            "funes.segmentation_review.SegmentationReviewState.record_inspection",
            "funes.segmentation_review.SegmentationReviewState.approve_global",
            "funes.experiment_roi_review.ExperimentPositionReview.approve_remaining",
            "funes.experiment_roi_review.ExperimentRoiReviewOrchestrator.approve_remaining",
            "funes.roi_review.apply_interactive_roi_review_decision",
        )
        patchers = [patch(target) for target in forbidden]
        spies = [item.start() for item in patchers]
        for item in patchers:
            self.addCleanup(item.stop)

        with patch(
            "funes.real_data_activation.run_reviewed_application",
            wraps=__import__(
                "funes.reviewed_application", fromlist=["run_reviewed_application"]
            ).run_reviewed_application,
        ) as d099_spy:
            result = run_explicit_real_data_activation(
                self.plan, self.authorization
            )

        d099_spy.assert_called_once()
        self.assertEqual(result.d099_call_count, 1)
        self.assertEqual(result.purpose, ACTIVATION_PURPOSE)
        self.assertEqual(result.scientific_status, ACTIVATION_SCIENTIFIC_STATUS)
        self.assertEqual(len(result.source_inventory), 4)
        self.assertTrue(result.output_directory.is_dir())
        self.assertTrue(result.started_receipt_path.is_file())
        self.assertTrue(result.completed_receipt_path.is_file())
        self.assertTrue(result.published_completed_receipt_path.is_file())
        self.assertFalse((self.audit / ACTIVATION_FAILED_RECEIPT_NAME).exists())
        self.assertTrue(result.application.analysis_package.path.is_file())
        restored = load_reviewed_analysis_package(
            result.application.analysis_package.path
        )
        self.assertEqual(
            tuple(
                position.pair.position_key
                for experiment in restored.analysis.experiment_results
                for position in experiment.position_results
            ),
            tuple(item.position_key for item in self.plan.positions),
        )
        receipt = json.loads(result.completed_receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "attempt_completed")
        self.assertEqual(receipt["d099_call_count"], 1)
        self.assertEqual(receipt["scientific_status"], "not_approved")
        self.assertFalse(receipt["inspection_performed"])
        self.assertFalse(receipt["approval_performed"])
        self.assertFalse(receipt["scientific_default_selected"])
        self.assertFalse(receipt["roi_or_mask_edited"])
        self.assertEqual(
            [item["status"] for item in receipt["review_records"]],
            ["manually_reviewed", "manually_reviewed"],
        )
        for spy in spies:
            spy.assert_not_called()

    def test_invalid_authority_performs_zero_acquisition_access_or_d099_calls(self) -> None:
        wrong_hash = "0" * 64
        authorization = RealDataActivationAuthorization(
            activation_id=self.plan.activation_id,
            plan_sha256=wrong_hash,
            statement=required_activation_statement(
                self.plan.activation_id, wrong_hash
            ),
        )
        with patch(
            "funes.real_data_activation._inventory_acquisition_sources"
        ) as inventory_spy, patch(
            "funes.real_data_activation.run_reviewed_application"
        ) as d099_spy:
            with self.assertRaisesRegex(
                RealDataActivationError, "exact activation plan ID and SHA-256"
            ):
                run_explicit_real_data_activation(self.plan, authorization)

        inventory_spy.assert_not_called()
        d099_spy.assert_not_called()
        self.assertFalse(self.audit.exists())
        self.assertFalse(self.output.exists())

    def test_exact_source_scope_mismatch_fails_after_reservation_before_d099(self) -> None:
        tifffile.imwrite(
            self.upstream.root
            / "Capture 3 - Position 1_XY1_Z0_T00_C0.tif",
            np.zeros((2, 3, 3), dtype=np.uint16),
        )
        with patch(
            "funes.real_data_activation.run_reviewed_application"
        ) as d099_spy:
            with self.assertRaisesRegex(
                RealDataActivationError, "source inventory mismatch"
            ) as raised:
                run_explicit_real_data_activation(self.plan, self.authorization)

        d099_spy.assert_not_called()
        self.assertEqual(raised.exception.d099_call_count, 0)
        self.assertTrue((self.audit / ACTIVATION_STARTED_RECEIPT_NAME).is_file())
        failed = json.loads(
            (self.audit / ACTIVATION_FAILED_RECEIPT_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual(failed["failure_stage"], "source_preflight")
        self.assertEqual(failed["d099_call_count"], 0)
        self.assertFalse(self.output.exists())

    def test_configuration_hash_is_bound_before_an_authorized_attempt(self) -> None:
        reversed_bundle = PositionConfigurationBundle(
            tuple(reversed(self.plan.position_configurations.entries))
        )
        with self.assertRaisesRegex(ValueError, "bundle SHA-256"):
            RealDataActivationPlan(
                activation_id="synthetic_config_mismatch",
                acquisition_root=self.upstream.root,
                positions=self.plan.positions,
                auxiliary_relative_paths=(),
                assignment_rules=self.rules,
                review_snapshot_path=self.snapshot,
                review_snapshot_sha256=self.plan.review_snapshot_sha256,
                position_configurations=reversed_bundle,
                position_configurations_sha256=self.plan.position_configurations_sha256,
                output_directory=self.artifact_root / "unused_output",
                attempt_audit_directory=self.artifact_root / "unused_audit",
            )
        self.assertFalse((self.artifact_root / "unused_audit").exists())

    def test_d099_failure_is_recorded_once_and_activation_id_cannot_be_reused(self) -> None:
        with patch(
            "funes.real_data_activation.run_reviewed_application",
            side_effect=RuntimeError("synthetic D099 failure"),
        ) as d099_spy:
            with self.assertRaisesRegex(
                RealDataActivationError, "synthetic D099 failure"
            ) as first:
                run_explicit_real_data_activation(self.plan, self.authorization)

        d099_spy.assert_called_once()
        self.assertEqual(first.exception.d099_call_count, 1)
        self.assertFalse(self.output.exists())
        failed_path = self.audit / ACTIVATION_FAILED_RECEIPT_NAME
        failed = json.loads(failed_path.read_text(encoding="utf-8"))
        self.assertEqual(failed["d099_call_count"], 1)
        self.assertFalse(failed["automatic_retry_performed"])

        with patch(
            "funes.real_data_activation._inventory_acquisition_sources"
        ) as inventory_spy, patch(
            "funes.real_data_activation.run_reviewed_application"
        ) as retry_spy:
            with self.assertRaisesRegex(
                RealDataActivationError, "already reserved"
            ):
                run_explicit_real_data_activation(self.plan, self.authorization)
        inventory_spy.assert_not_called()
        retry_spy.assert_not_called()

    def test_postflight_detects_changed_synthetic_source_and_publishes_nothing(self) -> None:
        real_runner = __import__(
            "funes.reviewed_application", fromlist=["run_reviewed_application"]
        ).run_reviewed_application
        changed_source = self.upstream.root / self.plan.positions[0].c0_relative_path

        def run_then_change(*args, **kwargs):
            result = real_runner(*args, **kwargs)
            changed_source.write_bytes(changed_source.read_bytes() + b"changed")
            return result

        with patch(
            "funes.real_data_activation.run_reviewed_application",
            side_effect=run_then_change,
        ) as d099_spy:
            with self.assertRaisesRegex(
                RealDataActivationError, "sources changed during D099"
            ) as raised:
                run_explicit_real_data_activation(self.plan, self.authorization)

        d099_spy.assert_called_once()
        self.assertEqual(raised.exception.d099_call_count, 1)
        self.assertFalse(self.output.exists())
        self.assertIsNotNone(raised.exception.quarantine_directory)
        self.assertTrue((self.audit / ACTIVATION_FAILED_RECEIPT_NAME).is_file())

    def _plan(self) -> RealDataActivationPlan:
        positions = tuple(
            ActivationPositionScope(
                pair.position_key,
                pair.c0.parsed_file.source.path.relative_to(self.upstream.root),
                pair.c1.parsed_file.source.path.relative_to(self.upstream.root),
            )
            for pair in self.setup.assigned_pairs
        )
        bundle = PositionConfigurationBundle(
            tuple(
                PositionAnalysisConfigEntry(
                    pair.position_key, self.configs[pair.position_key]
                )
                for pair in self.setup.assigned_pairs
            )
        )
        return RealDataActivationPlan(
            activation_id="synthetic_module23_contract_attempt",
            acquisition_root=self.upstream.root,
            positions=positions,
            auxiliary_relative_paths=(),
            assignment_rules=self.rules,
            review_snapshot_path=self.snapshot,
            review_snapshot_sha256=hashlib.sha256(self.snapshot.read_bytes()).hexdigest(),
            position_configurations=bundle,
            position_configurations_sha256=position_configuration_bundle_sha256(
                bundle
            ),
            output_directory=self.output,
            attempt_audit_directory=self.audit,
        )

    @staticmethod
    def _authorization(
        plan: RealDataActivationPlan,
    ) -> RealDataActivationAuthorization:
        plan_hash = real_data_activation_plan_sha256(plan)
        return RealDataActivationAuthorization(
            activation_id=plan.activation_id,
            plan_sha256=plan_hash,
            statement=required_activation_statement(plan.activation_id, plan_hash),
        )


if __name__ == "__main__":
    unittest.main()
