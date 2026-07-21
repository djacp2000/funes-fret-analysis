"""Immutable identities and typed execution contracts for the D071 boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re

from .contracts import Channel
from .segmentation_benchmark import SegmentationBenchmarkVariant
from .segmentation_benchmark_review import PreparedSegmentationBenchmarkField
from .segmentation_kmeans_causal_artifacts import KMeansCausalReviewRegion
from .segmentation_kmeans_local_background import (
    KMEANS_LOCAL_BACKGROUND_VARIANTS,
    KMeansLocalBackgroundTrace,
)
from .segmentation_selection import CapturePositionKey


D071_SELECTION_ID = "module7_kmeans_local_background_real_review_d071"
D071_DECLARED_DESTINATION = Path(
    "outputs/module7_kmeans_local_background_causal_review_d071"
)
D071_SYNTHETIC_AUTHORIZATION_SCOPE = (
    "D071 implementation-only synthetic contract verification; no real TIFF-derived "
    "candidate call or declared-destination publication is authorized."
)
D071_REQUIRED_REAL_AUTHORIZATION_SCOPE = (
    "Authorize only the D071 real-review plan "
    "module7_kmeans_local_background_real_review_d071 to write "
    "outputs/module7_kmeans_local_background_causal_review_d071/, after every "
    "preflight passes, with exactly two D069 candidate calls in the fixed order "
    "Capture 1 + Position 1 then Position 2. No retries, substitutions, additional "
    "variants, profile action, D046 action, or scientific conclusion are authorized."
)
D071_PACKAGE_SCOPE = (
    "Unclassified D071 evidence package only; no biological classification, final "
    "acceptability, profile action, D046 action, sufficiency, or representativeness."
)
D071_FIELD_KEYS = (
    CapturePositionKey("Capture 1", "Position 1"),
    CapturePositionKey("Capture 1", "Position 2"),
)
D071_REAL_REGIONS = (
    KMeansCausalReviewRegion("P1-R4", 250, 360, 510, 600),
    KMeansCausalReviewRegion("P2-R1", 95, 225, 85, 205),
)


@dataclass(frozen=True, slots=True)
class D071FieldIdentity:
    field_key: CapturePositionKey
    source_relative_path: Path
    source_sha256: str
    prepared_frame_sha256: str
    reference_relative_path: Path
    reference_sha256: str
    review_region: KMeansCausalReviewRegion


D071_REAL_FIELD_IDENTITIES = (
    D071FieldIdentity(
        D071_FIELD_KEYS[0],
        Path("raw_data/Capture 1 - Position 1_XY1757012095_Z0_T0_C1.tif"),
        "dd35903c267fb8528136fbadc4e4662bc6527ff6051a5fa1390111fca31307d8",
        "b25a71d92617853e53f23e479cb0d0e8c96467f9d2ffd4ab5513814a29fac2d7",
        Path("outputs/module7_ofat_review_20260714_kmeans/runs/field_001__variant_003/labels.npy"),
        "36ab719aec5b736f56deb1c44f9286b023536ccc906780bad8934f51ae2ba9af",
        D071_REAL_REGIONS[0],
    ),
    D071FieldIdentity(
        D071_FIELD_KEYS[1],
        Path("raw_data/Capture 1 - Position 2_XY1757012096_Z0_T0_C1.tif"),
        "c3eedf9770166c7b73a299df5d6a5f299597f0d504289b07884a3e5b64701238",
        "17b8b5261d404ff68516de4c05500e210a61b27e76dc30a42f58cc3831162e1e",
        Path("outputs/module7_ofat_review_20260714_kmeans/runs/field_002__variant_003/labels.npy"),
        "c4428d4f6f470ce00a9fbeaf57503f850237b8d5b7781b8dba259799b2c97aa3",
        D071_REAL_REGIONS[1],
    ),
)


class D071ExecutionMode(str, Enum):
    SYNTHETIC_CONTRACT_VERIFICATION = "synthetic_contract_verification"
    AUTHORIZED_REAL_REVIEW = "authorized_real_review"


class D071RealReviewPackageError(RuntimeError):
    """Fail-closed D071 error with auditable call and staging state."""

    def __init__(
        self,
        message: str,
        *,
        engine_calls_started: int = 0,
        engine_calls_completed: int = 0,
        incomplete_attempt_dir: Path | None = None,
    ) -> None:
        self.engine_calls_started = engine_calls_started
        self.engine_calls_completed = engine_calls_completed
        self.incomplete_attempt_dir = incomplete_attempt_dir
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class D071ReviewAuthorization:
    """Typed execution scope; construction alone does not execute or publish."""

    authorization_id: str
    authorization_scope: str
    execution_mode: D071ExecutionMode
    workspace_root: Path
    publication_destination: Path
    selection_id: str = D071_SELECTION_ID
    declared_destination: Path = D071_DECLARED_DESTINATION
    no_retry: bool = True

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", self.authorization_id):
            raise ValueError("authorization_id must be a filesystem-safe non-empty identifier")
        if not isinstance(self.execution_mode, D071ExecutionMode):
            raise TypeError("execution_mode must be a D071ExecutionMode")
        if self.selection_id != D071_SELECTION_ID:
            raise ValueError("D071 accepts only its exact selection identifier")
        declared = Path(self.declared_destination)
        if declared != D071_DECLARED_DESTINATION:
            raise ValueError("D071 accepts no alternate declared destination")
        if self.no_retry is not True:
            raise ValueError("D071 execution must preserve the no-retry scope")
        workspace = Path(self.workspace_root).resolve()
        publication = Path(self.publication_destination).resolve()
        canonical = (workspace / D071_DECLARED_DESTINATION).resolve()
        if self.execution_mode is D071ExecutionMode.AUTHORIZED_REAL_REVIEW:
            if self.authorization_scope != D071_REQUIRED_REAL_AUTHORIZATION_SCOPE:
                raise ValueError("real D071 execution requires the exact reviewed authorization scope")
            if publication != canonical:
                raise ValueError("real D071 execution accepts no alternate publication destination")
        else:
            if self.authorization_scope != D071_SYNTHETIC_AUTHORIZATION_SCOPE:
                raise ValueError("synthetic D071 verification requires its exact non-real scope")
            if publication == canonical:
                raise ValueError("synthetic verification cannot create the declared D071 destination")
        object.__setattr__(self, "workspace_root", workspace)
        object.__setattr__(self, "publication_destination", publication)
        object.__setattr__(self, "declared_destination", declared)


@dataclass(frozen=True, slots=True)
class D071RealReviewInput:
    """One prepared array and read-only source/reference identities."""

    field: PreparedSegmentationBenchmarkField
    expected_prepared_frame_sha256: str
    reference_labels_path: Path
    reference_labels_sha256: str
    review_region: KMeansCausalReviewRegion

    def __post_init__(self) -> None:
        if not isinstance(self.field, PreparedSegmentationBenchmarkField):
            raise TypeError("field must be a PreparedSegmentationBenchmarkField")
        if not _is_sha256(self.expected_prepared_frame_sha256):
            raise ValueError("expected_prepared_frame_sha256 must be a lowercase SHA-256 digest")
        if not _is_sha256(self.reference_labels_sha256):
            raise ValueError("reference_labels_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.review_region, KMeansCausalReviewRegion):
            raise TypeError("review_region must be a KMeansCausalReviewRegion")
        object.__setattr__(self, "reference_labels_path", Path(self.reference_labels_path).resolve())


@dataclass(frozen=True, slots=True)
class D071RealReviewPlan:
    """Exact two-input, one-candidate D071 plan."""

    authorization: D071ReviewAuthorization
    inputs: tuple[D071RealReviewInput, ...]
    variant: SegmentationBenchmarkVariant = field(
        default=KMEANS_LOCAL_BACKGROUND_VARIANTS[0]
    )

    def __post_init__(self) -> None:
        if not isinstance(self.authorization, D071ReviewAuthorization):
            raise TypeError("authorization must be a D071ReviewAuthorization")
        inputs = tuple(self.inputs)
        object.__setattr__(self, "inputs", inputs)
        if tuple(item.field.field_key for item in inputs) != D071_FIELD_KEYS:
            raise ValueError("D071 requires exactly Position 1 then Position 2, with no extra field")
        if self.variant != KMEANS_LOCAL_BACKGROUND_VARIANTS[0]:
            raise ValueError("D071 accepts only the unchanged D069 candidate")
        for item in inputs:
            if item.field.selected_channel is not Channel.C1:
                raise ValueError("D071 requires the existing C1 selection")
            if item.field.preprocessing_method != "identity_segmentation_preprocessing":
                raise ValueError("D071 requires identity preprocessing")
            if item.field.preprocessing_parameters.get("preserves_pixel_values") is not True:
                raise ValueError("D071 identity preprocessing must preserve pixel values")
        if self.authorization.execution_mode is D071ExecutionMode.AUTHORIZED_REAL_REVIEW:
            self._validate_real_identities()

    def _validate_real_identities(self) -> None:
        root = self.authorization.workspace_root
        for item, expected in zip(self.inputs, D071_REAL_FIELD_IDENTITIES, strict=True):
            if item.field.field_key != expected.field_key:
                raise ValueError("D071 real field identity is not exact")
            if item.field.selected_source_path.resolve() != (root / expected.source_relative_path).resolve():
                raise ValueError("D071 real source path does not match the reviewed plan")
            if item.field.selected_source_sha256 != expected.source_sha256:
                raise ValueError("D071 real source hash does not match the reviewed plan")
            if item.expected_prepared_frame_sha256 != expected.prepared_frame_sha256:
                raise ValueError("D071 real prepared-frame hash does not match the reviewed plan")
            if item.reference_labels_path != (root / expected.reference_relative_path).resolve():
                raise ValueError("D071 real reference path does not match the reviewed plan")
            if item.reference_labels_sha256 != expected.reference_sha256:
                raise ValueError("D071 real reference hash does not match the reviewed plan")
            if item.review_region != expected.review_region:
                raise ValueError("D071 real review region does not match the reviewed plan")
            if item.field.prepared_frame.shape != (600, 600):
                raise ValueError("D071 real prepared frames must have shape 600 x 600")


@dataclass(frozen=True, slots=True)
class D071ReviewArtifact:
    run_id: str
    run_dir: Path
    trace: KMeansLocalBackgroundTrace
    full_overlay_path: Path
    full_preview_path: Path
    focus_sheet_path: Path
    segmentation_execution_seconds: float


@dataclass(frozen=True, slots=True)
class D071RealReviewResult:
    output_dir: Path
    selection_path: Path
    runs_path: Path
    components_path: Path
    observations_path: Path
    index_path: Path
    manifest_path: Path
    artifacts: tuple[D071ReviewArtifact, ...]
    engine_calls_started: int
    engine_calls_completed: int


def _is_sha256(value: str) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))

