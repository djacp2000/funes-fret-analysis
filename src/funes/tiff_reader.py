"""Read TIFF frame sequences and validate paired C0/C1 acquisitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping

import numpy as np
from numpy.typing import NDArray

from .contracts import Channel, IssueSeverity, PipelineIssue, PositionKey
from .file_discovery import ParsedTiffFile

if TYPE_CHECKING:
    from .auxiliary_metadata import AuxiliaryMetadataPairAssociation


class TiffReadError(RuntimeError):
    """Raised when a TIFF cannot be read into the internal frame sequence."""

    def __init__(self, issue: PipelineIssue) -> None:
        super().__init__(issue.message)
        self.issue = issue


@dataclass(frozen=True, slots=True)
class TiffMetadata:
    """Raw and structural TIFF metadata preserved for audit trails."""

    page_count: int
    series_axes: str | None
    series_shape: tuple[int, ...]
    imagej_metadata: str | None
    ome_metadata: str | None
    page_descriptions: tuple[str, ...]
    first_page_tags: Mapping[str, str]
    page_tags: tuple[Mapping[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "first_page_tags", MappingProxyType(dict(self.first_page_tags)))
        object.__setattr__(
            self,
            "page_tags",
            tuple(MappingProxyType(dict(tags)) for tags in self.page_tags),
        )


@dataclass(frozen=True, slots=True)
class TiffFrameSequence:
    """One TIFF standardized as ordered temporal frames with shape T, Y, X."""

    parsed_file: ParsedTiffFile
    frames: NDArray[np.generic]
    metadata: TiffMetadata

    @property
    def frame_count(self) -> int:
        return int(self.frames.shape[0])

    @property
    def height(self) -> int:
        return int(self.frames.shape[1])

    @property
    def width(self) -> int:
        return int(self.frames.shape[2])

    @property
    def dtype_name(self) -> str:
        return str(self.frames.dtype)


@dataclass(frozen=True, slots=True)
class TiffPair:
    """Validated readable C0/C1 image data for one capture and position."""

    position_key: PositionKey
    c0: TiffFrameSequence
    c1: TiffFrameSequence
    auxiliary_metadata_associations: tuple[AuxiliaryMetadataPairAssociation, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "auxiliary_metadata_associations",
            tuple(self.auxiliary_metadata_associations),
        )


@dataclass(frozen=True, slots=True)
class TiffPairValidationResult:
    """Result of reading and validating one candidate C0/C1 pair."""

    pair: TiffPair | None
    issues: tuple[PipelineIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.pair is not None and not any(
            issue.severity == IssueSeverity.ERROR for issue in self.issues
        )


@dataclass(frozen=True, slots=True)
class TiffPairValidationBatch:
    """Validated pairs plus issues for missing channels or invalid pairs."""

    pairs: tuple[TiffPair, ...]
    issues: tuple[PipelineIssue, ...]


def read_tiff_sequence(parsed_file: ParsedTiffFile) -> TiffFrameSequence:
    """Read one TIFF and return an ordered temporal frame sequence."""

    try:
        import tifffile
    except ImportError as exc:  # pragma: no cover - exercised when dependency is absent
        raise TiffReadError(
            PipelineIssue(
                code="missing_tiff_backend",
                message="The tifffile package is required to read TIFF image data.",
                severity=IssueSeverity.ERROR,
                context={"path": str(parsed_file.source.path)},
            )
        ) from exc

    path = parsed_file.source.path
    try:
        with tifffile.TiffFile(path) as tif:
            series = tif.series[0]
            array = series.asarray()
            metadata = _extract_metadata(tif, series, array)
    except Exception as exc:
        raise TiffReadError(
            PipelineIssue(
                code="tiff_read_failed",
                message="TIFF image data could not be read.",
                severity=IssueSeverity.ERROR,
                context={
                    "path": str(path),
                    "filename": parsed_file.source.original_name,
                    "error": str(exc),
                },
            )
        ) from exc

    frames = _as_temporal_frames(array, parsed_file.source.path)
    return TiffFrameSequence(parsed_file=parsed_file, frames=frames, metadata=metadata)


def validate_tiff_pair(
    c0_file: ParsedTiffFile,
    c1_file: ParsedTiffFile,
) -> TiffPairValidationResult:
    """Read and validate one C0/C1 acquisition pair."""

    issues = list(_metadata_pair_issues(c0_file, c1_file))
    if c0_file.channel is not Channel.C0:
        issues.append(_wrong_channel_issue(c0_file, Channel.C0))
    if c1_file.channel is not Channel.C1:
        issues.append(_wrong_channel_issue(c1_file, Channel.C1))

    try:
        c0 = read_tiff_sequence(c0_file)
    except TiffReadError as exc:
        c0 = None
        issues.append(exc.issue)

    try:
        c1 = read_tiff_sequence(c1_file)
    except TiffReadError as exc:
        c1 = None
        issues.append(exc.issue)

    if c0 is None or c1 is None:
        return TiffPairValidationResult(pair=None, issues=tuple(issues))

    issues.extend(_shape_pair_issues(c0, c1))
    if any(issue.severity == IssueSeverity.ERROR for issue in issues):
        return TiffPairValidationResult(pair=None, issues=tuple(issues))

    pair = TiffPair(
        position_key=PositionKey(capture=c0_file.capture, position=c0_file.position),
        c0=c0,
        c1=c1,
    )
    return TiffPairValidationResult(pair=pair, issues=tuple(issues))


def validate_tiff_pairs(files: tuple[ParsedTiffFile, ...]) -> TiffPairValidationBatch:
    """Group parsed TIFF files by acquisition identity and validate complete pairs."""

    groups: dict[tuple[str, str, str, str, str], dict[Channel, ParsedTiffFile]] = {}
    issues: list[PipelineIssue] = []
    for parsed in files:
        group = groups.setdefault(_pair_identity(parsed), {})
        if parsed.channel in group:
            issues.append(
                PipelineIssue(
                    code="duplicate_channel_in_pair",
                    message="Multiple files were provided for the same channel in one acquisition pair.",
                    severity=IssueSeverity.ERROR,
                    context={
                        "first_path": str(group[parsed.channel].source.path),
                        "duplicate_path": str(parsed.source.path),
                        "channel": parsed.channel.value,
                    },
                )
            )
            continue
        group[parsed.channel] = parsed

    pairs: list[TiffPair] = []
    for identity, channels in sorted(groups.items()):
        c0_file = channels.get(Channel.C0)
        c1_file = channels.get(Channel.C1)
        if c0_file is None or c1_file is None:
            issues.append(_missing_channel_issue(identity, c0_file, c1_file))
            continue

        result = validate_tiff_pair(c0_file, c1_file)
        issues.extend(result.issues)
        if result.pair is not None:
            pairs.append(result.pair)

    return TiffPairValidationBatch(pairs=tuple(pairs), issues=tuple(issues))


def _as_temporal_frames(array: NDArray[np.generic], path: Path) -> NDArray[np.generic]:
    if array.ndim == 2:
        return array[np.newaxis, :, :]
    if array.ndim == 3:
        return array
    raise TiffReadError(
        PipelineIssue(
            code="unsupported_tiff_shape",
            message="TIFF shape cannot yet be normalized to temporal frames.",
            severity=IssueSeverity.ERROR,
            context={"path": str(path), "shape": str(tuple(array.shape))},
        )
    )


def _extract_metadata(tif: object, series: object, array: NDArray[np.generic]) -> TiffMetadata:
    pages = tuple(getattr(tif, "pages"))
    page_tags = tuple(
        {tag.name: repr(tag.value) for tag in page.tags.values()} for page in pages
    )
    first_page_tags = page_tags[0] if page_tags else {}

    return TiffMetadata(
        page_count=len(pages),
        series_axes=getattr(series, "axes", None),
        series_shape=tuple(int(size) for size in array.shape),
        imagej_metadata=repr(getattr(tif, "imagej_metadata", None)),
        ome_metadata=getattr(tif, "ome_metadata", None),
        page_descriptions=tuple(str(getattr(page, "description", "")) for page in pages),
        first_page_tags=first_page_tags,
        page_tags=page_tags,
    )


def _metadata_pair_issues(
    c0_file: ParsedTiffFile,
    c1_file: ParsedTiffFile,
) -> tuple[PipelineIssue, ...]:
    fields = {
        "capture": (c0_file.capture, c1_file.capture),
        "position": (c0_file.position, c1_file.position),
        "XY": (c0_file.xy, c1_file.xy),
        "Z": (c0_file.z_token, c1_file.z_token),
        "T": (c0_file.t_token, c1_file.t_token),
    }
    mismatches = {
        field: f"{left} != {right}"
        for field, (left, right) in fields.items()
        if left.casefold() != right.casefold()
    }
    if not mismatches:
        return ()
    return (
        PipelineIssue(
            code="pair_filename_metadata_mismatch",
            message="C0 and C1 filenames do not describe the same acquisition.",
            severity=IssueSeverity.ERROR,
            context={
                "c0_path": str(c0_file.source.path),
                "c1_path": str(c1_file.source.path),
                **mismatches,
            },
        ),
    )


def _shape_pair_issues(
    c0: TiffFrameSequence,
    c1: TiffFrameSequence,
) -> tuple[PipelineIssue, ...]:
    issues: list[PipelineIssue] = []
    if (c0.height, c0.width) != (c1.height, c1.width):
        issues.append(
            PipelineIssue(
                code="pair_dimension_mismatch",
                message="C0 and C1 TIFF dimensions do not match.",
                severity=IssueSeverity.ERROR,
                context={
                    "c0_shape": str(tuple(c0.frames.shape)),
                    "c1_shape": str(tuple(c1.frames.shape)),
                },
            )
        )
    if c0.frame_count != c1.frame_count:
        issues.append(
            PipelineIssue(
                code="pair_frame_count_mismatch",
                message="C0 and C1 TIFF temporal frame counts do not match.",
                severity=IssueSeverity.ERROR,
                context={"c0_frames": c0.frame_count, "c1_frames": c1.frame_count},
            )
        )
    if c0.metadata.series_axes != c1.metadata.series_axes:
        issues.append(
            PipelineIssue(
                code="pair_tiff_axes_metadata_mismatch",
                message="C0 and C1 TIFF series axes metadata differ.",
                severity=IssueSeverity.WARNING,
                context={
                    "c0_axes": c0.metadata.series_axes,
                    "c1_axes": c1.metadata.series_axes,
                },
            )
        )
    return tuple(issues)


def _wrong_channel_issue(parsed_file: ParsedTiffFile, expected: Channel) -> PipelineIssue:
    return PipelineIssue(
        code="unexpected_pair_channel",
        message="Parsed TIFF file was supplied in the wrong channel position.",
        severity=IssueSeverity.ERROR,
        context={
            "path": str(parsed_file.source.path),
            "expected": expected.value,
            "actual": parsed_file.channel.value,
        },
    )


def _pair_identity(parsed_file: ParsedTiffFile) -> tuple[str, str, str, str, str]:
    return (
        parsed_file.capture.casefold(),
        parsed_file.position.casefold(),
        parsed_file.xy.casefold(),
        parsed_file.z_token.casefold(),
        parsed_file.t_token.casefold(),
    )


def _missing_channel_issue(
    identity: tuple[str, str, str, str, str],
    c0_file: ParsedTiffFile | None,
    c1_file: ParsedTiffFile | None,
) -> PipelineIssue:
    present = c0_file or c1_file
    return PipelineIssue(
        code="missing_tiff_pair_channel",
        message="A parsed TIFF acquisition is missing one required channel.",
        severity=IssueSeverity.ERROR,
        context={
            "capture": identity[0],
            "position": identity[1],
            "XY": identity[2],
            "Z": identity[3],
            "T": identity[4],
            "missing_channel": Channel.C0.value if c0_file is None else Channel.C1.value,
            "present_path": str(present.source.path) if present is not None else None,
        },
    )
