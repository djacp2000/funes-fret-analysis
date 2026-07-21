"""Explicit field selection and auditable visual artifacts for Module 7 OFAT runs."""

from __future__ import annotations

import hashlib
from time import perf_counter
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from .contracts import Channel, MetadataValue
from .file_discovery import discover_tiff_files
from .segmentation_benchmark import (
    PARAMETER_BENCHMARK_EXTENSION_VARIANTS,
    PARAMETER_BENCHMARK_VARIANTS,
    SegmentationBenchmarkRun,
    SegmentationBenchmarkVariant,
    run_segmentation_benchmark_variant,
)
from .segmentation_benchmark_artifacts import (
    export_segmentation_benchmark_overlay_png,
    export_segmentation_benchmark_overlay_svg,
)
from .segmentation_benchmark_review_package import (
    manifest_payload,
    review_html,
    run_row,
    selection_payload,
    sha256_file,
    write_csv,
    write_json,
    write_observations_csv,
)
from .segmentation_channel import (
    SegmentationChannelSelectionConfig,
    select_segmentation_channel,
)
from .segmentation_preprocessing import (
    IdentitySegmentationPreprocessor,
    SegmentationPreprocessingStrategy,
    preprocess_for_segmentation,
)
from .segmentation_registry import SegmentationEngineRegistry
from .segmentation_selection import CapturePositionKey
from .tiff_reader import validate_tiff_pairs


REVIEW_SCOPE_STATEMENT = (
    "Explicit visual-review set only; sample sufficiency was not assessed."
)


class SegmentationBenchmarkReviewError(RuntimeError):
    """Raised when an explicit visual-review plan cannot be prepared or exported."""


@dataclass(frozen=True, slots=True)
class PreparedSegmentationBenchmarkField:
    """One explicitly selected and already prepared first frame with provenance."""

    field_key: CapturePositionKey
    prepared_frame: NDArray[np.float64]
    selected_channel: Channel
    channel_selection_method: str
    robust_contrast_by_channel: Mapping[str, float]
    preprocessing_method: str
    preprocessing_parameters: Mapping[str, MetadataValue]
    selected_source_path: Path
    selected_source_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.field_key, CapturePositionKey):
            raise TypeError("field_key must be a CapturePositionKey")
        if not isinstance(self.selected_channel, Channel):
            raise TypeError("selected_channel must be a Channel")
        _require_text(self.channel_selection_method, "channel_selection_method")
        _require_text(self.preprocessing_method, "preprocessing_method")
        frame = np.array(self.prepared_frame, dtype=np.float64, copy=True)
        if frame.ndim != 2 or frame.size == 0 or not np.all(np.isfinite(frame)):
            raise ValueError("prepared_frame must be a non-empty finite 2D array")
        frame.setflags(write=False)
        object.__setattr__(self, "prepared_frame", frame)
        contrasts = {str(key): float(value) for key, value in self.robust_contrast_by_channel.items()}
        if set(contrasts) != {Channel.C0.value, Channel.C1.value}:
            raise ValueError("robust_contrast_by_channel must contain exactly C0 and C1")
        object.__setattr__(self, "robust_contrast_by_channel", MappingProxyType(contrasts))
        object.__setattr__(
            self,
            "preprocessing_parameters",
            MappingProxyType(dict(self.preprocessing_parameters)),
        )
        object.__setattr__(self, "selected_source_path", Path(self.selected_source_path))
        if not _is_sha256(self.selected_source_sha256):
            raise ValueError("selected_source_sha256 must be a lowercase SHA-256 digest")

    @property
    def prepared_frame_sha256(self) -> str:
        return hashlib.sha256(self.prepared_frame.tobytes(order="C")).hexdigest()


@dataclass(frozen=True, slots=True)
class SegmentationBenchmarkReviewPlan:
    """Caller-selected fields and variants; it contains no approval semantics."""

    selection_id: str
    fields: tuple[PreparedSegmentationBenchmarkField, ...]
    variants: tuple[SegmentationBenchmarkVariant, ...]
    selection_note: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.selection_id, "selection_id")
        object.__setattr__(self, "fields", tuple(self.fields))
        object.__setattr__(self, "variants", tuple(self.variants))
        if not self.fields:
            raise ValueError("an explicit benchmark review plan requires at least one field")
        if not self.variants:
            raise ValueError("an explicit benchmark review plan requires at least one variant")
        field_keys = tuple(field.field_key for field in self.fields)
        if len(field_keys) != len(set(field_keys)):
            raise ValueError("explicit benchmark review fields must be unique")
        variant_keys = tuple((item.method, item.variant_id) for item in self.variants)
        if len(variant_keys) != len(set(variant_keys)):
            raise ValueError("explicit benchmark review variants must be unique")
        canonical = {
            (item.method, item.variant_id): item
            for item in (
                *PARAMETER_BENCHMARK_VARIANTS,
                *PARAMETER_BENCHMARK_EXTENSION_VARIANTS,
            )
        }
        for variant in self.variants:
            if canonical.get((variant.method, variant.variant_id)) != variant:
                raise ValueError(
                    "review variants must be unchanged members of an authorized OFAT catalog"
                )
        if self.selection_note is not None:
            _require_text(self.selection_note, "selection_note")


@dataclass(frozen=True, slots=True)
class SegmentationBenchmarkReviewArtifact:
    """One executed field/variant combination and its exact saved artifacts."""

    run_id: str
    run: SegmentationBenchmarkRun
    overlay_path: Path
    preview_path: Path
    label_image_path: Path
    segmentation_execution_seconds: float


@dataclass(frozen=True, slots=True)
class SegmentationBenchmarkReviewResult:
    """Complete static review package; no scientific decision is represented."""

    output_dir: Path
    index_path: Path
    selection_path: Path
    runs_path: Path
    observations_path: Path
    manifest_path: Path
    artifacts: tuple[SegmentationBenchmarkReviewArtifact, ...]


def prepare_explicit_benchmark_review_fields(
    input_dir: Path | str,
    field_keys: Sequence[CapturePositionKey],
    *,
    channel_config: SegmentationChannelSelectionConfig | None = None,
    preprocessor: SegmentationPreprocessingStrategy | None = None,
) -> tuple[PreparedSegmentationBenchmarkField, ...]:
    """Prepare only caller-identified fields using Modules 1, 2, 5, and 6."""

    input_path = Path(input_dir)
    if not input_path.is_dir():
        raise SegmentationBenchmarkReviewError(
            f"benchmark review input directory does not exist: {input_path}"
        )
    keys = tuple(field_keys)
    if not keys:
        raise ValueError("at least one explicit Capture + Position is required")
    if any(not isinstance(key, CapturePositionKey) for key in keys):
        raise TypeError("field_keys must contain CapturePositionKey values")
    if len(keys) != len(set(keys)):
        raise ValueError("explicit benchmark review field keys must be unique")

    discovery = discover_tiff_files(input_path)
    active_preprocessor = preprocessor or IdentitySegmentationPreprocessor()
    prepared: list[PreparedSegmentationBenchmarkField] = []
    for key in keys:
        selected_files = tuple(
            item
            for item in discovery.files
            if item.capture.casefold() == key.capture.casefold()
            and item.position.casefold() == key.position.casefold()
        )
        if not selected_files:
            raise SegmentationBenchmarkReviewError(
                "no parsed TIFF files matched the explicit benchmark review field: "
                f"{key.capture} + {key.position}"
            )
        validation = validate_tiff_pairs(selected_files)
        if len(validation.pairs) != 1:
            issue_codes = ", ".join(issue.code for issue in validation.issues) or "none"
            raise SegmentationBenchmarkReviewError(
                "explicit benchmark review field did not resolve to exactly one valid "
                f"C0/C1 pair: {key.capture} + {key.position}; issues: {issue_codes}"
            )
        pair = validation.pairs[0]
        selection = select_segmentation_channel(pair, channel_config)
        sequence = pair.c0 if selection.selected_channel is Channel.C0 else pair.c1
        context: dict[str, MetadataValue] = {
            "capture": key.capture,
            "position": key.position,
            "purpose": "module7_explicit_ofat_visual_review",
        }
        preprocessing = preprocess_for_segmentation(
            sequence.frames[0],
            strategy=active_preprocessor,
            context=context,
        )
        source_path = sequence.parsed_file.source.path
        prepared.append(
            PreparedSegmentationBenchmarkField(
                field_key=key,
                prepared_frame=preprocessing.processed_frame,
                selected_channel=selection.selected_channel,
                channel_selection_method=selection.method,
                robust_contrast_by_channel={
                    channel.value: metrics.robust_contrast
                    for channel, metrics in selection.metrics.items()
                },
                preprocessing_method=preprocessing.method,
                preprocessing_parameters=preprocessing.parameters,
                selected_source_path=source_path,
                selected_source_sha256=sha256_file(source_path),
            )
        )
    return tuple(prepared)


def export_segmentation_benchmark_review(
    plan: SegmentationBenchmarkReviewPlan,
    output_dir: Path | str,
    *,
    registry: SegmentationEngineRegistry | None = None,
) -> SegmentationBenchmarkReviewResult:
    """Execute exactly the plan's field/variant product and write a static package."""

    if not isinstance(plan, SegmentationBenchmarkReviewPlan):
        raise TypeError("plan must be a SegmentationBenchmarkReviewPlan")
    destination = Path(output_dir)
    if destination.exists() and any(destination.iterdir()):
        raise SegmentationBenchmarkReviewError(
            f"benchmark review output directory must be absent or empty: {destination}"
        )
    destination.mkdir(parents=True, exist_ok=True)
    runs_dir = destination / "runs"
    runs_dir.mkdir()

    selection_path = destination / "selection.json"
    write_json(selection_path, selection_payload(plan, REVIEW_SCOPE_STATEMENT))

    artifacts: list[SegmentationBenchmarkReviewArtifact] = []
    run_rows: list[dict[str, object]] = []
    for field_index, selected_field in enumerate(plan.fields, start=1):
        for variant_index, variant in enumerate(plan.variants, start=1):
            run_id = f"field_{field_index:03d}__variant_{variant_index:03d}"
            run_dir = runs_dir / run_id
            run_dir.mkdir()
            execution_started = perf_counter()
            run = run_segmentation_benchmark_variant(
                selected_field.prepared_frame,
                selected_field.field_key,
                variant,
                registry=registry,
                context={
                    "review_selection_id": plan.selection_id,
                    "review_run_id": run_id,
                    "selected_channel": selected_field.selected_channel.value,
                    "preprocessing_method": selected_field.preprocessing_method,
                },
            )
            segmentation_execution_seconds = perf_counter() - execution_started
            labels_path = run_dir / "labels.npy"
            np.save(labels_path, run.segmentation.label_image, allow_pickle=False)
            overlay_path = run_dir / "overlay.svg"
            export_segmentation_benchmark_overlay_svg(
                selected_field.prepared_frame,
                run.segmentation.label_image,
                overlay_path,
                title=f"{selected_field.field_key.capture} + {selected_field.field_key.position}",
                subtitle=f"{variant.method.value} | {variant.variant_id}",
                context={
                    "selected_channel": selected_field.selected_channel.value,
                    "changed_parameter": variant.changed_parameter,
                    "candidate_value": variant.candidate_value,
                },
            )
            preview_path = run_dir / "preview.png"
            export_segmentation_benchmark_overlay_png(
                selected_field.prepared_frame,
                run.segmentation.label_image,
                preview_path,
            )
            artifact = SegmentationBenchmarkReviewArtifact(
                run_id=run_id,
                run=run,
                overlay_path=overlay_path,
                preview_path=preview_path,
                label_image_path=labels_path,
                segmentation_execution_seconds=segmentation_execution_seconds,
            )
            artifacts.append(artifact)
            run_rows.append(run_row(artifact, selected_field, destination))

    runs_path = destination / "runs.csv"
    write_csv(runs_path, run_rows)
    observations_path = destination / "review_observations.csv"
    write_observations_csv(observations_path, run_rows)
    index_path = destination / "index.html"
    index_path.write_text(
        review_html(
            plan,
            artifacts,
            run_rows,
            destination,
            REVIEW_SCOPE_STATEMENT,
        ),
        encoding="utf-8",
        newline="\n",
    )
    manifest_path = destination / "manifest.json"
    write_json(
        manifest_path,
        manifest_payload(destination, plan, run_rows, REVIEW_SCOPE_STATEMENT),
    )
    return SegmentationBenchmarkReviewResult(
        output_dir=destination,
        index_path=index_path,
        selection_path=selection_path,
        runs_path=runs_path,
        observations_path=observations_path,
        manifest_path=manifest_path,
        artifacts=tuple(artifacts),
    )


def _is_sha256(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
