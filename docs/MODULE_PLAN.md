# Module Plan

Status values:

- `PENDING`
- `IN DISCUSSION`
- `READY`
- `IN PROGRESS`
- `IMPLEMENTED`
- `VALIDATED`
- `DEFERRED`

Work on one module per session unless two modules are inseparable and the user explicitly agrees.

## Module 0 — Repository scaffold and shared contracts

**Status:** VALIDATED

**Responsibility**

- Create a minimal package layout.
- Define shared typed data contracts without implementing scientific behavior.
- Establish configuration, testing, and documentation conventions.
- Avoid premature dependencies.

**Suggested outputs**

- package skeleton;
- test skeleton;
- shared identifiers and result/status types;
- no TIFF reading or segmentation yet.

**Acceptance criteria**

- Package imports.
- Tests run.
- Shared models are small and documented.
- No later-module behavior is implemented.

---

## Module 1 — File discovery and filename parsing

**Status:** VALIDATED

**Responsibility**

- Discover `.tif` and `.tiff`.
- Parse Capture, Position, XY, Z token, T token, Channel.
- Preserve original path and filename.
- Identify malformed or unrecognized files.
- Do not open image pixels.

**Acceptance criteria**

- Correctly parses representative filenames.
- Handles spaces and case safely where reasonable.
- Reports duplicates and malformed names.
- Unit tests cover valid and invalid cases.

---

## Module 2 — TIFF reader and pair validation

**Status:** VALIDATED

**Responsibility**

- Open TIFFs.
- Standardize internal data as ordered temporal frames.
- Preserve raw TIFF metadata.
- Validate C0/C1 dimensions and frame counts.
- Do not perform segmentation.

**Validated behavior**

- Real SlideBook TIFFs in `raw_data/` were inspected on 2026-07-13.
- Each inspected file is one `IYX` series with two ordered IFD pages and shape
  `(2, 600, 600)` using `uint16` grayscale pixels.
- The series first axis matches TIFF IFD/page order exactly and is treated as
  temporal frames under D003.
- Both inspected C0/C1 pairs match in frame count, dimensions, dtype, axes,
  page numbering, and structural acquisition metadata.
- TIFF tags are preserved for every page as well as through the existing
  first-page convenience mapping.
- The detailed inspection record is `docs/MODULE_2_REAL_DATA_VALIDATION.md`.

---

## Module 3 — Auxiliary metadata reader

**Status:** VALIDATED

**Responsibility**

- Discover associated `.txt` or similar files.
- Preserve raw text.
- Parse key/value metadata when safe.
- Avoid losing unrecognized lines.

**Implemented behavior**

- Discovers `.txt` and `.log` files recursively, case-insensitively.
- Reads text using a small configured encoding fallback list.
- Preserves raw text, source provenance, parsed key/value entries, duplicate keys, and unparsed non-empty lines.
- Structures recognized SlideBook log headers for downstream audit/export:
  export time, capture time, Z-plane count, time-point count, channel count,
  microns per pixel, Z-step size, and the average timelapse interval as reported.
- Structures each SlideBook table row with IFD, X/Y/Z positions, elapsed time,
  channel name, TIFF filename, source line number, and original row text.
- Emits a structured warning when a log declares more than two channels because
  the current analysis hierarchy supports only C0/C1; all channel metadata and
  rows remain preserved.
- Associates the inspected SlideBook `.log` family to exactly one C0/C1 TIFF
  pair using the explicit tab-separated `TIFF File Name` column.
- Requires both referenced TIFFs to be discovered beside the log and to share
  the same parsed Capture, Position, XY, Z, and T identity.
- Leaves unrecognized auxiliary formats unassociated and reports recognized
  but incomplete, missing, ambiguous, or mixed-pair log references as
  structured errors rather than guessing from the log filename.
- Keeps pair association in the Module 3 result and does not assign experiment
  labels; downstream propagation is defined separately by D038.

**Validation**

- Both real SlideBook logs in `raw_data/` associate to their intended C0/C1
  pairs without issues.
- The detailed inspection record is `docs/MODULE_3_REAL_DATA_VALIDATION.md`.

---

## Module 4 — Experiment assignment

**Status:** VALIDATED

**Responsibility**

- Add an `Experiment` label above Capture.
- Support a simple mapping/configuration first.
- Detect overlapping or missing assignments.

**Implemented behavior**

- Assigns validated TIFF pairs to experiments using explicit rules with one or
  more Capture labels and optional Position labels.
- Reports missing assignments and overlapping assignment rules as structured
  errors without silently choosing a label.
- Preserves auxiliary metadata files on the assignment result for downstream
  audit trails, but does not infer assignments from text metadata.
- Accepts Module 3 pair associations explicitly, matches them to the validated
  C0/C1 source paths, and carries each verified association on the assigned
  `TiffPair` through the Experiment > Capture > Position hierarchy.

---

## Module 5 — Segmentation-channel selection

**Status:** VALIDATED

**Responsibility**

- Compare first-frame C0/C1 signal robustly.
- Select the more suitable segmentation channel.
- Avoid using single-pixel maxima.
- Preserve metric values and selected channel.
- Permit future manual override.

**Implemented behavior**

- Calculates first-frame C0 and C1 robust contrast as configurable high
  percentile minus configurable background percentile.
- Selects the channel with the stronger robust contrast, without using a
  single-pixel maximum as the score.
- Preserves per-channel metrics, selected channel, method name, and structured
  warnings for low contrast or close scores.
- Supports an explicit manual channel override while still preserving computed
  metrics.

---

## Module 6 — Preliminary background/preprocessing interface

**Status:** VALIDATED

**Responsibility**

- Define replaceable background/preprocessing strategy used for segmentation.
- Keep it separate from quantitative background correction.

**Implemented behavior**

- Defines a replaceable segmentation preprocessing strategy interface.
- Provides an identity preprocessor that preserves pixel values while converting
  the frame to `float64` for downstream segmentation engines.
- Provides a configurable percentile-background subtraction preprocessor for
  preliminary segmentation-only use.
- Preserves method names, parameters, preliminary background estimates, issues,
  and caller-provided context for audit trails.
- Rejects non-2D, empty, or non-finite segmentation input frames.

**Pending scientific decision**

Choose the preferred preprocessing estimator and parameters for representative
images before relying on a production segmentation profile.

---

## Module 7 — Segmentation engine

**Status:** VALIDATED

**Responsibility**

- Segment first frame into labeled cell ROIs.
- Encapsulate Cellpose or another implementation behind an interface.
- Preserve engine name, version, model, and parameters.

**Implemented behavior**

- Keeps the stable replaceable engine interface accepting only a prepared,
  non-empty 2D first temporal frame. Its stable `SegmentationResult` output
  contains a read-only `int32` label image with the same spatial shape, zero as
  background, consecutive positive labels `1..roi_count`, engine/profile and
  parameter provenance, and structured issues. Module 8 consumes
  `label_image` directly; later modules reuse those same fixed label supports.
- Registers five typed methods in the confirmed presentation order:
  K-means + morphology, Cellpose CP-SAM, reproducible marker watershed,
  global Otsu + morphology, and P99 + connected components as an explicit
  control/fallback.
- Uses `method=kmeans` and `profile=provisional_working_kmeans_area32` as the
  configurable global working default. This profile copies the K-means
  `benchmark_baseline` parameters except for
  `minimum_object_area_pixels = 32`. It never attempts to infer a better
  algorithm or tune parameters per field.
- Registers one auditable `benchmark_baseline` profile per method using the
  fixed 2026-07-13 benchmark parameters. These profiles are diagnostic
  baselines, not `medium` presets and not accuracy claims.
- Registers the area-32 K-means choice separately as a provisional working
  profile, not as a universal-accuracy, sample-sufficiency, or complete-cell-
  coverage claim. Its typed catalog record preserves the known limitations:
  faint cells may be omitted, some cells may be covered only partially, and
  touching cells may remain combined in one ROI.
- Resolves an optional override scoped exactly to `Capture + Position` without
  changing any other field. Every configured result preserves the effective
  method/profile, the global method/profile, whether an override was applied,
  and the override field identity.
- Provides an immutable backend review ledger for explicit representative-field
  inspections and explicit approval of the current global method/profile. The
  approval record snapshots every inspection already present, including each
  exact method/profile and selection source; it imposes no automatic or minimum
  sample size.
- Resolves every field to one primary review status with precedence
  explicit override > manually reviewed > global policy accepted > unreviewed,
  while preserving manual inspection as an independent fact for overridden
  fields. A field covered only by global approval is never labeled manually
  reviewed.
- Carries review status, inspection provenance, approval identifier, approved
  global method/profile, and the pre-approval inspected-field snapshot into
  configured engine provenance. Rejects stale approvals, stale inspections,
  duplicate field inspections, mismatched review/execution configurations, and
  internally incoherent status records with actionable errors.
- Executes deterministic K-means, Otsu, marker-watershed, and P99 engines. The
  first three classical baselines use explicit production dependencies on
  SciPy, scikit-image, and scikit-learn so their operations match the reviewed
  benchmark rather than unrecorded approximations.
- Keeps the existing percentile-threshold engine compatible for explicit P99
  selection and direct custom use; it is no longer the configurable default.
- Provides a lazy Cellpose CP-SAM adapter through the optional `cellpose`
  dependency extra. Missing dependencies, model, or weights raise an actionable
  blocked-engine error and never trigger a fallback.
- Preserves all effective parameters, postprocessing, seeds, engine/model
  identity, installed package versions, selection provenance, issues, and
  caller context. Cellpose records the explicit warning that CP-SAM took about
  46–55 minutes per 600×600 field on CPU in the benchmark and requires about
  1.15 GB of weights.
- Reports a structured warning when segmentation produces no foreground ROIs.

**D074 validation**

- 37 focused Module 7 tests and the complete 138-test suite pass.
- Validation used synthetic arrays and temporary synthetic TIFF fixtures only;
  no TIFF under `raw_data/` was read or rerun, no parameter search was
  performed, and no D071 artifact was modified.

**Implemented parameter-benchmark infrastructure (not registered profiles)**

Use a small one-factor-at-a-time grid around `benchmark_baseline`, not a full
Cartesian search and not per-image tuning. The initial interpretable candidates
are:

- K-means: foreground-cluster count `1 / 2 baseline`, minimum object area
  `32 / 64 / 128`, opening radius `0 / 1 / 2`, and closing radius `1 / 3 / 5`.
- Cellpose CP-SAM: cell-probability threshold `-1 / 0 / 1`, minimum object area
  `8 / 15 / 30`, and maximum-size fraction `0.2 / 0.4 / 0.6`. Hold flow
  threshold at `0.4` initially because it is a flow-consistency acceptance
  control rather than a simple monotonic foreground selector.
- Marker watershed: Otsu foreground-threshold scale `0.9 / 1.0 / 1.1`, minimum
  object area `32 / 64 / 128`, opening radius `0 / 1 / 2`, and marker minimum
  distance `8 / 12 / 16` (the last controls splitting more than foreground).
- Global Otsu: threshold scale `0.9 / 1.0 / 1.1`, minimum object area
  `32 / 64 / 128`, opening radius `0 / 1 / 2`, and closing radius `1 / 3 / 5`.
- P99 control: threshold percentile `98 / 99 / 99.5`; connectivity remains a
  component-merging choice rather than a foreground-selectivity axis.

Only the baseline and one changed value should be compared in each initial
variant. `strict`, `medium`, and `permissive` remain unregistered until this
parameter benchmark and separate scientific review are complete. Those future
names will describe foreground selectivity, not accuracy.

- Materializes 36 immutable variants in the confirmed method order: 8 K-means,
  7 Cellpose CP-SAM, 9 marker-watershed, 9 global-Otsu, and 3 P99 runs,
  including exactly one unchanged baseline reference per method.
- Verifies that every non-baseline variant changes exactly one effective
  parameter. Holds Cellpose flow threshold and P99 connectivity fixed as
  planned.
- Creates candidate engines from ephemeral, explicitly identified parameter
  sets without adding candidate names to the production profile registry.
- Runs exactly one caller-selected variant on one identified Capture + Position
  prepared first frame. It never runs Cellpose implicitly, substitutes a
  blocked engine, ranks candidates, chooses a winner, or approves a profile.
- Reports only descriptive mask geometry: ROI count, foreground pixel count and
  fraction, and minimum/median/maximum ROI area. These values are not accuracy
  metrics and cannot replace visual or scientific review.
- Adds the planned Otsu and watershed threshold-scale controls with a baseline
  value of `1.0`, preserving both base Otsu and effective scaled thresholds in
  engine provenance.
- Keeps the D046 immutable inspection/global-approval backend and its contracts
  unchanged; benchmark runs are separate from review-ledger state.

The infrastructure is implemented and unit-tested. The first explicit static
review package has also been generated. Per-run scientific visual observations
are recorded without a field-set conclusion or profile decision.

**Implemented explicit visual-review artifact block**

- Accepts only caller-identified `Capture + Position` fields and unchanged D047
  variants, prepares the selected first frames through Modules 1, 2, 5, and 6,
  and executes exactly the selected field/variant product.
- Writes exact NPY labels, numbered unclassified SVG overlays, PNG previews,
  descriptive run CSV, a human-observation CSV, explicit selection provenance,
  an HTML index, and a SHA-256 manifest. The first package now preserves visual
  notes for all 16 runs while leaving reviewer and review-time provenance blank.
- Records per-run segmentation-engine duration and the package total strictly
  as operational timing, explicitly excluding it from scientific comparison,
  ranking, classification, selection, or approval.
- Records that sample sufficiency was not assessed, no ranking/classification
  or profile approval occurred, and the D046 review ledger was not used.
- The first explicit package selects `Capture 1 + Position 1/2` and the eight
  K-means D047 variants, producing 16 runs in
  `outputs/module7_ofat_review_20260714_kmeans/`. This selection does not assert
  that the field set is sufficient and does not evaluate other methods. Its
  observations do not classify variants or approve/register profiles.
- The validation record is
  `docs/MODULE_7_OFAT_VISUAL_REVIEW_ARTIFACTS.md`.

**Completed next explicit visual-review artifact block**

- D049 withdrew Cellpose CP-SAM as the next complete block. At the close of
  that block, Cellpose was deferred until a separate session explicitly ran
  exactly one timed test and defined an acceptable operational limit. No
  Cellpose dependency was installed and no Cellpose candidate was executed in
  the D049 block; D050 below records the later separate timed test.
- Explicitly selects `Capture 1 + Position 1/2` and all nine unchanged Marker
  Watershed D047 variants, in D047 order, for 18 runs.
- Generates the complete D048 package in
  `outputs/module7_ofat_review_20260714_marker_watershed/`: exact NPY labels,
  numbered unclassified SVG overlays, PNG previews, descriptive CSV with
  operational-only engine timings, 18 blank human-observation rows, selection
  and preparation provenance, an HTML index, and a SHA-256 manifest.
- Records explicitly that sample sufficiency was not assessed, variants were
  not ranked or classified, no profile was approved or registered, the global
  K-means baseline remains unchanged, and D046 was neither used nor modified.
- The block-specific record is
  `docs/MODULE_7_OFAT_MARKER_WATERSHED_VISUAL_REVIEW_ARTIFACTS.md`.
- The selection record is
  `docs/MODULE_7_OFAT_NEXT_VISUAL_REVIEW_SELECTION.md`.

**Completed K-means / Marker Watershed evidence synthesis**

- Reviews the existing full-field previews for all eight K-means and all nine
  Marker Watershed variants and compares the existing NPY masks read-only.
- Keeps visible facts, confirmed human fixed-crop observations, and exact mask
  comparisons separate. It records locally identical masks, support changes,
  label-only partitions, omissions, unions, artefacts, and border objects.
- Corrects P2-R4: K baseline and K `minimum_object_area_pixels=32` have the
  same binary mask inside that crop, although the complete Position 2 masks
  differ because the latter adds 21 small objects and label numbering changes.
- Applies D051 as the interpretation boundary for reliable touching-cell
  division and D052 as the current comparison scope. It does not infer field
  sufficiency or representativeness, rank candidates, choose a winner, approve
  or register a profile, change the global baseline, or use D046.
- The record is
  `docs/MODULE_7_KMEANS_MARKER_WATERSHED_VISUAL_SYNTHESIS.md`. The original
  OFAT packages remain unchanged; no new images or segmentation runs were
  produced.
- D053 confirms that dim silhouettes without contours are not mandatory ROI by
  appearance alone. D054 confirms that the small area-32 components added in
  these two reviewed fields are cells whose retention is desirable. These
  field-limited observations do not establish sufficiency or
  representativeness and do not select a variant.
- D055 records both pure Marker Watershed `distance=8` splits as doubtful; D051
  therefore keeps each as one joint ROI. D056 records that many valid cells
  remain outside the identical Marker Watershed baseline / distance-8 binary
  supports in both reviewed fields.
- A second read-only audit compares all 17 existing variants against the saved
  area-32 component supports confirmed as cells by D054. K `area=32` is the
  only existing mask that covers every such support from both method families;
  it nevertheless has human-confirmed omissions in P2-R1 and was not accepted
  in P1-R4. Its possible advance, or the alternative conclusion that the grid
  contains no acceptable variant for these examples, remains a human decision.
- The saved masks attribute some omissions exactly to the 64-pixel area filter
  and some Marker Watershed omissions to foreground thresholding. Existing
  opening variants recover almost none of the confirmed supports, while marker
  distance changes no support. D057 advances only K area `32` to a final human
  acceptability comparison without approving it. D058 subsequently authorized
  the proposed K area `16`, MW area `16`, and MW threshold scale `0.8` extension
  on the same two fields.

**Completed minimum causal OFAT extension**

- Keeps the original 36 D047 variants unchanged and adds a separate immutable
  three-variant extension catalog with origin
  `module7_minimum_ofat_extension_20260718`; none is a registered profile.
- Executes exactly six authorized runs and writes a new D048-style package to
  `outputs/module7_ofat_minimum_extension_20260718/`, preserving exact labels,
  unclassified SVG/PNG views, selection provenance, operational timings, blank
  human observations, and SHA-256 hashes.
- K area `16` is an exact superset of K area `32`, adding 144 / 179 pixels in
  7 / 7 components of 16-31 pixels. MW area `16` is an exact superset of MW
  area `32`, adding 120 / 138 pixels in 6 / 6 components of 16-30 pixels.
- MW threshold `0.8` is an exact superset of threshold `0.9`, adding 680 / 950
  pixels and 6 / 7 wholly new labels, but it still covers none of the 12 / 21
  K area-32 confirmed reference components.
- None of the three variants adds any support in P2-R1, where K area `32`
  already had human-confirmed omitted cells. K area `16` also adds no support
  in P1-R4, where K area `32` was not accepted. Thus the extension does not
  displace D057 on confirmed evidence. D059 confirms that all 7 / 7 K and 6 / 6
  MW components newly added by area `16` are cells in these fields. D060 still
  excludes all three extension variants from the final comparison, which
  contains only K area `32`.

**Completed final human acceptability evaluation of K area 32**

- Reviews only the two existing K-means
  `minimum_object_area_pixels = 32` previews and the confirmed evidence already
  recorded in the synthesis and minimum-extension package. No segmentation or
  new image generation was performed.
- D061 records the human outcome that K area `32` is not yet acceptable for
  these two examples because many cells are excluded and requires another
  causal extension before acceptance or rejection.
- Keeps the evidence classes separate: complete saved reference-support
  coverage; wholly omitted cells in P2-R1; unaccepted complete-cell coverage in
  P1-R4; no confirmed artefact classification for the area-32 additions; and
  joint ROIs acceptable under D051 when a reliable split is unavailable.
- The 64-to-32-pixel change confirms that minimum-area filtering caused a
  subset of omissions, recovering 12 / 21 cellular components. The 32-to-16
  extension adds no support in P2-R1 and does not change P1-R4, so the key
  residual limitations are not attributable to the tested minimum-area cutoff.
  Residual foreground/intensity selection remains a causal hypothesis rather
  than a confirmed cause.
- Does not authorize another run, infer sufficiency or representativeness,
  approve or register a profile, change the global baseline, or use or modify
  D046.

**Executed and reviewed minimum K-means foreground causal extension**

- D062 defines and D063 implements one new diagnostic factor,
  `foreground_boundary_relaxation_fraction`, around the intensity boundary
  between the excluded darkest K-means center and the lowest included center.
- The only proposed value is `0.5`, which moves the boundary from the midpoint
  to one quarter of that center-to-center interval while retaining the
  unchanged two-cluster foreground as a guaranteed subset.
- All other settings remain fixed to the D061 K area-32 candidate, including
  `minimum_object_area_pixels = 32`; area is not tested again.
- The implementation adds a separate immutable one-candidate catalog based on
  K area `32`; it is absent from both prior OFAT catalogs and from the profile
  registry. The ordinary K-means path retains exact selection behavior at
  relaxation `0.0`.
- D064 records the separately authorized real-data block. It executed exactly
  two new engine calls, one for each existing field, and used the saved K
  area-32 labels as immutable references without rerunning area variants.
- The implemented immutable trace separates raw foreground additions,
  post-morphology
  support, and final labels so causal contribution is not conflated with final
  acceptability. P2-R1 and P1-R4 retain their existing fixed coordinates for
  focused human review.
- The exact two-field package contract verifies source/reference hashes before
  execution, saves all causal masks and final labels, reports complete-field
  and fixed-crop changes, generates unclassified full-field/focused views, and
  hashes every generated artifact.
- Six new synthetic tests cover validation, determinism, unchanged behavior at
  `0.0`, monotonic raw support, the declared `0.5` threshold, exact one-factor
  construction, fixed area `32`, rejection of unauthorized variants/fields,
  and a synthetic exactly-two-call package. No real TIFF was read or segmented.
- The real package is
  `outputs/module7_kmeans_foreground_causal_review_20260718/`. Its two C1
  source hashes and two saved-reference hashes matched the earlier K-means
  manifest before execution. The new manifest lists 24 generated artifacts;
  post-run validation found no hash mismatch, both human-observation rows are
  blank, and both full-field PNG plus all four SVG files passed structural or
  render checks.
- Position 1 changed from the saved 60-ROI / 7,260-pixel reference to a
  descriptive candidate mask with 84 labels / 12,475 foreground pixels. It
  added 5,308 raw-selection pixels, 5,336 post-morphology pixels, and 5,215
  final pixels without removing saved-reference support. Inside P1-R4 it added
  133 raw-selection, 123 post-morphology, and 111 final pixels, with zero
  removals at the recorded post-morphology and final comparisons.
- Position 2 changed from the saved 81-ROI / 9,187-pixel reference to a
  descriptive candidate mask with 106 labels / 16,504 foreground pixels. It
  added 7,153 raw-selection pixels, 7,325 post-morphology pixels, and 7,317
  final pixels without removing saved-reference support. Inside P2-R1 it added
  423 raw-selection, 427 post-morphology, and 417 final pixels, with zero
  removals at the recorded post-morphology and final comparisons.
- These counts describe mask changes only. They do not classify the new
  support, establish causal contribution, assess final acceptability, infer
  sample sufficiency or representativeness, approve or register a profile,
  change the global baseline, or use D046. D065 separately records the later
  scientific visual classification.
- The complete design is
  `docs/MODULE_7_KMEANS_FOREGROUND_CAUSAL_EXTENSION_DESIGN.md`. No profile is
  registered, no baseline changes, no scientific conclusion is inferred, and
  D046 is not used or modified.

**Completed D064 scientific visual review**

- D065 records the scientific user's confirmation that the relaxed foreground
  boundary contributes to recovery in both P1-R4 and P2-R1.
- P1-R4 gains visible cellular support and expanded border-object coverage but
  also contains a small isolated addition without clear cellular structure.
- P2-R1 recovers several omitted cellular peripheries or bodies, while other
  dim bodies remain without final ROIs; its classification is contribution but
  not sufficient.
- The complete fields show no field-wide background carpet, but they retain
  many omissions and show localized nonspecific expansion and possible
  bridging. Read-only label overlap identifies 3 / 5 bridge candidates and
  27 / 31 wholly new candidate labels in Position 1 / Position 2.
- The `0.5` relaxation is not accepted as a production profile or global
  baseline. This two-field result does not establish sufficiency or
  representativeness, authorize another run, or use D046.
- The immutable D064 package remains unchanged. Its blank manifest-listed
  observation CSV is preserved, and the later confirmation is recorded in
  `docs/MODULE_7_D064_SCIENTIFIC_REVIEW.md` and D065.
- D066 closes the current monotonic K-means foreground-boundary relaxation
  branch without another segmentation execution. A smaller relaxation cannot
  recover support still omitted at `0.5`; a larger relaxation cannot remove
  the nonspecific support or connections already exposed at `0.5`. This does
  not reject K-means generally or authorize a different mechanism.
- D067 selects formulation of a new, separately justified K-means causal
  mechanism as the next Module 7 design block instead of immediately reopening
  the unchanged K-means versus Marker Watershed comparison. The saved Marker
  Watershed marker and threshold evidence does not resolve the current
  omission-versus-specificity problem, so repeating that comparison would add
  no discriminating evidence. The future mechanism must be outside the closed
  monotonic global-boundary branch and distinguish wholly omitted-cell recovery
  from expansion of an existing support. No candidate, implementation, or
  segmentation run is authorized.
- D068 completes that design block without implementation or execution. Its
  single candidate keeps the global K-means fit and area-32 controls fixed but
  conditions the baseline boundary on a deterministic local P20 offset in
  locally darker regions. The raw candidate remains a union with unchanged
  K-means support, while the audit trace separately identifies detached,
  single-anchor, and multi-anchor proposals and final de novo, expansion,
  carried, and bridge relations against the immutable area-32 labels.
- The field-relative local-window rule is fixed in the diagnostic design and
  is not a registered or approved acquisition profile. Geometric zero overlap
  does not identify a cell: omitted-cell recovery, cellular completion,
  nonspecific addition, and D051 bridge interpretation remain explicit human
  review classes. D068 authorizes no code, test execution, segmentation,
  artifact generation, global-baseline change, D046 use, or inference of
  sufficiency or representativeness. The design is
  `docs/MODULE_7_KMEANS_LOCAL_BACKGROUND_CAUSAL_DESIGN.md`.
- D069 records the later explicit implementation authorization. The single
  `local_background_p20` mode and its immutable trace are implemented exactly
  at P20 with NumPy-linear interpolation, NumPy-style reflection without edge
  repetition, and window side
  `2 * floor(min(height, width) / 8) + 1`. The global K-means fit, morphology,
  connectivity, area 32, and relaxation fraction `0.0` remain fixed.
- The candidate is an unregistered one-mode diagnostic outside all existing
  OFAT/relaxation catalogs, the global baseline, and D046. Its trace preserves
  local P20 and threshold maps, stage masks, immutable area-32 references,
  exact additions/removals, and raw/final topology relations. Every topology
  class remains geometric and requires later human interpretation.
- Five focused tests use synthetic arrays only and cover the exact window and
  percentile rule, unchanged control, determinism, threshold/gate arithmetic,
  raw/final support invariants, all proposal/final topology classes, fixed
  controls, and rejection paths. No TIFF was read or segmented and no real
  artifact was generated. Real execution, profile selection, sufficiency, and
  representativeness remain unauthorized and unassessed.
- D070 is a decision-only review of the D069 boundary. It confirms that any
  later real-data execution must first receive a separately reviewed
  authorization design. It does not define that design, authorize a real
  segmentation call or artifact, change the global baseline, register a
  profile, use D046, or assess sufficiency or representativeness.
- D071 now supplies that authorization design without activating it. It fixes
  one selection identifier, a new output destination, the same two fields in
  P1/P2 order, the exact D069 candidate, current source/prepared/reference
  hashes, fixed controls, fail-closed preflight, no-retry behavior, immutable
  artifact requirements, and a required later activation statement.
- Because the D069 runner deliberately records synthetic-only provenance,
  D071 requires a separately requested implementation-only package block with
  synthetic tests before a still later explicit real-execution authorization.
  No code, TIFF-derived candidate call, artifact, profile action, D046 action,
  or scientific conclusion is authorized by D071. The design is
  `docs/MODULE_7_KMEANS_LOCAL_BACKGROUND_REAL_EXECUTION_AUTHORIZATION_DESIGN.md`.
- D072 completes that separately requested implementation-only block. It adds
  a typed D071 package boundary with exact selection/destination/field/variant
  identities, distinct synthetic-contract and authorized-real execution
  scopes, fail-closed full preflight, started/completed call counters, no
  automatic retry, isolated incomplete attempts, postflight hash/file checks,
  and publication only after two successful calls. The public D069 runner
  remains synthetic-only and cannot accept a package execution scope.
- Five new tests exercise only synthetic arrays, synthetic source bytes, saved
  synthetic reference arrays, and temporary publication paths. They verify the
  exact two-call order, all rejection paths required by D071, trace/component
  and blank-observation preservation, complete artifact hashes, unchanged
  inputs, no-retry failure isolation, and non-creation of the declared D071
  destination. No real TIFF was read or segmented and the real gate remains
  inactive.
- A later separately authorized execution produced the immutable package at
  `outputs/module7_kmeans_local_background_causal_review_d071/`. D073 records a
  subsequent read-only integrity check and bounded visual observation block.
  All 35 manifest-listed artifacts, source hashes, and saved-reference hashes
  matched. Human review used only the two complete-field previews and the fixed
  P1-R4/P2-R1 sheets; detailed observations are preserved in
  `docs/MODULE_7_D071_REAL_REVIEW_HUMAN_OBSERVATIONS.md`.
- The D073 block reran no segmentation, modified no D071 artifact, tuned no
  parameter, took no profile action, did not use D046, and made no sufficiency,
  representativeness, acceptability, or final scientific conclusion.

**Completed single Cellpose operational test**

- D050 explicitly selects only `Capture 1 + Position 1` and the unchanged D047
  `cellpose_cpsam / benchmark_baseline` variant. The choice carries no
  representativeness, sufficiency, preference, ranking, or accuracy claim.
- Executes exactly one engine call on the selected 600 x 600 C1 first frame
  with identity preprocessing, CPU, `gpu = false`, `torch_threads = 1`, and
  `cpsam_v2`. No fallback, warm-cache repeat, second field, or second variant is
  run.
- Records `3003.7913557` seconds (50 minutes 3.791 seconds) as engine-only
  operational timing for the cold-cache call. The initial 1.15 GB weight
  download occurred inside that timed model construction; no warm-cache time
  is inferred.
- Defines a precondition for considering any complete Cellpose block under the
  same 600 x 600 CPU configuration: the conservative declared projection
  `run_count x 3003.7913557` must not exceed 43,200 seconds (12 engine-hours).
  This permits at most 14 declared runs and does not authorize such a block.
- Preserves the one-run package in
  `outputs/module7_cellpose_timed_test_20260714/` with exact labels,
  unclassified visual artifacts, blank observations, operational timing,
  provenance, and SHA-256 hashes.
- Does not infer sample sufficiency, rank or classify variants, approve or
  register a profile, establish scientific Cellpose feasibility, change the
  global K-means baseline, substitute another engine, or use or modify D046.

**Pending scientific decisions**

- Representative-field coverage and any future claim beyond provisional use.
  D074 permits development to continue with the area-32 K-means working
  profile but explicitly does not establish universal accuracy, sample
  sufficiency, or complete segmentation of every cell. No complete Cellpose
  block is currently selected or authorized.
- Calibration and scientific review of `strict`, `medium`, and `permissive`.
- D051 confirms the desired handling of touching cells: divide them into
  individual ROIs when the split is reliable; otherwise retain one connected
  ROI and quantify them jointly. The automatic reliability criterion and any
  corresponding engine change remain pending validation. D055 resolves the two
  inspected Marker Watershed `distance=8` cases as doubtful and joint, but does
  not define the future automatic criterion.
- D052 limits the current scientific comparison to K-means plus morphology and
  Marker Watershed. Cellpose remains on standby; Global Otsu and P99 are
  outside this comparison block without being universally rejected. No method
  or variant is selected. D067 defers reopening the unchanged comparison until
  a new causal candidate or another separately justified source of evidence
  can add discriminating information.
- D053 and D054 resolve the dim-silhouette and area-32-component questions for
  the two inspected fields only; they do not resolve representative-field
  coverage or profile calibration.
- D056 confirms omission of many valid cells by Marker Watershed baseline and
  distance=8 in these fields. D057 resolves candidacy by advancing only K
  `area=32` to final human comparison, without approving it. D058 resolves the
  six-run extension authorization, and the completed masks show no recovery in
  P2-R1. D059 resolves the new sub-32-pixel component classification as cells
  in these fields, and D060 resolves the final comparison set as K area `32`
  only. D061 records that K area `32` is not yet acceptable on these examples.
  D062 defines and D063 implements the minimum global-boundary intervention, D064
  records its exact authorized two-run package, and D065 confirms that the
  foreground boundary contributes but the `0.5` relaxation remains
  insufficient and is not accepted. D066 closes this specific scalar
  relaxation branch; no additional relaxation value, run, or profile change is
  authorized. D067 requires a separately justified spatial or locally adaptive
  mechanism, and D068 now defines the single locally background-conditioned
  candidate, its fixed controls, and its recovery-versus-expansion audit
  classes. D069 implements and verifies that exact candidate only on synthetic
  arrays. D070 requires a separate authorization design before real execution,
  and D071 supplies the exact two-call, fail-closed design without activating
  it. D072 implements and verifies its typed package boundary synthetically.
  A later separately authorized execution produced the D071 package, and D073
  verifies its manifest and records bounded complete-field and fixed-region
  human observations. D074 does not select that local-background variant and
  closes the immediate parameter-search branch by adopting unchanged K-means
  area 32 only as a provisional working profile. Broader scientific validity
  and representative-field coverage remain pending.
- Future GUI interaction for representative-field selection and approval.
- Future advanced user editing of engine parameters.

---

## Module 8 — Geometric ROI filtering

**Status:** VALIDATED

**Responsibility**

- Calculate ROI area and relevant geometry.
- Apply configurable minimum/maximum area.
- Handle border-touching objects.
- Preserve rejection reasons.

**Implemented behavior**

- Uses `filter_segmentation_rois(SegmentationResult, ...)` as the typed
  Module 7-to-8 boundary. It reads that result's existing `label_image`
  directly and retains the exact source `SegmentationResult`, including engine,
  provisional profile, effective parameters, seeds, package versions,
  structured issues, and selection/review provenance.
- Preserves the exact source label array by identity at that typed boundary.
  Filtering only replaces rejected-label supports with background in the
  filtered image; retained labels are never renumbered or reinterpreted.
- Keeps `filter_labeled_rois(...)` as a provenance-free low-level helper for
  synthetic masks and compatibility, not as the integrated Module 7 handoff.
- Measures each positive label in a 2D integer mask as one ROI, preserving the
  original label values rather than renumbering them.
- Records pixel area, inclusive bounding box, centroid, border-touching status,
  geometric status, and structured reasons for flagged or rejected ROIs.
- Applies configurable minimum and maximum area limits in pixels.
- Supports configurable border-touching policy: accept, flag while retaining,
  or exclude.
- Produces a filtered label image with rejected ROIs removed and structured
  issues carrying context for flagged/rejected ROIs.

**D075 validation**

- All 8 focused Module 8 tests and the complete 139-test suite pass. The new
  synthetic canonical `SegmentationResult` verifies that the provisional
  K-means area-32 profile provenance remains attached, the source label image
  is consumed directly, and rejecting label `1` leaves retained label `2`
  unchanged. The synthetic integration harness also verifies source-result and
  source-label identity through the configured validation path.
- Validation uses only small synthetic NumPy arrays and temporary synthetic
  TIFF fixtures. It does not read or rerun TIFF files under `raw_data/`, modify
  D071 packages, search parameters, or change any Module 7 profile setting.

**Pending scientific decision**

Physical-area filtering in µm² remains pending until pixel calibration handling
and acquisition profiles are defined.

---

## Module 9 — Visual ROI review

**Status:** VALIDATED

**Validated responsibility**

- Generate one dependency-free, self-contained HTML viewer from an existing
  typed `TiffPair`, `RoiFilteringResult`, and `SegmentationReviewState`.
- Navigate every temporal frame in C0 and C1 while applying the same fixed ROI
  contours to both channels and every frame.
- Preserve original positive label values and Module 8 accepted, flagged, and
  rejected statuses without relabeling or changing either label image.
- Persist an unfinished review draft in browser-local storage and export one
  explicit field-inspection JSON.
- Validate the exported field, exact source-label and Module 8 filtering
  SHA-256 values, effective method/profile, and selection source before
  recording the inspection through the existing immutable D046 backend.

**Acceptance criteria**

- C0/C1 selection, frame navigation, status visibility controls, and label
  visibility controls are present in the generated viewer.
- Every source ROI has one clickable contour with its unchanged label, geometry
  status, area, border contact, and reasons.
- Review export remains disabled until the reviewer explicitly confirms that
  the displayed field was inspected.
- Loading rejects malformed JSON; application rejects a different field,
  changed source labels or Module 8 statuses, or a stale
  method/profile/selection source with an actionable error.
- Applying a valid export calls D046 `record_inspection(...)` and does not grant
  global approval, delete an ROI, modify a mask, rerun segmentation, or change
  any scientific parameter.
- Synthetic expected and failure cases pass without reading TIFFs under
  `raw_data/` or adding a production dependency.

**Implemented behavior**

- `export_interactive_roi_review_html(...)` embeds normalized display-only PNG
  frames, a fixed SVG contour layer, exact ROI audit data, current D046 review
  status, and browser-side controls in one portable HTML file.
- Browser-local storage preserves channel/frame position, visibility settings,
  reviewer fields, notes, and explicit confirmation for that exact
  Capture + Position and source-label hash.
- The downloaded `funes.module9.roi_review.v1` JSON is strictly parsed into
  `InteractiveRoiReviewDecision`; `apply_interactive_roi_review_decision(...)`
  verifies provenance before returning a new immutable review state.
- A stable label-image hash includes the image shape and exact canonical
  `int32` pixel values. A second hash covers both masks, Module 8 configuration,
  statuses, reasons, and geometry. Intentional label gaps remain unchanged.
- The viewer records manual inspection only. D046 global approval remains a
  separate explicit operation and cannot be triggered from this viewer.

**Validation**

- Six focused synthetic tests cover two-channel/three-frame embedding, labels
  `1`, `2`, and `4`, all three Module 8 statuses, HTML controls and local draft
  persistence, exact D046 inspection recording, immutable masks, malformed
  review JSON, changed-label/status rejection, stale-selection rejection,
  shape mismatch, output extension, and display configuration.
- The generated inline JavaScript parses successfully with the bundled Node.js
  runtime. Automated visual opening of the local `file://` artifact was blocked
  by the in-app browser URL policy, so no browser screenshot is claimed.
- The six focused tests and the complete 152-test suite pass. All validation
  uses in-memory synthetic arrays; no real TIFF is read or segmented.
- A field-specific operational export for `Capture 1 + Position 2` reuses the
  persisted K-means area-32 label artifact whose recorded SHA-256 is
  `c4428d4f6f470ce00a9fbeaf57503f850237b8d5b7781b8dba259799b2c97aa3`.
  Because its typed Module 8 result was not persisted, the export reconstructs
  only geometry with the unchanged real-pair validation configuration
  (`min_area_pixels=20`, border exclusion), producing 81 source labels, 79
  retained labels, and 2 rejected labels over both temporal frames. It verifies
  both raw-TIFF hashes and the label-artifact hash before writing the viewer and
  explicitly records that segmentation was not executed. The reproducible
  script and output manifest are under
  `scripts/export_module9_capture1_position2.py` and
  `outputs/module9_roi_review_capture1_position2/`.
- Local-file browser storage is best-effort. Failure or malformed data from
  `localStorage` no longer aborts viewer initialization or disables channel and
  frame navigation; the viewer continues without draft persistence and reports
  that storage is unavailable. Position 2 verification confirms that both C0
  and C1 embedded frame PNGs have different SHA-256 values.
- Every generated viewer also includes an explicit static all-frame atlas below
  the interactive stage. It writes one ordinary HTML image per channel/frame,
  so temporal content remains directly inspectable when a `file://` browser
  blocks or caches interactive JavaScript. The Position 2 `v2` artifact contains
  exactly C0/F0, C0/F1, C1/F0, and C1/F1 panels.
- The explicit Position 2 inspection export was copied into the workspace with
  SHA-256 `7f4ac58780f832b79185f0989b3d25cdd401317e11e8c6e4a9350784ec4a96f1`,
  strictly loaded, and applied through the existing provenance checks. The
  resulting field status is `manually_reviewed`; reviewer, inspection time, and
  note remain unspecified as exported. A persistent receipt records that no
  global approval was granted and no segmentation, mask, or parameter changed.
- A matching operational export for `Capture 1 + Position 1` reuses the
  persisted K-means area-32 artifact with recorded SHA-256
  `36ab719aec5b736f56deb1c44f9286b023536ccc906780bad8934f51ae2ba9af`.
  The exporter verifies both TIFF hashes, reconstructs only the unchanged
  Module 8 geometry boundary (minimum 20 pixels, border exclusion), and calls
  no segmentation entry point. The v2 viewer has both C0/C1 temporal frames,
  60 source labels, 56 retained labels, 4 rejected labels, and exactly four
  static atlas panels. Its companion manifest records the generated HTML hash,
  unreviewed status, and JSON filename prepared for explicit manual export.
  Viewer JSON and JavaScript parse, all four embedded PNG hashes are distinct,
  six focused tests pass, and the complete 152-test suite passes.
- The explicit Position 1 inspection export with SHA-256
  `4c696164fcc0fa9d0f3b75cdf36789cc639288a36ff0c36f72de4d397a81ed23`
  was strictly validated against the field, source-label hash, complete Module
  8 filtering hash, and current global K-means area-32 selection, then applied
  through D046. The resulting field status is `manually_reviewed`; optional
  reviewer provenance remains null exactly as exported. Its persistent receipt
  records that no global approval was granted and no segmentation, mask, or
  parameter changed.

**Next pending review boundary after D087**

- Both fields currently present under `raw_data/` are now recorded as
  `manually_reviewed` for the global
  `kmeans/provisional_working_kmeans_area32` selection.
- Their inspection exports record only `decision: inspected`; neither export
  approves the profile for an uninspected field, assesses representative-field
  sufficiency, or removes the known D074 limitations.
- The next coherent D045/D046 block is therefore an explicit scientific-user
  decision on global approval. If approved, the immutable approval must
  snapshot both existing inspections and preserve a distinct approval
  identifier and receipt. Until that decision is supplied, no global approval
  exists and future uninspected fields remain `unreviewed`.
- No additional representative field is available in the current `raw_data/`
  directory. Expanding the inspection sample requires an explicitly supplied
  acquisition rather than another execution on these same two fields.

**Confirmed future coverage choice (D088)**

- Choose review coverage separately for each experiment: either manually
  inspect every position, or let the user select a subset and then separately
  approve the exact global method/profile for the remaining positions.
- A completed subset never triggers approval automatically, and an approval
  scoped to one experiment must not cover another experiment.
- Both positions in the current dataset are already manually reviewed, so the
  current experiment needs no global-policy acceptance to achieve complete
  position coverage.
- Each inspected position retains navigation through every C0/C1 frame. This
  segmentation-review choice does not approve temporal QC or other downstream
  scientific policies.
- D089 implements the bounded experiment-scoped orchestration described below.

**Implemented experiment-scoped position orchestration (D089)**

- The pre-implementation audit confirmed that D046 alone is not safe for a
  multi-experiment state: it normalizes `PositionKey` to `CapturePositionKey`
  and owns one global approval. D089 therefore leaves D046 unchanged and adds
  one typed, immutable D046 ledger owner per experiment.
- `ExperimentPositionReview` records the exact experiment, known positions,
  D088 mode, selected subset, D044 configuration, D046 inspections, and any
  explicit approval. `ExperimentRoiReviewOrchestrator` rejects duplicate
  experiment scopes and routes every query, viewer, inspection, and approval
  through the matching isolated ledger.
- `review_all` requires an individual inspection for every position and
  forbids remaining-position approval. `review_selected` requires a non-empty
  proper subset; completing that subset only removes its manual-review
  backlog. A separate `approve_remaining(...)` call is rejected until every
  selected position is manually inspected and at least one position remains
  `unreviewed`.
- D044 field overrides retain precedence. Existing D046 inspection records,
  approval snapshots, reviewer notes, method/profile, and selection-source
  provenance are carried unchanged inside the experiment owner. Positions
  outside an explicit approval and without an override or inspection remain
  exactly `unreviewed`.
- New experiment-scoped viewer exports carry the experiment in the downloaded
  inspection JSON, browser-storage key, and review filename. The loader remains
  backward compatible with the earlier D081-D087 JSON that lacks an experiment,
  while the new orchestrator requires an exact experiment identity.
- Scalability is bounded by exporting one requested position at a time instead
  of aggregating every experiment frame into one HTML artifact. Each position
  viewer still exposes every C0/C1 timepoint and the same fixed ROI contours;
  the orchestrator retains no image arrays and performs no segmentation.

**D089 validation**

- Seven new synthetic tests cover two experiments with identical Capture +
  Position names, non-propagating approval, both modes, incomplete-sample
  rejection, D044 precedence, D046 provenance, cross-experiment rejection,
  experiment-aware JSON round-trip, and a five-timepoint C0/C1 viewer.
- The 23 focused Module 7/9 review tests and the complete 159-test suite pass.
  `compileall` also passes. No real TIFF was read or segmented, and no mask,
  profile, ROI, or scientific parameter was changed.

**Implemented experiment-review snapshot persistence (D090)**

- The bounded next Module 9 block persists an entire
  `ExperimentRoiReviewOrchestrator` as the versioned
  `funes.module9.experiment_roi_review.v1` JSON schema. It preserves each exact
  experiment position scope, D088 mode and selected subset, D044 global
  selection and field overrides, D046 inspection ledger, optional reviewer
  provenance, approval, and pre-approval inspection snapshot.
- Export records both a canonical payload SHA-256 inside the document and the
  written-file SHA-256 in a typed result. Export is state-neutral: it cannot
  add an inspection, call `approve_global(...)`, or create a scientific
  approval.
- Loading requires the exact schema and exact fields, verifies payload
  integrity, reconstructs typed enums and immutable contracts, and then passes
  the result through the existing D044, D046, and D089 validation boundaries.
  Changed content, duplicate fields, stale selection provenance, an invalid
  approval snapshot, cross-scope positions, and unsupported schemas fail
  closed with actionable context.
- Persistence contains no TIFF pixels or ROI masks. It does not read real
  TIFFs, generate viewers, run segmentation, edit labels, or introduce a
  production dependency.

**D090 validation**

- Five new synthetic tests cover a two-experiment round trip with an isolated
  D044 override and D046 approval, unapproved state neutrality, changed
  payload and unknown-field rejection, rehashed incoherent approval rejection,
  malformed JSON, unsupported schema, and invalid output extension.
- The focused 28 Module 7/9 review tests, `compileall`, and the complete
  164-test suite pass. No current or future experiment received a new
  scientific approval.

**Implemented snapshot-backed review session (D091)**

- `ExperimentRoiReviewSession` is a small Module 9 application boundary over
  the unchanged D089 orchestrator and D090 snapshot APIs. It opens a strictly
  validated snapshot, reports all pending D088 manual targets, distinguishes
  targets whose typed material is available in the current delivery, exports
  one existing position viewer, applies one explicit viewer inspection, and
  writes the resulting state through D090.
- `PositionRoiReviewMaterial` accepts only an already-produced typed `TiffPair`
  and `RoiFilteringResult` with an assigned experiment. Material delivery may
  be partial, but duplicate, unknown, unassigned, and cross-experiment
  positions fail closed. The session never discovers or reads TIFF files and
  never runs Modules 5-8 or any later scientific analysis.
- The session deliberately has no approval operation. It cannot call D046
  global approval, infer sample sufficiency, or change D044 selection. Viewer
  decisions still pass through all D089 field, experiment, label-hash,
  filtering-hash, and selection-provenance checks before becoming an
  inspection.
- The session provides no ROI creation, deletion, drawing, relabeling, or mask
  persistence. Caller-owned frames and fixed Module 8 masks remain outside the
  D090 snapshot and are not mutated.

**D091 validation**

- Five new synthetic tests cover snapshot opening, ordered cross-experiment
  pending queues, partial material availability, one four-frame C0/C1 viewer
  and inspection round trip, state-neutral persistence, duplicate and
  out-of-scope rejection, missing material, typed inputs, unchanged masks, and
  the absence of TIFF reading, segmentation calls, and approval access.
- The focused 33 Module 7/9 review tests, `compileall`, and the complete
  169-test suite pass. No real TIFF was read or segmented and no scientific
  approval, ROI, mask, profile, or parameter changed.

**Initial substitute**

Static QC image export was implemented and validated separately on 2026-07-13:

- overlays the unchanged first-frame segmentation labels on the selected
  segmentation channel;
- preserves original label numbers and distinguishes accepted, flagged, and
  rejected geometry with both color and line pattern;
- embeds the grayscale frame and audit context in SVG and emits a dependency-
  free PNG view for inspection;
- does not by itself allow ROI deletion, editing, navigation, or
  manual-decision persistence; D081 later supplied navigation and inspection
  persistence while deletion and editing remain deferred;
- does not approve the D039 placeholder segmentation profile. The detailed
  review is `docs/MODULE_9_STATIC_ROI_OVERLAY_VALIDATION.md`.
- a broader static, auditable validation report for `Capture 1 + Position 1`
  now links the original frames, Module 5 metrics, preprocessing, Module 7
  threshold/mask/components, Module 8 numbered statuses and reasons,
  background/intensity/saturation summaries, ROI scatter, ratio distribution,
  module I/O table, CSV audit records, and a SHA-256 manifest. It changes no
  scientific parameter. The record is
  `docs/CAPTURE1_POSITION1_STATIC_VISUAL_VALIDATION.md`.

**Deferred extensions**

- Manual ROI deletion, mask drawing/editing, changed-mask persistence, and
  creation of new labels remain outside this validated read-only scope.
- D091 now coordinates pending work and caller-supplied material across many
  experiment fields, while each exported viewer intentionally remains limited
  to one explicitly supplied Capture + Position. Automatic acquisition loading
  and a full analysis pipeline runner remain separate.

---

## Module 10 — Quantitative background estimation

**Status:** VALIDATED

**Responsibility**

- Estimate quantitative background by channel and frame.
- Return values and diagnostics.
- Support replaceable strategies.

**Implemented behavior**

- Defines a replaceable quantitative background strategy interface that operates
  on validated C0/C1 TIFF pairs and returns one estimate per channel and
  temporal frame.
- Provides a configurable percentile-based estimator with explicit pixel
  source selection: non-ROI pixels or full-frame pixels.
- In the integrated Module 8-to-10 handoff, consumes
  `RoiFilteringResult.filtered_label_image` explicitly. Retained labels keep
  their original values (including intentional gaps), while supports rejected
  by geometry are background for the configured non-ROI pixel source.
- Preserves method name, parameters, frame reference, channel, background value,
  pixel count/fraction, mean, median, standard deviation, caller context, and
  structured issues.
- Reports structured errors when too few background pixels are available, while
  preserving per-frame records with `None` background values.
- Keeps quantitative background correction separate from segmentation-only
  preprocessing.

**D076 validation**

- A focused synthetic Module 7-to-8-to-10 test constructs the typed D074
  provisional area-32 result without running a segmentation engine, applies
  D075 filtering, and passes the exact `filtered_label_image` to Module 10.
  It verifies that rejected label `1` becomes eligible non-ROI background,
  retained label `2` remains excluded from background without renumbering, and
  the source segmentation profile provenance remains unchanged upstream.
- Validation uses only small synthetic NumPy arrays and in-memory synthetic
  frame sequences. It does not read or rerun TIFF files under `raw_data/`,
  reopen segmentation parameters, or modify any Module 7 review package.
- All 15 focused Module 8/10 tests and the complete 140-test suite pass; any
  TIFF files exercised by the complete suite are temporary synthetic fixtures.

**Pending scientific decision**

Choose the production quantitative background method and parameters after
representative images are inspected. Global, local, non-cell, manual, and
hybrid approaches remain scientifically open.

---

## Module 11 — Intensity quality control

**Status:** VALIDATED

**Responsibility**

- Evaluate saturation and low signal.
- Use camera profiles and background-aware thresholds.
- Preserve metrics, warnings, and exclusion reasons.
- Keep frame-, ROI-, and field-level decisions distinct.

**Implemented behavior**

- Defines a replaceable intensity-QC strategy interface operating on a validated
  C0/C1 TIFF pair, a fixed ROI label image, quantitative background estimates,
  and an explicit QC configuration.
- Exposes an integrated typed entry point that consumes
  `RoiFilteringResult.filtered_label_image` exactly, while retaining the
  array-based entry point for strategy compatibility and synthetic callers.
- Preserves intentional gaps in retained ROI labels and consumes the existing
  `QuantitativeBackgroundResult` from Module 10 without estimating background
  again. The background method is recorded in result parameters and ROI-frame
  metrics.
- Requires an explicit camera saturation profile rather than inferring the
  meaningful saturation limit from TIFF dtype.
- Evaluates saturated-pixel counts and fractions at field-frame and ROI-frame
  scope, then preserves aggregate ROI and field status separately.
- Evaluates low-signal ROI-frame status using background-corrected mean divided
  by background standard deviation, with channel-specific configurable SNR
  thresholds.
- Preserves method name, parameters, metrics, structured reasons, and issues
  when background estimates are missing or low-signal SNR cannot be assessed.

**D077 validation**

- A focused synthetic Module 7-to-8-to-10-to-11 test constructs the typed D074
  provisional area-32 result without executing a segmentation engine, applies
  D075 filtering, and gives Module 11 the resulting `RoiFilteringResult` plus
  the exact `QuantitativeBackgroundResult` already calculated by Module 10.
- An identity-checking replaceable strategy verifies that Module 11 receives
  the same `filtered_label_image` object and the same background-result object.
  Rejected label `1` produces no QC record; retained label `2` remains `2`, and
  its corrected measurements use the channel-specific Module 10 values.
- All 5 focused Module 11 tests and the complete 141-test suite pass. Validation
  uses synthetic arrays and temporary synthetic TIFF fixtures only; no TIFF
  under `raw_data/` was read or rerun and no segmentation parameter was reopened.

**Pending scientific decisions**

Production camera profiles, saturated-pixel fraction thresholds, low-signal SNR
thresholds, and final exclusion policy remain acquisition/profile-specific and
must be chosen after representative data review.

---

## Module 12 — Temporal intensity extraction

**Status:** VALIDATED

**Responsibility**

- Apply fixed ROIs to every frame in C0 and C1.
- Extract raw and corrected measurements.
- Preserve frame index and time when known.
- Do not calculate FRET ratios.

**Implemented behavior**

- Defines a replaceable temporal intensity extraction strategy operating on a
  validated C0/C1 TIFF pair, a fixed ROI label image, quantitative background
  estimates, and Module 11 intensity-QC records.
- Exposes an integrated typed entry point that consumes `RoiFilteringResult`
  and passes its exact `filtered_label_image` to the replaceable extraction
  strategy, while retaining the array-based entry point for compatibility and
  synthetic callers.
- Emits one measurement record per positive ROI label, temporal frame, and
  channel, preserving frame index and optional configured frame time.
- Records ROI area, raw mean, raw median, quantitative background value,
  background-corrected mean, and background-corrected median without calculating
  FRET ratios or channel-role mappings.
- Preserves matching Module 11 QC status and reasons at ROI-frame,
  field-frame, aggregate ROI, and aggregate field scopes.
- Reuses the existing Module 10 `QuantitativeBackgroundResult` and Module 11
  `IntensityQcResult` objects without estimating background or evaluating QC
  again, and records both upstream method names in result parameters.
- Reports structured issues when background estimates or expected QC records
  are missing while still preserving raw measurements.

**D078 validation**

- A focused synthetic Module 7-to-8-to-10-to-11-to-12 test constructs the
  typed D074 provisional area-32 result without executing a segmentation
  engine, rejects label `1` geometrically, and retains label `2` unchanged.
  An identity-checking replaceable strategy verifies that Module 12 receives
  the exact `filtered_label_image`, background-result, and intensity-QC-result
  objects. Temporal records contain label `2` only, use the existing
  channel-specific background correction, and preserve the matching Module 11
  QC status and reasons.
- All 4 focused Module 12 tests and the complete 142-test suite pass.
  Validation uses synthetic arrays and temporary synthetic TIFF fixtures only;
  no TIFF under `raw_data/` was read or rerun. The focused D078 handoff test
  executes no segmentation engine and reopens no Module 7 parameter.

---

## Module 13 — FRET calculations

**Status:** VALIDATED

**Responsibility**

- Preserve C0/C1 donor/FRET provenance according to configuration.
- Configure ratio numerator and denominator independently from biological roles.
- Calculate ratios and normalization.
- Preserve baseline definition and missing/excluded values.
- Do not export presentation-specific workbooks.

**Validated behavior**

- Defines a replaceable FRET calculation strategy operating only on Module 12
  temporal intensity measurements, not TIFF image data.
- Both public calculation boundaries require a runtime-validated
  `TemporalIntensityResult`; array-like, record-tuple, TIFF-pair, background,
  or QC inputs cannot enter Module 13 by structural duck typing.
- Fixes the ratio formula as C0 numerator divided by C1 denominator, independent
  from the separately configured biological donor/FRET provenance.
- Uses background-corrected ROI mean as the default manual-workflow intensity
  definition confirmed in D043, while preserving raw mean and corrected mean
  explicitly for both channels in every calculation record.
- Calculates C0/C1, R/R0, and delta R/R0 from the configured corrected metric;
  neither biological-role mapping can reverse the channel formula.
- Preserves biological donor/FRET roles, baseline definition, input QC status
  and reasons by C0/C1 channel, missing values, excluded-frame policy, and
  structured issues for missing paired channel measurements or unavailable
  baselines.
- Records the prior D039/D041 C1/C0 outputs as superseded in auditable
  parameters.
- Does not implement Module 14 export layouts.

**D079 validation**

- A focused synthetic D078-to-13 test obtains the input by calling
  `extract_filtered_roi_temporal_intensities(...)`, then verifies that a
  replaceable FRET strategy receives that exact `TemporalIntensityResult`
  object. Labels `2` and `4` remain unchanged after labels `1` and `3` are
  removed; Module 13 emits only ROI `2` and `4` records and never fills the
  intentional gaps.
- The same test spies on TIFF reading, quantitative-background estimation,
  both Module 11 QC entry points, and both Module 12 extraction entry points;
  none is called during FRET calculation. It uses only in-memory synthetic
  arrays and no TIFF under `raw_data/`.
- All 9 focused Module 13 tests and the complete 144-test suite pass.

---

## Module 14 — Export

**Status:** VALIDATED

**Responsibility**

- Create human-readable and machine-readable outputs.
- Include metadata, hierarchy, measurements, and QC.

**Implemented behavior**

- Creates one `.xlsx` workbook file per experiment from current upstream
  Module 8, 10, 11, 12, and 13 records.
- Requires every `Module14PositionExport` to contain runtime-validated
  `RoiFilteringResult`, `QuantitativeBackgroundResult`, `IntensityQcResult`,
  `TemporalIntensityResult`, and `FretCalculationResult` instances. None of
  these five analysis results is optional or accepted by structural duck
  typing at the Module 14 boundary.
- Consumes those completed upstream results without running segmentation, ROI
  filtering, quantitative-background estimation, intensity QC, temporal
  extraction, or FRET calculation. Positive ROI identifiers are exported as
  supplied; intentional gaps such as retained labels `2` and `4` are not
  filled or renumbered.
- Uses the D032 accepted wide layout for value sheets: elapsed-time rows, one
  ROI per column, row 6 as the displayed ROI label, row 7 as the abbreviated
  `cN/pN/rN` identity, blue spacer columns between positions, and double peach
  spacer columns between captures.
- Writes separate value sheets for `ratio`, `r_over_r0`,
  `delta_r_over_r0`, `donor_corrected`, `fret_corrected`, and `qc_status`.
- Preserves metadata, method parameters, ROI geometry records, background
  estimates, intensity QC records, temporal intensity records, FRET records,
  QC statuses, exclusion reasons, and structured issues as audit sheets in the
  same workbook.
- Adds the `roi_provenance` audit sheet with one row per exported position. It
  records the effective `automatic` or `manual_revision` mask source and, only
  for a manual revision, the exact finalized Module 24 `revision_sha256`; value
  sheets and their D032 layout remain unchanged.
- Reads verified Module 3 auxiliary associations directly from each exported
  `TiffPair`; the metadata sheet includes the association method and referenced
  TIFF names, parsed SlideBook header values, raw log text, and every structured
  table row with source-line and original-row provenance.
- Uses a small standard-library Office Open XML writer, adding no production
  spreadsheet dependency.

**Validation**

- Seven focused Module 14 synthetic tests cover workbook-per-experiment
  packaging, D032 header rows and spacer columns, QC status preservation,
  metadata, parameters, auxiliary metadata, issues, and rejection of an
  incorrect runtime type for each required Module 8/10/11/12/13 result, plus
  automatic/manual mask-source and revision-hash provenance.
- The D080 regression fixture contains only retained ROI labels `2` and `4`.
  It verifies those exact gaps in the wide headers and Module 8, 11, 12, and 13
  audit sheets. Spies confirm that Module 14 calls none of the public
  segmentation, ROI-filtering, quantitative-background, QC, temporal-
  extraction, or FRET-calculation entry points.
- All 39 focused Module 8/10/11/12/13/14 tests and the complete 146-test suite
  pass.
- Additional representative upstream-bundle validation on 2026-07-13 generated
  one workbook each for `Exp A Forskolin Pilot` and `Exp B Vehicle Control`
  from current Module 8, 10, 11, 12, and 13 record contracts, rendered every
  sheet to PNG, and scanned for spreadsheet error tokens. Visual review
  confirmed the D032 value sheets and prompted D034 semantic widths for
  audit/long sheets.
- Real-pair integration validation on 2026-07-13 ran `Capture 1 + Position 1`
  from the TIFF files in `raw_data/` through the available Modules 1-8 and
  10-14, producing 36 retained placeholder ROIs and one 15-sheet workbook.
  Every sheet rendered successfully, the spreadsheet error-token scan was
  empty, and the validation-only scientific assumptions were preserved as a
  structured warning. The run also corrected unknown frame times so the value
  sheets show `frame_index / index` rather than inventing seconds. The detailed
  record is `docs/MODULE_14_REAL_PAIR_VALIDATION.md`.

**Current planning artifact**

- `docs/MODULE_14_EXPORT_EXAMPLES_PLAN.md` lists candidate example workbook
  variants, synthetic cases, and review criteria. It is explicitly not a final
  workbook specification.
- `outputs/module14_review_examples_20260712/` contains non-final synthetic
  review artifacts for candidate variants A, B, and C. These files are examples
  only and do not select or define the final workbook format.
- Review feedback selected the human-review wide style as the basis for the
  final specification, with elapsed-time rows, ROI-as-columns, and visual
  spacer columns between positions/captures.
- `outputs/module14_refined_roi_columns_example_20260712/` contains a refined
  non-final example using one `.xlsx` file per experiment, elapsed-time rows,
  one ROI per column, separate value sheets, blue position spacer columns, and
  double peach capture spacer columns.
- Review accepted the refined layout for implementation. Row 6 keeps the
  displayed ROI label, row 7 keeps the abbreviated full ROI identity
  (`cN/pN/rN`), and the exporter creates one `.xlsx` workbook file per
  experiment.
- `outputs/module14_upstream_validation_20260713/` contains the representative
  upstream-bundle validation workbooks, render previews, and compact inspection
  logs used for the D034 audit-sheet readability refinement.
- `outputs/module14_real_pair_validation_20260713/` contains the workbook and
  verification artifacts from the real TIFF integration run.

---

## Module 15 — Reviewed single-position analysis orchestration

**Status:** VALIDATED

**Responsibility**

- Compose existing Modules 5-13 for one already assigned in-memory `TiffPair`.
- Consume, but never create, the exact experiment-scoped D089 review decision.
- Execute the exact D044/D046 named segmentation selection and preserve its
  review provenance in the Module 7 result.
- Require every scientific configuration explicitly at the orchestration
  boundary.
- Do not discover or read TIFFs, approve a segmentation policy, edit ROI,
  persist review state, export workbooks, or execute real data implicitly.

**Implemented behavior (D092)**

- Adds immutable `PositionAnalysisConfig` and `PositionAnalysisResult`
  contracts plus `run_reviewed_position_analysis(...)`.
- Requires explicit Module 5 channel selection, Module 6 preprocessing,
  Module 8 geometry, Module 10 quantitative background, Module 11 camera/QC,
  Module 12 timing, and Module 13 biological-role/baseline configurations.
  The D044/D046 segmentation selection comes only from the supplied D089
  ledger; the runner has no independent method/profile argument or fallback.
- Rejects unassigned or unknown positions. In D088 `review_all`, and for every
  selected target in `review_selected`, the position must have its own D046
  inspection even when a D044 override has primary status. Other positions
  must already be covered by an experiment-isolated decision, such as an
  existing explicit approval or an explicit field override.
- Calls `segment_configured_first_frame(...)` with the exact isolated D046
  state, retains that result through Module 8, applies the same fixed labels to
  both channels and every frame downstream, and aggregates stage issues
  without changing them.
- Fails before Modules 10-13 when geometry retains no ROI. It creates no
  approval, changes no D090 snapshot, and offers no ROI creation, deletion,
  drawing, relabeling, or changed-mask persistence.

**Validation**

- Five focused synthetic tests cover the complete Modules 5-13 path, exact
  manual-review provenance, consumption of an already-existing synthetic
  experiment approval without mutation, rejection before analysis of an
  unreviewed target, the D089 manual-inspection requirement for a
  `review_all` override, and assigned-position/context integrity.
- `compileall`, the focused 5-test runner suite, and the complete 174-test
  suite pass. No file under `raw_data/` was read, no segmentation was run on
  real data, and no scientific approval, ROI, mask, profile, parameter, or
  production dependency changed.

**Optional Module 24 integration (D104)**

- Accepts no revision or one finalized root `RoiMaskRevision` after automatic
  Module 8 geometry and before Module 10. A supplied revision is replayed
  fail-closed against the current automatic results with no fallback.
- Keeps automatic Module 7/8 provenance and the replayed Module 24 result
  separate, while Modules 10-13 consume only the one effective automatic or
  revised measurement mask.
- Seven position-runner tests now cover the original five cases plus finalized
  revised-mask propagation and draft/stale rejection before Module 10. The
  complete 231-test suite passes.

---

## Module 16 — Reviewed experiment analysis orchestration

**Status:** VALIDATED

**Responsibility**

- Compose Module 15 for every declared position in exactly one D089 experiment.
- Consume only already assigned, in-memory `TiffPair` values and explicit
  per-position `PositionAnalysisConfig` values.
- Preflight the complete experiment scope and its D046 coverage before any
  position analysis begins.
- Preserve deterministic D089 position order and aggregate unchanged stage
  issues.
- Do not discover or read TIFFs, create inspections or approvals, change D044
  selection, persist state/results, export, edit ROI, or activate real data.

**Implemented behavior (D093)**

- Adds immutable `ExperimentAnalysisResult`, actionable
  `ExperimentAnalysisError`, and `run_reviewed_experiment_analysis(...)`.
- Requires the supplied pairs and configuration mapping to match the complete
  isolated D089 scope exactly. Missing, unexpected, duplicate,
  cross-experiment, and conflicting batch-context identities fail closed.
- Validates every D088 manual target and every other coverage decision before
  invoking D092 for the first position, so a later uncovered position cannot
  cause an earlier partial analysis run.
- Runs positions in the order already declared by D089 even when pair and
  configuration inputs arrive in another order. Each call remains subject to
  the unchanged D092 and D044/D046 checks.
- Returns only ordered in-memory Module 15 results and their unchanged issues;
  it exposes no export, persistence, approval, inspection, ROI mutation, file
  loading, or scheduling-concurrency operation.

**Validation**

- Five focused synthetic tests cover deterministic D089 ordering, complete
  scope/configuration matching, duplicate and cross-experiment rejection,
  batch-context integrity, and whole-batch review preflight before analysis.
- `compileall`, the focused 10-test Module 15/16 suite, and the complete
  179-test suite pass. No file under `raw_data/` was read, no real-data
  segmentation was run, and no scientific approval, ROI, mask, profile,
  parameter, snapshot, export, or production dependency changed.

**Optional Module 24 propagation (D105)**

- Accepts an optional `PositionKey -> RoiMaskRevision` mapping for any subset
  of the exact D089 experiment scope. Positions omitted from the mapping keep
  the unchanged automatic-mask path.
- Preflights the complete mapping before the first Module 15 call: every key
  must belong to the experiment, every value must be a finalized root
  revision, and each revision source identity must match its mapping key.
- Passes the exact revision object only to its matching D089-ordered position.
  Module 15 performs the unchanged D104 replay against the automatic Module
  7/8 results and remains responsible for stale mask-hash rejection without
  fallback.
- Two additional synthetic tests cover mixed automatic/revised positions,
  exact revised-mask provenance and quantitative flow, unchanged D046 state,
  and complete preflight rejection of draft, wrong-key, and chained revisions.
  `compileall`, 29 focused Module 15/16/24 tests, and the complete 233-test
  suite pass.

---

## Module 17 - Reviewed experiment workbook export orchestration

**Status:** VALIDATED

**Responsibility**

- Consume exactly one already completed in-memory `ExperimentAnalysisResult`
  from Module 16.
- Adapt every ordered position to the existing typed Module 14 boundary and
  create the single D032 workbook for that experiment.
- Preserve the exact assigned pair, Module 8/10/11/12/13 result objects,
  position order, positive-label gaps, pair-associated auxiliary metadata, and
  aggregated issues supplied by D092/D093, including the effective mask source
  and finalized revision hash when Module 24 was used.
- Do not discover or read TIFFs, run or rerun analysis, create an inspection
  or approval, change D044 selection, persist D090 review state or a separate
  analysis bundle, edit ROI, schedule multiple experiments, or activate real
  data.

**Implemented behavior (D094)**

- Adds `export_reviewed_experiment_workbook(...)` plus immutable
  `ReviewedExperimentExportResult` and actionable
  `ReviewedExperimentExportError` contracts.
- Requires a runtime-validated Module 16 result. It constructs one
  `Module14PositionExport` per D089-ordered position using the exact existing
  `TiffPair`, `RoiFilteringResult`, `QuantitativeBackgroundResult`,
  `IntensityQcResult`, `TemporalIntensityResult`, and
  `FretCalculationResult` objects; no calculation or label transformation is
  available at this boundary.
- Passes the complete ordered tuple to `export_module14_workbooks(...)`
  exactly once. Because the input contains one experiment, the result requires
  exactly one workbook and exposes its path without changing the accepted D032
  layout.
- Retains the source Module 16 result and exact Module 14 position inputs in
  the returned contract for auditability. Export failures carry the experiment
  identity and original error as the cause.
- Requires every adapted `Module14PositionExport` to retain the exact Module
  16 `mask_source` and `revision_sha256`, which Module 14 writes only to its
  separate `roi_provenance` sheet.

**Validation**

- Focused synthetic tests cover a real `.xlsx` write from two positions,
  D089 ordering, exact upstream-object identity, unchanged issues, one and
  only one Module 14 invocation, rejection before export of an invalid input,
  contextual write failure, exact mask-source/revision-hash propagation, and
  absence of upstream analysis or D090 snapshot calls.
- The D108 closure runs 11 focused Module 14/17 tests, 27 focused
  Module 14/17/21/22 tests, and the complete 246-test suite. All validation
  uses in-memory synthetic arrays and temporary output paths; no file under
  `raw_data/` is read, no real-data segmentation is run, and no scientific
  approval, review snapshot, ROI, mask, profile, parameter, workbook layout,
  or production dependency changes.

---

## Module 18 - Acquisition loading and assignment orchestration

**Status:** VALIDATED

**Responsibility**

- Compose existing Modules 1-4 for one explicitly supplied acquisition
  directory and explicit experiment-assignment rules.
- Preserve each discovery, auxiliary-metadata association, TIFF validation,
  and experiment-assignment result and issue without reinterpretation.
- Supply only complete, error-free assigned in-memory `TiffPair` values to
  later callers.
- Do not create review state or approval, run Modules 5-17, persist an analysis
  bundle, schedule experiments, edit ROI, or activate `raw_data/` implicitly.

**Implemented behavior (D095)**

- Adds immutable `AcquisitionLoadResult`, actionable
  `AcquisitionLoadingError`, and `load_assigned_acquisition(...)`.
- Requires an existing directory plus explicit typed Module 4 rules. It calls
  TIFF discovery, auxiliary-text discovery, explicit Module 3 association,
  C0/C1 validation, and Module 4 assignment exactly once in dependency order.
- Retains all five typed stage results. Its aggregate issue tuple keeps each
  upstream issue object unchanged in stage order and appends only the Module 18
  `no_assigned_tiff_pairs` error when no assigned pair exists.
- `assigned_pairs` fails closed whenever any stage has an error, even if an
  earlier/later stage produced a valid subset. Warnings remain auditable and do
  not block an otherwise complete assigned load.
- Pair-associated auxiliary metadata reaches the assigned pair through the
  unchanged D036/Module 4 path. Experiment labels are never inferred from log
  content.

**Validation**

- Five focused temporary synthetic-TIFF tests cover the complete Modules 1-4
  composition, explicit SlideBook-log association, unchanged image-object and
  issue identity, missing assignment, a valid subset accompanied by a malformed
  TIFF, invalid roots, exact stage call counts, and the absence of review,
  segmentation, analysis, export, or snapshot calls.
- `compileall`, the focused 5-test Module 18 suite, and the complete 188-test
  suite pass. No file under `raw_data/` was read, no real-data analysis was run,
  and no scientific approval, review state, ROI, mask, profile, parameter,
  workbook, persisted analysis bundle, or production dependency changed.

---

## Module 19 - Acquisition review-scope initialization

**Status:** VALIDATED

**Responsibility**

- Consume one complete, error-free D095 `AcquisitionLoadResult` without
  rediscovering or rereading acquisition files.
- Require one explicit D088 coverage choice and exact D044 segmentation
  configuration for every assigned experiment.
- Construct fresh experiment-isolated D089 review owners in unchanged D095
  experiment and position order.
- Preserve exact assigned-pair and segmentation-configuration objects.
- Do not create an inspection or approval, run analysis, persist review or
  analysis state, export artifacts, edit ROI, or activate real data.

**Implemented behavior (D096)**

- Adds immutable `AcquisitionReviewExperimentConfig` and
  `AcquisitionReviewSetupResult` contracts, actionable
  `AcquisitionReviewSetupError`, and `initialize_acquisition_review(...)`.
- Fails closed unless the D095 load exposes its complete `assigned_pairs` and
  the caller supplies exactly one configuration for every loaded experiment;
  missing, unexpected, duplicate, invalid-subset, and duplicate-position
  scopes are rejected without producing a partial orchestrator.
- Preserves first-seen D095 experiment order and pair order within each
  experiment. The result retains the source load, exact ordered pair objects,
  exact caller-supplied configuration objects, and the fresh D089 orchestrator.
- Initializes each isolated D046 ledger with the exact D044 configuration and
  no inspections or global approval. A D044 field override remains an override
  and does not satisfy a D088 manual-review target.

**Validation**

- Five focused synthetic tests cover multi-experiment ordering and identity,
  `review_selected` pending state without automatic approval, unchanged D044
  override precedence, exact experiment-configuration coverage, and refusal of
  an error-bearing D095 load without downstream calls.
- `compileall`, 27 focused Module 18/19 and D089-D091 tests, and the complete
  193-test suite pass. No file under `raw_data/` was read, no real-data
  execution occurred, and no scientific approval, inspection, ROI, mask,
  profile, parameter, snapshot, workbook, analysis bundle, or production
  dependency changed.

---

## Module 20 - Reviewed acquisition analysis orchestration

**Status:** VALIDATED

**Responsibility**

- Compose existing Module 16 once per experiment in one exact D096 acquisition
  scope.
- Require an explicitly updated D089 review orchestrator and one explicit
  Module 15 scientific configuration for every assigned position.
- Preflight the complete cross-experiment scope and all D046 coverage before
  the first experiment analysis begins.
- Preserve D095/D096 experiment and position order, exact assigned pairs,
  D044 configuration identity, completed in-memory results, and unchanged
  issues.
- Do not inspect or approve fields, discover/read files, persist results or
  review state, export workbooks, edit ROI, or activate real data implicitly.

**Implemented behavior (D097)**

- Adds immutable `AcquisitionAnalysisResult`, actionable
  `AcquisitionAnalysisError`, and `run_reviewed_acquisition_analysis(...)`.
- Requires the exact D096 experiment order, D088 scopes, positions, selected
  subsets, and D044 configuration objects. The review orchestrator may contain
  only caller-recorded later inspections or explicit experiment-scoped
  approvals; this boundary creates or changes none.
- Requires exact acquisition-wide `PositionKey` coverage by typed
  `PositionAnalysisConfig` values and rejects experiment/capture/position
  identity fields in shared acquisition context.
- Audits every D088 manual target and every D046 coverage decision before the
  first Module 16 call, so an invalid later experiment cannot allow an earlier
  one to start.
- Invokes Module 16 exactly once per experiment in unchanged D096 order and
  retains the exact ordered `TiffPair` objects and in-memory Module 16 results.
  Aggregate issues retain upstream object identity and experiment/position
  order.

**Validation**

- Five focused temporary synthetic-TIFF tests cover ordered multi-experiment
  execution and exact object identity, whole-acquisition preflight, changed
  scope and D044 rejection, exact scientific-config coverage, acquisition
  context isolation, exact Module 16 call count, and absence of loading,
  approval, persistence, or export calls.
- `compileall`, the focused 42-test D089-D097 orchestration suite, and the
  complete 198-test suite pass. No file under `raw_data/` was read, no real-data
  execution occurred, and no scientific approval, persisted inspection, ROI,
  mask, profile, parameter, snapshot, workbook, analysis bundle, or production
  dependency changed.

**Optional Module 24 propagation (D106)**

- Accepts an optional `PositionKey -> RoiMaskRevision` mapping for any subset
  of the complete D096 acquisition. Omitted positions and an omitted mapping
  retain the unchanged automatic-mask path.
- Preflights the complete acquisition-wide mapping before the first Module 16
  call: every key must belong to D096, every value must be a finalized root
  revision, and every revision source position must equal its mapping key.
- Partitions the validated mapping by experiment in unchanged D096/D089 order
  and passes each exact revision object to Module 16. D105 and D104 remain the
  only per-experiment propagation and replay boundaries.
- Two additional synthetic tests cover mixed automatic/revised acquisition
  flow, exact revision and quantitative provenance, unchanged D046 state, and
  whole-mapping rejection of draft, out-of-scope, wrong-key, and chained
  revisions before any experiment call.
- Adds no export, persistence or artifact loading, UI, Module 23 binding,
  `raw_data` access, activation authority, or scientific approval.
- `compileall`, 36 focused Module 15/16/20/24 tests, and the complete 235-test
  suite pass using only synthetic or temporary fixtures for this block.

---

## Module 21 - Reviewed analysis package persistence

**Status:** VALIDATED

**Responsibility**

- Consume one already completed in-memory `AcquisitionAnalysisResult` plus the
  explicit Module 15 configuration for every completed position.
- Persist and strictly reconstruct all results needed for later inspection or
  export without discovering sources, reading TIFFs, or rerunning analysis.
- Preserve D095/D096/D097 experiment and position order, source identity and
  metadata, numerical arrays, configuration, D044/D046/D089 review provenance,
  stage issues, exclusions, and internal shared-object provenance.
- Use a versioned, typed, integrity-checked format and fail closed on unknown
  schema/types/fields, changed content, incomplete members, or incoherent
  reconstructed contracts.
- Do not inspect or approve fields, change review state or scientific
  configuration, export workbooks, edit ROI/masks, or activate real data.

**Implemented behavior (D098)**

- Adds immutable `PositionAnalysisConfigEntry`, `ReviewedAnalysisPackage`, and
  `ReviewedAnalysisPackageWriteResult` contracts, actionable
  `ReviewedAnalysisPackageError`, and
  `export_reviewed_analysis_package(...)` / `load_reviewed_analysis_package(...)`.
- Uses the exact schema identifier
  `funes.module21.reviewed_analysis_package.v1` in a
  `.funes-analysis.zip` container. `manifest.json` holds the typed object graph,
  canonical payload SHA-256, and the exact ordered member manifest; NumPy arrays
  are separate non-pickle `.npy` members with individual size, dtype, shape, and
  SHA-256 validation.
- The typed graph codec accepts only known FUNES contracts and enums, exact
  dataclass fields, ordered tuples/mappings, paths, finite or explicitly tagged
  non-finite scalars, and safe non-object NumPy arrays. It never imports a type
  named by package data and never uses `pickle`.
- Explicit object identifiers and references reconstruct shared provenance
  within the loaded package: assigned pairs remain the same objects used by
  position results, D044 configuration identity remains shared across D096 and
  the later review ledger, and Module 8 retains its exact Module 7 source.
- Export requires exact acquisition-wide configuration coverage, records it in
  unchanged result order, checks its observable method/geometry/channel
  compatibility, refuses to overwrite an existing package, and publishes a new
  package atomically. Loading reruns all existing immutable contract checks but
  invokes no pipeline stage or review operation.

**Validation**

- Five focused synthetic tests cover two-experiment round-trip ordering and
  shared provenance, exact and compatible configuration coverage, schema,
  payload and array tampering, typed reconstruction after a valid rewritten
  integrity hash, and absence of analysis, review mutation, TIFF loading, or
  workbook export calls.
- `compileall`, the focused 5-test Module 21 suite, and the complete 203-test
  suite pass. The Module 21 path read no file under `raw_data/`, executed no
  real data, and invoked no workbook exporter. No scientific approval,
  inspection, ROI, mask, profile, parameter, prior snapshot/schema, or
  production dependency changed.

**Versioned optional Module 24 persistence (D107)**

- Advances the current package and domain-separated payload hash to exact
  schema `funes.module21.reviewed_analysis_package.v2`; v1 remains D098's
  historical schema and is rejected fail-closed rather than silently
  reinterpreted or migrated.
- Extends the closed typed codec registry with the Module 24 revision and
  replay contracts already nested in a completed D106 result. A mixed package
  may contain automatic positions and revised positions while preserving the
  finalized revision, operation trace, edited and measurement masks, exact
  automatic Module 7/8 objects, shared identities, and Modules 10-13 results.
- Module 21 still consumes only one completed in-memory analysis. It does not
  load or export standalone revision artifacts, rerun analysis/replay, mutate
  D046 state, export a workbook, add UI, bind Module 23, access `raw_data/`,
  grant activation authority, or approve science.
- Seven focused synthetic tests cover prior Module 21 behavior plus mixed v2
  round trip, dual provenance/shared identity, effective revised measurements,
  unchanged D046 state, and explicit v1 rejection.
- `compileall`, 37 focused Module 15/16/20/21/24 tests, and the complete
  237-test suite pass.

---

## Module 22 - Complete reviewed application runner

**Status:** VALIDATED

**Responsibility**

- Compose one explicitly supplied acquisition, one existing D090 review
  snapshot, exact assignment rules, and explicit Module 15 scientific
  configuration through the existing D095-D098 boundaries.
- Reconstruct the D096 scope with the exact D044 configuration objects loaded
  from the snapshot, then require D097 to validate all existing D088/D046
  coverage before analysis.
- Export one unchanged D094 workbook per analyzed experiment and one complete
  D098 analysis package.
- Publish all artifacts together under one new caller-supplied output
  directory without overwriting an existing destination.
- Do not record an inspection, grant an approval, infer scientific acceptance,
  choose scientific defaults, edit ROI/masks, or activate `raw_data/`
  implicitly.

**Implemented behavior (D099)**

- Adds immutable `ReviewedApplicationRunResult`, actionable
  `ReviewedApplicationRunError`, and `run_reviewed_application(...)`.
- Requires caller-supplied acquisition root, explicit Module 4 assignment
  rules, a strictly validated D090 snapshot path, exact per-position
  `PositionAnalysisConfig` values, and a new output directory. It provides no
  default acquisition path and has no `raw_data/`-specific operation.
- Preserves the snapshot path and SHA-256, verifies that the snapshot does not
  change while loading, derives only D088/D044 setup inputs from its existing
  experiment ledgers, and creates no new review decision.
- Runs D095 once, D096 once, D097 once, D094 once per experiment in unchanged
  D095/D096 order, and D098 once. The result retains the exact typed
  acquisition, setup, loaded review orchestrator, analysis, ordered workbook
  adapters, and persisted-package receipt.
- Builds the fixed `workbooks/` directory and
  `reviewed_analysis.funes-analysis.zip` inside a private staging directory,
  then publishes the complete directory with one rename. Any artifact failure
  removes only the unpublished staging directory; an existing destination is
  never replaced.

**Validation**

- Five focused synthetic-TIFF tests cover the complete two-experiment path,
  exact object/order and snapshot preservation, loadable D098 evidence,
  D094 workbooks, absence of inspection/approval calls, fail-closed incomplete
  coverage, changed experiment order, and preservation of a pre-existing
  destination.
- `compileall`, the focused 25-test D095-D099 suite, and the complete 208-test
  suite pass. No file under `raw_data/` was read, no real acquisition was
  activated, and no scientific approval, inspection, ROI, mask, profile,
  parameter, prior schema, workbook layout, or production dependency changed.

**Optional Module 24 propagation (D108)**

- Adds a keyword-only optional per-position finalized root revision mapping to
  `run_reviewed_application(...)` and passes the exact mapping through the
  existing Module 20 acquisition-wide preflight. Omitted positions retain the
  automatic path.
- Retains the mixed automatic/revised graph in the Module 22 result and writes
  it through the existing Module 21 v2 package boundary, without standalone
  revision-artifact loading, export, or replay.
- Leaves D099's existing workbook publication unchanged and does not add
  Module 24 mask-source/revision-hash presentation to Module 17/14.
- Adds no UI, revision-chain/path consumption, Module 23 binding, `raw_data`
  access, activation authority, scientific approval, or dependency.
- Two synthetic tests cover exact propagation and v2 reconstruction, unchanged
  D046 state, absent standalone revision-artifact I/O, and fail-closed draft
  rejection before any experiment analysis. `compileall`, 35 focused Module
  15/16/20/21/22 tests, and all 239 tests pass.

---

## Module 23 - Explicit real-data activation boundary

**Status:** VALIDATED

**Responsibility**

- Put an explicit, single-attempt authorization boundary in front of D099
  before any acquisition-root access.
- Bind one immutable activation plan by SHA-256 to the exact acquisition scope,
  assignment rules, D090 snapshot, per-position Module 15 configurations,
  output/audit destinations, evidence-only purpose, and no-retry policy.
- Preserve D044/D046/D089-D099 unchanged and let D097 remain the authority for
  existing review coverage.
- Distinguish operational activation from review coverage, scientific-
  configuration approval, and later interpretation.
- Keep ROI/mask editing outside this module.

**Completed design (D100)**

- Defines separate design, implementation-only, and explicit real-activation
  gates. D100 itself grants no execution authority.
- Requires `purpose = evidence_generation_only` and
  `scientific_status = not_approved` until separate scientific decisions exist.
- Requires a versioned immutable plan, canonical hash, exact expected source
  scope, snapshot/configuration hashes, a unique single-use activation ID, one
  D099 call, no retry, and separate started/completed/failed receipts.
- Places authority validation before any acquisition-root read. Later source
  preflight and postflight must inventory hashes, reject scope drift, and prove
  that raw and auxiliary sources remained unchanged.
- Requires atomic publication only after a coherent D099 result and complete
  postflight. Failed attempts remain explicitly failed/quarantined evidence and
  cannot reuse their authorization identifier.
- Explicitly forbids using activation as D046 inspection/approval, scientific
  validation, configuration selection, source repair, field omission, fallback,
  or ROI/mask mutation.
- The complete contract is
  `docs/MODULE_23_REAL_DATA_ACTIVATION_BOUNDARY_DESIGN.md`.

**Acceptance criteria for the later implementation-only block**

- Adds small immutable typed plan, authorization, and receipt contracts plus one
  activation entry point without changing D099.
- Synthetic tests prove zero acquisition-root access before authorization,
  exact hash/scope/configuration binding, a single D099 call, no retry,
  single-use attempt IDs, failure receipts, source immutability checks, and
  atomic completed publication.
- Tests prove that inspection, approval, scientific-default selection, and
  ROI/mask editing APIs are never called.
- Uses only synthetic TIFFs and temporary paths; it does not inspect, hash, or
  execute `raw_data/` and does not create a concrete real activation plan.

**Implemented behavior (D101)**

- Adds immutable, versioned plan, configuration-bundle, authorization,
  source/artifact/review, receipt, result, and actionable error contracts.
  Domain-separated canonical SHA-256 values bind the complete typed Module 15
  configuration bundle and complete activation plan.
- Requires the later authorization statement to name the exact plan ID and
  hash. Before any acquisition-root access, it validates authority, fixed
  evidence-only/not-approved and one-call/no-retry policies, absent paths,
  configuration integrity, and the unchanged D090 hash/schema/scope/order.
- Atomically reserves the activation ID with a started receipt, then inventories
  exactly the planned TIFF/auxiliary sources and calls unchanged D099 at most
  once in private outer staging, with no fallback or retry.
- Postflight requires exact D099 scope, unchanged source/snapshot/configuration
  hashes, a matching loadable D098 package, exact D094 workbook paths/hashes,
  and preserved D046 statuses before atomic publication.
- Failure writes a typed failed receipt with stage and actual D099 call count,
  publishes no completed destination, and quarantines incomplete evidence.
  Every receipt retains `evidence_generation_only`, `not_approved`, and false
  inspection, approval, scientific-default-selection, and ROI/mask-edit flags.

**D101 validation**

- Six focused tests use only small synthetic TIFFs, synthetic D090 state, and
  temporary paths. They cover zero acquisition access before valid authority,
  exact source/configuration binding, one D099 call, source immutability,
  atomic success, failure quarantine, non-reusable IDs, and absent review or
  approval calls.
- `compileall`, focused Module 22/23 tests, and the complete 214-test suite
  pass. No path under `raw_data/` was listed, read, or hashed; no concrete real
  plan or activation ID was created; and no scientific approval, inspection,
  ROI, mask, profile, parameter, prior schema, workbook layout, or production
  dependency changed.

---

## Module 24 - Auditable manual ROI mask revision

**Status:** IN PROGRESS

**Responsibility**

- Add an optional, immutable mask-revision boundary after Module 8 and before
  Modules 10-13.
- Preserve the complete automatic Module 7/8 result while allowing explicit
  add, delete, replace, and restore operations on ROI labels.
- Keep label identity stable, make every change replayable, and bind source and
  result masks with canonical SHA-256 provenance.
- Recompute geometry, background, QC, temporal intensity, and FRET from one
  finalized revised mask applied unchanged to every frame in both channels.
- Keep D046 inspection/approval, scientific profile approval, interactive UI,
  and Module 23 activation authority separate.

**Completed design (D102)**

- Selects Module 24 before a concrete Module 23 plan because D101 v1 cannot
  bind manual mask revisions and the provisional automatic segmentation retains
  known whole-cell coverage limitations.
- Defines a backend-only first implementation block using synthetic masks and
  temporary paths, followed by separate integration, UI, and activation-binding
  blocks.
- Requires exact automatic-mask hashes, immutable ordered operations, stable
  existing labels, monotonically allocated new labels, explicit editor/reason
  provenance, deterministic replay, strict persistence, and fail-closed stale
  or invalid revisions.
- Requires later Module 23 versioning to bind the explicit absence or exact
  finalized hash/path of each position revision before any concrete activation
  plan for the corrected-mask workflow.
- The complete contract is
  `docs/MODULE_24_AUDITABLE_ROI_MASK_REVISION_DESIGN.md`.

**Implemented backend-only block (D103)**

- Adds immutable v1 source, pixel-support, operation, revision, trace, finalized
  result, and strict JSON artifact contracts without adding a UI or dependency.
- Binds each revision to exact Experiment + Capture + Position, image shape,
  Module 7 source-label SHA-256, and complete Module 8 filtering SHA-256.
- Replays ordered delete, replace, add, and restore operations deterministically;
  preserves existing labels, requires monotonically increasing fresh labels,
  rejects label reuse, overlap, out-of-bounds support, stale provenance, and
  per-operation or net no-ops.
- Supports explicit parent-revision hashes and carries the complete operation
  trace while retaining the exact original Module 7 and Module 8 objects.
- Recomputes geometry under the unchanged Module 8 configuration and keeps the
  complete edited mask distinct from the post-policy measurement mask, both as
  immutable arrays with canonical hashes.
- Finalization requires a caller-supplied timezone-aware timestamp. Drafts
  cannot replay or persist as analysis-eligible artifacts.
- Strict persistence rejects duplicate/unknown fields, non-standard JSON
  numbers, altered checksums, stale automatic inputs, and rehashed mask/audit
  tampering by reconstructing and replaying the complete artifact on load.

**D103 validation**

- 15 focused tests use only small synthetic label masks and temporary paths.
  They cover all four operations, deterministic and chained replay, stable and
  monotonic labels, geometry recomputation, immutable provenance, finalization,
  strict round-trip persistence, and the D102 failure cases.
- The complete 229-test suite passes using repository tests whose fixtures are
  synthetic or temporary; no path under `raw_data/` was listed or read.
- Tests prove the original Module 7/8 masks stay unchanged and the Module 9 /
  D046 inspection and approval APIs are never called by replay.
- No Modules 15-23 integration, exporter change, UI, activation plan or ID,
  real-data authority, scientific approval, dependency, or raw artifact was
  added.

**Implemented optional position-runner block (D104)**

- Adds one optional finalized `RoiMaskRevision` input to the reviewed position
  runner. With no revision, the prior automatic-mask path remains unchanged.
- Replays a supplied finalized root revision against the exact automatic
  Module 7/8 results produced in that run. Draft, stale, wrong-position, or
  otherwise invalid revisions fail before Module 10 with no automatic fallback.
- Preserves the automatic `RoiFilteringResult` and the finalized
  `RoiRevisionResult` separately on `PositionAnalysisResult`; exposes the sole
  effective measurement geometry, stable `automatic` / `manual_revision` mask
  source, and optional revision SHA-256 without converting an edit into D046
  inspection or approval.
- Runs Modules 10-13 exclusively with the automatic filtered mask or the
  revision's post-policy measurement mask, never a mixture. A revision may be
  applied before the no-retained-ROI guard so explicit add/restore operations
  are not precluded by an empty automatic measurement mask.
- Adds three focused synthetic integration tests for automatic compatibility,
  exclusive revised-mask propagation, immutable dual provenance, unchanged
  review state, and fail-closed draft/stale rejection before background
  estimation. No real data, UI, artifact path, Module 23 plan, or scientific
  approval is involved.
- `compileall`, the 32 focused Module 20/24 and adjacent orchestration tests,
  and the complete 231-test suite pass.

**Implemented optional experiment-runner propagation block (D105)**

- Adds an optional per-position revision mapping only to Module 16. The
  mapping may cover a subset of one complete D089 experiment; every omitted
  position retains the automatic path.
- Validates scope, value type, exact source-position identity, finalized state,
  and root-only status for the complete mapping before any Module 15 call.
- Propagates each exact revision object to its matching D089-ordered call and
  relies on D104 for replay against the current automatic hashes, exclusive
  revised-mask measurement, dual provenance, and fail-closed stale rejection.
- Adds no Module 20-23 propagation, export, persistence, artifact/path loading,
  UI, revision-chain orchestration, real-data access, or scientific approval.
  `compileall`, 29 focused Module 15/16/24 tests, and all 233 tests pass.

**Implemented optional acquisition-runner propagation block (D106)**

- Adds the same optional subset mapping to Module 20 and validates the complete
  D096 acquisition mapping before any Module 16 call.
- Distributes exact finalized root revision objects only to their matching
  experiment and leaves omitted positions on the automatic path.
- Adds no export, persistence/artifact loading, UI, Module 23 revision binding,
  `raw_data` access, activation authority, or scientific approval.
- `compileall`, 36 focused Module 15/16/20/24 tests, and all 235 tests pass.

**Implemented versioned Module 21 persistence block (D107)**

- Persists mixed automatic/revised D106 results under Module 21 schema v2 and
  reconstructs the complete finalized Module 24 result, dual automatic/revised
  provenance, masks, trace, shared identities, and quantitative outputs.
- Rejects D098 v1 packages explicitly rather than changing their fixed schema
  meaning, and performs no standalone revision-artifact I/O or replay.
- Adds no export, UI, Module 23 binding, `raw_data` access, activation authority,
  scientific approval, or production dependency.
- `compileall`, 37 focused Module 15/16/20/21/24 tests, and all 237 tests pass.

**Implemented optional complete-runner propagation block (D108)**

- Adds the same optional subset mapping to Module 22 and passes it unchanged
  through Module 20's complete acquisition preflight.
- Preserves exact in-memory revision identity in the mixed result and persists
  that graph with Module 21 v2; omitted positions remain automatic.
- The later D108 closure also accepts explicitly supplied artifact paths through
  the verified Module 22 route and presents the already effective provenance in
  Module 17/14's separate `roi_provenance` sheet; this does not alter Module
  22 publication, Module 21 v2, or D032 value sheets.
- Adds no UI, revision-chain/path consumption, Module 23 binding, `raw_data`
  access, activation authority, scientific approval, or dependency.
- Focused Module 22 artifact-route tests, 27 focused Module 14/17/21/22 tests,
  and all 246 tests pass.

**Integrated finalized-artifact and export-provenance close (D109)**

- Finalizes one caller-supplied Module 24 draft only by deterministic replay
  against its exact automatic Module 7/8 provenance, strict v1 artifact write,
  reload, and trace/mask/hash comparison; it refuses overwrite and never turns
  finalization into a scientific acceptance or D046 change.
- Module 22's optional explicit artifact-path route is mutually exclusive with
  the in-memory revision route, hashes each path before and after strict replay
  validation, and retains the resolved path plus artifact and revision hashes.
- Module 17/14 presents only the already effective `mask_source` and optional
  `revision_sha256` in `roi_provenance`; neither Module 21 v2 persistence nor
  D032 numerical/value-sheet behavior changes.

**Implemented finalized revision-chain consumer (D110)**

- Adds the isolated backend `load_finalized_roi_revision_chain(...)` for one
  explicit non-empty ordered sequence of finalized Module 24 JSON artifacts.
  It is not connected to Modules 15-23 or any application runner.
- Strictly replays every artifact against the same exact automatic Module 7/8
  results. The first revision must be a root; each following revision must name
  the immediately preceding finalized revision as its parent. The returned
  terminal result is the only mask result a future consumer could use.
- Preserves resolved artifact paths and SHA-256 values for every chain entry;
  rejects duplicate paths and verifies each artifact SHA-256 before and after
  strict load/replay to fail closed on a changed path.
- Five focused synthetic tests cover a valid two-revision chain and rejection
  of inverted order, a non-immediate parent, duplicate paths before replay, and
  a changed artifact. No `raw_data/`, UI, Module 23, activation, approval, or
  scientific parameter is involved.

**Implemented position-runner chain integration (D111)**

- Extends only `run_reviewed_position_analysis(...)` with one optional,
  already-validated `RoiRevisionChainResult`, mutually exclusive with its
  existing single-root revision input. It does not load artifact paths.
- Revalidates the supplied chain structure and requires its terminal source
  identity to match the newly produced automatic Module 7/8 provenance for the
  exact position. It preserves the complete chain in `PositionAnalysisResult`
  and passes only `terminal_result.geometry_audit` to Modules 10--13.
- Synthetic temporary-path tests cover a two-artifact chain whose terminal mask
  differs from its root, plus fail-closed rejection before Module 10 for a
  bifurcated chain, incompatible automatic provenance, and mixed input routes.
  No `raw_data/`, UI, Module 23, activation, or scientific approval is used.

**Deferred next blocks**

- Interactive revision editing, propagation of a consumed chain beyond the
  position runner, and the versioned Module 23 binding remain separate blocks.
- A concrete corrected-mask activation plan remains prohibited until those
  blocks are implemented and synthetically validated under D102.

---

## FUNES Lite source-only release

**Status:** IMPLEMENTED (public source-only release; automatic/provisional)

- The public identity is
  `FUNES — FRET Unified Normalization and Extraction Suite`.
- The standalone source is published on `origin/main` in commit `84a2a28`.
  The release contains source, tests, build instructions, package metadata,
  README, and license; it is not a binary distribution.
- `simple_results` is exclusive to the Lite path and is enabled only through
  its explicit Module 14 exporter opt-in. The reviewed Module 14 workbooks and
  their established sheets remain unchanged.
- The executable and ZIP are generated locally, ignored by Git, and not
  published. No experimental data, analysis outputs, generated images,
  executables, ZIP files, or other binaries are included in the release.
- Publication does not confer scientific approval. FUNES Lite remains an
  automatic, provisional route that is not scientifically validated and does
  not replace the reviewed/activation paths.
