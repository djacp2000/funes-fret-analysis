"""Conservative structured parsing for SlideBook auxiliary export logs."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import IssueSeverity, PipelineIssue, SourceFile

_TABLE_COLUMN_NAMES = {
    "ifd": "ifd",
    "x position (um)": "x_position_um",
    "y position (um)": "y_position_um",
    "z position (um)": "z_position_um",
    "elapsed time (ms)": "elapsed_time_ms",
    "channel name": "channel_name",
    "tiff file name": "tiff_filename",
}


@dataclass(frozen=True, slots=True)
class SlideBookLogRow:
    """One preserved row from the tab-separated SlideBook TIFF table."""

    line_number: int
    ifd: int | None
    x_position_um: float | None
    y_position_um: float | None
    z_position_um: float | None
    elapsed_time_ms: float | None
    channel_name: str | None
    tiff_filename: str
    raw_line: str


@dataclass(frozen=True, slots=True)
class SlideBookLogMetadata:
    """Structured fields useful for audit and future downstream export."""

    export_datetime: str | None
    capture_datetime: str | None
    z_planes: int | None
    time_points: int | None
    channel_count: int | None
    microns_per_pixel: float | None
    z_step_size_microns: float | None
    average_timelapse_interval: str | None
    rows: tuple[SlideBookLogRow, ...]


def parse_slidebook_log_metadata(
    source: SourceFile,
    raw_text: str,
) -> tuple[SlideBookLogMetadata | None, tuple[PipelineIssue, ...]]:
    """Parse a recognized SlideBook `.log` while preserving raw input elsewhere."""

    if source.path.suffix.casefold() != ".log":
        return None, ()

    lines = raw_text.splitlines()
    table = _find_table(lines)
    if table is None:
        return None, ()

    header_values = _parse_header_values(lines[: table.line_index])
    rows = _parse_table_rows(lines, table)
    channel_count = _parse_int(header_values.get("channels"))
    issues = _channel_count_issues(source, channel_count)
    return (
        SlideBookLogMetadata(
            export_datetime=header_values.get("export date-time"),
            capture_datetime=header_values.get("capture date-time"),
            z_planes=_parse_int(header_values.get("z planes")),
            time_points=_parse_int(header_values.get("time points")),
            channel_count=channel_count,
            microns_per_pixel=_parse_float(header_values.get("microns per pixel")),
            z_step_size_microns=_parse_float(header_values.get("z step size microns")),
            average_timelapse_interval=header_values.get("average timelapse interval"),
            rows=rows,
        ),
        issues,
    )


@dataclass(frozen=True, slots=True)
class _TableHeader:
    line_index: int
    columns: dict[str, int]


def _find_table(lines: list[str]) -> _TableHeader | None:
    for line_index, line in enumerate(lines):
        columns = [value.strip().casefold() for value in line.split("\t")]
        if "tiff file name" not in columns:
            continue
        return _TableHeader(
            line_index=line_index,
            columns={
                field_name: columns.index(column_name)
                for column_name, field_name in _TABLE_COLUMN_NAMES.items()
                if column_name in columns
            },
        )
    return None


def _parse_header_values(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", maxsplit=1)
        normalized_key = key.strip().casefold()
        normalized_value = value.strip()
        if normalized_key and normalized_value and normalized_key not in values:
            values[normalized_key] = normalized_value
    return values


def _parse_table_rows(lines: list[str], table: _TableHeader) -> tuple[SlideBookLogRow, ...]:
    rows: list[SlideBookLogRow] = []
    for line_index, raw_line in enumerate(lines[table.line_index + 1 :], start=table.line_index + 2):
        if not raw_line.strip():
            continue
        values = [value.strip() for value in raw_line.split("\t")]
        tiff_filename = _column_value(values, table.columns, "tiff_filename")
        if not tiff_filename:
            continue
        rows.append(
            SlideBookLogRow(
                line_number=line_index,
                ifd=_parse_int(_column_value(values, table.columns, "ifd")),
                x_position_um=_parse_float(
                    _column_value(values, table.columns, "x_position_um")
                ),
                y_position_um=_parse_float(
                    _column_value(values, table.columns, "y_position_um")
                ),
                z_position_um=_parse_float(
                    _column_value(values, table.columns, "z_position_um")
                ),
                elapsed_time_ms=_parse_float(
                    _column_value(values, table.columns, "elapsed_time_ms")
                ),
                channel_name=_column_value(values, table.columns, "channel_name"),
                tiff_filename=tiff_filename,
                raw_line=raw_line,
            )
        )
    return tuple(rows)


def _column_value(
    values: list[str],
    columns: dict[str, int],
    field_name: str,
) -> str | None:
    column_index = columns.get(field_name)
    if column_index is None or column_index >= len(values):
        return None
    return values[column_index] or None


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _channel_count_issues(
    source: SourceFile,
    channel_count: int | None,
) -> tuple[PipelineIssue, ...]:
    if channel_count is None or channel_count <= 2:
        return ()
    return (
        PipelineIssue(
            code="slidebook_log_channel_count_exceeds_supported",
            message=(
                "SlideBook log declares more than two channels; the current analysis pipeline "
                "supports only the C0/C1 pair."
            ),
            severity=IssueSeverity.WARNING,
            context={
                "path": str(source.path),
                "filename": source.original_name,
                "declared_channel_count": channel_count,
                "supported_channel_count": 2,
            },
        ),
    )
