# Module 24 auditable ROI mask revision design

## Outcome

Module 24 must be completed before preparing a concrete Module 23 activation
plan for the intended corrected-mask workflow.

D101 is operationally complete, but its version-1 activation plan binds the
existing Modules 5-15 configuration and D090 review state only. It has no
input for a manually revised ROI mask. Preparing a concrete plan now would
therefore bind an automatic-mask-only run even though D061 and D074 preserve
known whole-cell coverage limitations in the provisional segmentation.

This is a sequencing decision, not a claim that D101 is invalid or that an
evidence-only automatic-mask run is technically impossible. Module 23 remains
validated and inactive. No real-data access or execution is authorized here.

## Module boundary

Module 24 is an independent, optional mask-revision boundary between Module 8
geometric filtering and the quantitative consumers in Modules 10-13:

```text
Module 7 segmentation
  -> Module 8 automatic geometry/filtering
  -> Module 24 optional finalized ROI revision
  -> Module 10 background
  -> Module 11 intensity QC
  -> Module 12 temporal intensity
  -> Module 13 FRET calculation
```

The same finalized two-dimensional label mask must be used for every temporal
frame in both C0 and C1. Background and every downstream measurement must be
recomputed from that finalized mask; results from an automatic mask and a
revised mask must never be mixed.

Module 9 remains the existing read-only inspection and D046 review-coverage
interface. Module 24 must not turn an edit into a D046 inspection, global
approval, profile approval, or scientific acceptability conclusion.

## First implementation-only block

The first Module 24 implementation must be backend-only and use synthetic
arrays and temporary paths. It must define and validate immutable, versioned
contracts without building a browser editor or opening real images.

The minimum contracts are:

- an exact source identity containing Experiment, Capture, Position, image
  shape, Module 7 source-label SHA-256, and Module 8 filtering SHA-256;
- an ordered revision containing one or more explicit edit operations, editor
  identity, finalization time, non-empty reason per operation, parent revision
  hash when applicable, and a domain-separated canonical SHA-256;
- an immutable result retaining the exact original Module 7 and Module 8
  objects, the revised label image, recomputed geometric audit, operation
  trace, input/output hashes, and finalization state;
- a strict JSON persistence format that uses only known fields and validates
  the complete revision and mask on load.

Only a finalized revision may enter quantitative analysis. Draft persistence
and interactive tooling are later delivery blocks.

## Initial edit semantics

The backend must support the smallest operation set that can correct the known
failure modes without silently changing ROI identity:

- delete one currently retained ROI label;
- replace the pixel support of one currently retained ROI while preserving its
  label;
- add one omitted ROI using a fresh label greater than every label in the
  original Module 7/8 masks and every earlier revision;
- restore one Module 8-rejected original label explicitly, preserving its
  original label and recording that restoration.

Existing labels must never be renumbered. Deleted labels must never be reused.
Merges and splits are represented explicitly as deletions plus additions in
the first version; the operation trace must preserve the involved labels.

Every operation must be deterministic and sufficient to reconstruct the exact
output mask from the exact input mask. Reject out-of-bounds pixels, empty
supports, overlaps, duplicate labels, unknown labels, reused labels, shape
changes, negative values, values outside `int32`, stale source hashes, and
no-op revisions. Raw TIFFs and auxiliary files remain read-only.

## Geometry and downstream integration

After applying the revision, Module 8 geometry must be recalculated using the
same explicit `RoiGeometryFilterConfig`. The revision result must distinguish:

- the original automatic Module 8 result;
- the complete edited label image before geometric filtering;
- the final measurement label image after the explicit geometry policy; and
- any edited ROI rejected or flagged by that policy.

The future position runner must accept either no revision or exactly one
finalized revision matching the position and automatic-mask hashes. When a
revision is supplied, Modules 10-13 consume only its final measurement mask.
The runner result and Module 21 package must retain both automatic and revised
provenance. Export must identify the mask source (`automatic` or
`manual_revision`) and revision hash for every affected position.

No automatic fallback is allowed if a supplied revision is stale or invalid.
The run must fail before background estimation.

## Relationship to Module 23

D101 and its version-1 plan remain unchanged. A later, separately reviewed
Module 23 schema/version extension is required before a concrete activation
plan may use revised masks. That extension must bind, for every position, the
explicit absence of a revision or the exact finalized Module 24 revision hash
and artifact path. Preflight must validate those bindings before the D099 call,
and postflight must prove that the same revisions reached the persisted
analysis and workbook provenance.

Only after the Module 24 backend, its pipeline integration, persistence, and
the Module 23 binding extension are synthetically validated should a concrete
real activation plan be prepared. The separate exact-ID/SHA-256 authorization
required by D100/D101 remains mandatory afterward.

## Acceptance criteria for the implementation-only block

- Synthetic tests cover add, delete, replace, restore, deterministic replay,
  stable labels, monotonic new labels, geometry recomputation, and immutable
  provenance.
- Failure tests cover stale hashes, wrong position/shape, overlap, invalid or
  reused labels, empty/no-op edits, tampered JSON, and unfinalized revisions.
- Tests prove the original segmentation and Module 8 masks remain unchanged.
- Tests prove Module 9/D046 inspection and approval APIs are never called.
- No TIFF under `raw_data/` is listed, read, hashed, segmented, or analyzed.
- No GUI, concrete Module 23 plan, activation ID, real execution authority,
  scientific profile approval, or production dependency is added.

## Deferred blocks

- Interactive brush/polygon ergonomics, undo/redo, temporal navigation, and
  browser-local drafts.
- A human-facing finalization workflow for one revision artifact.
- Revision-chain and standalone artifact-path consumption.
- Module 17/14 export presentation of mask source and revision hash. D108
  completes in-memory propagation through Module 22 and Module 21 v2 package
  publication without changing that presentation boundary.
- The versioned Module 23 revision binding.
- A concrete real-data plan and its separate activation authorization.

These blocks must not be combined merely because they share the ROI concept.
