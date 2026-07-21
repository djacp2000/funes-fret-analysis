# Module 7 explicit OFAT visual-review artifacts

## Scope

This record covers only the next D047 block: an explicit `Capture + Position`
review set, explicit OFAT variants, and static auditable artifacts. It does not
assess whether the field set is sufficient, rank or classify methods or
variants, approve a profile, or write to the D046 review ledger.

## Explicit selection

Selection identifier: `module7_ofat_kmeans_review_20260714`.

Fields:

- `Capture 1 + Position 1`
- `Capture 1 + Position 2`

These are the two currently available real fields in `raw_data/`. Their
inclusion is an explicit review-set choice, not a sample-size conclusion. Module
5 selected C1 for both fields and Module 6 used identity segmentation
preprocessing. Source paths, source SHA-256 values, channel contrasts,
preprocessing parameters, prepared-frame hashes, shapes, and dtypes are saved
in `selection.json`.

Variants:

- K-means `benchmark_baseline`
- `foreground_cluster_count = 1`
- `minimum_object_area_pixels = 32`
- `minimum_object_area_pixels = 128`
- `opening_disk_radius = 0`
- `opening_disk_radius = 2`
- `closing_disk_radius = 1`
- `closing_disk_radius = 5`

These are the eight unchanged D047 K-means variants. No Cellpose or other
method was selected in this block, and no comparison across methods was made.

## Artifact package

The package is `outputs/module7_ofat_review_20260714_kmeans/` and contains 16
explicit runs: two fields times eight variants. It includes:

- `index.html`: static comparison index with explicit scope warnings;
- `selection.json`: exact field and variant selection and preparation
  provenance;
- `runs.csv`: descriptive D047 mask geometry only;
- `review_observations.csv`: per-run human visual observations, with reviewer
  and review-time provenance left blank rather than invented and with no
  classification or approval fields;
- `runs/*/labels.npy`: exact original integer label images;
- `runs/*/overlay.svg`: numbered, unclassified contours on the prepared frame;
- `runs/*/preview.png`: raster previews using the same single unclassified
  contour color;
- `manifest.json`: source hashes plus SHA-256 and byte size for every artifact.

The package records `sample_sufficiency_assessed=false`,
`method_ranking_performed=false`, `profile_approval_performed=false`, and
`d046_review_ledger_used=false`.

## Technical verification

- All 16 runs completed with no engine fallback.
- Exactly 16 SVG overlays, 16 PNG previews, and 16 NPY label images were
  generated.
- The manifest covers 52 package artifacts in addition to its own file.
- Focused D047, visual-review, and unchanged D046 tests pass.
- All 16 PNG previews were inspected at native 600 by 600 resolution. The
  three scientific note fields in every `review_observations.csv` row record
  only visible whole-cell-shape coverage, touching-object appearance, and
  other visible contour features. Reviewer and review-time fields remain blank.
- Across both fields, the contours visibly concentrate on high-intensity
  subregions while many dimmer cellular silhouettes and peripheral extensions
  remain unoutlined. Connected bright lobes sometimes share a continuous
  contour without a visible internal division; small isolated bright foci and
  border-intersecting contours also occur. The per-run wording is preserved in
  `review_observations.csv` rather than converted into a variant category.

The environment emitted a `joblib` warning because Windows Management
Instrumentation could not report physical-core count; execution used the
logical-core count. The warning did not block or substitute any run.

## Still pending

No conclusion about the selected field set or preferred K-means variant has
been recorded. Sample sufficiency remains unassessed; the package does not
evaluate the other D047 methods and does not calibrate, approve, or register
`strict`, `medium`, or `permissive` profiles. The D046 ledger remains unused
and unchanged.

A later read-only cross-method synthesis completes preview coverage of all
eight K-means and all nine Marker Watershed variants without modifying this
package. It is
`docs/MODULE_7_KMEANS_MARKER_WATERSHED_VISUAL_SYNTHESIS.md` and includes the
exact P2-R4 correction and the D051/D052 evidence boundary.
