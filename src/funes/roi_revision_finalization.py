"""Auditable backend completion of one human Module 24 ROI revision.

This module deliberately composes existing immutable Module 24 contracts.  It
does not offer editing controls, make a scientific decision, or load a revision
artifact as input.  A caller supplies an already prepared draft and the exact
automatic Module 7/8 results to which it is bound.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .contracts import PositionKey
from .roi_geometry import RoiFilteringResult
from .roi_revision import (
    RoiMaskRevision,
    RoiRevisionError,
    RoiRevisionFinalizationState,
    finalize_roi_revision,
)
from .roi_revision_persistence import (
    RoiRevisionArtifactWriteResult,
    export_roi_revision_artifact,
    load_roi_revision_artifact,
)
from .roi_revision_replay import RoiRevisionResult, replay_roi_revision
from .segmentation_engine import SegmentationResult


class RoiRevisionHumanFinalizationError(RoiRevisionError):
    """A requested human finalization cannot produce a verified artifact."""


@dataclass(frozen=True, slots=True)
class RoiRevisionHumanFinalizationResult:
    """One finalized revision plus its independently revalidated artifact.

    Completion is an administrative audit event only.  It does not grant
    scientific approval, change Module 9/D046 review state, or start analysis.
    """

    draft_revision: RoiMaskRevision
    revision_result: RoiRevisionResult
    artifact: RoiRevisionArtifactWriteResult

    def __post_init__(self) -> None:
        if self.draft_revision.finalization_state is not RoiRevisionFinalizationState.DRAFT:
            raise RoiRevisionHumanFinalizationError(
                "human finalization requires an unfinalized ROI revision draft"
            )
        if self.revision_result.finalization_state is not RoiRevisionFinalizationState.FINALIZED:
            raise RoiRevisionHumanFinalizationError(
                "human finalization result must retain a finalized revision"
            )
        if self.revision_result.revision.editor != self.draft_revision.editor:
            raise RoiRevisionHumanFinalizationError(
                "finalized revision editor does not match the submitted draft"
            )
        if self.artifact.revision_sha256 != self.revision_result.revision_sha256:
            raise RoiRevisionHumanFinalizationError(
                "artifact revision SHA-256 does not match the finalized revision"
            )


def finalize_human_roi_revision_artifact(
    draft_revision: RoiMaskRevision,
    segmentation: SegmentationResult,
    filtering: RoiFilteringResult,
    position_key: PositionKey,
    *,
    finalized_at: str,
    output_path: Path | str,
    parent_result: RoiRevisionResult | None = None,
) -> RoiRevisionHumanFinalizationResult:
    """Finalize, replay, persist, reload, and verify one human review draft.

    ``output_path`` must be new.  This prevents an audit artifact from silently
    replacing a prior human-finalization record.  If post-write verification
    fails, the just-created destination is removed and the verification error is
    raised; an existing file is never removed.
    """

    if not isinstance(draft_revision, RoiMaskRevision):
        raise TypeError("draft_revision must be a RoiMaskRevision")
    if draft_revision.finalization_state is not RoiRevisionFinalizationState.DRAFT:
        raise RoiRevisionHumanFinalizationError(
            "human finalization requires an unfinalized ROI revision draft"
        )
    destination = Path(output_path)
    if destination.exists():
        raise RoiRevisionHumanFinalizationError(
            f"refusing to overwrite existing ROI revision artifact: {destination}"
        )

    finalized = finalize_roi_revision(draft_revision, finalized_at=finalized_at)
    replayed = replay_roi_revision(
        finalized,
        segmentation,
        filtering,
        position_key,
        parent_result=parent_result,
    )
    written = export_roi_revision_artifact(replayed, destination)
    try:
        reloaded = load_roi_revision_artifact(
            destination,
            segmentation,
            filtering,
            position_key,
            parent_result=parent_result,
        )
        _require_exact_revalidation(replayed, reloaded, written, destination)
    except Exception:
        _remove_new_destination(destination)
        raise
    return RoiRevisionHumanFinalizationResult(
        draft_revision=draft_revision,
        revision_result=reloaded,
        artifact=written,
    )


def _require_exact_revalidation(
    expected: RoiRevisionResult,
    actual: RoiRevisionResult,
    written: RoiRevisionArtifactWriteResult,
    destination: Path,
) -> None:
    if actual.revision != expected.revision:
        raise RoiRevisionHumanFinalizationError(
            "reloaded ROI revision does not match the finalized revision"
        )
    if actual.operation_trace != expected.operation_trace:
        raise RoiRevisionHumanFinalizationError(
            "reloaded ROI revision operation trace does not match finalization"
        )
    if (
        actual.input_label_sha256 != expected.input_label_sha256
        or actual.edited_label_sha256 != expected.edited_label_sha256
        or actual.measurement_label_sha256 != expected.measurement_label_sha256
        or actual.revision_sha256 != expected.revision_sha256
        or not np.array_equal(actual.edited_label_image, expected.edited_label_image)
        or not np.array_equal(actual.measurement_label_image, expected.measurement_label_image)
    ):
        raise RoiRevisionHumanFinalizationError(
            "reloaded ROI revision masks do not match deterministic finalization"
        )
    observed_sha256 = hashlib.sha256(destination.read_bytes()).hexdigest()
    if observed_sha256 != written.sha256:
        raise RoiRevisionHumanFinalizationError(
            "ROI revision artifact changed during finalization verification"
        )


def _remove_new_destination(destination: Path) -> None:
    """Remove only the newly created failed artifact, preserving prior records."""

    try:
        destination.unlink(missing_ok=True)
    except OSError as exc:
        raise RoiRevisionHumanFinalizationError(
            f"could not remove unverified ROI revision artifact {destination}: {exc}"
        ) from exc
