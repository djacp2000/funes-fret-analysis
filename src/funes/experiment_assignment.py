"""Assign validated TIFF pairs to experiment labels."""

from __future__ import annotations

from dataclasses import dataclass

from .auxiliary_metadata import AuxiliaryMetadataFile, AuxiliaryMetadataPairAssociation
from .contracts import IssueSeverity, PipelineIssue, PositionKey
from .tiff_reader import TiffPair


@dataclass(frozen=True, slots=True)
class ExperimentAssignmentRule:
    """Configuration rule that assigns captures, and optionally positions, to an experiment."""

    experiment: str
    captures: tuple[str, ...]
    positions: tuple[str, ...] = ()
    source: str | None = None

    def __post_init__(self) -> None:
        experiment = _normalize_label(self.experiment)
        captures = tuple(_normalize_label(capture) for capture in self.captures)
        positions = tuple(_normalize_label(position) for position in self.positions)
        if not experiment:
            raise ValueError("experiment must be a non-empty string")
        if not captures:
            raise ValueError("captures must include at least one capture label")
        if any(not capture for capture in captures):
            raise ValueError("captures must not include blank labels")
        if any(not position for position in positions):
            raise ValueError("positions must not include blank labels")
        object.__setattr__(self, "experiment", experiment)
        object.__setattr__(self, "captures", captures)
        object.__setattr__(self, "positions", positions)

    def matches(self, pair: TiffPair) -> bool:
        """Return whether this rule applies to a validated TIFF pair."""

        key = pair.position_key
        capture_match = key.capture.casefold() in _casefolded(self.captures)
        position_match = not self.positions or key.position.casefold() in _casefolded(self.positions)
        return capture_match and position_match


@dataclass(frozen=True, slots=True)
class ExperimentAssignmentRecord:
    """Audit record for one pair assigned by one configuration rule."""

    original_position_key: PositionKey
    assigned_position_key: PositionKey
    rule_index: int
    rule_source: str | None = None


@dataclass(frozen=True, slots=True)
class ExperimentAssignmentResult:
    """Experiment-assigned TIFF pairs plus assignment and metadata provenance."""

    pairs: tuple[TiffPair, ...]
    assignments: tuple[ExperimentAssignmentRecord, ...]
    issues: tuple[PipelineIssue, ...]
    auxiliary_metadata: tuple[AuxiliaryMetadataFile, ...] = ()
    auxiliary_metadata_associations: tuple[AuxiliaryMetadataPairAssociation, ...] = ()


def assign_experiments(
    pairs: tuple[TiffPair, ...],
    rules: tuple[ExperimentAssignmentRule, ...],
    *,
    auxiliary_metadata: tuple[AuxiliaryMetadataFile, ...] = (),
    auxiliary_metadata_associations: tuple[AuxiliaryMetadataPairAssociation, ...] = (),
) -> ExperimentAssignmentResult:
    """Apply experiment assignment rules to validated TIFF pairs.

    Module 3 associations are matched to their validated C0/C1 pair and carried
    with that pair through the assigned Experiment > Capture > Position hierarchy.
    Module 4 still does not infer experiment labels from auxiliary metadata.
    """

    assigned_pairs: list[TiffPair] = []
    records: list[ExperimentAssignmentRecord] = []
    issues: list[PipelineIssue] = []

    for pair in pairs:
        matches = [
            (index, rule)
            for index, rule in enumerate(rules)
            if rule.matches(pair)
        ]
        if not matches:
            issues.append(_missing_assignment_issue(pair))
            continue
        if len(matches) > 1:
            issues.append(_overlapping_assignment_issue(pair, matches))
            continue

        rule_index, rule = matches[0]
        original_key = pair.position_key
        assigned_key = PositionKey(
            experiment=rule.experiment,
            capture=original_key.capture,
            position=original_key.position,
        )
        pair_associations = (
            *pair.auxiliary_metadata_associations,
            *(
                association
                for association in auxiliary_metadata_associations
                if _association_matches_pair(association, pair)
                and association not in pair.auxiliary_metadata_associations
            ),
        )
        assigned_pair = TiffPair(
            position_key=assigned_key,
            c0=pair.c0,
            c1=pair.c1,
            auxiliary_metadata_associations=pair_associations,
        )
        assigned_pairs.append(assigned_pair)
        records.append(
            ExperimentAssignmentRecord(
                original_position_key=original_key,
                assigned_position_key=assigned_key,
                rule_index=rule_index,
                rule_source=rule.source,
            )
        )

    return ExperimentAssignmentResult(
        pairs=tuple(assigned_pairs),
        assignments=tuple(records),
        issues=tuple(issues),
        auxiliary_metadata=tuple(auxiliary_metadata),
        auxiliary_metadata_associations=tuple(auxiliary_metadata_associations),
    )


def _association_matches_pair(
    association: AuxiliaryMetadataPairAssociation,
    pair: TiffPair,
) -> bool:
    return (
        association.c0.source.path.resolve(strict=False)
        == pair.c0.parsed_file.source.path.resolve(strict=False)
        and association.c1.source.path.resolve(strict=False)
        == pair.c1.parsed_file.source.path.resolve(strict=False)
    )


def _missing_assignment_issue(pair: TiffPair) -> PipelineIssue:
    return PipelineIssue(
        code="missing_experiment_assignment",
        message="No experiment assignment rule matched this validated TIFF pair.",
        severity=IssueSeverity.ERROR,
        context={
            "capture": pair.position_key.capture,
            "position": pair.position_key.position,
        },
    )


def _overlapping_assignment_issue(
    pair: TiffPair,
    matches: list[tuple[int, ExperimentAssignmentRule]],
) -> PipelineIssue:
    return PipelineIssue(
        code="overlapping_experiment_assignments",
        message="Multiple experiment assignment rules matched this validated TIFF pair.",
        severity=IssueSeverity.ERROR,
        context={
            "capture": pair.position_key.capture,
            "position": pair.position_key.position,
            "matching_rule_indexes": ", ".join(str(index) for index, _rule in matches),
            "matching_experiments": ", ".join(rule.experiment for _index, rule in matches),
        },
    )


def _normalize_label(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("labels must be strings")
    return " ".join(value.strip().split())


def _casefolded(values: tuple[str, ...]) -> frozenset[str]:
    return frozenset(value.casefold() for value in values)