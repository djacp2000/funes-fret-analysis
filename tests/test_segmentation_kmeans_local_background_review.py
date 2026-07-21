import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import Channel
from funes.segmentation_benchmark_review import PreparedSegmentationBenchmarkField
from funes.segmentation_kmeans import (
    KMeansMorphologyConfig,
    KMeansMorphologySegmentationEngine,
)
from funes.segmentation_kmeans_causal_artifacts import KMeansCausalReviewRegion
from funes.segmentation_kmeans_local_background import (
    KMEANS_LOCAL_BACKGROUND_VARIANTS,
    run_kmeans_local_background_candidate,
)
from funes.segmentation_kmeans_local_background_review import (
    D071_DECLARED_DESTINATION,
    D071_FIELD_KEYS,
    D071_SELECTION_ID,
    D071_SYNTHETIC_AUTHORIZATION_SCOPE,
    D071ExecutionMode,
    D071RealReviewInput,
    D071RealReviewPackageError,
    D071RealReviewPlan,
    D071ReviewAuthorization,
    export_d071_kmeans_local_background_review,
)
from funes.segmentation_selection import CapturePositionKey


class D071RealReviewBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="funes_d071_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir)

    def test_direct_d069_runner_remains_synthetic_only(self) -> None:
        frame = self._frame(1)
        reference = self._control_labels(frame)

        result, _ = run_kmeans_local_background_candidate(frame, reference)

        self.assertTrue(result.engine.parameters["synthetic_verification_only"])
        self.assertEqual(
            result.engine.parameters["execution_scope"],
            "direct_d069_synthetic_verification",
        )
        self.assertNotIn("d071_authorization_id", result.engine.parameters)

    def test_synthetic_package_completes_exactly_two_calls_and_hashes_every_artifact(self) -> None:
        declared_destination = PROJECT_ROOT / D071_DECLARED_DESTINATION
        existed_before = declared_destination.exists()
        inputs = self._inputs()
        source_bytes = tuple(item.field.selected_source_path.read_bytes() for item in inputs)
        reference_bytes = tuple(item.reference_labels_path.read_bytes() for item in inputs)
        plan = self._plan(inputs, "synthetic-success")

        result = export_d071_kmeans_local_background_review(plan)

        self.assertEqual(result.engine_calls_started, 2)
        self.assertEqual(result.engine_calls_completed, 2)
        self.assertEqual(len(result.artifacts), 2)
        self.assertEqual(declared_destination.exists(), existed_before)
        selection = json.loads(result.selection_path.read_text(encoding="utf-8"))
        self.assertEqual(selection["selection_id"], D071_SELECTION_ID)
        self.assertEqual(selection["planned_engine_call_count"], 2)
        self.assertEqual(selection["engine_call_counter_initial"], 0)
        self.assertFalse(selection["automatic_retry_authorized"])
        self.assertFalse(selection["sample_sufficiency_assessed"])
        self.assertFalse(selection["representativeness_assessed"])
        self.assertFalse(selection["profile_action_performed"])
        self.assertFalse(selection["d046_used"])
        self.assertEqual(
            selection["fixed_call_order"],
            ["Capture 1 + Position 1", "Capture 1 + Position 2"],
        )
        for artifact in result.artifacts:
            trace = json.loads((artifact.run_dir / "trace.json").read_text(encoding="utf-8"))
            self.assertTrue(trace["engine"]["parameters"]["synthetic_verification_only"])
            self.assertEqual(
                trace["engine"]["parameters"]["execution_scope"],
                "d071_package_boundary_synthetic_verification",
            )
            self.assertEqual(
                trace["engine"]["parameters"]["d071_authorization_id"],
                "synthetic-success",
            )
            for name in trace["trace_array_files"]:
                self.assertTrue((artifact.run_dir / name).is_file())
            self.assertTrue(artifact.full_preview_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertIn("UNCLASSIFIED CAUSAL REVIEW", artifact.focus_sheet_path.read_text(encoding="utf-8"))

        observations = result.observations_path.read_text(encoding="utf-8")
        self.assertIn("wholly_omitted_cell_recovery", observations)
        self.assertIn("d051_bridge_or_joint_roi_interpretation", observations)
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["engine_calls_started"], 2)
        self.assertEqual(manifest["engine_calls_completed"], 2)
        self.assertFalse(manifest["automatic_retry_performed"])
        listed = {item["path"] for item in manifest["artifacts"]}
        actual = {
            path.relative_to(result.output_dir).as_posix()
            for path in result.output_dir.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        }
        self.assertEqual(listed, actual)
        for item in manifest["artifacts"]:
            path = result.output_dir / item["path"]
            self.assertEqual(item["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(
            tuple(item.field.selected_source_path.read_bytes() for item in inputs),
            source_bytes,
        )
        self.assertEqual(
            tuple(item.reference_labels_path.read_bytes() for item in inputs),
            reference_bytes,
        )

    def test_contract_rejects_extra_order_variant_and_alternate_destination(self) -> None:
        first, second = self._inputs()
        authorization = self._authorization("synthetic-contract")
        with self.assertRaisesRegex(ValueError, "Position 1 then Position 2"):
            D071RealReviewPlan(authorization, (second, first))
        with self.assertRaisesRegex(ValueError, "no extra field"):
            D071RealReviewPlan(authorization, (first, second, first))
        with self.assertRaisesRegex(ValueError, "unchanged D069"):
            D071RealReviewPlan(
                authorization,
                (first, second),
                replace(KMEANS_LOCAL_BACKGROUND_VARIANTS[0], variant_id="copied_candidate"),
            )
        with self.assertRaisesRegex(ValueError, "alternate declared destination"):
            replace(authorization, declared_destination=Path("outputs/alternate"))
        with self.assertRaisesRegex(ValueError, "exact reviewed authorization scope"):
            D071ReviewAuthorization(
                authorization_id="invalid-real-scope",
                authorization_scope=D071_SYNTHETIC_AUTHORIZATION_SCOPE,
                execution_mode=D071ExecutionMode.AUTHORIZED_REAL_REVIEW,
                workspace_root=PROJECT_ROOT,
                publication_destination=PROJECT_ROOT / D071_DECLARED_DESTINATION,
            )

        plan = D071RealReviewPlan(authorization, (first, second))
        with self.assertRaisesRegex(D071RealReviewPackageError, "alternate execution"):
            export_d071_kmeans_local_background_review(
                plan, self.tmpdir / "alternate-publication"
            )

    def test_all_hashes_and_nonempty_destination_fail_before_first_call(self) -> None:
        cases = ("source", "prepared", "reference", "destination")
        for case in cases:
            with self.subTest(case=case):
                case_root = self.tmpdir / case
                case_root.mkdir()
                inputs = list(self._inputs(case_root))
                authorization = self._authorization(
                    f"synthetic-{case}", case_root / "package"
                )
                if case == "source":
                    inputs[1].field.selected_source_path.write_bytes(b"changed source")
                elif case == "prepared":
                    inputs[1] = replace(
                        inputs[1], expected_prepared_frame_sha256="0" * 64
                    )
                elif case == "reference":
                    inputs[1].reference_labels_path.write_bytes(b"changed reference")
                else:
                    authorization.publication_destination.mkdir()
                    (authorization.publication_destination / "existing.txt").write_text(
                        "occupied", encoding="utf-8"
                    )
                plan = D071RealReviewPlan(authorization, tuple(inputs))
                with patch(
                    "funes.segmentation_kmeans_local_background_review._run_kmeans_local_background_candidate_for_d071"
                ) as runner:
                    with self.assertRaises(D071RealReviewPackageError) as caught:
                        export_d071_kmeans_local_background_review(plan)
                runner.assert_not_called()
                self.assertEqual(caught.exception.engine_calls_started, 0)
                self.assertEqual(caught.exception.engine_calls_completed, 0)

    def test_failed_second_call_is_isolated_unpublished_and_never_retried(self) -> None:
        inputs = self._inputs()
        plan = self._plan(inputs, "synthetic-no-retry")
        from funes import segmentation_kmeans_local_background_review as review_module

        original = review_module._run_kmeans_local_background_candidate_for_d071
        call_count = 0

        def fail_second(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("synthetic second-call failure")
            return original(*args, **kwargs)

        with patch.object(
            review_module,
            "_run_kmeans_local_background_candidate_for_d071",
            side_effect=fail_second,
        ):
            with self.assertRaises(D071RealReviewPackageError) as caught:
                export_d071_kmeans_local_background_review(plan)

        error = caught.exception
        self.assertEqual(call_count, 2)
        self.assertEqual(error.engine_calls_started, 2)
        self.assertEqual(error.engine_calls_completed, 1)
        self.assertFalse(plan.authorization.publication_destination.exists())
        self.assertIsNotNone(error.incomplete_attempt_dir)
        record = json.loads(
            (error.incomplete_attempt_dir / "incomplete_attempt.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(record["automatic_retry_performed"])
        self.assertEqual(record["engine_calls_started"], 2)
        self.assertEqual(record["engine_calls_completed"], 1)
        with self.assertRaisesRegex(D071RealReviewPackageError, "prior D071 attempt") as retry:
            export_d071_kmeans_local_background_review(plan)
        self.assertEqual(retry.exception.engine_calls_started, 0)

    def _plan(
        self,
        inputs: tuple[D071RealReviewInput, ...],
        authorization_id: str,
    ) -> D071RealReviewPlan:
        return D071RealReviewPlan(
            self._authorization(authorization_id),
            inputs,
        )

    def _authorization(
        self,
        authorization_id: str,
        publication_destination: Path | None = None,
    ) -> D071ReviewAuthorization:
        return D071ReviewAuthorization(
            authorization_id=authorization_id,
            authorization_scope=D071_SYNTHETIC_AUTHORIZATION_SCOPE,
            execution_mode=D071ExecutionMode.SYNTHETIC_CONTRACT_VERIFICATION,
            workspace_root=PROJECT_ROOT,
            publication_destination=publication_destination
            or self.tmpdir / f"package-{authorization_id}",
        )

    def _inputs(self, root: Path | None = None) -> tuple[D071RealReviewInput, ...]:
        fixture_root = self.tmpdir if root is None else root
        return (
            self._input(fixture_root, D071_FIELD_KEYS[0], 1, KMeansCausalReviewRegion("P1-R4", 5, 35, 5, 35)),
            self._input(fixture_root, D071_FIELD_KEYS[1], 2, KMeansCausalReviewRegion("P2-R1", 40, 75, 40, 75)),
        )

    def _input(
        self,
        root: Path,
        key: CapturePositionKey,
        seed: int,
        region: KMeansCausalReviewRegion,
    ) -> D071RealReviewInput:
        frame = self._frame(seed)
        source = root / f"synthetic_source_{seed}.tif"
        source.write_bytes(f"immutable synthetic source {seed}".encode("ascii"))
        reference = root / f"synthetic_reference_{seed}.npy"
        np.save(reference, self._control_labels(frame), allow_pickle=False)
        field = PreparedSegmentationBenchmarkField(
            field_key=key,
            prepared_frame=frame,
            selected_channel=Channel.C1,
            channel_selection_method="synthetic_test_selection",
            robust_contrast_by_channel={"C0": 1.0, "C1": 2.0},
            preprocessing_method="identity_segmentation_preprocessing",
            preprocessing_parameters={"preserves_pixel_values": True},
            selected_source_path=source,
            selected_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        return D071RealReviewInput(
            field=field,
            expected_prepared_frame_sha256=field.prepared_frame_sha256,
            reference_labels_path=reference,
            reference_labels_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
            review_region=region,
        )

    @staticmethod
    def _control_labels(frame: np.ndarray) -> np.ndarray:
        return KMeansMorphologySegmentationEngine(
            KMeansMorphologyConfig(minimum_object_area_pixels=32)
        ).segment(frame).label_image

    @staticmethod
    def _frame(seed: int) -> np.ndarray:
        rng = np.random.default_rng(seed)
        frame = rng.normal(0.0, 0.05, size=(80, 80))
        frame[:30, :30] -= 5.0
        frame[8:22, 8:22] += 12.0
        frame[45:62, 10:28] += 30.0
        frame[46:70, 46:70] += 60.0
        return frame


if __name__ == "__main__":
    unittest.main()
