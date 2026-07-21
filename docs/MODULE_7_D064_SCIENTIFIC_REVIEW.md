# Module 7 D064 scientific review

## Scope

This record preserves the scientific user's 2026-07-19 confirmation of the
visual review of the immutable D064 package at
`outputs/module7_kmeans_foreground_causal_review_20260718/`.

The review used only the saved full-field previews, focused P1-R4/P2-R1
sheets, causal traces, and label arrays. No TIFF was segmented, no package
artifact was modified, and no segmentation parameter was executed or tuned.

## Confirmed focused classifications

### P1-R4

- The relaxed foreground selection reaches visible cellular signal that was
  outside the saved K area-32 reference and expands the border-intersecting
  objects.
- A small isolated added patch lacks a clear cellular structure in the focused
  view, exposing a localized specificity cost.
- Foreground-selection contribution is supported, but the candidate is not
  accepted finally.

### P2-R1

- The relaxed selection recovers several previously omitted cellular
  peripheries or bodies and expands prior bright-core masks.
- Several dim visible bodies remain without a final ROI.
- The confirmed classification is contribution but not sufficient, and the
  candidate is not accepted finally.

## Complete-field review

The saved-label comparison is read-only and does not create a new
segmentation. Position 1 contains 27 candidate labels with no overlap to a
saved reference label and three candidate labels that connect support from two
saved reference labels. Position 2 contains 31 candidate labels with no
overlap to a saved reference label and five candidate labels that connect
multiple saved reference labels; one of those connects three saved labels.

The complete-field previews do not show a field-wide background carpet, but
they do show localized nonspecific expansion, possible bridging, and many dim
bodies that still lack contours. The overlap counts identify possible bridge
events; they do not by themselves determine whether a joint ROI is
biologically unacceptable under D051.

## Decision boundary

The D064 relaxation confirms that the tested K-means foreground boundary
contributes to the residual omissions. The `0.5` relaxation is not sufficient
for acceptable segmentation on these two reviewed fields and introduces a
specificity/bridging risk. It is therefore not approved as a production
profile or global baseline.

This conclusion is limited to these two fields. It does not establish sample
sufficiency or representativeness, reject every possible K-means foreground
rule, authorize another execution, approve or register a profile, change the
global `benchmark_baseline`, or use D046.

The manifest-listed `causal_review_observations.csv` remains blank because it
is part of the immutable D064 package. This document and D065 preserve the
later human confirmation without invalidating the package hashes.
