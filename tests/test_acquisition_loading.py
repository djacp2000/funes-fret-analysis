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

from funes.acquisition_loading import AcquisitionLoadingError, load_assigned_acquisition
from funes.experiment_assignment import ExperimentAssignmentRule


class AcquisitionLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="funes_module18_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def test_composes_modules_1_to_4_and_preserves_associated_metadata(self) -> None:
        c0_name, c1_name = self._write_pair("Capture 1", "Position 2")
        (self.root / "capture.log").write_text(
            _slidebook_log_text(c0_name, c1_name), encoding="utf-8"
        )
        rule = ExperimentAssignmentRule(
            experiment="Experiment A", captures=("Capture 1",), source="test rule"
        )

        result = load_assigned_acquisition(self.root, (rule,))

        self.assertTrue(result.is_ready)
        self.assertEqual(result.issues, ())
        self.assertEqual(result.root, self.root.resolve())
        self.assertEqual(len(result.tiff_discovery.files), 2)
        self.assertEqual(len(result.auxiliary_discovery.files), 1)
        self.assertEqual(len(result.auxiliary_association.associations), 1)
        self.assertEqual(len(result.tiff_validation.pairs), 1)
        assigned = result.assigned_pairs[0]
        self.assertEqual(assigned.position_key.experiment, "Experiment A")
        self.assertIs(assigned.c0, result.tiff_validation.pairs[0].c0)
        self.assertIs(assigned.c1, result.tiff_validation.pairs[0].c1)
        self.assertEqual(
            assigned.auxiliary_metadata_associations,
            result.auxiliary_association.associations,
        )

    def test_preserves_stage_issue_identity_and_refuses_partial_scope(self) -> None:
        self._write_pair("Capture 1", "Position 1")
        tifffile.imwrite(
            self.root / "unrecognized.tif", np.zeros((2, 3, 3), dtype=np.uint16)
        )
        rule = ExperimentAssignmentRule(
            experiment="Experiment A", captures=("Capture 1",)
        )

        result = load_assigned_acquisition(self.root, (rule,))

        self.assertFalse(result.is_ready)
        self.assertEqual(len(result.experiment_assignment.pairs), 1)
        self.assertIs(result.issues[0], result.tiff_discovery.issues[0])
        with self.assertRaises(AcquisitionLoadingError) as raised:
            _ = result.assigned_pairs
        self.assertIs(raised.exception.result, result)
        self.assertIn("malformed_tiff_filename", str(raised.exception))

    def test_missing_assignment_is_auditable_and_returns_no_safe_pairs(self) -> None:
        self._write_pair("Capture 2", "Position 1")
        rule = ExperimentAssignmentRule(
            experiment="Experiment A", captures=("Capture 1",)
        )

        result = load_assigned_acquisition(self.root, (rule,))

        self.assertFalse(result.is_ready)
        self.assertEqual(result.experiment_assignment.pairs, ())
        self.assertEqual(
            tuple(issue.code for issue in result.issues),
            ("missing_experiment_assignment", "no_assigned_tiff_pairs"),
        )
        with self.assertRaisesRegex(
            AcquisitionLoadingError, "missing_experiment_assignment"
        ):
            _ = result.assigned_pairs

    def test_calls_only_modules_1_to_4_once(self) -> None:
        self._write_pair("Capture 1", "Position 1")
        rule = ExperimentAssignmentRule(
            experiment="Experiment A", captures=("Capture 1",)
        )
        stage_targets = (
            "discover_tiff_files",
            "discover_auxiliary_metadata_files",
            "associate_auxiliary_metadata_files",
            "validate_tiff_pairs",
            "assign_experiments",
        )
        forbidden_targets = (
            "funes.segmentation_registry.segment_configured_first_frame",
            "funes.position_analysis.run_reviewed_position_analysis",
            "funes.experiment_analysis.run_reviewed_experiment_analysis",
            "funes.reviewed_experiment_export.export_reviewed_experiment_workbook",
            "funes.experiment_roi_review_persistence.export_experiment_roi_review_snapshot",
        )
        module = sys.modules["funes.acquisition_loading"]
        stage_patchers = [
            patch(f"funes.acquisition_loading.{name}", wraps=getattr(module, name))
            for name in stage_targets
        ]
        forbidden_patchers = [patch(target) for target in forbidden_targets]
        stage_spies = [item.start() for item in stage_patchers]
        forbidden_spies = [item.start() for item in forbidden_patchers]
        for item in (*stage_patchers, *forbidden_patchers):
            self.addCleanup(item.stop)

        result = load_assigned_acquisition(self.root, (rule,))

        self.assertTrue(result.is_ready)
        for name, spy in zip(stage_targets, stage_spies):
            with self.subTest(stage=name):
                spy.assert_called_once()
        for target, spy in zip(forbidden_targets, forbidden_spies):
            with self.subTest(forbidden=target):
                spy.assert_not_called()

    def test_rejects_invalid_root_before_discovery(self) -> None:
        missing = self.root / "missing"
        file_root = self.root / "not-a-directory.txt"
        file_root.write_text("metadata", encoding="utf-8")

        with patch("funes.acquisition_loading.discover_tiff_files") as discover:
            with self.assertRaisesRegex(AcquisitionLoadingError, "does not exist"):
                load_assigned_acquisition(missing, ())
            with self.assertRaisesRegex(AcquisitionLoadingError, "directory"):
                load_assigned_acquisition(file_root, ())
        discover.assert_not_called()

    def _write_pair(self, capture: str, position: str) -> tuple[str, str]:
        stem = f"{capture} - {position}_XY1_Z0_T00"
        c0_name = f"{stem}_C0.tif"
        c1_name = f"{stem}_C1.tif"
        tifffile.imwrite(
            self.root / c0_name, np.arange(18, dtype=np.uint16).reshape(2, 3, 3)
        )
        tifffile.imwrite(
            self.root / c1_name,
            np.arange(18, dtype=np.uint16).reshape(2, 3, 3) + 1,
        )
        return c0_name, c1_name


def _slidebook_log_text(c0_name: str, c1_name: str) -> str:
    return (
        "Export Date-Time: 07/21/2026 12:00:00\n"
        "Capture Date-Time: 07/21/2026 11:59:00\n"
        "Z Planes: 1\nTime Points: 2\nChannels: 2\n"
        "Microns Per Pixel: 1\nZ Step Size Microns: 0\n"
        "Average Timelapse Interval: Unknown\n"
        "IFD\tX Position (um)\tY Position (um)\tZ Position (um)\t"
        "Elapsed Time (ms)\tChannel Name\tTIFF File Name\n"
        f"0\t1\t2\t3\t0\tC0\t{c0_name}\n"
        f"1\t1\t2\t3\t0\tC1\t{c1_name}\n"
    )


if __name__ == "__main__":
    unittest.main()
