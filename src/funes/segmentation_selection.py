"""Typed Module 7 method/profile selection and field override resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from .segmentation_review import SegmentationFieldReviewDecision

from .contracts import PositionKey


BENCHMARK_BASELINE_PROFILE = "benchmark_baseline"
PROVISIONAL_WORKING_PROFILE = "provisional_working_kmeans_area32"


class SegmentationMethodId(str, Enum):
    """Stable identifiers for the five scientifically reviewed methods."""

    KMEANS = "kmeans"
    CELLPOSE_CPSAM = "cellpose_cpsam"
    MARKER_WATERSHED = "marker_watershed"
    OTSU_GLOBAL = "otsu_global"
    CONTROL_P99 = "control_p99"


SEGMENTATION_METHOD_ORDER = (
    SegmentationMethodId.KMEANS,
    SegmentationMethodId.CELLPOSE_CPSAM,
    SegmentationMethodId.MARKER_WATERSHED,
    SegmentationMethodId.OTSU_GLOBAL,
    SegmentationMethodId.CONTROL_P99,
)


class SegmentationSelectionSource(str, Enum):
    """Where the effective field selection came from."""

    GLOBAL = "global"
    CAPTURE_POSITION_OVERRIDE = "capture_position_override"


class SegmentationReviewStatus(str, Enum):
    """Mutually exclusive field status after applying review precedence."""

    UNREVIEWED = "unreviewed"
    MANUALLY_REVIEWED = "manually_reviewed"
    GLOBAL_POLICY_ACCEPTED = "global_policy_accepted"
    EXPLICIT_OVERRIDE = "explicit_override"


@dataclass(frozen=True, slots=True)
class SegmentationSelection:
    """One named method/profile choice."""

    method: SegmentationMethodId = SegmentationMethodId.KMEANS
    profile: str = BENCHMARK_BASELINE_PROFILE

    def __post_init__(self) -> None:
        if not isinstance(self.method, SegmentationMethodId):
            try:
                object.__setattr__(self, "method", SegmentationMethodId(self.method))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"unknown segmentation method: {self.method!r}") from exc
        _require_text(self.profile, "profile")


@dataclass(frozen=True, slots=True)
class CapturePositionKey:
    """Override key scoped exactly to one Capture + Position field."""

    capture: str
    position: str

    def __post_init__(self) -> None:
        _require_text(self.capture, "capture")
        _require_text(self.position, "position")

    @classmethod
    def from_position_key(cls, value: PositionKey) -> CapturePositionKey:
        return cls(capture=value.capture, position=value.position)


@dataclass(frozen=True, slots=True)
class SegmentationConfiguration:
    """Global automatic selection plus independent per-field overrides."""

    global_selection: SegmentationSelection = field(
        default_factory=lambda: SegmentationSelection(
            SegmentationMethodId.KMEANS,
            PROVISIONAL_WORKING_PROFILE,
        )
    )
    field_overrides: Mapping[CapturePositionKey, SegmentationSelection] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        normalized: dict[CapturePositionKey, SegmentationSelection] = {}
        for key, selection in self.field_overrides.items():
            if not isinstance(key, CapturePositionKey):
                raise TypeError("field override keys must be CapturePositionKey values")
            if not isinstance(selection, SegmentationSelection):
                raise TypeError("field overrides must contain SegmentationSelection values")
            normalized[key] = selection
        object.__setattr__(self, "field_overrides", MappingProxyType(normalized))

    def resolve(
        self,
        field_key: CapturePositionKey | PositionKey | None = None,
    ) -> ResolvedSegmentationSelection:
        normalized_key = _normalize_field_key(field_key)
        override = self.field_overrides.get(normalized_key) if normalized_key else None
        effective = override or self.global_selection
        return ResolvedSegmentationSelection(
            method=effective.method,
            profile=effective.profile,
            source=(
                SegmentationSelectionSource.CAPTURE_POSITION_OVERRIDE
                if override is not None
                else SegmentationSelectionSource.GLOBAL
            ),
            global_method=self.global_selection.method,
            global_profile=self.global_selection.profile,
            field_key=normalized_key,
            override_applied=override is not None,
        )


@dataclass(frozen=True, slots=True)
class ResolvedSegmentationSelection:
    """Effective choice with enough context to audit an applied override."""

    method: SegmentationMethodId
    profile: str
    source: SegmentationSelectionSource
    global_method: SegmentationMethodId
    global_profile: str
    field_key: CapturePositionKey | None
    override_applied: bool

    def __post_init__(self) -> None:
        _require_text(self.profile, "profile")
        _require_text(self.global_profile, "global_profile")
        if self.override_applied != (
            self.source is SegmentationSelectionSource.CAPTURE_POSITION_OVERRIDE
        ):
            raise ValueError("override_applied must agree with selection source")


@dataclass(frozen=True, slots=True)
class SegmentationSelectionProvenance:
    """Immutable selection and review provenance stored on configured results."""

    effective_method: SegmentationMethodId
    effective_profile: str
    source: SegmentationSelectionSource
    global_method: SegmentationMethodId
    global_profile: str
    override_applied: bool
    capture: str | None = None
    position: str | None = None
    review_status: SegmentationReviewStatus = SegmentationReviewStatus.UNREVIEWED
    manually_inspected: bool = False
    inspected_method: SegmentationMethodId | None = None
    inspected_profile: str | None = None
    global_approval_id: str | None = None
    approved_global_method: SegmentationMethodId | None = None
    approved_global_profile: str | None = None
    inspected_before_global_approval: tuple[CapturePositionKey, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.effective_profile, "effective_profile")
        _require_text(self.global_profile, "global_profile")
        if self.override_applied != (
            self.source is SegmentationSelectionSource.CAPTURE_POSITION_OVERRIDE
        ):
            raise ValueError("override_applied must agree with provenance source")
        if (self.capture is None) != (self.position is None):
            raise ValueError("capture and position provenance must be present together")
        if self.capture is not None:
            _require_text(self.capture, "capture")
            _require_text(self.position, "position")
        if not isinstance(self.review_status, SegmentationReviewStatus):
            raise TypeError("review_status must be a SegmentationReviewStatus")
        has_inspected_selection = (
            self.inspected_method is not None and self.inspected_profile is not None
        )
        if self.manually_inspected != has_inspected_selection:
            raise ValueError(
                "manually_inspected must agree with inspected method/profile provenance"
            )
        if self.inspected_profile is not None:
            _require_text(self.inspected_profile, "inspected_profile")
        approval_values = (
            self.global_approval_id,
            self.approved_global_method,
            self.approved_global_profile,
        )
        if any(value is not None for value in approval_values) != all(
            value is not None for value in approval_values
        ):
            raise ValueError(
                "global approval id, method, and profile provenance must be present "
                "together"
            )
        if self.global_approval_id is not None:
            _require_text(self.global_approval_id, "global_approval_id")
            _require_text(self.approved_global_profile, "approved_global_profile")
        expected_review_status = (
            SegmentationReviewStatus.EXPLICIT_OVERRIDE
            if self.override_applied
            else SegmentationReviewStatus.MANUALLY_REVIEWED
            if self.manually_inspected
            else SegmentationReviewStatus.GLOBAL_POLICY_ACCEPTED
            if self.global_approval_id is not None
            else SegmentationReviewStatus.UNREVIEWED
        )
        if self.review_status is not expected_review_status:
            raise ValueError(
                "review_status is incoherent with override, manual-inspection, and "
                f"global-approval provenance; expected "
                f"'{expected_review_status.value}'"
            )
        for key in self.inspected_before_global_approval:
            if not isinstance(key, CapturePositionKey):
                raise TypeError(
                    "inspected_before_global_approval must contain CapturePositionKey "
                    "values"
                )


def selection_provenance(
    resolved: ResolvedSegmentationSelection,
    field_review: SegmentationFieldReviewDecision | None = None,
) -> SegmentationSelectionProvenance:
    if field_review is not None and field_review.selection != resolved:
        raise ValueError(
            "field review decision does not match the resolved segmentation selection"
        )
    key = resolved.field_key
    inspection = field_review.inspection if field_review is not None else None
    approval = field_review.global_approval if field_review is not None else None
    review_status = (
        field_review.status
        if field_review is not None
        else SegmentationReviewStatus.EXPLICIT_OVERRIDE
        if resolved.override_applied
        else SegmentationReviewStatus.UNREVIEWED
    )
    return SegmentationSelectionProvenance(
        effective_method=resolved.method,
        effective_profile=resolved.profile,
        source=resolved.source,
        global_method=resolved.global_method,
        global_profile=resolved.global_profile,
        override_applied=resolved.override_applied,
        capture=key.capture if key else None,
        position=key.position if key else None,
        review_status=review_status,
        manually_inspected=inspection is not None,
        inspected_method=inspection.selection.method if inspection else None,
        inspected_profile=inspection.selection.profile if inspection else None,
        global_approval_id=approval.approval_id if approval else None,
        approved_global_method=(
            approval.approved_selection.method if approval else None
        ),
        approved_global_profile=(
            approval.approved_selection.profile if approval else None
        ),
        inspected_before_global_approval=(
            approval.inspected_fields if approval else ()
        ),
    )


def _normalize_field_key(
    value: CapturePositionKey | PositionKey | None,
) -> CapturePositionKey | None:
    if value is None or isinstance(value, CapturePositionKey):
        return value
    if isinstance(value, PositionKey):
        return CapturePositionKey.from_position_key(value)
    raise TypeError("field_key must be CapturePositionKey, PositionKey, or None")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
