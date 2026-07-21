"""Exact two-field static review package for the D062 K-means extension."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from time import perf_counter

import numpy as np
from numpy.typing import NDArray

from .segmentation_benchmark import SegmentationBenchmarkVariant
from .segmentation_benchmark_artifacts import (
    export_segmentation_benchmark_overlay_png,
    export_segmentation_benchmark_overlay_svg,
)
from .segmentation_benchmark_review import PreparedSegmentationBenchmarkField
from .segmentation_benchmark_review_package import (
    sha256_file,
    write_csv,
    write_json,
)
from .segmentation_kmeans_causal import (
    KMEANS_FOREGROUND_CAUSAL_EXTENSION_VARIANTS,
    KMeansForegroundCausalRun,
    run_kmeans_foreground_causal_variant,
)
from .segmentation_kmeans_causal_artifacts import (
    KMeansCausalReviewRegion,
    export_kmeans_causal_focus_svg,
)
from .segmentation_registry import SegmentationEngineRegistry
from .segmentation_selection import CapturePositionKey


KMEANS_CAUSAL_REAL_FIELD_KEYS = (
    CapturePositionKey("Capture 1", "Position 1"),
    CapturePositionKey("Capture 1", "Position 2"),
)
KMEANS_CAUSAL_REAL_FIELD_REGIONS = {
    KMEANS_CAUSAL_REAL_FIELD_KEYS[0]: KMeansCausalReviewRegion(
        "P1-R4", x_start=250, x_stop=360, y_start=510, y_stop=600
    ),
    KMEANS_CAUSAL_REAL_FIELD_KEYS[1]: KMeansCausalReviewRegion(
        "P2-R1", x_start=95, x_stop=225, y_start=85, y_stop=205
    ),
}
KMEANS_CAUSAL_REVIEW_SCOPE = (
    "D062 causal review only; no cell classification, final acceptability, "
    "sample sufficiency, method ranking, profile approval, or D046 action."
)


class KMeansForegroundCausalReviewError(RuntimeError):
    """Raised before or during construction of the exact D062 review package."""


@dataclass(frozen=True, slots=True)
class KMeansForegroundCausalReviewInput:
    """One prepared field and its immutable saved K-means area-32 reference."""

    field: PreparedSegmentationBenchmarkField
    reference_labels_path: Path
    reference_labels_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.field, PreparedSegmentationBenchmarkField):
            raise TypeError("field must be a PreparedSegmentationBenchmarkField")
        object.__setattr__(self, "reference_labels_path", Path(self.reference_labels_path))
        if not _is_sha256(self.reference_labels_sha256):
            raise ValueError("reference_labels_sha256 must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class KMeansForegroundCausalReviewPlan:
    """Immutable exact two-call plan; it carries no scientific approval semantics."""

    selection_id: str
    inputs: tuple[KMeansForegroundCausalReviewInput, ...]
    variant: SegmentationBenchmarkVariant = field(
        default=KMEANS_FOREGROUND_CAUSAL_EXTENSION_VARIANTS[0]
    )

    def __post_init__(self) -> None:
        if not isinstance(self.selection_id, str) or not self.selection_id.strip():
            raise ValueError("selection_id must be a non-empty string")
        object.__setattr__(self, "inputs", tuple(self.inputs))
        keys = tuple(item.field.field_key for item in self.inputs)
        if keys != KMEANS_CAUSAL_REAL_FIELD_KEYS:
            raise ValueError(
                "D062 review plan requires exactly Capture 1 + Position 1/2 in fixed order"
            )
        if self.variant not in KMEANS_FOREGROUND_CAUSAL_EXTENSION_VARIANTS:
            raise ValueError("D062 review plan accepts only its unchanged one-variant catalog")


@dataclass(frozen=True, slots=True)
class KMeansForegroundCausalReviewArtifact:
    run_id: str
    run: KMeansForegroundCausalRun
    run_dir: Path
    full_overlay_path: Path
    full_preview_path: Path
    focus_sheet_path: Path
    segmentation_execution_seconds: float


@dataclass(frozen=True, slots=True)
class KMeansForegroundCausalReviewResult:
    output_dir: Path
    selection_path: Path
    runs_path: Path
    observations_path: Path
    index_path: Path
    manifest_path: Path
    artifacts: tuple[KMeansForegroundCausalReviewArtifact, ...]


def export_kmeans_foreground_causal_review(
    plan: KMeansForegroundCausalReviewPlan,
    output_dir: Path | str,
    *,
    registry: SegmentationEngineRegistry | None = None,
) -> KMeansForegroundCausalReviewResult:
    """Execute exactly two candidate calls and preserve all D062 causal stages."""

    if not isinstance(plan, KMeansForegroundCausalReviewPlan):
        raise TypeError("plan must be a KMeansForegroundCausalReviewPlan")
    destination = Path(output_dir)
    if destination.exists() and any(destination.iterdir()):
        raise KMeansForegroundCausalReviewError(
            f"causal review output directory must be absent or empty: {destination}"
        )
    references = tuple(_load_and_verify(item) for item in plan.inputs)
    destination.mkdir(parents=True, exist_ok=True)
    runs_dir = destination / "runs"
    runs_dir.mkdir()

    selection_path = destination / "selection.json"
    write_json(selection_path, _selection_payload(plan))
    artifacts: list[KMeansForegroundCausalReviewArtifact] = []
    run_rows: list[dict[str, object]] = []
    for index, (item, reference_labels) in enumerate(
        zip(plan.inputs, references, strict=True), start=1
    ):
        run_id = f"field_{index:03d}__candidate_001"
        run_dir = runs_dir / run_id
        run_dir.mkdir()
        started = perf_counter()
        run = run_kmeans_foreground_causal_variant(
            item.field.prepared_frame,
            item.field.field_key,
            plan.variant,
            registry=registry,
            context={"causal_review_selection_id": plan.selection_id, "causal_review_run_id": run_id},
        )
        elapsed = perf_counter() - started
        masks = {
            "baseline_raw_foreground.npy": run.trace.baseline_raw_foreground,
            "relaxed_raw_foreground.npy": run.trace.relaxed_raw_foreground,
            "raw_added_support.npy": run.trace.raw_added_support,
            "baseline_post_morphology_pre_area.npy": run.trace.baseline_post_morphology_pre_area,
            "post_morphology_pre_area.npy": run.trace.post_morphology_pre_area,
            "final_labels.npy": run.segmentation.label_image,
        }
        for name, array in masks.items():
            np.save(run_dir / name, array, allow_pickle=False)
        overlay_path = run_dir / "full_field_overlay.svg"
        export_segmentation_benchmark_overlay_svg(
            item.field.prepared_frame,
            run.segmentation.label_image,
            overlay_path,
            title=f"{item.field.field_key.capture} + {item.field.field_key.position}",
            subtitle="D062 K-means boundary relaxation 0.5 | area fixed at 32",
            context={"review": "unclassified causal candidate", "origin": plan.variant.origin},
        )
        preview_path = run_dir / "full_field_preview.png"
        export_segmentation_benchmark_overlay_png(
            item.field.prepared_frame, run.segmentation.label_image, preview_path
        )
        focus_path = run_dir / "focused_causal_review.svg"
        export_kmeans_causal_focus_svg(
            item.field.prepared_frame,
            reference_labels,
            run.segmentation.label_image,
            run.trace.raw_added_support,
            KMEANS_CAUSAL_REAL_FIELD_REGIONS[item.field.field_key],
            focus_path,
            title=f"{item.field.field_key.capture} + {item.field.field_key.position}",
        )
        final_support = run.segmentation.label_image > 0
        reference_support = reference_labels > 0
        region = KMEANS_CAUSAL_REAL_FIELD_REGIONS[item.field.field_key]
        crop = np.s_[region.y_start : region.y_stop, region.x_start : region.x_stop]
        baseline_post = run.trace.baseline_post_morphology_pre_area
        candidate_post = run.trace.post_morphology_pre_area
        row = {
            "run_id": run_id,
            "capture": item.field.field_key.capture,
            "position": item.field.field_key.position,
            "variant_id": plan.variant.variant_id,
            "minimum_object_area_pixels": run.segmentation.engine.parameters["minimum_object_area_pixels"],
            "foreground_boundary_relaxation_fraction": run.trace.relaxation_fraction,
            "ordered_cluster_centers": ",".join(f"{value:.17g}" for value in run.trace.ordered_cluster_centers),
            "baseline_threshold": run.trace.baseline_threshold,
            "candidate_threshold": run.trace.candidate_threshold,
            **dict(run.trace.stage_change_counts),
            "final_added_pixels_vs_saved_reference": int(np.count_nonzero(final_support & ~reference_support)),
            "final_removed_pixels_vs_saved_reference": int(np.count_nonzero(reference_support & ~final_support)),
            "focus_region": region.name,
            "focus_raw_added_pixels": int(np.count_nonzero(run.trace.raw_added_support[crop])),
            "focus_post_morphology_added_pixels": int(
                np.count_nonzero(candidate_post[crop] & ~baseline_post[crop])
            ),
            "focus_post_morphology_removed_pixels": int(
                np.count_nonzero(baseline_post[crop] & ~candidate_post[crop])
            ),
            "focus_final_added_pixels_vs_saved_reference": int(
                np.count_nonzero(final_support[crop] & ~reference_support[crop])
            ),
            "focus_final_removed_pixels_vs_saved_reference": int(
                np.count_nonzero(reference_support[crop] & ~final_support[crop])
            ),
            "segmentation_execution_seconds": elapsed,
            "execution_timing_scope": "segmentation_engine_only_operational",
            "source_sha256": item.field.selected_source_sha256,
            "prepared_frame_sha256": item.field.prepared_frame_sha256,
            "reference_labels_sha256": item.reference_labels_sha256,
        }
        run_rows.append(row)
        write_json(run_dir / "causal_trace.json", row)
        artifacts.append(
            KMeansForegroundCausalReviewArtifact(
                run_id=run_id,
                run=run,
                run_dir=run_dir,
                full_overlay_path=overlay_path,
                full_preview_path=preview_path,
                focus_sheet_path=focus_path,
                segmentation_execution_seconds=elapsed,
            )
        )

    runs_path = destination / "runs.csv"
    write_csv(runs_path, run_rows)
    observations_path = destination / "causal_review_observations.csv"
    write_csv(observations_path, _blank_observation_rows(plan))
    index_path = destination / "index.html"
    index_path.write_text(_review_html(plan, artifacts), encoding="utf-8", newline="\n")
    manifest_path = destination / "manifest.json"
    write_json(manifest_path, _manifest_payload(destination, plan, run_rows))
    return KMeansForegroundCausalReviewResult(
        output_dir=destination,
        selection_path=selection_path,
        runs_path=runs_path,
        observations_path=observations_path,
        index_path=index_path,
        manifest_path=manifest_path,
        artifacts=tuple(artifacts),
    )


def _load_and_verify(item: KMeansForegroundCausalReviewInput) -> NDArray[np.int32]:
    if not item.field.selected_source_path.is_file():
        raise KMeansForegroundCausalReviewError(
            f"selected source is missing: {item.field.selected_source_path}"
        )
    if sha256_file(item.field.selected_source_path) != item.field.selected_source_sha256:
        raise KMeansForegroundCausalReviewError("selected source SHA-256 no longer matches")
    if not item.reference_labels_path.is_file():
        raise KMeansForegroundCausalReviewError(
            f"saved area-32 reference is missing: {item.reference_labels_path}"
        )
    if sha256_file(item.reference_labels_path) != item.reference_labels_sha256:
        raise KMeansForegroundCausalReviewError("saved area-32 reference SHA-256 no longer matches")
    labels = np.load(item.reference_labels_path, allow_pickle=False)
    if (
        labels.shape != item.field.prepared_frame.shape
        or not np.issubdtype(labels.dtype, np.integer)
        or np.any(labels < 0)
    ):
        raise KMeansForegroundCausalReviewError(
            "saved area-32 reference must be a non-negative integer label image matching the prepared frame"
        )
    return labels.astype(np.int32, copy=False)


def _selection_payload(plan: KMeansForegroundCausalReviewPlan) -> dict[str, object]:
    return {
        "selection_id": plan.selection_id,
        "scope_statement": KMEANS_CAUSAL_REVIEW_SCOPE,
        "engine_call_count": 2,
        "sample_sufficiency_assessed": False,
        "final_acceptability_assessed": False,
        "profile_approval_performed": False,
        "d046_review_ledger_used": False,
        "variant": {
            "variant_id": plan.variant.variant_id,
            "origin": plan.variant.origin,
            "changed_parameter": plan.variant.changed_parameter,
            "baseline_value": plan.variant.baseline_value,
            "candidate_value": plan.variant.candidate_value,
            "effective_parameters": dict(plan.variant.effective_parameters),
        },
        "fields": [
            {
                "capture": item.field.field_key.capture,
                "position": item.field.field_key.position,
                "selected_channel": item.field.selected_channel.value,
                "source_path": str(item.field.selected_source_path),
                "source_sha256": item.field.selected_source_sha256,
                "prepared_frame_sha256": item.field.prepared_frame_sha256,
                "reference_labels_path": str(item.reference_labels_path),
                "reference_labels_sha256": item.reference_labels_sha256,
            }
            for item in plan.inputs
        ],
    }


def _blank_observation_rows(plan: KMeansForegroundCausalReviewPlan) -> list[dict[str, object]]:
    return [
        {
            "capture": item.field.field_key.capture,
            "position": item.field.field_key.position,
            "region": KMEANS_CAUSAL_REAL_FIELD_REGIONS[item.field.field_key].name,
            "reviewer": "",
            "reviewed_at": "",
            "foreground_selection_contribution": "",
            "final_acceptability": "",
            "bridging_or_background_notes": "",
            "other_notes": "",
        }
        for item in plan.inputs
    ]


def _review_html(
    plan: KMeansForegroundCausalReviewPlan,
    artifacts: list[KMeansForegroundCausalReviewArtifact],
) -> str:
    cards = "".join(
        f'<article><h2>{escape(item.run.field_key.capture)} + {escape(item.run.field_key.position)}</h2>'
        f'<p><a href="{item.focus_sheet_path.relative_to(item.run_dir.parent.parent).as_posix()}">Focused causal sheet</a> | '
        f'<a href="{item.full_overlay_path.relative_to(item.run_dir.parent.parent).as_posix()}">Full-field overlay</a></p></article>'
        for item in artifacts
    )
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>D062 causal review</title></head>
<body><h1>Module 7 D062 K-means foreground causal review</h1><p>{escape(KMEANS_CAUSAL_REVIEW_SCOPE)}</p>
<p>Selection <code>{escape(plan.selection_id)}</code>; exactly two candidate calls; minimum area fixed at 32.</p>{cards}</body></html>\n'''


def _manifest_payload(
    root: Path,
    plan: KMeansForegroundCausalReviewPlan,
    run_rows: list[dict[str, object]],
) -> dict[str, object]:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "manifest.json")
    return {
        "selection_id": plan.selection_id,
        "scope_statement": KMEANS_CAUSAL_REVIEW_SCOPE,
        "engine_call_count": len(run_rows),
        "total_engine_seconds_operational_only": sum(
            float(row["segmentation_execution_seconds"]) for row in run_rows
        ),
        "source_and_reference_files": [
            {
                "source_path": str(item.field.selected_source_path),
                "source_sha256": item.field.selected_source_sha256,
                "prepared_frame_sha256": item.field.prepared_frame_sha256,
                "reference_labels_path": str(item.reference_labels_path),
                "reference_labels_sha256": item.reference_labels_sha256,
            }
            for item in plan.inputs
        ],
        "artifacts": [
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ],
    }


def _is_sha256(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
