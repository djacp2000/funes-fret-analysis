"""Module 14 Excel workbook export for analyzed FRET experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from .auxiliary_metadata import AuxiliaryMetadataFile, AuxiliaryMetadataPairAssociation
from .contracts import Channel, MetadataValue, PipelineIssue, PositionKey
from .fret_calculation import (
    FretCalculationRecord,
    FretCalculationResult,
    FretCalculationStatus,
)
from .intensity_qc import IntensityQcRecord, IntensityQcResult, IntensityQcStatus
from .quantitative_background import QuantitativeBackgroundResult
from .roi_geometry import RoiFilteringResult
from .slidebook_log_metadata import SlideBookLogRow
from .temporal_intensity import TemporalIntensityRecord, TemporalIntensityResult
from .tiff_reader import TiffPair


VALUE_SHEETS = (
    ("ratio", "Ratio", "ratio", "0.000"),
    ("r_over_r0", "R/R0", "normalized_ratio", "0.000"),
    ("delta_r_over_r0", "Delta R/R0", "delta_ratio_over_baseline", "0.000"),
    ("donor_corrected", "Donor corrected mean", "donor_value", "0.0"),
    ("fret_corrected", "FRET-channel corrected mean", "fret_value", "0.0"),
    ("qc_status", "QC status", "qc_status", "@"),
)


@dataclass(frozen=True, slots=True)
class Module14PositionExport:
    """Current upstream records for one Experiment > Capture > Position site."""

    position_key: PositionKey
    roi_filtering: RoiFilteringResult
    background: QuantitativeBackgroundResult
    intensity_qc: IntensityQcResult
    temporal_intensity: TemporalIntensityResult
    fret: FretCalculationResult
    pair: TiffPair | None = None
    auxiliary_metadata: tuple[AuxiliaryMetadataFile, ...] = ()
    issues: tuple[PipelineIssue, ...] = ()
    mask_source: str = "automatic"
    revision_sha256: str | None = None

    def __post_init__(self) -> None:
        required_results = (
            ("roi_filtering", self.roi_filtering, RoiFilteringResult),
            ("background", self.background, QuantitativeBackgroundResult),
            ("intensity_qc", self.intensity_qc, IntensityQcResult),
            ("temporal_intensity", self.temporal_intensity, TemporalIntensityResult),
            ("fret", self.fret, FretCalculationResult),
        )
        for field_name, result, result_type in required_results:
            if not isinstance(result, result_type):
                raise TypeError(f"{field_name} must be a {result_type.__name__}")
        if self.position_key.experiment is None:
            raise ValueError("Module 14 export requires an experiment label")
        if self.mask_source not in {"automatic", "manual_revision"}:
            raise ValueError("mask_source must be automatic or manual_revision")
        if self.mask_source == "automatic" and self.revision_sha256 is not None:
            raise ValueError("automatic masks cannot have revision_sha256")
        if self.mask_source == "manual_revision" and not self.revision_sha256:
            raise ValueError("manual_revision masks require revision_sha256")
        object.__setattr__(self, "auxiliary_metadata", tuple(self.auxiliary_metadata))
        object.__setattr__(self, "issues", tuple(self.issues))


@dataclass(frozen=True, slots=True)
class Module14ExportResult:
    """Paths created by the Module 14 exporter."""

    workbook_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class _Cell:
    value: object = None
    style: int = 0


@dataclass(frozen=True, slots=True)
class _Sheet:
    name: str
    rows: tuple[tuple[_Cell, ...], ...]
    column_widths: Mapping[int, float]
    merges: tuple[str, ...] = ()
    freeze_rows: int = 0
    freeze_cols: int = 0


@dataclass(frozen=True, slots=True)
class _ExportColumn:
    kind: str
    capture: str | None = None
    position: str | None = None
    roi_label: int | None = None


def export_module14_workbooks(
    positions: Iterable[Module14PositionExport],
    output_dir: Path | str,
) -> Module14ExportResult:
    """Create one accepted D032 `.xlsx` workbook per experiment."""

    position_exports = tuple(positions)
    if not position_exports:
        raise ValueError("Module 14 export requires at least one position")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    for experiment, experiment_positions in _positions_by_experiment(position_exports):
        workbook = _build_experiment_workbook(experiment, experiment_positions)
        path = output_path / f"{_safe_file_stem(experiment)}.xlsx"
        _write_xlsx(path, workbook)
        created.append(path)

    return Module14ExportResult(workbook_paths=tuple(created))


def _positions_by_experiment(
    positions: tuple[Module14PositionExport, ...],
) -> tuple[tuple[str, tuple[Module14PositionExport, ...]], ...]:
    grouped: dict[str, list[Module14PositionExport]] = {}
    for position in positions:
        assert position.position_key.experiment is not None
        grouped.setdefault(position.position_key.experiment, []).append(position)
    return tuple(
        (experiment, tuple(sorted(items, key=_position_sort_key)))
        for experiment, items in sorted(grouped.items(), key=lambda item: _natural_key(item[0]))
    )


def _build_experiment_workbook(
    experiment: str,
    positions: tuple[Module14PositionExport, ...],
) -> tuple[_Sheet, ...]:
    columns = _build_columns(positions)
    sheets = [
        _build_value_sheet(experiment, positions, columns, *sheet_spec)
        for sheet_spec in VALUE_SHEETS
    ]
    sheets.extend(
        (
            _overview_sheet(experiment, positions),
            _fret_long_sheet(positions),
            _intensity_long_sheet(positions),
            _roi_summary_sheet(positions),
            _background_long_sheet(positions),
            _qc_long_sheet(positions),
            _metadata_sheet(positions),
            _parameters_sheet(positions),
            _issues_sheet(positions),
            _roi_provenance_sheet(positions),
        )
    )
    return tuple(sheets)


def _build_columns(positions: tuple[Module14PositionExport, ...]) -> tuple[_ExportColumn, ...]:
    columns: list[_ExportColumn] = [_ExportColumn(kind="time")]
    captures = _group_by(positions, lambda item: item.position_key.capture)
    for capture_index, (capture, capture_positions) in enumerate(captures):
        if capture_index:
            columns.extend((_ExportColumn(kind="capture_spacer"), _ExportColumn(kind="capture_spacer")))
        position_groups = _group_by(capture_positions, lambda item: item.position_key.position)
        for position_index, (position, grouped_positions) in enumerate(position_groups):
            if position_index:
                columns.append(_ExportColumn(kind="position_spacer"))
            for export in grouped_positions:
                for roi_label in _roi_labels(export):
                    columns.append(
                        _ExportColumn(
                            kind="roi",
                            capture=capture,
                            position=position,
                            roi_label=roi_label,
                        )
                    )
    return tuple(columns)


def _build_value_sheet(
    experiment: str,
    positions: tuple[Module14PositionExport, ...],
    columns: tuple[_ExportColumn, ...],
    name: str,
    title: str,
    value_field: str,
    number_format: str,
) -> _Sheet:
    use_time_seconds = _has_complete_time_seconds(positions)
    row_count = 7 + len(_time_rows(positions))
    col_count = len(columns)
    rows = _empty_grid(row_count, col_count)
    last_col = _column_name(col_count)

    rows[0][0] = _Cell(f"{experiment} - {title}", 1)
    rows[1][0] = _Cell(
        "Module 14 D032 export. Rows are temporal frames; the left column uses "
        + ("elapsed seconds. " if use_time_seconds else "frame indices because elapsed time is unknown. ")
        + "Each ROI is one column. "
        "Blue spacer = position break; peach double spacer = capture break.",
        2,
    )

    for start, end, label in _header_spans(columns, "capture"):
        rows[3][start - 1] = _Cell(label, 3)
        for col in range(start + 1, end + 1):
            rows[3][col - 1] = _Cell("", 3)
    for start, end, label in _header_spans(columns, "position"):
        rows[4][start - 1] = _Cell(label, 4)
        for col in range(start + 1, end + 1):
            rows[4][col - 1] = _Cell("", 4)

    rows[5] = [
        _Cell("time_s" if use_time_seconds else "frame_index", 5) if column.kind == "time"
        else _Cell(_roi_display_label(column.roi_label), 5) if column.kind == "roi"
        else _Cell("", _spacer_style(column))
        for column in columns
    ]
    rows[6] = [
        _Cell("seconds" if use_time_seconds else "index", 6) if column.kind == "time"
        else _Cell(_roi_identity(column), 6) if column.kind == "roi"
        else _Cell("", _spacer_style(column))
        for column in columns
    ]

    record_index = _fret_record_index(positions)
    for row_offset, (frame_index, time_seconds) in enumerate(_time_rows(positions), start=7):
        rows[row_offset][0] = _Cell(
            time_seconds if use_time_seconds else frame_index,
            9,
        )
        for col_index, column in enumerate(columns[1:], start=1):
            if column.kind != "roi":
                rows[row_offset][col_index] = _Cell("", _spacer_style(column))
                continue
            key = (column.capture, column.position, column.roi_label, frame_index)
            record = record_index.get(key)
            value = _record_value(record, value_field)
            style = _qc_style(value) if value_field == "qc_status" else 9
            rows[row_offset][col_index] = _Cell(value, style)

    for row_index in range(row_count):
        for col_index, column in enumerate(columns):
            if column.kind in {"position_spacer", "capture_spacer"}:
                rows[row_index][col_index] = _Cell(rows[row_index][col_index].value, _spacer_style(column))

    widths = {1: 10.0}
    for col_index, column in enumerate(columns[1:], start=2):
        widths[col_index] = 3.0 if column.kind.endswith("spacer") else 12.0
    merges = (f"A1:{last_col}1", f"A2:{last_col}2", *_merge_refs(columns))
    return _Sheet(
        name=name,
        rows=tuple(tuple(row) for row in rows),
        column_widths=widths,
        merges=merges,
        freeze_rows=7,
        freeze_cols=1,
    )


def _overview_sheet(experiment: str, positions: tuple[Module14PositionExport, ...]) -> _Sheet:
    rows = [
        [_Cell(f"{experiment} - overview", 1), *[_Cell("", 1) for _ in range(5)]],
        [_Cell("") for _ in range(6)],
        _header(("capture", "position", "roi_count", "frame_count", "issues", "source")),
    ]
    for export in positions:
        rows.append(
            [
                _Cell(export.position_key.capture),
                _Cell(export.position_key.position),
                _Cell(len(_roi_labels(export))),
                _Cell(len(_time_rows((export,)))),
                _Cell(_issue_count(export)),
                _Cell("Module 14 current upstream records"),
            ]
        )
    return _table_sheet("overview", rows, title_merge="A1:F1")


def _fret_long_sheet(positions: tuple[Module14PositionExport, ...]) -> _Sheet:
    rows = [
        _header(
            (
                "experiment",
                "capture",
                "position",
                "roi_label",
                "frame_index",
                "time_seconds",
                "donor_channel",
                "fret_channel",
                "donor_value",
                "fret_value",
                "ratio",
                "baseline_ratio",
                "r_over_r0",
                "delta_r_over_r0",
                "ratio_status",
                "ratio_reasons",
                "normalization_status",
                "normalization_reasons",
            )
        )
    ]
    for export in positions:
        for record in export.fret.records:
            rows.append(
                [
                    _Cell(export.position_key.experiment),
                    _Cell(export.position_key.capture),
                    _Cell(export.position_key.position),
                    _Cell(record.roi_label),
                    _Cell(record.frame.frame_index),
                    _Cell(record.frame.time_seconds),
                    _Cell(record.donor_channel.value),
                    _Cell(record.fret_channel.value),
                    _Cell(record.donor_value),
                    _Cell(record.fret_value),
                    _Cell(record.ratio),
                    _Cell(record.baseline_ratio),
                    _Cell(record.normalized_ratio),
                    _Cell(record.delta_ratio_over_baseline),
                    _Cell(record.ratio_status.value),
                    _Cell(_join(record.ratio_reasons)),
                    _Cell(record.normalization_status.value),
                    _Cell(_join(record.normalization_reasons)),
                ]
            )
    return _table_sheet("fret_long", rows)


def _intensity_long_sheet(positions: tuple[Module14PositionExport, ...]) -> _Sheet:
    rows = [
        _header(
            (
                "experiment",
                "capture",
                "position",
                "roi_label",
                "channel",
                "frame_index",
                "time_seconds",
                "roi_area_pixels",
                "raw_mean",
                "raw_median",
                "background_value",
                "background_corrected_mean",
                "background_corrected_median",
                "roi_frame_qc_status",
                "roi_frame_qc_reasons",
                "field_frame_qc_status",
                "field_frame_qc_reasons",
                "roi_qc_status",
                "roi_qc_reasons",
                "field_qc_status",
                "field_qc_reasons",
            )
        )
    ]
    for export in positions:
        for record in export.temporal_intensity.records:
            rows.append(_intensity_row(export.position_key, record))
    return _table_sheet("intensity_long", rows)


def _roi_summary_sheet(positions: tuple[Module14PositionExport, ...]) -> _Sheet:
    rows = [
        _header(
            (
                "experiment",
                "capture",
                "position",
                "roi_label",
                "geometry_status",
                "geometry_reasons",
                "area_pixels",
                "touches_border",
                "bbox_min_row",
                "bbox_min_col",
                "bbox_max_row",
                "bbox_max_col",
                "centroid_row",
                "centroid_col",
            )
        )
    ]
    for export in positions:
        for record in export.roi_filtering.records:
            geometry = record.geometry
            rows.append(
                [
                    _Cell(export.position_key.experiment),
                    _Cell(export.position_key.capture),
                    _Cell(export.position_key.position),
                    _Cell(geometry.label),
                    _Cell(record.status.value),
                    _Cell(_join(record.reasons)),
                    _Cell(geometry.area_pixels),
                    _Cell(geometry.touches_border),
                    _Cell(geometry.bounding_box.min_row),
                    _Cell(geometry.bounding_box.min_col),
                    _Cell(geometry.bounding_box.max_row),
                    _Cell(geometry.bounding_box.max_col),
                    _Cell(geometry.centroid_row),
                    _Cell(geometry.centroid_col),
                ]
            )
    return _table_sheet("roi_summary", rows)


def _background_long_sheet(positions: tuple[Module14PositionExport, ...]) -> _Sheet:
    rows = [
        _header(
            (
                "experiment",
                "capture",
                "position",
                "channel",
                "frame_index",
                "time_seconds",
                "background_value",
                "pixel_count",
                "pixel_fraction",
                "mean",
                "median",
                "standard_deviation",
                "method",
            )
        )
    ]
    for export in positions:
        for estimate in export.background.estimates:
            rows.append(
                [
                    _Cell(export.position_key.experiment),
                    _Cell(export.position_key.capture),
                    _Cell(export.position_key.position),
                    _Cell(estimate.channel.value),
                    _Cell(estimate.frame.frame_index),
                    _Cell(estimate.frame.time_seconds),
                    _Cell(estimate.value),
                    _Cell(estimate.pixel_count),
                    _Cell(estimate.pixel_fraction),
                    _Cell(estimate.mean),
                    _Cell(estimate.median),
                    _Cell(estimate.standard_deviation),
                    _Cell(estimate.method),
                ]
            )
    return _table_sheet("background_long", rows)


def _qc_long_sheet(positions: tuple[Module14PositionExport, ...]) -> _Sheet:
    rows = [
        _header(
            (
                "experiment",
                "capture",
                "position",
                "scope",
                "status",
                "reasons",
                "channel",
                "frame_index",
                "time_seconds",
                "roi_label",
                "metrics",
            )
        )
    ]
    for export in positions:
        for record in export.intensity_qc.records:
            rows.append(_qc_row(export.position_key, record))
    return _table_sheet("qc_long", rows)


def _metadata_sheet(positions: tuple[Module14PositionExport, ...]) -> _Sheet:
    rows = [
        _header(
            (
                "experiment",
                "capture",
                "position",
                "source_type",
                "channel",
                "original_name",
                "source_path",
                "xy",
                "z_token",
                "t_token",
                "frame_count",
                "height",
                "width",
                "dtype",
                "tiff_page_count",
                "tiff_series_axes",
                "tiff_series_shape",
                "metadata_key",
                "metadata_value",
                "association_method",
                "referenced_tiff_filenames",
                "source_line_number",
                "ifd",
                "x_position_um",
                "y_position_um",
                "z_position_um",
                "elapsed_time_ms",
                "channel_name",
                "tiff_filename",
                "raw_line",
            )
        )
    ]
    for export in positions:
        if export.pair is not None:
            rows.extend(_pair_metadata_rows(export))
        rows.extend(_auxiliary_metadata_rows(export))
    return _table_sheet("metadata", rows)


def _auxiliary_metadata_rows(export: Module14PositionExport) -> list[list[_Cell]]:
    rows: list[list[_Cell]] = []
    emitted_paths: set[str] = set()
    associations = (
        export.pair.auxiliary_metadata_associations
        if export.pair is not None
        else ()
    )
    for association in associations:
        auxiliary = association.metadata_file
        emitted_paths.add(_metadata_path_key(auxiliary))
        rows.extend(_auxiliary_file_rows(export, auxiliary, association))
    for auxiliary in export.auxiliary_metadata:
        if _metadata_path_key(auxiliary) in emitted_paths:
            continue
        rows.extend(_auxiliary_file_rows(export, auxiliary, None))
    return rows


def _auxiliary_file_rows(
    export: Module14PositionExport,
    auxiliary: AuxiliaryMetadataFile,
    association: AuxiliaryMetadataPairAssociation | None,
) -> list[list[_Cell]]:
    rows = [
        _auxiliary_metadata_row(
            export,
            auxiliary,
            source_type="auxiliary_text",
            metadata_key=entry.key,
            metadata_value=entry.value,
            association=association,
            source_line_number=entry.line_number,
            raw_line=entry.raw_line,
        )
        for entry in auxiliary.key_values
    ]
    slidebook_log = auxiliary.slidebook_log
    if association is None or slidebook_log is None:
        return rows

    rows.append(
        _auxiliary_metadata_row(
            export,
            auxiliary,
            source_type="slidebook_log_raw",
            metadata_key="raw_text",
            metadata_value=auxiliary.raw_text,
            association=association,
        )
    )
    header_values = (
        ("export_datetime", slidebook_log.export_datetime),
        ("capture_datetime", slidebook_log.capture_datetime),
        ("z_planes", slidebook_log.z_planes),
        ("time_points", slidebook_log.time_points),
        ("channel_count", slidebook_log.channel_count),
        ("microns_per_pixel", slidebook_log.microns_per_pixel),
        ("z_step_size_microns", slidebook_log.z_step_size_microns),
        ("average_timelapse_interval", slidebook_log.average_timelapse_interval),
    )
    rows.extend(
        _auxiliary_metadata_row(
            export,
            auxiliary,
            source_type="slidebook_log_header",
            metadata_key=key,
            metadata_value=value,
            association=association,
        )
        for key, value in header_values
    )
    rows.extend(
        _auxiliary_metadata_row(
            export,
            auxiliary,
            source_type="slidebook_log_table",
            metadata_key="table_row",
            association=association,
            source_line_number=log_row.line_number,
            log_row=log_row,
            raw_line=log_row.raw_line,
        )
        for log_row in slidebook_log.rows
    )
    return rows


def _auxiliary_metadata_row(
    export: Module14PositionExport,
    auxiliary: AuxiliaryMetadataFile,
    *,
    source_type: str,
    metadata_key: str,
    metadata_value: object = None,
    association: AuxiliaryMetadataPairAssociation | None,
    source_line_number: int | None = None,
    log_row: SlideBookLogRow | None = None,
    raw_line: str = "",
) -> list[_Cell]:
    return [
        _Cell(export.position_key.experiment),
        _Cell(export.position_key.capture),
        _Cell(export.position_key.position),
        _Cell(source_type),
        _Cell(""),
        _Cell(auxiliary.source.original_name),
        _Cell(str(auxiliary.source.path)),
        *[_Cell("") for _ in range(10)],
        _Cell(metadata_key),
        _Cell(_metadata_value(metadata_value)),
        _Cell(association.method if association is not None else ""),
        _Cell(
            "; ".join(association.referenced_tiff_filenames)
            if association is not None
            else ""
        ),
        _Cell(source_line_number),
        _Cell(log_row.ifd if log_row is not None else None),
        _Cell(log_row.x_position_um if log_row is not None else None),
        _Cell(log_row.y_position_um if log_row is not None else None),
        _Cell(log_row.z_position_um if log_row is not None else None),
        _Cell(log_row.elapsed_time_ms if log_row is not None else None),
        _Cell(log_row.channel_name if log_row is not None else ""),
        _Cell(log_row.tiff_filename if log_row is not None else ""),
        _Cell(raw_line),
    ]


def _metadata_path_key(auxiliary: AuxiliaryMetadataFile) -> str:
    return str(auxiliary.source.path.resolve(strict=False)).casefold()

def _parameters_sheet(positions: tuple[Module14PositionExport, ...]) -> _Sheet:
    rows = [_header(("experiment", "capture", "position", "module", "method", "parameter", "value"))]
    for export in positions:
        rows.extend(_parameter_rows(export, "module10_background", export.background))
        rows.extend(_parameter_rows(export, "module11_intensity_qc", export.intensity_qc))
        rows.extend(_parameter_rows(export, "module12_temporal_intensity", export.temporal_intensity))
        rows.extend(_parameter_rows(export, "module13_fret", export.fret))
        config = export.roi_filtering.config
        rows.extend(
            _simple_parameter_rows(
                export,
                "module8_roi_geometry",
                "roi_geometry_filter",
                {
                    "min_area_pixels": config.min_area_pixels,
                    "max_area_pixels": config.max_area_pixels,
                    "border_policy": config.border_policy.value,
                },
            )
        )
    return _table_sheet("parameters", rows)


def _issues_sheet(positions: tuple[Module14PositionExport, ...]) -> _Sheet:
    rows = [_header(("experiment", "capture", "position", "module", "code", "severity", "message", "context"))]
    for export in positions:
        rows.extend(_issue_rows(export, "module8_roi_geometry", export.roi_filtering.issues))
        rows.extend(_issue_rows(export, "module10_background", export.background.issues))
        rows.extend(_issue_rows(export, "module11_intensity_qc", export.intensity_qc.issues))
        rows.extend(_issue_rows(export, "module12_temporal_intensity", export.temporal_intensity.issues))
        rows.extend(_issue_rows(export, "module13_fret", export.fret.issues))
        rows.extend(_issue_rows(export, "module14_export_input", export.issues))
    return _table_sheet("issues", rows)


def _roi_provenance_sheet(positions: tuple[Module14PositionExport, ...]) -> _Sheet:
    """Export the effective Module 24 mask provenance without changing value sheets."""

    rows = [_header(("experiment", "capture", "position", "mask_source", "revision_sha256"))]
    for export in positions:
        rows.append(
            [
                _Cell(export.position_key.experiment),
                _Cell(export.position_key.capture),
                _Cell(export.position_key.position),
                _Cell(export.mask_source),
                _Cell(export.revision_sha256),
            ]
        )
    return _table_sheet("roi_provenance", rows)


def _table_sheet(
    name: str,
    rows: list[list[_Cell]],
    *,
    title_merge: str | None = None,
) -> _Sheet:
    width_count = max((len(row) for row in rows), default=1)
    normalized = [row + [_Cell() for _ in range(width_count - len(row))] for row in rows]
    if title_merge is not None:
        merges = (title_merge,)
        freeze_rows = 3
        header_row = normalized[2] if len(normalized) > 2 else ()
    else:
        merges = ()
        freeze_rows = 1
        header_row = normalized[0] if normalized else ()
    widths = _table_column_widths(header_row, width_count)
    return _Sheet(
        name=name,
        rows=tuple(tuple(row) for row in normalized),
        column_widths=widths,
        merges=merges,
        freeze_rows=freeze_rows,
    )


def _header(values: tuple[str, ...]) -> list[_Cell]:
    return [_Cell(value, 11) for value in values]


def _table_column_widths(header_row: tuple[_Cell, ...], width_count: int) -> dict[int, float]:
    semantic_widths = {
        "experiment": 24.0,
        "capture": 14.0,
        "position": 14.0,
        "roi_label": 10.0,
        "frame_index": 11.0,
        "time_seconds": 12.0,
        "source_type": 16.0,
        "original_name": 42.0,
        "source_path": 48.0,
        "tiff_series_shape": 16.0,
        "metadata_key": 18.0,
        "metadata_value": 48.0,
        "association_method": 32.0,
        "referenced_tiff_filenames": 64.0,
        "source_line_number": 12.0,
        "channel_name": 24.0,
        "tiff_filename": 42.0,
        "raw_line": 64.0,
        "module": 28.0,
        "method": 34.0,
        "parameter": 32.0,
        "message": 64.0,
        "context": 48.0,
        "metrics": 44.0,
        "ratio_reasons": 34.0,
        "normalization_reasons": 34.0,
        "geometry_reasons": 30.0,
        "roi_frame_qc_reasons": 34.0,
        "field_frame_qc_reasons": 34.0,
        "roi_qc_reasons": 30.0,
        "field_qc_reasons": 30.0,
    }
    widths: dict[int, float] = {}
    for index in range(1, width_count + 1):
        header = header_row[index - 1].value if index - 1 < len(header_row) else None
        widths[index] = semantic_widths.get(str(header), 16.0)
    return widths


def _intensity_row(key: PositionKey, record: TemporalIntensityRecord) -> list[_Cell]:
    return [
        _Cell(key.experiment),
        _Cell(key.capture),
        _Cell(key.position),
        _Cell(record.roi_label),
        _Cell(record.channel.value),
        _Cell(record.frame.frame_index),
        _Cell(record.frame.time_seconds),
        _Cell(record.roi_area_pixels),
        _Cell(record.raw_mean),
        _Cell(record.raw_median),
        _Cell(record.background_value),
        _Cell(record.background_corrected_mean),
        _Cell(record.background_corrected_median),
        _Cell(_status_value(record.roi_frame_qc_status)),
        _Cell(_join(record.roi_frame_qc_reasons)),
        _Cell(_status_value(record.field_frame_qc_status)),
        _Cell(_join(record.field_frame_qc_reasons)),
        _Cell(_status_value(record.roi_qc_status)),
        _Cell(_join(record.roi_qc_reasons)),
        _Cell(_status_value(record.field_qc_status)),
        _Cell(_join(record.field_qc_reasons)),
    ]


def _qc_row(key: PositionKey, record: IntensityQcRecord) -> list[_Cell]:
    return [
        _Cell(key.experiment),
        _Cell(key.capture),
        _Cell(key.position),
        _Cell(record.scope.value),
        _Cell(record.status.value),
        _Cell(_join(record.reasons)),
        _Cell(record.channel.value if record.channel is not None else ""),
        _Cell(record.frame.frame_index if record.frame is not None else None),
        _Cell(record.frame.time_seconds if record.frame is not None else None),
        _Cell(record.roi_label),
        _Cell(_format_mapping(record.metrics)),
    ]


def _pair_metadata_rows(export: Module14PositionExport) -> list[list[_Cell]]:
    assert export.pair is not None
    rows: list[list[_Cell]] = []
    for channel, sequence in ((Channel.C0, export.pair.c0), (Channel.C1, export.pair.c1)):
        parsed = sequence.parsed_file
        metadata = sequence.metadata
        rows.append(
            [
                _Cell(export.position_key.experiment),
                _Cell(export.position_key.capture),
                _Cell(export.position_key.position),
                _Cell("tiff"),
                _Cell(channel.value),
                _Cell(parsed.source.original_name),
                _Cell(str(parsed.source.path)),
                _Cell(parsed.xy),
                _Cell(parsed.z_token),
                _Cell(parsed.t_token),
                _Cell(sequence.frame_count),
                _Cell(sequence.height),
                _Cell(sequence.width),
                _Cell(sequence.dtype_name),
                _Cell(metadata.page_count),
                _Cell(metadata.series_axes),
                _Cell(str(metadata.series_shape)),
                _Cell("first_page_tags"),
                _Cell(_format_mapping(metadata.first_page_tags)),
            ]
        )
    return rows


def _parameter_rows(
    export: Module14PositionExport,
    module: str,
    result: object,
) -> list[list[_Cell]]:
    method = getattr(result, "method", "")
    parameters = getattr(result, "parameters", {})
    return _simple_parameter_rows(export, module, method, parameters)


def _simple_parameter_rows(
    export: Module14PositionExport,
    module: str,
    method: str,
    parameters: Mapping[str, object],
) -> list[list[_Cell]]:
    return [
        [
            _Cell(export.position_key.experiment),
            _Cell(export.position_key.capture),
            _Cell(export.position_key.position),
            _Cell(module),
            _Cell(method),
            _Cell(key),
            _Cell(_metadata_value(value)),
        ]
        for key, value in sorted(parameters.items())
    ]


def _issue_rows(
    export: Module14PositionExport,
    module: str,
    issues: tuple[PipelineIssue, ...],
) -> list[list[_Cell]]:
    return [
        [
            _Cell(export.position_key.experiment),
            _Cell(export.position_key.capture),
            _Cell(export.position_key.position),
            _Cell(module),
            _Cell(issue.code),
            _Cell(issue.severity.value),
            _Cell(issue.message),
            _Cell(_format_mapping(issue.context)),
        ]
        for issue in issues
    ]


def _roi_labels(export: Module14PositionExport) -> tuple[int, ...]:
    labels = {record.roi_label for record in export.fret.records}
    labels.update(record.roi_label for record in export.temporal_intensity.records)
    return tuple(sorted(labels))


def _time_rows(positions: tuple[Module14PositionExport, ...]) -> tuple[tuple[int, float | None], ...]:
    times: dict[int, float | None] = {}
    for export in positions:
        for record in export.fret.records:
            times.setdefault(record.frame.frame_index, record.frame.time_seconds)
        for record in export.temporal_intensity.records:
            times.setdefault(record.frame.frame_index, record.frame.time_seconds)
    return tuple(sorted(times.items()))


def _fret_record_index(
    positions: tuple[Module14PositionExport, ...],
) -> dict[tuple[str | None, str | None, int | None, int], FretCalculationRecord]:
    indexed = {}
    for export in positions:
        key = export.position_key
        for record in export.fret.records:
            indexed[(key.capture, key.position, record.roi_label, record.frame.frame_index)] = record
    return indexed


def _record_value(record: FretCalculationRecord | None, field_name: str) -> object:
    if record is None:
        return "MISSING" if field_name == "qc_status" else None
    if field_name == "qc_status":
        return _wide_qc_status(record)
    return getattr(record, field_name)


def _wide_qc_status(record: FretCalculationRecord) -> str:
    statuses = (record.ratio_status, record.normalization_status)
    if any(status is FretCalculationStatus.EXCLUDED for status in statuses):
        return "EXCLUDE"
    if any(status is FretCalculationStatus.MISSING for status in statuses):
        return "MISSING"
    if any(status is FretCalculationStatus.FLAGGED for status in statuses):
        return "FLAG"
    return "PASS"


def _qc_style(value: object) -> int:
    if value == "PASS":
        return 12
    if value == "FLAG":
        return 13
    if value == "EXCLUDE":
        return 14
    return 15


def _has_complete_time_seconds(positions: tuple[Module14PositionExport, ...]) -> bool:
    frames = (
        record.frame
        for export in positions
        for result in (export.fret, export.temporal_intensity)
        for record in result.records
    )
    observed = tuple(frames)
    return bool(observed) and all(frame.time_seconds is not None for frame in observed)


def _header_spans(
    columns: tuple[_ExportColumn, ...],
    field_name: str,
) -> tuple[tuple[int, int, str], ...]:
    spans = []
    start = None
    current = None
    for index, column in enumerate(columns, start=1):
        label = getattr(column, field_name) if column.kind == "roi" else None
        if label != current:
            if current is not None and start is not None:
                spans.append((start, index - 1, current))
            start = index if label is not None else None
            current = label
    if current is not None and start is not None:
        spans.append((start, len(columns), current))
    return tuple(spans)


def _merge_refs(columns: tuple[_ExportColumn, ...]) -> tuple[str, ...]:
    merges = []
    for row_index, field_name in ((4, "capture"), (5, "position")):
        for start, end, _label in _header_spans(columns, field_name):
            if end > start:
                merges.append(f"{_column_name(start)}{row_index}:{_column_name(end)}{row_index}")
    return tuple(merges)


def _spacer_style(column: _ExportColumn) -> int:
    return 8 if column.kind == "capture_spacer" else 7


def _roi_display_label(label: int | None) -> str:
    return f"ROI-{label:03d}" if label is not None else ""


def _roi_identity(column: _ExportColumn) -> str:
    return (
        f"c{_numeric_suffix(column.capture)}/"
        f"p{_numeric_suffix(column.position)}/"
        f"r{column.roi_label}"
    )


def _status_value(status: IntensityQcStatus | None) -> str:
    return "" if status is None else status.value


def _issue_count(export: Module14PositionExport) -> int:
    return sum(
        len(tuple(issues))
        for issues in (
            export.roi_filtering.issues,
            export.background.issues,
            export.intensity_qc.issues,
            export.temporal_intensity.issues,
            export.fret.issues,
            export.issues,
        )
    )


def _group_by(
    items: tuple[Module14PositionExport, ...],
    key_getter: Callable[[Module14PositionExport], str],
) -> tuple[tuple[str, tuple[Module14PositionExport, ...]], ...]:
    grouped: dict[str, list[Module14PositionExport]] = {}
    for item in items:
        key = key_getter(item)
        grouped.setdefault(key, []).append(item)
    return tuple(
        (key, tuple(sorted(values, key=_position_sort_key)))
        for key, values in sorted(grouped.items(), key=lambda item: _natural_key(item[0]))
    )


def _position_sort_key(item: Module14PositionExport) -> tuple[object, object]:
    return (_natural_key(item.position_key.capture), _natural_key(item.position_key.position))


def _natural_key(value: str) -> tuple[object, ...]:
    parts: list[object] = []
    current = ""
    digit_mode = False
    for char in value:
        if char.isdigit() != digit_mode:
            if current:
                parts.append(int(current) if digit_mode else current.casefold())
            current = char
            digit_mode = char.isdigit()
        else:
            current += char
    if current:
        parts.append(int(current) if digit_mode else current.casefold())
    return tuple(parts)


def _numeric_suffix(value: str | None) -> str:
    if value is None:
        return ""
    digits = ""
    for char in reversed(value):
        if not char.isdigit():
            break
        digits = char + digits
    return str(int(digits)) if digits else value


def _safe_file_stem(value: str) -> str:
    stem = "".join(char if char.isalnum() else "_" for char in value.strip().lower())
    stem = "_".join(part for part in stem.split("_") if part)
    return stem or "experiment"


def _join(values: tuple[str, ...]) -> str:
    return "; ".join(values)


def _format_mapping(values: Mapping[str, object]) -> str:
    return "; ".join(f"{key}={_metadata_value(value)}" for key, value in sorted(values.items()))


def _metadata_value(value: object) -> MetadataValue | str:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _empty_grid(row_count: int, col_count: int) -> list[list[_Cell]]:
    return [[_Cell() for _ in range(col_count)] for _ in range(row_count)]


def _write_xlsx(path: Path, sheets: tuple[_Sheet, ...]) -> None:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types(len(sheets)))
        archive.writestr("_rels/.rels", _root_rels())
        archive.writestr("docProps/core.xml", _core_props())
        archive.writestr("docProps/app.xml", _app_props())
        archive.writestr("xl/workbook.xml", _workbook_xml(sheets))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels(sheets))
        archive.writestr("xl/styles.xml", _styles_xml())
        for index, sheet in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(sheet))


def _content_types(sheet_count: int) -> str:
    sheets = "\n".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
{sheets}
</Types>'''


def _root_rels() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''


def _workbook_xml(sheets: tuple[_Sheet, ...]) -> str:
    sheet_xml = "\n".join(
        f'<sheet name="{_xml(sheet.name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, sheet in enumerate(sheets, start=1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
{sheet_xml}
</sheets>
</workbook>'''


def _workbook_rels(sheets: tuple[_Sheet, ...]) -> str:
    rels = "\n".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    style_id = len(sheets) + 1
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{rels}
<Relationship Id="rId{style_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''


def _sheet_xml(sheet: _Sheet) -> str:
    cols = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in sorted(sheet.column_widths.items())
    )
    rows = "\n".join(_row_xml(index, row) for index, row in enumerate(sheet.rows, start=1))
    merge_xml = ""
    if sheet.merges:
        refs = "".join(f'<mergeCell ref="{ref}"/>' for ref in sheet.merges)
        merge_xml = f'<mergeCells count="{len(sheet.merges)}">{refs}</mergeCells>'
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
{_sheet_views_xml(sheet)}
<cols>{cols}</cols>
<sheetData>
{rows}
</sheetData>
{merge_xml}
</worksheet>'''


def _sheet_views_xml(sheet: _Sheet) -> str:
    if not sheet.freeze_rows and not sheet.freeze_cols:
        return '<sheetViews><sheetView showGridLines="0" workbookViewId="0"/></sheetViews>'
    x_split = sheet.freeze_cols
    y_split = sheet.freeze_rows
    top_left = f"{_column_name(x_split + 1)}{y_split + 1}"
    return (
        '<sheetViews><sheetView showGridLines="0" workbookViewId="0">'
        f'<pane xSplit="{x_split}" ySplit="{y_split}" topLeftCell="{top_left}" '
        'activePane="bottomRight" state="frozen"/>'
        "</sheetView></sheetViews>"
    )


def _row_xml(row_index: int, row: tuple[_Cell, ...]) -> str:
    cells = "".join(
        _cell_xml(row_index, col_index, cell)
        for col_index, cell in enumerate(row, start=1)
        if cell.value not in (None, "") or cell.style
    )
    return f'<row r="{row_index}">{cells}</row>'


def _cell_xml(row_index: int, col_index: int, cell: _Cell) -> str:
    ref = f"{_column_name(col_index)}{row_index}"
    style = f' s="{cell.style}"' if cell.style else ""
    value = cell.value
    if value in (None, ""):
        return f'<c r="{ref}"{style}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}"{style} t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{style}><v>{value}</v></c>'
    return f'<c r="{ref}"{style} t="inlineStr"><is><t>{_xml(str(value))}</t></is></c>'


def _styles_xml() -> str:
    fills = (
        '<fill><patternFill patternType="none"/></fill>',
        '<fill><patternFill patternType="gray125"/></fill>',
        _fill("17494D"),
        _fill("FFF2CC"),
        _fill("D9EAD3"),
        _fill("DDEBF7"),
        _fill("2E6F73"),
        _fill("EAF3F1"),
        _fill("CFE2F3"),
        _fill("FCE4D6"),
        _fill("E6F4EA"),
        _fill("FFF4CC"),
        _fill("FCE8E6"),
        _fill("E8EAED"),
    )
    cell_xfs = (
        _xf(),
        _xf(fill_id=2, font_id=1, alignment="center"),
        _xf(fill_id=3, font_id=2, alignment="left", wrap=True),
        _xf(fill_id=4, font_id=3, alignment="center"),
        _xf(fill_id=5, font_id=3, alignment="center"),
        _xf(fill_id=6, font_id=1, alignment="center"),
        _xf(fill_id=7, font_id=2, alignment="center", wrap=True),
        _xf(fill_id=8),
        _xf(fill_id=9),
        _xf(num_fmt_id=4),
        _xf(),
        _xf(fill_id=6, font_id=1, alignment="center"),
        _xf(fill_id=10, alignment="center"),
        _xf(fill_id=11, alignment="center"),
        _xf(fill_id=12, alignment="center"),
        _xf(fill_id=13, alignment="center"),
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="4">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font>
<font><i/><color rgb="FF44545A"/><sz val="9"/><name val="Calibri"/></font>
<font><b/><color rgb="FF173A3D"/><sz val="11"/><name val="Calibri"/></font>
</fonts>
<fills count="{len(fills)}">{''.join(fills)}</fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="{len(cell_xfs)}">{''.join(cell_xfs)}</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def _xf(
    *,
    fill_id: int = 0,
    font_id: int = 0,
    num_fmt_id: int = 0,
    alignment: str | None = None,
    wrap: bool = False,
) -> str:
    apply_fill = ' applyFill="1"' if fill_id else ""
    apply_font = ' applyFont="1"' if font_id else ""
    apply_number = ' applyNumberFormat="1"' if num_fmt_id else ""
    if alignment is None and not wrap:
        return (
            f'<xf numFmtId="{num_fmt_id}" fontId="{font_id}" fillId="{fill_id}" '
            f'borderId="0" xfId="0"{apply_fill}{apply_font}{apply_number}/>'
        )
    wrap_attr = ' wrapText="1"' if wrap else ""
    return (
        f'<xf numFmtId="{num_fmt_id}" fontId="{font_id}" fillId="{fill_id}" '
        f'borderId="0" xfId="0"{apply_fill}{apply_font}{apply_number} applyAlignment="1">'
        f'<alignment horizontal="{alignment or "general"}"{wrap_attr}/></xf>'
    )


def _fill(color: str) -> str:
    return (
        '<fill><patternFill patternType="solid">'
        f'<fgColor rgb="FF{color}"/><bgColor indexed="64"/>'
        '</patternFill></fill>'
    )


def _core_props() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:creator>FUNES Module 14</dc:creator>
<cp:lastModifiedBy>FUNES Module 14</cp:lastModifiedBy>
</cp:coreProperties>'''


def _app_props() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>FUNES</Application>
</Properties>'''


def _column_name(index: int) -> str:
    name = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xml(value: str) -> str:
    return escape(value, {'"': "&quot;"})
