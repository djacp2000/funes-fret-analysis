# Module 7 Marker Watershed OFAT visual-review artifacts

## Scope

This record covers only the corrected D049 Marker Watershed block under the
D048 static-artifact contract. It contains no sample-sufficiency inference,
scientific classification, ranking, profile approval or registration, global
default change, or D046 review-ledger use.

## Explicit selection

Selection identifier:
`module7_ofat_marker_watershed_review_20260714`.

The selected fields are `Capture 1 + Position 1` and
`Capture 1 + Position 2`. The selected variants are all nine unchanged Marker
Watershed variants from D047, in D047 order:

1. `benchmark_baseline`
2. `ofat__foreground_threshold_scale__0_9`
3. `ofat__foreground_threshold_scale__1_1`
4. `ofat__minimum_object_area_pixels__32`
5. `ofat__minimum_object_area_pixels__128`
6. `ofat__foreground_opening_disk_radius__0`
7. `ofat__foreground_opening_disk_radius__2`
8. `ofat__marker_min_distance_pixels__8`
9. `ofat__marker_min_distance_pixels__16`

No parameter was altered outside the fixed D047 grid.

## Artifact package

The package is
`outputs/module7_ofat_review_20260714_marker_watershed/` and contains 18
explicit runs. It includes:

- `index.html`: static comparison index with the D048 scope warnings;
- `selection.json`: exact field/variant selection and preparation provenance;
- `runs.csv`: descriptive D047 mask geometry and operational engine timing;
- `review_observations.csv`: 18 human-observation rows with reviewer, review
  time, and all three observation fields blank;
- `runs/*/labels.npy`: exact original integer label images;
- `runs/*/overlay.svg`: numbered, unclassified contours;
- `runs/*/preview.png`: raster previews with one unclassified contour color;
- `manifest.json`: source hashes, operational timing scope, and SHA-256 plus
  byte size for every package artifact.

The package records `sample_sufficiency_assessed=false`,
`method_ranking_performed=false`, `profile_approval_performed=false`, and
`d046_review_ledger_used=false`.

## Operational timing

Timing covers only each segmentation-engine call. Across the 18 executions,
the recorded total was 2.865647 seconds, with individual executions from
0.117444 to 0.593892 seconds. These values are operational information only;
they were not used as an accuracy measure or to order, classify, select,
accept, or reject variants.

## Technical verification

- Exactly 18 runs, 18 NPY label images, 18 SVG overlays, and 18 PNG previews
  were generated.
- All NPY arrays are non-negative integer labels with shape 600 by 600.
- All SVG overlays parse as XML and all PNG previews have a valid PNG
  signature.
- The manifest covers 58 artifacts in addition to its own file; all 58 saved
  SHA-256 values were recomputed without mismatch.
- Both selected source TIFF hashes match their recorded provenance.
- All 18 human-observation rows are blank in every human-entered field.
- Focused D047/D048 tests pass with the timing-provenance assertions, and the
  full suite passes on 118 tests.

## Deferred and unchanged work

No visual scientific observations were entered and no conclusion was recorded
about the selected field set or any Marker Watershed variant. No `strict`,
`medium`, or `permissive` profile was calibrated, approved, or registered. The
global K-means baseline and the D046 ledger remain unchanged.

Cellpose CP-SAM is not the next complete block. It remains deferred until a
separate session performs exactly one explicitly selected timed test and
defines an acceptable operational limit before considering any complete
Cellpose block. No Cellpose installation or execution occurred here.

A later read-only cross-method synthesis completes preview coverage of all
nine Marker Watershed and all eight K-means variants without modifying this
package. It is
`docs/MODULE_7_KMEANS_MARKER_WATERSHED_VISUAL_SYNTHESIS.md` and keeps D051
touching-cell interpretation separate from exact mask comparisons while using
D052 as the comparison scope.
