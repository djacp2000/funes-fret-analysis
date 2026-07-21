# Module 7 corrected next OFAT visual-review selection and Cellpose timed test

## Scope

This record corrects D049. Cellpose CP-SAM is no longer selected as the next
complete D048 artifact block. Marker Watershed is the explicitly selected and
completed next block. This record does not infer sample sufficiency, classify
or rank variants, approve or register a profile, change the global K-means
baseline, or use or modify the D046 review ledger.

## Cellpose CP-SAM operational deferral

The former planned 14-run Cellpose CP-SAM package is withdrawn. No Cellpose
dependency was installed, no Cellpose model or weights were obtained, and no
Cellpose candidate was executed in this block. The former planned destination
`outputs/module7_ofat_review_20260714_cellpose_cpsam/` does not exist.

At the close of the D049 block, Cellpose remained deferred until a separate
session explicitly selected exactly one timed test run and defined an
acceptable operational limit before any complete multi-field or multi-variant
block could be considered. The completed separate test below is an operational
feasibility check only and cannot rank or approve Cellpose scientifically.

## Completed single Cellpose CP-SAM timed test

The required separate session selected exactly one unchanged D047 variant and
one explicitly identified field before execution:

- selection identifier: `module7_cellpose_timed_test_20260714`;
- field: `Capture 1 + Position 1`;
- method/variant: `cellpose_cpsam / benchmark_baseline`;
- selected first-frame channel: C1 by `robust_first_frame_contrast`;
- preprocessing: `identity_segmentation_preprocessing`;
- prepared frame: 600 x 600 `float64`;
- execution: CPU, `gpu = false`, `torch_threads = 1`, model `cpsam_v2`;
- runtime: Python 3.12.13, Cellpose 4.2.1.1, and PyTorch 2.13.0.

`benchmark_baseline` was selected because it is the unchanged D047 reference,
not because it is preferred or scientifically adequate. `Capture 1 + Position
1` was selected because it already has real-chain preparation provenance, not
because it is sufficient or representative.

Exactly one D047 engine call was executed. Its engine-only operational duration
was `3003.7913557` seconds, or 50 minutes 3.791 seconds. This was a cold-cache
call: the `cpsam_v2` 1.15 GB weights were downloaded during model construction,
inside the timed engine boundary. The download progress reported approximately
4 minutes 43 seconds. No second warm-cache call was made, so no warm-cache
duration is claimed. Cellpose also emitted a PyTorch warning that sparse tensor
invariant checks were implicitly disabled; the call nevertheless completed and
the package was written successfully.

The one-run artifact package is
`outputs/module7_cellpose_timed_test_20260714/`. It contains the exact NPY
labels, unclassified SVG overlay, PNG preview, descriptive CSV with the one
operational time, blank human-observation row, explicit selection/preparation
provenance, an HTML index, and source/artifact SHA-256 hashes.

## Operational limit before any complete Cellpose block

The acceptable operational gate is a maximum projected 12 hours of
segmentation-engine time for a complete Cellpose block under the same 600 x 600
CPU configuration. Before such a block may even be considered, calculate the
conservative projection as:

`declared run count x 3003.7913557 seconds per run <= 43,200 seconds`.

This permits consideration of at most 14 declared runs under this gate. A
14-run projection is `42,053.0789798` seconds, or 11 hours 40 minutes 53.079
seconds. The multiplication deliberately applies the cold-cache observation to
every planned run; it is a scheduling bound, not a measured block duration.
Different image dimensions, hardware, GPU use, threading, model, or effective
parameters fall outside this gate and require a separately authorized
operational assessment before a complete block is considered.

Passing this gate does not authorize a block, establish sample sufficiency,
classify or rank variants, approve or register a profile, or establish
scientific Cellpose feasibility. No complete Cellpose block was selected,
approved, or executed in this session.

## Explicit Marker Watershed selection

Selection identifier:
`module7_ofat_marker_watershed_review_20260714`.

Fields:

- `Capture 1 + Position 1`
- `Capture 1 + Position 2`

These are explicit field identities, not a statement that two fields are
sufficient or representative. Both were prepared through Modules 1, 2, 5, and
6. Module 5 selected C1 and Module 6 used identity preprocessing for both.

Variants, in unchanged D047 order:

1. `benchmark_baseline`
2. `ofat__foreground_threshold_scale__0_9`
3. `ofat__foreground_threshold_scale__1_1`
4. `ofat__minimum_object_area_pixels__32`
5. `ofat__minimum_object_area_pixels__128`
6. `ofat__foreground_opening_disk_radius__0`
7. `ofat__foreground_opening_disk_radius__2`
8. `ofat__marker_min_distance_pixels__8`
9. `ofat__marker_min_distance_pixels__16`

The unchanged baseline values are `foreground_threshold_scale = 1.0`,
`minimum_object_area_pixels = 64`,
`foreground_opening_disk_radius = 1`, and
`marker_min_distance_pixels = 12`. Every non-baseline variant changes exactly
the one parameter encoded in its identifier.

## Completed package boundary

The explicit product contains 18 runs: two named fields times nine unchanged
variants. The package is
`outputs/module7_ofat_review_20260714_marker_watershed/` and follows the D048
contract: exact NPY labels, unclassified numbered SVG overlays, PNG previews,
descriptive CSV, blank human-observation fields, selection and preparation
provenance, an HTML index, and source/artifact SHA-256 hashes.

Execution duration is recorded only as operational information for the
segmentation-engine call. It is not a scientific metric and was not used to
order, classify, select, accept, or reject any variant.

## Explicit non-decisions

- Sample sufficiency was not assessed.
- No method or variant was classified or ranked.
- No profile was calibrated, approved, or registered.
- The global K-means `benchmark_baseline` remains unchanged.
- D046 was neither used nor modified.
- No scientific conclusion was drawn from the operational execution time; it
  was used only to define the scheduling gate above.
- The single Cellpose time was not used to rank, classify, accept, or reject a
  method or variant.
- No Cellpose complete block was selected, approved, or executed.
