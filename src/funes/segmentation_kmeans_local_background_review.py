"""Typed D071 real-review package boundary with fail-closed publication."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from html import escape
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from numpy.typing import NDArray

from .segmentation_benchmark_artifacts import (
    export_segmentation_benchmark_overlay_png,
    export_segmentation_benchmark_overlay_svg,
)
from .segmentation_benchmark_review_package import sha256_file, write_csv, write_json
from .segmentation_engine import SegmentationEngineRecord
from .segmentation_kmeans_causal_artifacts import export_kmeans_causal_focus_svg
from .segmentation_kmeans_local_background import (
    KMeansLocalBackgroundTrace,
    _D071PackageRunnerContext,
    _LocalBackgroundExecutionScope,
    _run_kmeans_local_background_candidate_for_d071,
)
from .segmentation_kmeans_local_background_review_contracts import (
    D071_DECLARED_DESTINATION,
    D071_FIELD_KEYS,
    D071_PACKAGE_SCOPE,
    D071_REAL_FIELD_IDENTITIES,
    D071_REAL_REGIONS,
    D071_REQUIRED_REAL_AUTHORIZATION_SCOPE,
    D071_SELECTION_ID,
    D071_SYNTHETIC_AUTHORIZATION_SCOPE,
    D071ExecutionMode,
    D071FieldIdentity,
    D071RealReviewInput,
    D071RealReviewPackageError,
    D071RealReviewPlan,
    D071RealReviewResult,
    D071ReviewArtifact,
    D071ReviewAuthorization,
)


@dataclass(frozen=True, slots=True)
class _PreflightState:
    destination: Path
    staging: Path
    references: tuple[NDArray[np.int32], ...]
    source_hashes: tuple[str, ...]
    reference_hashes: tuple[str, ...]


_TRACE_ARRAYS = (
    "fit_sample_indices",
    "local_p20",
    "local_threshold_map",
    "baseline_raw_foreground",
    "candidate_raw_foreground",
    "raw_added_support",
    "control_post_morphology_pre_area",
    "candidate_post_morphology_pre_area",
    "control_final_labels",
    "candidate_final_labels",
    "immutable_reference_labels",
)


def export_d071_kmeans_local_background_review(
    plan: D071RealReviewPlan,
    output_dir: Path | str | None = None,
) -> D071RealReviewResult:
    """Execute the typed boundary once; callers cannot obtain retries or variants."""

    if not isinstance(plan, D071RealReviewPlan):
        raise TypeError("plan must be a D071RealReviewPlan")
    destination = (
        plan.authorization.publication_destination
        if output_dir is None
        else Path(output_dir).resolve()
    )
    if destination != plan.authorization.publication_destination:
        raise D071RealReviewPackageError("D071 accepts no alternate execution destination")
    preflight = _preflight(plan, destination)
    started = 0
    completed = 0
    artifacts: list[D071ReviewArtifact] = []
    run_rows: list[dict[str, object]] = []
    component_rows: list[dict[str, object]] = []
    preflight.staging.mkdir(parents=True)
    (preflight.staging / "runs").mkdir()
    try:
        write_json(preflight.staging / "selection.json", _selection_payload(plan))
        runner_context = _runner_context(plan.authorization)
        for index, (item, reference) in enumerate(
            zip(plan.inputs, preflight.references, strict=True), start=1
        ):
            run_id = f"field_{index:03d}__candidate_001"
            run_dir = preflight.staging / "runs" / run_id
            run_dir.mkdir()
            started += 1
            began = perf_counter()
            result, trace = _run_kmeans_local_background_candidate_for_d071(
                item.field.prepared_frame,
                reference,
                plan.variant,
                package_context=runner_context,
                context={"d071_selection_id": D071_SELECTION_ID, "d071_run_id": run_id},
            )
            elapsed = perf_counter() - began
            completed += 1
            for name in _TRACE_ARRAYS:
                np.save(run_dir / f"{name}.npy", getattr(trace, name), allow_pickle=False)
            overlay = export_segmentation_benchmark_overlay_svg(
                item.field.prepared_frame,
                result.label_image,
                run_dir / "full_field_overlay.svg",
                title=f"{item.field.field_key.capture} + {item.field.field_key.position}",
                subtitle="D071 local-P20 candidate | unclassified",
                context={"scope": D071_PACKAGE_SCOPE, "authorization_id": plan.authorization.authorization_id},
            ).path
            preview = export_segmentation_benchmark_overlay_png(
                item.field.prepared_frame,
                result.label_image,
                run_dir / "full_field_preview.png",
            ).path
            focus = export_kmeans_causal_focus_svg(
                item.field.prepared_frame,
                reference,
                result.label_image,
                trace.raw_added_support,
                item.review_region,
                run_dir / "focused_review.svg",
                title=f"{item.field.field_key.capture} + {item.field.field_key.position}",
            )
            trace_payload = _trace_payload(plan, item, result.engine, trace, elapsed)
            write_json(run_dir / "trace.json", trace_payload)
            row = _run_row(run_id, item, trace, elapsed)
            run_rows.append(row)
            component_rows.extend(_component_rows(run_id, trace))
            artifacts.append(
                D071ReviewArtifact(
                    run_id,
                    run_dir,
                    trace,
                    overlay,
                    preview,
                    focus,
                    elapsed,
                )
            )
        if completed != 2:
            raise RuntimeError("D071 completed-call counter did not reach exactly two")
        write_csv(preflight.staging / "runs.csv", run_rows)
        write_csv(preflight.staging / "components.csv", component_rows)
        write_csv(preflight.staging / "human_observations.csv", _blank_observations(plan))
        (preflight.staging / "index.html").write_text(
            _review_html(plan, artifacts), encoding="utf-8", newline="\n"
        )
        _verify_immutable_inputs(plan, preflight)
        _verify_saved_trace_arrays(preflight.staging, artifacts)
        manifest_path = preflight.staging / "manifest.json"
        write_json(manifest_path, _manifest_payload(preflight.staging, plan, started, completed))
        _postflight(preflight.staging, manifest_path, started, completed)
        _publish(preflight.staging, destination)
    except Exception as exc:
        error_path = preflight.staging / "incomplete_attempt.json"
        write_json(
            error_path,
            {
                "selection_id": D071_SELECTION_ID,
                "authorization_id": plan.authorization.authorization_id,
                "execution_mode": plan.authorization.execution_mode.value,
                "engine_calls_started": started,
                "engine_calls_completed": completed,
                "automatic_retry_performed": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        raise D071RealReviewPackageError(
            f"D071 attempt is incomplete and was not published: {exc}",
            engine_calls_started=started,
            engine_calls_completed=completed,
            incomplete_attempt_dir=preflight.staging,
        ) from exc

    published_artifacts = tuple(
        D071ReviewArtifact(
            item.run_id,
            destination / item.run_dir.relative_to(preflight.staging),
            item.trace,
            destination / item.full_overlay_path.relative_to(preflight.staging),
            destination / item.full_preview_path.relative_to(preflight.staging),
            destination / item.focus_sheet_path.relative_to(preflight.staging),
            item.segmentation_execution_seconds,
        )
        for item in artifacts
    )
    return D071RealReviewResult(
        output_dir=destination,
        selection_path=destination / "selection.json",
        runs_path=destination / "runs.csv",
        components_path=destination / "components.csv",
        observations_path=destination / "human_observations.csv",
        index_path=destination / "index.html",
        manifest_path=destination / "manifest.json",
        artifacts=published_artifacts,
        engine_calls_started=started,
        engine_calls_completed=completed,
    )


def _preflight(plan: D071RealReviewPlan, destination: Path) -> _PreflightState:
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise D071RealReviewPackageError("D071 final destination must be absent or empty")
    staging = destination.parent / (
        f".{destination.name}.incomplete-{plan.authorization.authorization_id}"
    )
    if staging.exists():
        raise D071RealReviewPackageError(
            "a prior D071 attempt exists for this authorization identifier",
            incomplete_attempt_dir=staging,
        )
    references: list[NDArray[np.int32]] = []
    source_hashes: list[str] = []
    reference_hashes: list[str] = []
    for item in plan.inputs:
        frame = item.field.prepared_frame
        region = item.review_region
        if region.x_stop > frame.shape[1] or region.y_stop > frame.shape[0]:
            raise D071RealReviewPackageError("D071 review region falls outside its prepared array")
        if item.field.prepared_frame_sha256 != item.expected_prepared_frame_sha256:
            raise D071RealReviewPackageError("prepared-frame SHA-256 does not match preflight")
        source = item.field.selected_source_path
        if not source.is_file():
            raise D071RealReviewPackageError(f"selected source is missing: {source}")
        source_hash = sha256_file(source)
        if source_hash != item.field.selected_source_sha256:
            raise D071RealReviewPackageError("source SHA-256 does not match preflight")
        if not item.reference_labels_path.is_file():
            raise D071RealReviewPackageError(
                f"saved area-32 reference is missing: {item.reference_labels_path}"
            )
        reference_hash = sha256_file(item.reference_labels_path)
        if reference_hash != item.reference_labels_sha256:
            raise D071RealReviewPackageError("reference SHA-256 does not match preflight")
        labels = np.load(item.reference_labels_path, allow_pickle=False)
        if (
            labels.shape != frame.shape
            or not np.issubdtype(labels.dtype, np.integer)
            or np.any(labels < 0)
        ):
            raise D071RealReviewPackageError(
                "reference must be a nonnegative integer label image matching the prepared array"
            )
        references.append(np.asarray(labels, dtype=np.int32))
        source_hashes.append(source_hash)
        reference_hashes.append(reference_hash)
    return _PreflightState(
        destination,
        staging,
        tuple(references),
        tuple(source_hashes),
        tuple(reference_hashes),
    )


def _runner_context(authorization: D071ReviewAuthorization) -> _D071PackageRunnerContext:
    scope = (
        _LocalBackgroundExecutionScope.D071_PACKAGE_SYNTHETIC
        if authorization.execution_mode is D071ExecutionMode.SYNTHETIC_CONTRACT_VERIFICATION
        else _LocalBackgroundExecutionScope.D071_AUTHORIZED_REAL_REVIEW
    )
    return _D071PackageRunnerContext(
        execution_scope=scope,
        authorization_id=authorization.authorization_id,
        authorization_scope=authorization.authorization_scope,
    )


def _selection_payload(plan: D071RealReviewPlan) -> dict[str, object]:
    return {
        "selection_id": D071_SELECTION_ID,
        "declared_destination": D071_DECLARED_DESTINATION.as_posix() + "/",
        "actual_publication_destination": str(plan.authorization.publication_destination),
        "authorization_id": plan.authorization.authorization_id,
        "authorization_scope": plan.authorization.authorization_scope,
        "execution_mode": plan.authorization.execution_mode.value,
        "scope_statement": D071_PACKAGE_SCOPE,
        "planned_engine_call_count": 2,
        "engine_call_counter_initial": 0,
        "fixed_call_order": [f"{key.capture} + {key.position}" for key in D071_FIELD_KEYS],
        "automatic_retry_authorized": False,
        "sample_sufficiency_assessed": False,
        "representativeness_assessed": False,
        "biological_classification_performed": False,
        "profile_action_performed": False,
        "global_baseline_changed": False,
        "d046_used": False,
        "variant": {
            "variant_id": plan.variant.variant_id,
            "origin": plan.variant.origin,
            "changed_parameter": plan.variant.changed_parameter,
            "baseline_value": plan.variant.baseline_value,
            "candidate_value": plan.variant.candidate_value,
            "effective_parameters": dict(plan.variant.effective_parameters),
        },
        "inputs": [_input_payload(item) for item in plan.inputs],
    }


def _input_payload(item: D071RealReviewInput) -> dict[str, object]:
    return {
        "capture": item.field.field_key.capture,
        "position": item.field.field_key.position,
        "selected_channel": item.field.selected_channel.value,
        "channel_selection_method": item.field.channel_selection_method,
        "preprocessing_method": item.field.preprocessing_method,
        "preprocessing_parameters": dict(item.field.preprocessing_parameters),
        "source_path": str(item.field.selected_source_path),
        "source_sha256": item.field.selected_source_sha256,
        "prepared_frame_sha256": item.expected_prepared_frame_sha256,
        "reference_labels_path": str(item.reference_labels_path),
        "reference_labels_sha256": item.reference_labels_sha256,
        "review_region": asdict(item.review_region),
    }


def _trace_payload(
    plan: D071RealReviewPlan,
    item: D071RealReviewInput,
    engine: SegmentationEngineRecord,
    trace: KMeansLocalBackgroundTrace,
    elapsed: float,
) -> dict[str, object]:
    return {
        **_input_payload(item),
        "authorization_id": plan.authorization.authorization_id,
        "authorization_scope": plan.authorization.authorization_scope,
        "execution_mode": plan.authorization.execution_mode.value,
        "segmentation_execution_seconds": elapsed,
        "execution_timing_scope": "segmentation_engine_only_operational",
        "engine": {
            "name": engine.name,
            "version": engine.version,
            "model": engine.model,
            "profile": engine.profile,
            "parameters": dict(engine.parameters),
            "seeds": dict(engine.seeds),
            "package_versions": dict(engine.package_versions),
        },
        "prepared_frame_sha256_from_trace": trace.prepared_frame_sha256,
        "original_cluster_centers": list(trace.original_cluster_centers),
        "ordered_cluster_centers": list(trace.ordered_cluster_centers),
        "selected_cluster_ids": list(trace.selected_cluster_ids),
        "baseline_threshold": trace.baseline_threshold,
        "field_p20": trace.field_p20,
        "local_percentile": trace.local_percentile,
        "local_percentile_method": trace.local_percentile_method,
        "local_window_side": trace.local_window_side,
        "local_window_rule": trace.local_window_rule,
        "padding_rule": trace.padding_rule,
        "stage_change_counts": dict(trace.stage_change_counts),
        "trace_array_files": [f"{name}.npy" for name in _TRACE_ARRAYS],
        "component_count": len(trace.components),
        "geometric_classes_are_biological": False,
    }


def _run_row(
    run_id: str,
    item: D071RealReviewInput,
    trace: KMeansLocalBackgroundTrace,
    elapsed: float,
) -> dict[str, object]:
    region = item.review_region
    crop = np.s_[region.y_start : region.y_stop, region.x_start : region.x_stop]
    reference = trace.immutable_reference_labels > 0
    candidate = trace.candidate_final_labels > 0
    return {
        "run_id": run_id,
        "capture": item.field.field_key.capture,
        "position": item.field.field_key.position,
        "prepared_frame_sha256": trace.prepared_frame_sha256,
        "source_sha256": item.field.selected_source_sha256,
        "reference_labels_sha256": item.reference_labels_sha256,
        **dict(trace.stage_change_counts),
        "focus_region": region.name,
        "focus_raw_added_pixels": int(np.count_nonzero(trace.raw_added_support[crop])),
        "focus_final_added_pixels": int(np.count_nonzero(candidate[crop] & ~reference[crop])),
        "focus_final_removed_pixels": int(np.count_nonzero(reference[crop] & ~candidate[crop])),
        "segmentation_execution_seconds": elapsed,
        "execution_timing_scope": "segmentation_engine_only_operational",
    }


def _component_rows(run_id: str, trace: KMeansLocalBackgroundTrace) -> list[dict[str, object]]:
    return [
        {
            "run_id": run_id,
            "stage": item.stage,
            "component_id": item.component_id,
            "area_pixels": item.area_pixels,
            "bounding_box_yx_half_open": ",".join(str(value) for value in item.bounding_box_yx_half_open),
            "touched_raw_anchor_labels": ",".join(str(value) for value in item.touched_raw_anchor_labels),
            "overlapped_reference_labels": ",".join(str(value) for value in item.overlapped_reference_labels),
            "geometric_class": item.geometric_class,
            "biological_classification": "",
        }
        for item in trace.components
    ]


def _blank_observations(plan: D071RealReviewPlan) -> list[dict[str, object]]:
    return [
        {
            "capture": item.field.field_key.capture,
            "position": item.field.field_key.position,
            "region": item.review_region.name,
            "reviewer": "",
            "reviewed_at": "",
            "wholly_omitted_cell_recovery": "",
            "existing_cell_completion": "",
            "nonspecific_addition_or_expansion": "",
            "d051_bridge_or_joint_roi_interpretation": "",
            "other_notes": "",
        }
        for item in plan.inputs
    ]


def _review_html(plan: D071RealReviewPlan, artifacts: list[D071ReviewArtifact]) -> str:
    cards = "".join(
        f'<article><h2>{escape(item.run_id)}</h2><p>'
        f'<a href="{item.focus_sheet_path.relative_to(item.run_dir.parent.parent).as_posix()}">Focused review</a> | '
        f'<a href="{item.full_overlay_path.relative_to(item.run_dir.parent.parent).as_posix()}">Full field</a></p></article>'
        for item in artifacts
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>D071 review package</title></head><body>'
        '<h1>Module 7 D071 local-background review package</h1>'
        f'<p>{escape(D071_PACKAGE_SCOPE)}</p>'
        f'<p>Authorization <code>{escape(plan.authorization.authorization_id)}</code>; '
        f'mode <code>{escape(plan.authorization.execution_mode.value)}</code>; no retry.</p>'
        f'{cards}</body></html>\n'
    )


def _verify_immutable_inputs(plan: D071RealReviewPlan, preflight: _PreflightState) -> None:
    for index, item in enumerate(plan.inputs):
        if sha256_file(item.field.selected_source_path) != preflight.source_hashes[index]:
            raise RuntimeError("source changed during D071 package execution")
        if sha256_file(item.reference_labels_path) != preflight.reference_hashes[index]:
            raise RuntimeError("reference changed during D071 package execution")
        if item.field.prepared_frame_sha256 != item.expected_prepared_frame_sha256:
            raise RuntimeError("prepared array changed during D071 package execution")


def _verify_saved_trace_arrays(root: Path, artifacts: list[D071ReviewArtifact]) -> None:
    for artifact in artifacts:
        run_dir = root / "runs" / artifact.run_id
        for name in _TRACE_ARRAYS:
            saved = np.load(run_dir / f"{name}.npy", allow_pickle=False)
            if not np.array_equal(saved, getattr(artifact.trace, name)):
                raise RuntimeError(f"saved D071 trace array does not match memory: {name}")


def _manifest_payload(
    root: Path,
    plan: D071RealReviewPlan,
    started: int,
    completed: int,
) -> dict[str, object]:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "manifest.json")
    return {
        "selection_id": D071_SELECTION_ID,
        "authorization_id": plan.authorization.authorization_id,
        "authorization_scope": plan.authorization.authorization_scope,
        "execution_mode": plan.authorization.execution_mode.value,
        "engine_calls_started": started,
        "engine_calls_completed": completed,
        "automatic_retry_performed": False,
        "source_prepared_reference_identities": [_input_payload(item) for item in plan.inputs],
        "artifacts": [
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ],
    }


def _postflight(root: Path, manifest_path: Path, started: int, completed: int) -> None:
    if started != 2 or completed != 2:
        raise RuntimeError("D071 postflight requires exactly two completed candidate calls")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    listed = {item["path"] for item in manifest["artifacts"]}
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if listed != actual:
        raise RuntimeError("D071 postflight found missing or unplanned files")
    for item in manifest["artifacts"]:
        path = root / item["path"]
        if path.stat().st_size != item["size_bytes"] or sha256_file(path) != item["sha256"]:
            raise RuntimeError("D071 postflight artifact hash mismatch")


def _publish(staging: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if any(destination.iterdir()):
            raise RuntimeError("D071 destination became nonempty before publication")
        destination.rmdir()
    staging.replace(destination)

