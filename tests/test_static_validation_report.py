import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import tifffile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import Channel
from funes.fret_calculation import FretCalculationConfig, FretChannelMapping
from funes.intensity_qc import CameraSaturationProfile, FractionThresholds, IntensityQcConfig
from funes.real_data_validation import RealPairValidationConfig, run_real_pair_validation
from funes.roi_geometry import BorderTouchPolicy, RoiGeometryFilterConfig
from funes.segmentation_engine import (
    PercentileThresholdSegmentationConfig,
    PercentileThresholdSegmentationEngine,
)
from funes.static_validation_report import export_static_visual_validation_report


class StaticValidationReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="funes_static_report_"))
        self.raw_dir = self.tmpdir / "raw"
        self.output_dir = self.tmpdir / "output"
        self.raw_dir.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir)

    def test_exports_static_audit_artifacts_without_modifying_sources(self) -> None:
        c0_path, c1_path = self._write_pair_and_log()
        before = {path: path.read_bytes() for path in self.raw_dir.iterdir()}
        validation = run_real_pair_validation(
            self.raw_dir,
            self.output_dir,
            self._config(),
            export_workbook=False,
        )

        result = export_static_visual_validation_report(validation, self.output_dir)

        self.assertTrue(result.report_path.exists())
        self.assertTrue(result.manifest_path.exists())
        self.assertTrue(result.roi_audit_path.exists())
        self.assertTrue(result.roi_measurements_path.exists())
        report = result.report_path.read_text(encoding="utf-8")
        self.assertIn("Nunca segmentadas", report)
        self.assertIn("Segmentadas y rechazadas geométricamente", report)
        self.assertIn("Excluidas por intensidad o saturación", report)
        self.assertIn("pendiente de confirmación", report)
        self.assertIn("No es un análisis de producción", report)
        self.assertIn("Qué entra y qué sale de cada módulo", report)
        self.assertIn("fórmula está fijada por D042 como <strong>C0/C1</strong>", report)
        self.assertIn("Resultados anteriores superseded", report)
        self.assertNotIn("Por qué aparece el rango 2.77–10.86", report)
        self.assertEqual(result.intensity_excluded_rois, 0)

        measurements_header = result.roi_measurements_path.read_text(
            encoding="utf-8"
        ).splitlines()[0]
        self.assertIn("c0_raw_mean", measurements_header)
        self.assertIn("c0_background_corrected_mean", measurements_header)
        self.assertIn("c1_raw_mean", measurements_header)
        self.assertIn("c1_background_corrected_mean", measurements_header)
        self.assertIn("ratio_formula", measurements_header)

        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        self.assertFalse(manifest["production_ready"])
        self.assertEqual(manifest["ratio_formula"], "C0/C1")
        self.assertEqual(manifest["supersedes"]["formula"], "C1/C0")
        source_hashes = {row["name"]: row["sha256"] for row in manifest["source_files"]}
        self.assertEqual(source_hashes[c0_path.name], hashlib.sha256(before[c0_path]).hexdigest())
        self.assertEqual(source_hashes[c1_path.name], hashlib.sha256(before[c1_path]).hexdigest())
        for path, original in before.items():
            self.assertEqual(path.read_bytes(), original)

    def _write_pair_and_log(self) -> tuple[Path, Path]:
        c0 = np.full((2, 10, 10), 10, dtype=np.uint16)
        c1 = np.full((2, 10, 10), 20, dtype=np.uint16)
        c0[:, 3:7, 3:7] = np.array([35, 40], dtype=np.uint16)[:, None, None]
        c1[:, 3:7, 3:7] = np.array([100, 120], dtype=np.uint16)[:, None, None]
        stem = "Capture 1 - Position 1_XY1_Z0_T0"
        c0_path = self.raw_dir / f"{stem}_C0.tif"
        c1_path = self.raw_dir / f"{stem}_C1.tif"
        tifffile.imwrite(c0_path, c0)
        tifffile.imwrite(c1_path, c1)
        log = self.raw_dir / f"{stem}_C0.log"
        log.write_text(
            "Channels: 2\n"
            "IFD\tChannel Name\tTIFF File Name\n"
            f"0\ti_FRET_By_(CFPex/CFPem[F])\t{c0_path.name}\n"
            f"0\ti_FRET_bY_(CFPex/YFPem[F])\t{c1_path.name}\n",
            encoding="utf-8",
        )
        return c0_path, c1_path

    def _config(self) -> RealPairValidationConfig:
        return RealPairValidationConfig(
            experiment_label="Validation",
            capture="Capture 1",
            position="Position 1",
            segmentation_engine=PercentileThresholdSegmentationEngine(
                PercentileThresholdSegmentationConfig(
                    threshold_percentile=70.0,
                    connectivity=8,
                )
            ),
            roi_geometry=RoiGeometryFilterConfig(
                min_area_pixels=4,
                max_area_pixels=100,
                border_policy=BorderTouchPolicy.EXCLUDE,
            ),
            intensity_qc=IntensityQcConfig(
                camera_profile=CameraSaturationProfile(
                    name="synthetic_validation",
                    saturation_threshold=255.0,
                ),
                roi_saturation=FractionThresholds(),
                field_saturation=FractionThresholds(),
            ),
            fret=FretCalculationConfig(
                channel_mapping=FretChannelMapping(Channel.C0, Channel.C1),
                baseline_frame_indices=(0,),
            ),
        )


if __name__ == "__main__":
    unittest.main()
