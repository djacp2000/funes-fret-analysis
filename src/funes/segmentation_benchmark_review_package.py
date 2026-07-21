"""Serialization helpers for static Module 7 OFAT visual-review packages."""

from __future__ import annotations

import csv
import hashlib
import json
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .segmentation_benchmark_review import (
        PreparedSegmentationBenchmarkField,
        SegmentationBenchmarkReviewArtifact,
        SegmentationBenchmarkReviewPlan,
    )


def selection_payload(
    plan: SegmentationBenchmarkReviewPlan,
    scope_statement: str,
) -> dict[str, object]:
    return {
        "selection_id": plan.selection_id,
        "selection_note": plan.selection_note,
        "scope_statement": scope_statement,
        "sample_sufficiency_assessed": False,
        "method_ranking_performed": False,
        "profile_approval_performed": False,
        "d046_review_ledger_used": False,
        "execution_timing_purpose": "operational_only_not_scientific_comparison",
        "fields": [
            {
                "capture": item.field_key.capture,
                "position": item.field_key.position,
                "selected_channel": item.selected_channel.value,
                "channel_selection_method": item.channel_selection_method,
                "robust_contrast_by_channel": dict(item.robust_contrast_by_channel),
                "preprocessing_method": item.preprocessing_method,
                "preprocessing_parameters": dict(item.preprocessing_parameters),
                "selected_source_path": str(item.selected_source_path),
                "selected_source_sha256": item.selected_source_sha256,
                "prepared_frame_shape": list(item.prepared_frame.shape),
                "prepared_frame_dtype": str(item.prepared_frame.dtype),
                "prepared_frame_sha256": item.prepared_frame_sha256,
            }
            for item in plan.fields
        ],
        "variants": [
            {
                "method": item.method.value,
                "variant_id": item.variant_id,
                "changed_parameter": item.changed_parameter,
                "baseline_value": item.baseline_value,
                "candidate_value": item.candidate_value,
                "origin": item.origin,
                "status": item.status,
                "effective_parameters": dict(item.effective_parameters),
            }
            for item in plan.variants
        ],
    }


def run_row(
    artifact: SegmentationBenchmarkReviewArtifact,
    selected_field: PreparedSegmentationBenchmarkField,
    root: Path,
) -> dict[str, object]:
    run = artifact.run
    summary = run.summary
    variant = run.variant
    return {
        "run_id": artifact.run_id,
        "capture": run.field_key.capture,
        "position": run.field_key.position,
        "selected_channel": selected_field.selected_channel.value,
        "preprocessing_method": selected_field.preprocessing_method,
        "method": variant.method.value,
        "variant_id": variant.variant_id,
        "changed_parameter": variant.changed_parameter,
        "baseline_value": variant.baseline_value,
        "candidate_value": variant.candidate_value,
        "variant_origin": variant.origin,
        "variant_status": variant.status,
        "roi_count": summary.roi_count,
        "foreground_pixel_count": summary.foreground_pixel_count,
        "foreground_fraction": summary.foreground_fraction,
        "roi_area_min_pixels": summary.roi_area_min_pixels,
        "roi_area_median_pixels": summary.roi_area_median_pixels,
        "roi_area_max_pixels": summary.roi_area_max_pixels,
        "segmentation_execution_seconds": artifact.segmentation_execution_seconds,
        "execution_timing_scope": "segmentation_engine_only_operational",
        "overlay_path": artifact.overlay_path.relative_to(root).as_posix(),
        "preview_path": artifact.preview_path.relative_to(root).as_posix(),
        "label_image_path": artifact.label_image_path.relative_to(root).as_posix(),
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError("benchmark review CSV requires at least one run")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_observations_csv(path: Path, run_rows: list[dict[str, object]]) -> None:
    fields = (
        "run_id",
        "capture",
        "position",
        "method",
        "variant_id",
        "reviewer",
        "reviewed_at",
        "whole_cell_shape_notes",
        "touching_cell_notes",
        "other_visual_notes",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for run in run_rows:
            writer.writerow({name: run.get(name, "") for name in fields})


def review_html(
    plan: SegmentationBenchmarkReviewPlan,
    artifacts: list[SegmentationBenchmarkReviewArtifact],
    run_rows: list[dict[str, object]],
    root: Path,
    scope_statement: str,
) -> str:
    cards: list[str] = []
    for artifact, row in zip(artifacts, run_rows, strict=True):
        overlay = artifact.overlay_path.relative_to(root).as_posix()
        preview = artifact.preview_path.relative_to(root).as_posix()
        change = (
            "unchanged baseline"
            if row["changed_parameter"] is None
            else f"{row['changed_parameter']}: {row['baseline_value']} -> {row['candidate_value']}"
        )
        cards.append(
            f'''<article class="card">
  <h2>{escape(str(row['capture']))} + {escape(str(row['position']))}</h2>
  <p><code>{escape(str(row['method']))}</code> / <code>{escape(str(row['variant_id']))}</code></p>
  <p>{escape(change)}</p>
  <a href="{escape(overlay)}"><img src="{escape(preview)}" alt="Raw unclassified segmentation preview"></a>
  <p>Descriptive geometry: ROI {row['roi_count']}; foreground {float(row['foreground_fraction']):.4f}; area min/median/max {row['roi_area_min_pixels']} / {row['roi_area_median_pixels']} / {row['roi_area_max_pixels']} px.</p>
  <p>Operational timing only: segmentation engine {float(row['segmentation_execution_seconds']):.6f} s. Not a scientific comparison.</p>
</article>'''
        )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Module 7 explicit OFAT visual review</title>
<style>body{{font-family:Arial,sans-serif;margin:24px;background:#f2f4f7;color:#17202a}}.notice{{background:#fff3cd;border:1px solid #e1b84b;padding:14px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(460px,1fr));gap:18px;margin-top:20px}}.card{{background:white;border:1px solid #ccd3da;padding:14px}}img{{width:100%;height:auto;background:#111820}}code{{font-size:.9em}}</style></head>
<body><h1>Module 7 explicit OFAT visual review</h1>
<div class="notice"><strong>Scope:</strong> {escape(scope_statement)} These artifacts do not rank methods, classify variants, or approve a profile. The D046 review ledger was not used or changed.</div>
<p>Selection: <code>{escape(plan.selection_id)}</code>. Fields: {len(plan.fields)}. Explicit variants: {len(plan.variants)}. Runs: {len(artifacts)}.</p>
<p>Audit files: <a href="selection.json">selection.json</a>, <a href="runs.csv">runs.csv</a>, <a href="review_observations.csv">review_observations.csv</a>, <a href="manifest.json">manifest.json</a>.</p>
<main class="grid">{''.join(cards)}</main></body></html>
'''


def manifest_payload(
    root: Path,
    plan: SegmentationBenchmarkReviewPlan,
    run_rows: list[dict[str, object]],
    scope_statement: str,
) -> dict[str, object]:
    files = sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "manifest.json"
    )
    return {
        "selection_id": plan.selection_id,
        "scope_statement": scope_statement,
        "operational_timing": {
            "purpose": "operational_only_not_scientific_comparison",
            "scope": "segmentation_engine_only",
            "run_count": len(run_rows),
            "total_seconds": sum(
                float(row["segmentation_execution_seconds"]) for row in run_rows
            ),
        },
        "source_files": [
            {
                "path": str(item.selected_source_path),
                "sha256": item.selected_source_sha256,
            }
            for item in plan.fields
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


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
