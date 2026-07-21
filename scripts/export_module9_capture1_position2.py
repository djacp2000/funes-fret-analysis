"""Export the Module 9 viewer from the persisted Position 2 label artifact.

This script deliberately does not call a segmentation entry point. It verifies
the selected, previously calculated K-means area-32 label artifact, restores
the typed Module 7/8 boundary, and exports the read-only Module 9 HTML viewer.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from funes.file_discovery import parse_tiff_filename
from funes.roi_geometry import (
    BorderTouchPolicy,
    RoiGeometryFilterConfig,
    filter_segmentation_rois,
)
from funes.roi_review import export_interactive_roi_review_html
from funes.segmentation_engine import SegmentationResult
from funes.segmentation_registry import DEFAULT_SEGMENTATION_REGISTRY
from funes.segmentation_review import SegmentationReviewState
from funes.segmentation_selection import CapturePositionKey
from funes.tiff_reader import validate_tiff_pair


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIELD_KEY = CapturePositionKey("Capture 1", "Position 2")

C0_PATH = PROJECT_ROOT / "raw_data" / (
    "Capture 1 - Position 2_XY1757012096_Z0_T0_C0.tif"
)
C1_PATH = PROJECT_ROOT / "raw_data" / (
    "Capture 1 - Position 2_XY1757012096_Z0_T0_C1.tif"
)
LABEL_PATH = PROJECT_ROOT / "outputs" / "module7_ofat_review_20260714_kmeans" / (
    "runs/field_002__variant_003/labels.npy"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "module9_roi_review_capture1_position2"
OUTPUT_HTML = OUTPUT_DIR / "capture1_position2_roi_review_v2.html"
OUTPUT_MANIFEST = OUTPUT_DIR / "capture1_position2_roi_review_manifest.json"

EXPECTED_SHA256 = {
    C0_PATH: "31e137998414ee5204e9e47c1c0fb351c996d227defd0ff15b84fb24eceb3a46",
    C1_PATH: "c3eedf9770166c7b73a299df5d6a5f299597f0d504289b07884a3e5b64701238",
    LABEL_PATH: "c4428d4f6f470ce00a9fbeaf57503f850237b8d5b7781b8dba259799b2c97aa3",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_hashes() -> dict[str, str]:
    observed: dict[str, str] = {}
    for path, expected in EXPECTED_SHA256.items():
        if not path.is_file():
            raise FileNotFoundError(f"required persisted input is missing: {path}")
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(
                f"persisted input hash changed for {path}: expected {expected}, got {actual}"
            )
        observed[str(path.relative_to(PROJECT_ROOT))] = actual
    return observed


def _validated_pair():
    parsed_c0 = parse_tiff_filename(C0_PATH)
    parsed_c1 = parse_tiff_filename(C1_PATH)
    if parsed_c0 is None or parsed_c1 is None:
        raise ValueError("the fixed Position 2 TIFF filenames no longer parse")
    validation = validate_tiff_pair(parsed_c0, parsed_c1)
    if validation.pair is None:
        issue_codes = ", ".join(issue.code for issue in validation.issues) or "none"
        raise ValueError(f"Position 2 TIFF pair validation failed: {issue_codes}")
    pair = validation.pair
    if (
        pair.position_key.capture != FIELD_KEY.capture
        or pair.position_key.position != FIELD_KEY.position
    ):
        raise ValueError("validated TIFF pair does not match Capture 1 + Position 2")
    return pair


def main() -> None:
    input_hashes = _verified_hashes()
    pair = _validated_pair()

    labels = np.load(LABEL_PATH, allow_pickle=False)
    if labels.shape != pair.c0.frames.shape[1:]:
        raise ValueError(
            "persisted Position 2 labels do not match the validated TIFF frame shape"
        )

    review_state = SegmentationReviewState()
    field_review = review_state.query(FIELD_KEY)
    engine = DEFAULT_SEGMENTATION_REGISTRY.create_engine(
        field_review.selection,
        field_review,
    )
    if field_review.selection.method.value != "kmeans" or (
        field_review.selection.profile != "provisional_working_kmeans_area32"
    ):
        raise ValueError(
            "current segmentation selection no longer matches the persisted area-32 labels"
        )

    segmentation = SegmentationResult(
        label_image=labels,
        roi_count=int(np.max(labels)),
        engine=engine.record,
    )
    geometry_config = RoiGeometryFilterConfig(
        min_area_pixels=20,
        border_policy=BorderTouchPolicy.EXCLUDE,
    )
    roi_filtering = filter_segmentation_rois(
        segmentation,
        config=geometry_config,
        context={
            "capture": FIELD_KEY.capture,
            "position": FIELD_KEY.position,
            "source": "persisted_module7_area32_artifact",
            "purpose": "module9_read_only_viewer_export",
        },
    )

    result = export_interactive_roi_review_html(
        pair,
        roi_filtering,
        review_state,
        OUTPUT_HTML,
        title="Module 9 ROI review — Capture 1 / Position 2",
    )

    manifest = {
        "artifact": str(result.path.relative_to(PROJECT_ROOT)),
        "field": {"capture": FIELD_KEY.capture, "position": FIELD_KEY.position},
        "input_sha256": input_hashes,
        "source_label_sha256": result.source_label_sha256,
        "roi_filtering_sha256": result.roi_filtering_sha256,
        "frame_count": result.frame_count,
        "source_roi_count": len(result.roi_labels),
        "retained_roi_count": roi_filtering.accepted_count,
        "rejected_roi_count": roi_filtering.rejected_count,
        "segmentation": {
            "executed": False,
            "method": field_review.selection.method.value,
            "profile": field_review.selection.profile,
            "selection_source": field_review.selection.source.value,
            "persisted_label_artifact": str(LABEL_PATH.relative_to(PROJECT_ROOT)),
        },
        "module8_reconstruction": {
            "reason": "typed RoiFilteringResult was not persisted with the labels",
            "min_area_pixels": geometry_config.min_area_pixels,
            "max_area_pixels": geometry_config.max_area_pixels,
            "border_policy": geometry_config.border_policy.value,
            "parameter_source": "RealPairValidationConfig default",
        },
        "raw_tiff_modified": False,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
