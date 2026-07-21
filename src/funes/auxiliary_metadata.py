"""Discover and preserve auxiliary text metadata files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .contracts import Channel, IssueSeverity, PipelineIssue, SourceFile
from .file_discovery import ParsedTiffFile
from .slidebook_log_metadata import SlideBookLogMetadata, parse_slidebook_log_metadata

TEXT_METADATA_EXTENSIONS = frozenset({".txt", ".log"})
DEFAULT_TEXT_ENCODINGS = ("utf-8-sig", "utf-16", "cp1252")
_KEY_VALUE_DELIMITERS = (":", "=")
_SLIDEBOOK_TIFF_COLUMN = "tiff file name"
_SLIDEBOOK_LOG_ASSOCIATION_METHOD = "slidebook_log_tiff_table"


@dataclass(frozen=True, slots=True)
class TextMetadataEntry:
    """One conservatively parsed key/value line from an auxiliary text file."""

    line_number: int
    key: str
    value: str
    raw_line: str

    def __post_init__(self) -> None:
        if self.line_number < 1:
            raise ValueError("line_number must be one or greater")
        if not self.key.strip():
            raise ValueError("key must be a non-empty string")


@dataclass(frozen=True, slots=True)
class UnparsedTextLine:
    """A non-empty text line that was preserved but not parsed as metadata."""

    line_number: int
    text: str

    def __post_init__(self) -> None:
        if self.line_number < 1:
            raise ValueError("line_number must be one or greater")


@dataclass(frozen=True, slots=True)
class AuxiliaryMetadataFile:
    """Raw auxiliary text plus any safely parsed key/value metadata."""

    source: SourceFile
    raw_text: str
    encoding: str
    key_values: tuple[TextMetadataEntry, ...]
    unparsed_lines: tuple[UnparsedTextLine, ...]
    slidebook_log: SlideBookLogMetadata | None = None


@dataclass(frozen=True, slots=True)
class AuxiliaryMetadataDiscoveryResult:
    """Auxiliary text metadata files plus read/parse issues."""

    files: tuple[AuxiliaryMetadataFile, ...]
    issues: tuple[PipelineIssue, ...]


@dataclass(frozen=True, slots=True)
class AuxiliaryMetadataPairAssociation:
    """One auxiliary metadata file explicitly linked to a C0/C1 TIFF pair."""

    metadata_file: AuxiliaryMetadataFile
    capture: str
    position: str
    xy: str
    z_token: str
    t_token: str
    c0: ParsedTiffFile
    c1: ParsedTiffFile
    referenced_tiff_filenames: tuple[str, ...]
    method: str = _SLIDEBOOK_LOG_ASSOCIATION_METHOD


@dataclass(frozen=True, slots=True)
class AuxiliaryMetadataAssociationResult:
    """Validated pair associations plus files that could not be associated."""

    associations: tuple[AuxiliaryMetadataPairAssociation, ...]
    unassociated_files: tuple[AuxiliaryMetadataFile, ...]
    issues: tuple[PipelineIssue, ...]


def discover_auxiliary_metadata_files(
    root: Path | str,
    *,
    extensions: frozenset[str] = TEXT_METADATA_EXTENSIONS,
) -> AuxiliaryMetadataDiscoveryResult:
    """Recursively find auxiliary text metadata files under *root* and read them."""

    root_path = Path(root)
    files: list[AuxiliaryMetadataFile] = []
    issues: list[PipelineIssue] = []

    for path in sorted(_iter_text_paths(root_path, extensions), key=lambda item: str(item).casefold()):
        metadata_file, read_issues = read_auxiliary_metadata_file(path)
        issues.extend(read_issues)
        if metadata_file is not None:
            files.append(metadata_file)

    return AuxiliaryMetadataDiscoveryResult(files=tuple(files), issues=tuple(issues))


def read_auxiliary_metadata_file(
    path: Path | str,
    *,
    encodings: tuple[str, ...] = DEFAULT_TEXT_ENCODINGS,
) -> tuple[AuxiliaryMetadataFile | None, tuple[PipelineIssue, ...]]:
    """Read one auxiliary text file, preserving raw text and safe key/value lines."""

    source_path = Path(path).resolve(strict=False)
    raw_text, encoding, issue = _read_text(source_path, encodings)
    if issue is not None:
        return None, (issue,)

    source = SourceFile(path=source_path, original_name=source_path.name)
    key_values, unparsed_lines = _parse_text_metadata(raw_text)
    slidebook_log, log_issues = parse_slidebook_log_metadata(source, raw_text)
    return (
        AuxiliaryMetadataFile(
            source=source,
            raw_text=raw_text,
            encoding=encoding,
            key_values=key_values,
            unparsed_lines=unparsed_lines,
            slidebook_log=slidebook_log,
        ),
        log_issues,
    )


def associate_auxiliary_metadata_files(
    metadata_files: Iterable[AuxiliaryMetadataFile],
    tiff_files: Iterable[ParsedTiffFile],
) -> AuxiliaryMetadataAssociationResult:
    """Associate SlideBook logs using their explicit ``TIFF File Name`` table.

    Only TIFFs in the same directory as the log are eligible. Files without a
    recognizable SlideBook table remain unassociated without an issue; a
    recognized table that cannot identify exactly one complete C0/C1 pair is
    reported as an error rather than guessed from the auxiliary filename.
    """

    metadata = tuple(metadata_files)
    tiffs = tuple(tiff_files)
    index = _index_tiffs_by_directory_and_name(tiffs)
    associations: list[AuxiliaryMetadataPairAssociation] = []
    unassociated: list[AuxiliaryMetadataFile] = []
    issues: list[PipelineIssue] = []

    for metadata_file in metadata:
        references = _slidebook_log_tiff_references(metadata_file)
        if references is None:
            unassociated.append(metadata_file)
            continue
        if not references:
            unassociated.append(metadata_file)
            issues.append(
                _association_issue(
                    metadata_file,
                    code="auxiliary_metadata_log_has_no_tiff_references",
                    message="SlideBook log table has no TIFF filename references.",
                )
            )
            continue

        matched, match_issue = _match_tiff_references(metadata_file, references, index)
        if match_issue is not None:
            unassociated.append(metadata_file)
            issues.append(match_issue)
            continue

        association, validation_issue = _build_pair_association(
            metadata_file,
            references,
            matched,
        )
        if validation_issue is not None:
            unassociated.append(metadata_file)
            issues.append(validation_issue)
            continue
        assert association is not None
        associations.append(association)

    return AuxiliaryMetadataAssociationResult(
        associations=tuple(associations),
        unassociated_files=tuple(unassociated),
        issues=tuple(issues),
    )


def _iter_text_paths(root: Path, extensions: frozenset[str]) -> tuple[Path, ...]:
    normalized_extensions = frozenset(extension.casefold() for extension in extensions)
    if root.is_file():
        return (root,) if root.suffix.casefold() in normalized_extensions else ()
    if not root.exists():
        return ()
    return tuple(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.casefold() in normalized_extensions
    )


def _index_tiffs_by_directory_and_name(
    tiff_files: tuple[ParsedTiffFile, ...],
) -> dict[tuple[str, str], tuple[ParsedTiffFile, ...]]:
    indexed: dict[tuple[str, str], list[ParsedTiffFile]] = {}
    for tiff_file in tiff_files:
        key = (
            str(tiff_file.source.path.parent.resolve(strict=False)).casefold(),
            tiff_file.source.original_name.casefold(),
        )
        indexed.setdefault(key, []).append(tiff_file)
    return {key: tuple(values) for key, values in indexed.items()}


def _slidebook_log_tiff_references(
    metadata_file: AuxiliaryMetadataFile,
) -> tuple[str, ...] | None:
    if metadata_file.slidebook_log is not None:
        references: list[str] = []
        seen: set[str] = set()
        for row in metadata_file.slidebook_log.rows:
            normalized_filename = row.tiff_filename.casefold()
            if normalized_filename not in seen:
                references.append(row.tiff_filename)
                seen.add(normalized_filename)
        return tuple(references)

    if metadata_file.source.path.suffix.casefold() != ".log":
        return None

    lines = metadata_file.raw_text.splitlines()
    tiff_column: int | None = None
    header_line_index: int | None = None
    for line_index, line in enumerate(lines):
        columns = [value.strip() for value in line.split("\t")]
        normalized = [value.casefold() for value in columns]
        if _SLIDEBOOK_TIFF_COLUMN in normalized:
            tiff_column = normalized.index(_SLIDEBOOK_TIFF_COLUMN)
            header_line_index = line_index
            break
    if tiff_column is None or header_line_index is None:
        return None

    references: list[str] = []
    seen: set[str] = set()
    for line in lines[header_line_index + 1 :]:
        if not line.strip():
            continue
        columns = [value.strip() for value in line.split("\t")]
        if tiff_column >= len(columns) or not columns[tiff_column]:
            continue
        filename = columns[tiff_column]
        normalized_filename = filename.casefold()
        if normalized_filename not in seen:
            references.append(filename)
            seen.add(normalized_filename)
    return tuple(references)


def _match_tiff_references(
    metadata_file: AuxiliaryMetadataFile,
    references: tuple[str, ...],
    index: dict[tuple[str, str], tuple[ParsedTiffFile, ...]],
) -> tuple[tuple[ParsedTiffFile, ...], PipelineIssue | None]:
    directory = str(metadata_file.source.path.parent.resolve(strict=False)).casefold()
    matched: list[ParsedTiffFile] = []
    missing: list[str] = []
    ambiguous: list[str] = []
    for filename in references:
        candidates = index.get((directory, filename.casefold()), ())
        if not candidates:
            missing.append(filename)
        elif len(candidates) > 1:
            ambiguous.append(filename)
        else:
            matched.append(candidates[0])

    if missing:
        return (), _association_issue(
            metadata_file,
            code="auxiliary_metadata_tiff_reference_not_found",
            message="SlideBook log references TIFF files that were not discovered beside the log.",
            extra_context={"missing_tiff_filenames": ", ".join(missing)},
        )
    if ambiguous:
        return (), _association_issue(
            metadata_file,
            code="auxiliary_metadata_tiff_reference_ambiguous",
            message="SlideBook log TIFF references match multiple discovered files.",
            extra_context={"ambiguous_tiff_filenames": ", ".join(ambiguous)},
        )
    return tuple(matched), None


def _build_pair_association(
    metadata_file: AuxiliaryMetadataFile,
    references: tuple[str, ...],
    matched: tuple[ParsedTiffFile, ...],
) -> tuple[AuxiliaryMetadataPairAssociation | None, PipelineIssue | None]:
    identities = {
        (
            tiff.capture.casefold(),
            tiff.position.casefold(),
            tiff.xy.casefold(),
            tiff.z_token.casefold(),
            tiff.t_token.casefold(),
        )
        for tiff in matched
    }
    if len(identities) != 1:
        return None, _association_issue(
            metadata_file,
            code="auxiliary_metadata_references_multiple_tiff_pairs",
            message="SlideBook log references TIFF files from more than one parsed acquisition pair.",
            extra_context={"referenced_tiff_filenames": ", ".join(references)},
        )

    by_channel = {tiff.channel: tiff for tiff in matched}
    if set(by_channel) != {Channel.C0, Channel.C1} or len(matched) != 2:
        return None, _association_issue(
            metadata_file,
            code="auxiliary_metadata_incomplete_tiff_pair",
            message="SlideBook log must reference exactly one discovered C0 and one discovered C1 TIFF.",
            extra_context={
                "referenced_tiff_filenames": ", ".join(references),
                "matched_channels": ", ".join(sorted(channel.value for channel in by_channel)),
            },
        )

    c0 = by_channel[Channel.C0]
    c1 = by_channel[Channel.C1]
    return (
        AuxiliaryMetadataPairAssociation(
            metadata_file=metadata_file,
            capture=c0.capture,
            position=c0.position,
            xy=c0.xy,
            z_token=c0.z_token,
            t_token=c0.t_token,
            c0=c0,
            c1=c1,
            referenced_tiff_filenames=references,
        ),
        None,
    )


def _association_issue(
    metadata_file: AuxiliaryMetadataFile,
    *,
    code: str,
    message: str,
    extra_context: dict[str, str] | None = None,
) -> PipelineIssue:
    context = {
        "path": str(metadata_file.source.path),
        "filename": metadata_file.source.original_name,
    }
    if extra_context is not None:
        context.update(extra_context)
    return PipelineIssue(
        code=code,
        message=message,
        severity=IssueSeverity.ERROR,
        context=context,
    )


def _read_text(
    path: Path,
    encodings: tuple[str, ...],
) -> tuple[str, str, PipelineIssue | None]:
    errors: list[str] = []
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding), encoding, None
        except UnicodeError as exc:
            errors.append(f"{encoding}: {exc}")
        except OSError as exc:
            return "", "", _read_failed_issue(path, exc)

    return "", "", PipelineIssue(
        code="auxiliary_metadata_decode_failed",
        message="Auxiliary metadata text file could not be decoded with the configured encodings.",
        severity=IssueSeverity.ERROR,
        context={
            "path": str(path),
            "filename": path.name,
            "encodings": ", ".join(encodings),
            "errors": " | ".join(errors),
        },
    )


def _parse_text_metadata(
    raw_text: str,
) -> tuple[tuple[TextMetadataEntry, ...], tuple[UnparsedTextLine, ...]]:
    key_values: list[TextMetadataEntry] = []
    unparsed_lines: list[UnparsedTextLine] = []

    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parsed = _parse_key_value_line(line)
        if parsed is None:
            unparsed_lines.append(UnparsedTextLine(line_number=line_number, text=raw_line))
            continue
        key, value = parsed
        key_values.append(
            TextMetadataEntry(
                line_number=line_number,
                key=key,
                value=value,
                raw_line=raw_line,
            )
        )

    return tuple(key_values), tuple(unparsed_lines)


def _parse_key_value_line(line: str) -> tuple[str, str] | None:
    candidates = [(line.find(delimiter), delimiter) for delimiter in _KEY_VALUE_DELIMITERS]
    positions = [(index, delimiter) for index, delimiter in candidates if index > 0]
    if not positions:
        return None

    index, delimiter = min(positions)
    key, value = line.split(delimiter, maxsplit=1)
    key = key.strip()
    value = value.strip()
    if not key or not value:
        return None
    return key, value


def _read_failed_issue(path: Path, exc: OSError) -> PipelineIssue:
    return PipelineIssue(
        code="auxiliary_metadata_read_failed",
        message="Auxiliary metadata text file could not be read.",
        severity=IssueSeverity.ERROR,
        context={"path": str(path), "filename": path.name, "error": str(exc)},
    )
