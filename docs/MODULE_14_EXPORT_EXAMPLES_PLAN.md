# Module 14 Export Examples Plan

This document plans the example outputs that should be generated and reviewed
before Module 14 export formatting is finalized.

## Scope for this planning step

- Plan example workbook variants only.
- Do not implement exporter code.
- Do not choose the final workbook structure.
- Do not add production spreadsheet dependencies.
- Keep CSV and other machine-readable outputs as candidate companions, not
  finalized deliverables.

## Existing upstream data to represent

Module 14 examples should be based on the current upstream records rather than
invented export-only structures:

- Experiment, Capture, Position, channel, frame, and ROI identifiers.
- Source TIFF filenames, source paths, parsed filename metadata, TIFF metadata,
  and auxiliary text metadata when available.
- Module 8 ROI geometry status, area, bounds, centroid, and rejection or flag
  reasons.
- Module 10 quantitative background estimates by channel and frame.
- Module 11 QC records at field, field-frame, ROI, and ROI-frame scopes.
- Module 12 temporal intensity records by ROI, channel, and frame.
- Module 13 FRET calculation records by ROI and frame, including channel
  mapping, baseline settings, ratio, R/R0, delta R/R0, statuses, and reasons.
- Pipeline issues and method parameters from each module.

## Example workbook variants to generate later

These are review candidates, not final formats.

### Example A: analysis-first long workbook

Purpose: prioritize downstream analysis and filtering.

Candidate sheets:

- `fret_long`: one row per Experiment/Capture/Position/ROI/frame with donor,
  FRET, ratio, R/R0, delta R/R0, statuses, and reasons.
- `intensity_long`: one row per Experiment/Capture/Position/ROI/channel/frame
  with raw, background, corrected, and QC fields.
- `roi_summary`: one row per ROI with geometry, aggregate QC, and inclusion
  status.
- `field_summary`: one row per Experiment/Capture/Position with frame count,
  ROI counts, field QC, and issue counts.
- `metadata`: source files, filename metadata, TIFF metadata summaries, and
  auxiliary text metadata references.
- `parameters`: method names and parameter values used by upstream modules.
- `issues`: structured warnings and errors with context.

Review question: is this enough for analysis without forcing users to reshape
the data manually?

### Example B: human-review wide workbook

Purpose: make experiment/capture/position blocks visually easy to scan.

Candidate sheets:

- `fret_by_roi`: grouped by Experiment/Capture/Position, with frame or time as
  rows and one column group per ROI for ratio, R/R0, delta R/R0, and status.
- `donor_by_roi`: same grouping, one column per ROI for donor corrected values.
- `fret_channel_by_roi`: same grouping, one column per ROI for FRET-channel
  corrected values.
- `qc_overview`: compact block-level summary of pass, flagged, excluded, and
  missing counts.
- `roi_summary`: ROI geometry and aggregate status.
- `metadata_notes`: concise metadata and provenance sheet.

Review question: do wide ROI views help manual review enough to justify their
extra formatting complexity?

### Example C: audit-focused workbook plus companion CSVs

Purpose: separate a readable workbook from robust machine-readable files.

Candidate workbook sheets:

- `summary`: experiment/capture/position overview and inclusion counts.
- `fret_review`: compact FRET values and statuses for human inspection.
- `qc_review`: reasons and affected scopes summarized for review.
- `metadata`: human-readable provenance summary.

Candidate companion files:

- `fret_long.csv`
- `intensity_long.csv`
- `roi_summary.csv`
- `background_long.csv`
- `qc_long.csv`
- `issues.csv`
- `parameters.csv`

Review question: should the workbook be lighter if CSVs carry the complete
analysis-grade records?

## Synthetic example cases to include

Each candidate layout should be generated from small synthetic data with enough
variation to reveal layout problems:

- Two experiments with different captures and positions.
- At least one position with multiple ROIs and multiple temporal frames.
- One ROI that passes all QC.
- One ROI with a flagged frame.
- One ROI or frame excluded because of QC.
- One missing or unavailable corrected value.
- One unavailable baseline or normalization case.
- Both known and unknown frame time examples.
- Preserved auxiliary metadata and at least one structured pipeline issue.

## Review criteria

Compare examples using these criteria before choosing a final format:

- Can a scientist trace every result back to Experiment > Capture > Position >
  ROI > frame?
- Are raw, background-corrected, ratio, and normalized values clearly separated?
- Are QC statuses and exclusion reasons visible without hiding analysis data?
- Are source filenames, metadata, parameters, and pipeline issues auditable?
- Is the workbook readable on screen without excessive horizontal scrolling?
- Is the data easy to import into analysis tools without merged-cell problems?
- Are experiment/capture/position separators visually clear in human-readable
  sheets?
- Is file size likely to remain manageable for realistic experiments?

## Decisions deliberately left open

- Final sheet names and ordering.
- Whether Excel is the only primary output or paired with required CSV files.
- Whether wide ROI views are primary, secondary, or omitted.
- Whether to use formatting features such as frozen panes, filters, tables,
  conditional formatting, and separators.
- Exact column names and column ordering.
- How much raw TIFF and auxiliary metadata belongs in the workbook versus
  companion machine-readable files.
- Any dependency choice for writing `.xlsx` files.

## Review feedback received

The first visual review selected the human-review wide layout as the preferred
basis for the final Module 14 export specification.

Confirmed direction:

- Rows should be elapsed-time timepoints, such as 0, 2, 4, 6 seconds, continuing
  according to the acquisition interval.
- Each ROI should be side-by-side in columns, with one ROI per column in the
  main value matrix for a given measurement view.
- Row 6 should display the ROI label, and row 7 should display the abbreviated
  full ROI identity as `cN/pN/rN`, for example `c1/p1/r1`, `c1/p1/r2`, and
  `c1/p2/r1`.
- Prefer separate value sheets or clearly separated views for different
  measurement types, rather than splitting each ROI into multiple subcolumns in
  the main review matrix.
- Position and capture boundaries should be visible as empty spacer columns.
- Single and double spacer columns should use different colors to distinguish
  position-level and capture-level breaks.
- Each experiment should be separated into its own spreadsheet-level export
  unit.

Still pending:

- Decide whether complete long/tidy data should also be included as hidden or
  secondary sheets, companion CSV files, or omitted from the first final
  workbook specification.

Refined example generated:

- `outputs/module14_refined_roi_columns_example_20260712/` contains a refined
  non-final example using one workbook file per synthetic experiment. The value
  sheets use elapsed-time rows, one ROI per column, abbreviated ROI identity in
  row 7, blue position spacer columns, and double peach capture spacer columns.
