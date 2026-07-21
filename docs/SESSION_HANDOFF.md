# Session Handoff

## Current state

D111 integrates one already validated Module 24 revision chain only at the
Modules 5--13 position-runner boundary. It accepts `RoiRevisionChainResult`,
never artifact paths, and keeps that route mutually exclusive with the existing
single root-revision input. The runner revalidates chain ordering, binds its
terminal result to the fresh exact automatic Module 7/8 provenance, retains the
complete chain on `PositionAnalysisResult`, and routes Modules 10--13 solely
through the terminal geometry audit. Synthetic temporary-path tests cover a
valid two-artifact terminal mask plus fail-closed bifurcated, incompatible, and
mixed-route inputs before Module 10. No `raw_data/`, UI, Module 23, activation,
or scientific approval was used.

D110 adds the isolated fail-closed backend consumer for an explicitly ordered,
non-empty chain of finalized Module 24 artifacts. It replays every artifact
against the same automatic Module 7/8 provenance, requires root then exact
immediate-parent ordering, records each resolved path and SHA-256, and returns
only the terminal replay result for a possible later consumer. It rejects
duplicate paths before replay and rejects an artifact that changes during
validation. It is not wired into Modules 15-23, UI, activation, approval, or
scientific state. Five focused synthetic tests and `compileall` pass; no
`raw_data/` path was accessed.

D109 closes the Module 17/14 provenance presentation after the integrated D108
work. Module 17 preserves the effective `mask_source` and `revision_sha256`
from each completed Module 16 position, and Module 14 writes them in a
separate `roi_provenance` sheet. Automatic rows contain no revision hash;
manual rows contain the exact finalized hash. The D032 value sheets and
numerical results are unchanged.

The three integrated handoffs are now reflected together: Module 24 can
strictly finalize and post-write replay-verify one supplied human draft without
overwriting an existing artifact or changing scientific state; Module 22 can
resolve one explicit, in-scope artifact path per position (mutually exclusive
with its in-memory route), hash it before and after strict replay validation,
and retain path/artifact/revision hashes; and the mixed graph remains preserved
by Module 21 `funes.module21.reviewed_analysis_package.v2`. Focused Module
14/17/21/22 tests pass (27), as does the complete 246-test suite. This close
used no `raw_data/`, UI, Module 23 work, real activation, or scientific
approval.

D107 integrates optional finalized root Module 24 revisions into Module 21
using the new exact package schema
`funes.module21.reviewed_analysis_package.v2` and matching v2 hash domain. The
closed codec now reconstructs mixed automatic/revised acquisitions with the
complete revision, operation trace, edited and measurement masks, automatic
Module 7/8 provenance, shared object identity, and unchanged Modules 10-13
results. D098 v1 is rejected fail-closed rather than silently reinterpreted.
Seven focused synthetic Module 21 tests pass. The block performs no standalone
revision-artifact I/O, replay, export, UI, Module 23 binding, `raw_data/`
access, activation, or scientific approval. `compileall`, 37 focused
Module 15/16/20/21/24 tests, and all 237 tests pass.

D106 propagates D105's optional finalized root Module 24 revision through
Module 20 for any subset of one exact D096 acquisition. It preflights the
complete mapping before the first experiment call, then partitions exact
revision objects by unchanged experiment and position order. Two synthetic
tests, 36 focused Module 15/16/20/24 tests, `compileall`, and all 235 tests pass
at that boundary.

D105 propagates D104's optional finalized root Module 24 revision through
Module 16 for any subset of one exact D089 experiment. Module 16 preflights
scope, type, source-position identity, finalized state, and root-only status
for the complete mapping before its first position call; omitted positions
retain the automatic path. Each exact revision then reaches only its matching
D089-ordered Module 15 call, where D104 replays it against the current
automatic Module 7/8 hashes and Modules 10-13 use only the effective mask. Two
new synthetic tests, 29 focused Module 15/16/24 tests, `compileall`, and all
233 tests pass. No export, persistence/path loading, UI, Module 20-23
propagation, `raw_data` access, activation authority, or scientific approval
was added. The controlling design remains
`docs/MODULE_24_AUDITABLE_ROI_MASK_REVISION_DESIGN.md`.

D101 completes the typed Module 23 activation boundary with six focused
synthetic tests and a complete 214-test suite. It binds one immutable plan and
separate authorization before acquisition access, permits at most one unchanged
D099 call with no retry, and records started/completed/failed receipts with
source and artifact verification. No concrete real plan or activation ID
exists, and no `raw_data/` path was listed, read, or hashed. D100/D101's exact
plan-ID/SHA-256 authorization remains mandatory after the later revision-aware
plan extension.

D099 completes Module 22 as the full reviewed application runner. Given only
caller-supplied acquisition/assignment inputs, an existing strictly validated
D090 snapshot, exact per-position scientific configurations, and a new output
directory, it composes D095-D098 plus D094. D097 still performs the complete
coverage preflight and the runner has no inspection or approval operation. It
publishes ordered experiment workbooks and one complete analysis package
together from private staging, refuses an existing destination, and preserves
the snapshot path/hash plus exact typed stage objects. Five focused synthetic
tests, `compileall`, the 25-test D095-D099 suite, and all 208 tests pass. No
`raw_data/` file was read and no real acquisition, scientific approval, ROI,
mask, profile, parameter, schema, layout, or production dependency changed.

D098 completes Module 21 as strict persistence of one already completed D097
analysis plus every explicit Module 15 configuration. Its versioned ZIP graph
preserves arrays, object sharing, review provenance, metadata, issues, and
configuration without pickle or dynamic imports. Five focused synthetic
tests, `compileall`, and all 203 tests passed at that boundary; persistence
neither reruns analysis nor changes review state.

D097 completes Module 20 as the fail-closed cross-experiment composition of
D093 for one exact D096 acquisition. It requires an explicitly updated D089
orchestrator retaining the exact D088/D044 scopes and one explicit Module 15
scientific configuration per position. It audits every experiment and D046
coverage decision before the first D093 call, then runs once per experiment in
unchanged D095/D096 order while preserving exact pair/result/issue provenance.
Five focused synthetic-TIFF tests, `compileall`, the 42-test focused D089-D097
suite, and the full 198-test suite pass. No `raw_data/` file, scientific
approval, persisted inspection, ROI, mask, profile, parameter, snapshot,
workbook, analysis bundle, or production dependency changed.

D096 completes Module 19 as the fail-closed bridge from one ready D095 load to
fresh experiment-isolated D089 review scopes. It requires exactly one explicit
D088 coverage choice and exact D044 segmentation configuration per loaded
experiment, preserves D095 experiment/position order and exact object identity,
and initializes every D046 ledger without inspections or approval. Five
focused synthetic tests, `compileall`, 27 focused Module 18/19 and D089-D091
tests, and the full 193-test suite pass. No `raw_data/` file, real-data
execution, scientific approval, inspection, ROI, mask, profile, parameter,
snapshot, workbook, analysis bundle, or production dependency changed.

D095 completes Module 18 as a fail-closed acquisition-loading boundary over
existing Modules 1-4. Given one explicit directory and explicit typed
experiment-assignment rules, it discovers TIFF and auxiliary files, associates
recognized SlideBook logs, validates C0/C1 pairs, and assigns experiments once
in dependency order. It retains every typed stage result and unchanged issue;
`assigned_pairs` refuses partial/error-bearing material. Five focused synthetic
TIFF tests, `compileall`, and the full 188-test suite pass. No `raw_data/` file,
scientific approval, review state, analysis, ROI, mask, profile, parameter,
workbook, persisted analysis bundle, or production dependency changed.

D093 completes Module 16 as a fail-closed, deterministic one-experiment
orchestrator over D092. It accepts only the complete set of already assigned,
in-memory pairs for one isolated D089 scope plus one explicit scientific
configuration per position. It validates exact identities, configuration
coverage, and every D046 coverage decision before the first position begins,
then runs in D089 order and returns unchanged in-memory D092 results. Five new
synthetic tests, `compileall`, the 10 focused Module 15/16 tests, and the full
179-test suite pass. It performs no discovery, TIFF reading, approval,
inspection, persistence, export, ROI editing, concurrency, or real-data
activation, and changes no scientific setting or production dependency.

D092 completes the next bounded block after D091 as Module 15: a fail-closed
single-position runner across existing Modules 5-13. It accepts only an
already assigned in-memory `TiffPair`, an explicit `PositionAnalysisConfig`,
and an existing experiment-isolated D089 orchestrator. Required D088 manual
targets must have their own D046 inspection; all other positions must already
be covered. The exact D044/D046 selection and review provenance enter the
configured Module 7 engine and remain attached through the fixed Module 8
labels used by Modules 10-13. The runner creates no inspection or approval,
changes no snapshot, and has no discovery, TIFF-read, export, ROI-edit, or
real-data execution operation. Five focused synthetic tests, `compileall`, and
the full 174-test suite pass. No scientific approval, ROI, mask, profile,
parameter, production dependency, or file under `raw_data/` changed.

D091 completes the next bounded Module 9 block after D090: a snapshot-backed
`ExperimentRoiReviewSession` for repeatable, on-demand review delivery. It
opens the strictly validated D090 state, registers only caller-supplied typed
`TiffPair` plus `RoiFilteringResult` material, reports pending D088 manual
targets and which are available now, exports one D089 viewer, applies one
explicit inspection, and persists the new immutable state. Partial delivery is
allowed; duplicate, unknown, unassigned, and cross-experiment positions fail
closed. The session exposes no approval operation and performs no discovery,
TIFF read, segmentation, downstream analysis, ROI edit, or mask persistence.
Five synthetic tests, the 33 focused Module 7/9 review tests, `compileall`, and
the full 169-test suite pass. No real TIFF, scientific approval, ROI, mask,
profile, or parameter changed.

D090 completes the next bounded Module 9 block after D089: versioned JSON
persistence for the full `ExperimentRoiReviewOrchestrator`. The snapshot
preserves each experiment's exact positions, D088 mode and selected subset,
D044 global selection and overrides, and the entire D046 inspection/approval
ledger including reviewer fields and the pre-approval inspection snapshot. A
canonical payload SHA-256 detects changed or incomplete content, while the
typed loader rejects unknown fields, unsupported schemas, stale provenance,
incoherent approvals, and cross-scope state. Export/load cannot create an
inspection or approval. Five focused tests, the 28 focused Module 7/9 review
tests, `compileall`, and the full 164-test suite pass using synthetic state
only; no TIFF, mask, ROI, profile, parameter, or scientific approval changed.

D089 implements the bounded Module 9 experiment position-review orchestrator.
The preflight audit found that D046 alone cannot safely share one state across
experiments because it drops the experiment when normalizing field keys and
owns one global approval. D089 leaves D046 unchanged and adds an immutable
`ExperimentPositionReview` with one isolated D046 ledger per experiment plus
an `ExperimentRoiReviewOrchestrator` that rejects duplicate scopes and routes
all position operations by exact experiment identity.

Both D088 modes are enforced. `review_all` requires every position to be
manually inspected and cannot approve a remainder. `review_selected` requires
a non-empty proper subset; completing it never approves anything. A later
explicit `approve_remaining(...)` is allowed only after every selected
position has an inspection and while at least one position remains
`unreviewed`. The approval remains inaccessible outside that experiment.
D044 exceptions keep precedence, while D046 inspection notes, reviewer data,
approval snapshots, and selection provenance remain intact.

New orchestrated viewers add the experiment to their JSON, local-storage key,
and downloaded filename. The low-level loader remains compatible with D081-
D087 decisions without an experiment, but the orchestration boundary requires
an exact experiment match. Viewer export is on demand per position, so a
browser never receives one experiment-wide frame bundle; each selected viewer
still provides every C0/C1 timepoint with the unchanged fixed ROI contours.
Seven new tests use only synthetic arrays. The 23 focused review tests,
`compileall`, and the full 159-test suite pass. No real TIFF was read or
segmented, and no ROI, mask, profile, or scientific parameter changed.

D087 accepts the explicit Position 1 Module 9 inspection. Its canonical JSON
hash is `4c696164fcc0fa9d0f3b75cdf36789cc639288a36ff0c36f72de4d397a81ed23`,
and its persisted receipt records `manually_reviewed` with no global approval,
segmentation execution, mask modification, or parameter modification. Together
with D085, both fields currently available under `raw_data/` are now manually
reviewed for `kmeans/provisional_working_kmeans_area32`.

The next pending boundary has been reviewed read-only. Both inspection exports
say only `decision: inspected`; they do not approve the provisional profile for
future uninspected fields or establish representative-field sufficiency. The
next coherent D045/D046 block was an explicit scientific-user decision on
review coverage. No approval receipt was created, and there is no third local
field with which to expand the sample.

D088 subsequently confirms the future review policy. For each experiment, the
user must be able to choose either manual inspection of every position or a
user-selected subset followed by a separate explicit approval for the
remaining positions. The choice and any approval are experiment-scoped and
must not spill into another experiment. Both positions in the current dataset
are already manually reviewed, so it is fully covered without global-policy
acceptance. No current global approval was granted.

D086 exports the requested Module 9 v2 viewer for `Capture 1 + Position 1`
from the verified persisted K-means area-32 labels. The two TIFF hashes and the
recorded label-artifact hash match before export; no segmentation entry point
is called. Reconstructing only the unchanged Module 8 geometry boundary yields
60 source labels, 56 retained labels, and 4 border-rejected labels. The viewer
contains both frames of C0 and C1 plus exactly four static atlas panels; viewer
JSON and JavaScript parse, the four embedded PNG hashes are distinct, and the
HTML hash matches its companion manifest. At D086 the field remained
`unreviewed`, and `Capture_1_Position_1_roi_review.json` was prepared for
browser export only after explicit manual confirmation; D087 later accepted
that export as the manual inspection. Six focused tests and the complete
152-test suite pass. The reproducible script and outputs are under
`scripts/export_module9_capture1_position1.py` and
`outputs/module9_roi_review_capture1_position1/`.

D085 accepts the user-exported Position 2 inspection. Both browser downloads
were byte-identical; their SHA-256 is
`7f4ac58780f832b79185f0989b3d25cdd401317e11e8c6e4a9350784ec4a96f1`.
The canonical decision in the Module 9 output directory strictly matches the
field, label hash, filtering hash, and current global area-32 K-means selection.
Applying it through D046 produces `manually_reviewed`; optional reviewer fields
remain null and no global approval is granted. The adjacent applied-review
receipt preserves the validated result for later reconstruction. Segmentation,
masks, parameters, TIFFs, and label artifacts remain unchanged.

D084 adds a JavaScript-independent all-frame atlas to every Module 9 viewer and
publishes the corrected Position 2 artifact as
`capture1_position2_roi_review_v2.html` to avoid stale local-tab caching. The
atlas contains exactly C0/F0, C0/F1, C1/F0, and C1/F1 as ordinary embedded HTML
images. Viewer JSON and JavaScript parse, six focused tests pass, and the full
152-test suite passes. This display fallback changes no TIFF, ROI, parameter,
geometry status, or review provenance.

D083 fixes Module 9 navigation when a browser denies `localStorage` for a local
HTML file. Draft loading and saving are now best-effort and cannot abort event
handler registration; navigation and review controls continue without browser
storage. The Position 2 viewer was regenerated. Its two raw frames differ in
356,257 C0 pixels and 356,845 C1 pixels, and all four embedded frame PNG hashes
are distinct. Viewer JSON and JavaScript parse, six focused tests pass, and the
complete 152-test suite passes. No ROI, parameter, TIFF, or provenance changed.

D082 exports the requested read-only Module 9 viewer for `Capture 1 + Position
2`. It verifies the documented hashes of both raw TIFFs and the persisted
K-means area-32 `labels.npy`, creates current typed segmentation provenance
without running segmentation, and reconstructs only the missing Module 8
geometry result with the unchanged real-pair validation configuration (minimum
20 pixels, border exclusion). The self-contained viewer has two temporal frames
per channel, 81 source labels, 79 retained labels, and 2 rejected labels.
`outputs/module9_roi_review_capture1_position2/` contains the HTML and manifest;
`scripts/export_module9_capture1_position2.py` reproduces them. Raw TIFFs,
segmentation parameters, and the persisted label artifact remain unchanged.

D081 validates the bounded read-only Module 9 viewer. One self-contained HTML
artifact consumes an existing typed `TiffPair`, `RoiFilteringResult`, and
`SegmentationReviewState`, embeds every C0/C1 temporal frame, and overlays the
exact fixed source labels with accepted, flagged, and rejected Module 8
statuses. Browser-local storage keeps an unfinished draft; an explicit
confirmation exports a strict `funes.module9.roi_review.v1` inspection JSON.
Application verifies the Capture + Position, exact source-label hash, complete
Module 8 filtering hash, and current method/profile/selection source before
calling the immutable D046 `record_inspection(...)` boundary. It cannot grant
global approval, edit a mask, delete an ROI, rerun segmentation, or change a
scientific parameter. Six focused synthetic tests pass and the inline
JavaScript parses with the bundled runtime; the complete 152-test suite also
passes. Automated visual opening of the local file was blocked by the in-app
browser URL policy, so no browser visual review is claimed.

D079 verifies the Module 12-to-13 handoff. Both public Module 13 calculation
boundaries now require a runtime-validated `TemporalIntensityResult`. A
focused synthetic test obtains that object through the typed D078 entry point,
passes the exact instance to a replaceable FRET strategy, and proves that
retained ROI labels `2` and `4` remain unchanged while intentional gaps `1`
and `3` remain absent. Spies confirm that Module 13 performs no TIFF read,
background estimation, QC evaluation, or temporal-intensity extraction. All 9
focused Module 13 tests and the complete 144-test suite pass. The test uses
only in-memory synthetic arrays and reads no TIFF under `raw_data/`.

D078 verifies the Module 8/10/11-to-12 handoff. The integrated path now calls
`extract_filtered_roi_temporal_intensities(...)` with the typed
`RoiFilteringResult` and the existing Module 10 background and Module 11 QC
results. An identity-checking replaceable strategy proves that it receives the
exact `filtered_label_image`, `QuantitativeBackgroundResult`, and
`IntensityQcResult` objects. Rejected label `1` produces no temporal record;
retained label `2` remains `2`, uses the existing channel-specific background
correction, and preserves its matching QC status and reasons. Module 12 records
both upstream method names in its result parameters. All 4 focused Module 12
tests and the complete 142-test suite pass. Only synthetic arrays and temporary
synthetic TIFF fixtures were used; no TIFF under `raw_data/` was read or rerun
and the focused D078 handoff test executed no segmentation engine or reopened
parameter.

D077 verifies the Module 8/10-to-11 handoff. The integrated path now calls
`evaluate_filtered_roi_intensity_qc(...)` with the typed `RoiFilteringResult`
and the existing `QuantitativeBackgroundResult`. The helper passes the exact
`filtered_label_image` and background-result objects to the replaceable QC
strategy. A focused synthetic test proves that rejected label `1` produces no
QC record, retained label `2` is not renumbered, and its corrected C0/C1 means
use the channel-specific Module 10 background values. Module 11 also records
the background method in its result parameters and ROI-frame metrics. All 5
focused Module 11 tests and the complete 141-test suite pass. Only synthetic
arrays and temporary synthetic TIFF fixtures were used; no TIFF under
`raw_data/` was read or rerun and no segmentation engine or parameter was
reopened.

D076 verifies the Module 8-to-10 handoff. The integrated path passes the exact
`RoiFilteringResult.filtered_label_image` to quantitative background
estimation. A focused synthetic test proves that a geometrically rejected
label becomes eligible non-ROI background, a retained label remains excluded
without renumbering, and the upstream D074 provisional area-32 provenance is
unchanged. All 15 focused Module 8/10 tests and the complete 140-test suite
pass. No segmentation engine or real TIFF under `raw_data/` was run; TIFFs
used elsewhere by the suite were temporary synthetic fixtures.

D075 closes the typed Module 7-to-8 handoff. Module 8 now exposes
`filter_segmentation_rois(SegmentationResult, ...)`, consumes the exact
read-only `label_image`, and retains the complete source result as provenance.
Geometric rejection zeros only the rejected supports and never renumbers the
remaining labels. The integrated validation path uses this typed entry point;
the older array-only helper remains available for synthetic masks and
compatibility without claiming Module 7 provenance. Synthetic focused tests
cover the provisional K-means area-32 identity and a deliberate label gap. All
8 focused Module 8 tests and the complete 139-test suite pass, using only
synthetic arrays and temporary synthetic TIFF fixtures. No TIFF under
`raw_data/` was read or rerun, no D071 artifact was changed, and no Module 7
parameter or default was reopened.

D074 records the current Module 7 handoff decision. The global working
selection is now `kmeans / provisional_working_kmeans_area32`, which retains
all K-means benchmark parameters except
`minimum_object_area_pixels = 32`. It is explicitly provisional: faint cells
may be omitted, some cells may have only partial coverage, and touching cells
may remain one joint ROI. It is sufficient to continue development but is not
a claim of universal accuracy, sample sufficiency, representative coverage,
or complete segmentation. The D071 local-background variant was not adopted,
no parameter search or real-TIFF rerun occurred, and D046 was not used.

The stable Module 7 output is `SegmentationResult`: a read-only 2D `int32`
label image matching the prepared first-frame shape, with background `0`,
canonical consecutive positive labels `1..roi_count`, complete engine/profile
and parameter provenance, and structured issues. Module 8 can consume
`label_image` directly, and the same label supports remain fixed for both
channels and all temporal frames downstream.

The D074 validation ran 37 focused Module 7 tests and the complete 138-test
suite successfully. Only synthetic arrays and temporary synthetic TIFF
fixtures were used; nothing under `raw_data/` was read or rerun.

D061 records that K-means area=32 is not yet acceptable on the two reviewed
fields because P2-R1 still contains wholly omitted cells and P1-R4 still has
unaccepted complete-cell coverage. The 32-to-16 area extension adds no support
in P2-R1 and leaves P1-R4 unchanged, so minimum area is not being tested again.

D062 defines and D063 now implements the causal extension for the remaining
K-means foreground/intensity hypothesis. The implementation adds the single
field-relative relaxation candidate, keeps area fixed at 32 and every other
K-means setting unchanged, exposes the causal trace, and enforces an exact
two-field review-package contract using saved K area-32 masks as references.
Six synthetic tests pass, including a synthetic exactly-two-call package.
The design and implementation boundary are recorded in
`docs/MODULE_7_KMEANS_FOREGROUND_CAUSAL_EXTENSION_DESIGN.md`.

D064 records the explicitly authorized real execution. Preflight verified both
C1 source-TIFF hashes and both saved K area-32 reference hashes against the
earlier manifest, an exact two-call P1/P2 plan, relaxation `0.5`, and fixed area
`32`. Exactly those two calls were made; no area 16, 32, or 64 variant was
rerun. The new immutable package is
`outputs/module7_kmeans_foreground_causal_review_20260718/`.

D065 records the completed scientific review. The user confirmed that the
relaxed foreground boundary contributes in both P1-R4 and P2-R1, but that the
candidate is not acceptable finally. P1-R4 gains cellular support and expanded
border-object coverage while also showing a small isolated nonspecific patch.
P2-R1 recovers several omitted cellular peripheries or bodies but still leaves
dim bodies without ROIs, so its classification is contribution but not
sufficient. Complete-field review finds localized nonspecific expansion and
possible bridging, not a field-wide background carpet. The `0.5` relaxation is
not approved or registered, the global baseline is unchanged, and D046 remains
unused. The immutable D064 package and its manifest-listed blank observation
CSV remain unchanged; the review is preserved in
`docs/MODULE_7_D064_SCIENTIFIC_REVIEW.md`.

D066 closes the current K-means foreground-boundary causal branch without
another segmentation execution. Because the relaxation is monotonic, a value
below `0.5` cannot recover bodies still omitted at `0.5`, while a value above
`0.5` cannot remove the nonspecific support or connections already exposed at
`0.5`. No further value on this scalar axis is therefore a justified single
causal step. This does not reject K-means generally; any future K-means work
would need a separately justified mechanism and a new causal design.

D067 chooses formulation of that new K-means causal mechanism as the next
Module 7 design block instead of immediately reopening the unchanged K-means
versus Marker Watershed comparison. The saved comparison has already shown
that Marker Watershed marker-distance changes only partition an insufficient
support, its doubtful splits remain joint ROI, and its threshold `0.8`
extension adds no support in P2-R1 or coverage of the saved K area-32 confirmed
supports. The future design must be outside the monotonic global-boundary
branch, use a spatially conditional or locally adaptive hypothesis, and
distinguish recovery of wholly omitted cells from expansion of already
detected objects. D067 defines no candidate and authorizes no implementation
or segmentation.

D068 now completes that design block. It defines exactly one diagnostic mode,
`foreground_spatial_conditioning = local_background_p20`, while leaving the
global K-means fit and boundary, identity preprocessing, seed, morphology, and
area 32 controls fixed. The candidate lowers the baseline boundary only by a
negative local P20 offset, using one predeclared field-relative, reflect-padded
window rule, and unions the result with unchanged K-means raw support. It does
not enable D062's `0.5` relaxation. This spatial threshold map is not another
point on the closed global scalar axis.

The required trace distinguishes detached, single-anchor, and multi-anchor raw
proposals and compares final labels with the immutable area-32 labels as de
novo, expansion, carried, or bridge candidates. Those are geometric relations,
not cell classifications: only explicit human review may identify a wholly
omitted cell, cellular completion, nonspecific addition, or a D051 joint/bridge
outcome. The detailed design is
`docs/MODULE_7_KMEANS_LOCAL_BACKGROUND_CAUSAL_DESIGN.md`. D068 authorizes no
implementation, test execution, segmentation, artifact generation, profile,
baseline change, D046 use, or sufficiency/representativeness inference.

D069 records the later explicit authorization to implement that exact rule and
trace with synthetic arrays only. The implementation adds one unregistered
`local_background_p20` mode-switch candidate, exact NumPy-linear P20 using the
field-relative reflected window, and an immutable trace from K-means fit through
final topology. It retains area 32, relaxation `0.0`, and all other controls;
requires the supplied reference labels to match the unchanged control exactly;
and keeps detached/single-anchor/multi-anchor plus de novo/expansion/carried/
bridge classes purely geometric. Five focused synthetic tests and the full
131-test suite pass. No real TIFF was read or segmented, no artifact or profile
was generated, the global baseline is unchanged, D046 was not used, and real
execution remains unauthorized.

D070 confirms that real execution must first receive its own reviewed
authorization design. D071 now supplies that design but does not activate it.
It fixes one plan,
`module7_kmeans_local_background_real_review_d071`, for exactly two later
candidate calls in P1/P2 order, with the current C1 source hashes, prepared
first-frame hashes, saved area-32 reference hashes, unchanged D068/D069
controls, fail-closed preflight, no retries, incomplete-run isolation, and an
immutable review package. The full contract is
`docs/MODULE_7_KMEANS_LOCAL_BACKGROUND_REAL_EXECUTION_AUTHORIZATION_DESIGN.md`.

D072 now completes that implementation-only prerequisite. The typed package
boundary fixes the exact real identities, separates synthetic verification
from authorized real-review scope, completes every preflight check before the
first call, counts started and completed calls, never retries, isolates an
incomplete attempt, verifies immutable inputs and generated artifacts
postflight, and publishes only after exactly two successful calls. The public
D069 runner remains synthetic-only and cannot accept a package execution
scope. Five new tests use only small synthetic arrays, synthetic source bytes,
temporary reference arrays, and temporary publication paths.

During the D072 implementation-only block, no real TIFF was read or segmented,
no real-data package was created, and the declared D071 destination remained
absent. A later separately authorized execution created that package; D073
subsequently verified it read-only and recorded bounded human observations.
Those events do not make the D071 variant part of the D074 working profile.

Descriptively, Position 1 has 84 candidate labels / 12,475 foreground pixels
and adds 5,308 raw-selection, 5,336 post-morphology, and 5,215 final pixels
relative to its saved area-32 reference. P1-R4 contains 133 / 123 / 111 added
pixels at those stages. Position 2 has 106 candidate labels / 16,504
foreground pixels and adds 7,153 / 7,325 / 7,317 pixels; P2-R1 contains 423 /
427 / 417 additions. Neither field removes saved-reference final support, and
neither focused comparison records post-morphology or final removals. These are
unclassified mask facts, not a causal, biological, sufficiency,
representativeness, or acceptability conclusion by themselves. D065 supplies
the later human classification without changing those measurements; no profile
was registered, no baseline changed, and D046 was not used.

Module 7 now includes the D044 five-engine registry and baseline profiles, the
D045/D046 immutable representative-field review/global-approval backend, and
the D047 explicit OFAT parameter-benchmark infrastructure. D047 materializes 36
immutable baseline/candidate variants and can execute one explicitly selected
variant for one identified prepared first frame while returning descriptive
mask geometry. It registers no new production profiles, performs no automatic
ranking or selection, and leaves the validated review backend unchanged.

D048 now adds the static artifact block. The explicit selection contains
`Capture 1 + Position 1/2` and all eight K-means D047 variants, yielding 16
runs with NPY labels, SVG overlays, PNG previews, descriptive CSV, blank human
observation rows, an HTML index, and a SHA-256 manifest. This does not assess
sample sufficiency, classify or rank variants, approve a profile, or use the
D046 ledger. Scientific whole-cell observations are still pending. No
`strict`, `medium`, or `permissive` profile is registered or approved.

D049 is corrected: Cellpose CP-SAM was withdrawn as the next complete block and
deferred until a separate session performed exactly one explicitly selected
timed test and defined an acceptable operational limit. No Cellpose dependency
was installed and no Cellpose candidate was executed in that D049 block.

D050 now completes that separate operational check. Exactly one unchanged D047
run was executed: `cellpose_cpsam / benchmark_baseline` on `Capture 1 +
Position 1`. The cold-cache engine call took `3003.7913557` seconds (50 minutes
3.791 seconds), including the initial 1.15 GB weight download inside model
construction. No warm-cache repeat, additional field, or additional variant was
run. Before any complete Cellpose block can be considered under the same 600 x
600 CPU configuration, its conservative declared projection must be no more
than 12 engine-hours (`run_count x 3003.7913557 <= 43,200`), permitting at most
14 declared runs. No complete block is selected or authorized.

The completed next block explicitly contains `Capture 1 + Position 1/2` and
all nine unchanged Marker Watershed D047 variants, yielding 18 runs with NPY
labels, SVG overlays, PNG previews, descriptive CSV, blank human-observation
fields, selection/provenance, an HTML index, and a SHA-256 manifest. Per-run
segmentation-engine times are recorded only as operational information. The
block does not assess sample sufficiency, classify or rank variants, approve a
profile, change the global K-means baseline, or use or modify D046.

D042 now confirms the core workflow: whole-cell-shaped fixed ROI, average
intensity from both channels at each timepoint, C0/C1, and Excel export. D043
confirms that average intensity means the ROI arithmetic mean after background
subtraction. Module 13 is corrected and `VALIDATED`: the formula is fixed as
C0/C1 independently from donor/FRET provenance, and raw and corrected means are
preserved separately.

Module 14 exporter is implemented and validated. `docs/MODULE_PLAN.md` marks
Module 14 as `VALIDATED`.

The selected follow-up validation is complete. A focused configurable harness
now reads one explicitly selected real C0/C1 pair, wires the available Modules
1-8 and 10-13 in memory, constructs `Module14PositionExport`, and generates the
Module 14 workbook. It is intentionally not a general pipeline runner.

The requested static Module 9 substitute is also implemented and reviewed for
the same pair. D081 later validates a separate read-only interactive viewer;
ROI deletion and mask editing remain deferred.

A complete static visual validation report is now also generated for
`Capture 1 + Position 1`. It connects the first frames and each relevant module
boundary to background, intensity, saturation, and ratio diagnostics, while
preserving the D039 profile unchanged. Details are in
`docs/CAPTURE1_POSITION1_STATIC_VISUAL_VALIDATION.md`.
Its corrected ratio sections and companions have been regenerated; the former
C1/C0 distribution and interpretation remain explicitly superseded.

## Decisions saved

- Use one `.xlsx` workbook file per experiment.
- In each value sheet, rows are elapsed-time timepoints.
- Each ROI is one column in the main value matrix.
- Row 6 displays the ROI label, for example `ROI-001`.
- Row 7 displays the abbreviated full ROI identity as `cN/pN/rN`, for example
  `c1/p1/r1`, `c1/p1/r2`, and `c1/p2/r1`.
- Separate measurement views into separate sheets:
  `ratio`, `r_over_r0`, `delta_r_over_r0`, `donor_corrected`,
  `fret_corrected`, and `qc_status`.
- Use blue empty spacer columns between positions.
- Use double peach empty spacer columns between captures.
- Preserve metadata, parameters, QC statuses, exclusion reasons, structured
  issues, and long/tidy audit data as secondary sheets inside the same
  workbook.
- Do not add a production spreadsheet dependency for the first exporter; the
  implementation writes the required Office Open XML package using the Python
  standard library.
- D034 records the audit-sheet readability refinement: keep the D032 value
  sheet structure unchanged, but use semantic widths for audit and long/tidy
  sheets so traceability fields remain readable.
- D039 records the real-pair validation boundary and requires Module 14 to use
  `frame_index / index` when measured frame times are unknown.
- D040 records the static overlay boundary and the conclusion that the D039
  placeholder segmentation is not approved for production.
- D041 records the full-chain static report boundary, its audit companions, and
  the rule that diagnostic sensitivity comparisons cannot change production
  parameters.
- D042 records the core manual-workflow target, whole-cell ROI requirement, and
  confirmed C0/C1 numerator/denominator order. It supersedes the prior C1/C0
  ratio outputs and interpretation.
- D043 records the confirmed background-corrected ROI mean, the fixed C0/C1
  Module 13 contract, preservation of raw/corrected means, and regenerated
  diagnostic range.
- D044 records the five-engine registry, global K-means baseline default,
  per-field override, reproducibility provenance, and optional lazy CP-SAM.
- D045 and D046 record representative-field sampling, explicit global approval,
  and the immutable review-ledger backend and status precedence.
- D047 records the explicit 36-run OFAT grid, ephemeral non-profile candidates,
  descriptive-only summaries, and the prohibition on automatic ranking,
  selection, approval, or Cellpose fallback.
- D048 records explicit field/variant review plans, unclassified static
  artifacts, exact-label and hash provenance, and the first two-field/eight-
  variant K-means package without a sufficiency or profile conclusion.
- Corrected D049 defers a complete Cellpose CP-SAM block until one separate
  timed test and an acceptable operational limit are defined, and records the
  completed two-field/nine-variant Marker Watershed package without sufficiency
  inference, classification, ranking, profile approval, or D046 changes.
- D050 records the one completed cold-cache Cellpose baseline call, its
  engine-only operational duration, and the 12-engine-hour gate required before
  a complete block may be considered under the same CPU/600 x 600 conditions.
  It does not authorize a block or make a scientific Cellpose conclusion.
- D064 records the exact two-call real D063 execution, its verified immutable
  review package, descriptive mask changes, and the requirement to stop before
  human causal or acceptability classification.
- D065 records the later scientific confirmation that foreground selection
  contributes in both focused regions but the `0.5` relaxation is insufficient
  and not acceptable on these two fields.
- D066 closes the monotonic global foreground-boundary relaxation branch.
- D067 selects a new, separately justified K-means causal-mechanism design as
  the next block and defers reopening the unchanged K-means/Marker Watershed
  comparison until genuinely new evidence exists.
- D068 fixes the exact local-P20/window design, and D069 implements only that
  candidate and immutable trace with synthetic verification. Real execution,
  profile registration, sufficiency, and representativeness remain outside the
  completed block.

## Real-pair validation completed

The harness processed `Capture 1 + Position 1` from `raw_data/`. C1 was selected
for segmentation; the validation-only percentile engine produced 58 connected
components, and geometry filtering retained 36 while rejecting 22. The run
created 144 temporal-intensity records, 72 Module 13 records, and one 15-sheet
workbook. The regenerated corrected-mean C0/C1 values range from 0.0921 to
0.3606. All provisional scientific settings are recorded with a structured
non-production warning.

The first render exposed that unknown times were being labeled as seconds. The
exporter now displays `frame_index / index` unless every exported frame has a
known `time_seconds`. The detailed record is
`docs/MODULE_14_REAL_PAIR_VALIDATION.md`.

## Static ROI overlay review completed

The first C1 frame now has an auditable SVG overlay and a PNG view. Both show
all 58 original labels: 36 retained and 22 rejected. Retained contours are
solid cyan; rejected contours are dashed coral; the current profile produced
no flagged labels. The visualization does not renumber or modify masks.

Visual review shows predominantly bright puncta and compact fragments rather
than consistent whole-cell outlines. Retained area has median 60.5 pixels, and
25 of 36 retained labels are at or below 100 pixels. This evidence does not
approve the placeholder engine, percentile, area minimum, or border policy.
Details are in `docs/MODULE_9_STATIC_ROI_OVERLAY_VALIDATION.md`.

## Static full-chain validation completed

The report distinguishes 356,400 never-segmented pixels from 22 geometrically
rejected components and from zero intensity/saturation exclusions. The zero QC
exclusion count reflects disabled thresholds rather than approved signal
quality. It preserves all 58 component labels in `roi_audit.csv`, all 72
retained ROI-frame ratio observations in `roi_measurements.csv`, and source and
artifact hashes in `audit_manifest.json`.

The saved 2.7729-10.8600 values are inverted C1/C0 results and their prior
interpretation remains superseded. Module 13 and both artifacts were
regenerated: corrected-mean C0/C1 is 0.092081-0.360629 with median 0.1990;
raw-mean C0/C1 remains separately auditable at approximately 0.1184-0.3675.
The P99 visual evidence remains valid: it selects sparse C1-bright puncta and
clips many visible cells rather than outlining complete cell shapes. No
production segmentation threshold was approved.

## Implemented and validation artifacts

- `src/funes/module14_exporter.py`
- `src/funes/real_data_validation.py`
- `scripts/validate_real_pair_to_module14.py`
- `tests/test_module14_exporter.py`
- `tests/test_real_data_validation.py`
- `src/funes/static_roi_overlay.py`
- `scripts/generate_real_pair_roi_overlay.py`
- `tests/test_static_roi_overlay.py`
- `src/funes/static_validation_charts.py`
- `src/funes/static_validation_report.py`
- `src/funes/segmentation_benchmark.py`
- `scripts/generate_static_visual_validation_report.py`
- `tests/test_static_validation_report.py`
- `tests/test_segmentation_benchmark.py`
- `src/funes/segmentation_benchmark_artifacts.py`
- `src/funes/segmentation_benchmark_review.py`
- `src/funes/segmentation_benchmark_review_package.py`
- `src/funes/segmentation_kmeans_causal.py`
- `src/funes/segmentation_kmeans_causal_artifacts.py`
- `src/funes/segmentation_kmeans_causal_review.py`
- `src/funes/segmentation_kmeans_local_background.py`
- `scripts/generate_module7_ofat_review.py`
- `tests/test_segmentation_benchmark_review.py`
- `tests/test_segmentation_kmeans_causal.py`
- `tests/test_segmentation_kmeans_local_background.py`
- `docs/MODULE_7_OFAT_VISUAL_REVIEW_ARTIFACTS.md`
- `docs/MODULE_7_OFAT_NEXT_VISUAL_REVIEW_SELECTION.md`
- `docs/MODULE_7_OFAT_MARKER_WATERSHED_VISUAL_REVIEW_ARTIFACTS.md`
- `src/funes/__init__.py`
- `docs/MODULE_PLAN.md`
- `docs/DECISIONS.md`
- `docs/SESSION_HANDOFF.md`
- `outputs/module14_upstream_validation_20260713/`
- `outputs/module14_real_pair_validation_20260713/`
- `outputs/module9_static_roi_overlay_20260713/`
- `outputs/capture1_position1_static_validation_20260713/`
- `outputs/module7_ofat_review_20260714_kmeans/`
- `outputs/module7_ofat_review_20260714_marker_watershed/`
- `outputs/module7_cellpose_timed_test_20260714/`
- `outputs/module7_kmeans_foreground_causal_review_20260718/`

The representative validation output contains two workbooks:

- `outputs/module14_upstream_validation_20260713/workbooks/exp_a_forskolin_pilot.xlsx`
- `outputs/module14_upstream_validation_20260713/workbooks/exp_b_vehicle_control.xlsx`

Each representative workbook has 15 sheets:

- `ratio`
- `r_over_r0`
- `delta_r_over_r0`
- `donor_corrected`
- `fret_corrected`
- `qc_status`
- `overview`
- `fret_long`
- `intensity_long`
- `roi_summary`
- `background_long`
- `qc_long`
- `metadata`
- `parameters`
- `issues`

The latest check confirmed:

- The real pair reaches Module 14 without a saved upstream bundle.
- The real validation workbook imports and all 15 sheets render successfully.
- The workbook has zero matches for spreadsheet error tokens such as `#REF!`,
  `#DIV/0!`, `#VALUE!`, `#NAME?`, and `#N/A`.
- Module 13 and related exporter/report/harness tests pass.
- The synthetic integration test verifies that source TIFF bytes remain
  unchanged.
- The real SVG parses as XML, contains 58 status-tagged ROI groups, and the PNG
  view received a visual review at native 600 x 600 resolution.
- The 12 focused D047/D048 tests pass with operational-timing provenance
  checks.
- The full test suite passes on 198 tests, including the six D063 tests, five
  D069 local-background synthetic tests, and five D072 package-boundary tests.
- The D064 real package contains exactly two runs and 24 manifest-listed
  artifacts. All artifact, source, and saved-reference SHA-256 values match;
  every required NPY/JSON/SVG/PNG/CSV/HTML artifact is present, both observation
  rows remain blank, and the two complete-field PNGs render at 600 x 600.
- The Marker Watershed package contains 18 runs and 58 hashed artifacts, with
  no hash mismatch and no nonblank human-observation field. Its engine-only
  operational time totaled 2.865647 seconds across the 18 runs.
- The Cellpose timed-test package contains exactly one field and one unchanged
  D047 variant. Its cold-cache engine-only operational time is
  `3003.7913557` seconds; its source and seven listed artifacts have matching
  SHA-256 hashes, and its one human-observation row remains blank.

## D094 reviewed experiment workbook export completed

- Module 17 consumes only one already completed in-memory D093
  `ExperimentAnalysisResult`.
- It adapts each D089-ordered position to `Module14PositionExport` using the
  exact existing pair and Module 8/10/11/12/13 result objects, then calls the
  existing D032 exporter exactly once.
- The returned immutable result retains the source Module 16 result, exact
  position-export inputs, Module 14 result, and single workbook path.
- Four focused synthetic tests, the 14 focused Module 15/16/17 tests,
  `compileall`, and all 183 tests pass. No file under `raw_data/` was read and
  no approval, review snapshot, ROI, mask, profile, parameter, layout, or
  production dependency changed.

## Pending tasks

- D096 supplies fresh D089 scopes from complete D095 material and explicit
  per-experiment D088/D044 configuration. It does not record an inspection or
  approval, choose any Module 15 scientific configuration, run D093/D094,
  persist review or analysis results, or activate a real acquisition. D097 now
  coordinates only already covered experiments through D093, without adding
  any of those omitted decisions or side effects.

- D089-D091 complete bounded experiment-scoped orchestration, durable
  review-state persistence, and a snapshot-backed on-demand review session.
  They do not grant any real-data approval or load acquisition material
  automatically; a real acquisition must still supply its assigned experiment
  positions, chosen mode, existing typed pairs/filtering results, and explicit
  decisions.
- Manual ROI deletion, drawing/editing, changed-mask persistence, new-label
  creation, and explicit real-data activation remain separate future tasks.
  D100 defines the activation boundary but implements and authorizes nothing;
  D099 has no default acquisition path and cannot create D090 coverage.
- D069, the D071 real-execution authorization design, and the D072 typed
  package boundary with synthetic verification are complete. Do not treat
  P20/window scale as a production profile. Before any real call, the
  scientific user must still provide the exact later activation statement
  defined by D071. Do not infer coverage or scientific acceptability from the
  synthetic tests or the design.
- Any later scientific visual observations for the Marker Watershed package
  must be entered explicitly without treating the two fields as sufficient or
  selecting a preferred variant automatically.
- Cellpose CP-SAM scientific evaluation remains deferred. The required single
  timed test and 12-engine-hour operational gate are complete, but no complete
  block is selected or authorized and no review coverage may be inferred.
- Do not interpret real-data scientific outputs as production-ready until
  acquisition profiles and pending scientific decisions are resolved.
- Production acquisition profiles still need scientific decisions for FRET
  channel mapping, baseline windows, saturation thresholds, low-signal
  thresholds, and background method.
- New auxiliary metadata families still need explicit association rules;
  the inspected SlideBook `.log` family is already resolved by D036.
- D094 provides the reviewed one-experiment workbook-export bridge; D095-D098
  provide loading, scope construction, complete acquisition analysis, and
  strict analysis-package persistence. D099 now composes them into one complete
  reviewed application run with ordered multi-experiment workbooks. D100 fixes
  the later activation contract: implement it synthetically first, review a
  concrete plan, then require an explicit statement naming its ID and hash.
- Any later proposal for a complete Cellpose block must declare its exact field
  and unchanged D047 variant count, satisfy the D050 12-engine-hour projection
  under the same CPU/600 x 600 conditions, and receive separate authorization.
  Do not tune thresholds, infer scientific feasibility, or add Cellpose as a
  production dependency.
- Confirm the SlideBook channel-role interpretation and identify the camera,
  optical-correction, and biological-context information needed to interpret
  the provisional absolute ratio values.

## Suggested next-session prompt

Continúa desde D111 solo con un bloque futuro explícitamente autorizado; no
propagues cadenas más allá del runner de posición, ni inicies UI, Module 23,
activación real, `raw_data` ni aprobación científica.
