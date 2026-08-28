# Decision Log

This file records confirmed scientific and architectural decisions. Add dates when practical. Do not rewrite prior decisions silently; append a superseding decision with a reason.

## Confirmed decisions

### D001 — Primary implementation language

Use Python.

### D002 — Initial input format

Start with TIFF exports rather than direct `.sld` reading.

### D003 — Temporal interpretation

Every TIFF contains a temporal sequence. Even if TIFF/SlideBook metadata labels the internal images as Z planes or another axis, the ordered images are treated as temporal frames for this project.

### D004 — Analysis hierarchy

Use:

`Experiment > Capture > Position > C0/C1 > temporal frames`

The `Experiment` label is assigned above Capture and may group several captures and positions from the same batch.

### D005 — Metadata preservation

Preserve filename-derived `XY`, `Z`, and `T`, raw filenames, file paths, TIFF metadata, and associated text metadata even when they are not used directly in analysis.

### D006 — ROI temporal behavior

Segment on the first temporal frame and use fixed ROIs for the complete C0/C1 sequence.

### D007 — Segmentation channel

Choose the segmentation channel automatically using a robust signal comparison between first-frame C0 and C1. C1 is often brighter but must not be hard-coded.

### D008 — ROI sizes

Minimum and maximum ROI size must be configurable because objectives, camera settings, pixel calibration, and cell types vary.

### D009 — Camera saturation

Saturation limits vary by camera mode and must not be inferred only from TIFF dtype. Support metadata or camera profiles.

### D010 — Low-signal logic

Low-signal filtering must be background-aware rather than relying only on a universal absolute intensity.

### D011 — Drift

Automatic drift correction is deferred. A future quality-control step may compare early and late frames and flag cells or fields.

### D012 — ROI review interface

Interactive visualization and ROI deletion are desirable but optional. The initial pipeline may omit the interface.

### D013 — Modularity

Implement small independent modules with stable interfaces. Work module by module in separate sessions.

### D014 — Export

Do not finalize Module 14 until example Excel outputs have been generated and reviewed.

### D015 - Initial Python scaffold (2026-07-11)

Use a `src/` layout package named `funes`, require Python 3.10 or newer, and use
the standard-library `unittest` runner for the initial scaffold. Add no
production dependencies until a later module requires them and the decision is
recorded.

### D016 - Module 1 filename discovery and parsing (2026-07-11)

Discover only `.tif` and `.tiff` files for Module 1, matching extensions
case-insensitively. Parse representative SlideBook export names with a
conservative pattern for `Capture`, `Position`, `XY`, `Z`, `T`, and `C0`/`C1`.
Report malformed TIFF candidate names and duplicate parsed identities as
structured issues. Preserve the original filename and a resolved source path
without opening image pixels.

### D017 - Module 2 TIFF reader backend and provisional frame normalization (2026-07-11)

Use `tifffile` as the production TIFF-reading backend because Module 2 must
read multipage TIFF image data and preserve TIFF tags/series metadata. Until
representative SlideBook exports are inspected, normalize 2D TIFF data as one
temporal frame and 3D TIFF data as ordered temporal frames on the first axis.
Reject higher-dimensional shapes with a structured error rather than guessing
biological or acquisition axes.

### D018 - Module 3 auxiliary metadata preservation boundary (2026-07-11)

Discover and read auxiliary `.txt` metadata files independently from TIFF
discovery. Preserve raw text, source provenance, duplicate key/value lines, and
unparsed non-empty lines. Parse only simple non-empty `key: value` and
`key = value` lines. Do not assign auxiliary metadata to experiments, captures,
positions, or TIFF pairs in Module 3.

### D019 - Module 4 explicit experiment assignment rules (2026-07-11)

Assign experiments from explicit configuration rules applied to validated TIFF
pairs. Each rule names an experiment and one or more Capture labels, with
optional Position labels to narrow the scope. Treat missing assignments and
overlapping matching rules as structured errors. Preserve auxiliary metadata in
the assignment result, but do not infer experiment labels from text metadata
until reliable association rules are defined.

### D020 - Module 5 first-frame segmentation-channel metric (2026-07-11)

Select the segmentation channel from the first temporal frame using robust
contrast, defined as a configurable high signal percentile minus a configurable
background percentile. Preserve C0 and C1 metric values, the selected channel,
and the selection method. Treat close scores and low-contrast fields as
structured warnings, and support an explicit manual override while retaining
the computed metrics for auditability.

### D021 - Module 6 segmentation-only preprocessing boundary (2026-07-11)

Define preliminary segmentation preprocessing as a replaceable strategy that
returns a processed first frame plus method, parameters, issues, and any
preliminary background estimate. Keep these estimates explicitly scoped to
segmentation preprocessing and separate from future quantitative background
correction. Use identity preprocessing as the conservative default until
representative images are inspected, while providing a configurable percentile
background subtraction strategy for tests and provisional segmentation-only
experiments.

### D022 - Module 7 initial segmentation engine boundary (2026-07-11)

Define segmentation engines behind a replaceable interface that accepts a
prepared non-empty 2D first-frame image and returns a labeled integer ROI mask
plus engine name, version, model, parameters, and structured issues. Use a
deterministic percentile-threshold connected-components engine as the initial
test/provisional implementation. Do not install Cellpose until representative
images justify the production model choice.

### D023 - Module 8 geometric ROI filtering boundary (2026-07-11)

Filter labeled segmentation masks with a small geometry module that treats each
positive integer label as one ROI and preserves original label numbers in the
filtered mask. Configure minimum and maximum area limits in pixels for the
initial implementation. Record area, bounding box, centroid, border-touching
status, geometric status, and structured reasons for every flagged or rejected
ROI. Border-touching handling is configurable as accept, flag, or exclude, with
flagging as the conservative default until acquisition profiles define stricter
behavior.

### D024 - Module 10 quantitative background boundary (2026-07-11)

Define quantitative background estimation as a replaceable strategy that returns
one auditable estimate per channel and temporal frame for a validated C0/C1
TIFF pair. Keep this module separate from segmentation-only preprocessing. Use
a configurable percentile estimator as the initial implementation, with explicit
pixel-source selection between non-ROI pixels and full-frame pixels. Preserve
method name, parameters, pixel counts/fractions, summary diagnostics, caller
context, and structured issues when estimates cannot be produced.

### D025 - Module 11 intensity quality-control boundary (2026-07-12)

Define intensity quality control as a replaceable strategy that operates on a
validated C0/C1 TIFF pair, fixed ROI label image, quantitative background
estimates, and explicit QC configuration. Require an explicit camera saturation
profile for the meaningful saturation threshold rather than inferring it from
TIFF dtype. Preserve saturated-pixel counts/fractions and background-aware
low-signal SNR metrics separately at field-frame, ROI-frame, ROI, and field
decision scopes. Keep production saturation fractions, low-signal thresholds,
and exclusion policy configurable until representative acquisition profiles are
reviewed.

### D026 - Module 12 temporal intensity extraction boundary (2026-07-12)

Define temporal intensity extraction as a replaceable strategy that applies a
fixed ROI label image to every temporal frame in both C0 and C1 after pair
validation. Emit one auditable measurement record per ROI, channel, and frame,
including raw mean, raw median, ROI area, quantitative background value, and
background-corrected mean and median when background is available. Preserve
matching Module 11 QC statuses and reasons by scope, but do not calculate FRET
ratios, normalize values, or map C0/C1 to donor/FRET roles in Module 12.

### D027 - Module 13 FRET calculation boundary (2026-07-12)

Define FRET calculation as a replaceable strategy that consumes Module 12
temporal intensity records rather than TIFF image data. Require an explicit
configuration mapping C0/C1 to donor/FRET roles and explicit baseline frame
indices. Calculate FRET/donor ratio, R/R0, and delta R/R0 from configurable
background-corrected mean or median values. Preserve the mapping, baseline
definition, input QC statuses and reasons, missing values, excluded-frame
handling policy, and structured issues for missing paired measurements or
unavailable baselines. Do not implement export formatting in Module 13.

### D028 - Module 14 examples-first planning boundary (2026-07-12)

Plan and compare example Module 14 workbook layouts before implementing export
code or finalizing the workbook format. The examples should represent current
upstream outputs from Modules 8, 10, 11, 12, and 13, including metadata,
parameters, QC statuses, exclusion reasons, and structured issues. Candidate
layouts may include analysis-first long sheets, human-review wide ROI sheets,
and lighter workbooks paired with companion CSV files, but none of these
variants is yet selected as final.

### D029 - Module 14 synthetic review examples generated (2026-07-12)

Generate non-final synthetic Excel examples for Module 14 visual review using
the planning variants A, B, and C. Keep the examples clearly marked as
non-final, and use them only to compare organization, traceability, formatting,
and review ergonomics. Do not treat any generated workbook or companion CSV
candidate as the final export specification until the examples are reviewed and
a separate decision is recorded.

### D030 - Module 14 review direction: wide ROI layout (2026-07-12)

Use the human-review wide layout as the basis for the final Module 14 workbook
specification. The preferred visual organization is one timepoint row per
elapsed time, such as 0, 2, 4, 6 seconds, with each ROI side-by-side as its own
column. Each value sheet should represent one measurement type or closely
related measurement view so that a ROI is not split into multiple subcolumns in
the main review matrix. Separate positions and captures visually with empty
spacer columns using distinct colors for single-space and double-space breaks.
Separate experiments into their own spreadsheet-level export unit, while the
exact packaging of that unit as one workbook file per experiment or one
worksheet/tab per experiment remains to be clarified before implementation.

### D031 - Module 14 refined ROI-column examples generated (2026-07-12)

Generate refined non-final examples that show the D030 layout more directly:
one `.xlsx` file per synthetic experiment, one elapsed-time row per timepoint
such as 0, 2, 4, and 6 seconds, one ROI per column in each value sheet,
separate value sheets for different measurement views, blue empty spacer
columns between positions, and double peach empty spacer columns between
captures. These examples are visual-review artifacts only and are not an
implemented exporter.

### D032 - Module 14 refined layout accepted for implementation (2026-07-12)

Use one `.xlsx` workbook file per experiment for the Module 14 human-readable
export. In each value sheet, keep elapsed-time timepoints as rows and one ROI
per column. Keep row 6 as the displayed ROI label and row 7 as the abbreviated
full ROI identity in the form `cN/pN/rN`, such as `c1/p1/r1`, `c1/p1/r2`, and
`c1/p2/r1`. Keep blue empty spacer columns between positions and double peach
empty spacer columns between captures. The refined example in
`outputs/module14_refined_roi_columns_example_20260712/` is the accepted visual
basis for the first exporter implementation.

### D033 - Module 14 first exporter implementation boundary (2026-07-12)

Implement the first Module 14 exporter as a Python standard-library `.xlsx`
writer rather than adding a production spreadsheet dependency. The exporter
uses the D032 workbook-per-experiment, elapsed-time-row, ROI-column layout for
human-readable value sheets and preserves audit material as secondary sheets in
the same workbook rather than introducing companion CSVs or other unreviewed
external output formats. The audit sheets preserve current upstream Module 8,
10, 11, 12, and 13 records, including metadata, method parameters, QC statuses,
exclusion reasons, and structured issues.

### D034 - Module 14 audit sheet visual readability refinement (2026-07-13)

Validation with a representative upstream analysis bundle showed that the D032
value sheets are readable, but fixed 16-character widths in secondary audit and
long/tidy sheets clip important traceability fields such as method names,
parameter names, issue messages, issue context, original filenames, source
paths, and metadata values. Keep the D032 workbook structure and value-sheet
layout unchanged, but use semantic column widths for audit and long/tidy sheets
so provenance, parameters, QC reasons, and issues remain visually inspectable
without manual resizing.

### D035 - Module 2 real SlideBook TIFF normalization (2026-07-13)

Validate the representative SlideBook TIFF exports in `raw_data/` as one
generic `IYX` series per file. Each inspected file has two IFD pages with
`PageNumber` values `(0, 2)` and `(1, 2)`, and `tifffile` returns those pages in
the same order as a `(2, 600, 600)` `uint16` array. Under D003, normalize the
first `I` axis to ordered temporal `frame_index` values without interpreting it
as biological depth. The paired C0/C1 files match in axes, page count, frame
dimensions, dtype, page numbering, and structural acquisition metadata. No
per-frame elapsed time is available in the TIFF tags, so retain time as unknown
rather than inventing an interval. Preserve TIFF tags for every page because
the real files contain page-specific values. Continue to reject arrays with
more than three dimensions until a representative export requiring another
rule is inspected.

### D036 - Module 3 SlideBook log support and pair association (2026-07-13)

Supersede only the no-association boundary in D018 for the inspected SlideBook
`.log` family. Discover `.log` alongside `.txt` as auxiliary text metadata and
continue preserving raw text, source provenance, safe key/value entries, and
unparsed lines. Associate a log to a TIFF pair only from its explicit
tab-separated `TIFF File Name` column, after verifying that the referenced
files were discovered beside the log and resolve to exactly one parsed
Capture, Position, XY, Z, and T identity with one C0 and one C1 TIFF. Do not
infer an association from the log filename alone. Preserve unrecognized
auxiliary formats without association; report recognized tables with missing,
ambiguous, incomplete, or mixed-pair references as structured errors. Keep the
association as a Module 3 output and do not change experiment assignment or
later-module behavior in this decision. The real-data inspection is recorded
in `docs/MODULE_3_REAL_DATA_VALIDATION.md`.

### D037 - Preserve structured SlideBook acquisition context (2026-07-13)

For recognized SlideBook logs, preserve structured values for export date-time,
capture date-time, Z-plane count, time-point count, channel count, microns per
pixel, Z-step size, and average timelapse interval. Preserve the average
interval verbatim because examples may report `Unknown` and no unit-normalizing
rule has been established. Also preserve each table row as structured IFD,
X/Y/Z position, elapsed time, channel name, and TIFF filename data together
with its source line number and original row text. These fields are required
provenance for eventual final outputs even when they are not yet used in
analysis. Emit a structured warning when the declared channel count exceeds
two because the current pipeline supports only C0/C1; do not discard the extra
channel metadata. Keep this implementation within Module 3 and defer wiring it
through later modules to a separately requested session.

### D038 - Carry verified SlideBook metadata through pair hierarchy to export (2026-07-13)

Extend the validated `TiffPair` contract with an immutable, default-empty tuple
of Module 3 auxiliary metadata pair associations. During Module 4 experiment
assignment, attach only associations whose verified C0 and C1 source paths
match the validated pair; continue assigning experiments solely from explicit
rules and never from auxiliary text content. Downstream scientific calculations
remain unchanged because the association is provenance carried beside the image
pair.

Module 14 reads these associations from the exported pair automatically. In the
existing metadata audit sheet, preserve the association method and referenced
TIFF filenames, structured SlideBook header values, the complete raw log text,
and every structured table row including source line, IFD, X/Y/Z position,
elapsed time, channel name, TIFF filename, and original row text. Continue to
support explicitly supplied unassociated auxiliary files, and avoid duplicate
metadata rows when the same source file is also present as a pair association.
No production dependency or scientific interpretation is added.

### D039 - Real-pair integration validation boundary and unknown-time export (2026-07-13)

Add a focused, configurable harness that runs exactly one explicitly selected
C0/C1 TIFF pair through the available Modules 1-8 and 10-14. Keep it separate
from a future general pipeline runner. Its default segmentation, geometry,
background, camera, QC, channel-role, and baseline settings are validation-only
and must be preserved in the workbook with a structured non-production warning;
they do not resolve the corresponding pending scientific decisions.

When every exported temporal record has a known `time_seconds`, Module 14 keeps
the D032 `time_s / seconds` axis. If any frame time is unknown, use
`frame_index / index` and export frame indices rather than labeling those
indices as seconds. This enforces D003 and D035 without inventing an acquisition
interval. The real-pair validation is recorded in
`docs/MODULE_14_REAL_PAIR_VALIDATION.md`.

### D040 - Static ROI overlay boundary and review outcome (2026-07-13)

Implement only the static quality-control substitute permitted by deferred
Module 9. Render the first frame of the already selected segmentation channel,
use the unchanged Module 7 source labels and Module 8 status records, preserve
original label numbers, and encode accepted, flagged, and rejected geometry
with both color and line pattern. Export an auditable SVG plus a dependency-free
PNG view. Display percentile stretching is presentation-only and must not alter
image data, masks, geometry, or acceptance decisions.

Keep the interactive viewer, temporal navigation, ROI deletion, mask editing,
and manual-decision persistence deferred. Review of the D039 real overlay shows
mostly small bright puncta and compact fragments rather than consistent whole-
cell outlines. Therefore do not approve the placeholder engine, 99th-percentile
threshold, 20-pixel minimum, or border policy for production. The evidence and
geometry summary are recorded in
`docs/MODULE_9_STATIC_ROI_OVERLAY_VALIDATION.md`; production segmentation
choices remain pending scientific review.

### D041 - Static full-chain visual validation boundary (2026-07-13)

Extend the D040 static substitute only for the explicitly requested
`Capture 1 + Position 1` diagnostic review. Generate a dependency-free HTML
report with PNG/SVG views, CSV audit tables, and a JSON manifest containing
source and artifact SHA-256 hashes. Render existing intermediate results from
Modules 5-8 and summaries from Modules 10-13 without recalculating scientific
decisions, editing ROI, or introducing a GUI.

Keep the D039 P99 segmentation, 20-pixel minimum, border exclusion, P20 non-ROI
background, provisional 65,535 camera ceiling, disabled intensity decisions,
and provisional C0 donor/C1 FRET mapping unchanged. Sensitivity comparisons may
describe alternative pixel pools but are not pipeline runs and cannot select a
production parameter. Preserve the SlideBook log mapping of C0 CFPex/CFPem and
C1 CFPex/YFPem as provenance while leaving its biological interpretation
pending under P011. The validation record is
`docs/CAPTURE1_POSITION1_STATIC_VISUAL_VALIDATION.md`.

### D042 - Manual-workflow target, whole-cell ROI, and C0/C1 ratio (2026-07-13)

The scientific user confirmed that FUNES automates a simple manual workflow:
view a cell, draw a ROI following the complete visible cell shape, apply that
fixed ROI to both channels at every timepoint, extract average intensity from
C0 and C1, calculate `C0 / C1`, and transfer the timepoint series to Excel.
Additional metadata, preprocessing, background, QC, and audit stages support
that objective but must not obscure it.

Supersede the ratio orientation in D027 for this workflow. Numerator and
denominator must be represented explicitly as C0 and C1 rather than inferred
from donor/FRET role names. Continue preserving the SlideBook descriptions C0
CFPex/CFPem and C1 CFPex/YFPem as provenance, with their biological
interpretation still pending confirmation.

The D039/D041 real-pair calculations used C1/C0 and are therefore inverted for
the intended workflow. Their 2.77-10.86 ratio distribution and the causal
interpretation of that distribution are superseded. Reciprocating the saved
values gives approximately 0.0921-0.3606, but Module 13 must be corrected and
the artifacts regenerated before those values are treated as validated output.
The raw channel intensities, Module 5 channel metrics, P99 mask, component
geometry, and visual conclusion that the current mask traces bright puncta
rather than complete cells remain valid diagnostic evidence.

The P99 mask is not approved for production segmentation. It includes only the
brightest 1% of C1 pixels and visibly clips cells. Regions outside that sparse
foreground were never segmented; they are not equivalent to ROI that were
segmented and later rejected by geometry.

### D043 - Module 13 corrected mean and fixed C0/C1 contract (2026-07-13)

The scientific user confirmed that the manual procedure's “average intensity”
is the arithmetic mean inside the ROI after subtracting the quantitative
background, not the raw ROI mean. Use `background_corrected_mean` as the default
Module 13 measurement for the manual-workflow ratio. Preserve the raw ROI mean
and background-corrected ROI mean separately for C0 and C1 so neither can be
mistaken for the other.

Fix the scientific ratio contract as C0 numerator divided by C1 denominator.
Biological donor/FRET roles remain separately configured provenance and cannot
change that orientation. Preserve explicit `ratio_formula`, numerator,
denominator, selected measurement metric, and role mapping in audit parameters.
The earlier D039/D041 C1/C0 values, histogram, examples, and causal
interpretation remain superseded.

The regenerated Capture 1 + Position 1 diagnostic contains 72 corrected-mean
C0/C1 records ranging from approximately 0.0921 to 0.3606, with median 0.1990.
Raw-mean C0/C1 values are retained separately and range from approximately
0.1184 to 0.3675. These values validate the corrected Module 13 orientation and
artifact traceability only; they do not approve the unchanged P99 segmentation,
20-pixel minimum, P20 background method, QC profile, baseline window, channel
biology, or any ratio acceptance limits for production.

### D044 - Module 7 engine registry and benchmark-baseline profiles (2026-07-14)

Incorporate all five scientifically reviewed segmentation methods behind the
stable Module 7 interface. Present them in this order: K-means plus morphology,
Cellpose CP-SAM, reproducible marker watershed, global Otsu plus morphology,
and P99 plus connected components. Keep P99 as an explicit control/fallback,
not as a recommended whole-cell method. Use typed method identifiers and set
the configurable automatic default to `method=kmeans` with
`profile=benchmark_baseline`.

Register the fixed 2026-07-13 parameters as `benchmark_baseline` separately for
every method. This name records their origin without asserting that they are a
validated `medium` profile or that any method is universally accurate. The
benchmark had no manual reference masks or validated accuracy metric and its
parameters were neither tuned per field nor obtained from a systematic search.
Do not choose a supposedly best engine per image. Fully automatic operation
uses the configured global method/profile for every field.

Support an explicit override scoped to exactly one `Capture + Position`. Store
the effective method/profile, global method/profile, configuration source,
override status, and field key as immutable selection provenance. Every engine
run also records all effective parameters, postprocessing, random seeds,
engine/model identity, and installed package versions.

Implement the reviewed classical operations with SciPy, scikit-image, and
scikit-learn as declared production dependencies. These packages are required
to reproduce the reviewed Gaussian/Otsu/morphology/watershed and seeded sklearn
K-means behavior rather than introducing silent NumPy approximations. Keep
Cellpose outside the core dependencies as the optional `cellpose` extra and
import Cellpose/PyTorch only when CP-SAM is explicitly selected. If its
dependency, model, or weights cannot be used, raise an actionable blocked-engine
error and never substitute another method. Preserve the benchmark warning that
CP-SAM took about 46-55 minutes per 600x600 field on CPU and needs about 1.15 GB
of weights.

Keep Module 5 channel selection, first-frame-only segmentation, later fixed-ROI
application, TIFF inputs, GUI/editor deferral, and all unrelated scientific
modules unchanged. The direct configurable percentile engine remains available
for backward-compatible explicit P99 use, but is not the new default.

### D045 - Segmentation review by sampling and global approval (2026-07-14)

Do not require the user to inspect or choose segmentation independently for
every `Capture + Position`. The intended review workflow starts from one global
method/profile, lets the user inspect a representative subset of fields, and
then permits explicit approval of that global configuration for the remaining
fields when the user considers its behavior reasonable. Fields that need a
different method/profile continue to use the D044 per-field override.

Preserve review provenance without overstating what occurred. Distinguish at
least fields inspected manually, fields accepted under an approved global
policy without individual inspection, fields with an explicit override, and
fields not yet covered by review or approval. Record which representative
fields were inspected before global approval and the exact method/profile that
was approved. Acceptance by global policy is not equivalent to manual review
and is not evidence of universal segmentation accuracy.

The later workflow may support user-directed or predefined sampling, but it
must not silently decide that enough fields have been reviewed. GUI design,
manual ROI drawing, and mask editing remain separate deferred work.

### D046 - Module 7 immutable review and global-approval backend (2026-07-14)

Implement D045 as an immutable backend ledger composed with the D044
SegmentationConfiguration. Recording an inspection snapshots the exact
Capture + Position, effective method/profile, and whether that selection came
from the global configuration or a field override. Caller-supplied reviewer,
time, and note fields are optional provenance; the backend does not invent
timestamps or user identities.

Global approval must be a separate explicit operation. It records an approval
identifier, the exact current global method/profile, and an immutable snapshot
of all inspection records already present. Permit an empty or arbitrarily sized
snapshot: the backend must neither impose a scientific minimum nor infer that a
sample is sufficient. Inspections added after approval remain manual
inspections, but are not retroactively added to the pre-approval snapshot.

For each field, resolve one primary status using this precedence: explicit
override, then manually reviewed, then global policy accepted, then unreviewed.
Preserve the presence of a manual inspection independently, so an inspected
override remains auditable as both an override and an inspection. A field
accepted only because the approved global policy applies must always preserve
manually_inspected as false.

Configured Module 7 engine runs may consume the same immutable review ledger
and carry the resolved review status, inspected method/profile, approval
identifier, approved global method/profile, and pre-approval inspected fields
in selection provenance. Reject stale approval/global-selection combinations,
stale inspection/effective-selection combinations, duplicate inspections,
mismatched review and execution configurations, and incoherent manually
constructed status records with actionable errors. Add no GUI, mask or ROI
editing, parameter benchmark, new profile preset, production dependency, or
change to segmentation engines or other scientific modules.

### D047 - Module 7 explicit OFAT parameter-benchmark boundary (2026-07-14)

Implement the already planned one-factor-at-a-time grid as immutable benchmark
variants around each D044 `benchmark_baseline`. Include exactly one unchanged
reference per method and change exactly one parameter in every other variant.
Keep the confirmed method, parameter-axis, and candidate-value order. Add the
required Otsu and watershed threshold multipliers with baseline `1.0`, and
preserve both the unscaled Otsu threshold and effective scaled threshold.

Benchmark candidates are ephemeral parameter sets, not registered named
profiles. Do not add `strict`, `medium`, or `permissive`, change the global
K-means default, mutate the D046 review ledger, infer review coverage, tune per
field, rank candidates, or select a winner. Execution must be an explicit call
for one candidate and one identified Capture + Position prepared first frame.
Cellpose remains lazy and optional; it runs only when its candidate is selected
explicitly and a blocked dependency/model must never trigger fallback.

Return the original labels and descriptive mask geometry only: ROI count,
foreground pixels and fraction, and minimum/median/maximum labeled area. These
summaries are not accuracy metrics and cannot approve segmentation. The fixed
grid contains 36 runs including baselines: 8 K-means, 7 CP-SAM, 9 watershed,
9 Otsu, and 3 P99. Representative-field selection, execution artifacts, visual
review, and any future profile calibration remain separate scientific work.

### D048 - Module 7 explicit OFAT visual-review artifact boundary (2026-07-14)

Add a static artifact layer around D047 without changing its execution contract
or the D046 review backend. A review plan must name every selected
`Capture + Position` and every unchanged D047 variant explicitly. Preparing
real fields may compose Modules 1, 2, 5, and 6, but benchmark execution remains
one D047 call per planned field/variant combination. Do not infer additional
fields or variants.

For each completed run, preserve the exact integer label image and generate an
unclassified numbered overlay plus a raster preview. Also preserve the explicit
selection and preparation provenance, descriptive D047 mask geometry, blank
human-observation fields, and source/artifact SHA-256 hashes. The artifact
package must state that sample sufficiency was not assessed, no method ranking
or variant classification was performed, no profile was approved, and the
D046 ledger was not used or changed.

The first explicit package selects both currently available real fields,
`Capture 1 + Position 1` and `Capture 1 + Position 2`, and the eight K-means
variants in D047, for 16 runs. This is an explicit review set rather than a
sample-size conclusion. It neither selects a preferred K-means variant nor
evaluates Cellpose, watershed, Otsu, or P99 in this block. Artifacts are stored
in `outputs/module7_ofat_review_20260714_kmeans/` and documented in
`docs/MODULE_7_OFAT_VISUAL_REVIEW_ARTIFACTS.md`.

### D049 - Module 7 Cellpose operational deferral and Marker Watershed block (2026-07-14)

Withdraw Cellpose CP-SAM as the next complete D048 artifact block. Before any
complete Cellpose block is considered, a separate session must explicitly
select exactly one timed Cellpose test and define an acceptable operational
limit. That future test is an operational-feasibility check only and cannot
rank or approve Cellpose scientifically. Do not install or execute Cellpose in
the current block; the former planned 14-run destination remains absent.

Select Marker Watershed as the next block, naming both currently available
real fields, `Capture 1 + Position 1` and `Capture 1 + Position 2`, and all nine
unchanged D047 Marker Watershed variants in D047 order. Use selection identifier
`module7_ofat_marker_watershed_review_20260714` and destination
`outputs/module7_ofat_review_20260714_marker_watershed/`, for exactly 18 runs.

Generate the full D048 package with exact NPY labels, unclassified numbered SVG
overlays, PNG previews, descriptive CSV, blank human-observation fields,
selection/preparation provenance, an HTML index, and source/artifact SHA-256
hashes. Record segmentation-engine execution duration only as operational
information; it is not an accuracy measure and cannot be used to order,
classify, select, accept, or reject variants.

This decision does not infer that the two fields are sufficient or
representative, classify or rank any method or variant, approve or register a
profile, change the global K-means `benchmark_baseline`, or use or modify D046.
The durable selection record is
`docs/MODULE_7_OFAT_NEXT_VISUAL_REVIEW_SELECTION.md`, and the completed package
record is
`docs/MODULE_7_OFAT_MARKER_WATERSHED_VISUAL_REVIEW_ARTIFACTS.md`.

### D050 - Module 7 single Cellpose timed test and complete-block operational gate (2026-07-14)

Complete the separate operational evaluation required by corrected D049 using
exactly one unchanged D047 run: `cellpose_cpsam / benchmark_baseline` on
`Capture 1 + Position 1`. The selected C1 first frame is prepared through the
existing Modules 1, 2, 5, and 6 path with identity preprocessing. The selection
does not assert that the field is sufficient or representative or that the
baseline is preferred.

Run Cellpose exactly once on CPU with the unchanged D047 parameters, including
`cpsam_v2`, `gpu = false`, and `torch_threads = 1`. Record only the existing
engine-only operational timer. The completed cold-cache call, including the
initial 1.15 GB weight download within model construction, took
`3003.7913557` seconds (50 minutes 3.791 seconds) under Python 3.12.13,
Cellpose 4.2.1.1, and PyTorch 2.13.0. Do not execute a warm-cache repeat.

Before any complete Cellpose block may be considered under the same 600 x 600
CPU configuration, require a conservative declared projection no greater than
12 engine-hours: `run_count x 3003.7913557 <= 43,200 seconds`. This permits at
most 14 declared runs; 14 runs project to `42,053.0789798` seconds (11 hours
40 minutes 53.079 seconds). This is an operational scheduling gate only. It
does not authorize a block, rank or classify variants, approve or register a
profile, establish sample sufficiency, or establish scientific feasibility.
Different dimensions, hardware, GPU/threading, model, or effective parameters
remain outside the gate until separately authorized operational assessment.

Preserve the one-run package at
`outputs/module7_cellpose_timed_test_20260714/`. Do not change the global
K-means baseline, substitute another engine, or use or modify D046.

### D051 - Module 7 touching-cell division and joint-quantification fallback (2026-07-18)

When touching cells can be divided reliably, prefer separate labeled ROIs so
that the cells can be quantified individually. If a reliable division is not
possible, retain the connected cells as one ROI and quantify them jointly
rather than forcing an uncertain split. This decision defines the desired
scientific outcome but does not yet define an automatic reliability criterion,
select an engine or variant, or authorize a segmentation implementation change.

### D052 - Module 7 K-means and Marker Watershed comparison scope (2026-07-18)

Limit the current scientific comparison for a future global segmentation
selection to K-means plus morphology and Marker Watershed. Cellpose remains on
standby, and Global Otsu and P99 are outside this comparison block. Exclusion
from this block is not a universal rejection of those methods. This decision
defines only the comparison scope; it does not rank either included method,
select a winner or variant, approve or register a profile, change the global
K-means baseline, or authorize use of D046.

### D053 - Dim silhouettes are not mandatory ROI by appearance alone (2026-07-18)

For the current two-field K-means and Marker Watershed visual comparison, do
not require every dim silhouette without a contour to receive a ROI solely
because it is visible in the preview. Its omission is not by itself sufficient
to reject a variant. This does not authorize clipping a structure that has
been identified as a cell, contradict the complete-cell ROI objective in D042,
or establish that the inspected fields are sufficient or representative.

### D054 - Area-32 added components are cells in the reviewed fields (2026-07-18)

The scientific user identified the small components added by the
`minimum_object_area_pixels = 32` K-means and Marker Watershed variants as
cells in the two currently reviewed full-field previews. Treat their retention
as desirable within this comparison. This interpretation is limited to these
inspected fields and does not select a method or variant, approve or register a
profile, change the global baseline, use D046, or establish sufficiency or
representativeness.

### D055 - Doubtful Marker Watershed distance-8 splits remain joint ROI (2026-07-18)

The scientific user classified both pure Marker Watershed
`marker_min_distance_pixels = 8` divisions in the reviewed fields as doubtful:
the Position 1 object at `x=424:440, y=436:456` and the Position 2 object at
`x=471:481, y=313:332`. Apply D051 by retaining each object as one joint ROI
rather than forcing the two-label partition. This field-specific interpretation
does not define an automatic reliability criterion or universally reject the
parameter value.

### D056 - Valid cells omitted by the reviewed Marker Watershed supports (2026-07-18)

The scientific user confirmed that many valid cells remain outside the saved
Marker Watershed baseline / `marker_min_distance_pixels = 8` masks in both
reviewed fields. Those two variants have identical binary support, so the
distance change does not recover the omitted cells. This does not mean every
dim silhouette is a cell, supersede D053, establish field-set sufficiency or
representativeness, or select a competing method or variant.

### D057 - K-means area-32 advances only as a final-review candidate (2026-07-18)

Advance K-means `minimum_object_area_pixels = 32` as the only existing variant
from the 17-mask comparison that merits a final human acceptability comparison
on the two reviewed examples. This confirmation records review candidacy only.
It does not select a winner, approve or register a profile, establish that the
mask is acceptable, infer sample sufficiency or representativeness, change the
global K-means baseline, or use D046. Preserve the known human observations
that cells remain omitted in P2-R1 and that its P1-R4 coverage was not accepted.

### D058 - Minimum six-run OFAT causal extension authorized (2026-07-18)

Authorize exactly three new one-factor variants on the same two fields, for six
runs total: K-means `minimum_object_area_pixels = 16`, Marker Watershed
`minimum_object_area_pixels = 16`, and Marker Watershed
`foreground_threshold_scale = 0.8`. Keep these variants in a separate immutable
extension catalog with explicit origin, not in the unchanged D047 grid and not
in the production profile registry. Generate a new static review package at
`outputs/module7_ofat_minimum_extension_20260718/` without modifying the prior
OFAT or fixed-crop packages. Do not combine MW threshold `0.9` with area `32`,
because that would cease to be OFAT. This authorization does not rank or approve
a result, change the global baseline, assess representativeness, use D046, or
authorize any further variant.

### D059 - Area-16 added components are cells in the reviewed fields (2026-07-18)

The scientific user identified as cells all components newly added by the
authorized area-16 variants relative to their corresponding area-32 masks: 7 / 7
K-means components and 6 / 6 Marker Watershed components in Position 1 /
Position 2. Retain these components when interpreting the extension on these
two fields. This confirmation is limited to the inspected examples and does not
establish complete-cell coverage, sample sufficiency, representativeness, an
acceptable production minimum area, or a registered profile.

### D060 - Final comparison contains only K-means area-32 (2026-07-18)

Include only K-means `minimum_object_area_pixels = 32` in the final human
acceptability comparison. Do not add K-means area `16`, Marker Watershed area
`16`, or Marker Watershed threshold scale `0.8`, even though D059 confirms that
the area-16 additions are cells in these fields. The extension variants do not
recover the key P2-R1 omissions and do not displace the D057 candidate. This
decision limits the final comparison set; it does not yet approve K area `32`
for production, register a profile, change the global baseline, establish
sufficiency or representativeness, or use D046.

### D061 - K-means area-32 requires another causal extension (2026-07-18)

The scientific user selected the final-review outcome that K-means
`minimum_object_area_pixels = 32` is not yet acceptable for these two examples
because many cells are excluded, and that another causal extension is required
before deciding acceptance or rejection. Preserve as separate confirmed
limitations the cells wholly omitted in P2-R1 and the unaccepted complete-cell
coverage in P1-R4. Do not count an uncertain touching-cell division as a defect
when D051 permits a joint ROI, and do not classify the area-32 additions as
artefacts because D054 confirms that they are cells in these fields.

The existing masks establish that area filtering caused a subset of prior
omissions: lowering the K-means minimum area from 64 to 32 pixels retained
12 / 21 additional cellular components in Position 1 / Position 2. They also
establish that the key residual limitations are not repaired by lowering that
minimum from 32 to 16 pixels: the area-16 extension adds no foreground pixel in
P2-R1 and leaves P1-R4 unchanged. The current evidence therefore does not
support attributing those key residual omissions to the tested minimum-area
filter. A foreground/intensity-selection cause upstream of area filtering is a
causal hypothesis, not a confirmed cause, because no genuinely more permissive
K-means foreground variant exists in the saved artifacts.

This decision requires a separately reviewed causal-extension design but does
not authorize a particular variant or run. It does not reject K area `32`
finally, approve or register a profile, change the global baseline, establish
sufficiency or representativeness, or use or modify D046.

### D062 - Minimum K-means foreground-boundary causal design (2026-07-18)

Design the next D061 extension around one new diagnostic K-means factor,
`foreground_boundary_relaxation_fraction`, without implementing or executing
it in this block. For the ordered centers around the existing foreground
boundary, `c0 < c1`, retain `0.0` as unchanged behavior and propose exactly
one candidate value, `0.5`. The candidate moves the threshold from
`c0 + 0.5 * (c1 - c0)` to `c0 + 0.25 * (c1 - c0)`. Define the candidate raw
foreground as a union with the unchanged two-cluster foreground so the
intervention is a guaranteed permissive superset.

Hold every other effective input fixed to the D061 K area-32 candidate,
including three fitted clusters, two foreground clusters, identity
preprocessing, morphology, seed, and `minimum_object_area_pixels = 32`. Do not
test minimum area again. Do not vary cluster count or select all three clusters
as foreground because either change would confound or degenerate the intended
causal question.

If later implemented and separately authorized, run only this candidate on
`Capture 1 + Position 1/2`, for two new engine calls total. Use the existing
saved K area-32 labels as immutable final references rather than rerunning area
variants. Preserve raw baseline and relaxed selection masks, their exact added
support, post-morphology/pre-area support, final labels, thresholds, centers,
fixed-crop changes for P2-R1 and P1-R4, and complete hash provenance. Human
review must distinguish a foreground-selection contribution from final mask
acceptability and from downstream loss of newly selected pixels.

The detailed design is
`docs/MODULE_7_KMEANS_FOREGROUND_CAUSAL_EXTENSION_DESIGN.md`. This decision
does not authorize implementation or execution, approve or register a profile,
change the global baseline, infer sufficiency or representativeness, reject K
area `32`, or use or modify D046.

### D063 - K-means foreground causal extension implemented synthetically (2026-07-18)

Implement the D062 diagnostic extension within Module 7 and verify it only on
synthetic arrays. Add `foreground_boundary_relaxation_fraction` to the K-means
internals with exact unchanged selection behavior at `0.0`; expose an immutable
diagnostic trace; and define exactly one separate catalog candidate at `0.5`
relative to K-means `minimum_object_area_pixels = 32`. Keep the area fixed at
32 and keep the candidate outside both existing OFAT catalogs, the registered
profiles, the global baseline, and D046.

Add a causal review-package contract that accepts only the unchanged candidate
and exactly `Capture 1 + Position 1/2` in fixed order. It must verify source and
saved area-32-reference hashes before execution; preserve baseline/relaxed raw
selection, exact raw additions, baseline/candidate post-morphology pre-area
support, final labels, thresholds, centers, complete-field and fixed-crop
changes; generate unclassified full-field and focused artifacts; and hash every
generated artifact. Synthetic tests may execute this exact two-call package as
implementation verification.

The implementation block executed no real TIFF, created no real-data output,
made no causal or acceptability conclusion, approved no profile, changed no
baseline, inferred no sample sufficiency or representativeness, and did not use
or modify D046. The two real candidate calls remain pending explicit user
authorization.

### D064 - Exact two-call K-means foreground causal package executed (2026-07-18)

Accept the scientific user's explicit authorization to execute the single
D063 candidate exactly once on each of `Capture 1 + Position 1` and `Capture 1
+ Position 2`, in that order, for exactly two real segmentation-engine calls.
Before execution, verify the current C1 source-TIFF and saved K area-32 label
hashes against the earlier immutable K-means package, verify the plan length,
and confirm `foreground_boundary_relaxation_fraction = 0.5` plus
`minimum_object_area_pixels = 32`. Do not rerun area 16, 32, or 64.

The preflight passed. The resulting immutable package is
`outputs/module7_kmeans_foreground_causal_review_20260718/`. Position 1 has 84
candidate labels and 12,475 final foreground pixels; relative to the saved
area-32 reference it adds 5,308 raw-selection pixels, 5,336 post-morphology
pixels, and 5,215 final pixels, with no recorded removal. In P1-R4 the
corresponding descriptive additions are 133, 123, and 111 pixels. Position 2
has 106 candidate labels and 16,504 final foreground pixels; it adds 7,153
raw-selection pixels, 7,325 post-morphology pixels, and 7,317 final pixels,
with no recorded removal. In P2-R1 the corresponding descriptive additions are
423, 427, and 417 pixels. Baseline/candidate thresholds are
4710.581047162152 / 2633.3384415672913 for Position 1 and
4631.51462890531 / 2600.7434765015214 for Position 2.

The package preserves all required masks and traces, full-field overlays and
previews, focused causal sheets, complete-field and focused comparisons, two
blank human-observation rows, source/reference provenance, and a SHA-256
manifest covering 24 generated artifacts. Post-run validation found no hash
mismatch and confirmed that source and reference hashes remain unchanged. The
six D063 tests and the complete 126-test suite pass.

All numeric results are descriptive mask facts only. Do not automatically
classify newly selected support as cellular or non-cellular, infer causal
contribution, sufficiency, representativeness, scientific or final
acceptability, approve or register a profile, change the global baseline, or
use D046. Stop for human visual and scientific review of both complete fields
and the P1-R4/P2-R1 focused sheets.

### D065 - D064 review confirms contribution but rejects the relaxation for acceptance (2026-07-19)

Accept the scientific user's explicit confirmation of the read-only D064
full-field and focused-sheet review. In P1-R4, the relaxed selection reaches
visible cellular signal outside the saved K area-32 reference and expands the
border-intersecting objects, but it also produces a small isolated addition
without clear cellular structure. Foreground-selection contribution is
supported there, but final acceptance is not. In P2-R1, the candidate recovers
several previously omitted cellular peripheries or bodies while other dim
visible bodies remain without a final ROI. Classify P2-R1 as contribution but
not sufficient and do not accept the candidate finally.

The confirmed complete-field review finds no field-wide background carpet but
does find localized nonspecific expansion and possible bridging. A read-only
comparison of the saved labels identifies 27 / 31 wholly new candidate labels
in Position 1 / Position 2 and 3 / 5 candidate labels that connect support
from multiple saved reference labels; one Position 2 candidate connects three
saved labels. These overlap relations identify bridge candidates and do not
override D051's allowance for a joint ROI when no reliable biological split is
available.

Conclude that the tested `foreground_boundary_relaxation_fraction = 0.5`
confirms a contribution from the K-means foreground boundary but is not
sufficient for acceptable segmentation on these two fields and introduces a
specificity/bridging risk. Do not approve or register it as a profile, change
the global `benchmark_baseline`, infer sample sufficiency or
representativeness, authorize another run, or use D046. Preserve the immutable
D064 package unchanged; its manifest-listed blank observation CSV is not a
post-review writable ledger. The detailed review record is
`docs/MODULE_7_D064_SCIENTIFIC_REVIEW.md`.

### D066 - Close the current K-means foreground-boundary causal branch (2026-07-19)

Close the current K-means causal branch based on the saved D064 evidence and
the D065 scientific review, without another segmentation execution. The tested
factor is a monotonic permissive relaxation of one global intensity boundary.
With every downstream setting fixed, a value below `0.5` selects a subset of
the raw support selected at `0.5`; it therefore cannot recover the dim bodies
that remain omitted at `0.5`, even if it might reduce some nonspecific support.
A value above `0.5` selects a superset and therefore cannot remove the
localized nonspecific addition or the connections already exposed at `0.5`,
even if it might recover more cellular signal. The tested value itself was not
accepted under D065.

Consequently, no additional value of
`foreground_boundary_relaxation_fraction` is a justified single next causal
step for resolving both residual omission and specificity/bridging within this
branch. Do not design or authorize another real run along this scalar
relaxation axis. Any future K-means investigation would require a separately
justified mechanism and a new explicit causal design; it is not a continuation
of D062-D065 and is not authorized here.

This branch closure does not reject K-means universally, reject K area `32` as
a diagnostic reference, select another engine, approve or register a profile,
change the global `benchmark_baseline`, infer sample sufficiency or
representativeness, or use D046. The immutable D064 package remains unchanged.

### D067 - Formulate a new K-means mechanism before reopening the method comparison (2026-07-19)

Choose a new, separately justified K-means causal-mechanism design as the next
Module 7 block instead of returning immediately to the pending K-means versus
Marker Watershed comparison. This is a design-direction decision only; it does
not define a candidate, authorize implementation, or authorize segmentation.

The existing comparison has already exhausted the currently saved discriminating
evidence on these two fields. K-means `minimum_object_area_pixels = 32` covers
all saved D054-confirmed component supports from both method families, whereas
no reviewed Marker Watershed variant does. Marker-distance changes alter only
the partition of an unchanged, insufficient support and the two inspected
splits are doubtful under D055. The separately executed Marker Watershed
threshold `0.8` extension still adds no support in P2-R1 and covers none of the
saved K area-32 confirmed supports. Re-reading the same comparison without a
new mechanism or new evidence would therefore not resolve the current
omission-versus-specificity problem.

The next design must be outside the D062-D066 monotonic global-boundary branch.
It should state one auditable causal hypothesis for making foreground selection
spatially conditional or locally adaptive, so recovery of dim cellular bodies
or peripheries can be distinguished from isolated nonspecific additions and
connections between prior objects. It must also distinguish recovery of a
wholly omitted cell from expansion of an already detected object; a mechanism
that can only grow existing supports cannot by itself address both confirmed
failure classes. Exact mechanism, factor, controls, traces, and any future
execution boundary remain unresolved and require a separate design review.

Defer reopening the K-means versus Marker Watershed comparison until such a
new candidate supplies genuinely new causal evidence or another separately
justified source of evidence is identified. This does not select K-means as a
production method, reject Marker Watershed, approve or register a profile,
change the global `benchmark_baseline`, use D046, infer sample sufficiency or
representativeness, or authorize a real or synthetic segmentation run.

### D068 - Minimum locally background-conditioned K-means design (2026-07-19)

Define one new diagnostic K-means foreground-selection mode,
`foreground_spatial_conditioning = local_background_p20`, against the exact
unchanged control mode `none`. Keep the global three-cluster K-means fit and its
existing boundary between the lowest and middle ordered centers. In the
candidate only, lower that boundary pixelwise by the negative local-background
offset: use field P20 as the reference and a reflect-padded local P20 window
whose odd side is `2 * floor(min(height, width) / 8) + 1` (151 pixels for the
current 600 x 600 fields). Do not raise the boundary in brighter regions, and
allow additions only where local P20 is strictly below field P20. Define
candidate raw support as a union with the unchanged two-highest-cluster
support.

This is one predeclared mode switch, not a grid or another value on the closed
D062-D066 scalar relaxation axis. Keep
`foreground_boundary_relaxation_fraction = 0.0`, identity preprocessing,
three clusters, two foreground clusters, the fit and seed, morphology,
connectivity, and minimum area 32 fixed. The field-relative window rule and P20
are diagnostic settings only and carry no production-scale or biological
optimality claim.

Require an auditable topology trace. Raw additions must be classified as
detached, single-anchor, or multi-anchor proposals according to contact with
unchanged raw components. Final candidate labels must be classified against
the immutable K area-32 final labels as de novo, existing-object expansion,
unchanged/carried, or bridge candidates. These are geometric relations only.
Only explicit scientific review may identify a de novo candidate as a wholly
omitted cell, an expansion as cellular completion or nonspecific growth, or a
bridge as acceptable under D051 or unacceptable. Counts, area, or zero overlap
must not make those biological classifications automatically.

The complete design, controls, traces, interpretation rules, and possible
future two-call boundary are recorded in
`docs/MODULE_7_KMEANS_LOCAL_BACKGROUND_CAUSAL_DESIGN.md`. This decision
authorizes no implementation, synthetic verification, real segmentation, or
artifact generation. It does not change the global baseline, register or
approve a profile, reopen the method comparison, use D046, or infer sample
sufficiency or representativeness.

### D069 - Exact D068 candidate implemented with synthetic verification only (2026-07-19)

Accept the scientific user's explicit authorization to implement only the
single D068 diagnostic candidate and its audit trace, using exactly
`foreground_spatial_conditioning = local_background_p20` against control mode
`none`. Preserve P20 with NumPy `linear` interpolation, the odd window rule
`2 * floor(min(height, width) / 8) + 1`, and NumPy-style reflected padding that
does not repeat the edge sample. Keep the global three-cluster K-means fit,
two highest-center foreground clusters, fitting behavior, seed, morphology,
connectivity, minimum area 32, and
`foreground_boundary_relaxation_fraction = 0.0` unchanged.

Implement the candidate as one immutable, unregistered mode-switch variant
outside the D047 and D058 catalogs, the D062-D066 relaxation catalog, the
production profile registry, the global baseline, and D046. Its synthetic-only
runner requires immutable area-32 reference labels that exactly equal the
unchanged control labels for the supplied prepared array. The trace preserves
the prepared-array SHA-256, fit sample indices, original and ordered centers,
selected cluster identifiers, global boundary, field P20, complete local-P20
and threshold arrays, raw/control/candidate masks through final labels, exact
stage changes, and an immutable component table.

Keep every topology class geometric. Raw additions are recorded as detached,
single-anchor, or multi-anchor proposals; final labels are recorded as de novo,
existing-object expansion, unchanged/carried, or bridge candidates. None is
automatically classified as a cell, cellular completion, nonspecific support,
or an acceptable/unacceptable D051 joint ROI.

Verification uses synthetic NumPy arrays only. It checks unchanged control
behavior, deterministic masks, the 600 x 600 window result of 151, exact local
P20 values against explicit NumPy reflection and linear percentile windows,
threshold arithmetic, strict negative-offset gating, raw-superset and
no-removal invariants, all declared topology relations, fixed controls, and
rejection of an unauthorized variant or mismatched reference. No TIFF was read
or segmented, no real-data or review artifact was generated, no profile or
baseline was changed, D046 was not used, and no sufficiency or
representativeness conclusion was made. Real execution remains separately
unauthorized.

### D070 - Separate real-execution authorization design is required (2026-07-19)

Review D069 and confirm that any real-data execution of the D068 diagnostic
candidate must remain behind a separately reviewed authorization design.
D069 authorizes only the exact implementation and synthetic-array
verification; it does not provide authority to pass a real TIFF-derived frame
to the candidate runner or to generate a real-data review package.

This decision establishes only that the separate authorization design is the
required next boundary if real execution is later requested. It does not
design that authorization, select or execute any real call, generate an
artifact, change the global `benchmark_baseline`, register or approve a
profile, use D046, or infer sample sufficiency or representativeness. The
possible future execution boundary already described by D068 remains a design
input, not an authorization.

### D071 - Exact D069 real-execution authorization contract designed, not activated (2026-07-19)

Define the separate real-execution authorization contract required by D070
without implementing or activating it. The only eligible plan is
`module7_kmeans_local_background_real_review_d071`, writing
`outputs/module7_kmeans_local_background_causal_review_d071/`, with the
unchanged D069 `local_background_p20` candidate and exactly two candidate calls
in fixed order: Capture 1 + Position 1, then Position 2. It uses the C1 first
frames after identity preprocessing and the saved K-means area-32 labels
read-only. Current source, prepared-frame, and reference hashes and every
D068/D069 control are fixed by the detailed design.

Require fail-closed preflight before the first call, a zero-to-two call
counter, no automatic retry, incomplete-attempt isolation, postflight
hash/invariant verification, and publication only after both calls succeed.
Preserve every D069 array and topology record, unclassified full-field/focused
views, blank human-observation records, exact authorization provenance, and a
complete SHA-256 manifest. Geometric classes remain non-biological and human
review remains separate.

Because the current runner deliberately records synthetic-only provenance,
require a separately requested implementation-only Module 7 block that adds a
typed package-level real-review boundary and verifies it on synthetic arrays.
Only after review of that contract may a later explicit scientific-user
statement naming the D071 selection, destination, order, and no-retry scope
authorize execution. D071 itself authorizes no code change, real TIFF read or
segmentation, artifact, retry, profile/baseline change, D046 action, biological
classification, sufficiency/representativeness inference, or scientific
conclusion. The full contract is
`docs/MODULE_7_KMEANS_LOCAL_BACKGROUND_REAL_EXECUTION_AUTHORIZATION_DESIGN.md`.

### D072 - D071 typed package boundary implemented synthetically (2026-07-20)

Accept the explicit implementation-only request required by D071. Add one
typed package-level boundary for selection
`module7_kmeans_local_background_real_review_d071`, the declared destination
`outputs/module7_kmeans_local_background_causal_review_d071/`, the unchanged
D069 candidate, and exactly Capture 1 + Position 1 followed by Position 2.
Keep the exact reviewed real source, prepared-frame, reference, and focused-
region identities in immutable typed constants.

Represent synthetic contract verification and authorized real review as
distinct typed execution modes. The synthetic mode must reject the declared
D071 destination; the real mode must require the reviewed authorization scope
and exact workspace-relative destination. Keep the public D069 runner unable
to accept either package scope and always record
`synthetic_verification_only = true`. The package-only entry point records the
authorization identifier, authorization scope, execution mode, and whether
the call is synthetic in engine provenance.

Before the first call, verify the complete two-input plan, output state,
source/prepared/reference hashes, reference label shape/dtype, C1 selection,
identity preprocessing, fixed region bounds, and absence of a prior attempt
under the authorization identifier. Count calls started and completed
separately, perform no retry, preserve an incomplete attempt plus error record
outside the final destination on failure, recheck immutable inputs, verify all
artifact hashes and planned files, and publish only after exactly two calls
complete successfully.

Preserve every D069 trace array, scalar fit/local-threshold record, geometric
component row, complete-field and focused unclassified view, blank biological
observation field, operational-only timing, selection/authorization
provenance, and a complete SHA-256 manifest. Five focused tests use only small
synthetic NumPy arrays, synthetic immutable source bytes, temporary `.npy`
references, and temporary output paths. Together with the five unchanged D069
tests, all ten focused tests pass. They verify complete preflight before any
call, exact order/count, no retry, failure isolation, late publication,
manifest completeness, input immutability, and rejection of extra fields,
copied variants, alternate destinations, and mismatched identities.

This block did not read or segment a real TIFF, create or reserve the declared
D071 destination, activate the real-execution gate, change the global
baseline, register or approve a profile, use D046, classify any component
biologically, or assess sufficiency or representativeness. A later explicit
scientific-user activation statement matching D071 remains required.

### D073 - D071 package integrity and bounded human observations recorded (2026-07-20)

Record the existing separately authorized real-review package at
`outputs/module7_kmeans_local_background_causal_review_d071/` as immutable and
verify it read-only before human review. Its `manifest.json` SHA-256 is
`e9af768a03f1e1bbd821f8f594018711b8328c3542adc6f21cebe0f7675d90a8`.
All 35 listed artifacts match their recorded sizes and hashes, the package has
no unlisted file other than the manifest itself, both source TIFF hashes and
both saved area-32 reference hashes match, and the two in-package observation
rows remain blank. The records preserve the exact D071 selection, authorized
real-review mode, Position 1 then Position 2 order, two started and completed
calls, and no retry.

Limit visual review to the two complete-field previews and the fixed P1-R4 and
P2-R1 sheets. In P1-R4 the displayed saved-reference and candidate contours
coincide, and the raw-addition panel shows no magenta addition. In P2-R1 the
same three visible structures remain outlined, while two isolated magenta raw-
addition pixels lie inside two bright structures that already have reference
contours; no new outlined structure is visible. In both complete fields,
contours remain concentrated mainly on brighter compact structures, many faint
or diffuse structures remain unoutlined, and no field-wide contour carpet is
visible.

These are explicit human visual observations, not biological component
classifications or a final scientific conclusion. Do not infer acceptability,
sufficiency, representativeness, preference, or production readiness; do not
approve or register a profile, change the global baseline, use D046, tune a
parameter, rerun segmentation, or modify the D071 package. The separate review
record is `docs/MODULE_7_D071_REAL_REVIEW_HUMAN_OBSERVATIONS.md`.

### D074 - K-means area-32 adopted as a provisional working profile (2026-07-20)

Accept the scientific user's decision that the unchanged K-means segmentation
with `minimum_object_area_pixels = 32` is sufficiently usable to continue
incremental development, while remaining imperfect. Register it as the typed
profile `provisional_working_kmeans_area32` and make
`kmeans / provisional_working_kmeans_area32` the configurable global working
default. Copy every K-means `benchmark_baseline` parameter unchanged except
for the minimum object area. Keep the five `benchmark_baseline` profiles as
separate diagnostic references and do not infer or tune a method per field.

The word *provisional* is part of the profile identity and its catalog status.
This decision does not claim universal accuracy, representative or sufficient
sampling, or complete segmentation of every cell. Preserve three explicit
known limitations on the profile: faint cells may be omitted, some cells may
receive only partial coverage, and cells in contact may remain combined in one
joint ROI. This working choice permits downstream development; it is not an
explicit D046 global scientific approval and does not erase the earlier visual
observations or their bounded scope.

Define `SegmentationResult` as the stable Module 7 output. It contains a
read-only, non-empty 2D `int32` label image with the same spatial shape as the
prepared first frame; label `0` is background; positive ROI labels are
canonical and consecutive from `1` through `roi_count`; and engine identity,
method/profile selection, effective parameters, deterministic seeds, package
versions, structured issues, and review/override provenance remain attached.
Module 8 consumes `label_image` without reinterpretation, and later fixed-ROI
consumers use the same label supports. Shape and label invariants fail closed
with actionable errors.

Do not use the D071 `local_background_p20` candidate for this profile or
default. Do not perform another parameter search, read or rerun the real TIFFs,
modify prior immutable review packages, or infer new biological conclusions.
Validation for this decision is limited to synthetic unit tests covering the
profile registry/default, its exact area-32 parameter and limitation metadata,
selection/review provenance, canonical immutable output labels, shape checks,
and the unchanged explicit benchmark boundary.

### D075 - Typed Module 7-to-8 geometry handoff (2026-07-20)

Use `filter_segmentation_rois(SegmentationResult, ...)` as the integrated
Module 8 entry point. It must consume the exact
`SegmentationResult.label_image`, retain the source `SegmentationResult` so its
engine, provisional profile, effective parameters, deterministic seeds,
package versions, issues, and selection/review provenance remain available,
and apply geometric decisions without relabeling retained ROIs. A rejected ROI
is replaced by background only on its own support; gaps in positive label
numbers after filtering are intentional and must not be canonicalized again.

Keep the array-only `filter_labeled_rois(...)` helper for synthetic masks and
compatibility, explicitly without Module 7 provenance. This handoff adopts the
existing D074 K-means area-32 working result unchanged: it does not rerun a
TIFF, search or modify segmentation parameters, adopt the D071 local-background
candidate, change the Module 7 default, or make a new biological conclusion.
Validate the boundary with synthetic canonical labels only.

### D076 - Module 10 consumes the geometrically filtered ROI mask (2026-07-20)

At the integrated Module 8-to-10 boundary, pass the exact
`RoiFilteringResult.filtered_label_image` to the replaceable quantitative
background strategy. For the D024 non-ROI pixel source, zero-valued supports
created when Module 8 rejects an ROI are therefore eligible background pixels;
positive retained supports remain excluded. Preserve retained label values and
intentional gaps without relabeling or reinterpretation.

This is the direct downstream consequence of D074 and D075, not a new
segmentation selection or scientific approval. Verify it with a synthetic
typed `SegmentationResult` carrying the provisional area-32 profile, without
executing a segmentation engine, reading or rerunning real TIFFs, reopening
Module 7 parameters, or modifying immutable review artifacts. Module 10 still
accepts the label-image interface defined by D024 and does not duplicate or
take ownership of Module 7/8 provenance.

### D077 - Module 11 consumes the filtered ROI result and Module 10 background (2026-07-20)

At the integrated Module 8-to-11 boundary, pass the typed
`RoiFilteringResult` to `evaluate_filtered_roi_intensity_qc(...)`. That entry
point must give the replaceable Module 11 strategy the exact
`RoiFilteringResult.filtered_label_image`, preserving retained positive label
values and intentional gaps without relabeling. Keep the array-based
`evaluate_intensity_qc(...)` entry point for compatibility and synthetic use.

Module 11 must consume the existing `QuantitativeBackgroundResult` produced by
Module 10 and must not estimate background again. Preserve the Module 10 method
in Module 11 result parameters and per-ROI-frame metrics so the correction and
SNR inputs remain auditable. This is a typed downstream handoff and no new
background, saturation, low-signal, segmentation, or biological decision.

Validate the handoff with synthetic arrays, a typed provisional area-32
`SegmentationResult`, and in-memory frame sequences only. Do not execute a
segmentation engine, read or rerun a TIFF under `raw_data/`, reopen Module 7
parameters, or modify immutable review artifacts.

### D078 - Module 12 consumes filtered ROIs and reuses Module 10/11 results (2026-07-20)

At the integrated Module 8/10/11-to-12 boundary, pass the typed
`RoiFilteringResult` to `extract_filtered_roi_temporal_intensities(...)`.
That entry point must give the replaceable Module 12 strategy the exact
`RoiFilteringResult.filtered_label_image`, the existing
`QuantitativeBackgroundResult` produced by Module 10, and the existing
`IntensityQcResult` produced by Module 11. Keep the array-based
`extract_temporal_intensities(...)` entry point for compatibility and synthetic
use.

Module 12 must preserve retained positive label values and intentional gaps
without relabeling; geometrically rejected labels produce no temporal records.
It must use the supplied channel/frame background estimates for correction and
copy the supplied Module 11 statuses and reasons by scope without estimating
background or evaluating QC again. Preserve the Module 10 and Module 11 method
names in Module 12 result parameters for auditability.

Validate the handoff with synthetic arrays, a typed provisional area-32
`SegmentationResult`, and in-memory frame sequences only. Do not execute a
segmentation engine, read or rerun a TIFF under `raw_data/`, reopen Module 7
parameters, or modify immutable review artifacts.

### D079 - Module 13 consumes only the typed D078 result (2026-07-20)

At the Module 12-to-13 boundary, require `calculate_fret(...)` and direct
`ConfiguredFretCalculator.calculate(...)` calls to receive a runtime-validated
`TemporalIntensityResult`. Pass that exact object to a replaceable Module 13
strategy and calculate only from its already extracted records. Do not accept
raw record tuples, arrays, TIFF pairs, quantitative-background results, or
intensity-QC results as alternative structural inputs.

Preserve every positive ROI label carried by the D078 result, including
intentional gaps created by upstream geometric rejection. Pair C0 and C1 only
by the existing `(roi_label, frame_index)` identifiers; do not enumerate or
canonicalize labels. Module 13 must not read or reopen TIFF data, estimate
background, evaluate QC, or extract temporal intensities again.

Validate the boundary with one in-memory synthetic call to the typed D078
entry point. The fixture removes labels `1` and `3`, retains labels `2` and
`4`, and proves that the exact returned `TemporalIntensityResult` reaches the
replaceable FRET strategy unchanged. Spies verify that TIFF reading,
background estimation, both QC entry points, and both temporal-intensity entry
points are not called during FRET calculation. This decision adds no new
ratio, baseline, background, QC, segmentation, or biological interpretation.

### D080 - Module 14 requires completed typed Module 8/10/11/12/13 results (2026-07-20)

At the upstream-to-export boundary, require every `Module14PositionExport` to
receive runtime-validated `RoiFilteringResult`,
`QuantitativeBackgroundResult`, `IntensityQcResult`,
`TemporalIntensityResult`, and `FretCalculationResult` instances. These five
results are mandatory; do not accept `None`, mappings, record tuples, arrays,
or structurally similar objects in their place.

Module 14 consumes only those already completed results. It must not execute
segmentation, geometric ROI filtering, quantitative-background estimation,
intensity QC, temporal-intensity extraction, or FRET calculation. Preserve
positive ROI labels exactly across wide and audit sheets, including intentional
gaps introduced upstream; do not enumerate or canonicalize them during export.

Validate the boundary with synthetic completed results whose retained labels
are exactly `2` and `4`. Verify both wide workbook headers and the Module 8,
11, 12, and 13 audit records, and use spies on the public upstream entry points
to prove that export invokes none of them. This contract hardening changes no
workbook layout, analysis method, threshold, ratio, baseline, QC policy,
segmentation profile, or biological interpretation.

### D081 - Module 9 read-only interactive field review (2026-07-20)

Activate only the bounded read-only portion of Module 9. Generate one
self-contained HTML viewer for one explicitly supplied typed `TiffPair`,
`RoiFilteringResult`, and `SegmentationReviewState`. Permit C0/C1 selection,
temporal-frame navigation, visibility controls for accepted, flagged, and
rejected Module 8 records, label visibility, and inspection of geometry details.
Use the exact `source_label_image` contours on both channels and every frame;
never enumerate, canonicalize, delete, redraw, or modify a label.

Persist unfinished form and viewing state only in browser-local storage. An
explicit reviewer confirmation may export one
`funes.module9.roi_review.v1` JSON with optional reviewer, inspection-time, and
note fields. Loading is strict. Before passing it to D046
`record_inspection(...)`, verify the exact Capture + Position, a SHA-256 over
the shaped canonical `int32` source-label image, a second SHA-256 over the
complete Module 8 masks/configuration/status/geometry record, and the current
effective method/profile and selection source. A valid viewer decision records manual
inspection only; global approval remains a separate D046 operation and the
viewer must not infer review sufficiency.

Validate with synthetic in-memory arrays containing nonconsecutive labels and
all three Module 8 statuses. Cover successful D046 recording and fail-closed
handling of malformed JSON, changed labels or Module 8 statuses, stale
segmentation selection, shape mismatch, and invalid display/output
configuration. Add no production
dependency and do not read or segment any TIFF under `raw_data/`. Manual ROI
deletion, mask drawing/editing, changed-mask persistence, new-label creation,
multi-field application orchestration, segmentation changes, scientific
approval, and parameter changes remain deferred extensions. The generated
JavaScript must parse with the bundled runtime; automated visual opening may
not be claimed when the local-file browser policy blocks it.

### D082 - Reconstruct only the missing typed Module 8 boundary for the Position 2 viewer (2026-07-20)

For the requested `Capture 1 + Position 2` Module 9 artifact, reuse the exact
persisted K-means area-32 labels from
`outputs/module7_ofat_review_20260714_kmeans/runs/field_002__variant_003/labels.npy`.
Require its recorded SHA-256
`c4428d4f6f470ce00a9fbeaf57503f850237b8d5b7781b8dba259799b2c97aa3`
and the already documented C0/C1 TIFF hashes to match before export.

The typed `RoiFilteringResult` was never persisted with that label artifact.
Reconstruct only this missing Module 8 boundary from the verified labels using
the unchanged real-pair validation geometry configuration:
`min_area_pixels=20`, no maximum area, and border-touching ROI exclusion.
Create the typed segmentation provenance from the current registered
`kmeans/provisional_working_kmeans_area32` selection without calling any
segmentation entry point. Use an unreviewed `SegmentationReviewState`; the HTML
may record a later explicit inspection but grants no approval.

The resulting viewer contains both temporal frames for C0 and C1, 81 unchanged
source labels, 79 retained labels, and 2 border-rejected labels. Preserve a
companion manifest with input hashes, Module 9 label/filtering hashes, exact
configuration, and `segmentation.executed=false`. This operational recovery
does not change a segmentation profile, scientific threshold, raw TIFF, or
persisted label artifact.

### D083 - Browser-local draft storage must not gate Module 9 navigation (2026-07-20)

Treat `localStorage` as an optional convenience because browsers may deny it
for a self-contained `file://` artifact or it may contain malformed JSON. Catch
both load and save failures. On load failure, initialize an empty draft; on save
failure, keep channel selection, frame navigation, ROI visibility, and review
controls operational while displaying a storage-unavailable notice. Do not let
draft persistence failure prevent event handlers from being registered.

Regenerate the `Capture 1 + Position 2` viewer with this behavior. Verify that
the two raw frames differ in 356,257 C0 pixels and 356,845 C1 pixels and that
the four embedded channel/frame PNG payloads have distinct SHA-256 values.
This correction changes browser robustness only; it does not change any image,
ROI, filtering status, scientific parameter, or review provenance.

### D084 - Embed a static all-frame fallback in every Module 9 viewer (2026-07-20)

In addition to the interactive stage, write one labeled ordinary HTML image for
every C0 and C1 temporal frame. Keep this all-frame atlas visible below the
interactive review controls. It must not depend on JavaScript, local storage,
button handlers, or a network resource. This is a display fallback only: fixed
ROI overlays remain in the interactive stage and the atlas does not change or
duplicate any analytical calculation.

Publish the corrected Position 2 artifact under a new `v2` filename to prevent
an already-open local tab from serving cached markup. Verify that it contains
exactly four static panels (C0/F0, C0/F1, C1/F0, C1/F1), that viewer JSON and
JavaScript still parse, and that the complete test suite passes. No TIFF,
segmentation result, geometry decision, parameter, or review state changes.

### D085 - Accept the explicit Position 2 Module 9 inspection (2026-07-20)

Accept the user-exported `funes.module9.roi_review.v1` decision for `Capture 1
+ Position 2`. Two browser downloads were found and are byte-identical with
SHA-256 `7f4ac58780f832b79185f0989b3d25cdd401317e11e8c6e4a9350784ec4a96f1`.
Persist one canonical copy under
`outputs/module9_roi_review_capture1_position2/capture1_position2_roi_review.json`.

Strictly validate the field, source-label SHA-256, complete Module 8 filtering
SHA-256, effective `kmeans/provisional_working_kmeans_area32` selection, and
global selection source before applying it through D046. Record the field as
`manually_reviewed`. The optional inspector, inspection time, and note remain
null exactly as exported. Do not infer scientific sufficiency and do not grant
global approval.

Persist an application receipt containing the decision hash, validated source
hashes, final field status, and explicit false values for segmentation
execution, mask modification, parameter modification, and global approval. The
exported decision is sufficient to reproduce the immutable in-memory review
state in later sessions.

### D086 - Export the Position 1 Module 9 v2 viewer from persisted area-32 labels (2026-07-20)

For `Capture 1 + Position 1`, reuse the exact persisted K-means area-32 labels
from
`outputs/module7_ofat_review_20260714_kmeans/runs/field_001__variant_003/labels.npy`.
Require its recorded SHA-256
`36ab719aec5b736f56deb1c44f9286b023536ccc906780bad8934f51ae2ba9af`
and the documented C0/C1 TIFF hashes to match before export. Reconstruct only
the missing typed Module 8 boundary with the unchanged real-pair validation
configuration: `min_area_pixels=20`, no maximum area, and border-touching ROI
exclusion. Create current typed provenance for
`kmeans/provisional_working_kmeans_area32` without calling segmentation.

Publish `capture1_position1_roi_review_v2.html` with both temporal frames for
both channels and the JavaScript-independent four-panel atlas. The verified
result has 60 unchanged source labels, 56 retained labels, and 4 border-rejected
labels. Preserve a companion manifest with the exact input, source-label,
filtering, and generated-HTML hashes; record `segmentation.executed=false` and
the still-unreviewed D046 status.

The viewer prepares `Capture_1_Position_1_roi_review.json` for export only after
explicit manual confirmation. Do not pre-create or apply a decision that would
claim an inspection before it occurs. Viewer JSON and JavaScript must parse,
the atlas must contain exactly C0/F0, C0/F1, C1/F0, and C1/F1, and all four
embedded PNG payload hashes must be distinct. This export changes no TIFF,
persisted label, mask support, segmentation parameter, or review decision.

### D087 - Accept the explicit Position 1 Module 9 inspection (2026-07-20)

Accept the user-exported `funes.module9.roi_review.v1` decision for `Capture 1
+ Position 1` with SHA-256
`4c696164fcc0fa9d0f3b75cdf36789cc639288a36ff0c36f72de4d397a81ed23`.
Preserve the export under
`outputs/module9_roi_review_capture1_position1/Capture_1_Position_1_roi_review.json`.

Strictly validate the field, source-label SHA-256, complete Module 8 filtering
SHA-256, effective `kmeans/provisional_working_kmeans_area32` selection, and
global selection source before applying it through D046. Record the field as
`manually_reviewed`. The optional inspector, inspection time, and note remain
null exactly as exported. Do not infer scientific sufficiency and do not grant
global approval.

Persist an application receipt containing the decision hash, validated source
hashes, final field status, and explicit false values for segmentation
execution, mask modification, parameter modification, and global approval. The
exported decision and receipt reproduce the immutable in-memory review state
without changing any raw TIFF, persisted label artifact, ROI mask, or
segmentation parameter.

### D088 - Choose full or sampled position review separately for each experiment (2026-07-20)

For every experiment or explicitly bounded acquisition review, let the user
choose between two position-coverage modes:

1. **Review all positions.** Every position must receive its own manual
   inspection. Positions not yet inspected remain `unreviewed`; no global
   policy acceptance fills the gap.
2. **Review selected positions.** The user chooses a subset, inspects those
   positions, and may then perform a separate explicit D046 approval of the
   exact method/profile for the remaining positions in that experiment. Merely
   selecting or completing a subset never grants approval automatically.

Record the chosen mode and its experiment/acquisition scope. An approval from
one experiment must not silently cover another experiment. The user may still
inspect additional positions later, and D044 field overrides retain precedence.
Do not impose an automatic sample size or infer representativeness.

For every manually inspected position, retain navigation across all available
C0/C1 temporal frames with the same fixed ROI supports. Position-coverage
approval concerns only segmentation-review provenance; it does not approve
temporal QC, background, saturation, low-signal, FRET baseline, or other
scientific policies. A future many-position/many-timepoint orchestration layer
may need a more scalable delivery mechanism than one large self-contained HTML
file, but that implementation choice must preserve these two review modes.

D088 grants no current global approval. Both presently available positions
have already been inspected, so the current two-position dataset is fully
covered manually without using global-policy acceptance. The existing D046
backend is sufficient for an isolated review ledger, but experiment-scoped
orchestration and persistence remain a separate Module 9 extension.

### D089 - Isolate Module 9 review ledgers and approval by experiment (2026-07-20)

The D046 backend cannot safely represent multiple experiments in one state.
Although `PositionKey` carries an experiment label, D046 intentionally
normalizes it to `CapturePositionKey` and owns one global approval. Keep D046
unchanged for compatibility and place each D046 state inside a typed immutable
`ExperimentPositionReview` that fixes one experiment, its exact known
positions, its D088 coverage mode, and any selected subset. Collect those
owners in `ExperimentRoiReviewOrchestrator`, with exactly one ledger per
experiment and fail-closed routing for every position operation.

In `review_all`, every position is a required manual target and no global
remaining-position approval is permitted. In `review_selected`, require a
non-empty proper subset. Inspecting the last selected position never calls
approval and leaves every otherwise uncovered position `unreviewed`. Only a
later explicit `approve_remaining(...)` operation may call D046
`approve_global(...)`; reject that call until all selected positions have
their own inspections and reject it when no `unreviewed` position remains.
The wrapper only exposes approval within its registered experiment, so an
approval cannot cover an equal Capture + Position identity in another
experiment.

Preserve D044 field overrides and their precedence, every D046 manual
inspection and reviewer field, the approval inspection snapshot, and exact
method/profile/selection-source provenance. Restore the experiment identity
around each D046 query in an `ExperimentPositionReviewDecision`. Reject
inspections or configuration overrides outside the declared experiment
position scope.

For new experiment-scoped viewers, add the experiment label to the inspection
JSON field, local draft key, and download filename. Continue accepting the
older D081-D087 schema form without an experiment at the low-level loader, but
require the exact label at the new orchestration boundary. Generate a viewer
only for the requested position rather than one experiment-wide document;
that viewer must still contain every C0/C1 timepoint with the existing fixed
ROI layer. The orchestrator stores no frames and provides no ROI creation,
editing, or deletion operation.

D089 changes no current scientific approval and does not reinterpret D085 or
D087. It executes no segmentation, reads no real TIFF, and changes no mask,
profile, or parameter. Seven new tests use synthetic arrays only; the 23
focused review tests, `compileall`, and the complete 159-test suite pass.

### D090 - Persist the isolated Module 9 experiment-review state (2026-07-20)

Choose durable, versioned JSON persistence as the next bounded Module 9 block
after D089. Persist one complete `ExperimentRoiReviewOrchestrator`, including
every experiment's exact known positions, D088 coverage mode and selected
subset, D044 global selection and field overrides, and the complete D046
inspection and approval provenance. Keep the experiments isolated in the
serialized structure; never flatten their D046 ledgers into one shared state.

Use the exact schema identifier `funes.module9.experiment_roi_review.v1` and
record a canonical payload SHA-256. Loading is fail-closed: require the exact
schema and fields, verify the payload hash, reconstruct the existing typed
immutable contracts, and let all D044/D046/D089 consistency checks run again.
Do not repair, discard, or silently reinterpret stale inspections, approval
snapshots, duplicate scopes, invalid modes, cross-scope positions, or changed
selection provenance.

Snapshot export and load are state-neutral. They do not record a new
inspection, call global approval, infer sample sufficiency, or grant coverage.
The snapshot stores no TIFF frames or ROI masks and adds no viewer, ROI edit,
segmentation execution, real-data execution, profile, parameter, scientific
decision, or production dependency. Five focused synthetic tests,
`compileall`, the 28 focused Module 7/9 review tests, and the complete 164-test
suite pass.

### D091 - Add a snapshot-backed Module 9 review session (2026-07-20)

Choose a narrow application boundary as the next bounded Module 9 block after
D090. `ExperimentRoiReviewSession` composes the existing D089 orchestrator and
D090 snapshot APIs without replacing either contract. It may open a validated
snapshot, enumerate pending D088 manual targets in declared experiment order,
distinguish available from missing caller-supplied review material, export one
position viewer, apply one explicit inspection decision, and persist the new
immutable state.

Accept review material only as an already-produced typed `TiffPair` plus its
typed `RoiFilteringResult`, with an exact assigned experiment position already
registered by D089. Allow partial material delivery for scalable on-demand
review, but reject duplicate, unknown, unassigned, and cross-experiment
positions. Do not discover or read TIFF files, execute segmentation or other
analysis modules, or store frames or masks in the D090 snapshot.

Keep scientific approval outside this session. It exposes no
`approve_remaining` or D046 global-approval operation, cannot infer that a
sample is sufficient, and cannot change D044 selection. Applying a viewer
decision continues through the unchanged D089/D046 provenance and integrity
checks. ROI creation, deletion, drawing, relabeling, changed-mask persistence,
and a full analysis pipeline runner remain separate tasks.

D091 changes no scientific approval, ROI, mask, profile, parameter, or
production dependency. Five new tests use synthetic arrays only; the 33
focused Module 7/9 review tests, `compileall`, and the complete 169-test suite
pass without reading or segmenting a real TIFF.

### D092 - Add fail-closed reviewed position analysis orchestration (2026-07-20)

Choose a new Module 15 application boundary as the next bounded block after
D091. `run_reviewed_position_analysis(...)` composes existing Modules 5-13 for
exactly one already assigned, in-memory `TiffPair`. It consumes an existing
`ExperimentRoiReviewOrchestrator` decision and executes the exact D044/D046
selection from that experiment's isolated D089 ledger. It has no operation for
recording an inspection, calling approval, changing D044 selection, or writing
the D090 snapshot.

Fail closed on coverage. A position that is a D088 manual target must have its
own explicit D046 inspection even if a D044 override has primary status. Any
other position must already be covered by its isolated D089 decision; the
runner cannot infer sample sufficiency or scientific approval. Reject
unassigned, unknown, cross-scope, and conflicting-context identities before
analysis.

Require explicit channel-selection, segmentation-preprocessing, geometry,
quantitative-background, camera/QC, temporal-timing, biological-channel-role,
and FRET-baseline configurations. Do not create orchestration defaults for
these unresolved or profile-dependent scientific choices. Continue through
the existing typed Module 7-to-8, 8-to-10, 8/10-to-11, 8/10/11-to-12, and
12-to-13 handoffs, retaining fixed labels and exact D046 provenance. Stop
before downstream measurement if Module 8 retains no ROI.

Keep discovery, TIFF reading, experiment assignment, Module 9 viewing and
persistence, Module 14 export, multi-position scheduling, and real-data
execution outside this boundary. ROI creation, deletion, drawing, relabeling,
and changed-mask persistence remain a separate task. D092 grants no scientific
approval and changes no ROI, mask, profile, parameter, or production
dependency. Five focused synthetic tests, `compileall`, and the complete
174-test suite pass without reading or segmenting real TIFF data.

### D093 - Add fail-closed reviewed experiment analysis orchestration (2026-07-21)

Choose Module 16 as the next bounded block after D092. Add
`run_reviewed_experiment_analysis(...)` only for exactly one complete D089
experiment scope whose assigned `TiffPair` values are already in memory. Require
one explicit `PositionAnalysisConfig` per declared position; do not add shared
scientific defaults or infer profile-dependent settings.

Before the first D092 call, require exact pair and configuration coverage and
validate every isolated D046 decision. Reject missing, unexpected, duplicate,
unassigned, cross-experiment, conflicting-context, required-but-uninspected,
and otherwise uncovered positions. Execute in the immutable position order
declared by D089, regardless of caller input order, and preserve each D092
result and issue without rewriting provenance.

D093 creates no inspection or approval, changes no D044 selection or D090
snapshot, and cannot infer sample sufficiency or scientific acceptability. It
does not discover/read TIFFs, persist analysis results, call Module 14 export,
introduce concurrency, execute real data, or create/delete/draw/relabel/edit
ROI or masks. Five focused synthetic tests, `compileall`, the 10 focused
Module 15/16 tests, and the complete 179-test suite pass. No production
dependency changed.

### D094 - Export one completed reviewed experiment through Module 14 (2026-07-21)

Choose Module 17 as the next bounded block after D093. Add
`export_reviewed_experiment_workbook(...)` only as an adapter from one already
completed in-memory `ExperimentAnalysisResult` to the existing Module 14 D032
workbook exporter. Require the runtime-validated Module 16 result and construct
one `Module14PositionExport` for every position in the unchanged D089 order.

Pass the exact assigned `TiffPair` and exact Module 8, 10, 11, 12, and 13
result objects by identity. Preserve each D092 aggregate issue tuple unchanged;
do not recalculate, relabel, canonicalize, filter, or reinterpret any upstream
value. Pair-associated auxiliary metadata remains available to Module 14
through the exact `TiffPair`. Invoke `export_module14_workbooks(...)` exactly
once and require exactly one workbook because the Module 16 input represents
one experiment.

Return an immutable result retaining the source Module 16 object, the exact
ordered Module 14 position inputs, the Module 14 result, and the single
workbook path. Wrap export failures with the experiment identity while
preserving the original exception as the cause.

D094 introduces no scientific default or approval and changes none of
D044/D046/D089/D090/D091/D092/D093. It does not discover/read TIFFs, run or
rerun analysis, persist or mutate review state, create inspections or
approvals, infer sufficiency or acceptability, persist a separate analysis
bundle, schedule multiple experiments, activate real data, or
create/delete/draw/relabel/edit ROI or masks. Four focused synthetic tests,
`compileall`, the 14 focused Module 15/16/17 tests, and the complete 183-test
suite pass without reading `raw_data/` or changing a production dependency.

### D095 - Load and explicitly assign acquisition material through Modules 1-4 (2026-07-21)

Choose Module 18 as the next bounded block after D094. Add
`load_assigned_acquisition(...)` only to compose the existing Modules 1-4 for
one caller-supplied directory and caller-supplied typed experiment-assignment
rules. Execute TIFF discovery, auxiliary-text discovery, explicit D036
association, C0/C1 TIFF validation, and experiment assignment exactly once in
dependency order.

Return an immutable result retaining each exact typed stage result. Aggregate
stage issues without recreating or reordering them and add only an actionable
Module 18 error when no assigned pair exists. Refuse to expose
`assigned_pairs` whenever any error occurred, including a malformed or invalid
source outside an otherwise valid subset, so incomplete acquisition material
cannot silently enter D089/D093. Preserve warning-bearing complete loads and
the unchanged Module 3 auxiliary associations carried by Module 4. Continue to
derive experiment labels only from explicit rules, never from log text.

D095 creates no review scope, inspection, or approval and changes none of
D044/D046/D089-D094. It does not run Modules 5-17, choose scientific
configuration, persist review or analysis results, schedule multiple
experiments, invoke `raw_data/`, or create/delete/draw/relabel/edit ROI or
masks. Five focused temporary synthetic-TIFF tests, `compileall`, and the
complete 188-test suite pass. No production dependency changed.

### D096 - Initialize fresh experiment review scopes from D095 material (2026-07-21)

Choose Module 19 as the next bounded block after D095. Add
`initialize_acquisition_review(...)` only to bridge one already complete,
error-free D095 load into fresh D089 experiment owners. Require exactly one
caller-supplied typed configuration per assigned experiment, containing the
explicit D088 coverage mode and the exact D044 segmentation configuration.
Do not provide a scientific or coverage default at this boundary.

Preserve first-seen D095 experiment order and assigned-pair order within each
experiment. Retain the exact D095 load, exact ordered `TiffPair` objects, and
exact caller-supplied D044 configuration objects. Reject missing, unexpected,
or duplicate experiment configurations, duplicate assigned positions, invalid
selected subsets, cross-scope overrides, and any incomplete/error-bearing D095
load before returning an orchestrator.

Initialize every isolated D046 ledger with no inspections and no global
approval. Preserve D044 override precedence, but do not treat an override as a
manual inspection or as completion of a D088 manual target. D096 grants no
scientific approval and changes none of D044/D046/D089-D095. It does not
discover/read TIFFs, run Modules 5-17, record an inspection, approve remaining
positions, persist a D090 snapshot or analysis bundle, coordinate execution,
invoke `raw_data/`, or create/delete/draw/relabel/edit ROI or masks. Five
focused synthetic tests, `compileall`, 27 focused Module 18/19 and D089-D091
tests, and the complete 193-test suite pass. No production dependency changed.

### D097 - Coordinate reviewed analysis across one complete acquisition (2026-07-21)

Choose Module 20 as the next bounded block after D096. Add
`run_reviewed_acquisition_analysis(...)` only to compose the existing D093
one-experiment runner across every experiment in one exact D096 acquisition.
Require a caller-supplied D089 orchestrator that retains the exact D096
experiment order, D088 coverage scopes, positions, selected subsets, and D044
configuration objects, plus one explicit typed Module 15 scientific
configuration for every assigned position. Accept later review coverage only
as state already recorded by the caller; create or change no inspection or
approval at this boundary.

Preflight the complete acquisition before the first D093 call. Reject changed,
missing, reordered, or cross-scope experiment review state, changed D044
configuration identity, incomplete or unexpected per-position scientific
configuration, conflicting scoped context, an uninspected D088 manual target,
or any other uncovered D046 position. Then invoke D093 exactly once per
experiment in unchanged D095/D096 order, retaining the exact assigned
`TiffPair` objects, ordered in-memory results, and unchanged issues.

D097 grants no scientific approval and changes none of
D044/D046/D089-D096. It does not discover or read files, persist review or
analysis state, export workbooks, coordinate concurrency, invoke `raw_data/`,
or create/delete/draw/relabel/edit ROI or masks. Persisted analysis bundles, a
complete reviewed application runner, real-data activation, and ROI editing
remain separate tasks. Five focused synthetic-TIFF tests, `compileall`, the
42-test focused D089-D097 orchestration suite, and the complete 198-test suite
pass. No production dependency changed.

### D098 - Persist one complete reviewed analysis package without rerunning it (2026-07-21)

Choose Module 21 as the next bounded block after D097. Persist one already
completed `AcquisitionAnalysisResult` together with exactly one explicit
`PositionAnalysisConfig` for every completed position. Do not change D097 to
retain those configurations implicitly: require them again at the persistence
boundary, order them by the unchanged Module 20 result, and reject missing,
unexpected, or observably incompatible configuration records.

Use a ZIP container ending in `.funes-analysis.zip` with the exact schema
identifier `funes.module21.reviewed_analysis_package.v1`. Store a canonical,
domain-separated payload SHA-256 in `manifest.json`, require its exact ordered
member list, and store every NumPy array as a separate non-pickle `.npy` member
with size, dtype, shape, and SHA-256 validation. Encode only known FUNES typed
contracts, enums, paths, containers, scalars, and non-object arrays; never use
`pickle` or import a type named by untrusted package data. Preserve shared
object references so reconstructed Module 7-to-8 provenance, D095/D096 pair
identity, D044 configuration identity, review inspections/approval state, and
ordered issues remain internally coherent. Run every existing dataclass and
orchestration invariant again during load, and fail closed on unknown schemas,
types, fields, references, members, hashes, or incoherent values.

Package export and load are state-neutral. They create no inspection or
approval, confer no scientific acceptance or sample-sufficiency conclusion,
change none of D044/D046/D089-D097, and do not discover/read TIFFs, rerun any
analysis module, invoke `raw_data/`, export a workbook, or create, delete,
draw, relabel, or edit ROI/masks. Five focused synthetic tests, `compileall`,
and the complete 203-test suite pass. No production dependency changed.

### D099 - Compose the complete reviewed application without implicit activation (2026-07-21)

Choose Module 22 as the next bounded block after D098. Add
`run_reviewed_application(...)` to compose only existing typed boundaries for
one caller-supplied acquisition root: D095 loading and explicit assignment, a
strictly loaded existing D090 review snapshot, D096 scope reconstruction, D097
reviewed acquisition analysis, D094 workbook export once per experiment, and
D098 package persistence once for the complete acquisition.

Require the acquisition root, Module 4 assignment rules, D090 snapshot, every
per-position Module 15 scientific configuration, and a new output directory
explicitly. Derive D096 experiment setup only from the snapshot's existing
D088 mode, selected subset, and exact D044 configuration objects. Require the
snapshot experiment order and scope to match D095 and let the unchanged D097
preflight reject any required-but-uninspected or otherwise uncovered position
before the first D093 call. The runner exposes no inspection or approval
operation and never repairs, completes, or scientifically interprets review
state.

Preserve the review-snapshot path and SHA-256 and reject a snapshot that changes
while being loaded. Retain the exact typed D095, D096, D090, D097, D094, and
D098 results in one immutable application result. Publish D094 workbooks under
`workbooks/` and the complete package as
`reviewed_analysis.funes-analysis.zip` inside one new caller-supplied output
directory. Build both in private staging and publish the directory only after
all artifacts succeed; never overwrite an existing destination.

D099 adds no scientific default, inspection, approval, sample-sufficiency or
acceptability conclusion, real-data authorization, ROI/mask editing, schema,
workbook layout, or production dependency. It has no default acquisition path
and does not activate `raw_data/`. Five focused synthetic-TIFF tests,
`compileall`, the focused 25-test D095-D099 suite, and the complete 208-test
suite pass without reading a real TIFF.

### D100 - Design explicit single-attempt real-data activation (2026-07-21)

Choose Module 23 as one design-only block after D099. Put a future explicit
authorization boundary before any acquisition-root access and before the one
permitted D099 call. Separate existing D044/D046/D089 review coverage,
operational activation authority, explicit Module 15 scientific configuration,
and later scientific interpretation. Activation creates none of the other
three and cannot repair or complete them.

Require a versioned immutable plan with canonical SHA-256 that binds a unique
activation ID, `evidence_generation_only` purpose,
`scientific_status = not_approved`, the exact expected ordered acquisition
scope and filenames, assignment rules, D090 snapshot path/hash, exact
per-position configuration bundle/hash, absent final output, separate new
attempt-audit destination, exactly one D099 call, and no retry. Validate the
plan and a later explicit user activation statement before listing, hashing,
or opening the acquisition root. Reserve the activation ID with an immutable
started receipt; a started, failed, or completed ID is never reusable.

After authority validation, require exact source inventory and hashes, unchanged
D090/configuration inputs, exact scope, and the existing D095-D097 fail-closed
checks. D097 retains its unchanged D088/D046 coverage semantics: activation is
not an inspection or global approval. Invoke unchanged D099 at most once in
private staging. Before atomic final publication, require exact result scope,
unchanged raw/auxiliary/snapshot/configuration hashes, D098 verification, D094
workbook hashes, an actual call count of one, and a completed receipt preserving
the existing review statuses and explicit not-approved scientific state. A
failure publishes no completed destination, records a failed receipt, and
quarantines any incomplete evidence; retry requires a new reviewed plan and
authorization.

D100 implements no contract or runner and grants no current execution authority.
It does not list, read, hash, or execute `raw_data/`, create a concrete plan,
call D095/D099, approve D074 or any scientific configuration, add or modify a
D046 decision, infer acceptability/sufficiency/representativeness, edit an ROI
or mask, change D044/D046/D089-D099, or add a dependency. The complete design
is `docs/MODULE_23_REAL_DATA_ACTIVATION_BOUNDARY_DESIGN.md`. A later
implementation-only block must use synthetic TIFFs and temporary paths; a still
later explicit statement naming the reviewed plan ID and SHA-256 is required
for any real attempt.

### D101 - Implement the D100 typed boundary with synthetic verification only (2026-07-21)

Accept the explicitly requested implementation-only gate after D100. Add one
immutable, versioned Module 23 plan whose domain-separated canonical SHA-256
binds a unique activation ID, exact ordered Experiment > Capture > Position >
C0/C1 filenames, auxiliary filenames, Module 4 rules, D090 path/schema/hash,
the complete typed Module 15 configuration bundle and its independent hash,
new final/audit paths, fixed D099 artifact names, exactly one call, no retry,
`purpose = evidence_generation_only`, and
`scientific_status = not_approved`.

Add a separate typed authorization statement bound to the exact plan ID/hash.
Validate it, the fixed non-approving policy, absent/non-aliasing destinations,
configuration integrity, and unchanged strict D090 snapshot scope before any
acquisition-root listing, stat, hash, or read. Only then atomically reserve the
attempt ID with an immutable started receipt. A started, failed, or completed
audit directory permanently prevents reuse of that identifier.

After reservation, require the exact planned TIFF/auxiliary inventory and
hashes, invoke unchanged D099 at most once inside private outer staging, and
perform no fallback or retry. Postflight requires the exact ordered D099 scope,
unchanged source/snapshot/configuration hashes, a coherent loadable D098
package, D094 workbook paths and hashes, one actual call, and unchanged D046
review statuses. Publish only the complete contained application payload and
activation audit area. Failure publishes no final destination, writes a typed
failed receipt with the actual call count, and quarantines incomplete evidence.

Every receipt explicitly records that no inspection, approval, scientific
default selection, or ROI/mask edit occurred and that scientific status remains
not approved. Module 23 exposes none of those operations and leaves
D044/D046/D089-D100 unchanged. Six focused tests and the complete 214-test
suite use only small synthetic TIFFs and temporary paths. This block did not
list, read, hash, or execute `raw_data/`, create a concrete real activation
plan, reserve a real activation ID, call D099 on real data, grant operational
authority for a future plan, approve a scientific configuration, add a
dependency, or implement ROI editing. A later reviewed concrete plan and a
separate explicit statement naming its exact ID and SHA-256 remain mandatory
before one real attempt.

### D102 - Design auditable ROI revision before a concrete Module 23 plan (2026-07-21)

Choose manual ROI/mask revision as independent Module 24 before preparing a
concrete Module 23 activation plan for the intended corrected-mask workflow.
D101 remains validated and operationally coherent, but its version-1 plan
binds only the existing D090 state and Modules 5-15 configuration; it cannot
bind a manually revised mask. D061 and D074 also preserve known whole-cell
coverage limitations in the provisional automatic segmentation. A concrete
plan now would therefore freeze an automatic-mask-only run rather than the
workflow that needs correction. This sequencing does not prohibit a future
automatic-mask evidence run and grants no real-data authority.

Place Module 24 after Module 8 and before Modules 10-13. Preserve the exact
automatic segmentation and filtering result, then allow only explicit,
replayable add, delete, replace, and restore operations with stable existing
labels, monotonically allocated new labels, non-reused deleted labels, exact
source/output hashes, editor/time/reason provenance, and strict finalization.
Apply the one finalized mask unchanged to every temporal frame in C0 and C1,
recalculate geometry under the same explicit policy, and recompute background,
QC, temporal intensities, and FRET from that final mask. Never mix automatic-
mask and revised-mask downstream results.

Keep Module 9 and D046 read-only inspection/coverage semantics unchanged. An
edit is not an inspection, global approval, profile approval, or scientific
acceptability conclusion. The first implementation block is backend-only and
synthetic: immutable contracts, deterministic replay, strict JSON persistence,
and failure validation. Interactive editing, position-runner integration,
analysis-package/export propagation, and Module 23 binding are later separate
blocks.

Before any concrete Module 23 plan uses revised masks, add and synthetically
validate a versioned activation-plan extension binding each position to either
the explicit absence of a revision or the exact finalized Module 24 artifact
path/hash. D100/D101's later exact-ID/SHA-256 authorization remains mandatory.
This decision reads, hashes, segments, and analyzes no real data, implements no
code, creates no activation plan or ID, grants no authority or scientific
approval, and adds no dependency. The complete design is
`docs/MODULE_24_AUDITABLE_ROI_MASK_REVISION_DESIGN.md`.

### D103 - Implement the finalized Module 24 revision backend (2026-07-21)

Implement only D102's first backend block. Use immutable v1 contracts for the
exact Experiment + Capture + Position scope, image shape, Module 7 source-label
SHA-256, complete Module 8 filtering SHA-256, ordered reasoned operations,
editor identity, caller-supplied timezone-aware finalization time, optional
parent revision hash, domain-separated canonical revision SHA-256, and a
complete input/output operation trace.

Start each root revision from the exact Module 8 retained mask. Permit only
delete of a present label, replacement of one present label's pixel support,
addition with a fresh label greater than every original or earlier revision
label, and explicit restoration of a Module 8-rejected original label from its
unchanged Module 7 support. Reject overlap, empty or duplicate supports,
out-of-bounds coordinates, unknown/deleted/reused labels, changed shape,
non-`int32`-compatible labels, stale scope or hashes, unchanged replacements,
and revisions whose final edited mask equals their input. A child revision must
name and receive its exact finalized parent; allocated labels remain monotonic
even when an earlier added label was later deleted.

After deterministic replay, recalculate geometry with the exact original
`RoiGeometryFilterConfig`. Retain the exact original `SegmentationResult` and
`RoiFilteringResult`, the immutable complete edited label image before policy,
the immutable final measurement image after policy, every geometric record and
issue, and canonical hashes for all boundaries. Only a finalized revision may
replay or persist for future quantitative use; this decision does not yet wire
that mask into Modules 10-23.

Persist one finalized result as strict JSON schema
`funes.module24.roi_revision_artifact.v1`. Reject duplicate or unknown fields,
non-standard JSON numbers, unsupported schemas, altered payload/revision
hashes, and even rehashed mask or audit changes. Loading requires the exact
caller-supplied Module 7/8 objects and position, reconstructs the immutable
revision, replays it, and compares the complete revision, masks, trace, and
geometric audit using type-exact JSON equality.

Fifteen focused tests use only synthetic masks and temporary paths; the full
229-test suite passes. The replay tests explicitly prove that Module 9/D046
inspection and approval APIs are not called and that original Module 7/8 masks
are unchanged. No `raw_data/` path was listed or read. This block adds no UI,
Modules 15-23 integration, activation plan or ID, real-data authority,
scientific approval, exporter change, or dependency. Module 24 remains in
progress because the later integration, human-facing finalization/editor, and
Module 23 binding blocks remain deferred.

### D104 - Integrate one optional finalized ROI revision in the position runner (2026-07-21)

Extend only the reviewed single-position runner boundary. Accept either no
Module 24 input or one finalized root `RoiMaskRevision`. Preserve the existing
automatic path unchanged when the input is absent. When present, replay the
revision against the exact automatic Module 7 segmentation and Module 8
filtering results created by the current run, after automatic geometry and
before Module 10. Reject draft, stale, wrong-scope, hash-mismatched, or invalid
revisions with `PositionAnalysisError`; never fall back to the automatic mask
after a revision was supplied, and never start quantitative background after
revision validation fails.

Keep the automatic `RoiFilteringResult` as independent provenance on
`PositionAnalysisResult` and retain the complete replayed `RoiRevisionResult`
separately. Expose the effective measurement geometry, mask source
(`automatic` or `manual_revision`), and finalized revision SHA-256. Modules
10-13 consume only that effective geometry: the automatic filtered mask when
no revision exists, or the revision's recomputed post-policy measurement mask
when one exists. Include the mask source and optional revision hash in the
downstream run context. Apply the no-retained-ROI guard only after optional
replay so a finalized add or restore is not blocked solely because automatic
Module 8 retained no ROI.

Three focused tests use only synthetic in-memory TIFF pairs and masks. They
prove backward-compatible automatic analysis, exclusive revised-label flow
through temporal intensity and FRET, exact dual provenance, unchanged D046
review state, and fail-closed draft/stale rejection before a bomb Module 10
strategy can run. This block adds no UI, persistence/path loading, revision-
chain orchestration, Modules 16-23 propagation, real-data access or authority,
scientific approval, exporter change, or dependency. Module 24 remains in
progress for those separate later blocks. `compileall`, 32 focused tests, and
the complete 231-test suite pass.

### D105 - Propagate optional finalized ROI revisions through Module 16 (2026-07-21)

Extend only the reviewed one-experiment runner after D104. Add an optional
mapping from `PositionKey` to `RoiMaskRevision` for any subset of the exact
D089 experiment scope. Absence of the mapping, or absence of a particular
position from it, preserves the prior automatic-mask path unchanged. Do not
require a revision for every position and do not infer one from a file or
shared default.

Preflight the complete supplied mapping before the first Module 15 call.
Require typed in-scope keys, typed values, exact equality between each mapping
key and revision source position, finalized state, and no parent revision hash.
This keeps D104's current one-finalized-root-revision boundary explicit and
leaves revision-chain orchestration separate. Pass the exact revision object
only to the matching position in immutable D089 order. D104 remains the sole
replay boundary against the current automatic Module 7/8 results and rejects
stale hashes or invalid operations without automatic fallback before Module
10 for that position.

Keep the existing `ExperimentAnalysisResult`: its ordered
`PositionAnalysisResult` values already retain automatic and revised
provenance, effective mask source, revision SHA-256, and exclusive downstream
measurements. Do not add export presentation, persistence or artifact-path
loading, UI, Module 20-23 propagation, real-data access, activation authority,
or scientific approval. Two new tests use only synthetic in-memory pairs and
masks. Together with the existing Module 24 tests they prove mixed
automatic/revised experiment flow, exact revision propagation, unchanged D046
state, and whole-mapping rejection of draft, wrong-key, and chained revisions
before any position call. `compileall`, 29 focused Module 15/16/24 tests, and
the complete 233-test suite pass.

### D106 - Propagate optional finalized ROI revisions through Module 20 (2026-07-21)

Extend only the reviewed acquisition runner after D105. Add an optional
mapping from `PositionKey` to `RoiMaskRevision` for any subset of the complete
D096 acquisition scope. Absence of the mapping, or absence of a position from
it, keeps the prior automatic-mask path. Do not load or infer revisions from
artifacts or require complete revision coverage.

Preflight the whole mapping before the first Module 16 call. Require typed
in-scope keys and values, exact equality between each mapping key and revision
source position, finalized state, and no parent revision hash. Partition the
validated objects by the unchanged D096 experiment and D089 position order,
then pass each exact object to the existing D105 Module 16 input. D104 remains
the only replay boundary against automatic Module 7/8 hashes and the only
place that can admit the revised mask to Modules 10-13.

Keep `AcquisitionAnalysisResult` unchanged because its nested Module 16/15
results already preserve automatic and revised provenance, mask source,
revision hash, and exclusive measurements. This block adds no export,
persistence or artifact/path loading, UI, Module 23 revision binding,
`raw_data` access, activation authority, or scientific approval. Two synthetic
tests prove mixed automatic/revised acquisition flow, exact propagation,
unchanged D046 state, and whole-mapping rejection of draft, out-of-scope,
wrong-key, and chained revisions before any experiment call. `compileall`, 36
focused Module 15/16/20/24 tests, and the complete 235-test suite pass.

### D107 - Version Module 21 persistence for optional ROI revisions (2026-07-21)

Extend only the existing Module 21 typed package boundary after D106. Use the
new exact schema identifier `funes.module21.reviewed_analysis_package.v2` and
the matching domain-separated v2 payload-hash domain because a completed
Module 20 graph may now contain Module 24 contracts and arrays. Do not silently
reinterpret D098's fixed v1 schema. The current loader remains fail-closed and
rejects v1 or any other non-current schema rather than attempting an
unreviewed migration.

Add the closed Module 24 revision and replay contract modules to the existing
safe codec registry. Preserve, reconstruct, and revalidate the optional
`RoiRevisionResult`, its finalized `RoiMaskRevision`, operation trace, edited
and measurement masks, automatic Module 7/8 provenance, shared object
identity, mask-source/revision-hash properties, and the already recomputed
Modules 10-13 results. Automatic positions continue to persist with no
revision, so one package may contain mixed automatic and revised positions.

Module 21 consumes only the already completed in-memory D106 result. It does
not load or export a standalone Module 24 artifact, rerun replay or analysis,
change D046 review state, export a workbook, add UI, bind Module 23, access
`raw_data/`, grant activation authority, or approve any scientific choice.
Synthetic tests cover the mixed v2 round trip, exact dual provenance and
shared identity, effective revised measurement mask, unchanged D046 state,
and explicit v1 rejection. `compileall`, 37 focused Module 15/16/20/21/24
tests, and the complete 237-test suite pass. No production dependency changes.

### D108 - Propagate optional ROI revisions through Module 22 (2026-07-21)

Extend only the existing D099 application-runner boundary after D107. Add one
keyword-only optional `roi_revisions` mapping to
`run_reviewed_application(...)` and pass it unchanged to Module 20. Preserve
the existing automatic path when the mapping is absent or omits a position.
Module 20 remains the single acquisition-wide authority that validates the
complete mapping before any experiment analysis, including scope, exact source
position, finalized state, and root-only status.

Retain the exact finalized Module 24 object in the in-memory Module 22 result
and let the already versioned Module 21 v2 writer persist the resulting mixed
automatic/revised graph. Do not load or export standalone revision artifacts,
add revision-chain/path consumption, or change replay and quantitative
semantics established by D104-D107.

This block does not extend Module 17/14 workbook presentation. D099's existing
workbook calls and atomic publication remain unchanged, while explicit
mask-source/revision-hash presentation stays pending as its own block. It also
adds no UI, Module 23 binding, `raw_data/` access, activation authority, or
scientific approval. Two synthetic Module 22 tests cover exact mixed
propagation through the v2 package, unchanged D046 state, absence of standalone
revision-artifact I/O, and fail-closed draft rejection before any experiment
analysis. `compileall`, 35 focused Module 15/16/20/21/22 tests, and the complete
239-test suite pass. No production dependency changes.

## Pending decisions

### P001 — Python environment

Resolved for the initial scaffold by D015. Revisit only if later dependencies
require a narrower Python version or a different environment workflow.

### P002 — TIFF axis normalization

Resolved for the current representative SlideBook export family by D035. New
higher-dimensional export structures still require inspection before adding
axis rules.

### P003 — Auxiliary text-file naming and association

Resolved for the inspected SlideBook `.log` family by D036. Other auxiliary
formats remain preserved but unassociated until representative examples define
an equally explicit and verifiable rule.

### P004 — Preliminary segmentation background

Module 6 defines the interface and conservative default. Select the preferred
production preprocessing/background estimator and profile parameters after
viewing representative images.

### P005 — Segmentation engine

Partially resolved by D022, D044, and D046. The five reviewed engines, their
order, default K-means selection, baseline profile name, field override
boundary, optional Cellpose architecture, and backend review workflow are
fixed. No engine is declared universally accurate. Profile calibration remains
pending; future GUI review controls are tracked in P019.

D052 limits the current scientific comparison for a future global selection to
K-means and Marker Watershed. Cellpose remains on standby, while Global Otsu
and P99 remain outside this comparison block without being universally
rejected. D060 limits the final comparison to K area `32`, and D061 records
that it is not yet acceptable on these examples and requires another causal
extension. D064 completes the exact two-call extension package, and D065
confirms that the tested foreground relaxation contributes but remains
insufficient and is not accepted. D066 closes that monotonic boundary branch.
D067 chooses a new, locally conditional or adaptive K-means causal mechanism,
and D068-D073 record its bounded implementation, execution, and review. D074
now selects unchanged K-means area 32 only as a provisional working profile so
downstream development can continue. No universally accurate,
representative-sample-validated, or complete-cell-coverage profile has been
selected, and the D071 local-background variant remains outside the working
profile.

### P006 — ROI size units

Partially resolved by D023 for Module 8: initial filtering uses configurable
pixel-area limits. Prefer µm² when pixel calibration is available; define
physical-unit conversion and fallback profile behavior in a later configuration
module.

### P007 — Border-touching ROIs

Resolved for Module 8 by D023: border-touching handling is configurable as
accept, flag, or exclude, with flagging as the default. Acquisition-specific
profiles may choose stricter behavior later.

### P008 — Quantitative background method

Partially resolved by D024 for the replaceable interface and initial
percentile implementation. Choose the production scientific method and
parameters after representative images are inspected; global, local, non-cell,
manual, and hybrid approaches remain open.

### P009 — Saturation exclusion policy

Partially resolved by D025 for the interface and decision scopes. Define
production saturated-pixel fraction thresholds, affected-frame count policy, and
profile-specific exclusion behavior after representative data review.

### P010 — Low-signal thresholds

Partially resolved by D025 for the initial background-aware metric: ROI-frame
background-corrected mean divided by background standard deviation, with
channel-specific configurable SNR thresholds. Define production threshold
values, baseline-window behavior, and channel-role-specific criteria after
scientific review.

### P011 — FRET channel mapping

Partially resolved by D027 and clarified by D043: Module 13 preserves an
explicit C0/C1 donor/FRET mapping as biological provenance, but that mapping no
longer defines the ratio orientation. The correct role mapping for each
production acquisition profile remains pending. The inspected SlideBook log names C0 as
CFPex/CFPem and C1 as CFPex/YFPem; D041 preserves C0 donor and C1 FRET for the
diagnostic report, but scientific confirmation is still required.

The C0/C1 ratio order is no longer pending: D042 confirms C0 numerator and C1
denominator for the manual workflow. This does not by itself resolve the
biological donor/FRET interpretation of those channels.

### P012 — FRET baseline and normalization

Partially resolved by D027 for Module 13: baseline frame indices and excluded
value handling are explicit calculation configuration. Production R0 windows
and profile-specific policies for missing, flagged, or excluded frames remain
pending scientific review.

### P013 — Export layouts

Review example `.xlsx` workbooks before choosing final Module 14 outputs. The
planning artifact is `docs/MODULE_14_EXPORT_EXAMPLES_PLAN.md`.

Resolved for the first exporter by D032 and D033. Future export variants or
companion formats should be treated as new decisions.

### P014 - Touching-cell segmentation behavior

Resolved in principle by D051: divide touching cells into individual ROIs when
the division can be performed reliably; otherwise retain one connected ROI and
quantify the cells jointly. The automatic criterion for deciding when a split
is reliable remains pending and must be validated before changing production
segmentation behavior.

### P015 - Module 14 example review preferences

Review the generated non-final workbooks in
`outputs/module14_review_examples_20260712/` and decide which organization,
visual formatting, and companion-file approach should become the basis for the
final Module 14 workbook specification.

Partially resolved by D030: the final specification should be based on a wide
ROI-as-columns layout where rows are elapsed-time timepoints, with visual
capture/position separators and experiment-level separation. Remaining
questions are tracked below.

Resolved for the first exporter by D032 and D033.

### P016 - Module 14 experiment-level packaging

Resolved by D032: use one `.xlsx` workbook file per experiment.

### P017 - Scientific interpretation of high provisional ratios

Superseded in part by D042: 2.77-10.86 was the inverted C1/C0 calculation and
must not be scientifically interpreted as the intended ratio. Camera scaling,
exposures/gains, optical correction requirements, and the production background
method still need review. D043 resolves the manual average-intensity definition
as background-corrected ROI mean and validates the corrected Module 13
orientation. D042 also confirms that the target ROI should outline the complete
visible cell, so the current C1-bright puncta are not an adequate production
segmentation result.

### P018 - Segmentation selectivity profiles

Partially resolved by D047 for the immutable one-factor-at-a-time grid and its
explicit execution/summary boundary. Select representative fields, execute and
visually review the variants, then calibrate any future `strict`, `medium`, and
`permissive` profiles. Do not register those names until that separate
scientific review is complete. The names will describe foreground selectivity,
not accuracy, and parameters must not be tuned per image.

D048 partially resolves the artifact boundary and records the first explicit
two-field K-means review package. Per-run human visual observations are now
recorded without assessing sample sufficiency, classifying variants, approving
a profile, or changing D046. Any conclusion about that field set, additional
selected methods/variants, and all profile calibration remain pending.

D049 withdraws Cellpose CP-SAM as the next complete block and defers it until a
separate session performs exactly one explicitly selected timed test and
defines an acceptable operational limit. It selects and completes the
two-field/nine-variant Marker Watershed package without assessing field-set
sufficiency, entering human observations, classifying variants, approving a
profile, changing the global K-means baseline, or using D046. Any scientific
conclusion, later method/field selection, Cellpose feasibility decision, and
all profile calibration remain pending.

D050 completes the required one-run operational check without adding review
coverage or a scientific conclusion. The cold-cache `benchmark_baseline` call
on `Capture 1 + Position 1` took `3003.7913557` seconds. A complete Cellpose
block may only be considered under the same 600 x 600 CPU configuration when
its conservative declared projection is no more than 12 engine-hours, which
permits at most 14 runs at this planning value. No complete block is selected
or authorized, and all scientific Cellpose evaluation remains pending.

The read-only follow-up synthesis in
`docs/MODULE_7_KMEANS_MARKER_WATERSHED_VISUAL_SYNTHESIS.md` covers all eight
K-means and nine Marker Watershed variants in the existing two-field packages.
It adds no scientific decision: it keeps sample sufficiency and
representativeness unassessed, selects no winner, changes no baseline or
profile, and does not use D046. It explicitly corrects the P2-R4 local
comparison because K baseline and K `minimum_object_area_pixels=32` have the
same binary mask inside that crop even though their complete-field masks and
label numbering differ.

D053 records that an unoutlined dim silhouette is not obligatorily a ROI by
appearance alone. D054 records that the area-32 components added in these two
reviewed fields are cells and should be retained in this comparison. D055
resolves both pure Marker Watershed `marker_min_distance_pixels = 8` divisions
as doubtful and therefore joint ROI under D051. D056 records that many valid
cells remain outside the identical baseline / distance-8 supports. No human
question remains from this three-question artifact review, but method/variant
selection and representative-field coverage remain pending.

A later read-only audit uses those D054-confirmed component supports as fixed
references across all 17 existing variants. K `minimum_object_area_pixels=32`
is the only variant that covers every saved reference support from both method
families, but the prior human record still reports omitted cells in P2-R1 and
does not accept its P1-R4 coverage. D057 advanced it as the sole final-review
candidate, D058 authorized the completed minimum extension, D059 classified
the area-16 additions as cells, and D060 kept only K area `32` in the final
comparison.

D061 records the final human outcome that K area `32` is not yet acceptable on
these examples because many cells are excluded and that another causal
extension is required. The saved masks confirm an area-filter cause only for a
subset: 64 to 32 pixels recovers 12 / 21 confirmed cells, whereas 32 to 16 adds
no foreground in P2-R1 and leaves P1-R4 unchanged. A residual
foreground/intensity-selection cause is therefore a hypothesis requiring a
separately reviewed design, not a confirmed causal conclusion or an authorized
run. Production selection and representative-field coverage remain pending.

D062 supplies that minimum design, D063 implements it with synthetic
verification, and D064 records the exact two-call real execution with area
fixed at 32 and saved area-32 references. D065 confirms that the relaxed
foreground boundary contributes to recovery in both focused regions but is
not sufficient for acceptable segmentation and introduces localized
specificity/bridging risk. The candidate is not approved; production
selection and representative-field coverage remain pending. D066 closes this
specific monotonic foreground-boundary relaxation branch without another run;
any future K-means investigation requires a new, separately justified
mechanism and causal design. D067 selects formulation of that new mechanism as
the next design block rather than reopening the unchanged K-means versus Marker
Watershed comparison. D068 defines the exact single locally
background-conditioned P20 mechanism and its recovery-versus-expansion audit
classes. D069 implements that exact candidate and trace and verifies them only
on synthetic arrays. Real execution, production selection, and
representative-field coverage remain pending and separately unauthorized.
D070 confirms that real execution, if later requested, must first receive its
own reviewed authorization design. D071 supplies that exact two-call,
fail-closed design without activating it. D072 completes the separately
requested typed package boundary with synthetic verification only. A later
separately authorized execution produced the immutable D071 package, and D073
verifies its manifest and records only bounded complete-field and fixed-region
human observations. D074 adopts unchanged K-means area 32 as a clearly named
provisional working profile without adopting D071, reopening a parameter
search, or claiming universal accuracy, sample sufficiency, complete cell
coverage, or representative-field coverage.

### P019 - Field-by-field segmentation review experience

Resolved for the backend by D045 and D046: review of every field is not
mandatory; representative-field inspections, explicit approval of one global
method/profile, D044 overrides, precedence, and review-status provenance now
have immutable contracts and queries. The backend deliberately sets no minimum
sample size and never approves a policy automatically. D081 now resolves the
single-field read-only viewer: it navigates C0/C1 temporal frames, displays the
exact fixed Module 7/8 labels and statuses, persists a local draft, and exports
one provenance-checked D046 inspection. Selection of representative fields and
global approval remain outside the viewer and require explicit orchestration.
Manual ROI deletion, drawing, new-label creation, and mask editing remain out
of scope until explicitly requested.

D085 and D087 record both fields currently available under `raw_data/` as
manually inspected for the global
`kmeans/provisional_working_kmeans_area32` selection. The exports say only
`decision: inspected`, contain no acceptance note, and explicitly grant no
global approval. The next unresolved D045/D046 boundary is an explicit
scientific-user choice whether to approve that provisional selection for
future uninspected fields. Do not infer this approval from inspection coverage;
D074's limitations and the absence of a representativeness claim remain in
force. No additional field is available locally for a broader sample.

D088 resolves the future coverage choice: each experiment must offer both
review-all and user-selected-subset modes. Subset review requires a separate
explicit approval before remaining positions become
`global_policy_accepted`, and approval scope must not spill into another
experiment. Multi-position orchestration, experiment-scoped persistence, and
scalable delivery were left as implementation work by D088; D088 itself does
not grant approval to any current or future uninspected field.

D089 resolves experiment-scoped orchestration and on-demand position delivery.
D090 resolves durable experiment-scoped review-state persistence with strict
typed reconstruction and integrity validation. D091 adds the bounded
snapshot-backed review session for pending-work reporting and caller-supplied
per-position material, while deliberately exposing no approval operation.
None of these decisions grants a scientific approval, changes the D074
provisional profile, or authorizes ROI editing. D092 supplies the reviewed
single-position Modules 5-13 runner, and D093 now composes it deterministically
over one complete, already loaded D089 experiment scope. D094 now adapts that
completed one-experiment result to the existing Module 14 workbook exporter
without rerunning analysis or changing review state. D095 now composes
discovery, auxiliary association, TIFF validation, and explicit experiment
assignment through Modules 1-4 with fail-closed access to complete assigned
pairs. D096 now constructs fresh D089 scopes from that material only when every
experiment has an explicit D088/D044 configuration, without creating an
inspection or approval. D097 now coordinates D093 across every experiment in
one exact D096 acquisition only after complete acquisition-wide review and
scientific-configuration preflight. D098 now resolves versioned persistence of
one completed reviewed analysis package without rerunning analysis. D099 now
composes the complete reviewed application runner from an explicit D090
snapshot through D095-D098 and D094, without adding an approval operation or a
default acquisition path. Explicit real-data activation and ROI editing remain
separate future work. D100 now defines the activation boundary without granting
authority or changing this scientific state. ROI editing remains a different
future module.

### P020 - Advanced user segmentation parameters

Decide how a future advanced user may inspect and edit engine parameters beyond
named profiles, including validation, provenance, reproducibility, and how such
custom configurations are distinguished from scientifically reviewed profiles.

### P021 - Explicit real-data activation

Partially resolved by D100 and D101. The authority, provenance, fail-closed,
single-call, no-retry, source-immutability, receipt, and not-approved-science
contracts are implemented and synthetically validated. No concrete real plan
or real activation ID exists, and no access to `raw_data/` is authorized. A
later concrete plan review and a separate explicit statement naming its exact
activation ID and SHA-256 remain mandatory before one real attempt. Manual
ROI/mask editing is not part of this decision. Under D102, a concrete plan for
the intended corrected-mask workflow waits for Module 24 integration and a
versioned Module 23 revision binding.

### D109 - Close D108 provenance presentation and finalized-artifact routes (2026-07-21)

Consolidate the independently integrated Module 24 human-finalization and
Module 22 finalized-artifact route with the narrow Module 17/14 export close.
The Module 24 finalizer writes one new strict v1 JSON artifact from a supplied
draft at a timezone-aware timestamp, deterministically replays it against the
exact automatic Module 7/8 provenance, reloads it, and compares trace, masks,
and hashes. It never overwrites an existing artifact; a failed post-write check
removes only the newly written, unverified destination. This is an
administrative audit record, not scientific acceptance or a D046 mutation.

Module 22 may resolve one explicit artifact path per in-scope position instead
of the existing in-memory route, but never both. It hashes the path before and
after strict loading/replay validation against unpublished automatic Module 7/8
results, retains the resolved path, artifact SHA-256, and revision SHA-256, and
then passes the verified root revision through the unchanged Module 20 route.
The published mixed graph remains the exact Module 21
`funes.module21.reviewed_analysis_package.v2` graph; no package migration,
replay, or change to D032 value sheets is introduced.

Module 17 must preserve each Module 16 result's effective `mask_source` and
optional `revision_sha256` in its exact Module 14 input. Module 14 records
those fields in a separate `roi_provenance` sheet, with a blank hash cell for
an automatic mask and the exact finalized revision hash for `manual_revision`.
This provenance is audit-only: it changes no numerical values, ROI labels,
workbook value layout, review coverage, activation authority, or scientific
status. Synthetic tests explicitly verify both fields, Module 21 v2 mixed
round-trip provenance, and Module 22's finalized artifact route. The focused
Module 14/17/21/22 run has 27 tests and the complete suite has 246 tests; no
`raw_data/` file was read, no UI or Module 23 work was started, and no
scientific approval occurred.

### D110 - Consume finalized Module 24 revision chains fail-closed (2026-07-21)

Implement only an isolated backend consumer for an explicitly ordered,
non-empty sequence of finalized Module 24 v1 JSON artifacts for one exact
automatic Module 7/8 position. It reloads and strictly replay-verifies every
artifact with the same automatic provenance. The first artifact must be a root;
every later artifact must declare the immediately preceding revision SHA-256 as
its parent. The immutable returned chain retains each resolved path, artifact
SHA-256, replay result, and terminal result; no analysis runner consumes it yet.

Reject non-path or empty input, repeated resolved paths before replay, malformed
or stale artifacts, an inverted chain, a skipped/forked parent, and a file whose
SHA-256 changes between pre- and post-validation reads. This is audit-only and
does not add UI, Module 23 binding, runner propagation, raw-data access,
activation, D046 mutation, approval, or a scientific conclusion. Five focused
tests use only synthetic masks and temporary artifact paths.

### D111 - Integrate only validated Module 24 chains in the position runner (2026-07-21)

Extend only the Modules 5--13 position-runner boundary with an optional
already-validated `RoiRevisionChainResult`. It is mutually exclusive with the
existing optional root `RoiMaskRevision` input and does not accept or load
artifact paths. Revalidate the chain structure at the runner boundary, compare
its terminal source identity with the automatic Module 7/8 provenance produced
in that same call, and fail before Module 10 if it is invalid, bifurcated, or
incompatible.

Retain the exact complete chain on `PositionAnalysisResult`, retain its exact
terminal result as `roi_revision`, and route Modules 10--13 solely through the
terminal geometry audit. This authorizes neither propagation to experiment,
acquisition, or application runners nor UI, Module 23 binding, raw-data access,
activation, approval, or a scientific conclusion. Tests use synthetic masks and
temporary artifact paths only.

### D125 - Publish FUNES Lite as a source-only reproducible release (2026-08-27)

Use `FUNES — FRET Unified Normalization and Extraction Suite` as the public
product identity. The standalone source entered `origin/main` in commit
`84a2a28` as a source-only release: source code, tests, build instructions,
package metadata, README, and license are public, but no prebuilt
distribution is part of the release. The formal documentation close is
recorded separately on `origin/main` in commit `058606f`.

Keep the `simple_results` worksheet exclusive to the Lite route and require
its explicit exporter opt-in. The reviewed Module 14 route retains its
established workbook sheets and behavior unchanged. The standalone executable
and ZIP remain generated artifacts, ignored by Git and not published. No
experimental data, analysis outputs, generated images, executables, ZIP files,
or other binaries were included.

This publication does not change the scientific status of FUNES Lite: the
route remains automatic and provisional, is not scientifically validated, and
does not become a reviewed or activated analysis path by being public.

### P022 - Manual ROI mask revision

Resolved for sequencing by D102 and for the first backend implementation by
D103. D104 integrates one optional finalized root revision in the position
runner and routes Modules 10-13 exclusively through its revised measurement
mask while preserving the automatic Module 7/8 provenance. D105 propagates an
optional per-position subset of those exact revisions through Module 16 after
complete structural preflight, and D106 propagates the same optional subset
through Module 20 after acquisition-wide preflight. D107 persists the mixed
automatic/revised acquisition graph through the versioned Module 21 v2
boundary while retaining dual provenance and shared identity. D108 propagates
the same optional subset through Module 22 and its v2 package publication.
D109 completes strict human artifact finalization, the mutually exclusive
verified Module 22 artifact-path route, and separate Module 17/14
`roi_provenance` presentation without changing value sheets. Module 24 now
provides immutable finalized/replayable contracts, exact automatic-mask binding, deterministic
add/delete/replace/restore semantics, geometry recomputation, strict JSON
persistence, and synthetic quantitative integration through one acquisition.
Interactive editing ergonomics, revision-chain propagation beyond the position
runner, and the versioned Module 23 revision binding remain separate future
blocks. No real activation authority or scientific acceptance exists.
