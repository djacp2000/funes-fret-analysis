# Module 9 static ROI overlay validation

Date: 2026-07-13

## Scope

Generate and review the static quality-control substitute allowed by Module 9
for the existing D039 real-pair validation. The interactive viewer, ROI deletion,
mask editing, and persistence of manual decisions remain deferred.

## Input and provenance

- pair: `Capture 1 + Position 1`;
- temporal frame: first ordered frame (`frame_index=0`);
- segmentation channel: C1, selected by the Module 5 robust comparison;
- segmentation and geometry: the unchanged D039 validation-only profile;
- source labels: all 58 labels from the Module 7 placeholder engine;
- status records: the unchanged Module 8 geometry decisions.

The overlay does not recalculate, renumber, accept, reject, or edit any ROI.

## Implemented static output

- Embeds the selected grayscale frame in an auditable SVG.
- Uses the original segmentation label as the displayed ROI number.
- Shows accepted contours as solid cyan, flagged contours as dotted yellow,
  and rejected contours as dashed coral, pairing color with line pattern.
- Records status and rejection reasons as SVG data attributes.
- Includes a legend, status counts, the validation-only warning, and display
  stretch values.
- Produces a dependency-free PNG view with the same contours and numbers for
  local visual inspection.
- Uses a display-only P1-P99.5 grayscale stretch. For this frame the observed
  endpoints were 281.0 and approximately 14221.1. This changes only display
  contrast and has no effect on segmentation or measurement values.

Artifacts:

- `outputs/module9_static_roi_overlay_20260713/capture1_position1_roi_overlay.svg`
- `outputs/module9_static_roi_overlay_20260713/capture1_position1_roi_overlay.png`

## Geometry summary

- 58 source labels were displayed.
- 36 were retained and 22 were rejected; none were flagged by this profile.
- Retained areas ranged from 23 to 441 pixels, with median 60.5 pixels.
- 25 of 36 retained labels had area at or below 100 pixels; 14 were at or
  below 50 pixels.
- Rejected areas ranged from 1 to 76 pixels, with median 8 pixels.
- 20 rejected labels included `roi_area_below_minimum`.
- 4 rejected labels included `roi_touches_border`; reason counts overlap when
  one label fails both criteria.

## Visual review

The overlay is legible at the native 600 x 600 frame size. Original labels can
be related directly to the geometry records, and border rejections are visible
at the image edges.

The retained contours predominantly trace isolated high-intensity puncta or
small compact signal clusters. They do not consistently outline complete cell
bodies in the first C1 frame. Several nearby bright structures are represented
as separate small labels, while dimmer apparent cellular regions are not
enclosed. This is consistent with a 99th-percentile connected-component
placeholder rather than a production cell-segmentation model.

## Conclusion

The static overlay exporter is suitable as a non-interactive QC artifact, but
the displayed ROI set does not justify approving the current segmentation
engine, percentile, area limit, or border policy for production use. No
scientific threshold or production segmentation choice is made in this review.
The next choice requires representative-image review by the scientific user
and an explicit candidate-engine/evaluation decision.
