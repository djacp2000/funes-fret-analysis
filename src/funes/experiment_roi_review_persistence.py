"""Versioned persistence for the experiment-scoped Module 9 review state."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import PositionKey
from .experiment_roi_review import (
    ExperimentPositionReview,
    ExperimentPositionReviewMode,
    ExperimentRoiReviewOrchestrator,
)
from .segmentation_review import (
    GlobalSegmentationApproval,
    SegmentationFieldInspection,
    SegmentationReviewState,
)
from .segmentation_selection import (
    CapturePositionKey,
    SegmentationConfiguration,
    SegmentationMethodId,
    SegmentationSelection,
    SegmentationSelectionSource,
)


EXPERIMENT_ROI_REVIEW_SNAPSHOT_SCHEMA = (
    "funes.module9.experiment_roi_review.v1"
)


class ExperimentRoiReviewSnapshotError(ValueError):
    """A persisted Module 9 review snapshot is unreadable or incoherent."""


@dataclass(frozen=True, slots=True)
class ExperimentRoiReviewSnapshotResult:
    """Audit details for one successfully written review snapshot."""

    path: Path
    sha256: str
    experiment_count: int


def export_experiment_roi_review_snapshot(
    orchestrator: ExperimentRoiReviewOrchestrator,
    output_path: Path | str,
) -> ExperimentRoiReviewSnapshotResult:
    """Persist all isolated ledgers without changing their review state."""

    if not isinstance(orchestrator, ExperimentRoiReviewOrchestrator):
        raise TypeError("orchestrator must be an ExperimentRoiReviewOrchestrator")
    destination = Path(output_path)
    if destination.suffix.casefold() != ".json":
        raise ValueError("experiment ROI review snapshots require a .json output path")

    experiments = [_experiment_payload(item) for item in orchestrator.experiments]
    payload_sha256 = _payload_sha256(experiments)
    document = {
        "schema": EXPERIMENT_ROI_REVIEW_SNAPSHOT_SCHEMA,
        "payload_sha256": payload_sha256,
        "experiments": experiments,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        document, indent=2, sort_keys=True, ensure_ascii=False
    ) + "\n"
    destination.write_text(rendered, encoding="utf-8")
    return ExperimentRoiReviewSnapshotResult(
        path=destination,
        sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        experiment_count=len(experiments),
    )


def load_experiment_roi_review_snapshot(
    input_path: Path | str,
) -> ExperimentRoiReviewOrchestrator:
    """Restore isolated ledgers after strict schema and integrity validation."""

    source = Path(input_path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ExperimentRoiReviewSnapshotError(
            f"cannot read experiment ROI review snapshot {source}: {exc}"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExperimentRoiReviewSnapshotError(
            f"invalid experiment ROI review snapshot JSON in {source}: {exc}"
        ) from exc

    try:
        document = _mapping(raw, "snapshot")
        _exact_keys(document, {"schema", "payload_sha256", "experiments"}, "snapshot")
        schema = _text(document["schema"], "snapshot.schema")
        if schema != EXPERIMENT_ROI_REVIEW_SNAPSHOT_SCHEMA:
            raise ExperimentRoiReviewSnapshotError(
                f"unsupported experiment ROI review snapshot schema: {schema!r}"
            )
        checksum = _text(document["payload_sha256"], "snapshot.payload_sha256")
        experiments_raw = _list(document["experiments"], "snapshot.experiments")
        expected = _payload_sha256(experiments_raw)
        if not hmac.compare_digest(checksum, expected):
            raise ExperimentRoiReviewSnapshotError(
                "experiment ROI review snapshot payload SHA-256 does not match; "
                "the file is incomplete or has changed"
            )
        experiments = tuple(
            _parse_experiment(value, f"snapshot.experiments[{index}]")
            for index, value in enumerate(experiments_raw)
        )
        return ExperimentRoiReviewOrchestrator(experiments)
    except ExperimentRoiReviewSnapshotError:
        raise
    except (TypeError, ValueError) as exc:
        raise ExperimentRoiReviewSnapshotError(
            f"incoherent experiment ROI review snapshot {source}: {exc}"
        ) from exc


def _experiment_payload(review: ExperimentPositionReview) -> dict[str, Any]:
    return {
        "experiment": review.experiment,
        "positions": [_position_payload(key) for key in review.positions],
        "mode": review.mode.value,
        "selected_positions": [
            _position_payload(key) for key in review.selected_positions
        ],
        "review_state": _review_state_payload(review.review_state),
    }


def _review_state_payload(state: SegmentationReviewState) -> dict[str, Any]:
    overrides = [
        {"field": _field_payload(key), "selection": _selection_payload(selection)}
        for key, selection in state.configuration.field_overrides.items()
    ]
    return {
        "configuration": {
            "global_selection": _selection_payload(
                state.configuration.global_selection
            ),
            "field_overrides": overrides,
        },
        "inspections": [_inspection_payload(item) for item in state.inspections],
        "global_approval": (
            _approval_payload(state.global_approval)
            if state.global_approval is not None
            else None
        ),
    }


def _position_payload(key: PositionKey) -> dict[str, str]:
    return {"capture": key.capture, "position": key.position}


def _field_payload(key: CapturePositionKey) -> dict[str, str]:
    return {"capture": key.capture, "position": key.position}


def _selection_payload(selection: SegmentationSelection) -> dict[str, str]:
    return {"method": selection.method.value, "profile": selection.profile}


def _inspection_payload(inspection: SegmentationFieldInspection) -> dict[str, Any]:
    return {
        "field": _field_payload(inspection.field_key),
        "selection": _selection_payload(inspection.selection),
        "selection_source": inspection.selection_source.value,
        "inspector": inspection.inspector,
        "inspected_at": inspection.inspected_at,
        "note": inspection.note,
    }


def _approval_payload(approval: GlobalSegmentationApproval) -> dict[str, Any]:
    return {
        "approval_id": approval.approval_id,
        "approved_selection": _selection_payload(approval.approved_selection),
        "inspections_before_approval": [
            _inspection_payload(item)
            for item in approval.inspections_before_approval
        ],
        "approved_by": approval.approved_by,
        "approved_at": approval.approved_at,
        "note": approval.note,
    }


def _parse_experiment(value: object, context: str) -> ExperimentPositionReview:
    raw = _mapping(value, context)
    _exact_keys(
        raw,
        {"experiment", "positions", "mode", "selected_positions", "review_state"},
        context,
    )
    experiment = _text(raw["experiment"], f"{context}.experiment")
    positions = tuple(
        _parse_position(item, experiment, f"{context}.positions[{index}]")
        for index, item in enumerate(_list(raw["positions"], f"{context}.positions"))
    )
    selected = tuple(
        _parse_position(
            item, experiment, f"{context}.selected_positions[{index}]"
        )
        for index, item in enumerate(
            _list(raw["selected_positions"], f"{context}.selected_positions")
        )
    )
    try:
        mode = ExperimentPositionReviewMode(
            _text(raw["mode"], f"{context}.mode")
        )
    except ValueError as exc:
        raise ExperimentRoiReviewSnapshotError(
            f"{context}.mode has an unknown value: {raw['mode']!r}"
        ) from exc
    return ExperimentPositionReview(
        experiment=experiment,
        positions=positions,
        mode=mode,
        selected_positions=selected,
        review_state=_parse_review_state(raw["review_state"], f"{context}.review_state"),
    )


def _parse_review_state(value: object, context: str) -> SegmentationReviewState:
    raw = _mapping(value, context)
    _exact_keys(raw, {"configuration", "inspections", "global_approval"}, context)
    configuration = _parse_configuration(
        raw["configuration"], f"{context}.configuration"
    )
    inspections = tuple(
        _parse_inspection(item, f"{context}.inspections[{index}]")
        for index, item in enumerate(
            _list(raw["inspections"], f"{context}.inspections")
        )
    )
    approval_raw = raw["global_approval"]
    approval = (
        None
        if approval_raw is None
        else _parse_approval(approval_raw, f"{context}.global_approval")
    )
    return SegmentationReviewState(configuration, inspections, approval)


def _parse_configuration(value: object, context: str) -> SegmentationConfiguration:
    raw = _mapping(value, context)
    _exact_keys(raw, {"global_selection", "field_overrides"}, context)
    overrides: dict[CapturePositionKey, SegmentationSelection] = {}
    for index, item in enumerate(
        _list(raw["field_overrides"], f"{context}.field_overrides")
    ):
        item_context = f"{context}.field_overrides[{index}]"
        override = _mapping(item, item_context)
        _exact_keys(override, {"field", "selection"}, item_context)
        key = _parse_field(override["field"], f"{item_context}.field")
        if key in overrides:
            raise ExperimentRoiReviewSnapshotError(
                f"{context}.field_overrides contains duplicate fields"
            )
        overrides[key] = _parse_selection(
            override["selection"], f"{item_context}.selection"
        )
    return SegmentationConfiguration(
        global_selection=_parse_selection(
            raw["global_selection"], f"{context}.global_selection"
        ),
        field_overrides=overrides,
    )


def _parse_inspection(value: object, context: str) -> SegmentationFieldInspection:
    raw = _mapping(value, context)
    _exact_keys(
        raw,
        {
            "field",
            "selection",
            "selection_source",
            "inspector",
            "inspected_at",
            "note",
        },
        context,
    )
    try:
        source = SegmentationSelectionSource(
            _text(raw["selection_source"], f"{context}.selection_source")
        )
    except ValueError as exc:
        raise ExperimentRoiReviewSnapshotError(
            f"{context}.selection_source has an unknown value: "
            f"{raw['selection_source']!r}"
        ) from exc
    return SegmentationFieldInspection(
        field_key=_parse_field(raw["field"], f"{context}.field"),
        selection=_parse_selection(raw["selection"], f"{context}.selection"),
        selection_source=source,
        inspector=_optional_text(raw["inspector"], f"{context}.inspector"),
        inspected_at=_optional_text(
            raw["inspected_at"], f"{context}.inspected_at"
        ),
        note=_optional_text(raw["note"], f"{context}.note"),
    )


def _parse_approval(value: object, context: str) -> GlobalSegmentationApproval:
    raw = _mapping(value, context)
    _exact_keys(
        raw,
        {
            "approval_id",
            "approved_selection",
            "inspections_before_approval",
            "approved_by",
            "approved_at",
            "note",
        },
        context,
    )
    snapshot = tuple(
        _parse_inspection(item, f"{context}.inspections_before_approval[{index}]")
        for index, item in enumerate(
            _list(
                raw["inspections_before_approval"],
                f"{context}.inspections_before_approval",
            )
        )
    )
    return GlobalSegmentationApproval(
        approval_id=_text(raw["approval_id"], f"{context}.approval_id"),
        approved_selection=_parse_selection(
            raw["approved_selection"], f"{context}.approved_selection"
        ),
        inspections_before_approval=snapshot,
        approved_by=_optional_text(raw["approved_by"], f"{context}.approved_by"),
        approved_at=_optional_text(raw["approved_at"], f"{context}.approved_at"),
        note=_optional_text(raw["note"], f"{context}.note"),
    )


def _parse_position(value: object, experiment: str, context: str) -> PositionKey:
    field = _parse_field(value, context)
    return PositionKey(field.capture, field.position, experiment)


def _parse_field(value: object, context: str) -> CapturePositionKey:
    raw = _mapping(value, context)
    _exact_keys(raw, {"capture", "position"}, context)
    return CapturePositionKey(
        _text(raw["capture"], f"{context}.capture"),
        _text(raw["position"], f"{context}.position"),
    )


def _parse_selection(value: object, context: str) -> SegmentationSelection:
    raw = _mapping(value, context)
    _exact_keys(raw, {"method", "profile"}, context)
    try:
        method = SegmentationMethodId(_text(raw["method"], f"{context}.method"))
    except ValueError as exc:
        raise ExperimentRoiReviewSnapshotError(
            f"{context}.method has an unknown value: {raw['method']!r}"
        ) from exc
    return SegmentationSelection(method, _text(raw["profile"], f"{context}.profile"))


def _payload_sha256(experiments: object) -> str:
    canonical = json.dumps(
        {
            "schema": EXPERIMENT_ROI_REVIEW_SNAPSHOT_SCHEMA,
            "experiments": experiments,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(b"funes-module9-experiment-review-v1\0" + canonical).hexdigest()


def _mapping(value: object, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise ExperimentRoiReviewSnapshotError(f"{context} must be a JSON object")
    return value


def _list(value: object, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise ExperimentRoiReviewSnapshotError(f"{context} must be a JSON array")
    return value


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExperimentRoiReviewSnapshotError(
            f"{context} must be a non-empty string"
        )
    return value


def _optional_text(value: object, context: str) -> str | None:
    if value is None:
        return None
    return _text(value, context)


def _exact_keys(
    value: Mapping[str, Any], expected: set[str], context: str
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        details: list[str] = []
        if missing:
            details.append(f"missing {missing}")
        if unknown:
            details.append(f"unknown {unknown}")
        raise ExperimentRoiReviewSnapshotError(
            f"{context} has invalid fields ({'; '.join(details)})"
        )
