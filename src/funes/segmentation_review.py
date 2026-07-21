"""Immutable backend for Module 7 segmentation review and global approval."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import PositionKey
from .segmentation_selection import (
    CapturePositionKey,
    ResolvedSegmentationSelection,
    SegmentationConfiguration,
    SegmentationReviewStatus,
    SegmentationSelection,
    SegmentationSelectionSource,
)


@dataclass(frozen=True, slots=True)
class SegmentationFieldInspection:
    """Auditable record that one field and exact selection were inspected."""

    field_key: CapturePositionKey
    selection: SegmentationSelection
    selection_source: SegmentationSelectionSource
    inspector: str | None = None
    inspected_at: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.field_key, CapturePositionKey):
            raise TypeError("inspection field_key must be a CapturePositionKey")
        if not isinstance(self.selection, SegmentationSelection):
            raise TypeError("inspection selection must be a SegmentationSelection")
        if not isinstance(self.selection_source, SegmentationSelectionSource):
            raise TypeError(
                "inspection selection_source must be a SegmentationSelectionSource"
            )
        _require_optional_text(self.inspector, "inspector")
        _require_optional_text(self.inspected_at, "inspected_at")
        _require_optional_text(self.note, "note")


@dataclass(frozen=True, slots=True)
class GlobalSegmentationApproval:
    """Explicit approval of one global selection and its inspection snapshot."""

    approval_id: str
    approved_selection: SegmentationSelection
    inspections_before_approval: tuple[SegmentationFieldInspection, ...] = ()
    approved_by: str | None = None
    approved_at: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.approval_id, "approval_id")
        if not isinstance(self.approved_selection, SegmentationSelection):
            raise TypeError("approved_selection must be a SegmentationSelection")
        inspections = tuple(self.inspections_before_approval)
        for inspection in inspections:
            if not isinstance(inspection, SegmentationFieldInspection):
                raise TypeError(
                    "inspections_before_approval must contain "
                    "SegmentationFieldInspection values"
                )
        keys = tuple(inspection.field_key for inspection in inspections)
        if len(set(keys)) != len(keys):
            raise ValueError(
                "inspections_before_approval contains duplicate Capture + Position "
                "fields; keep one inspection record per field"
            )
        object.__setattr__(self, "inspections_before_approval", inspections)
        _require_optional_text(self.approved_by, "approved_by")
        _require_optional_text(self.approved_at, "approved_at")
        _require_optional_text(self.note, "note")

    @property
    def inspected_fields(self) -> tuple[CapturePositionKey, ...]:
        """Fields known to have been inspected before this approval."""

        return tuple(
            inspection.field_key for inspection in self.inspections_before_approval
        )


@dataclass(frozen=True, slots=True)
class SegmentationFieldReviewDecision:
    """Effective selection and review status for one Capture + Position."""

    field_key: CapturePositionKey
    selection: ResolvedSegmentationSelection
    status: SegmentationReviewStatus
    inspection: SegmentationFieldInspection | None = None
    global_approval: GlobalSegmentationApproval | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.field_key, CapturePositionKey):
            raise TypeError("field review field_key must be a CapturePositionKey")
        if not isinstance(self.selection, ResolvedSegmentationSelection):
            raise TypeError(
                "field review selection must be a ResolvedSegmentationSelection"
            )
        if not isinstance(self.status, SegmentationReviewStatus):
            raise TypeError("field review status must be a SegmentationReviewStatus")
        if self.selection.field_key != self.field_key:
            raise ValueError(
                "field review decision key must match the resolved selection key"
            )
        if self.inspection is not None:
            if not isinstance(self.inspection, SegmentationFieldInspection):
                raise TypeError(
                    "field review inspection must be a SegmentationFieldInspection"
                )
            expected_inspection_selection = SegmentationSelection(
                self.selection.method,
                self.selection.profile,
            )
            if (
                self.inspection.field_key != self.field_key
                or self.inspection.selection != expected_inspection_selection
                or self.inspection.selection_source is not self.selection.source
            ):
                raise ValueError(
                    "field review inspection does not match the resolved field, "
                    "method/profile, or selection source; rebuild it from the current "
                    "configuration"
                )
        if self.global_approval is not None:
            if not isinstance(self.global_approval, GlobalSegmentationApproval):
                raise TypeError(
                    "field review global_approval must be a "
                    "GlobalSegmentationApproval"
                )
            resolved_global = SegmentationSelection(
                self.selection.global_method,
                self.selection.global_profile,
            )
            if self.global_approval.approved_selection != resolved_global:
                raise ValueError(
                    "field review global approval does not match the resolved global "
                    "method/profile; record a new approval for the current global "
                    "selection"
                )
        has_override = self.selection.override_applied
        has_inspection = self.inspection is not None
        has_approval = self.global_approval is not None
        expected = (
            SegmentationReviewStatus.EXPLICIT_OVERRIDE
            if has_override
            else SegmentationReviewStatus.MANUALLY_REVIEWED
            if has_inspection
            else SegmentationReviewStatus.GLOBAL_POLICY_ACCEPTED
            if has_approval
            else SegmentationReviewStatus.UNREVIEWED
        )
        if self.status is not expected:
            raise ValueError(
                "field review status is incoherent with override, inspection, and "
                f"global approval records; expected '{expected.value}'"
            )

    @property
    def manually_inspected(self) -> bool:
        return self.inspection is not None

    @property
    def accepted_by_global_policy(self) -> bool:
        return self.status is SegmentationReviewStatus.GLOBAL_POLICY_ACCEPTED

    @property
    def covered(self) -> bool:
        return self.status is not SegmentationReviewStatus.UNREVIEWED


@dataclass(frozen=True, slots=True)
class SegmentationReviewState:
    """Immutable review ledger composed with D044 selection resolution."""

    configuration: SegmentationConfiguration = field(
        default_factory=SegmentationConfiguration
    )
    inspections: tuple[SegmentationFieldInspection, ...] = ()
    global_approval: GlobalSegmentationApproval | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, SegmentationConfiguration):
            raise TypeError("configuration must be a SegmentationConfiguration")
        inspections = tuple(self.inspections)
        for inspection in inspections:
            if not isinstance(inspection, SegmentationFieldInspection):
                raise TypeError(
                    "inspections must contain SegmentationFieldInspection values"
                )
        keys = tuple(inspection.field_key for inspection in inspections)
        if len(set(keys)) != len(keys):
            raise ValueError(
                "duplicate field inspection; keep one current inspection record per "
                "Capture + Position"
            )
        object.__setattr__(self, "inspections", inspections)
        self._validate_inspections_against_configuration()
        self._validate_global_approval()

    def record_inspection(
        self,
        field_key: CapturePositionKey | PositionKey,
        *,
        inspector: str | None = None,
        inspected_at: str | None = None,
        note: str | None = None,
    ) -> SegmentationReviewState:
        """Return a new ledger after an explicit field inspection."""

        normalized_key = _normalize_required_field_key(field_key)
        if any(item.field_key == normalized_key for item in self.inspections):
            raise ValueError(
                f"inspection already recorded for {_format_key(normalized_key)}; "
                "remove the existing record before recording a replacement"
            )
        resolved = self.configuration.resolve(normalized_key)
        inspection = SegmentationFieldInspection(
            field_key=normalized_key,
            selection=SegmentationSelection(resolved.method, resolved.profile),
            selection_source=resolved.source,
            inspector=inspector,
            inspected_at=inspected_at,
            note=note,
        )
        return SegmentationReviewState(
            configuration=self.configuration,
            inspections=(*self.inspections, inspection),
            global_approval=self.global_approval,
        )

    def approve_global(
        self,
        approval_id: str,
        *,
        approved_by: str | None = None,
        approved_at: str | None = None,
        note: str | None = None,
    ) -> SegmentationReviewState:
        """Explicitly approve the current global choice with no sample minimum."""

        if self.global_approval is not None:
            raise ValueError(
                "a global segmentation approval is already recorded; create a new "
                "review state before recording a replacement approval"
            )
        approval = GlobalSegmentationApproval(
            approval_id=approval_id,
            approved_selection=self.configuration.global_selection,
            inspections_before_approval=self.inspections,
            approved_by=approved_by,
            approved_at=approved_at,
            note=note,
        )
        return SegmentationReviewState(
            configuration=self.configuration,
            inspections=self.inspections,
            global_approval=approval,
        )

    def query(
        self,
        field_key: CapturePositionKey | PositionKey,
    ) -> SegmentationFieldReviewDecision:
        """Resolve selection and review provenance for one field."""

        normalized_key = _normalize_required_field_key(field_key)
        resolved = self.configuration.resolve(normalized_key)
        inspection = next(
            (item for item in self.inspections if item.field_key == normalized_key),
            None,
        )
        status = (
            SegmentationReviewStatus.EXPLICIT_OVERRIDE
            if resolved.override_applied
            else SegmentationReviewStatus.MANUALLY_REVIEWED
            if inspection is not None
            else SegmentationReviewStatus.GLOBAL_POLICY_ACCEPTED
            if self.global_approval is not None
            else SegmentationReviewStatus.UNREVIEWED
        )
        return SegmentationFieldReviewDecision(
            field_key=normalized_key,
            selection=resolved,
            status=status,
            inspection=inspection,
            global_approval=self.global_approval,
        )

    def _validate_inspections_against_configuration(self) -> None:
        for inspection in self.inspections:
            resolved = self.configuration.resolve(inspection.field_key)
            expected = SegmentationSelection(resolved.method, resolved.profile)
            if (
                inspection.selection != expected
                or inspection.selection_source is not resolved.source
            ):
                raise ValueError(
                    f"inspection for {_format_key(inspection.field_key)} records "
                    f"'{inspection.selection.method.value}/"
                    f"{inspection.selection.profile}' from "
                    f"'{inspection.selection_source.value}', but the current "
                    f"configuration resolves '{resolved.method.value}/"
                    f"{resolved.profile}' from '{resolved.source.value}'; re-inspect "
                    "the field with the current configuration or remove the stale "
                    "inspection"
                )

    def _validate_global_approval(self) -> None:
        approval = self.global_approval
        if approval is None:
            return
        if not isinstance(approval, GlobalSegmentationApproval):
            raise TypeError("global_approval must be a GlobalSegmentationApproval")
        if approval.approved_selection != self.configuration.global_selection:
            approved = approval.approved_selection
            current = self.configuration.global_selection
            raise ValueError(
                "global approval is stale: it approves "
                f"'{approved.method.value}/{approved.profile}', but the current "
                f"global selection is '{current.method.value}/{current.profile}'; "
                "record a new explicit approval for the current global selection"
            )
        snapshot = approval.inspections_before_approval
        if self.inspections[: len(snapshot)] != snapshot:
            raise ValueError(
                "global approval inspection snapshot is not the leading audit "
                "history; preserve all inspections made before approval in their "
                "original order"
            )



def _normalize_required_field_key(
    value: CapturePositionKey | PositionKey,
) -> CapturePositionKey:
    if isinstance(value, CapturePositionKey):
        return value
    if isinstance(value, PositionKey):
        return CapturePositionKey.from_position_key(value)
    raise TypeError("field_key must be CapturePositionKey or PositionKey")


def _format_key(value: CapturePositionKey) -> str:
    return f"Capture '{value.capture}' + Position '{value.position}'"


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_optional_text(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_text(value, field_name)
