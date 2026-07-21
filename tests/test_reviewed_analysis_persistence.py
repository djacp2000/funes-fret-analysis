import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.acquisition_analysis import run_reviewed_acquisition_analysis
from funes.contracts import PositionKey
from funes.roi_geometry import BorderTouchPolicy, RoiGeometryFilterConfig
from funes.roi_revision import finalize_roi_revision
from funes.reviewed_analysis_persistence import (
    REVIEWED_ANALYSIS_PACKAGE_SCHEMA,
    ReviewedAnalysisPackageError,
    export_reviewed_analysis_package,
    load_reviewed_analysis_package,
)

from tests import test_acquisition_analysis as acquisition_test_support
from tests.test_position_analysis import _revision_for


class ReviewedAnalysisPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.upstream = acquisition_test_support.AcquisitionAnalysisTests()
        self.upstream.setUp()
        self.addCleanup(self.upstream.tearDown)
        self.setup = self.upstream._setup_two_experiments()
        self.reviewed = self.upstream._inspect_all(self.setup.review_orchestrator)
        self.configs = self.upstream._configs(self.setup)
        self.analysis = run_reviewed_acquisition_analysis(
            self.setup, self.reviewed, self.configs
        )
        self.output_dir = Path(tempfile.mkdtemp(prefix="funes_module21_"))
        self.addCleanup(shutil.rmtree, self.output_dir)
        self.path = self.output_dir / "reviewed.funes-analysis.zip"

    def test_round_trip_preserves_order_types_provenance_and_shared_identity(self) -> None:
        written = export_reviewed_analysis_package(
            self.analysis, self.configs, self.path
        )
        restored = load_reviewed_analysis_package(self.path)

        self.assertEqual(written.path, self.path)
        self.assertEqual(written.experiment_count, 2)
        self.assertEqual(written.position_count, 2)
        self.assertGreater(written.array_count, 0)
        self.assertEqual(
            tuple(item.experiment for item in restored.analysis.experiment_results),
            ("Experiment B", "Experiment A"),
        )
        restored_keys = tuple(
            entry.position_key for entry in restored.position_configs
        )
        self.assertEqual(
            restored_keys,
            tuple(pair.position_key for pair in self.setup.assigned_pairs),
        )
        self.assertEqual(
            restored.analysis.review_setup.assigned_pairs[0]
            .c0.parsed_file.source.original_name,
            self.setup.assigned_pairs[0].c0.parsed_file.source.original_name,
        )
        self.assertEqual(
            restored.analysis.review_setup.assigned_pairs[0]
            .c0.parsed_file.source.path,
            self.setup.assigned_pairs[0].c0.parsed_file.source.path,
        )
        self.assertEqual(
            tuple(issue.code for issue in restored.analysis.issues),
            tuple(issue.code for issue in self.analysis.issues),
        )
        for experiment in restored.analysis.experiment_results:
            for position in experiment.position_results:
                with self.subTest(position=position.pair.position_key):
                    self.assertIs(
                        position.roi_filtering.source_segmentation,
                        position.segmentation,
                    )
                    self.assertEqual(position.fret.parameters["ratio_formula"], "C0/C1")
                    self.assertEqual(
                        restored.config_for(position.pair.position_key).roi_geometry,
                        position.roi_filtering.config,
                    )
        self.assertIs(
            restored.analysis.review_setup.assigned_pairs[0],
            restored.analysis.experiment_results[0].position_results[0].pair,
        )
        self.assertIs(
            restored.analysis.review_setup.experiment_configs[
                0
            ].segmentation_configuration,
            restored.analysis.review_orchestrator.experiments[
                0
            ].review_state.configuration,
        )
        self.assertIs(
            restored.analysis.review_orchestrator.experiments[
                0
            ].review_state.inspections[0],
            restored.analysis.experiment_results[0]
            .position_results[0]
            .review_decision.field_review.inspection,
        )

    def test_requires_exact_and_result_compatible_scientific_configs(self) -> None:
        missing = dict(self.configs)
        missing.pop(next(iter(missing)))
        with self.assertRaisesRegex(ReviewedAnalysisPackageError, "missing"):
            export_reviewed_analysis_package(self.analysis, missing, self.path)

        key = next(iter(self.configs))
        incompatible = dict(self.configs)
        incompatible[key] = replace(
            incompatible[key],
            roi_geometry=RoiGeometryFilterConfig(
                min_area_pixels=2,
                max_area_pixels=10,
                border_policy=BorderTouchPolicy.ACCEPT,
            ),
        )
        with self.assertRaisesRegex(ValueError, "ROI geometry"):
            export_reviewed_analysis_package(self.analysis, incompatible, self.path)

    def test_v2_round_trip_preserves_optional_module24_dual_provenance(self) -> None:
        revised_key = self.setup.assigned_pairs[-1].position_key
        automatic_position = self.analysis.result_for_experiment(
            revised_key.experiment
        ).position_results[0]
        revision = finalize_roi_revision(
            _revision_for(automatic_position),
            finalized_at="2026-07-21T21:00:00-04:00",
        )
        revised_analysis = run_reviewed_acquisition_analysis(
            self.setup,
            self.reviewed,
            self.configs,
            roi_revisions={revised_key: revision},
        )

        export_reviewed_analysis_package(revised_analysis, self.configs, self.path)
        with zipfile.ZipFile(self.path, "r") as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        restored = load_reviewed_analysis_package(self.path)

        self.assertEqual(manifest["schema"], REVIEWED_ANALYSIS_PACKAGE_SCHEMA)
        self.assertTrue(REVIEWED_ANALYSIS_PACKAGE_SCHEMA.endswith(".v2"))
        automatic = restored.analysis.experiment_results[0].position_results[0]
        revised = restored.analysis.experiment_results[1].position_results[0]
        self.assertEqual(automatic.mask_source, "automatic")
        self.assertIsNone(automatic.roi_revision)
        self.assertEqual(revised.mask_source, "manual_revision")
        self.assertIsNotNone(revised.roi_revision)
        assert revised.roi_revision is not None
        self.assertEqual(revised.revision_sha256, revision.sha256)
        self.assertEqual(revised.roi_revision.revision, revision)
        self.assertIs(
            revised.roi_revision.original_segmentation,
            revised.segmentation,
        )
        self.assertIs(
            revised.roi_revision.original_filtering,
            revised.roi_filtering,
        )
        self.assertIs(
            revised.measurement_roi_filtering,
            revised.roi_revision.geometry_audit,
        )
        self.assertTrue(
            np.array_equal(
                revised.roi_revision.measurement_label_image,
                revised.measurement_roi_filtering.filtered_label_image,
            )
        )
        self.assertEqual(
            {record.roi_label for record in revised.temporal_intensity.records},
            {1, 2},
        )
        self.assertTrue(
            all(
                experiment.review_state.global_approval is None
                for experiment in restored.analysis.review_orchestrator.experiments
            )
        )

    def test_v1_package_identifier_is_rejected_after_versioned_integration(self) -> None:
        export_reviewed_analysis_package(self.analysis, self.configs, self.path)
        legacy = self.output_dir / "legacy-v1.funes-analysis.zip"
        _rewrite_package(
            self.path,
            legacy,
            manifest_change=lambda value: value.update(
                schema="funes.module21.reviewed_analysis_package.v1"
            ),
        )

        with self.assertRaisesRegex(ReviewedAnalysisPackageError, "unsupported.*schema"):
            load_reviewed_analysis_package(legacy)

    def test_rejects_schema_payload_and_array_tampering(self) -> None:
        export_reviewed_analysis_package(self.analysis, self.configs, self.path)

        unsupported = self.output_dir / "unsupported.funes-analysis.zip"
        _rewrite_package(
            self.path,
            unsupported,
            manifest_change=lambda value: value.update(schema="future.schema"),
        )
        with self.assertRaisesRegex(ReviewedAnalysisPackageError, "unsupported.*schema"):
            load_reviewed_analysis_package(unsupported)

        changed_payload = self.output_dir / "payload.funes-analysis.zip"
        _rewrite_package(
            self.path,
            changed_payload,
            manifest_change=lambda value: value["payload"].update(
                {"$type": "funes.unknown.Contract"}
            ),
        )
        with self.assertRaisesRegex(ReviewedAnalysisPackageError, "payload SHA-256"):
            load_reviewed_analysis_package(changed_payload)

        changed_array = self.output_dir / "array.funes-analysis.zip"
        with zipfile.ZipFile(self.path, "r") as archive:
            array_name = next(name for name in archive.namelist() if name.endswith(".npy"))
        _rewrite_package(
            self.path,
            changed_array,
            member_change=(array_name, b"not-the-saved-array"),
        )
        with self.assertRaisesRegex(ReviewedAnalysisPackageError, "integrity check"):
            load_reviewed_analysis_package(changed_array)

    def test_load_revalidates_typed_contracts_after_valid_integrity_hash(self) -> None:
        export_reviewed_analysis_package(self.analysis, self.configs, self.path)
        invalid = self.output_dir / "invalid-type.funes-analysis.zip"

        def change(manifest):
            from funes.reviewed_analysis_persistence import _payload_sha256

            manifest["payload"]["$type"] = "funes.unknown.Contract"
            manifest["payload_sha256"] = _payload_sha256(
                manifest["payload"], manifest["members"]
            )

        _rewrite_package(self.path, invalid, manifest_change=change)
        with self.assertRaisesRegex(ReviewedAnalysisPackageError, "unsupported contract"):
            load_reviewed_analysis_package(invalid)

    def test_export_and_load_do_not_rerun_analysis_mutate_review_or_export_workbooks(self) -> None:
        forbidden = (
            "funes.acquisition_loading.load_assigned_acquisition",
            "funes.position_analysis.run_reviewed_position_analysis",
            "funes.experiment_analysis.run_reviewed_experiment_analysis",
            "funes.acquisition_analysis.run_reviewed_acquisition_analysis",
            "funes.segmentation_review.SegmentationReviewState.record_inspection",
            "funes.segmentation_review.SegmentationReviewState.approve_global",
            "funes.reviewed_experiment_export.export_reviewed_experiment_workbook",
            "funes.module14_exporter.export_module14_workbooks",
            "funes.roi_revision_persistence.export_roi_revision_artifact",
            "funes.roi_revision_persistence.load_roi_revision_artifact",
        )
        patchers = [patch(target) for target in forbidden]
        spies = [patcher.start() for patcher in patchers]
        for patcher in patchers:
            self.addCleanup(patcher.stop)

        export_reviewed_analysis_package(self.analysis, self.configs, self.path)
        restored = load_reviewed_analysis_package(self.path)

        self.assertEqual(len(restored.analysis.experiment_results), 2)
        for target, spy in zip(forbidden, spies):
            with self.subTest(forbidden=target):
                spy.assert_not_called()


def _rewrite_package(
    source: Path,
    destination: Path,
    *,
    manifest_change=None,
    member_change: tuple[str, bytes] | None = None,
) -> None:
    with zipfile.ZipFile(source, "r") as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(contents["manifest.json"].decode("utf-8"))
    if manifest_change is not None:
        manifest_change(manifest)
    contents["manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if member_change is not None:
        contents[member_change[0]] = member_change[1]
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in contents.items():
            archive.writestr(name, content)


if __name__ == "__main__":
    unittest.main()
