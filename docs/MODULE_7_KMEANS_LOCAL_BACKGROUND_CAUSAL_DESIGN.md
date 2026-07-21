# Module 7 locally background-conditioned K-means causal design

## Status and scope

This document formulates the minimum post-D067 K-means causal mechanism. It is
a design record. At the time of D068, no code was implemented and no synthetic
or real image was segmented. D069 later authorized and records implementation
of this exact candidate and trace with synthetic-array verification only. No
real image was segmented, no output package was generated, and no existing
artifact was modified by that implementation block.

The design asks whether a spatially varying background offset causes the global
K-means foreground rule to omit dim cells or cell peripheries. It does not ask
whether another value on the closed D062-D066 global relaxation axis would be
better.

The immutable diagnostic reference remains K-means
`minimum_object_area_pixels = 32` for `Capture 1 + Position 1/2`. The global
`benchmark_baseline` is unchanged. This design does not register a profile,
use D046, or assess sample sufficiency or representativeness.

## Causal hypothesis

The global K-means fit provides one foreground boundary for the complete
field. A dim cell in a locally darker part of the field can have usable
cell-to-local-background contrast while still falling below that single
absolute boundary. Conversely, applying one lower boundary everywhere admits
support in regions where no local downward adjustment is justified.

The causal hypothesis is therefore:

> Some residual omissions are caused by applying the globally fitted K-means
> boundary without conditioning it on the local background offset. Holding the
> fit and all downstream operations fixed, lowering the boundary only where a
> predeclared local background estimate is below the field background can add
> disconnected cell candidates and missing peripheries without reproducing
> every addition of a global scalar relaxation.

This hypothesis can fail independently for wholly omitted cells, incomplete
existing objects, and specificity. A result in one class must not be used as a
result in another.

## One minimum intervention

Introduce one diagnostic foreground-selection mode:

`foreground_spatial_conditioning = local_background_p20`

The unchanged control mode is:

`foreground_spatial_conditioning = none`

There is exactly one candidate mode and no parameter grid. Both modes use the
same prepared frame `I` and the same fitted three-cluster K-means model. For
ordered fitted centers `c0 < c1 < c2`, preserve the existing global boundary:

`t_base = c0 + 0.5 * (c1 - c0)`

Let `b_global` be the 20th percentile of the complete prepared frame, using
linear percentile interpolation. For every pixel `x`, let `b_local(x)` be the
20th percentile with the same interpolation in a square window centered on
`x`, using NumPy-style reflection that does not repeat the edge sample. The
window side is determined once from the image shape:

`w = 2 * floor(min(height, width) / 8) + 1`

For the current 600 x 600 fields this gives `w = 151`. The field-relative rule
is identical for both fields, is not selected from P1-R4 or P2-R1, and carries
no claim that 151 pixels is a production or biologically optimal scale.

Define the spatially conditioned threshold map as:

`t_local(x) = t_base + min(0, b_local(x) - b_global)`

Thus the boundary is unchanged where the local background is equal to or above
the field P20 and is lowered by the measured offset only in locally darker
regions. There is no fitted amplitude, field-specific value, crop-specific
value, or additional scalar relaxation fraction.

Let `B_raw` be the unchanged raw foreground selected by membership in the two
K-means clusters with the highest centers. The candidate raw foreground is:

`L_raw = B_raw union {x : b_local(x) < b_global AND I(x) > t_local(x)}`

The explicit `b_local(x) < b_global` gate prevents threshold/tie behavior from
adding support where no negative local offset exists. The union preserves all
unchanged raw support. The fixed morphology and 32-pixel area operation are
then applied once to `L_raw`. The candidate must not enable or reuse D062's
`foreground_boundary_relaxation_fraction = 0.5`; that parameter remains at
its unchanged value `0.0`.

## Why this is outside the closed D062-D066 branch

D062-D066 varies one field-wide scalar threshold and therefore produces a
nested sequence of global supports. This candidate uses a threshold map: one
region can retain `t_base` while another uses a lower boundary determined by
its local P20 offset. It can therefore propose intensity support below the
D064 boundary in one dark region without necessarily admitting the D064
support in an unrelated region.

The candidate is still permissive relative to the unchanged K area-32 raw
selection, but it is not another point on the closed scalar relaxation axis.
The causal factor is the declared spatial conditioning mode, not the amount of
global relaxation.

## Fixed controls

Any later implementation or execution must hold the following inputs fixed:

- diagnostic fields: `Capture 1 + Position 1` and
  `Capture 1 + Position 2`, without a coverage claim;
- source channel: the existing Module 5 C1 selection;
- Module 6 preprocessing: identity;
- K-means clusters: 3;
- foreground clusters: the two highest-center clusters for `B_raw`;
- fit sample, initialization count, algorithm, and random seed: unchanged;
- D062 global relaxation fraction: `0.0`;
- opening radius: 1;
- closing radius: 3;
- hole filling: enabled;
- minimum object area: 32 pixels;
- connectivity: 2;
- local statistic: P20;
- local-window rule: the single field-relative formula above;
- edge handling: reflection, fixed and recorded.

Changing the channel, preprocessing, cluster count, foreground-cluster count,
local percentile, window rule, morphology, area, seed, or fitting behavior in
the same block would confound this causal question.

## Required distinction between recovery and expansion

Spatial overlap is an audit relation, not a biological classifier. The design
must preserve the following distinctions at both proposal and final-mask
stages.

First label the connected components of `L_raw AND NOT B_raw` with connectivity
2. For each raw added-support component, record how many unchanged `B_raw`
components it touches under connectivity 2:

- `detached_proposal`: touches none;
- `single_anchor_proposal`: touches exactly one;
- `multi_anchor_proposal`: touches two or more.

Then compare every candidate final label against the immutable saved K
area-32 final labels:

- `de_novo_final_candidate`: overlaps no saved label;
- `existing_object_expansion`: overlaps exactly one saved label and contains
  candidate support outside that saved label;
- `unchanged_or_carried_object`: overlaps exactly one saved label and adds no
  final support;
- `bridge_candidate`: overlaps two or more saved labels.

A `de_novo_final_candidate` is only geometrically compatible with recovery of
a wholly omitted cell. It must not be called a cell automatically. Human
review must classify it as `confirmed_wholly_omitted_cell`,
`isolated_nonspecific_addition`, or `indeterminate`.

Likewise, an `existing_object_expansion` must be classified by human review as
`confirmed_cell_completion`, `nonspecific_expansion`, or `indeterminate`.
A `bridge_candidate` must be reviewed as `acceptable_joint_roi_under_D051`,
`unacceptable_bridge`, or `indeterminate`; overlap alone cannot decide the
biological interpretation.

These separate tracks prevent an increase in foreground pixels or ROI count
from being reported as omitted-cell recovery.

## Required causal trace and artifacts

For each future candidate call, preserve:

- source and prepared-frame identity plus SHA-256;
- K-means fit sample indices, seed, ordered and original cluster centers, and
  selected cluster identifiers;
- `t_base`, `b_global`, the exact local-window rule, percentile definition,
  padding rule, and library versions;
- the complete `b_local` and `t_local` arrays;
- `B_raw`, `L_raw`, and their exact added-support mask;
- unchanged and candidate post-morphology pre-area masks;
- candidate final labels and the immutable saved-reference labels;
- exact added and removed pixel counts at raw, post-morphology, and final
  stages, with any removal treated as an invariant failure because the
  candidate is defined as a raw union;
- a component table with stage, component identifier, area, bounding box,
  touched raw anchors, overlapped saved final labels, and the geometric class
  above;
- complete-field and unchanged P1-R4/P2-R1 summaries, without using the crops
  to choose any parameter;
- unclassified full-field and focused review views;
- blank, separately writable human-observation records; and
- a manifest hashing every generated artifact.

The immutable K area-32 labels remain the final comparison reference. A later
package must verify their hashes and the source hashes before any call. It must
not write into the D064 package or the D046 ledger.

## Causal interpretation

The future review must make three independent statements:

1. **Wholly omitted-cell contribution.** Supported only when the scientific
   reviewer identifies at least one `de_novo_final_candidate` as a previously
   wholly omitted cell. A detached component alone is insufficient.
2. **Existing-object completion contribution.** Supported only when added
   support in an `existing_object_expansion` is identified as missing cellular
   body or periphery. It says nothing about wholly omitted cells.
3. **Specificity and topology cost.** Record isolated nonspecific additions,
   nonspecific expansions, and bridge candidates separately. D051 governs
   whether a reviewed multi-object result may remain a joint ROI.

Possible outcomes include support for only one recovery class, support for
both with unacceptable specificity, no support for either, or an indeterminate
result. None of these outcomes by itself establishes final acceptability or a
production profile.

## Minimum future implementation and execution boundaries

If implementation is later requested, keep it inside Module 7 and verify it on
synthetic arrays only. The minimum implementation would add the single mode,
an immutable local-background trace, the component-overlap audit table, and
tests for exact unchanged behavior in `none` mode, determinism, the window
formula, local-threshold arithmetic, raw-superset preservation, topology
classification, fixed controls, and rejection of unauthorized settings.

Synthetic verification would not authorize real TIFF segmentation. A later
real-data block would require separate authorization and would contain exactly
one candidate call for each of the same two fields, two calls total, using the
saved K area-32 labels read-only. It would not rerun the global baseline, D064,
area variants, Marker Watershed, or any profile comparison.

## Explicit exclusions

This design does not:

- implement or execute segmentation;
- continue or reopen the monotonic global-boundary relaxation branch;
- use `foreground_boundary_relaxation_fraction = 0.5` in the candidate;
- tune a parameter from a field or focused crop;
- change the selected channel or identity preprocessing;
- change K-means fitting, morphology, connectivity, or area filtering;
- test another engine;
- infer that a detached or zero-overlap component is a cell;
- infer sample sufficiency or representativeness;
- approve, reject, or register a production profile;
- change the global `benchmark_baseline`; or
- use or modify D046.
