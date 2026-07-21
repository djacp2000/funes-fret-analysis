import tempfile
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import Channel
from funes.file_discovery import discover_tiff_files, parse_tiff_filename


class FileDiscoveryTests(unittest.TestCase):
    def test_parse_representative_filename_preserves_metadata_and_source(self) -> None:
        path = Path("Capture 1 - Position 2_XY1782521382_Z0_T00_C1.tif")

        parsed = parse_tiff_filename(path)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.capture, "Capture 1")
        self.assertEqual(parsed.position, "Position 2")
        self.assertEqual(parsed.xy, "XY1782521382")
        self.assertEqual(parsed.z_token, "Z0")
        self.assertEqual(parsed.t_token, "T00")
        self.assertEqual(parsed.channel, Channel.C1)
        self.assertEqual(parsed.source.original_name, path.name)
        self.assertTrue(parsed.source.path.is_absolute())
        self.assertEqual(parsed.source.metadata["XY"], "XY1782521382")

    def test_discover_reports_malformed_tiff_names_without_rejecting_valid_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid = root / "Capture 1 - Position 1_XY1782521382_Z0_T00_C0.tif"
            malformed = root / "Capture 1 - Position 1_C0.tif"
            valid.write_text("not image pixels")
            malformed.write_text("not image pixels")

            result = discover_tiff_files(root)

        self.assertEqual(len(result.files), 1)
        self.assertEqual(result.files[0].source.original_name, valid.name)
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].code, "malformed_tiff_filename")
        self.assertEqual(result.issues[0].context["filename"], malformed.name)

    def test_discover_reports_duplicate_parsed_identities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_dir = root / "a"
            second_dir = root / "b"
            first_dir.mkdir()
            second_dir.mkdir()
            name = "Capture 1 - Position 1_XY1782521382_Z0_T00_C0.tif"
            (first_dir / name).write_text("")
            (second_dir / name).write_text("")

            result = discover_tiff_files(root)

        duplicate_issues = [
            issue for issue in result.issues if issue.code == "duplicate_tiff_filename_identity"
        ]
        self.assertEqual(len(result.files), 2)
        self.assertEqual(len(duplicate_issues), 1)
        self.assertEqual(duplicate_issues[0].context["channel"], "C0")

    def test_case_insensitive_extension_and_channel_are_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lower_channel = root / "Capture 1 - Position 1_XY1782521382_Z0_T00_c1.TIFF"
            ignored = root / "Capture 1 - Position 1_XY1782521382_Z0_T00_C0.txt"
            lower_channel.write_text("")
            ignored.write_text("")

            result = discover_tiff_files(root)

        self.assertEqual(len(result.files), 1)
        self.assertEqual(result.files[0].channel, Channel.C1)
        self.assertEqual(result.files[0].source.original_name, lower_channel.name)
        self.assertEqual(result.issues, ())


if __name__ == "__main__":
    unittest.main()
