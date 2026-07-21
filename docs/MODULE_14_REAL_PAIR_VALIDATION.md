# Module 14 real-pair integration validation

Date: 2026-07-13

## Regenerated ratio correction

D042 confirms that the intended ratio is C0/C1, and D043 confirms that the
manual average is the ROI mean after background subtraction. The workbook has
been regenerated from the corrected Module 13. It now records C0 as numerator,
C1 as denominator, `background_corrected_mean` as the active measurement, and
the earlier D039/D041 C1/C0 results as superseded.

## Scope

Validate one real SlideBook C0/C1 TIFF pair through the existing Module 1-8
and 10-14 interfaces. This is an integration and export validation only. It is
not a production scientific analysis and does not resolve any pending
acquisition-profile decisions.

## Input

- `raw_data/Capture 1 - Position 1_XY1757012095_Z0_T0_C0.tif`
- `raw_data/Capture 1 - Position 1_XY1757012095_Z0_T0_C1.tif`
- the associated SlideBook `.log`, matched through its explicit TIFF table

The harness reads source files without modifying or overwriting them.

## Validation-only profile

- experiment label: `Real Pair Integration Validation`;
- segmentation channel: automatic robust first-frame comparison;
- segmentation preprocessing: identity;
- segmentation engine: deterministic percentile-threshold connected
  components, 99th percentile, 8-connectivity;
- geometry: minimum 20 pixels, no maximum, exclude border-touching objects;
- quantitative background: 20th percentile of non-ROI pixels;
- camera ceiling: explicit validation-only value `65535`;
- saturation decisions: disabled, metrics preserved only;
- low-signal decisions: disabled because no thresholds are approved;
- provisional channel roles: C0 donor and C1 FRET;
- provisional baseline: frame 0;
- frame times: unknown.

Every provisional assumption is preserved in the workbook, including the
structured `real_data_validation_profile_not_production` warning.

## Results

- C1 was selected for segmentation. Robust contrast scores were 279 for C0
  and approximately 1435.05 for C1.
- The placeholder engine produced 58 connected components.
- Geometry filtering retained 36 labels and rejected 22.
- Module 12 emitted 144 intensity records: 36 ROIs x 2 channels x 2 frames.
- Module 13 emitted 72 FRET records: 36 ROIs x 2 frames.
- Corrected-mean C0/C1 ranges from approximately 0.0921 to 0.3606, with median
  0.1990. The raw-mean values remain separate in `intensity_long`.
- Module 14 generated one workbook with the expected 15 sheets.
- The workbook preserves the verified SlideBook log association and structured
  acquisition metadata.

## Validation-driven correction

The first rendered workbook exposed that unknown frame times were displayed as
`0, 1` beneath `time_s / seconds`. This contradicted D035 because those values
were frame indices, not measured seconds. The exporter now uses
`frame_index / index` whenever any exported frame time is unknown, and retains
`time_s / seconds` only when all exported frame times are known.

## Workbook verification

- Imported successfully with the bundled spreadsheet runtime.
- All 15 sheets rendered to PNG and received a visual pass.
- The D032 value-sheet layout and D034 audit-sheet widths remained legible.
- The key `ratio!A1:J12` range showed `frame_index / index` and frames 0 and 1.
- The `parameters` sheet contains `ratio_formula = C0/C1`, explicit numerator
  and denominator channels, the corrected-mean definition, and superseded
  markers for the earlier C1/C0 outputs.
- The non-production validation warning was found in the `issues` sheet.
- No matches were found for `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, or `#N/A`.

Artifacts are under `outputs/module14_real_pair_validation_20260713/`.

The subsequent static ROI review is recorded in
`docs/MODULE_9_STATIC_ROI_OVERLAY_VALIDATION.md`.

## Scientific limitation

The numerical values and ROI set must not be interpreted as production-ready.
The segmentation engine/profile, ROI geometry, camera ceiling, QC thresholds,
background method, C0/C1 biological roles, and baseline window still require
representative-image review and scientific approval.
