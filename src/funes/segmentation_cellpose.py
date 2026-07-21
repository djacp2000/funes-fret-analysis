"""Lazy optional Cellpose CP-SAM adapter for Module 7."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from .contracts import IssueSeverity, MetadataValue, PipelineIssue
from .segmentation_engine import (
    SegmentationEngineRecord,
    SegmentationEngineUnavailableError,
    SegmentationResult,
    _installed_package_versions,
    _validated_float_frame,
)
from .segmentation_selection import (
    SegmentationMethodId,
    SegmentationSelectionProvenance,
)


CELLPOSE_CPU_WARNING = (
    "CP-SAM required approximately 46-55 minutes per 600x600 field on CPU in "
    "the FUNES benchmark and its weights require approximately 1.15 GB."
)


@dataclass(frozen=True, slots=True)
class CellposeCPSamConfig:
    pretrained_model: str = "cpsam_v2"
    gpu: bool = False
    diameter: float | None = None
    normalize: bool = True
    augment: bool = False
    batch_size: int = 1
    resample: bool = True
    flow_threshold: float = 0.4
    cellprob_threshold: float = 0.0
    minimum_object_area_pixels: int = 15
    max_size_fraction: float = 0.4
    tile_overlap: float = 0.1
    random_seed: int = 1729
    torch_threads: int = 1

    def __post_init__(self) -> None:
        if not self.pretrained_model.strip():
            raise ValueError("pretrained_model must be a non-empty string")
        if self.diameter is not None and self.diameter <= 0:
            raise ValueError("diameter must be greater than zero when present")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        if self.minimum_object_area_pixels <= 0:
            raise ValueError("minimum_object_area_pixels must be greater than zero")
        if not 0 < self.max_size_fraction <= 1:
            raise ValueError("max_size_fraction must be within (0, 1]")
        if not 0 <= self.tile_overlap <= 1:
            raise ValueError("tile_overlap must be within [0, 1]")
        if self.torch_threads <= 0:
            raise ValueError("torch_threads must be greater than zero")


@dataclass(frozen=True, slots=True)
class CellposeCPSamSegmentationEngine:
    """Adapter that imports Cellpose/PyTorch only when CP-SAM is executed."""

    config: CellposeCPSamConfig = field(default_factory=CellposeCPSamConfig)
    profile: str | None = None
    selection: SegmentationSelectionProvenance | None = None

    @property
    def record(self) -> SegmentationEngineRecord:
        return self._record()

    def _record(self) -> SegmentationEngineRecord:
        return SegmentationEngineRecord(
            name="cellpose_cpsam",
            version="1.0",
            model=self.config.pretrained_model,
            method=SegmentationMethodId.CELLPOSE_CPSAM,
            profile=self.profile,
            selection=self.selection,
            parameters={
                "package": "cellpose",
                "model_description": "Cellpose-SAM generalist whole-cell model (CP-SAM)",
                "pretrained_model": self.config.pretrained_model,
                "gpu": self.config.gpu,
                "channels": "single_selected_grayscale_channel_[0,0]",
                "diameter": self.config.diameter,
                "normalize": self.config.normalize,
                "augment": self.config.augment,
                "batch_size": self.config.batch_size,
                "resample": self.config.resample,
                "flow_threshold": self.config.flow_threshold,
                "cellprob_threshold": self.config.cellprob_threshold,
                "minimum_object_area_pixels": self.config.minimum_object_area_pixels,
                "max_size_fraction": self.config.max_size_fraction,
                "tile_overlap": self.config.tile_overlap,
                "torch_threads": self.config.torch_threads,
                "torch_deterministic_algorithms": "enabled_warn_only",
                "postprocessing": "none;canonicalize_positive_labels_only",
                "resource_warning": CELLPOSE_CPU_WARNING,
            },
            seeds={
                "numpy_random_seed": self.config.random_seed,
                "torch_manual_seed": self.config.random_seed,
            },
            package_versions=_installed_package_versions(
                "funes", "numpy", "cellpose", "torch"
            ),
        )

    def segment(
        self,
        frame: NDArray[np.generic],
        context: Mapping[str, MetadataValue] | None = None,
    ) -> SegmentationResult:
        values = _validated_float_frame(frame)
        try:
            import_module("cellpose")
            torch = import_module("torch")
            models = import_module("cellpose.models")
        except (ImportError, ModuleNotFoundError) as exc:
            raise _unavailable("the optional Cellpose/PyTorch dependency is not installed") from exc

        np.random.seed(self.config.random_seed)
        torch.manual_seed(self.config.random_seed)
        torch.set_num_threads(self.config.torch_threads)
        torch.use_deterministic_algorithms(True, warn_only=True)
        try:
            model = models.CellposeModel(
                gpu=self.config.gpu,
                pretrained_model=self.config.pretrained_model,
            )
            evaluated = model.eval(
                values,
                batch_size=self.config.batch_size,
                resample=self.config.resample,
                channels=[0, 0],
                diameter=self.config.diameter,
                normalize=self.config.normalize,
                flow_threshold=self.config.flow_threshold,
                cellprob_threshold=self.config.cellprob_threshold,
                min_size=self.config.minimum_object_area_pixels,
                max_size_fraction=self.config.max_size_fraction,
                augment=self.config.augment,
                tile_overlap=self.config.tile_overlap,
            )
        except Exception as exc:
            raise _unavailable(
                f"CP-SAM model '{self.config.pretrained_model}' or its weights could not be loaded/run: {exc}"
            ) from exc

        masks = evaluated[0] if isinstance(evaluated, tuple) else evaluated
        labels = _canonicalize_labels(np.asarray(masks))
        roi_count = int(np.count_nonzero(np.unique(labels) > 0))
        issues: list[PipelineIssue] = [
            PipelineIssue(
                code="cellpose_cpsam_cpu_resource_warning",
                message=CELLPOSE_CPU_WARNING,
                severity=IssueSeverity.WARNING,
                context={
                    **dict(context or {}),
                    "segmentation_profile": self.profile,
                    "gpu": self.config.gpu,
                },
            )
        ]
        if roi_count == 0:
            issues.append(
                PipelineIssue(
                    code="segmentation_no_foreground",
                    message="Segmentation produced no foreground ROIs.",
                    severity=IssueSeverity.WARNING,
                    context={
                        **dict(context or {}),
                        "segmentation_method": SegmentationMethodId.CELLPOSE_CPSAM.value,
                        "segmentation_profile": self.profile,
                    },
                )
            )
        return SegmentationResult(
            label_image=labels,
            roi_count=roi_count,
            engine=self._record(),
            issues=tuple(issues),
        )


def _unavailable(reason: str) -> SegmentationEngineUnavailableError:
    return SegmentationEngineUnavailableError(
        SegmentationMethodId.CELLPOSE_CPSAM,
        reason,
        (
            "Install the optional extra with 'pip install -e .[cellpose]' and ensure "
            f"the cpsam_v2 weights are accessible. {CELLPOSE_CPU_WARNING}"
        ),
    )


def _canonicalize_labels(labels: NDArray[np.generic]) -> NDArray[np.int32]:
    source = np.asarray(labels)
    if source.ndim != 2 or source.size == 0:
        raise ValueError("Cellpose returned a label image that is not non-empty 2D")
    if not np.issubdtype(source.dtype, np.integer):
        source = source.astype(np.int64)
    if np.any(source < 0):
        raise ValueError("Cellpose returned negative labels")
    flat = source.ravel()
    positive_flat = flat[flat > 0]
    result = np.zeros(source.shape, dtype=np.int32)
    if positive_flat.size == 0:
        return result
    positive, first_indices = np.unique(positive_flat, return_index=True)
    first_seen_order = positive[np.argsort(first_indices)]
    for new_label, old_label in enumerate(first_seen_order, start=1):
        result[source == old_label] = new_label
    return result
