# Capture 1 + Position 1 static visual validation

Date: 2026-07-13

## Regenerated Module 13 correction

D042 confirms that the intended manual-workflow ratio is `C0 / C1`. This report
previously calculated `C1 / C0`, producing 2.77-10.86. That histogram, its
examples, and its prior causal explanation remain superseded and must not be
used scientifically.

D043 records the user's confirmation that manual “average intensity” means the
ROI arithmetic mean after background subtraction. The static HTML, audit CSVs,
manifest, charts, and workbook were regenerated from the corrected Module 13.
The 72 corrected-mean C0/C1 values range from approximately 0.0921 to 0.3606,
with median 0.1990. Raw-mean C0/C1 remains separate and ranges from approximately
0.1184 to 0.3675.

The image evidence remains valid: the unchanged P99 mask contains only 1% of
C1 pixels and traces bright puncta or clipped fragments rather than the full
shape of many visible cells. Many potentially valid cell regions were never
segmented; they were not rejected later as ROI.

## Scope

Generate one static, auditable diagnostic report for the D039 real-pair run.
The report observes the existing outputs from Modules 1-8 and 10-13. It does
not build a GUI, edit ROI, change the D039 profile, or approve production
scientific parameters.

Input pair:

- `raw_data/Capture 1 - Position 1_XY1757012095_Z0_T0_C0.tif`;
- `raw_data/Capture 1 - Position 1_XY1757012095_Z0_T0_C1.tif`;
- the explicitly associated SlideBook `.log`.

The output manifest records absolute source paths, sizes, and SHA-256 hashes.
Raw source files were read only and were not overwritten.

## Static artifacts

The main artifact is:

- `outputs/capture1_position1_static_validation_20260713/capture1_position1_static_validation.html`.

Its companions include original-frame PNGs, the preprocessed frame, the binary
mask, pre- and post-geometry SVG overlays, a PNG overlay preview, SVG scatter
and histogram charts, `roi_audit.csv`, `roi_measurements.csv`, `module_io.csv`,
and `audit_manifest.json`.

The HTML is a static document with relative local assets. It contains no GUI,
JavaScript controls, navigation state, manual-decision storage, or ROI editing.

## Step-by-step result

1. The original first frames of C0 and C1 are displayed using a display-only
   P1-P99.5 stretch.
2. Module 5 selected C1 by robust first-frame contrast: C0 was 279 and C1 was
   approximately 1435.05. The selection method remains unchanged.
3. Module 6 used identity preprocessing. The displayed processed frame is the
   C1 first frame converted to `float64` without pixel subtraction.
4. Module 7 used the unchanged P99 rule. The observed threshold was
   approximately 8899.03 and exactly 3,600 of 360,000 pixels were foreground.
5. Those pixels formed 58 eight-connected components before geometry.
6. Module 8 retained 36 components and rejected 22. The numbered overlay uses
   the original labels and the adjacent report table gives each rejection
   reason. Twenty rejected labels were below the 20-pixel validation minimum;
   four touched a border, with overlapping reasons possible.
7. The report summarizes areas, accepted-ROI intensities, four channel-frame
   background estimates, observed maxima, and possible saturation evidence.
8. Corrected C0 versus corrected C1 is plotted for every retained ROI in each
   frame, with the original ROI number displayed. Donor/FRET labels remain
   separate biological provenance.
9. The corrected-mean C0/C1 histogram includes all 72 ROI-frame records. The
   three lowest and three highest records are shown only as descriptive
   inspection examples, not as a ratio acceptance interval.
10. The final table records the input and output boundary for every module used
    by this validation.

## Explicit region categories

- **Never segmented:** 356,400 pixels remained label 0 after Module 7. These
  pixels are not ROI, so they have no geometric or intensity rejection reason.
  This is a pixel count and must not be interpreted as a count of missed cells.
- **Segmented then rejected geometrically:** 22 of 58 components were removed
  by the unchanged size/border profile before Modules 10-13.
- **Excluded by intensity or saturation:** zero ROI. Saturation fractions and
  background-aware metrics were recorded, but D039 has no enabled saturation
  or low-signal thresholds. Zero therefore means no exclusion decision was
  configured, not that scientific validity was demonstrated.
- **Retained geometrically:** 36 ROI proceeded to intensity and ratio
  calculation. Their area range was 23-441 pixels and median area was 60.5
  pixels. “Retained” is intentionally not called “production accepted.”

## Intensity, background, and possible saturation evidence

The provisional non-ROI P20 backgrounds were:

| Channel | Frame 0 | Frame 1 |
| --- | ---: | ---: |
| C0 | 299 | 296 |
| C1 | 358 | 357 |

Observed frame maxima were 39,627 and 40,662 for C0, and 64,035 in both C1
frames. The D039 validation-only ceiling of 65,535 counted zero saturated
pixels. A clearly labeled diagnostic comparison counted pixels at or above
4,095: 1,499 and 1,507 for C0, and 8,702 and 8,675 for C1. Because 4,095 is
only an example candidate ceiling and the TIFFs contain much larger values,
this comparison does not identify saturation or select a camera profile.

## Investigation of the 2.77-10.86 ratios

**Superseded by D042:** the following section documents the inverted C1/C0
diagnostic that exposed the error. It is retained for audit history only.

With the provisional SlideBook channel roles, Module 13 produced 72 corrected
mean ratios from approximately 2.7729 to 10.8600, with median 5.0275. Raw-mean
C1/C0 ratios ranged from approximately 2.7214 to 8.4457.

The P99 mask conditions inclusion on exceptionally high C1 signal but does not
require similarly high C0 donor signal. This creates a selection bias toward a
large FRET numerator. Across the retained ROI-frame records, ratio and corrected
C0 donor had correlation approximately -0.7303. The largest ratio was ROI 2,
frame 0: corrected C0 approximately 897.67 and corrected C1 approximately
9748.67, giving 10.8600. Subtracting the C0 background can further reduce an
already modest denominator.

The diagnostic pixel-pool comparison was:

| C1 pool | Pixels | Threshold | Corrected C1/C0 ratio of pool means |
| --- | ---: | ---: | ---: |
| > P90 | 35,958 | 944.00 | 4.724 |
| > P95 | 18,000 | 1793.05 | 4.745 |
| > P98 | 7,200 | 5010.02 | 4.449 |
| > P99 | 3,600 | 8899.03 | 4.041 |

This comparison is descriptive and is not a reconfigured pipeline. It shows
that selecting bright C1 pixels does enrich the numerator, but the complete
P99 pool does not itself have a ratio near 10.86. The extreme upper ROI ratios
appear when that sparse pool is split into small connected components with
heterogeneous and sometimes much lower C0 denominators. The conclusion is
therefore more specific than “P99 makes every ratio high”: P99 selects C1-bright
puncta, while component-level donor variability and background correction
amplify the upper tail.

No production percentile, area, intensity, saturation, or ratio threshold is
selected by this analysis.

## Regenerated C0/C1 result

Module 13 now indexes the pair by acquisition channel rather than by donor/FRET
role. C0 is always the numerator and C1 is always the denominator. The primary
manual-workflow calculation uses each channel's background-corrected ROI mean.
The generated CSV and workbook also retain raw means and corrected means as
distinct fields.

The regenerated corrected-mean C0/C1 distribution contains 72 records, ranges
from 0.092081 to 0.360629, and has median 0.1990. The corresponding raw-mean
C0/C1 diagnostic ranges from 0.1184 to 0.3675. These figures replace the
superseded inverse distribution but remain validation-only because the P99 mask
does not outline complete cells.

## Channel-role provenance

The SlideBook log identifies:

- C0: `i_FRET_By_(CFPex/CFPem[F])`;
- C1: `i_FRET_bY_(CFPex/YFPem[F])`.

The validation preserves C0 CFPex/CFPem as donor and C1 CFPex/YFPem as FRET,
matching the log. This remains pending scientific confirmation and does not
resolve P011. Exposure, gain, detector scaling, donor bleed-through, direct
acceptor excitation, and any required instrumental correction are not yet
known from the current project records.

## Verification and limitation

- Module 13 and all related report, harness, and exporter tests pass.
- All generated SVG files parse as XML.
- The manifest references 13 present artifacts and three hashed source files.
- `roi_audit.csv` has 58 rows; `roi_measurements.csv` has 72 rows.
- The original C0/C1 images, binary mask, and numbered PNG overlay received a
  visual pass at their native 600 x 600 resolution.
- The complete project suite passes on 88 tests.
- All 15 workbook sheets rendered successfully; the workbook contains the
  explicit C0/C1 formula and superseded markers, with zero formula errors.
- The in-app browser security policy blocked loading the local `file://` HTML,
  so the complete assembled page could not receive a browser-rendered visual
  pass in this session. Static structure and asset presence were validated,
  and the key raster outputs were reviewed directly.

## Scientific questions still pending

1. Does the experimental protocol confirm the SlideBook role interpretation
   C0 donor and C1 FRET for this acquisition family?
2. What camera mode, effective ceiling, exposure, gain, and scaling produced
   these pixel values?
3. Are the C1-bright puncta valid cellular structures for the intended analysis,
   or evidence that a whole-cell segmentation engine is required?
4. Which bleed-through, direct-excitation, detector-response, or other optical
   corrections are scientifically required before interpreting absolute ratios?
5. Which production preprocessing, segmentation, quantitative-background, and
   QC profiles should be evaluated on representative data?
