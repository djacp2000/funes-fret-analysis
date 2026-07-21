"""Immutable, replayable backend contracts for Module 24 ROI mask revision."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

import numpy as np

from .contracts import PositionKey
from .roi_geometry import RoiFilteringResult
from .roi_review import roi_filtering_sha256, roi_label_sha256
from .segmentation_engine import SegmentationResult


ROI_REVISION_SCHEMA_VERSION = "funes.module24.roi_revision.v1"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_INT32_MAX = int(np.iinfo(np.int32).max)


class RoiRevisionError(ValueError):
    """A revision contract or deterministic replay is invalid or stale."""


class RoiRevisionOperationType(str, Enum):
    """The four explicit mask changes supported by the first backend block."""

    DELETE = "delete"
    REPLACE = "replace"
    ADD = "add"
    RESTORE = "restore"


class RoiRevisionFinalizationState(str, Enum):
    """Whether an immutable revision is still a draft or is analysis-eligible."""

    DRAFT = "draft"
    FINALIZED = "finalized"


@dataclass(frozen=True, slots=True, order=True)
class RoiPixel:
    """One zero-based pixel coordinate in a revised ROI support."""

    row: int
    col: int

    def __post_init__(self) -> None:
        _require_plain_int(self.row, "pixel row", minimum=0)
        _require_plain_int(self.col, "pixel col", minimum=0)


@dataclass(frozen=True, slots=True)
class RoiRevisionSourceIdentity:
    """Exact field and automatic Module 7/8 identity bound by a revision."""

    experiment: str
    capture: str
    position: str
    image_shape: tuple[int, int]
    module7_source_label_sha256: str
    module8_filtering_sha256: str

    def __post_init__(self) -> None:
        for name, value in (
            ("experiment", self.experiment),
            ("capture", self.capture),
            ("position", self.position),
        ):
            _require_text(value, name)
        shape = tuple(self.image_shape)
        if len(shape) != 2:
            raise RoiRevisionError("image_shape must contain exactly height and width")
        for value in shape:
            _require_plain_int(value, "image_shape value", minimum=1)
        object.__setattr__(self, "image_shape", shape)
        _require_sha256(
            self.module7_source_label_sha256,
            "module7_source_label_sha256",
        )
        _require_sha256(self.module8_filtering_sha256, "module8_filtering_sha256")

    @property
    def position_key(self) -> PositionKey:
        """Return the exact Experiment > Capture > Position scope."""

        return PositionKey(self.capture, self.position, self.experiment)

    @classmethod
    def from_automatic_results(
        cls,
        position_key: PositionKey,
        segmentation: SegmentationResult,
        filtering: RoiFilteringResult,
    ) -> "RoiRevisionSourceIdentity":
        """Bind one exact automatic Module 7/8 result without changing it."""

        _validate_automatic_results(segmentation, filtering)
        if not isinstance(position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if position_key.experiment is None:
            raise RoiRevisionError(
                "Module 24 source identity requires an explicit experiment"
            )
        return cls(
            experiment=position_key.experiment,
            capture=position_key.capture,
            position=position_key.position,
            image_shape=tuple(int(value) for value in segmentation.label_image.shape),
            module7_source_label_sha256=roi_label_sha256(
                segmentation.label_image
            ),
            module8_filtering_sha256=roi_filtering_sha256(filtering),
        )


@dataclass(frozen=True, slots=True)
class RoiRevisionOperation:
    """One ordered, reasoned edit sufficient for deterministic replay."""

    operation_type: RoiRevisionOperationType
    label: int
    pixels: tuple[RoiPixel, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        try:
            operation_type = RoiRevisionOperationType(self.operation_type)
        except ValueError as exc:
            raise RoiRevisionError(
                f"unsupported ROI revision operation: {self.operation_type!r}"
            ) from exc
        object.__setattr__(self, "operation_type", operation_type)
        _require_plain_int(self.label, "operation label", minimum=1, maximum=_INT32_MAX)
        _require_text(self.reason, "operation reason")
        pixels = tuple(self.pixels)
        if not all(isinstance(pixel, RoiPixel) for pixel in pixels):
            raise TypeError("operation pixels must contain only RoiPixel values")
        if len(set(pixels)) != len(pixels):
            raise RoiRevisionError("operation pixel support contains duplicates")
        pixels = tuple(sorted(pixels))
        needs_pixels = operation_type in (
            RoiRevisionOperationType.REPLACE,
            RoiRevisionOperationType.ADD,
        )
        if needs_pixels and not pixels:
            raise RoiRevisionError(
                f"{operation_type.value} operation requires a non-empty pixel support"
            )
        if not needs_pixels and pixels:
            raise RoiRevisionError(
                f"{operation_type.value} operation must not include a pixel support"
            )
        object.__setattr__(self, "pixels", pixels)

    @classmethod
    def delete(cls, label: int, *, reason: str) -> "RoiRevisionOperation":
        return cls(RoiRevisionOperationType.DELETE, label, reason=reason)

    @classmethod
    def replace(
        cls,
        label: int,
        pixels: tuple[RoiPixel | tuple[int, int], ...],
        *,
        reason: str,
    ) -> "RoiRevisionOperation":
        return cls(
            RoiRevisionOperationType.REPLACE,
            label,
            _coerce_pixels(pixels),
            reason,
        )

    @classmethod
    def add(
        cls,
        label: int,
        pixels: tuple[RoiPixel | tuple[int, int], ...],
        *,
        reason: str,
    ) -> "RoiRevisionOperation":
        return cls(
            RoiRevisionOperationType.ADD,
            label,
            _coerce_pixels(pixels),
            reason,
        )

    @classmethod
    def restore(cls, label: int, *, reason: str) -> "RoiRevisionOperation":
        return cls(RoiRevisionOperationType.RESTORE, label, reason=reason)


@dataclass(frozen=True, slots=True)
class RoiMaskRevision:
    """One immutable ordered revision, optionally awaiting finalization."""

    source: RoiRevisionSourceIdentity
    operations: tuple[RoiRevisionOperation, ...]
    editor: str
    finalized_at: str | None = None
    parent_revision_sha256: str | None = None
    schema_version: str = ROI_REVISION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ROI_REVISION_SCHEMA_VERSION:
            raise RoiRevisionError(
                f"unsupported ROI revision schema_version: {self.schema_version!r}"
            )
        if not isinstance(self.source, RoiRevisionSourceIdentity):
            raise TypeError("source must be a RoiRevisionSourceIdentity")
        operations = tuple(self.operations)
        if not operations:
            raise RoiRevisionError("ROI revision must contain at least one operation")
        if not all(isinstance(operation, RoiRevisionOperation) for operation in operations):
            raise TypeError("operations must contain only RoiRevisionOperation values")
        object.__setattr__(self, "operations", operations)
        _require_text(self.editor, "editor")
        if self.finalized_at is not None:
            _require_finalization_time(self.finalized_at)
        if self.parent_revision_sha256 is not None:
            _require_sha256(
                self.parent_revision_sha256,
                "parent_revision_sha256",
            )

    @property
    def finalization_state(self) -> RoiRevisionFinalizationState:
        return (
            RoiRevisionFinalizationState.FINALIZED
            if self.finalized_at is not None
            else RoiRevisionFinalizationState.DRAFT
        )

    @property
    def sha256(self) -> str:
        return roi_revision_sha256(self)


def finalize_roi_revision(
    revision: RoiMaskRevision,
    *,
    finalized_at: str,
) -> RoiMaskRevision:
    """Return a finalized immutable copy; never mutate or auto-time a draft."""

    if not isinstance(revision, RoiMaskRevision):
        raise TypeError("revision must be a RoiMaskRevision")
    if revision.finalization_state is RoiRevisionFinalizationState.FINALIZED:
        raise RoiRevisionError("ROI revision is already finalized")
    _require_finalization_time(finalized_at)
    return replace(revision, finalized_at=finalized_at)


@dataclass(frozen=True, slots=True)
class RoiRevisionTraceEntry:
    """Input/output mask hashes for one operation in a replay chain."""

    revision_sha256: str
    operation_index: int
    operation: RoiRevisionOperation
    input_label_sha256: str
    output_label_sha256: str

    def __post_init__(self) -> None:
        _require_sha256(self.revision_sha256, "trace revision_sha256")
        _require_plain_int(self.operation_index, "operation_index", minimum=0)
        if not isinstance(self.operation, RoiRevisionOperation):
            raise TypeError("trace operation must be a RoiRevisionOperation")
        _require_sha256(self.input_label_sha256, "trace input_label_sha256")
        _require_sha256(self.output_label_sha256, "trace output_label_sha256")
        if self.input_label_sha256 == self.output_label_sha256:
            raise RoiRevisionError("every traced operation must change the label image")


def roi_revision_sha256(revision: RoiMaskRevision) -> str:
    """Return a domain-separated canonical identity for one ordered revision."""

    if not isinstance(revision, RoiMaskRevision):
        raise TypeError("revision must be a RoiMaskRevision")
    canonical = json.dumps(
        _revision_hash_payload(revision),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(b"funes-module24-roi-revision-v1\0" + canonical).hexdigest()


def _validate_automatic_results(
    segmentation: SegmentationResult,
    filtering: RoiFilteringResult,
) -> None:
    if not isinstance(segmentation, SegmentationResult):
        raise TypeError("segmentation must be a SegmentationResult")
    if not isinstance(filtering, RoiFilteringResult):
        raise TypeError("filtering must be a RoiFilteringResult")
    if filtering.source_segmentation is not segmentation:
        raise RoiRevisionError(
            "Module 24 requires Module 8 to retain the exact source SegmentationResult"
        )
    if not np.array_equal(filtering.source_label_image, segmentation.label_image):
        raise RoiRevisionError("Module 8 source mask does not match Module 7")


def _coerce_pixels(
    pixels: tuple[RoiPixel | tuple[int, int], ...],
) -> tuple[RoiPixel, ...]:
    converted: list[RoiPixel] = []
    for value in pixels:
        if isinstance(value, RoiPixel):
            converted.append(value)
        elif isinstance(value, tuple) and len(value) == 2:
            converted.append(RoiPixel(value[0], value[1]))
        else:
            raise TypeError("pixels must contain RoiPixel or (row, col) tuples")
    return tuple(converted)


def _source_payload(source: RoiRevisionSourceIdentity) -> dict[str, object]:
    return {
        "experiment": source.experiment,
        "capture": source.capture,
        "position": source.position,
        "image_shape": list(source.image_shape),
        "module7_source_label_sha256": source.module7_source_label_sha256,
        "module8_filtering_sha256": source.module8_filtering_sha256,
    }


def _operation_payload(operation: RoiRevisionOperation) -> dict[str, object]:
    return {
        "operation_type": operation.operation_type.value,
        "label": operation.label,
        "pixels": [
            {"row": pixel.row, "col": pixel.col} for pixel in operation.pixels
        ],
        "reason": operation.reason,
    }


def _revision_hash_payload(revision: RoiMaskRevision) -> dict[str, object]:
    return {
        "schema_version": revision.schema_version,
        "source": _source_payload(revision.source),
        "operations": [
            _operation_payload(operation) for operation in revision.operations
        ],
        "editor": revision.editor,
        "finalized_at": revision.finalized_at,
        "parent_revision_sha256": revision.parent_revision_sha256,
    }


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RoiRevisionError(f"{name} must be non-empty text")


def _require_plain_int(
    value: object,
    name: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> None:
    if type(value) is not int or value < minimum or (
        maximum is not None and value > maximum
    ):
        boundary = f"{minimum}..{maximum}" if maximum is not None else f">= {minimum}"
        raise RoiRevisionError(f"{name} must be an integer in {boundary}")


def _require_sha256(value: object, name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise RoiRevisionError(f"{name} must be a lowercase SHA-256 value")


def _require_finalization_time(value: object) -> None:
    _require_text(value, "finalized_at")
    assert isinstance(value, str)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RoiRevisionError(
            "finalized_at must be an ISO-8601 timestamp with a timezone"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RoiRevisionError(
            "finalized_at must be an ISO-8601 timestamp with a timezone"
        )
