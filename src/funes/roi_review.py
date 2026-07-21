"""Read-only interactive ROI review and auditable inspection decisions."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from numpy.typing import NDArray

from .roi_geometry import RoiFilterRecord, RoiFilteringResult
from .roi_review_template import ROI_REVIEW_HTML_TEMPLATE
from .segmentation_review import SegmentationReviewState
from .segmentation_selection import (
    CapturePositionKey,
    SegmentationSelection,
    SegmentationSelectionSource,
)
from .static_roi_overlay import (
    _boundary_path,
    _grayscale_png_bytes,
    _validated_records,
)
from .tiff_reader import TiffPair


ROI_REVIEW_SCHEMA_VERSION = "funes.module9.roi_review.v1"


@dataclass(frozen=True, slots=True)
class InteractiveRoiReviewConfig:
    """Display-only contrast limits for both embedded channel stacks."""

    lower_percentile: float = 1.0
    upper_percentile: float = 99.5

    def __post_init__(self) -> None:
        if not 0 <= self.lower_percentile < self.upper_percentile <= 100:
            raise ValueError(
                "lower_percentile must be below upper_percentile within 0..100"
            )


@dataclass(frozen=True, slots=True)
class InteractiveRoiReviewResult:
    """Created viewer and exact image/ROI identity represented in it."""

    path: Path
    field_key: CapturePositionKey
    frame_count: int
    roi_labels: tuple[int, ...]
    source_label_sha256: str
    roi_filtering_sha256: str
    review_filename: str


@dataclass(frozen=True, slots=True)
class InteractiveRoiReviewDecision:
    """Validated inspection exported by the Module 9 read-only viewer."""

    field_key: CapturePositionKey
    source_label_sha256: str
    roi_filtering_sha256: str
    selection: SegmentationSelection
    selection_source: SegmentationSelectionSource
    experiment: str | None = None
    inspector: str | None = None
    inspected_at: str | None = None
    note: str | None = None
    schema_version: str = ROI_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ROI_REVIEW_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported ROI review schema_version: {self.schema_version!r}"
            )
        if not isinstance(self.field_key, CapturePositionKey):
            raise TypeError("field_key must be a CapturePositionKey")
        for name, value in (
            ("source_label_sha256", self.source_label_sha256),
            ("roi_filtering_sha256", self.roi_filtering_sha256),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError(f"{name} must be a lowercase SHA-256 value")
        if not isinstance(self.selection, SegmentationSelection):
            raise TypeError("selection must be a SegmentationSelection")
        if not isinstance(self.selection_source, SegmentationSelectionSource):
            raise TypeError("selection_source must be a SegmentationSelectionSource")
        if self.experiment is not None and (
            not isinstance(self.experiment, str) or not self.experiment.strip()
        ):
            raise ValueError("experiment must be non-empty text when provided")
        for name, value in (
            ("inspector", self.inspector),
            ("inspected_at", self.inspected_at),
            ("note", self.note),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be non-empty text when provided")


def export_interactive_roi_review_html(
    pair: TiffPair,
    roi_filtering: RoiFilteringResult,
    review_state: SegmentationReviewState,
    output_path: Path | str,
    *,
    title: str | None = None,
    config: InteractiveRoiReviewConfig | None = None,
) -> InteractiveRoiReviewResult:
    """Create one self-contained read-only HTML viewer for a validated field."""

    if not isinstance(pair, TiffPair):
        raise TypeError("pair must be a TiffPair")
    if not isinstance(roi_filtering, RoiFilteringResult):
        raise TypeError("roi_filtering must be a RoiFilteringResult")
    if not isinstance(review_state, SegmentationReviewState):
        raise TypeError("review_state must be a SegmentationReviewState")
    config = config or InteractiveRoiReviewConfig()
    if not isinstance(config, InteractiveRoiReviewConfig):
        raise TypeError("config must be an InteractiveRoiReviewConfig")

    destination = Path(output_path)
    if destination.suffix.casefold() not in (".html", ".htm"):
        raise ValueError("interactive ROI review output path must use .html or .htm")

    field_key = CapturePositionKey.from_position_key(pair.position_key)
    field_review = review_state.query(field_key)
    labels = roi_filtering.source_label_image
    records = _validated_records(labels, roi_filtering.records)
    c0 = _validated_stack(pair.c0.frames, "C0")
    c1 = _validated_stack(pair.c1.frames, "C1")
    if c0.shape != c1.shape:
        raise ValueError("interactive ROI review requires matching C0/C1 stack shapes")
    if c0.shape[1:] != labels.shape:
        raise ValueError(
            "interactive ROI review requires frame and ROI label shapes to match"
        )

    source_label_sha256 = roi_label_sha256(labels)
    filtering_sha256 = roi_filtering_sha256(roi_filtering)
    experiment = pair.position_key.experiment
    review_filename = _review_filename(field_key, experiment)
    review_field = {
        "capture": field_key.capture,
        "position": field_key.position,
        **({"experiment": experiment} if experiment is not None else {}),
    }
    display_title = title or f"ROI review — {field_key.capture} / {field_key.position}"
    if not isinstance(display_title, str) or not display_title.strip():
        raise ValueError("title must be non-empty text when provided")

    selection = field_review.selection
    encoded_c0 = _encoded_stack(c0, config)
    encoded_c1 = _encoded_stack(c1, config)
    viewer_data = {
        "field": review_field,
        "width": int(labels.shape[1]),
        "height": int(labels.shape[0]),
        "frame_count": int(c0.shape[0]),
        "channels": {
            "C0": encoded_c0,
            "C1": encoded_c1,
        },
        "rois": {
            str(record.geometry.label): _record_data(record) for record in records
        },
        "selection": {
            "method": selection.method.value,
            "profile": selection.profile,
            "source": selection.source.value,
        },
        "review_status": field_review.status.value,
        "source_label_sha256": source_label_sha256,
        "roi_filtering_sha256": filtering_sha256,
        "storage_key": (
            f"funes-module9:{experiment or 'unassigned'}:{field_key.capture}:"
            f"{field_key.position}:"
            f"{source_label_sha256}"
        ),
        "review_filename": review_filename,
        "review_record": {
            "schema_version": ROI_REVIEW_SCHEMA_VERSION,
            "decision": "inspected",
            "field": review_field,
            "source_label_sha256": source_label_sha256,
            "roi_filtering_sha256": filtering_sha256,
            "selection": {
                "method": selection.method.value,
                "profile": selection.profile,
                "source": selection.source.value,
            },
            "inspection": None,
        },
    }
    replacements = {
        "TITLE": escape(display_title),
        "OVERLAY": _overlay_svg(labels, records),
        "FRAME_ATLAS": _frame_atlas(encoded_c0, encoded_c1),
        "VIEWER_DATA": _json_for_html(viewer_data),
    }
    rendered = re.sub(
        r"__FUNES_(TITLE|OVERLAY|FRAME_ATLAS|VIEWER_DATA)__",
        lambda match: replacements[match.group(1)],
        ROI_REVIEW_HTML_TEMPLATE,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8", newline="\n")
    return InteractiveRoiReviewResult(
        path=destination,
        field_key=field_key,
        frame_count=int(c0.shape[0]),
        roi_labels=tuple(record.geometry.label for record in records),
        source_label_sha256=source_label_sha256,
        roi_filtering_sha256=filtering_sha256,
        review_filename=review_filename,
    )


def load_interactive_roi_review_decision(
    path: Path | str,
) -> InteractiveRoiReviewDecision:
    """Load and strictly validate a review JSON downloaded by the viewer."""

    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"ROI review decision could not be read: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"ROI review decision is not valid JSON: {source}") from exc
    root = _exact_mapping(
        raw,
        {
            "schema_version",
            "decision",
            "field",
            "source_label_sha256",
            "roi_filtering_sha256",
            "selection",
            "inspection",
        },
        "ROI review decision",
    )
    if root["decision"] != "inspected":
        raise ValueError("ROI review decision must explicitly be 'inspected'")
    field_value = root["field"]
    if not isinstance(field_value, dict):
        raise ValueError("field must be a JSON object")
    field_keys = set(field_value)
    expected_field_keys = (
        {"experiment", "capture", "position"}
        if "experiment" in field_keys
        else {"capture", "position"}
    )
    field = _exact_mapping(field_value, expected_field_keys, "field")
    selection = _exact_mapping(
        root["selection"], {"method", "profile", "source"}, "selection"
    )
    inspection = _exact_mapping(
        root["inspection"], {"inspector", "inspected_at", "note"}, "inspection"
    )
    try:
        source_value = SegmentationSelectionSource(selection["source"])
    except (TypeError, ValueError) as exc:
        raise ValueError("selection.source is not a supported selection source") from exc
    return InteractiveRoiReviewDecision(
        schema_version=root["schema_version"],
        field_key=CapturePositionKey(field["capture"], field["position"]),
        source_label_sha256=root["source_label_sha256"],
        roi_filtering_sha256=root["roi_filtering_sha256"],
        selection=SegmentationSelection(selection["method"], selection["profile"]),
        selection_source=source_value,
        experiment=field.get("experiment"),
        inspector=inspection["inspector"],
        inspected_at=inspection["inspected_at"],
        note=inspection["note"],
    )


def apply_interactive_roi_review_decision(
    review_state: SegmentationReviewState,
    pair: TiffPair,
    roi_filtering: RoiFilteringResult,
    decision: InteractiveRoiReviewDecision,
) -> SegmentationReviewState:
    """Validate viewer provenance and return D046 state with the inspection."""

    if not isinstance(review_state, SegmentationReviewState):
        raise TypeError("review_state must be a SegmentationReviewState")
    if not isinstance(pair, TiffPair):
        raise TypeError("pair must be a TiffPair")
    if not isinstance(roi_filtering, RoiFilteringResult):
        raise TypeError("roi_filtering must be a RoiFilteringResult")
    if not isinstance(decision, InteractiveRoiReviewDecision):
        raise TypeError("decision must be an InteractiveRoiReviewDecision")

    expected_key = CapturePositionKey.from_position_key(pair.position_key)
    if (
        decision.experiment is not None
        and decision.experiment != pair.position_key.experiment
    ):
        raise ValueError(
            "ROI review experiment does not match the supplied TIFF pair; apply "
            "the decision only inside its original experiment scope"
        )
    if decision.field_key != expected_key:
        raise ValueError(
            "ROI review field does not match the supplied TIFF pair; apply the "
            "decision to its original Capture + Position"
        )
    expected_hash = roi_label_sha256(roi_filtering.source_label_image)
    if decision.source_label_sha256 != expected_hash:
        raise ValueError(
            "ROI review source-label hash does not match the supplied filtering "
            "result; regenerate and inspect the viewer for the current labels"
        )
    expected_filtering_hash = roi_filtering_sha256(roi_filtering)
    if decision.roi_filtering_sha256 != expected_filtering_hash:
        raise ValueError(
            "ROI review filtering hash does not match the supplied Module 8 result; "
            "regenerate and inspect the viewer for the current statuses"
        )
    resolved = review_state.configuration.resolve(expected_key)
    expected_selection = SegmentationSelection(resolved.method, resolved.profile)
    if (
        decision.selection != expected_selection
        or decision.selection_source is not resolved.source
    ):
        raise ValueError(
            "ROI review selection is stale or does not match the current "
            "configuration; regenerate and inspect the viewer"
        )
    return review_state.record_inspection(
        expected_key,
        inspector=decision.inspector,
        inspected_at=decision.inspected_at,
        note=decision.note,
    )


def roi_label_sha256(labels: NDArray[np.generic]) -> str:
    """Return a stable identity for the exact shaped integer label image."""

    values = np.asarray(labels)
    if values.ndim != 2 or values.size == 0:
        raise ValueError("ROI label hashing requires a non-empty 2D array")
    if not np.issubdtype(values.dtype, np.integer) or np.any(values < 0):
        raise ValueError("ROI label hashing requires non-negative integer labels")
    if int(values.max()) > np.iinfo(np.int32).max:
        raise ValueError("ROI label hashing requires labels that fit within int32")
    canonical = np.ascontiguousarray(values.astype(np.int32, copy=False))
    digest = hashlib.sha256()
    digest.update(b"funes-roi-label-image-v1\0")
    digest.update(f"{canonical.shape[0]}x{canonical.shape[1]}\0".encode("ascii"))
    digest.update(canonical.tobytes(order="C"))
    return digest.hexdigest()


def roi_filtering_sha256(roi_filtering: RoiFilteringResult) -> str:
    """Hash the exact Module 8 masks, configuration, statuses, and geometry."""

    if not isinstance(roi_filtering, RoiFilteringResult):
        raise TypeError("roi_filtering must be a RoiFilteringResult")
    payload = {
        "source_label_sha256": roi_label_sha256(
            roi_filtering.source_label_image
        ),
        "filtered_label_sha256": roi_label_sha256(
            roi_filtering.filtered_label_image
        ),
        "config": {
            "min_area_pixels": roi_filtering.config.min_area_pixels,
            "max_area_pixels": roi_filtering.config.max_area_pixels,
            "border_policy": roi_filtering.config.border_policy.value,
        },
        "records": [
            {
                "label": record.geometry.label,
                "status": record.status.value,
                "reasons": list(record.reasons),
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
            }
            for record in roi_filtering.records
        ],
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(b"funes-roi-filtering-v1\0" + serialized).hexdigest()


def _validated_stack(frames: NDArray[np.generic], channel: str) -> NDArray[np.generic]:
    values = np.asarray(frames)
    if values.ndim != 3 or values.shape[0] < 1 or min(values.shape[1:]) < 1:
        raise ValueError(f"interactive ROI review requires a non-empty 3D {channel} stack")
    if not np.issubdtype(values.dtype, np.number):
        raise ValueError(f"interactive ROI review requires numeric {channel} frames")
    if np.issubdtype(values.dtype, np.floating) and not np.all(np.isfinite(values)):
        raise ValueError(f"interactive ROI review requires finite {channel} frames")
    return values


def _encoded_stack(
    frames: NDArray[np.generic],
    config: InteractiveRoiReviewConfig,
) -> list[str]:
    low = float(np.percentile(frames, config.lower_percentile))
    high = float(np.percentile(frames, config.upper_percentile))
    encoded: list[str] = []
    for frame in frames:
        if high <= low:
            normalized = np.zeros(frame.shape, dtype=np.uint8)
        else:
            scaled = np.clip((np.asarray(frame, dtype=np.float64) - low) / (high - low), 0, 1)
            normalized = np.rint(scaled * 255).astype(np.uint8)
        payload = base64.b64encode(_grayscale_png_bytes(normalized)).decode("ascii")
        encoded.append(f"data:image/png;base64,{payload}")
    return encoded


def _overlay_svg(
    labels: NDArray[np.int32],
    records: tuple[RoiFilterRecord, ...],
) -> str:
    height, width = labels.shape
    groups = []
    for record in records:
        geometry = record.geometry
        reasons = ",".join(record.reasons) or "none"
        groups.append(
            f'<g class="roi {record.status.value}" data-label="{geometry.label}" '
            f'data-reasons="{escape(reasons)}">'
            f'<path d="{_boundary_path(labels, geometry.label, 0, 0)}"/>'
            f'<text x="{geometry.centroid_col + 0.5:.2f}" '
            f'y="{geometry.centroid_row + 0.5:.2f}">{geometry.label}</text>'
            "</g>"
        )
    return (
        f'<svg id="roi-overlay" viewBox="0 0 {width} {height}" '
        f'aria-label="Fixed ROI contours">{"".join(groups)}</svg>'
    )


def _record_data(record: RoiFilterRecord) -> dict[str, Any]:
    geometry = record.geometry
    return {
        "label": geometry.label,
        "status": record.status.value,
        "reasons": list(record.reasons),
        "area_pixels": geometry.area_pixels,
        "touches_border": geometry.touches_border,
    }


def _frame_atlas(encoded_c0: list[str], encoded_c1: list[str]) -> str:
    cards: list[str] = []
    for channel, frames in (("C0", encoded_c0), ("C1", encoded_c1)):
        for frame_index, source in enumerate(frames):
            cards.append(
                '<figure class="frame-card" '
                f'data-static-channel="{channel}" data-static-frame="{frame_index}">'
                f'<img src="{source}" alt="{channel} temporal frame {frame_index}">'
                f'<figcaption>{channel} — Frame {frame_index}</figcaption>'
                "</figure>"
            )
    return "".join(cards)


def _review_filename(
    field_key: CapturePositionKey, experiment: str | None = None
) -> str:
    prefix = f"{experiment}_" if experiment is not None else ""
    stem = _safe_slug(f"{prefix}{field_key.capture}_{field_key.position}")
    return f"{stem}_roi_review.json"


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._-")
    return slug or "field"


def _json_for_html(value: Mapping[str, Any]) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def _exact_mapping(
    value: Any,
    expected_keys: set[str],
    field_name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    actual = set(value)
    if actual != expected_keys:
        missing = sorted(expected_keys - actual)
        extra = sorted(actual - expected_keys)
        raise ValueError(
            f"{field_name} has an invalid schema; missing={missing}, extra={extra}"
        )
    return value
