import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.auxiliary_metadata import (
    AuxiliaryMetadataFile,
    AuxiliaryMetadataPairAssociation,
    TextMetadataEntry,
)
from funes.contracts import Channel, FrameReference, IssueSeverity, PipelineIssue, PositionKey, SourceFile
from funes.file_discovery import parse_tiff_filename
from funes.fret_calculation import FretCalculationRecord, FretCalculationResult, FretCalculationStatus
from funes.intensity_qc import IntensityQcRecord, IntensityQcResult, IntensityQcScope, IntensityQcStatus
from funes.module14_exporter import Module14PositionExport, export_module14_workbooks
from funes.quantitative_background import FrameBackgroundEstimate, QuantitativeBackgroundResult
from funes.slidebook_log_metadata import parse_slidebook_log_metadata
from funes.roi_geometry import (
    RoiBoundingBox,
    RoiFilterRecord,
    RoiFilteringResult,
    RoiFilterStatus,
    RoiGeometry,
    RoiGeometryFilterConfig,
)
from funes.temporal_intensity import TemporalIntensityRecord, TemporalIntensityResult
from funes.tiff_reader import TiffFrameSequence, TiffMetadata, TiffPair


NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class Module14ExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="funes_module14_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir)

    def test_exports_one_workbook_per_experiment_with_d032_layout(self) -> None:
        result = export_module14_workbooks(
            (
                _position_export("Exp A", "Capture 1", "Position 1", (1, 2)),
                _position_export("Exp A", "Capture 1", "Position 2", (1,)),
                _position_export("Exp A", "Capture 2", "Position 1", (1,)),
                _position_export("Exp B", "Capture 1", "Position 1", (1,)),
            ),
            self.tmpdir,
        )

        self.assertEqual(
            sorted(path.name for path in result.workbook_paths),
            ["exp_a.xlsx", "exp_b.xlsx"],
        )
        exp_a = self.tmpdir / "exp_a.xlsx"
        self.assertTrue(exp_a.exists())

        sheet_names = _sheet_names(exp_a)
        self.assertEqual(
            sheet_names[:6],
            ["ratio", "r_over_r0", "delta_r_over_r0", "donor_corrected", "fret_corrected", "qc_status"],
        )
        self.assertIn("metadata", sheet_names)
        self.assertIn("parameters", sheet_names)
        self.assertIn("issues", sheet_names)

        ratio = _sheet_cells(exp_a, 1)
        self.assertEqual(ratio["A6"], "time_s")
        self.assertEqual(ratio["A7"], "seconds")
        self.assertEqual(ratio["B6"], "ROI-001")
        self.assertEqual(ratio["C6"], "ROI-002")
        self.assertEqual(ratio["E6"], "ROI-001")
        self.assertEqual(ratio["H6"], "ROI-001")
        self.assertEqual(ratio["B7"], "c1/p1/r1")
        self.assertEqual(ratio["C7"], "c1/p1/r2")
        self.assertEqual(ratio["E7"], "c1/p2/r1")
        self.assertEqual(ratio["H7"], "c2/p1/r1")
        self.assertEqual(ratio["A8"], "0.0")
        self.assertEqual(ratio["A9"], "2.0")
        self.assertEqual(ratio["B8"], "3.0")

        ratio_styles = _sheet_styles(exp_a, 1)
        self.assertEqual(ratio_styles["D6"], "7")
        self.assertEqual(ratio_styles["F6"], "8")
        self.assertEqual(ratio_styles["G6"], "8")

    def test_preserves_qc_statuses_metadata_parameters_and_issues(self) -> None:
        issue = PipelineIssue(
            code="synthetic_export_issue",
            message="Synthetic issue preserved for audit.",
            severity=IssueSeverity.WARNING,
            context={"roi_label": 2},
        )
        result = export_module14_workbooks(
            (
                _position_export(
                    "Exp Audit",
                    "Capture 1",
                    "Position 1",
                    (1, 2),
                    extra_issue=issue,
                    roi2_status=FretCalculationStatus.EXCLUDED,
                ),
            ),
            self.tmpdir,
        )

        workbook = result.workbook_paths[0]
        qc_sheet = _sheet_cells(workbook, 6)
        self.assertEqual(qc_sheet["B8"], "PASS")
        self.assertEqual(qc_sheet["C8"], "EXCLUDE")

        all_text = "\n".join(_zip_texts(workbook))
        self.assertIn("synthetic_export_issue", all_text)
        self.assertIn("roi_label=2", all_text)
        self.assertIn("background_percentile", all_text)
        self.assertIn("synthetic_12_bit", all_text)
        self.assertIn("Capture 1 - Position 1_XY1782521382_Z0_T00_C0.tif", all_text)
        self.assertIn("operator", all_text)
        self.assertIn("Ada", all_text)
        self.assertIn("slidebook_log_tiff_table", all_text)
        self.assertIn("slidebook_log_header", all_text)
        self.assertIn("export_datetime", all_text)
        self.assertIn("07/13/2026 11:47:1", all_text)
        self.assertIn("slidebook_log_table", all_text)
        self.assertIn("43115", all_text)
        self.assertIn("channel 0", all_text)
        self.assertIn("raw_text", all_text)

    def test_audit_sheets_use_semantic_widths_for_traceability_fields(self) -> None:
        result = export_module14_workbooks(
            (
                _position_export(
                    "Exp Audit",
                    "Capture 1",
                    "Position 1",
                    (1,),
                    extra_issue=PipelineIssue(
                        code="synthetic_export_issue",
                        message="Synthetic issue preserved for audit.",
                        severity=IssueSeverity.WARNING,
                        context={"roi_label": 1},
                    ),
                ),
            ),
            self.tmpdir,
        )

        workbook = result.workbook_paths[0]

        metadata_widths = _sheet_widths(workbook, 13)
        self.assertGreater(metadata_widths["F"], 16.0)
        self.assertGreater(metadata_widths["G"], 16.0)
        self.assertGreater(metadata_widths["S"], 16.0)
        self.assertGreater(metadata_widths["T"], 16.0)
        self.assertGreater(metadata_widths["U"], 16.0)
        self.assertGreater(metadata_widths["AD"], 16.0)

        parameter_widths = _sheet_widths(workbook, 14)
        self.assertGreater(parameter_widths["D"], 16.0)
        self.assertGreater(parameter_widths["E"], 16.0)
        self.assertGreater(parameter_widths["F"], 16.0)

        issue_widths = _sheet_widths(workbook, 15)
        self.assertGreater(issue_widths["G"], 16.0)
        self.assertGreater(issue_widths["H"], 16.0)

    def test_requires_experiment_label(self) -> None:
        with self.assertRaisesRegex(ValueError, "experiment label"):
            Module14PositionExport(
                position_key=PositionKey(capture="Capture 1", position="Position 1"),
                roi_filtering=_roi_filtering(()),
                background=_background_result(),
                intensity_qc=_qc_result(()),
                temporal_intensity=TemporalIntensityResult(records=(), method="synthetic"),
                fret=FretCalculationResult(records=(), method="synthetic"),
            )

    def test_requires_runtime_typed_results_from_modules_8_10_11_12_and_13(self) -> None:
        valid = _position_export("Exp Typed", "Capture 1", "Position 1", (2, 4))
        expected_types = {
            "roi_filtering": "RoiFilteringResult",
            "background": "QuantitativeBackgroundResult",
            "intensity_qc": "IntensityQcResult",
            "temporal_intensity": "TemporalIntensityResult",
            "fret": "FretCalculationResult",
        }

        for field_name, expected_type in expected_types.items():
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(
                    TypeError,
                    rf"^{field_name} must be a {expected_type}$",
                ):
                    replace(valid, **{field_name: object()})

    def test_preserves_nonconsecutive_roi_labels_without_running_upstream_modules(self) -> None:
        position_export = _position_export(
            "Exp Gapped Labels",
            "Capture 1",
            "Position 1",
            (2, 4),
        )
        upstream_calls = (
            "funes.segmentation_engine.segment_first_frame",
            "funes.segmentation_registry.segment_configured_first_frame",
            "funes.roi_geometry.filter_labeled_rois",
            "funes.roi_geometry.filter_segmentation_rois",
            "funes.quantitative_background.estimate_quantitative_background",
            "funes.intensity_qc.evaluate_intensity_qc",
            "funes.intensity_qc.evaluate_filtered_roi_intensity_qc",
            "funes.temporal_intensity.extract_temporal_intensities",
            "funes.temporal_intensity.extract_filtered_roi_temporal_intensities",
            "funes.fret_calculation.calculate_fret",
        )

        with ExitStack() as stack:
            spies = [stack.enter_context(patch(target)) for target in upstream_calls]
            result = export_module14_workbooks((position_export,), self.tmpdir)

        for target, spy in zip(upstream_calls, spies):
            with self.subTest(target=target):
                spy.assert_not_called()

        workbook = result.workbook_paths[0]
        ratio = _sheet_cells(workbook, 1)
        self.assertEqual(ratio["B6"], "ROI-002")
        self.assertEqual(ratio["C6"], "ROI-004")
        self.assertEqual(ratio["B7"], "c1/p1/r2")
        self.assertEqual(ratio["C7"], "c1/p1/r4")
        self.assertNotIn("ROI-001", ratio.values())
        self.assertNotIn("ROI-003", ratio.values())

        roi_summary = _sheet_cells(workbook, 10)
        intensity_long = _sheet_cells(workbook, 9)
        fret_long = _sheet_cells(workbook, 8)
        qc_long = _sheet_cells(workbook, 12)
        self.assertEqual((roi_summary["D2"], roi_summary["D3"]), ("2", "4"))
        self.assertEqual({intensity_long[f"D{row}"] for row in range(2, 10)}, {"2", "4"})
        self.assertEqual({fret_long[f"D{row}"] for row in range(2, 6)}, {"2", "4"})
        self.assertEqual((qc_long["J2"], qc_long["J3"]), ("2", "4"))


def _position_export(
    experiment: str,
    capture: str,
    position: str,
    roi_labels: tuple[int, ...],
    *,
    extra_issue: PipelineIssue | None = None,
    roi2_status: FretCalculationStatus = FretCalculationStatus.PASS,
) -> Module14PositionExport:
    key = PositionKey(experiment=experiment, capture=capture, position=position)
    return Module14PositionExport(
        position_key=key,
        roi_filtering=_roi_filtering(roi_labels),
        background=_background_result(),
        intensity_qc=_qc_result(roi_labels),
        temporal_intensity=_temporal_intensity(roi_labels),
        fret=_fret_result(roi_labels, roi2_status=roi2_status),
        pair=_pair(capture, position),
        auxiliary_metadata=(_auxiliary_metadata(),),
        issues=tuple(issue for issue in (extra_issue,) if issue is not None),
    )


def _fret_result(
    roi_labels: tuple[int, ...],
    *,
    roi2_status: FretCalculationStatus,
) -> FretCalculationResult:
    records = []
    for roi_label in roi_labels:
        for frame_index, time_seconds in ((0, 0.0), (1, 2.0)):
            status = roi2_status if roi_label == 2 and frame_index == 0 else FretCalculationStatus.PASS
            ratio = None if status is FretCalculationStatus.EXCLUDED else 3.0 + frame_index
            records.append(
                FretCalculationRecord(
                    frame=FrameReference(frame_index=frame_index, time_seconds=time_seconds),
                    roi_label=roi_label,
                    c0_raw_mean=31.0 + roi_label + frame_index,
                    c1_raw_mean=11.0 + roi_label + frame_index,
                    c0_background_corrected_mean=30.0 + roi_label + frame_index,
                    c1_background_corrected_mean=10.0 + roi_label + frame_index,
                    c0_value=30.0 + roi_label + frame_index,
                    c1_value=10.0 + roi_label + frame_index,
                    donor_channel=Channel.C0,
                    fret_channel=Channel.C1,
                    ratio=ratio,
                    baseline_ratio=3.0,
                    normalized_ratio=(ratio / 3.0) if ratio is not None else None,
                    delta_ratio_over_baseline=(ratio / 3.0 - 1.0) if ratio is not None else None,
                    ratio_status=status,
                    ratio_reasons=("synthetic_exclusion",) if status is FretCalculationStatus.EXCLUDED else (),
                    normalization_status=status,
                    normalization_reasons=("synthetic_exclusion",) if status is FretCalculationStatus.EXCLUDED else (),
                )
            )
    return FretCalculationResult(
        records=tuple(records),
        method="configured_fret_calculation",
        parameters={
            "ratio_formula": "C0/C1",
            "numerator_channel": "C0",
            "denominator_channel": "C1",
            "biological_donor_channel": "C0",
            "biological_fret_channel": "C1",
            "baseline_frame_indices": "0",
        },
        issues=(
            PipelineIssue(
                code="fret_synthetic_warning",
                message="Synthetic FRET warning.",
                severity=IssueSeverity.WARNING,
                context={"frame_index": 1},
            ),
        ),
    )


def _temporal_intensity(roi_labels: tuple[int, ...]) -> TemporalIntensityResult:
    records = []
    for roi_label in roi_labels:
        for channel in (Channel.C0, Channel.C1):
            for frame_index, time_seconds in ((0, 0.0), (1, 2.0)):
                records.append(
                    TemporalIntensityRecord(
                        channel=channel,
                        frame=FrameReference(frame_index=frame_index, time_seconds=time_seconds),
                        roi_label=roi_label,
                        roi_area_pixels=4,
                        raw_mean=100.0,
                        raw_median=99.0,
                        background_value=2.0,
                        background_corrected_mean=98.0,
                        background_corrected_median=97.0,
                        roi_frame_qc_status=IntensityQcStatus.PASS,
                        field_frame_qc_status=IntensityQcStatus.PASS,
                        roi_qc_status=IntensityQcStatus.PASS,
                        field_qc_status=IntensityQcStatus.PASS,
                    )
                )
    return TemporalIntensityResult(
        records=tuple(records),
        method="fixed_roi_temporal_intensity",
        parameters={"uses_fixed_rois": True},
    )


def _roi_filtering(roi_labels: tuple[int, ...]) -> RoiFilteringResult:
    label_image = np.zeros((2, max(1, len(roi_labels) * 3)), dtype=np.int32)
    records = []
    for index, roi_label in enumerate(roi_labels):
        min_col = index * 3
        label_image[:, min_col : min_col + 2] = roi_label
        geometry = RoiGeometry(
            label=roi_label,
            area_pixels=4,
            bounding_box=RoiBoundingBox(0, min_col, 1, min_col + 1),
            centroid_row=0.5,
            centroid_col=min_col + 0.5,
            touches_border=True,
        )
        records.append(
            RoiFilterRecord(
                geometry=geometry,
                status=RoiFilterStatus.FLAGGED,
                reasons=("roi_touches_border",),
            )
        )
    return RoiFilteringResult(
        source_label_image=label_image,
        filtered_label_image=label_image,
        records=tuple(records),
        config=RoiGeometryFilterConfig(min_area_pixels=1, max_area_pixels=100),
    )


def _background_result() -> QuantitativeBackgroundResult:
    estimates = []
    for channel in (Channel.C0, Channel.C1):
        for frame_index, time_seconds in ((0, 0.0), (1, 2.0)):
            estimates.append(
                FrameBackgroundEstimate(
                    channel=channel,
                    frame=FrameReference(frame_index=frame_index, time_seconds=time_seconds),
                    value=2.0,
                    pixel_count=8,
                    pixel_fraction=0.5,
                    mean=2.5,
                    median=2.0,
                    standard_deviation=0.25,
                    method="percentile_quantitative_background",
                    parameters={"background_percentile": 20.0},
                )
            )
    return QuantitativeBackgroundResult(
        estimates=tuple(estimates),
        method="percentile_quantitative_background",
        parameters={"background_percentile": 20.0},
    )


def _qc_result(roi_labels: tuple[int, ...]) -> IntensityQcResult:
    return IntensityQcResult(
        records=tuple(
            IntensityQcRecord(
                scope=IntensityQcScope.ROI_FRAME,
                status=IntensityQcStatus.PASS,
                channel=Channel.C0,
                frame=FrameReference(frame_index=0, time_seconds=0.0),
                roi_label=roi_label,
                metrics={"camera_profile": "synthetic_12_bit"},
            )
            for roi_label in roi_labels
        ),
        method="configured_intensity_qc",
        parameters={"camera_profile": "synthetic_12_bit"},
    )


def _pair(capture: str, position: str) -> TiffPair:
    c0 = _sequence(capture, position, Channel.C0)
    c1 = _sequence(capture, position, Channel.C1)
    auxiliary = _slidebook_auxiliary_metadata(capture, position, c0, c1)
    association = AuxiliaryMetadataPairAssociation(
        metadata_file=auxiliary,
        capture=capture,
        position=position,
        xy=c0.parsed_file.xy,
        z_token=c0.parsed_file.z_token,
        t_token=c0.parsed_file.t_token,
        c0=c0.parsed_file,
        c1=c1.parsed_file,
        referenced_tiff_filenames=(
            c0.parsed_file.source.original_name,
            c1.parsed_file.source.original_name,
        ),
    )
    return TiffPair(
        position_key=PositionKey(capture=capture, position=position),
        c0=c0,
        c1=c1,
        auxiliary_metadata_associations=(association,),
    )


def _sequence(capture: str, position: str, channel: Channel) -> TiffFrameSequence:
    filename = f"{capture} - {position}_XY1782521382_Z0_T00_{channel.value}.tif"
    parsed = parse_tiff_filename(Path(filename))
    assert parsed is not None
    return TiffFrameSequence(
        parsed_file=parsed,
        frames=np.zeros((2, 2, 2), dtype=np.uint16),
        metadata=TiffMetadata(
            page_count=2,
            series_axes="TYX",
            series_shape=(2, 2, 2),
            imagej_metadata=None,
            ome_metadata=None,
            page_descriptions=(),
            first_page_tags={"ImageWidth": "2"},
        ),
    )


def _slidebook_auxiliary_metadata(
    capture: str,
    position: str,
    c0: TiffFrameSequence,
    c1: TiffFrameSequence,
) -> AuxiliaryMetadataFile:
    source = SourceFile(
        path=Path(f"{capture} - {position}_XY1782521382_Z0_T00_C0.log"),
        original_name=f"{capture} - {position}_XY1782521382_Z0_T00_C0.log",
    )
    raw_text = (
        "Export Date-Time: 07/13/2026 11:47:1\n"
        "Capture Date-Time: 9/4/2025 14:55:52\n"
        "Z Planes: 1\n"
        "Time Points: 2\n"
        "Channels: 2\n"
        "Microns Per Pixel: 4\n"
        "Z Step Size Microns: 0\n"
        "Average Timelapse Interval: Unknown\n"
        "IFD\tX Position (um)\tY Position (um)\tZ Position (um)\t"
        "Elapsed Time (ms)\tChannel Name\tTIFF File Name\n"
        f"0\t43115\t24395\t8066.12\t0\tchannel 0\t{c0.parsed_file.source.original_name}\n"
        f"1\t43116\t24395\t8066.12\t0\tchannel 1\t{c1.parsed_file.source.original_name}\n"
    )
    slidebook_log, issues = parse_slidebook_log_metadata(source, raw_text)
    assert slidebook_log is not None
    assert issues == ()
    return AuxiliaryMetadataFile(
        source=source,
        raw_text=raw_text,
        encoding="utf-8",
        key_values=(
            TextMetadataEntry(
                line_number=1,
                key="Export Date-Time",
                value="07/13/2026 11:47:1",
                raw_line="Export Date-Time: 07/13/2026 11:47:1",
            ),
        ),
        unparsed_lines=(),
        slidebook_log=slidebook_log,
    )

def _auxiliary_metadata() -> AuxiliaryMetadataFile:
    source = SourceFile(path=Path("acquisition.txt"), original_name="acquisition.txt")
    return AuxiliaryMetadataFile(
        source=source,
        raw_text="operator: Ada",
        encoding="utf-8",
        key_values=(TextMetadataEntry(line_number=1, key="operator", value="Ada", raw_line="operator: Ada"),),
        unparsed_lines=(),
    )


def _sheet_names(path: Path) -> list[str]:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("xl/workbook.xml"))
    return [sheet.attrib["name"] for sheet in root.findall("main:sheets/main:sheet", NS)]


def _sheet_cells(path: Path, sheet_number: int) -> dict[str, str]:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read(f"xl/worksheets/sheet{sheet_number}.xml"))
    cells = {}
    for cell in root.findall(".//main:c", NS):
        ref = cell.attrib["r"]
        inline = cell.find("main:is/main:t", NS)
        value = cell.find("main:v", NS)
        if inline is not None:
            cells[ref] = inline.text or ""
        elif value is not None:
            cells[ref] = value.text or ""
        else:
            cells[ref] = ""
    return cells


def _sheet_styles(path: Path, sheet_number: int) -> dict[str, str]:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read(f"xl/worksheets/sheet{sheet_number}.xml"))
    return {cell.attrib["r"]: cell.attrib.get("s", "0") for cell in root.findall(".//main:c", NS)}


def _sheet_widths(path: Path, sheet_number: int) -> dict[str, float]:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read(f"xl/worksheets/sheet{sheet_number}.xml"))
    widths = {}
    for col in root.findall("main:cols/main:col", NS):
        start = int(col.attrib["min"])
        end = int(col.attrib["max"])
        width = float(col.attrib["width"])
        for index in range(start, end + 1):
            widths[_column_name(index)] = width
    return widths


def _column_name(index: int) -> str:
    name = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _zip_texts(path: Path) -> list[str]:
    with ZipFile(path) as archive:
        return [
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xml")
        ]


if __name__ == "__main__":
    unittest.main()
