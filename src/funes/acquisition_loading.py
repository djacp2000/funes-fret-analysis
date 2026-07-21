"""Module 18 orchestration for loading explicitly assigned acquisitions.

This boundary composes existing Modules 1-4 only. It does not create review
state, grant scientific approval, run segmentation or later analysis, export
workbooks, persist analysis results, or edit ROI masks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .auxiliary_metadata import (
    AuxiliaryMetadataAssociationResult,
    AuxiliaryMetadataDiscoveryResult,
    associate_auxiliary_metadata_files,
    discover_auxiliary_metadata_files,
)
from .contracts import IssueSeverity, PipelineIssue
from .experiment_assignment import (
    ExperimentAssignmentResult,
    ExperimentAssignmentRule,
    assign_experiments,
)
from .file_discovery import FileDiscoveryResult, discover_tiff_files
from .tiff_reader import TiffPair, TiffPairValidationBatch, validate_tiff_pairs


class AcquisitionLoadingError(RuntimeError):
    """Raised when a Module 18 load cannot safely supply assigned pairs."""

    def __init__(
        self,
        message: str,
        *,
        result: AcquisitionLoadResult | None = None,
    ) -> None:
        super().__init__(message)
        self.result = result


@dataclass(frozen=True, slots=True)
class AcquisitionLoadResult:
    """Complete audit trail for one Modules 1-4 acquisition load."""

    root: Path
    assignment_rules: tuple[ExperimentAssignmentRule, ...]
    tiff_discovery: FileDiscoveryResult
    auxiliary_discovery: AuxiliaryMetadataDiscoveryResult
    auxiliary_association: AuxiliaryMetadataAssociationResult
    tiff_validation: TiffPairValidationBatch
    experiment_assignment: ExperimentAssignmentResult
    orchestration_issues: tuple[PipelineIssue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.tiff_discovery, FileDiscoveryResult):
            raise TypeError("tiff_discovery must be a FileDiscoveryResult")
        if not isinstance(
            self.auxiliary_discovery, AuxiliaryMetadataDiscoveryResult
        ):
            raise TypeError(
                "auxiliary_discovery must be an AuxiliaryMetadataDiscoveryResult"
            )
        if not isinstance(
            self.auxiliary_association, AuxiliaryMetadataAssociationResult
        ):
            raise TypeError(
                "auxiliary_association must be an AuxiliaryMetadataAssociationResult"
            )
        if not isinstance(self.tiff_validation, TiffPairValidationBatch):
            raise TypeError("tiff_validation must be a TiffPairValidationBatch")
        if not isinstance(self.experiment_assignment, ExperimentAssignmentResult):
            raise TypeError(
                "experiment_assignment must be an ExperimentAssignmentResult"
            )
        rules = tuple(self.assignment_rules)
        if any(not isinstance(rule, ExperimentAssignmentRule) for rule in rules):
            raise TypeError(
                "assignment_rules must contain only ExperimentAssignmentRule values"
            )
        orchestration_issues = tuple(self.orchestration_issues)
        if any(not isinstance(issue, PipelineIssue) for issue in orchestration_issues):
            raise TypeError(
                "orchestration_issues must contain only PipelineIssue values"
            )
        object.__setattr__(self, "root", Path(self.root))
        object.__setattr__(self, "assignment_rules", rules)
        object.__setattr__(self, "orchestration_issues", orchestration_issues)

    @property
    def issues(self) -> tuple[PipelineIssue, ...]:
        """All unchanged stage issues followed by Module 18 boundary issues."""

        return (
            *self.tiff_discovery.issues,
            *self.auxiliary_discovery.issues,
            *self.auxiliary_association.issues,
            *self.tiff_validation.issues,
            *self.experiment_assignment.issues,
            *self.orchestration_issues,
        )

    @property
    def is_ready(self) -> bool:
        """Whether complete assigned pairs are safe to pass downstream."""

        return bool(self.experiment_assignment.pairs) and not any(
            issue.severity is IssueSeverity.ERROR for issue in self.issues
        )

    @property
    def assigned_pairs(self) -> tuple[TiffPair, ...]:
        """Return complete assigned pairs, refusing partial/error-bearing loads."""

        if not self.is_ready:
            raise AcquisitionLoadingError(
                _incomplete_result_message(self),
                result=self,
            )
        return self.experiment_assignment.pairs


def load_assigned_acquisition(
    root: Path | str,
    assignment_rules: tuple[ExperimentAssignmentRule, ...],
) -> AcquisitionLoadResult:
    """Discover, read, associate, and explicitly assign one acquisition tree.

    Every Module 1-4 stage runs exactly once in dependency order. Stage results
    and issues remain separately available for audit. Errors do not authorize a
    partial downstream scope: callers must use ``assigned_pairs``, which fails
    closed unless the complete load is ready.
    """

    root_path = Path(root).resolve(strict=False)
    if not root_path.exists():
        raise AcquisitionLoadingError(
            f"acquisition root does not exist: {root_path}"
        )
    if not root_path.is_dir():
        raise AcquisitionLoadingError(
            f"acquisition root must be a directory: {root_path}"
        )

    rules = tuple(assignment_rules)
    if any(not isinstance(rule, ExperimentAssignmentRule) for rule in rules):
        raise TypeError(
            "assignment_rules must contain only ExperimentAssignmentRule values"
        )

    tiff_discovery = discover_tiff_files(root_path)
    auxiliary_discovery = discover_auxiliary_metadata_files(root_path)
    auxiliary_association = associate_auxiliary_metadata_files(
        auxiliary_discovery.files,
        tiff_discovery.files,
    )
    tiff_validation = validate_tiff_pairs(tiff_discovery.files)
    experiment_assignment = assign_experiments(
        tiff_validation.pairs,
        rules,
        auxiliary_metadata=auxiliary_discovery.files,
        auxiliary_metadata_associations=auxiliary_association.associations,
    )
    orchestration_issues = ()
    if not experiment_assignment.pairs:
        orchestration_issues = (
            PipelineIssue(
                code="no_assigned_tiff_pairs",
                message=(
                    "The acquisition load produced no complete experiment-assigned "
                    "C0/C1 TIFF pairs."
                ),
                severity=IssueSeverity.ERROR,
                context={"root": str(root_path)},
            ),
        )

    return AcquisitionLoadResult(
        root=root_path,
        assignment_rules=rules,
        tiff_discovery=tiff_discovery,
        auxiliary_discovery=auxiliary_discovery,
        auxiliary_association=auxiliary_association,
        tiff_validation=tiff_validation,
        experiment_assignment=experiment_assignment,
        orchestration_issues=orchestration_issues,
    )


def _incomplete_result_message(result: AcquisitionLoadResult) -> str:
    error_codes = tuple(
        issue.code
        for issue in result.issues
        if issue.severity is IssueSeverity.ERROR
    )
    detail = ", ".join(error_codes) if error_codes else "no assigned pairs"
    return (
        f"acquisition load is not ready for downstream use at {result.root}: "
        f"{detail}"
    )
