"""Immutable Module 23 activation contracts and canonical hashes.

These contracts bind one caller-authored acquisition plan.  Constructing or
hashing them performs no filesystem access and grants no scientific approval.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ._analysis_package_codec import encode_object_graph
from .contracts import Channel, PositionKey
from .experiment_assignment import ExperimentAssignmentRule
from .experiment_roi_review_persistence import EXPERIMENT_ROI_REVIEW_SNAPSHOT_SCHEMA
from .file_discovery import parse_tiff_filename
from .position_analysis import PositionAnalysisConfig
from .reviewed_analysis_persistence import PositionAnalysisConfigEntry
from .reviewed_application import (
    APPLICATION_ANALYSIS_PACKAGE_NAME,
    APPLICATION_WORKBOOK_DIRECTORY,
)


REAL_DATA_ACTIVATION_PLAN_SCHEMA = "funes.module23.real_data_activation_plan.v1"
POSITION_CONFIG_BUNDLE_SCHEMA = "funes.module23.position_config_bundle.v1"
ACTIVATION_PURPOSE = "evidence_generation_only"
ACTIVATION_SCIENTIFIC_STATUS = "not_approved"
ACTIVATION_APPLICATION_DIRECTORY = "application"
ACTIVATION_AUDIT_DIRECTORY = "activation_audit"
PLANNED_D099_CALL_COUNT = 1

_PLAN_HASH_DOMAIN = b"funes-module23-real-data-activation-plan-v1\0"
_CONFIG_HASH_DOMAIN = b"funes-module23-position-config-bundle-v1\0"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_SAFE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


class ActivationAttemptStatus(str, Enum):
    STARTED = "attempt_started"
    COMPLETED = "attempt_completed"
    FAILED = "attempt_failed"


@dataclass(frozen=True, slots=True)
class ActivationPositionScope:
    """One exact ordered Experiment > Capture > Position C0/C1 source pair."""

    position_key: PositionKey
    c0_relative_path: Path
    c1_relative_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if self.position_key.experiment is None:
            raise ValueError("activation positions require an experiment label")
        c0 = _relative_path(self.c0_relative_path, "c0_relative_path")
        c1 = _relative_path(self.c1_relative_path, "c1_relative_path")
        _validate_tiff_identity(c0, self.position_key, Channel.C0)
        _validate_tiff_identity(c1, self.position_key, Channel.C1)
        if _path_key(c0) == _path_key(c1):
            raise ValueError("C0 and C1 activation paths must be distinct")
        object.__setattr__(self, "c0_relative_path", c0)
        object.__setattr__(self, "c1_relative_path", c1)


@dataclass(frozen=True, slots=True)
class PositionConfigurationBundle:
    """Versioned exact Module 15 configuration entries in acquisition order."""

    entries: tuple[PositionAnalysisConfigEntry, ...]
    schema: str = POSITION_CONFIG_BUNDLE_SCHEMA
    purpose: str = ACTIVATION_PURPOSE
    scientific_status: str = ACTIVATION_SCIENTIFIC_STATUS

    def __post_init__(self) -> None:
        if self.schema != POSITION_CONFIG_BUNDLE_SCHEMA:
            raise ValueError("unsupported Module 23 configuration-bundle schema")
        _require_non_approving_scope(self.purpose, self.scientific_status)
        entries = tuple(self.entries)
        if not entries:
            raise ValueError("position configuration bundle must not be empty")
        if any(not isinstance(item, PositionAnalysisConfigEntry) for item in entries):
            raise TypeError(
                "entries must contain PositionAnalysisConfigEntry values"
            )
        keys = tuple(item.position_key for item in entries)
        if any(key.experiment is None for key in keys):
            raise ValueError("configuration positions require experiment labels")
        if len(set(keys)) != len(keys):
            raise ValueError("configuration bundle contains duplicate positions")
        object.__setattr__(self, "entries", entries)

    @property
    def as_mapping(self) -> dict[PositionKey, PositionAnalysisConfig]:
        return {item.position_key: item.config for item in self.entries}


@dataclass(frozen=True, slots=True)
class RealDataActivationPlan:
    """One immutable caller-authored, single-attempt Module 23 plan."""

    activation_id: str
    acquisition_root: Path
    positions: tuple[ActivationPositionScope, ...]
    auxiliary_relative_paths: tuple[Path, ...]
    assignment_rules: tuple[ExperimentAssignmentRule, ...]
    review_snapshot_path: Path
    review_snapshot_sha256: str
    position_configurations: PositionConfigurationBundle
    position_configurations_sha256: str
    output_directory: Path
    attempt_audit_directory: Path
    schema: str = REAL_DATA_ACTIVATION_PLAN_SCHEMA
    review_snapshot_schema: str = EXPERIMENT_ROI_REVIEW_SNAPSHOT_SCHEMA
    purpose: str = ACTIVATION_PURPOSE
    scientific_status: str = ACTIVATION_SCIENTIFIC_STATUS
    planned_d099_call_count: int = PLANNED_D099_CALL_COUNT
    no_retry: bool = True
    application_directory_name: str = ACTIVATION_APPLICATION_DIRECTORY
    activation_audit_directory_name: str = ACTIVATION_AUDIT_DIRECTORY
    expected_analysis_package_name: str = APPLICATION_ANALYSIS_PACKAGE_NAME
    expected_workbook_directory_name: str = APPLICATION_WORKBOOK_DIRECTORY

    def __post_init__(self) -> None:
        if not isinstance(self.activation_id, str) or not _SAFE_ID_PATTERN.fullmatch(
            self.activation_id
        ):
            raise ValueError("activation_id must be a filesystem-safe identifier")
        if self.schema != REAL_DATA_ACTIVATION_PLAN_SCHEMA:
            raise ValueError("unsupported Module 23 activation-plan schema")
        if self.review_snapshot_schema != EXPERIMENT_ROI_REVIEW_SNAPSHOT_SCHEMA:
            raise ValueError("activation plan requires the exact D090 snapshot schema")
        _require_non_approving_scope(self.purpose, self.scientific_status)
        if self.planned_d099_call_count != 1 or self.no_retry is not True:
            raise ValueError("Module 23 requires exactly one D099 call and no retry")
        if (
            self.application_directory_name != ACTIVATION_APPLICATION_DIRECTORY
            or self.activation_audit_directory_name != ACTIVATION_AUDIT_DIRECTORY
            or self.expected_analysis_package_name != APPLICATION_ANALYSIS_PACKAGE_NAME
            or self.expected_workbook_directory_name != APPLICATION_WORKBOOK_DIRECTORY
        ):
            raise ValueError("Module 23 artifact names are fixed by D100")
        if not _is_sha256(self.review_snapshot_sha256):
            raise ValueError("review_snapshot_sha256 must be lowercase SHA-256")
        if not _is_sha256(self.position_configurations_sha256):
            raise ValueError(
                "position_configurations_sha256 must be lowercase SHA-256"
            )
        if not isinstance(
            self.position_configurations, PositionConfigurationBundle
        ):
            raise TypeError(
                "position_configurations must be a PositionConfigurationBundle"
            )
        actual_config_hash = position_configuration_bundle_sha256(
            self.position_configurations
        )
        if actual_config_hash != self.position_configurations_sha256:
            raise ValueError("position configuration bundle SHA-256 does not match")

        positions = tuple(self.positions)
        if not positions or any(
            not isinstance(item, ActivationPositionScope) for item in positions
        ):
            raise TypeError(
                "positions must contain at least one ActivationPositionScope"
            )
        keys = tuple(item.position_key for item in positions)
        if len(set(keys)) != len(keys):
            raise ValueError("activation plan contains duplicate positions")
        if tuple(item.position_key for item in self.position_configurations.entries) != keys:
            raise ValueError(
                "configuration bundle must match the exact ordered activation scope"
            )
        _require_contiguous_experiments(keys)

        auxiliary = tuple(
            _relative_path(path, "auxiliary_relative_paths")
            for path in self.auxiliary_relative_paths
        )
        if any(path.suffix.casefold() not in {".txt", ".log"} for path in auxiliary):
            raise ValueError("activation auxiliary sources must be .txt or .log files")
        source_paths = tuple(
            path
            for item in positions
            for path in (item.c0_relative_path, item.c1_relative_path)
        ) + auxiliary
        if len({_path_key(path) for path in source_paths}) != len(source_paths):
            raise ValueError("activation plan contains duplicate source paths")

        rules = tuple(self.assignment_rules)
        if not rules or any(
            not isinstance(rule, ExperimentAssignmentRule) for rule in rules
        ):
            raise TypeError(
                "assignment_rules must contain at least one ExperimentAssignmentRule"
            )
        _validate_assignment_coverage(keys, rules)

        acquisition_root = _absolute_path(self.acquisition_root)
        snapshot_path = _absolute_path(self.review_snapshot_path)
        output_directory = _absolute_path(self.output_directory)
        audit_directory = _absolute_path(self.attempt_audit_directory)
        _validate_role_paths(
            acquisition_root, snapshot_path, output_directory, audit_directory
        )

        object.__setattr__(self, "positions", positions)
        object.__setattr__(self, "auxiliary_relative_paths", auxiliary)
        object.__setattr__(self, "assignment_rules", rules)
        object.__setattr__(self, "acquisition_root", acquisition_root)
        object.__setattr__(self, "review_snapshot_path", snapshot_path)
        object.__setattr__(self, "output_directory", output_directory)
        object.__setattr__(self, "attempt_audit_directory", audit_directory)

    @property
    def expected_source_paths(self) -> tuple[Path, ...]:
        return tuple(
            path
            for item in self.positions
            for path in (item.c0_relative_path, item.c1_relative_path)
        ) + self.auxiliary_relative_paths


@dataclass(frozen=True, slots=True)
class RealDataActivationAuthorization:
    """A separate explicit statement bound to one exact plan identifier/hash."""

    activation_id: str
    plan_sha256: str
    statement: str
    purpose: str = ACTIVATION_PURPOSE
    scientific_status: str = ACTIVATION_SCIENTIFIC_STATUS
    authorized_d099_call_count: int = PLANNED_D099_CALL_COUNT
    no_retry: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.activation_id, str) or not _SAFE_ID_PATTERN.fullmatch(
            self.activation_id
        ):
            raise ValueError("authorization activation_id is invalid")
        if not _is_sha256(self.plan_sha256):
            raise ValueError("authorization plan_sha256 must be lowercase SHA-256")
        _require_non_approving_scope(self.purpose, self.scientific_status)
        if self.authorized_d099_call_count != 1 or self.no_retry is not True:
            raise ValueError("authorization must permit one D099 call and no retry")
        expected = required_activation_statement(self.activation_id, self.plan_sha256)
        if self.statement != expected:
            raise ValueError(
                "authorization statement must name the exact plan ID and SHA-256"
            )


@dataclass(frozen=True, slots=True)
class ActivationSourceRecord:
    relative_path: Path
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        path = _relative_path(self.relative_path, "relative_path")
        if not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise ValueError("source size_bytes must be non-negative")
        if not _is_sha256(self.sha256):
            raise ValueError("source sha256 must be lowercase SHA-256")
        object.__setattr__(self, "relative_path", path)


@dataclass(frozen=True, slots=True)
class ActivationArtifactRecord:
    relative_path: Path
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        path = _relative_path(self.relative_path, "relative_path")
        if not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise ValueError("artifact size_bytes must be non-negative")
        if not _is_sha256(self.sha256):
            raise ValueError("artifact sha256 must be lowercase SHA-256")
        object.__setattr__(self, "relative_path", path)


@dataclass(frozen=True, slots=True)
class ActivationReviewRecord:
    position_key: PositionKey
    status: str
    manually_inspected: bool
    selection_method: str
    selection_profile: str
    selection_source: str
    approval_id: str | None


@dataclass(frozen=True, slots=True)
class ActivationAttemptReceipt:
    """Immutable operational receipt; never a scientific approval record."""

    status: ActivationAttemptStatus
    activation_id: str
    plan_sha256: str
    recorded_at: str
    d099_call_count: int
    source_inventory: tuple[ActivationSourceRecord, ...] = ()
    artifacts: tuple[ActivationArtifactRecord, ...] = ()
    review_records: tuple[ActivationReviewRecord, ...] = ()
    failure_stage: str | None = None
    failure_message: str | None = None
    purpose: str = ACTIVATION_PURPOSE
    scientific_status: str = ACTIVATION_SCIENTIFIC_STATUS
    no_retry: bool = True
    automatic_retry_performed: bool = False
    inspection_performed: bool = False
    approval_performed: bool = False
    scientific_default_selected: bool = False
    roi_or_mask_edited: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.status, ActivationAttemptStatus):
            raise TypeError("status must be an ActivationAttemptStatus")
        if not isinstance(self.activation_id, str) or not _SAFE_ID_PATTERN.fullmatch(
            self.activation_id
        ):
            raise ValueError("receipt activation_id is invalid")
        if not _is_sha256(self.plan_sha256):
            raise ValueError("receipt plan_sha256 must be lowercase SHA-256")
        if not isinstance(self.recorded_at, str) or not self.recorded_at.strip():
            raise ValueError("receipt recorded_at must be non-empty")
        if self.d099_call_count not in (0, 1):
            raise ValueError("receipt D099 call count must be zero or one")
        _require_non_approving_scope(self.purpose, self.scientific_status)
        if (
            self.no_retry is not True
            or self.automatic_retry_performed
            or self.inspection_performed
            or self.approval_performed
            or self.scientific_default_selected
            or self.roi_or_mask_edited
        ):
            raise ValueError("receipt contradicts the D100 non-approving boundary")
        sources = tuple(self.source_inventory)
        artifacts = tuple(self.artifacts)
        reviews = tuple(self.review_records)
        if any(not isinstance(item, ActivationSourceRecord) for item in sources):
            raise TypeError("source_inventory contains an invalid record")
        if any(not isinstance(item, ActivationArtifactRecord) for item in artifacts):
            raise TypeError("artifacts contains an invalid record")
        if any(not isinstance(item, ActivationReviewRecord) for item in reviews):
            raise TypeError("review_records contains an invalid record")
        if self.status is ActivationAttemptStatus.STARTED:
            if self.d099_call_count != 0 or self.failure_stage is not None:
                raise ValueError("started receipt must precede D099 and failure")
        elif self.status is ActivationAttemptStatus.COMPLETED:
            if self.d099_call_count != 1 or self.failure_stage is not None:
                raise ValueError("completed receipt requires exactly one D099 call")
        elif not self.failure_stage or not self.failure_message:
            raise ValueError("failed receipt requires an actionable stage and message")
        object.__setattr__(self, "source_inventory", sources)
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "review_records", reviews)


def position_configuration_bundle_sha256(
    value: PositionConfigurationBundle,
) -> str:
    if not isinstance(value, PositionConfigurationBundle):
        raise TypeError("value must be a PositionConfigurationBundle")
    return _graph_sha256(
        value,
        POSITION_CONFIG_BUNDLE_SCHEMA,
        _CONFIG_HASH_DOMAIN,
        (PositionConfigurationBundle, PositionAnalysisConfigEntry),
    )


def real_data_activation_plan_sha256(value: RealDataActivationPlan) -> str:
    if not isinstance(value, RealDataActivationPlan):
        raise TypeError("value must be a RealDataActivationPlan")
    return _graph_sha256(
        value,
        REAL_DATA_ACTIVATION_PLAN_SCHEMA,
        _PLAN_HASH_DOMAIN,
        (
            RealDataActivationPlan,
            ActivationPositionScope,
            PositionConfigurationBundle,
            PositionAnalysisConfigEntry,
        ),
    )


def required_activation_statement(activation_id: str, plan_sha256: str) -> str:
    """Return the exact statement a later caller must explicitly supply."""

    return (
        f"Authorize exactly one D100 real-data attempt for activation plan "
        f"{activation_id} with SHA-256 {plan_sha256}. Permit the acquisition "
        "reads and exactly one D099 call bound to that plan, with no retry, "
        "substitution, repair, approval action, or ROI/mask edit. The run is "
        "for evidence generation only and its scientific status remains not approved."
    )


def _graph_sha256(
    value: object,
    schema: str,
    domain: bytes,
    extra_types: tuple[type[object], ...],
) -> str:
    payload, arrays = encode_object_graph(value, extra_types=extra_types)
    members = [
        {
            "path": name,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for name, content in sorted(arrays.items())
    ]
    canonical = json.dumps(
        {"schema": schema, "payload": payload, "members": members},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(domain + canonical).hexdigest()


def _validate_tiff_identity(
    relative_path: Path, position_key: PositionKey, channel: Channel
) -> None:
    parsed = parse_tiff_filename(relative_path.name)
    if parsed is None:
        raise ValueError(f"planned TIFF filename is not recognized: {relative_path}")
    if (
        parsed.capture.casefold() != position_key.capture.casefold()
        or parsed.position.casefold() != position_key.position.casefold()
        or parsed.channel is not channel
    ):
        raise ValueError(
            f"planned {channel.value} TIFF does not match its Capture + Position"
        )


def _validate_assignment_coverage(
    keys: tuple[PositionKey, ...], rules: tuple[ExperimentAssignmentRule, ...]
) -> None:
    for key in keys:
        matches = [
            rule
            for rule in rules
            if key.capture.casefold() in {item.casefold() for item in rule.captures}
            and (
                not rule.positions
                or key.position.casefold()
                in {item.casefold() for item in rule.positions}
            )
        ]
        if len(matches) != 1 or matches[0].experiment != key.experiment:
            raise ValueError(
                "assignment rules must map every planned position exactly once "
                "to its declared experiment"
            )


def _require_contiguous_experiments(keys: tuple[PositionKey, ...]) -> None:
    seen: set[str] = set()
    prior: str | None = None
    for key in keys:
        experiment = key.experiment
        assert experiment is not None
        if experiment != prior:
            if experiment in seen:
                raise ValueError(
                    "positions for one experiment must form one contiguous ordered scope"
                )
            seen.add(experiment)
            prior = experiment


def _validate_role_paths(
    acquisition: Path, snapshot: Path, output: Path, audit: Path
) -> None:
    paths = (acquisition, snapshot, output, audit)
    if len({_path_key(path) for path in paths}) != len(paths):
        raise ValueError("activation path roles must not alias one another")
    if _contains(acquisition, snapshot) or _contains(acquisition, output) or _contains(
        acquisition, audit
    ):
        raise ValueError(
            "snapshot, output, and audit paths must remain outside acquisition root"
        )
    if _contains(output, audit) or _contains(audit, output):
        raise ValueError("output and attempt-audit directories must not overlap")


def _relative_path(value: Path | str, name: str) -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"{name} must be a safe relative path")
    return path


def _absolute_path(value: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(value)))


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _path_key(path: Path) -> str:
    return os.path.normcase(os.fspath(path))


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA256_PATTERN.fullmatch(value))


def _require_non_approving_scope(purpose: str, scientific_status: str) -> None:
    if purpose != ACTIVATION_PURPOSE:
        raise ValueError("Module 23 purpose must be evidence_generation_only")
    if scientific_status != ACTIVATION_SCIENTIFIC_STATUS:
        raise ValueError("Module 23 scientific status must remain not_approved")
