# Module 7 K-means foreground-selection causal-extension design

## Implementation status (2026-07-18)

D063 implements this design and verifies it with synthetic data only. The
single candidate catalog, diagnostic trace, exact two-field package contract,
fixed area of 32 pixels, focused regions, and hash provenance are now present.
No real TIFF was read or segmented in that implementation block. The two real
candidate calls described below remain pending explicit authorization.

## Scope

This document originally designed the minimum post-D061 causal extension. D063
subsequently implements it but does not authorize a real-data run, execute a
real-data segmentation engine,
generate an image, change a registered profile, alter the global K-means
baseline, use D046, or assess sample sufficiency or representativeness.

The only causal question in scope is whether the K-means intensity boundary
used to select foreground contributes to:

- cells wholly omitted in P2-R1; and
- incomplete whole-cell coverage in P1-R4.

Minimum object area is not tested again. The value remains fixed at 32 pixels
throughout the proposed extension.

## Existing evidence and unresolved mechanism

The D061 reference is K-means `minimum_object_area_pixels = 32` on
`Capture 1 + Position 1/2`. Lowering the area limit from 32 to 16 added no
foreground in P2-R1 and did not change P1-R4. The tested area limit therefore
does not explain either key residual defect.

The current K-means engine fits three one-dimensional intensity clusters and
selects the two clusters with the highest centers. Its saved foreground OFAT
variant selects only the single brightest cluster, so it is more restrictive
and cannot test the required permissive direction. Selecting all three
clusters would classify the complete image as foreground and would not provide
a useful causal intervention.

For ordered cluster centers `c0 < c1 < c2`, the current two-cluster foreground
assignment has its relevant intensity boundary at the midpoint between `c0`
and `c1`:

`t_base = c0 + 0.5 * (c1 - c0)`

The unresolved hypothesis is that some valid cell pixels fall between the
dark-cluster center and this baseline boundary.

## Minimum intervention

Add one diagnostic K-means parameter:

`foreground_boundary_relaxation_fraction`

Its unchanged value is `0.0`. The only proposed candidate value is `0.5`.
The candidate boundary is:

`t_candidate = t_base - 0.5 * (t_base - c0)`

which is equivalently:

`t_candidate = c0 + 0.25 * (c1 - c0)`

The candidate raw foreground is the union of the unchanged cluster-membership
foreground and pixels above `t_candidate`. Defining it as a union guarantees
that the intervention is a permissive superset of the existing two-cluster
selection even in a possible intensity tie at the original midpoint.

The value `0.5` is a single, predeclared, field-relative step. It moves halfway
from the existing boundary toward the excluded cluster center while remaining
above that center. It must be identical for both fields and must not be tuned
from either problem crop.

## Fixed controls

The proposed candidate is relative to the saved D061 K area-32 reference. All
other effective inputs remain fixed:

- fields: `Capture 1 + Position 1` and `Capture 1 + Position 2`;
- source channel: C1, selected by the existing Module 5 result;
- preprocessing: identity;
- K-means clusters: 3;
- foreground-cluster count: 2;
- fitting sample, initialization count, algorithm, and random seed: unchanged;
- opening radius: 1;
- closing radius: 3;
- hole filling: enabled;
- minimum object area: **32 pixels, fixed and not varied**;
- connectivity: 2.

Changing cluster count, foreground-cluster count, preprocessing, morphology,
or area in this block would confound the causal question and is excluded.

## Minimum future execution block

If separately authorized, execute exactly one new candidate on each of the two
existing fields: two engine calls total. Do not rerun area 16, 32, or 64 as a
parameter comparison. Use the immutable saved K area-32 labels as the final
reference:

- Position 1 reference:
  `outputs/module7_ofat_review_20260714_kmeans/runs/field_001__variant_003/labels.npy`;
- Position 2 reference:
  `outputs/module7_ofat_review_20260714_kmeans/runs/field_002__variant_003/labels.npy`.

The extension must have a new immutable catalog origin and output directory.
It must not be inserted into D047, registered as a profile, or added to the
D046 review ledger.

## Required causal artifacts

For each candidate call, preserve:

- ordered fitted cluster centers;
- `t_base` and `t_candidate`;
- the unchanged raw cluster-membership foreground mask;
- the relaxed raw foreground mask;
- their exact added-support mask;
- the post-morphology mask before the fixed area operation;
- the final integer labels after the fixed 32-pixel operation;
- exact counts of added and removed pixels at every recorded stage;
- source, prepared-frame, reference-label, and generated-artifact SHA-256
  values.

The final candidate support must be compared read-only against the saved
area-32 reference. Report complete-field changes and changes inside the
unchanged fixed coordinates:

- P2-R1: `x=95:225, y=85:205`;
- P1-R4: `x=250:360, y=510:600`.

Generate unclassified full-field overlays plus a focused causal review sheet
for only these two regions. The sheet should show the saved area-32 reference,
the candidate final contour, and the raw selection-only additions. It must not
classify a cell automatically.

## Interpretation rules

Keep causal contribution separate from final acceptability:

1. **Foreground-selection contribution supported.** Newly selected support is
   identified by the scientific user as belonging to a previously omitted
   P2-R1 cell or to the missing portion of the P1-R4 cell.
2. **Contribution but not sufficient.** The raw selection addition reaches a
   confirmed cell, but the final contour still omits it or remains incomplete.
   This implicates the selection boundary while showing that another fixed
   downstream stage also prevents an acceptable final ROI.
3. **No support at the tested relaxation.** No newly selected support reaches
   the confirmed problem structure. This rejects only the declared 0.5
   relaxation as an explanation; it does not prove that every possible
   intensity-selection rule is irrelevant.
4. **Non-cellular expansion.** New support is present but is not identified as
   part of the target cells. This does not confirm the causal hypothesis and
   may expose a specificity cost.

Any final acceptability decision also requires inspection of both complete
fields for unacceptable bridging or background foreground. A causal recovery
does not by itself approve the candidate or a production profile.

## Minimal implementation boundary before any real run

Implementation, if later requested, should remain within Module 7:

- extend the K-means foreground-selection internals with the validated
  relaxation parameter while preserving exact behavior at `0.0`;
- expose an extension-specific diagnostic trace without changing the stable
  `SegmentationResult` responsibility for ordinary engine callers;
- add a separate immutable one-variant catalog based on K area=32;
- allow the static review package to accept only that exact authorized
  catalog member and save the causal masks listed above;
- add synthetic unit tests for validation, determinism, unchanged behavior at
  `0.0`, monotonic raw support, exact one-factor construction, fixed area=32,
  and rejection of unauthorized variants.

Synthetic tests are implementation verification, not scientific executions.
No real TIFF run should occur until the implementation and the exact two-run
plan receive separate authorization.

## Explicit exclusions

This design does not:

- test minimum area again;
- vary the number of K-means clusters;
- select all clusters as foreground;
- change the segmentation channel or preprocessing;
- tune a value per image or crop;
- test Marker Watershed, Cellpose, Otsu, or P99;
- infer that the two fields are sufficient or representative;
- accept or reject K area=32 finally;
- approve or register `strict`, `medium`, or `permissive`;
- change the global `benchmark_baseline`;
- use or modify D046.
