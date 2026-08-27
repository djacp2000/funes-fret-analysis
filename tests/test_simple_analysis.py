import json
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

from funes.simple_analysis import SimpleFretAnalysisConfig, run_simple_fret_analysis


class SimpleAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="funes_simple_"))
        self.input_dir = self.root / "input"
        self.input_dir.mkdir()
        self.output_dir = self.root / "output"

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def test_runs_current_default_scope_without_review_or_activation_and_preserves_sources(self) -> None:
        sources = []
        for position in (39, 45):
            sources.extend(self._write_pair(position))
        before = {path: path.read_bytes() for path in sources}

        result = run_simple_fret_analysis(self.input_dir, self.output_dir)

        self.assertEqual(len(result.positions), 2)
        self.assertEqual([item.roi_filtering.accepted_count for item in result.positions], [1, 1])
        self.assertEqual(len(result.export.workbook_paths), 1)
        self.assertTrue((self.output_dir / "roi_overlays").is_dir())
        self.assertTrue((self.output_dir / "position_reports").is_dir())
        self.assertEqual(len(result.report_paths), 2)
        summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["analysis_status"], "automatic_provisional_not_scientifically_validated")
        self.assertEqual([item["detected_rois"] for item in summary["positions"]], [1, 1])
        with ZipFile(result.export.workbook_paths[0]) as archive:
            workbook_text = "\n".join(
                archive.read(name).decode("utf-8")
                for name in archive.namelist()
                if name.endswith(".xml")
            )
        self.assertIn("simple_results", workbook_text)
        self.assertIn("C0_mean", workbook_text)
        self.assertIn("C1_mean", workbook_text)
        self.assertIn("ratio_C0_C1", workbook_text)
        self.assertIn("real_data_validation_profile_not_production", workbook_text)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

    def test_discovers_every_valid_pair_without_a_position_allowlist(self) -> None:
        self._write_pair(39)
        self._write_pair(45)
        self._write_pair(8, capture=2)

        result = run_simple_fret_analysis(self.input_dir, self.output_dir)

        self.assertEqual(len(result.positions), 3)
        observed = {
            (item.position_export.position_key.capture, item.position_export.position_key.position)
            for item in result.positions
        }
        self.assertEqual(
            observed,
            {
                ("Capture 5", "Position 39"),
                ("Capture 5", "Position 45"),
                ("Capture 2", "Position 8"),
            },
        )

    def test_reports_total_batch_progress_without_changing_analysis(self) -> None:
        self._write_pair(39)
        self._write_pair(45)
        events: list[tuple[str, int, int]] = []

        run_simple_fret_analysis(
            self.input_dir,
            self.output_dir,
            config=SimpleFretAnalysisConfig(progress_callback=lambda *event: events.append(event)),
        )

        self.assertEqual(events[0][1:], (0, 2))
        self.assertIn("Procesando Capture 5 / Position 39", [event[0] for event in events])
        self.assertEqual(events[-1][1:], (2, 2))

    def test_one_failed_position_does_not_block_a_valid_pair(self) -> None:
        self._write_pair(39)
        self._write_pair(45, foreground=False)

        result = run_simple_fret_analysis(self.input_dir, self.output_dir)

        self.assertEqual(len(result.positions), 1)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0].position, "Position 45")
        self.assertTrue(result.failures[0].report_path.is_file())
        self.assertEqual(len(result.export.workbook_paths), 1)

    def _write_pair(
        self,
        position: int,
        *,
        capture: int = 5,
        foreground: bool = True,
    ) -> tuple[Path, Path]:
        c0 = np.full((2, 64, 64), 10, dtype=np.uint16)
        c1 = np.full((2, 64, 64), 20, dtype=np.uint16)
        if foreground:
            c0[:, 16:48, 16:48] = 50
            c1[:, 16:48, 16:48] = 100
        stem = f"Capture {capture} - Position {position}_XY{position}_Z0_T00"
        c0_path = self.input_dir / f"{stem}_C0.tif"
        c1_path = self.input_dir / f"{stem}_C1.tif"
        tifffile.imwrite(c0_path, c0)
        tifffile.imwrite(c1_path, c1)
        return c0_path, c1_path


if __name__ == "__main__":
    unittest.main()
