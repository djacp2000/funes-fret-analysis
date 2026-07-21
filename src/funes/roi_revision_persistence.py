"""Strict JSON persistence for finalized Module 24 ROI mask revisions."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import PositionKey
from .roi_revision import (
    ROI_REVISION_SCHEMA_VERSION,
    RoiMaskRevision,
    RoiPixel,
    RoiRevisionError,
    RoiRevisionFinalizationState,
    RoiRevisionOperation,
    RoiRevisionOperationType,
    RoiRevisionSourceIdentity,
    _operation_payload,
    _revision_hash_payload,
    _source_payload,
)
from .roi_revision_replay import RoiRevisionResult, replay_roi_revision
from .segmentation_engine import SegmentationResult
from .roi_geometry import RoiFilteringResult


ROI_REVISION_ARTIFACT_SCHEMA = "funes.module24.roi_revision_artifact.v1"
_ARTIFACT_DOMAIN = b"funes-module24-roi-revision-artifact-v1\0"


class RoiRevisionArtifactError(RoiRevisionError):
    """A persisted Module 24 artifact is unreadable, altered, or incoherent."""


@dataclass(frozen=True, slots=True)
class RoiRevisionArtifactWriteResult:
    """Identity of one successfully persisted finalized revision artifact."""

    path: Path
    sha256: str
    revision_sha256: str


def export_roi_revision_artifact(
    result: RoiRevisionResult,
    output_path: Path | str,
) -> RoiRevisionArtifactWriteResult:
    """Persist one finalized replay result without changing review state."""

    if not isinstance(result, RoiRevisionResult):
        raise TypeError("result must be a RoiRevisionResult")
    if result.finalization_state is not RoiRevisionFinalizationState.FINALIZED:
        raise RoiRevisionArtifactError("only finalized ROI revisions may be persisted")
    destination = Path(output_path)
    if destination.suffix.casefold() != ".json":
        raise ValueError("ROI revision artifacts require a .json output path")

    payload = {
        "revision": _persisted_revision_payload(result.revision),
        "result": _result_payload(result),
    }
    document = {
        "schema": ROI_REVISION_ARTIFACT_SCHEMA,
        "payload_sha256": roi_revision_artifact_payload_sha256(payload),
        **payload,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        document,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    destination.write_text(rendered, encoding="utf-8", newline="\n")
    return RoiRevisionArtifactWriteResult(
        path=destination,
        sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        revision_sha256=result.revision_sha256,
    )


def load_roi_revision_artifact(
    input_path: Path | str,
    segmentation: SegmentationResult,
    filtering: RoiFilteringResult,
    position_key: PositionKey,
    *,
    parent_result: RoiRevisionResult | None = None,
) -> RoiRevisionResult:
    """Strictly load, reconstruct, replay, and verify a finalized artifact."""

    source = Path(input_path)
    try:
        raw = _load_strict_json(source)
        document = _mapping(raw, "artifact")
        _exact_keys(
            document,
            {"schema", "payload_sha256", "revision", "result"},
            "artifact",
        )
        schema = _text(document["schema"], "artifact.schema")
        if schema != ROI_REVISION_ARTIFACT_SCHEMA:
            raise RoiRevisionArtifactError(
                f"unsupported ROI revision artifact schema: {schema!r}"
            )
        stored_checksum = _sha256(
            document["payload_sha256"], "artifact.payload_sha256"
        )
        raw_payload = {
            "revision": document["revision"],
            "result": document["result"],
        }
        expected_checksum = roi_revision_artifact_payload_sha256(raw_payload)
        if not hmac.compare_digest(stored_checksum, expected_checksum):
            raise RoiRevisionArtifactError(
                "ROI revision artifact payload SHA-256 does not match; the file "
                "is incomplete or has changed"
            )

        revision = _parse_revision(document["revision"], "artifact.revision")
        replayed = replay_roi_revision(
            revision,
            segmentation,
            filtering,
            position_key,
            parent_result=parent_result,
        )
        expected_revision = _persisted_revision_payload(replayed.revision)
        expected_result = _result_payload(replayed)
        if not _exact_json_equal(document["revision"], expected_revision):
            raise RoiRevisionArtifactError(
                "persisted revision does not match its canonical reconstruction"
            )
        if not _exact_json_equal(document["result"], expected_result):
            raise RoiRevisionArtifactError(
                "persisted masks or audit do not match deterministic replay"
            )
        return replayed
    except RoiRevisionArtifactError:
        raise
    except RoiRevisionError as exc:
        raise RoiRevisionArtifactError(
            f"incoherent ROI revision artifact {source}: {exc}"
        ) from exc
    except (TypeError, ValueError) as exc:
        raise RoiRevisionArtifactError(
            f"incoherent ROI revision artifact {source}: {exc}"
        ) from exc


def roi_revision_artifact_payload_sha256(payload: object) -> str:
    """Hash the exact revision/result payload for strict integrity validation."""

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(_ARTIFACT_DOMAIN + canonical).hexdigest()


def _persisted_revision_payload(revision: RoiMaskRevision) -> dict[str, object]:
    return {**_revision_hash_payload(revision), "revision_sha256": revision.sha256}


def _result_payload(result: RoiRevisionResult) -> dict[str, object]:
    geometry = result.geometry_audit
    return {
        "finalization_state": result.finalization_state.value,
        "input_label_sha256": result.input_label_sha256,
        "edited_label_sha256": result.edited_label_sha256,
        "measurement_label_sha256": result.measurement_label_sha256,
        "revision_sha256": result.revision_sha256,
        "edited_label_image": result.edited_label_image.tolist(),
        "measurement_label_image": result.measurement_label_image.tolist(),
        "operation_trace": [
            {
                "revision_sha256": entry.revision_sha256,
                "operation_index": entry.operation_index,
                "operation": _operation_payload(entry.operation),
                "input_label_sha256": entry.input_label_sha256,
                "output_label_sha256": entry.output_label_sha256,
            }
            for entry in result.operation_trace
        ],
        "geometry_audit": {
            "config": {
                "min_area_pixels": geometry.config.min_area_pixels,
                "max_area_pixels": geometry.config.max_area_pixels,
                "border_policy": geometry.config.border_policy.value,
            },
            "records": [
                {
                    "label": record.geometry.label,
                    "area_pixels": record.geometry.area_pixels,
                    "bounding_box": {
                        "min_row": record.geometry.bounding_box.min_row,
                        "min_col": record.geometry.bounding_box.min_col,
                        "max_row": record.geometry.bounding_box.max_row,
                        "max_col": record.geometry.bounding_box.max_col,
                    },
                    "centroid_row": record.geometry.centroid_row,
                    "centroid_col": record.geometry.centroid_col,
                    "touches_border": record.geometry.touches_border,
                    "status": record.status.value,
                    "reasons": list(record.reasons),
                }
                for record in geometry.records
            ],
            "issues": [
                {
                    "code": issue.code,
                    "message": issue.message,
                    "severity": issue.severity.value,
                    "context": dict(issue.context),
                }
                for issue in geometry.issues
            ],
        },
    }


def _parse_revision(value: object, context: str) -> RoiMaskRevision:
    raw = _mapping(value, context)
    _exact_keys(
        raw,
        {
            "schema_version",
            "source",
            "operations",
            "editor",
            "finalized_at",
            "parent_revision_sha256",
            "revision_sha256",
        },
        context,
    )
    schema_version = _text(raw["schema_version"], f"{context}.schema_version")
    if schema_version != ROI_REVISION_SCHEMA_VERSION:
        raise RoiRevisionArtifactError(
            f"unsupported ROI revision schema_version: {schema_version!r}"
        )
    source = _parse_source(raw["source"], f"{context}.source")
    operations_raw = _list(raw["operations"], f"{context}.operations")
    operations = tuple(
        _parse_operation(operation, f"{context}.operations[{index}]")
        for index, operation in enumerate(operations_raw)
    )
    finalized_value = raw["finalized_at"]
    finalized_at = (
        None
        if finalized_value is None
        else _text(finalized_value, f"{context}.finalized_at")
    )
    parent_value = raw["parent_revision_sha256"]
    parent = (
        None
        if parent_value is None
        else _sha256(parent_value, f"{context}.parent_revision_sha256")
    )
    revision = RoiMaskRevision(
        source=source,
        operations=operations,
        editor=_text(raw["editor"], f"{context}.editor"),
        finalized_at=finalized_at,
        parent_revision_sha256=parent,
        schema_version=schema_version,
    )
    stored_hash = _sha256(raw["revision_sha256"], f"{context}.revision_sha256")
    if not hmac.compare_digest(stored_hash, revision.sha256):
        raise RoiRevisionArtifactError(
            "persisted revision SHA-256 does not match its canonical content"
        )
    return revision


def _parse_source(value: object, context: str) -> RoiRevisionSourceIdentity:
    raw = _mapping(value, context)
    _exact_keys(
        raw,
        {
            "experiment",
            "capture",
            "position",
            "image_shape",
            "module7_source_label_sha256",
            "module8_filtering_sha256",
        },
        context,
    )
    shape = _list(raw["image_shape"], f"{context}.image_shape")
    if len(shape) != 2:
        raise RoiRevisionArtifactError(
            f"{context}.image_shape must contain exactly two integers"
        )
    return RoiRevisionSourceIdentity(
        experiment=_text(raw["experiment"], f"{context}.experiment"),
        capture=_text(raw["capture"], f"{context}.capture"),
        position=_text(raw["position"], f"{context}.position"),
        image_shape=(
            _integer(shape[0], f"{context}.image_shape[0]"),
            _integer(shape[1], f"{context}.image_shape[1]"),
        ),
        module7_source_label_sha256=_sha256(
            raw["module7_source_label_sha256"],
            f"{context}.module7_source_label_sha256",
        ),
        module8_filtering_sha256=_sha256(
            raw["module8_filtering_sha256"],
            f"{context}.module8_filtering_sha256",
        ),
    )


def _parse_operation(value: object, context: str) -> RoiRevisionOperation:
    raw = _mapping(value, context)
    _exact_keys(raw, {"operation_type", "label", "pixels", "reason"}, context)
    try:
        operation_type = RoiRevisionOperationType(
            _text(raw["operation_type"], f"{context}.operation_type")
        )
    except ValueError as exc:
        raise RoiRevisionArtifactError(
            f"{context}.operation_type is unknown: {raw['operation_type']!r}"
        ) from exc
    pixels = tuple(
        _parse_pixel(pixel, f"{context}.pixels[{index}]")
        for index, pixel in enumerate(_list(raw["pixels"], f"{context}.pixels"))
    )
    return RoiRevisionOperation(
        operation_type=operation_type,
        label=_integer(raw["label"], f"{context}.label"),
        pixels=pixels,
        reason=_text(raw["reason"], f"{context}.reason"),
    )


def _parse_pixel(value: object, context: str) -> RoiPixel:
    raw = _mapping(value, context)
    _exact_keys(raw, {"row", "col"}, context)
    return RoiPixel(
        _integer(raw["row"], f"{context}.row"),
        _integer(raw["col"], f"{context}.col"),
    )


def _load_strict_json(path: Path) -> object:
    def reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise RoiRevisionArtifactError(
                    f"ROI revision artifact contains duplicate JSON field {key!r}"
                )
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise RoiRevisionArtifactError(
            f"ROI revision artifact contains non-standard JSON number {value}"
        )

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RoiRevisionArtifactError(
            f"cannot read ROI revision artifact {path}: {exc}"
        ) from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise RoiRevisionArtifactError(
            f"invalid ROI revision artifact JSON in {path}: {exc}"
        ) from exc


def _mapping(value: object, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise RoiRevisionArtifactError(f"{context} must be a JSON object")
    return value


def _list(value: object, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise RoiRevisionArtifactError(f"{context} must be a JSON array")
    return value


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoiRevisionArtifactError(f"{context} must be a non-empty string")
    return value


def _sha256(value: object, context: str) -> str:
    text = _text(value, context)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise RoiRevisionArtifactError(f"{context} must be a lowercase SHA-256 value")
    return text


def _integer(value: object, context: str) -> int:
    if type(value) is not int:
        raise RoiRevisionArtifactError(f"{context} must be an integer")
    return value


def _exact_keys(
    value: Mapping[str, Any], expected: set[str], context: str
) -> None:
    actual = set(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    details: list[str] = []
    if missing:
        details.append(f"missing {missing}")
    if unknown:
        details.append(f"unknown {unknown}")
    raise RoiRevisionArtifactError(
        f"{context} has invalid fields ({'; '.join(details)})"
    )


def _exact_json_equal(actual: object, expected: object) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        return set(actual) == set(expected) and all(
            _exact_json_equal(actual[key], expected[key]) for key in expected
        )
    if isinstance(expected, list):
        assert isinstance(actual, list)
        return len(actual) == len(expected) and all(
            _exact_json_equal(left, right)
            for left, right in zip(actual, expected)
        )
    return actual == expected
