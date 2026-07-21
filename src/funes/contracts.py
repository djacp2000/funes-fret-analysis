"""Shared typed contracts used across FUNES modules.

These models describe identifiers, source provenance, frame references, and
structured issues. They intentionally do not read images, parse filenames,
segment cells, or perform scientific calculations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

MetadataValue = str | int | float | bool | None


class Channel(str, Enum):
    """Supported two-channel acquisition labels."""

    C0 = "C0"
    C1 = "C1"


class IssueSeverity(str, Enum):
    """Severity for warnings and errors that should be preserved downstream."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PositionKey:
    """Identifier for one Experiment > Capture > Position acquisition site."""

    capture: str
    position: str
    experiment: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.capture, "capture")
        _require_text(self.position, "position")
        if self.experiment is not None:
            _require_text(self.experiment, "experiment")


@dataclass(frozen=True, slots=True)
class ChannelKey:
    """Identifier for one channel within a capture/position site."""

    position_key: PositionKey
    channel: Channel


@dataclass(frozen=True, slots=True)
class FrameReference:
    """Reference to a temporal frame after TIFF axis normalization."""

    frame_index: int
    time_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValueError("frame_index must be zero or greater")
        if self.time_seconds is not None and self.time_seconds < 0:
            raise ValueError("time_seconds must be zero or greater when present")


@dataclass(frozen=True, slots=True)
class SourceFile:
    """Provenance for an input file without reading or modifying its contents."""

    path: Path
    original_name: str
    metadata: Mapping[str, MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.original_name, "original_name")
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class PipelineIssue:
    """Structured warning/error message with enough context for audit trails."""

    code: str
    message: str
    severity: IssueSeverity = IssueSeverity.WARNING
    context: Mapping[str, MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.code, "code")
        _require_text(self.message, "message")
        object.__setattr__(self, "context", _frozen_mapping(self.context))


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _frozen_mapping(values: Mapping[str, MetadataValue]) -> Mapping[str, MetadataValue]:
    return MappingProxyType(dict(values))
