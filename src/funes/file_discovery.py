"""Discover TIFF source files and parse SlideBook-style filenames."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .contracts import Channel, IssueSeverity, PipelineIssue, SourceFile

TIFF_EXTENSIONS = frozenset({".tif", ".tiff"})

_FILENAME_CORE_PATTERN = re.compile(
    r"(?P<capture>Capture\s+\d+)\s*-\s*"
    r"(?P<position>Position\s+\d+)_"
    r"(?P<xy>XY[^_]+)_"
    r"(?P<z_token>Z[^_]+)_"
    r"(?P<t_token>T[^_]+)_"
    r"(?P<channel>C[01])",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ParsedTiffFile:
    """Filename-derived metadata for one TIFF without reading image pixels."""

    source: SourceFile
    capture: str
    position: str
    xy: str
    z_token: str
    t_token: str
    channel: Channel

    @property
    def identity(self) -> tuple[str, str, str, str, str, Channel]:
        """Identity used to detect duplicate channel files."""

        return (
            self.capture.casefold(),
            self.position.casefold(),
            self.xy.casefold(),
            self.z_token.casefold(),
            self.t_token.casefold(),
            self.channel,
        )


@dataclass(frozen=True, slots=True)
class FileDiscoveryResult:
    """Parsed TIFF candidates plus audit issues for malformed names or duplicates."""

    files: tuple[ParsedTiffFile, ...]
    issues: tuple[PipelineIssue, ...]


def discover_tiff_files(root: Path | str) -> FileDiscoveryResult:
    """Recursively find TIFF files under *root* and parse their filenames."""

    root_path = Path(root)
    parsed_files: list[ParsedTiffFile] = []
    issues: list[PipelineIssue] = []

    for path in sorted(_iter_tiff_paths(root_path), key=lambda candidate: str(candidate).casefold()):
        parsed = parse_tiff_filename(path)
        if parsed is None:
            issues.append(_malformed_issue(path))
        else:
            parsed_files.append(parsed)

    issues.extend(_duplicate_issues(parsed_files))
    return FileDiscoveryResult(files=tuple(parsed_files), issues=tuple(issues))


def parse_tiff_filename(path: Path | str) -> ParsedTiffFile | None:
    """Parse one SlideBook filename core while preserving outer name text.

    The ``Capture N - Position M_..._C0/C1`` core supplies the acquisition
    identity.  Export systems may add arbitrary descriptive text before that
    core or between its channel token and the TIFF extension; both parts are
    retained as source metadata and never influence pairing.
    """

    source_path = Path(path).resolve(strict=False)
    if source_path.suffix.casefold() not in TIFF_EXTENSIONS:
        return None

    stem = source_path.name[: -len(source_path.suffix)]
    matches = tuple(_FILENAME_CORE_PATTERN.finditer(stem))
    if len(matches) != 1:
        return None
    match = matches[0]

    channel = Channel(match.group("channel").upper())
    metadata = {
        "capture": _normalize_label(match.group("capture")),
        "position": _normalize_label(match.group("position")),
        "XY": match.group("xy"),
        "Z": match.group("z_token"),
        "T": match.group("t_token"),
        "channel": channel.value,
        "filename_prefix": stem[: match.start()],
        "filename_suffix": stem[match.end() :],
    }
    source = SourceFile(
        path=source_path,
        original_name=source_path.name,
        metadata=metadata,
    )
    return ParsedTiffFile(
        source=source,
        capture=metadata["capture"],
        position=metadata["position"],
        xy=metadata["XY"],
        z_token=metadata["Z"],
        t_token=metadata["T"],
        channel=channel,
    )


def _iter_tiff_paths(root: Path) -> tuple[Path, ...]:
    if root.is_file():
        return (root,) if root.suffix.casefold() in TIFF_EXTENSIONS else ()
    if not root.exists():
        return ()
    return tuple(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.casefold() in TIFF_EXTENSIONS
    )


def _normalize_label(value: str) -> str:
    return " ".join(value.strip().split())


def _malformed_issue(path: Path) -> PipelineIssue:
    return PipelineIssue(
        code="malformed_tiff_filename",
        message="TIFF filename does not match the expected SlideBook export pattern.",
        severity=IssueSeverity.ERROR,
        context={"path": str(path), "filename": path.name},
    )


def _duplicate_issues(files: list[ParsedTiffFile]) -> tuple[PipelineIssue, ...]:
    seen: dict[tuple[str, str, str, str, str, Channel], ParsedTiffFile] = {}
    issues: list[PipelineIssue] = []
    for parsed in files:
        prior = seen.get(parsed.identity)
        if prior is None:
            seen[parsed.identity] = parsed
            continue
        issues.append(
            PipelineIssue(
                code="duplicate_tiff_filename_identity",
                message="Multiple TIFF files have the same parsed capture, position, XY, Z, T, and channel.",
                severity=IssueSeverity.ERROR,
                context={
                    "first_path": str(prior.source.path),
                    "duplicate_path": str(parsed.source.path),
                    "capture": parsed.capture,
                    "position": parsed.position,
                    "XY": parsed.xy,
                    "Z": parsed.z_token,
                    "T": parsed.t_token,
                    "channel": parsed.channel.value,
                },
            )
        )
    return tuple(issues)
