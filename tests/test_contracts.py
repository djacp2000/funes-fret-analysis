import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes import (
    Channel,
    ChannelKey,
    FrameReference,
    IssueSeverity,
    PipelineIssue,
    PositionKey,
    SourceFile,
)


class ContractSmokeTests(unittest.TestCase):
    def test_package_contracts_describe_basic_hierarchy(self) -> None:
        position = PositionKey(
            experiment="Experiment A",
            capture="Capture 1",
            position="Position 2",
        )
        channel_key = ChannelKey(position_key=position, channel=Channel.C1)
        frame = FrameReference(frame_index=3, time_seconds=12.5)

        self.assertEqual(channel_key.position_key.capture, "Capture 1")
        self.assertEqual(channel_key.channel, Channel.C1)
        self.assertEqual(frame.frame_index, 3)

    def test_position_key_rejects_blank_required_labels(self) -> None:
        with self.assertRaisesRegex(ValueError, "capture"):
            PositionKey(capture=" ", position="Position 1")

        with self.assertRaisesRegex(ValueError, "position"):
            PositionKey(capture="Capture 1", position="")

    def test_frame_reference_rejects_negative_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "frame_index"):
            FrameReference(frame_index=-1)

        with self.assertRaisesRegex(ValueError, "time_seconds"):
            FrameReference(frame_index=0, time_seconds=-0.1)

    def test_source_file_preserves_provenance_without_requiring_file_read(self) -> None:
        metadata = {"XY": "1782521382", "Z": "Z0"}
        source = SourceFile(
            path=Path("Capture 1 - Position 1_XY1782521382_Z0_T00_C0.tif"),
            original_name="Capture 1 - Position 1_XY1782521382_Z0_T00_C0.tif",
            metadata=metadata,
        )
        metadata["XY"] = "changed"

        self.assertEqual(source.metadata["XY"], "1782521382")
        self.assertEqual(source.path.suffix, ".tif")

    def test_pipeline_issue_preserves_context(self) -> None:
        issue = PipelineIssue(
            code="example_warning",
            message="Example warning for a future module.",
            severity=IssueSeverity.INFO,
            context={"capture": "Capture 1", "frame_index": 0},
        )

        self.assertEqual(issue.severity, IssueSeverity.INFO)
        self.assertEqual(issue.context["frame_index"], 0)

    def test_pipeline_issue_rejects_empty_code(self) -> None:
        with self.assertRaisesRegex(ValueError, "code"):
            PipelineIssue(code="", message="Message")


if __name__ == "__main__":
    unittest.main()
