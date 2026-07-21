import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import tifffile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import Channel
from funes.fret_calculation import FretCalculationConfig, FretChannelMapping
from funes.intensity_qc import CameraSaturationProfile, FractionThresholds, IntensityQcConfig
from funes.real_data_validation import (
    RealPairValidationConfig,
    RealPairValidationError,
    run_real_pair_validation,
)
from funes.roi_geometry import BorderTouchPolicy, RoiGeometryFilterConfig
from funes.segmentation_engine import (
    PercentileThresholdSegmentationConfig,
    PercentileThresholdSegmentationEngine,
)


class RealDataValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="funes_real_validation_"))
        self.raw_dir = self.tmpdir / "raw"
        self.output_dir = self.tmpdir / "output"
        self.raw_dir.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir)

    def test_runs_one_pair_to_module14_without_modifying_raw_tiffs(self) -> None:
        c0_path, c1_path = self._write_pair()
        original_bytes = {path: path.read_bytes() for path in (c0_path, c1_path)}

        result = run_real_pair_validation(
            self.raw_dir,
            self.output_dir,
            self._config(),
        )

        self.assertEqual(result.selected_channel.selected_channel, Channel.C1)
        self.assertEqual(result.segmentation.roi_count, 1)
        self.assertEqual(result.roi_filtering.accepted_count, 1)
        self.assertIs(result.roi_filtering.source_segmentation, result.segmentation)
        self.assertIs(
            result.roi_filtering.source_label_image,
            result.segmentation.label_image,
        )
        self.assertEqual(len(result.position_export.temporal_intensity.records), 4)
        self.assertEqual(len(result.position_export.fret.records), 2)
        self.assertEqual(result.position_export.fret.parameters["ratio_formula"], "C0/C1")
        self.assertEqual(
            result.position_export.fret.parameters["measurement_metric"],
            "background_corrected_mean",
        )
        self.assertTrue(
            all(
                record.ratio is not None and record.ratio < 1.0
                for record in result.position_export.fret.records
            )
        )
        self.assertEqual(len(result.export.workbook_paths), 1)
        workbook = result.export.workbook_paths[0]
        self.assertTrue(workbook.exists())
        with ZipFile(workbook) as archive:
            workbook_text = "\n".join(
                archive.read(name).decode("utf-8")
                for name in archive.namelist()
                if name.endswith(".xml")
            )
        self.assertIn("real_data_validation_profile_not_production", workbook_text)
        self.assertIn("frame_index", workbook_text)
        self.assertIn("C0/C1", workbook_text)
        self.assertIn("superseded", workbook_text)
        self.assertNotIn(">time_s<", workbook_text)
        self.assertIn(c0_path.name, workbook_text)
        self.assertIn(c1_path.name, workbook_text)
        for path, before in original_bytes.items():
            self.assertEqual(path.read_bytes(), before)

    def test_reports_requested_pair_when_no_files_match(self) -> None:
        self._write_pair()
        config = RealPairValidationConfig(
            experiment_label="Validation",
            capture="Capture 9",
            position="Position 9",
        )

        with self.assertRaisesRegex(
            RealPairValidationError,
            r"Capture 9 \+ Position 9",
        ):
            run_real_pair_validation(self.raw_dir, self.output_dir, config)

        self.assertFalse(self.output_dir.exists())

    def test_can_prepare_upstream_records_without_rewriting_workbook(self) -> None:
        self._write_pair()

        result = run_real_pair_validation(
            self.raw_dir,
            self.output_dir,
            self._config(),
            export_workbook=False,
        )

        self.assertEqual(result.export.workbook_paths, ())
        self.assertFalse(self.output_dir.exists())

    def _write_pair(self) -> tuple[Path, Path]:
        c0 = np.full((2, 8, 8), 10, dtype=np.uint16)
        c1 = np.full((2, 8, 8), 20, dtype=np.uint16)
        c0[:, 2:6, 2:6] = np.array([30, 35], dtype=np.uint16)[:, None, None]
        c1[:, 2:6, 2:6] = np.array([100, 120], dtype=np.uint16)[:, None, None]
        stem = "Capture 1 - Position 1_XY1_Z0_T0"
        c0_path = self.raw_dir / f"{stem}_C0.tif"
        c1_path = self.raw_dir / f"{stem}_C1.tif"
        tifffile.imwrite(c0_path, c0)
        tifffile.imwrite(c1_path, c1)
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
                max_area_pixels=64,
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
