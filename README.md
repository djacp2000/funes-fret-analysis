# F.U.N.E.S. — FRET Unified Normalization and Extraction Suite

**FUNES Lite** is a portable Windows application for automatic and **provisional** analysis of two-channel FRET time-series exported from SlideBook as TIFF files. It does not require installing Python or using a command line.

It analyzes every valid C0/C1 acquisition it finds, segments cells on the first frame, keeps the same masks for both channels and all frames, and calculates the explicit `C0 / C1` ratio.

> **Important:** FUNES Lite is not scientifically validated and is not clinical software. Its analysis is automatic and provisional; review the results, masks, and reports before using them for scientific conclusions.

## What a user can run today

The `FUNES_lite_standalone_v1` distribution includes this structure:

```text
FUNES_lite_standalone_v1/
├── FUNES_lite_standalone_v1.exe
├── funes_files/
├── input/
├── output/
└── README.txt
```

Run `FUNES_lite_standalone_v1.exe`. The window shows progress by position and total progress; it asks for no parameters, confirmations, or arguments. The application starts processing the contents of its neighboring `input/` folder automatically.

All valid pairs are labeled as `Experiment 1` in this Lite edition. Experiment assignment, manual ROI review, and reviewed-analysis workflows are not part of the Lite interface.

## Prepare Input

1. Copy the TIFF files for one or more acquisitions into the `input/` folder without modifying the originals.
2. Each position must have one `C0` TIFF and one `C1` TIFF with the same acquisition identity. `.tif` and `.tiff` extensions are accepted.
3. Keep the pattern exported by SlideBook, for example:

   ```text
   Capture 1 - Position 1_XY1782521382_Z0_T00_C0.tif
   Capture 1 - Position 1_XY1782521382_Z0_T00_C1.tif
   ```

   The `Capture`, `Position`, `XY`, `Z`, and `T` fields are preserved as metadata. Each TIFF is interpreted as an ordered temporal sequence of frames: `Z` and `T` in the filename do not redefine that sequence.

4. You may include auxiliary SlideBook files, such as `.log` or `.txt`, alongside the TIFFs. They are preserved when they can be unambiguously associated with the pair.

The application only reads the input TIFFs and auxiliary files; it does not rename, overwrite, or modify them.

## Get Results

When processing finishes, review the `output/` folder:

| Location | Contents |
| --- | --- |
| `output/workbooks/` | Excel `.xlsx` workbook(s) with exported results. |
| `simple_results` sheet | One row per experiment, capture, position, ROI, and frame; includes `C0_mean`, `C1_mean`, and `ratio_C0_C1`. The means on this sheet are background-corrected. |
| `intensity_long` sheet | Detailed measurements, including raw intensities, for traceability. |
| `output/roi_overlays/` | First-frame ROI masks in PNG and SVG for visual review. |
| `output/position_reports/` | One HTML report per completed or failed position. |
| `output/simple_analysis_summary.json` | Batch summary: created workbooks, completed pairs, failures, and discovery/validation issues. |

Segmentation automatically selects channel C0 or C1 using a robust first-frame signal metric. Each accepted ROI remains fixed for C0, C1, and all temporal frames. The application performs background correction and calculates `C0 / C1`; the parameters for this Lite route are fixed and provisional.

A failure in one position does not prevent processing the other valid positions. See that position's HTML report for the error. The batch stops only if `input/` cannot be read, `output/` cannot be used, or no valid pair can be exported.

## Optional Python Route

To run the same automatic route from a repository clone, for developers or technical users, Python 3.10 or later and the project dependencies are required:

```powershell
python -m pip install -e .
python scripts/run_simple_fret_analysis.py input output
```

The first argument is the input folder and the second is the output folder. This route generates the same provisional result types; it does not turn the analysis into scientific validation.

To build the portable Windows distribution:

```powershell
python -m pip install -e ".[standalone]"
python scripts/build_funes_lite_standalone.py
```

The build creates `dist/FUNES_lite_standalone_v1/` and its ZIP. Both are generated artifacts ignored by Git; they are not part of the published source code.

To check the project contracts with synthetic data:

```powershell
python -m unittest discover -s tests
```

## Known Limits

- FUNES Lite does not automatically correct drift or provide interactive ROI editing.
- Lite ROI size limits, segmentation, and quality criteria do not replace experiment-specific scientific configuration or review.
- Results must be reviewed with the masks and side reports before interpretation.
- The Lite route does not run the modular project's review, authorization, or analysis-activation workflows.

## For Developers

FUNES keeps a modular architecture for file discovery, TIFF reading, auxiliary metadata, segmentation, quality control, temporal extraction, FRET calculation, and auditable export. The specifications, decisions, and module status are in [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md), [docs/MODULE_PLAN.md](docs/MODULE_PLAN.md), and [docs/DECISIONS.md](docs/DECISIONS.md).

## License

MIT. See [LICENSE](LICENSE).
