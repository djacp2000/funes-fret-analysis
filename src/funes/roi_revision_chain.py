"""Fail-closed backend consumption of finalized Module 24 revision chains.

This boundary reads an explicitly ordered sequence of already-finalized JSON
artifacts for one automatic Module 7/8 position.  It is deliberately separate
from Modules 15--23: it does not publish an analysis, select a scientific
configuration, or grant any review or activation authority.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .contracts import PositionKey
from .roi_geometry import RoiFilteringResult
from .roi_revision import RoiRevisionError
from .roi_revision_persistence import load_roi_revision_artifact
from .roi_revision_replay import RoiRevisionResult
from .segmentation_engine import SegmentationResult


class RoiRevisionChainError(RoiRevisionError):
    """An ordered finalized revision chain is incomplete or incoherent."""


@dataclass(frozen=True, slots=True)
class RoiRevisionChainEntry:
    """One verified artifact and its deterministic replay result."""

    path: Path
    artifact_sha256: str
    result: RoiRevisionResult

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise TypeError("path must be a Path")
        _require_sha256(self.artifact_sha256, "artifact_sha256")
        if not isinstance(self.result, RoiRevisionResult):
            raise TypeError("result must be a RoiRevisionResult")


@dataclass(frozen=True, slots=True)
class RoiRevisionChainResult:
    """The complete verified chain and its terminal effective mask result."""

    entries: tuple[RoiRevisionChainEntry, ...]

    def __post_init__(self) -> None:
        entries = tuple(self.entries)
        if not entries:
            raise RoiRevisionChainError("ROI revision chain must not be empty")
        object.__setattr__(self, "entries", entries)
        first = entries[0].result
        if first.revision.parent_revision_sha256 is not None:
            raise RoiRevisionChainError("first ROI revision artifact must be a root")
        seen_paths: set[Path] = set()
        for index, entry in enumerate(entries):
            if entry.path in seen_paths:
                raise RoiRevisionChainError(
                    f"ROI revision chain repeats artifact path at index {index}: {entry.path}"
                )
            seen_paths.add(entry.path)
            if entry.result.source_identity != first.source_identity:
                raise RoiRevisionChainError(
                    f"ROI revision chain artifact at index {index} has a different source identity"
                )
            if (
                entry.result.original_segmentation is not first.original_segmentation
                or entry.result.original_filtering is not first.original_filtering
            ):
                raise RoiRevisionChainError(
                    f"ROI revision chain artifact at index {index} has different automatic provenance"
                )
            if index:
                parent = entries[index - 1].result
                if entry.result.revision.parent_revision_sha256 != parent.revision_sha256:
                    raise RoiRevisionChainError(
                        f"ROI revision chain artifact at index {index} does not name the preceding revision as parent"
                    )

    @property
    def terminal_result(self) -> RoiRevisionResult:
        """Return the only result eligible for a later quantitative consumer."""

        return self.entries[-1].result


def load_finalized_roi_revision_chain(
    artifact_paths: Sequence[Path | str],
    segmentation: SegmentationResult,
    filtering: RoiFilteringResult,
    position_key: PositionKey,
) -> RoiRevisionChainResult:
    """Load one ordered chain, checking every artifact before returning it.

    The first artifact must be a root revision.  Every later artifact must name
    the immediately preceding finalized revision as its parent.  Each artifact
    is hashed immediately before and after strict load/replay verification, so
    a changed artifact is rejected rather than accepted from a race-prone path.
    """

    if isinstance(artifact_paths, (str, bytes)) or not isinstance(
        artifact_paths, Sequence
    ):
        raise TypeError("artifact_paths must be a non-string ordered sequence of paths")
    if not artifact_paths:
        raise RoiRevisionChainError("ROI revision chain must not be empty")

    normalized_paths: list[Path] = []
    seen_paths: set[Path] = set()
    for index, raw_path in enumerate(artifact_paths):
        if not isinstance(raw_path, (Path, str)):
            raise TypeError(f"artifact_paths[{index}] must be a Path or str")
        path = Path(raw_path).resolve(strict=False)
        if path in seen_paths:
            raise RoiRevisionChainError(
                f"ROI revision chain repeats artifact path at index {index}: {path}"
            )
        seen_paths.add(path)
        normalized_paths.append(path)

    entries: list[RoiRevisionChainEntry] = []
    parent: RoiRevisionResult | None = None
    for index, path in enumerate(normalized_paths):
        before = _file_sha256(path)
        try:
            replayed = load_roi_revision_artifact(
                path,
                segmentation,
                filtering,
                position_key,
                parent_result=parent,
            )
        except RoiRevisionError as exc:
            raise RoiRevisionChainError(
                f"invalid ROI revision chain artifact at index {index} ({path}): {exc}"
            ) from exc
        after = _file_sha256(path)
        if after != before:
            raise RoiRevisionChainError(
                f"ROI revision chain artifact changed while loading at index {index}: {path}"
            )
        entries.append(RoiRevisionChainEntry(path, before, replayed))
        parent = replayed
    return RoiRevisionChainResult(tuple(entries))


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise RoiRevisionChainError(
            f"cannot read ROI revision chain artifact {path}: {exc}"
        ) from exc


def _require_sha256(value: object, context: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise RoiRevisionChainError(f"{context} must be a lowercase SHA-256 value")
