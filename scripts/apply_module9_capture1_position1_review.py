"""Validate and apply the persisted Module 9 Position 1 inspection decision."""

from __future__ import annotations

import hashlib
import json

import numpy as np

from export_module9_capture1_position1 import (
    FIELD_KEY,
    LABEL_PATH,
    OUTPUT_DIR,
    PROJECT_ROOT,
    _validated_pair,
    _verified_hashes,
)
from funes.roi_geometry import (
    BorderTouchPolicy,
    RoiGeometryFilterConfig,
    filter_segmentation_rois,
)
from funes.roi_review import (
    apply_interactive_roi_review_decision,
    load_interactive_roi_review_decision,
)
from funes.segmentation_engine import SegmentationResult
from funes.segmentation_registry import DEFAULT_SEGMENTATION_REGISTRY
from funes.segmentation_review import SegmentationReviewState
from funes.segmentation_selection import SegmentationReviewStatus


DECISION_PATH = OUTPUT_DIR / "Capture_1_Position_1_roi_review.json"
RECEIPT_PATH = OUTPUT_DIR / "capture1_position1_roi_review_applied.json"


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    input_hashes = _verified_hashes()
    pair = _validated_pair()
    labels = np.load(LABEL_PATH, allow_pickle=False)

    review_state = SegmentationReviewState()
    field_review = review_state.query(FIELD_KEY)
    engine = DEFAULT_SEGMENTATION_REGISTRY.create_engine(
        field_review.selection,
        field_review,
    )
    segmentation = SegmentationResult(
        label_image=labels,
        roi_count=int(np.max(labels)),
        engine=engine.record,
    )
    roi_filtering = filter_segmentation_rois(
        segmentation,
        config=RoiGeometryFilterConfig(
            min_area_pixels=20,
            border_policy=BorderTouchPolicy.EXCLUDE,
        ),
        context={
            "capture": FIELD_KEY.capture,
            "position": FIELD_KEY.position,
            "source": "persisted_module7_area32_artifact",
            "purpose": "apply_module9_review_decision",
        },
    )

    decision = load_interactive_roi_review_decision(DECISION_PATH)
    reviewed_state = apply_interactive_roi_review_decision(
        review_state,
        pair,
        roi_filtering,
        decision,
    )
    reviewed = reviewed_state.query(FIELD_KEY)
    if reviewed.status is not SegmentationReviewStatus.MANUALLY_REVIEWED:
        raise ValueError("validated decision did not produce manually_reviewed status")
    if reviewed.global_approval is not None:
        raise ValueError("field inspection unexpectedly granted global approval")

    receipt = {
        "schema_version": "funes.module9.applied_review_receipt.v1",
        "decision_path": str(DECISION_PATH.relative_to(PROJECT_ROOT)),
        "decision_sha256": _sha256(DECISION_PATH),
        "field": {"capture": FIELD_KEY.capture, "position": FIELD_KEY.position},
        "status": reviewed.status.value,
        "selection": {
            "method": reviewed.selection.method.value,
            "profile": reviewed.selection.profile,
            "source": reviewed.selection.source.value,
        },
        "inspection": {
            "inspector": reviewed.inspection.inspector,
            "inspected_at": reviewed.inspection.inspected_at,
            "note": reviewed.inspection.note,
        },
        "source_label_sha256": decision.source_label_sha256,
        "roi_filtering_sha256": decision.roi_filtering_sha256,
        "verified_input_sha256": input_hashes,
        "global_approval_granted": False,
        "segmentation_executed": False,
        "masks_modified": False,
        "parameters_modified": False,
    }
    RECEIPT_PATH.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
