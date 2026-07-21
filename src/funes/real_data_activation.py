"""Fail-closed Module 23 boundary for one explicitly authorized D099 attempt."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Mapping

from .contracts import MetadataValue, PositionKey
from .experiment_roi_review import ExperimentRoiReviewOrchestrator
from .experiment_roi_review_persistence import (
    load_experiment_roi_review_snapshot,
)
from .module14_exporter import Module14ExportResult
from .real_data_activation_contracts import (
    ACTIVATION_APPLICATION_DIRECTORY,
    ACTIVATION_AUDIT_DIRECTORY,
    ACTIVATION_PURPOSE,
    ACTIVATION_SCIENTIFIC_STATUS,
    ActivationArtifactRecord,
    ActivationAttemptReceipt,
    ActivationAttemptStatus,
    ActivationReviewRecord,
    ActivationSourceRecord,
    RealDataActivationAuthorization,
    RealDataActivationPlan,
    position_configuration_bundle_sha256,
    real_data_activation_plan_sha256,
)
from .reviewed_analysis_persistence import (
    ReviewedAnalysisPackageWriteResult,
    load_reviewed_analysis_package,
)
from .reviewed_application import (
    APPLICATION_ANALYSIS_PACKAGE_NAME,
    APPLICATION_WORKBOOK_DIRECTORY,
    ReviewedApplicationRunResult,
    run_reviewed_application,
)
from .reviewed_experiment_export import ReviewedExperimentExportResult
from .segmentation_registry import SegmentationEngineRegistry


ACTIVATION_STARTED_RECEIPT_NAME = "attempt_started.json"
ACTIVATION_COMPLETED_RECEIPT_NAME = "attempt_completed.json"
ACTIVATION_FAILED_RECEIPT_NAME = "attempt_failed.json"
ACTIVATION_PLAN_DOCUMENT_NAME = "activation_plan.json"

_SOURCE_EXTENSIONS = frozenset({".tif", ".tiff", ".txt", ".log"})


class RealDataActivationError(RuntimeError):
    """One activation attempt failed closed, with its audit location."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        d099_call_count: int = 0,
        attempt_audit_directory: Path | None = None,
        failed_receipt_path: Path | None = None,
        quarantine_directory: Path | None = None,
    ) -> None:
        self.stage = stage
        self.d099_call_count = d099_call_count
        self.attempt_audit_directory = attempt_audit_directory
        self.failed_receipt_path = failed_receipt_path
        self.quarantine_directory = quarantine_directory
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RealDataActivationResult:
    """Published evidence and receipts from one completed Module 23 attempt."""

    output_directory: Path
    application: ReviewedApplicationRunResult
    plan_sha256: str
    source_inventory: tuple[ActivationSourceRecord, ...]
    artifacts: tuple[ActivationArtifactRecord, ...]
    review_records: tuple[ActivationReviewRecord, ...]
    attempt_audit_directory: Path
    started_receipt_path: Path
    completed_receipt_path: Path
    published_completed_receipt_path: Path
    d099_call_count: int = 1
    purpose: str = ACTIVATION_PURPOSE
    scientific_status: str = ACTIVATION_SCIENTIFIC_STATUS

    def __post_init__(self) -> None:
        output = Path(self.output_directory)
        audit = Path(self.attempt_audit_directory)
        if self.application.output_directory != (
            output / ACTIVATION_APPLICATION_DIRECTORY
        ):
            raise ValueError("application must be contained in the activation output")
        if self.d099_call_count != 1:
            raise ValueError("completed activation requires exactly one D099 call")
        if self.purpose != ACTIVATION_PURPOSE or self.scientific_status != ACTIVATION_SCIENTIFIC_STATUS:
            raise ValueError("activation result cannot claim scientific approval")
        object.__setattr__(self, "output_directory", output)
        object.__setattr__(self, "attempt_audit_directory", audit)
        object.__setattr__(self, "source_inventory", tuple(self.source_inventory))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "review_records", tuple(self.review_records))


@dataclass(frozen=True, slots=True)
class _AuthorityState:
    plan_sha256: str
    snapshot_sha256: str
    review_orchestrator: ExperimentRoiReviewOrchestrator


def run_explicit_real_data_activation(
    plan: RealDataActivationPlan,
    authorization: RealDataActivationAuthorization,
    *,
    segmentation_registry: SegmentationEngineRegistry | None = None,
    context: Mapping[str, MetadataValue] | None = None,
) -> RealDataActivationResult:
    """Execute one plan-bound D099 call after the complete D100 authority gate.

    The authority preflight intentionally precedes any acquisition-root listing,
    stat, hash, or read.  No retry, inspection, approval, scientific default, or
    ROI/mask mutation operation is available at this boundary.
    """

    authority = _authority_preflight(plan, authorization)
    audit_directory = plan.attempt_audit_directory
    _reserve_attempt(plan, authority.plan_sha256)
    started_path = audit_directory / ACTIVATION_STARTED_RECEIPT_NAME

    stage = "source_preflight"
    d099_call_count = 0
    source_inventory: tuple[ActivationSourceRecord, ...] = ()
    staging: Path | None = None
    application_result: ReviewedApplicationRunResult | None = None
    try:
        source_inventory = _inventory_acquisition_sources(plan)
        _require_snapshot_unchanged(plan, authority.snapshot_sha256)
        if (
            position_configuration_bundle_sha256(plan.position_configurations)
            != plan.position_configurations_sha256
        ):
            raise RuntimeError("position configuration bundle changed before D099")

        stage = "application_execution"
        staging = _create_activation_staging(plan)
        application_destination = staging / ACTIVATION_APPLICATION_DIRECTORY
        d099_call_count += 1
        application_result = run_reviewed_application(
            plan.acquisition_root,
            plan.assignment_rules,
            plan.review_snapshot_path,
            plan.position_configurations.as_mapping,
            application_destination,
            segmentation_registry=segmentation_registry,
            context=context,
        )

        stage = "postflight"
        artifacts, review_records = _postflight(
            plan,
            authority,
            application_result,
            source_inventory,
            d099_call_count,
        )
        completed_receipt = ActivationAttemptReceipt(
            status=ActivationAttemptStatus.COMPLETED,
            activation_id=plan.activation_id,
            plan_sha256=authority.plan_sha256,
            recorded_at=_now_utc(),
            d099_call_count=d099_call_count,
            source_inventory=source_inventory,
            artifacts=artifacts,
            review_records=review_records,
        )
        published_audit = staging / ACTIVATION_AUDIT_DIRECTORY
        published_audit.mkdir()
        _write_json_exclusive(
            published_audit / ACTIVATION_PLAN_DOCUMENT_NAME,
            _plan_document(plan, authority.plan_sha256),
        )
        _write_json_exclusive(
            published_audit / ACTIVATION_STARTED_RECEIPT_NAME,
            _receipt_document(_started_receipt(plan, authority.plan_sha256)),
        )
        published_completed = published_audit / ACTIVATION_COMPLETED_RECEIPT_NAME
        _write_json_exclusive(
            published_completed, _receipt_document(completed_receipt)
        )

        stage = "publication"
        if plan.output_directory.exists():
            raise RuntimeError("activation output appeared before publication")
        os.replace(staging, plan.output_directory)
        staging = None
        completed_path = audit_directory / ACTIVATION_COMPLETED_RECEIPT_NAME
        _write_json_exclusive(completed_path, _receipt_document(completed_receipt))
    except Exception as exc:
        quarantine = _quarantine_incomplete_attempt(plan, staging)
        failed_path = audit_directory / ACTIVATION_FAILED_RECEIPT_NAME
        failed_receipt = ActivationAttemptReceipt(
            status=ActivationAttemptStatus.FAILED,
            activation_id=plan.activation_id,
            plan_sha256=authority.plan_sha256,
            recorded_at=_now_utc(),
            d099_call_count=d099_call_count,
            source_inventory=source_inventory,
            failure_stage=stage,
            failure_message=str(exc),
        )
        try:
            _write_json_exclusive(failed_path, _receipt_document(failed_receipt))
        except Exception:
            failed_path = None
        raise RealDataActivationError(
            f"Module 23 attempt failed during {stage}: {exc}",
            stage=stage,
            d099_call_count=d099_call_count,
            attempt_audit_directory=audit_directory,
            failed_receipt_path=failed_path,
            quarantine_directory=quarantine,
        ) from exc

    assert application_result is not None
    relocated_application = _relocate_application_result(
        application_result,
        plan.output_directory / ACTIVATION_APPLICATION_DIRECTORY,
    )
    return RealDataActivationResult(
        output_directory=plan.output_directory,
        application=relocated_application,
        plan_sha256=authority.plan_sha256,
        source_inventory=source_inventory,
        artifacts=artifacts,
        review_records=review_records,
        attempt_audit_directory=audit_directory,
        started_receipt_path=started_path,
        completed_receipt_path=completed_path,
        published_completed_receipt_path=(
            plan.output_directory
            / ACTIVATION_AUDIT_DIRECTORY
            / ACTIVATION_COMPLETED_RECEIPT_NAME
        ),
    )


def _authority_preflight(
    plan: RealDataActivationPlan,
    authorization: RealDataActivationAuthorization,
) -> _AuthorityState:
    """Validate all authority inputs without touching the acquisition root."""

    if not isinstance(plan, RealDataActivationPlan):
        raise TypeError("plan must be a RealDataActivationPlan")
    if not isinstance(authorization, RealDataActivationAuthorization):
        raise TypeError("authorization must be a RealDataActivationAuthorization")
    plan_hash = real_data_activation_plan_sha256(plan)
    if (
        authorization.activation_id != plan.activation_id
        or authorization.plan_sha256 != plan_hash
    ):
        raise RealDataActivationError(
            "authorization does not match the exact activation plan ID and SHA-256",
            stage="authority_preflight",
        )
    if plan.output_directory.exists():
        raise RealDataActivationError(
            f"activation output directory already exists: {plan.output_directory}",
            stage="authority_preflight",
        )
    if plan.attempt_audit_directory.exists():
        raise RealDataActivationError(
            "activation ID is already reserved by a started, failed, or completed attempt",
            stage="authority_preflight",
        )
    if (
        position_configuration_bundle_sha256(plan.position_configurations)
        != plan.position_configurations_sha256
    ):
        raise RealDataActivationError(
            "position configuration bundle SHA-256 changed",
            stage="authority_preflight",
        )
    try:
        snapshot_before = _file_sha256(plan.review_snapshot_path)
        if snapshot_before != plan.review_snapshot_sha256:
            raise ValueError("D090 snapshot SHA-256 does not match the plan")
        review = load_experiment_roi_review_snapshot(plan.review_snapshot_path)
        _validate_snapshot_scope(plan, review)
        snapshot_after = _file_sha256(plan.review_snapshot_path)
        if snapshot_after != snapshot_before:
            raise ValueError("D090 snapshot changed during authority preflight")
    except Exception as exc:
        raise RealDataActivationError(
            f"activation snapshot authority preflight failed: {exc}",
            stage="authority_preflight",
        ) from exc
    return _AuthorityState(plan_hash, snapshot_before, review)


def _reserve_attempt(plan: RealDataActivationPlan, plan_hash: str) -> None:
    audit = plan.attempt_audit_directory
    try:
        audit.parent.mkdir(parents=True, exist_ok=True)
        audit.mkdir()
        _write_json_exclusive(
            audit / ACTIVATION_PLAN_DOCUMENT_NAME,
            _plan_document(plan, plan_hash),
        )
        _write_json_exclusive(
            audit / ACTIVATION_STARTED_RECEIPT_NAME,
            _receipt_document(_started_receipt(plan, plan_hash)),
        )
    except Exception as exc:
        raise RealDataActivationError(
            f"could not atomically reserve activation ID {plan.activation_id!r}: {exc}",
            stage="attempt_reservation",
            attempt_audit_directory=audit if audit.exists() else None,
        ) from exc


def _inventory_acquisition_sources(
    plan: RealDataActivationPlan,
) -> tuple[ActivationSourceRecord, ...]:
    root = plan.acquisition_root
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"acquisition root is not an existing directory: {root}")
    actual: dict[str, Path] = {}
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.casefold() in _SOURCE_EXTENSIONS:
            if path.is_symlink():
                raise RuntimeError(f"acquisition source symlinks are not allowed: {path}")
            relative = path.relative_to(root)
            key = os.path.normcase(os.fspath(relative))
            if key in actual:
                raise RuntimeError(f"duplicate acquisition source path: {relative}")
            actual[key] = path
    expected = {
        os.path.normcase(os.fspath(path)): path for path in plan.expected_source_paths
    }
    if set(actual) != set(expected):
        missing = [str(expected[key]) for key in sorted(set(expected) - set(actual))]
        unexpected = [str(actual[key].relative_to(root)) for key in sorted(set(actual) - set(expected))]
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise RuntimeError("acquisition source inventory mismatch: " + "; ".join(details))
    records = []
    for relative in plan.expected_source_paths:
        source = actual[os.path.normcase(os.fspath(relative))]
        records.append(
            ActivationSourceRecord(
                relative_path=relative,
                size_bytes=source.stat().st_size,
                sha256=_file_sha256(source),
            )
        )
    return tuple(records)


def _postflight(
    plan: RealDataActivationPlan,
    authority: _AuthorityState,
    result: ReviewedApplicationRunResult,
    source_inventory: tuple[ActivationSourceRecord, ...],
    d099_call_count: int,
) -> tuple[tuple[ActivationArtifactRecord, ...], tuple[ActivationReviewRecord, ...]]:
    if not isinstance(result, ReviewedApplicationRunResult):
        raise TypeError("D099 did not return ReviewedApplicationRunResult")
    if d099_call_count != 1:
        raise RuntimeError("Module 23 postflight requires one actual D099 call")
    expected_application = (
        plan.output_directory.parent
        / f".{plan.output_directory.name}.{plan.activation_id}.incomplete"
        / ACTIVATION_APPLICATION_DIRECTORY
    )
    if result.output_directory != expected_application:
        raise RuntimeError("D099 result was not written to the private planned staging path")
    if result.review_snapshot_sha256 != authority.snapshot_sha256:
        raise RuntimeError("D099 used a different D090 snapshot hash")
    actual_scope = tuple(pair.position_key for pair in result.acquisition.assigned_pairs)
    expected_scope = tuple(item.position_key for item in plan.positions)
    if actual_scope != expected_scope:
        raise RuntimeError("D099 result scope does not match the exact ordered plan")
    if tuple(
        position.pair.position_key
        for experiment in result.analysis.experiment_results
        for position in experiment.position_results
    ) != expected_scope:
        raise RuntimeError("D099 analysis scope does not match the exact ordered plan")
    _require_snapshot_unchanged(plan, authority.snapshot_sha256)
    if position_configuration_bundle_sha256(plan.position_configurations) != plan.position_configurations_sha256:
        raise RuntimeError("position configuration bundle changed during D099")
    if _inventory_acquisition_sources(plan) != source_inventory:
        raise RuntimeError("raw or auxiliary acquisition sources changed during D099")

    package_path = result.analysis_package.path
    if (
        package_path.name != APPLICATION_ANALYSIS_PACKAGE_NAME
        or _file_sha256(package_path) != result.analysis_package.sha256
    ):
        raise RuntimeError("D098 package receipt or SHA-256 is incoherent")
    restored = load_reviewed_analysis_package(package_path)
    restored_scope = tuple(
        position.pair.position_key
        for experiment in restored.analysis.experiment_results
        for position in experiment.position_results
    )
    if restored_scope != expected_scope:
        raise RuntimeError("D098 package does not preserve the exact planned scope")

    artifacts = [
        ActivationArtifactRecord(
            Path(ACTIVATION_APPLICATION_DIRECTORY) / APPLICATION_ANALYSIS_PACKAGE_NAME,
            package_path.stat().st_size,
            _file_sha256(package_path),
        )
    ]
    for workbook in result.workbook_paths:
        if workbook.parent != result.output_directory / APPLICATION_WORKBOOK_DIRECTORY:
            raise RuntimeError("D094 workbook lies outside the D099 application payload")
        artifacts.append(
            ActivationArtifactRecord(
                Path(ACTIVATION_APPLICATION_DIRECTORY)
                / APPLICATION_WORKBOOK_DIRECTORY
                / workbook.name,
                workbook.stat().st_size,
                _file_sha256(workbook),
            )
        )
    if len(result.workbook_paths) != len(result.analysis.experiment_results):
        raise RuntimeError("D094 workbook count does not match analyzed experiments")
    reviews = tuple(_review_record(result.review_orchestrator, key) for key in expected_scope)
    return tuple(artifacts), reviews


def _validate_snapshot_scope(
    plan: RealDataActivationPlan,
    review: ExperimentRoiReviewOrchestrator,
) -> None:
    expected_groups: list[tuple[str, tuple[PositionKey, ...]]] = []
    for item in plan.positions:
        experiment = item.position_key.experiment
        assert experiment is not None
        if not expected_groups or expected_groups[-1][0] != experiment:
            expected_groups.append((experiment, (item.position_key,)))
        else:
            name, keys = expected_groups[-1]
            expected_groups[-1] = (name, (*keys, item.position_key))
    actual = tuple((item.experiment, item.positions) for item in review.experiments)
    if actual != tuple(expected_groups):
        raise ValueError("D090 snapshot scope/order does not match the activation plan")


def _review_record(
    review: ExperimentRoiReviewOrchestrator, key: PositionKey
) -> ActivationReviewRecord:
    decision = review.query(key).field_review
    approval = decision.global_approval
    return ActivationReviewRecord(
        position_key=key,
        status=decision.status.value,
        manually_inspected=decision.manually_inspected,
        selection_method=decision.selection.method.value,
        selection_profile=decision.selection.profile,
        selection_source=decision.selection.source.value,
        approval_id=None if approval is None else approval.approval_id,
    )


def _create_activation_staging(plan: RealDataActivationPlan) -> Path:
    plan.output_directory.parent.mkdir(parents=True, exist_ok=True)
    staging = (
        plan.output_directory.parent
        / f".{plan.output_directory.name}.{plan.activation_id}.incomplete"
    )
    if staging.exists():
        raise FileExistsError(f"incomplete activation staging already exists: {staging}")
    staging.mkdir()
    return staging


def _quarantine_incomplete_attempt(
    plan: RealDataActivationPlan, staging: Path | None
) -> Path | None:
    if staging is None or not staging.exists():
        return None
    quarantine = plan.attempt_audit_directory / "quarantined_application_evidence"
    try:
        os.replace(staging, quarantine)
        return quarantine
    except OSError:
        return staging


def _relocate_application_result(
    value: ReviewedApplicationRunResult, destination: Path
) -> ReviewedApplicationRunResult:
    exports = tuple(
        ReviewedExperimentExportResult(
            analysis=item.analysis,
            position_exports=item.position_exports,
            module14_export=Module14ExportResult(
                workbook_paths=(
                    destination / APPLICATION_WORKBOOK_DIRECTORY / item.workbook_path.name,
                )
            ),
        )
        for item in value.workbook_exports
    )
    package = ReviewedAnalysisPackageWriteResult(
        path=destination / APPLICATION_ANALYSIS_PACKAGE_NAME,
        sha256=value.analysis_package.sha256,
        payload_sha256=value.analysis_package.payload_sha256,
        experiment_count=value.analysis_package.experiment_count,
        position_count=value.analysis_package.position_count,
        array_count=value.analysis_package.array_count,
    )
    return ReviewedApplicationRunResult(
        output_directory=destination,
        review_snapshot_path=value.review_snapshot_path,
        review_snapshot_sha256=value.review_snapshot_sha256,
        acquisition=value.acquisition,
        review_setup=value.review_setup,
        review_orchestrator=value.review_orchestrator,
        analysis=value.analysis,
        workbook_exports=exports,
        analysis_package=package,
    )


def _require_snapshot_unchanged(plan: RealDataActivationPlan, expected: str) -> None:
    if _file_sha256(plan.review_snapshot_path) != expected:
        raise RuntimeError("D090 snapshot changed during the activation attempt")


def _started_receipt(
    plan: RealDataActivationPlan, plan_hash: str
) -> ActivationAttemptReceipt:
    return ActivationAttemptReceipt(
        status=ActivationAttemptStatus.STARTED,
        activation_id=plan.activation_id,
        plan_sha256=plan_hash,
        recorded_at=_now_utc(),
        d099_call_count=0,
    )


def _plan_document(plan: RealDataActivationPlan, plan_hash: str) -> dict[str, object]:
    return {
        "schema": plan.schema,
        "plan_sha256": plan_hash,
        "activation_id": plan.activation_id,
        "purpose": plan.purpose,
        "scientific_status": plan.scientific_status,
        "acquisition_root": str(plan.acquisition_root),
        "ordered_positions": [
            {
                "experiment": item.position_key.experiment,
                "capture": item.position_key.capture,
                "position": item.position_key.position,
                "c0_relative_path": item.c0_relative_path.as_posix(),
                "c1_relative_path": item.c1_relative_path.as_posix(),
            }
            for item in plan.positions
        ],
        "auxiliary_relative_paths": [path.as_posix() for path in plan.auxiliary_relative_paths],
        "assignment_rules": [_json_value(rule) for rule in plan.assignment_rules],
        "review_snapshot_path": str(plan.review_snapshot_path),
        "review_snapshot_schema": plan.review_snapshot_schema,
        "review_snapshot_sha256": plan.review_snapshot_sha256,
        "position_configurations_schema": plan.position_configurations.schema,
        "position_configurations_sha256": plan.position_configurations_sha256,
        "position_configurations": _json_value(plan.position_configurations),
        "output_directory": str(plan.output_directory),
        "attempt_audit_directory": str(plan.attempt_audit_directory),
        "planned_d099_call_count": 1,
        "no_retry": True,
        "expected_application_artifacts": {
            "application_directory": ACTIVATION_APPLICATION_DIRECTORY,
            "workbook_directory": APPLICATION_WORKBOOK_DIRECTORY,
            "analysis_package": APPLICATION_ANALYSIS_PACKAGE_NAME,
        },
    }


def _receipt_document(receipt: ActivationAttemptReceipt) -> dict[str, object]:
    value = _json_value(receipt)
    assert isinstance(value, dict)
    return value


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _write_json_exclusive(path: Path, payload: Mapping[str, object]) -> None:
    rendered = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    with path.open("xb") as handle:
        handle.write(rendered)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()
