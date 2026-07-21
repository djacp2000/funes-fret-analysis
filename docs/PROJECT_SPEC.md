# FRET Analysis Project Specification

## 1. Goal

Create a modular Python program to analyze two-channel FRET time-series exported from SlideBook as TIFF files.

The program will eventually:

- discover and pair C0/C1 TIFF files;
- preserve acquisition metadata and associated text metadata;
- organize acquisitions into experiments, captures, and positions;
- segment cells;
- create fixed cell ROIs;
- estimate background;
- reject or flag invalid ROIs;
- extract temporal channel intensities;
- calculate FRET ratios and normalization;
- export auditable results.

Development must proceed in short, separate sessions so that each module can be understood, tested, and modified without reviewing a monolithic codebase.

### Operational target of the automation

The core workflow being automated is intentionally simple:

1. view the cell in the first temporal frame;
2. define one ROI that follows the visible shape of the complete cell rather
   than only its brightest subregions;
3. apply that fixed ROI to every timepoint in both channels;
4. extract average intensity from C0 and C1 for each timepoint;
5. calculate `C0 / C1`;
6. write the timepoint-by-timepoint result to an Excel table.

Metadata preservation, background estimation, quality control, audit trails,
and replaceable algorithms support this workflow. They must not obscure or
replace its central measurement objective.

## 2. Input naming pattern

Representative filenames:

```text
Capture 1 - Position 1_XY1782521382_Z0_T00_C0.tif
Capture 1 - Position 1_XY1782521382_Z0_T00_C1.tif
Capture 1 - Position 2_XY1782521382_Z0_T00_C0.tif
Capture 1 - Position 2_XY1782521382_Z0_T00_C1.tif
Capture 2 - Position 1_XY1782521382_Z0_T00_C0.tif
Capture 2 - Position 1_XY1782521382_Z0_T00_C1.tif
```

The exact extension may be `.tif` or `.tiff`.

Fields to parse and preserve:

- Capture
- Position
- XY
- Z token
- T token
- Channel
- Original filename
- Full source path

`XY`, `Z`, and `T` are metadata. They are not currently used to organize the temporal frames.

## 3. Logical hierarchy

```text
Experiment
└── Capture
    └── Position
        ├── C0 TIFF
        └── C1 TIFF
```

The `Experiment` label is above Capture. Several captures and positions can belong to the same experimental condition or experiment within one acquisition batch.

Experiment labels may initially be assigned using a simple mapping or configuration file. A future interface may make this easier.

## 4. Temporal interpretation

Every TIFF contains a temporal sequence.

SlideBook may store or export that sequence as TIFF pages, a time axis, a Z axis, or another multidimensional arrangement. The reader must convert the ordered images into a standard internal temporal-frame sequence without interpreting them as biological Z depth.

Use neutral internal terms:

- `frame_index`
- `time_seconds`, only when known or supplied

Do not assume the time interval is present. Preserve it if found; otherwise allow it to remain unknown until configured.

## 5. Pair-level analysis

The initial unit of analysis is one paired acquisition:

```text
Capture N + Position M + C0/C1
```

The pair must be validated for:

- matching width and height;
- matching temporal-frame count;
- readable image data;
- compatible frame ordering;
- metadata inconsistencies worth reporting.

## 6. Segmentation

### Initial behavior

- Use the first temporal frame.
- Compare C0 and C1 using a robust signal metric.
- Select the channel with stronger usable cellular signal for segmentation.
- Do not select based on a single maximum pixel.
- Store which channel and selection method were used.
- Segment cells into individually labeled ROIs.
- A production ROI should follow the visible shape of a complete cell. A mask
  that retains only bright puncta or clips substantial cell regions is not a
  successful whole-cell segmentation merely because it produces connected
  components.
- Apply the same fixed ROI masks to all temporal frames of both channels.

### Segmentation engine

A prebuilt library such as Cellpose may be used, but it must be encapsulated behind a segmentation interface so it can be replaced or supplemented later.

A simpler classical segmentation method may be retained as a fallback or test implementation.

### Geometry filtering

Configurable parameters include:

- minimum ROI area;
- maximum ROI area;
- exclusion or flagging of border-touching objects;
- objective/cell-type/acquisition profile.

Physical units are preferable when pixel size is available. Pixel units must remain possible when calibration is unknown.

## 7. Optional visual ROI review

A future optional interface may allow:

- viewing the ROI overlay;
- navigating through temporal frames;
- deleting aberrant ROIs;
- inspecting exclusion reasons;
- possibly editing masks later.

This interface is not required for the first working version.

Before a GUI exists, the pipeline may save static quality-control images with numbered ROI contours and status information.

## 8. Background

Background handling is not finalized and must be implemented behind a replaceable interface.

Conceptually separate:

1. Preliminary background or preprocessing used to aid segmentation.
2. Definitive quantitative background used for channel correction.

The definitive background may eventually be:

- calculated separately for C0 and C1;
- calculated per frame;
- based on non-cell pixels after mask dilation;
- replaced by manual or local methods when needed.

Do not finalize the scientific method without recording the decision.

## 9. Intensity quality control

### Saturation

- Saturation threshold depends on camera mode.
- The meaningful maximum may be around 4095 in one mode and around 65535 in another.
- TIFF dtype alone is not sufficient to determine the true saturation limit.
- Use metadata, a camera profile, or explicit configuration.
- Evaluate the proportion of saturated pixels, not merely whether one pixel reaches the limit.
- Preserve whether exclusion applies to a frame, a ROI, or a complete field.
- Preserve exclusion reason and supporting measurements.

### Low signal

- Signal must be assessed relative to background and background noise.
- Avoid a universal absolute cutoff.
- Under the confirmed `C0 / C1` workflow, the C1 denominator requires particular
  care because low corrected C1 signal can destabilize the ratio. Biological
  donor/FRET roles remain separate provenance and must not silently reverse the
  requested numerator and denominator.
- Criteria and baseline windows remain configurable and pending scientific review.

## 10. Drift and temporal ROI validity

The initial version uses fixed ROIs selected on the first frame, matching the current manual workflow.

Automatic drift correction is deferred.

A later module may compare the first and last frame, or an early and late reference, to flag:

- excessive global field displacement;
- a cell leaving its ROI;
- a substantial shape change;
- focus loss;
- a field that should be excluded.

## 11. Measurements

For every accepted or flagged ROI, frame, and channel, preserve enough information to support later analysis. Candidate measurements include:

- raw mean intensity;
- raw median intensity;
- background estimate;
- background-corrected mean;
- background-corrected median;
- saturated-pixel count and fraction;
- ROI area;
- quality-control status and reasons.

Raw and corrected values must remain distinguishable.

## 12. FRET calculations

The numerical FRET module will operate on extracted measurements, not directly on TIFF data.

Candidate calculations include:

```text
ratio = average C0 intensity / average C1 intensity
R/R0
ΔR/R0
```

The first corrected implementation should use the same average-intensity
definition as the manual workflow and preserve raw and background-corrected
values separately. The C0/C1 numerator/denominator order must be explicit and
independent from the recorded biological donor/FRET channel roles.

Baseline definition and handling of excluded frames remain pending decisions.

## 13. Export

Module 14 is pending.

The preferred main format is likely Excel, accompanied by machine-readable CSV or similar data, but no final layout should be implemented before example files are generated and visually reviewed.

Requirements already known:

- separate experiments clearly;
- organize by Experiment > Capture > Position > ROI;
- include metadata from TIFF and associated text files;
- preserve QC status and exclusion reasons;
- support one-column-per-ROI views where useful;
- provide an analysis-friendly long/tidy representation;
- make experiment/capture/position separators visually clear in human-readable workbooks.

Word and plain text may be supplementary outputs, not necessarily the primary numerical format.

## 14. Non-goals for the first version

- Direct reading of proprietary SlideBook `.sld`.
- Automatic drift correction.
- Full interactive ROI editor.
- Final polished GUI.
- Final Module 14 workbook design.
- Automatic interpretation of every possible TIFF axis convention without inspected sample files.
