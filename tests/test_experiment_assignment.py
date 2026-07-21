import unittest
from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.auxiliary_metadata import AuxiliaryMetadataFile, AuxiliaryMetadataPairAssociation
from funes.contracts import Channel, PositionKey, SourceFile
from funes.experiment_assignment import (
    ExperimentAssignmentRule,
    assign_experiments,
)
from funes.file_discovery import ParsedTiffFile
from funes.tiff_reader import TiffFrameSequence, TiffMetadata, TiffPair


class ExperimentAssignmentTests(unittest.TestCase):
    def test_assigns_experiment_to_matching_pairs(self) -> None:
        pair = _pair("Capture 1", "Position 2")
        rule = ExperimentAssignmentRule(
            experiment="Drug A",
            captures=("Capture 1",),
        )

        result = assign_experiments((pair,), (rule,))

        self.assertEqual(result.issues, ())
        self.assertEqual(len(result.pairs), 1)
        self.assertEqual(result.pairs[0].position_key.experiment, "Drug A")
        self.assertEqual(result.pairs[0].position_key.capture, "Capture 1")
        self.assertIs(result.pairs[0].c0, pair.c0)
        self.assertIs(result.pairs[0].c1, pair.c1)
        self.assertEqual(result.assignments[0].rule_index, 0)

    def test_position_filter_limits_rule_scope(self) -> None:
        pairs = (
            _pair("Capture 1", "Position 1"),
            _pair("Capture 1", "Position 2"),
        )
        rule = ExperimentAssignmentRule(
            experiment="Baseline",
            captures=("Capture 1",),
            positions=("Position 2",),
        )

        result = assign_experiments(pairs, (rule,))

        self.assertEqual(len(result.pairs), 1)
        self.assertEqual(result.pairs[0].position_key.position, "Position 2")
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].code, "missing_experiment_assignment")
        self.assertEqual(result.issues[0].context["position"], "Position 1")

    def test_overlapping_rules_are_reported_without_assigning_pair(self) -> None:
        pair = _pair("Capture 2", "Position 1")
        rules = (
            ExperimentAssignmentRule(experiment="Experiment A", captures=("Capture 2",)),
            ExperimentAssignmentRule(
                experiment="Experiment B",
                captures=("Capture 2",),
                positions=("Position 1",),
            ),
        )

        result = assign_experiments((pair,), rules)

        self.assertEqual(result.pairs, ())
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].code, "overlapping_experiment_assignments")
        self.assertEqual(result.issues[0].context["matching_experiments"], "Experiment A, Experiment B")

    def test_auxiliary_metadata_is_preserved_but_not_assigned(self) -> None:
        metadata = AuxiliaryMetadataFile(
            source=SourceFile(path=Path("notes.txt"), original_name="notes.txt"),
            raw_text="Experiment: Drug A\n",
            encoding="utf-8",
            key_values=(),
            unparsed_lines=(),
        )
        pair = _pair("Capture 1", "Position 1")
        rule = ExperimentAssignmentRule(experiment="Drug A", captures=("Capture 1",))

        result = assign_experiments((pair,), (rule,), auxiliary_metadata=(metadata,))

        self.assertEqual(result.auxiliary_metadata, (metadata,))

    def test_associated_metadata_is_attached_to_the_assigned_pair(self) -> None:
        pair = _pair("Capture 1", "Position 1")
        association = _association(pair)
        unrelated_association = _association(_pair("Capture 2", "Position 1"))
        rule = ExperimentAssignmentRule(experiment="Drug A", captures=("Capture 1",))

        result = assign_experiments(
            (pair,),
            (rule,),
            auxiliary_metadata_associations=(association, unrelated_association),
        )

        self.assertEqual(
            result.auxiliary_metadata_associations,
            (association, unrelated_association),
        )
        self.assertEqual(result.pairs[0].auxiliary_metadata_associations, (association,))

    def test_rules_require_non_empty_capture_scope(self) -> None:
        with self.assertRaisesRegex(ValueError, "captures"):
            ExperimentAssignmentRule(experiment="Drug A", captures=())


def _association(pair: TiffPair) -> AuxiliaryMetadataPairAssociation:
    metadata = AuxiliaryMetadataFile(
        source=SourceFile(path=Path("capture.log"), original_name="capture.log"),
        raw_text="Export Date-Time: 07/13/2026 11:47:1\n",
        encoding="utf-8",
        key_values=(),
        unparsed_lines=(),
    )
    return AuxiliaryMetadataPairAssociation(
        metadata_file=metadata,
        capture=pair.position_key.capture,
        position=pair.position_key.position,
        xy=pair.c0.parsed_file.xy,
        z_token=pair.c0.parsed_file.z_token,
        t_token=pair.c0.parsed_file.t_token,
        c0=pair.c0.parsed_file,
        c1=pair.c1.parsed_file,
        referenced_tiff_filenames=(
            pair.c0.parsed_file.source.original_name,
            pair.c1.parsed_file.source.original_name,
        ),
    )

def _pair(capture: str, position: str) -> TiffPair:
    c0 = _sequence(capture, position, Channel.C0)
    c1 = _sequence(capture, position, Channel.C1)
    return TiffPair(position_key=PositionKey(capture=capture, position=position), c0=c0, c1=c1)


def _sequence(capture: str, position: str, channel: Channel) -> TiffFrameSequence:
    parsed = ParsedTiffFile(
        source=SourceFile(
            path=Path(f"{capture} - {position}_XY1_Z0_T00_{channel.value}.tif"),
            original_name=f"{capture} - {position}_XY1_Z0_T00_{channel.value}.tif",
        ),
        capture=capture,
        position=position,
        xy="XY1",
        z_token="Z0",
        t_token="T00",
        channel=channel,
    )
    metadata = TiffMetadata(
        page_count=1,
        series_axes=None,
        series_shape=(1, 2, 2),
        imagej_metadata=None,
        ome_metadata=None,
        page_descriptions=(),
        first_page_tags={},
    )
    return TiffFrameSequence(
        parsed_file=parsed,
        frames=np.zeros((1, 2, 2), dtype=np.uint16),
        metadata=metadata,
    )


if __name__ == "__main__":
    unittest.main()
