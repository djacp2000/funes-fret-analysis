import tempfile
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.auxiliary_metadata import (
    associate_auxiliary_metadata_files,
    discover_auxiliary_metadata_files,
    read_auxiliary_metadata_file,
)
from funes.contracts import IssueSeverity
from funes.file_discovery import discover_tiff_files


class AuxiliaryMetadataTests(unittest.TestCase):
    def test_read_preserves_raw_text_and_safe_key_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "acquisition notes.txt"
            path.write_text(
                "Objective: 40x\n"
                "Exposure = 250 ms\n"
                "free-form note without delimiter\n",
                encoding="utf-8",
            )

            metadata_file, issues = read_auxiliary_metadata_file(path)

        self.assertEqual(issues, ())
        assert metadata_file is not None
        self.assertEqual(metadata_file.source.original_name, "acquisition notes.txt")
        self.assertIn("free-form note", metadata_file.raw_text)
        self.assertEqual(metadata_file.encoding, "utf-8-sig")
        self.assertEqual(
            [(entry.key, entry.value) for entry in metadata_file.key_values],
            [("Objective", "40x"), ("Exposure", "250 ms")],
        )
        self.assertEqual(len(metadata_file.unparsed_lines), 1)
        self.assertEqual(metadata_file.unparsed_lines[0].line_number, 3)

    def test_discover_reads_txt_and_log_files_and_ignores_non_text_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "nested"
            nested.mkdir()
            (root / "metadata.TXT").write_text("Camera: EMCCD\n", encoding="utf-8")
            (root / "export.LOG").write_text("Time Points: 2\n", encoding="utf-8")
            (nested / "ignore.tif").write_text("not metadata", encoding="utf-8")

            result = discover_auxiliary_metadata_files(root)

        self.assertEqual(len(result.files), 2)
        self.assertEqual(
            [metadata.source.original_name for metadata in result.files],
            ["export.LOG", "metadata.TXT"],
        )
        self.assertEqual(result.issues, ())

    def test_slidebook_log_associates_to_explicit_complete_tiff_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c0_name = "Capture 1 - Position 2_XY1757012096_Z0_T0_C0.tif"
            c1_name = "Capture 1 - Position 2_XY1757012096_Z0_T0_C1.tif"
            (root / c0_name).write_bytes(b"")
            (root / c1_name).write_bytes(b"")
            log_path = root / "Capture 1 - Position 2_XY1757012096_Z0_T0_C0.log"
            log_path.write_text(_slidebook_log_text(c0_name, c1_name), encoding="utf-8")

            metadata = discover_auxiliary_metadata_files(root)
            tiffs = discover_tiff_files(root)
            result = associate_auxiliary_metadata_files(metadata.files, tiffs.files)

        self.assertEqual(metadata.issues, ())
        self.assertEqual(tiffs.issues, ())
        self.assertEqual(result.issues, ())
        self.assertEqual(result.unassociated_files, ())
        self.assertEqual(len(result.associations), 1)
        association = result.associations[0]
        self.assertEqual(association.capture, "Capture 1")
        self.assertEqual(association.position, "Position 2")
        self.assertEqual(association.xy, "XY1757012096")
        self.assertEqual(association.z_token, "Z0")
        self.assertEqual(association.t_token, "T0")
        self.assertEqual(association.c0.source.original_name, c0_name)
        self.assertEqual(association.c1.source.original_name, c1_name)
        self.assertEqual(association.referenced_tiff_filenames, (c0_name, c1_name))
        self.assertEqual(association.method, "slidebook_log_tiff_table")
        slidebook_log = association.metadata_file.slidebook_log
        assert slidebook_log is not None
        self.assertEqual(slidebook_log.export_datetime, "07/13/2026 11:47:1")
        self.assertEqual(slidebook_log.capture_datetime, "9/4/2025 14:55:52")
        self.assertEqual(slidebook_log.z_planes, 1)
        self.assertEqual(slidebook_log.time_points, 2)
        self.assertEqual(slidebook_log.channel_count, 2)
        self.assertEqual(slidebook_log.microns_per_pixel, 4.0)
        self.assertEqual(slidebook_log.z_step_size_microns, 0.0)
        self.assertEqual(slidebook_log.average_timelapse_interval, "Unknown")
        self.assertEqual(len(slidebook_log.rows), 2)
        self.assertEqual(slidebook_log.rows[0].x_position_um, 43115.0)
        self.assertEqual(slidebook_log.rows[0].y_position_um, 24395.0)
        self.assertEqual(slidebook_log.rows[0].z_position_um, 8066.12)
        self.assertEqual(slidebook_log.rows[0].elapsed_time_ms, 0.0)
        self.assertEqual(slidebook_log.rows[0].tiff_filename, c0_name)

    def test_more_than_two_declared_channels_produces_preserved_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "three-channel-export.log"
            path.write_text(
                _slidebook_log_text(
                    "Capture 1 - Position 1_XY1_Z0_T0_C0.tif",
                    "Capture 1 - Position 1_XY1_Z0_T0_C1.tif",
                    "Capture 1 - Position 1_XY1_Z0_T0_C2.tif",
                    channel_count=3,
                ),
                encoding="utf-8",
            )

            metadata_file, issues = read_auxiliary_metadata_file(path)

        assert metadata_file is not None
        assert metadata_file.slidebook_log is not None
        self.assertEqual(metadata_file.slidebook_log.channel_count, 3)
        self.assertEqual(len(metadata_file.slidebook_log.rows), 3)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "slidebook_log_channel_count_exceeds_supported")
        self.assertEqual(issues[0].severity, IssueSeverity.WARNING)
        self.assertEqual(issues[0].context["declared_channel_count"], 3)

    def test_log_filename_alone_is_not_used_to_guess_an_association(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c0_name = "Capture 1 - Position 1_XY1_Z0_T0_C0.tif"
            c1_name = "Capture 1 - Position 1_XY1_Z0_T0_C1.tif"
            (root / c0_name).write_bytes(b"")
            (root / c1_name).write_bytes(b"")
            (root / c0_name.replace(".tif", ".log")).write_text(
                "free-form export notes\n",
                encoding="utf-8",
            )

            metadata = discover_auxiliary_metadata_files(root)
            tiffs = discover_tiff_files(root)
            result = associate_auxiliary_metadata_files(metadata.files, tiffs.files)

        self.assertEqual(result.associations, ())
        self.assertEqual(result.unassociated_files, metadata.files)
        self.assertEqual(result.issues, ())

    def test_incomplete_slidebook_pair_is_reported_without_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c0_name = "Capture 1 - Position 1_XY1_Z0_T0_C0.tif"
            (root / c0_name).write_bytes(b"")
            (root / c0_name.replace(".tif", ".log")).write_text(
                _slidebook_log_text(c0_name),
                encoding="utf-8",
            )

            metadata = discover_auxiliary_metadata_files(root)
            tiffs = discover_tiff_files(root)
            result = associate_auxiliary_metadata_files(metadata.files, tiffs.files)

        self.assertEqual(result.associations, ())
        self.assertEqual(result.unassociated_files, metadata.files)
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].code, "auxiliary_metadata_incomplete_tiff_pair")

    def test_unreadable_binary_file_is_reported_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.txt"
            path.write_bytes(b"\xff\xfe\x00\xd8")

            metadata_file, issues = read_auxiliary_metadata_file(path, encodings=("utf-8",))

        self.assertIsNone(metadata_file)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "auxiliary_metadata_decode_failed")
        self.assertEqual(issues[0].context["filename"], "metadata.txt")

    def test_duplicate_keys_are_preserved_as_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.txt"
            path.write_text("Laser: low\nLaser: high\n", encoding="utf-8")

            metadata_file, issues = read_auxiliary_metadata_file(path)

        self.assertEqual(issues, ())
        assert metadata_file is not None
        self.assertEqual(
            [(entry.line_number, entry.key, entry.value) for entry in metadata_file.key_values],
            [(1, "Laser", "low"), (2, "Laser", "high")],
        )


def _slidebook_log_text(
    *tiff_filenames: str,
    channel_count: int = 2,
) -> str:
    header = (
        "Export Date-Time: 07/13/2026 11:47:1\n"
        "Capture Date-Time: 9/4/2025 14:55:52\n"
        "Z Planes: 1\n"
        "Time Points: 2\n"
        f"Channels: {channel_count}\n"
        "Microns Per Pixel: 4\n"
        "Z Step Size Microns: 0\n"
        "Average Timelapse Interval: Unknown\n"
        "IFD\tX Position (um)\tY Position (um)\tZ Position (um)\t"
        "Elapsed Time (ms)\tChannel Name\tTIFF File Name\n"
    )
    rows = [
        f"0\t{43115 + index}\t24395\t8066.12\t0\tchannel {index}\t{filename}\n"
        for index, filename in enumerate(tiff_filenames)
    ]
    return header + "".join(rows)


if __name__ == "__main__":
    unittest.main()
