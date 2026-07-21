import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np
import tifffile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import Channel
from funes.file_discovery import parse_tiff_filename
from funes.tiff_reader import read_tiff_sequence, validate_tiff_pair, validate_tiff_pairs


class TiffReaderTests(unittest.TestCase):
    def test_read_2d_tiff_as_single_temporal_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Capture 1 - Position 1_XY1782521382_Z0_T00_C0.tif"
            pixels = np.arange(6, dtype=np.uint16).reshape(2, 3)
            tifffile.imwrite(path, pixels, description="synthetic single frame")
            parsed = parse_tiff_filename(path)

            assert parsed is not None
            sequence = read_tiff_sequence(parsed)

        self.assertEqual(sequence.frames.shape, (1, 2, 3))
        self.assertEqual(sequence.frame_count, 1)
        self.assertEqual(sequence.height, 2)
        self.assertEqual(sequence.width, 3)
        self.assertEqual(sequence.dtype_name, "uint16")
        self.assertEqual(sequence.parsed_file.channel, Channel.C0)
        self.assertIn("ImageWidth", sequence.metadata.first_page_tags)

    def test_validate_pair_accepts_matching_3d_temporal_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c0_path = root / "Capture 1 - Position 2_XY1782521382_Z0_T00_C0.tif"
            c1_path = root / "Capture 1 - Position 2_XY1782521382_Z0_T00_C1.tif"
            tifffile.imwrite(c0_path, np.zeros((4, 3, 5), dtype=np.uint16), photometric="minisblack")
            tifffile.imwrite(c1_path, np.ones((4, 3, 5), dtype=np.uint16), photometric="minisblack")
            c0 = parse_tiff_filename(c0_path)
            c1 = parse_tiff_filename(c1_path)

            assert c0 is not None
            assert c1 is not None
            result = validate_tiff_pair(c0, c1)

        self.assertTrue(result.is_valid)
        self.assertIsNotNone(result.pair)
        assert result.pair is not None
        self.assertEqual(result.pair.c0.frames.shape, (4, 3, 5))
        self.assertEqual(result.pair.c1.frame_count, 4)
        self.assertEqual(result.pair.position_key.capture, "Capture 1")

    def test_read_slidebook_style_ifd_pages_in_ifd_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Capture 1 - Position 1_XY1782521382_Z0_T00_C0.tif"
            expected = np.stack(
                (
                    np.arange(12, dtype=np.uint16).reshape(3, 4),
                    np.arange(12, 24, dtype=np.uint16).reshape(3, 4),
                )
            )
            with tifffile.TiffWriter(path) as writer:
                for frame in expected:
                    writer.write(
                        frame,
                        photometric="minisblack",
                        metadata=None,
                        contiguous=True,
                    )
            parsed = parse_tiff_filename(path)

            assert parsed is not None
            sequence = read_tiff_sequence(parsed)

        self.assertEqual(sequence.metadata.series_axes, "IYX")
        self.assertEqual(sequence.metadata.page_count, 2)
        self.assertEqual(len(sequence.metadata.page_tags), 2)
        self.assertTrue(np.array_equal(sequence.frames, expected))
        self.assertIn("ImageWidth", sequence.metadata.page_tags[0])
        self.assertIn("ImageWidth", sequence.metadata.page_tags[1])

    def test_validate_pair_reports_frame_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c0_path = root / "Capture 1 - Position 1_XY1782521382_Z0_T00_C0.tif"
            c1_path = root / "Capture 1 - Position 1_XY1782521382_Z0_T00_C1.tif"
            tifffile.imwrite(c0_path, np.zeros((2, 3, 3), dtype=np.uint16))
            tifffile.imwrite(c1_path, np.ones((3, 3, 3), dtype=np.uint16))
            c0 = parse_tiff_filename(c0_path)
            c1 = parse_tiff_filename(c1_path)

            assert c0 is not None
            assert c1 is not None
            result = validate_tiff_pair(c0, c1)

        self.assertFalse(result.is_valid)
        self.assertIsNone(result.pair)
        self.assertIn("pair_frame_count_mismatch", {issue.code for issue in result.issues})

    def test_validate_pairs_reports_missing_channel_without_reading_next_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Capture 1 - Position 1_XY1782521382_Z0_T00_C0.tif"
            tifffile.imwrite(path, np.zeros((2, 3), dtype=np.uint16))
            parsed = parse_tiff_filename(path)

            assert parsed is not None
            batch = validate_tiff_pairs((parsed,))

        self.assertEqual(batch.pairs, ())
        self.assertEqual(len(batch.issues), 1)
        self.assertEqual(batch.issues[0].code, "missing_tiff_pair_channel")
        self.assertEqual(batch.issues[0].context["missing_channel"], "C1")


if __name__ == "__main__":
    unittest.main()
