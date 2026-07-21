# Module 7 D069 local-background real-execution authorization design

## Status and authority boundary

This document supplies the separate authorization design required by D070 for
the D069 implementation. It is a design record only. It does not implement a
real-data package, pass a TIFF-derived frame to the D069 candidate, execute a
segmentation call, generate a review artifact, or authorize any of those
actions.

The boundary has three distinct gates:

1. **Design gate (D071).** This document fixes the only admissible real-review
   plan and its fail-closed controls. Completing this gate grants no execution
   authority.
2. **Implementation-only gate.** A later explicit request may implement the
   package contract and verify it with synthetic arrays only. That block must
   still perform no real TIFF-derived candidate call.
3. **Real-execution gate.** Only a later, explicit scientific-user statement
   that names the D071 plan may authorize the two real candidate calls. The
   implementation-only request, passing tests, availability of the files, or
   this design cannot substitute for that statement.

This separation is required because the current D069 runner intentionally
records `synthetic_verification_only = true`. A real call must not reuse that
provenance as if it described real execution. The implementation-only gate
must add a typed, package-level real-review entry point that records the later
authorization identifier and execution scope while keeping the direct D069
runner synthetic-only and rejecting unrecognized execution modes.

## Implementation status after D072

D072 implements the implementation-only prerequisite without activating the
real gate. The typed boundary is
`src/funes/segmentation_kmeans_local_background_review.py`; its five focused
tests use only small synthetic arrays, synthetic source bytes, temporary saved
references, and temporary publication paths. The direct D069 runner remains
synthetic-only. No real TIFF was read or segmented and the declared D071
destination was not created. The later activation statement in this document
is still required before either real candidate call.

## Exact plan eligible for later authorization

The only plan eligible under this design is:

- selection identifier:
  `module7_kmeans_local_background_real_review_d071`;
- destination:
  `outputs/module7_kmeans_local_background_causal_review_d071/`;
- variant:
  `causal_candidate__foreground_spatial_conditioning__local_background_p20`;
- origin:
  `module7_kmeans_local_background_causal_candidate_20260719`;
- calls: exactly two candidate calls, in the fixed order below;
- comparison references: the saved K-means area-32 labels, read-only;
- review regions: unchanged P1-R4 and P2-R1 coordinates from D062/D068.

| Call | Field | Source | Source SHA-256 | Prepared-frame SHA-256 | Area-32 reference | Reference SHA-256 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Capture 1 + Position 1 | `raw_data/Capture 1 - Position 1_XY1757012095_Z0_T0_C1.tif` | `dd35903c267fb8528136fbadc4e4662bc6527ff6051a5fa1390111fca31307d8` | `b25a71d92617853e53f23e479cb0d0e8c96467f9d2ffd4ab5513814a29fac2d7` | `outputs/module7_ofat_review_20260714_kmeans/runs/field_001__variant_003/labels.npy` | `36ab719aec5b736f56deb1c44f9286b023536ccc906780bad8934f51ae2ba9af` |
| 2 | Capture 1 + Position 2 | `raw_data/Capture 1 - Position 2_XY1757012096_Z0_T0_C1.tif` | `c3eedf9770166c7b73a299df5d6a5f299597f0d504289b07884a3e5b64701238` | `17b8b5261d404ff68516de4c05500e210a61b27e76dc30a42f58cc3831162e1e` | `outputs/module7_ofat_review_20260714_kmeans/runs/field_002__variant_003/labels.npy` | `c4428d4f6f470ce00a9fbeaf57503f850237b8d5b7781b8dba259799b2c97aa3` |

The selected source for both fields is the existing Module 5 C1 result. The
prepared frame is the first temporal frame after Module 6 identity
preprocessing and has shape 600 x 600 with `float64` values. The fixed focused
regions are:

- P1-R4: `x=250:360, y=510:600`;
- P2-R1: `x=95:225, y=85:205`.

The hashes above identify the plan; recording them here does not authorize
reading, preparing, or segmenting the sources in this design block.

## Fixed candidate and controls

The future package must accept only the exact D069 catalog member and must
reject a copied, renamed, or modified variant. The only changed factor relative
to the immutable K area-32 control is:

`foreground_spatial_conditioning: none -> local_background_p20`

Every other control remains fixed:

- identity preprocessing and the existing C1 channel selection;
- three K-means clusters and the two highest-center foreground clusters;
- unchanged evenly spaced fit sampling, `fit_max_pixels = 100000`,
  `n_init = 10`, Lloyd algorithm, and `random_state = 1729`;
- `foreground_boundary_relaxation_fraction = 0.0`;
- opening radius 1, closing radius 3, hole filling enabled;
- minimum object area 32 pixels and connectivity 2;
- local percentile P20 with NumPy `linear` interpolation;
- window side `2 * floor(min(height, width) / 8) + 1`, yielding 151;
- NumPy-style reflected padding without repeating the edge sample; and
- strict negative-offset gating plus union with unchanged raw K-means support.

No value may be selected or adjusted from either complete field or focused
crop. A mismatch is a failed authorization precondition, not permission to
substitute a nearby configuration.

## Implementation-only prerequisite

Before a real-execution authorization can be activated, a Module 7 package
contract must be implemented and reviewed without real execution. Its
synthetic tests must demonstrate at least:

- exact two-input order and exactly one unchanged candidate;
- rejection of extra fields, extra variants, alternate destinations, and
  mismatched source, prepared-frame, or reference hashes;
- rejection of a nonempty final destination;
- a real-review execution scope that cannot be obtained through the direct
  synthetic D069 runner accidentally;
- an engine-call counter that begins at zero, reaches exactly two only on a
  successful complete run, and never retries automatically;
- complete preflight before the first candidate call;
- incomplete-run isolation and publication only after postflight validation;
- preservation of every required trace array, topology record, provenance
  field, and artifact hash; and
- source/reference immutability checks before and after the synthetic package
  exercise.

Those tests may use synthetic arrays and temporary paths only. They cannot use
the two real source TIFFs as implementation fixtures and cannot create the
declared final destination.

## Fail-closed real preflight

After a later explicit execution authorization, all of the following must pass
before the first candidate call:

1. The reviewed package implementation and focused synthetic tests pass.
2. The selection identifier, destination, variant identity, origin, call
   count, field order, effective parameters, and focused regions match this
   document exactly.
3. Both source paths and both saved references exist and match the recorded
   SHA-256 values.
4. Modules 1, 2, 5, and 6 reproduce C1 selection, first-frame identity
   preparation, 600 x 600 shape, `float64` dtype, and both prepared-frame
   hashes.
5. Both reference arrays are nonnegative integer label images with the exact
   prepared-frame shape.
6. The final destination is absent or empty, the staging destination is new,
   and neither earlier OFAT package nor the D064 package is writable through
   the plan.
7. The candidate-call counter is zero and no prior attempt exists under the
   same authorization identifier.

Any mismatch stops the block before segmentation. The package must not repair,
regenerate, or replace a source or reference; choose another source, channel,
field, parameter, or destination; or fall back to another engine.

## Exactly authorized execution behavior

If and only if every preflight condition passes, the later authorization may
permit:

1. one call for Capture 1 + Position 1; then
2. one call for Capture 1 + Position 2.

Each call must use the prepared first frame and its saved area-32 reference in
the table above. The control calculation performed internally by the D069
runner to verify the reference is part of that candidate call; it is not
authority for a separate baseline run. Area 16/32/64 variants, D064, Marker
Watershed, Cellpose, Otsu, P99, or any other candidate must not be rerun.

There is no automatic retry. If either call or any invariant fails, stop. Do
not make a replacement call under the same authorization. Keep an incomplete
attempt outside the final destination with an error record and actual call
count, and do not publish it as a completed review package. Any retry requires
a new explicit authorization after the failure is reviewed.

## Required immutable package

For each successful call, preserve the full D069 trace:

- prepared-frame hash, fit indices, original and ordered centers, selected
  cluster identifiers, seed, package/library versions, and timing as
  operational information only;
- global boundary, field P20, local P20 definition, window/padding rules, the
  complete local-P20 array, and the complete threshold map;
- baseline and candidate raw masks, raw additions, unchanged and candidate
  post-morphology/pre-area masks, control and candidate final labels, and the
  immutable saved reference labels;
- exact raw, post-morphology, and final added/removed counts, with every
  removal remaining an invariant failure;
- the complete raw/final component table with geometric classes; and
- complete-field plus fixed P1-R4/P2-R1 summaries.

The package must also contain:

- an exact `selection.json` including the later authorization identifier and
  verbatim authorization scope;
- machine-readable run and component tables;
- unclassified full-field and focused SVG/PNG review views;
- blank human-observation records that keep de novo recovery, existing-object
  completion, nonspecific additions/expansions, and D051 bridge interpretation
  separate;
- an HTML index; and
- a manifest hashing every generated artifact and listing the immutable source,
  prepared-frame, and reference identities.

Postflight must verify exactly two completed calls, every trace invariant,
every artifact hash, the absence of unplanned files, and unchanged source and
reference hashes before atomically publishing the final destination. Artifact
generation and postflight do not authorize any additional candidate call.

## Human interpretation remains separate

The real package is an evidence package, not a scientific conclusion. Raw
`detached_proposal`, `single_anchor_proposal`, and `multi_anchor_proposal`
classes and final `de_novo_final_candidate`, `existing_object_expansion`,
`unchanged_or_carried_object`, and `bridge_candidate` classes remain geometric.

A later human-review block must explicitly classify wholly omitted-cell
recovery, existing-cell completion, nonspecific support, and D051 bridge/joint
ROI acceptability. The execution package must leave those fields blank. The
two selected examples do not establish sample sufficiency or
representativeness, and real execution does not approve the candidate.

## Required future activation statement

The real-execution gate is activated only by a later scientific-user statement
substantively equivalent to:

> Authorize only the D071 real-review plan
> `module7_kmeans_local_background_real_review_d071` to write
> `outputs/module7_kmeans_local_background_causal_review_d071/`, after every
> preflight passes, with exactly two D069 candidate calls in the fixed order
> Capture 1 + Position 1 then Position 2. No retries, substitutions, additional
> variants, profile action, D046 action, or scientific conclusion are
> authorized.

The statement must be made after the implementation-only package contract has
been reviewed. References to “continue,” “run the test,” D069 alone, this
design alone, or passing preflight/tests are insufficient authority.

## Explicit exclusions

This design does not:

- implement the real package or change the D069 runner;
- read or segment a real TIFF-derived frame;
- generate or reserve the declared output directory;
- authorize either real candidate call or a retry;
- modify raw TIFFs, saved references, prior packages, or D046;
- tune P20, window scale, morphology, area, fit, seed, or another parameter;
- rerun a control/profile/engine comparison;
- classify geometric components biologically;
- assess final acceptability, sample sufficiency, or representativeness;
- approve, reject, or register a profile; or
- change the global `benchmark_baseline`.
