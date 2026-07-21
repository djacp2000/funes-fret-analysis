# Module 23 explicit real-data activation boundary design

## Status and authority boundary

This document defines the D100 boundary that may eventually permit one
caller-selected real acquisition to enter the already implemented D099
application runner. It is a design record only. It does not add an entry point,
read or hash an acquisition file, call D095 or D099, create an output, record a
D046 inspection or approval, or authorize a real-data attempt.

The boundary deliberately separates four facts that must never be conflated:

1. **Review coverage** is existing D044/D046/D089 state loaded from the exact
   D090 snapshot. D097 remains the authority that decides whether every field
   is covered for execution.
2. **Real-data activation authority** is permission for one exact operational
   attempt. It does not create review coverage and cannot repair a snapshot.
3. **Scientific configuration** is the exact caller-supplied Module 15
   configuration for each position. Explicit supply does not mean scientific
   validation or production approval.
4. **Scientific interpretation** occurs only in a later, separate human review.
   Successful execution or artifact publication is not an acceptability,
   sample-sufficiency, representativeness, or biological conclusion.

Until the unresolved acquisition profiles and scientific thresholds are
reviewed, the only admissible activation purpose is
`evidence_generation_only`. Every plan and receipt must state
`scientific_status = not_approved`.

## Required gates

The future workflow has three gates:

1. **Design gate (D100).** This document fixes the contract and exclusions. It
   grants no implementation or execution authority.
2. **Implementation-only gate.** A later explicit request may implement the
   typed plan, authorization, attempt, and receipt contracts and verify them
   with synthetic TIFFs and temporary paths only. It must not inspect or use
   `raw_data/`.
3. **Real-activation gate.** Only a later explicit user statement naming one
   reviewed plan identifier and SHA-256 may permit its single attempt. Passing
   tests, the presence of `raw_data/`, an existing D090 snapshot, completed
   D046 inspections, or a callable D099 runner cannot substitute for that
   statement.

No gate exposes `record_inspection`, `approve_global`, `approve_remaining`, or
any ROI/mask mutation operation.

## Future typed activation plan

The implementation-only block must define one immutable, versioned plan. Its
canonical payload and SHA-256 must cover at least:

- a unique `activation_id` and schema identifier;
- `purpose = evidence_generation_only` and
  `scientific_status = not_approved`;
- the explicit acquisition-root path, with no default and no special implicit
  meaning assigned to `raw_data/`;
- the exact expected ordered `Experiment > Capture > Position > C0/C1` scope,
  raw filenames, and auxiliary filenames;
- the exact ordered Module 4 assignment rules;
- the D090 snapshot path, schema, and expected file SHA-256;
- the exact typed Module 15 configuration for every expected position, encoded
  in a versioned bundle with its own canonical SHA-256;
- the exact D044 global selections and overrides expected from the snapshot,
  without copying them into a second editable source of truth;
- the final output directory, which must be absent;
- a separate new attempt-audit directory used to prevent reuse of the same
  authorization identifier;
- one-call/no-retry policy for D099; and
- the expected Module 22 artifact names and the activation receipt layout.

Paths must be resolved and compared without allowing an acquisition source,
snapshot, output, audit directory, or configuration bundle to alias another
role. The plan must contain no raw frame, segmentation label image, ROI mask,
or editable review state.

The plan is caller-authored input. The future boundary may validate it but must
not discover a convenient acquisition, choose assignment rules, construct
scientific configurations, select a D044 profile, complete D046 coverage, or
choose an output destination on the caller's behalf.

## Scientific-configuration declaration

Because several production choices remain pending, each position entry must
bind the exact existing `PositionAnalysisConfig` to a declaration that:

- names its acquisition/position scope and configuration-bundle hash;
- records the segmentation-channel, preprocessing, ROI-geometry, quantitative-
  background, camera/saturation, low-signal, timing, biological channel-role,
  baseline, and excluded/flagged-value policies supplied to Module 15;
- labels those values `not_approved` unless a later independent decision record
  says otherwise; and
- states that execution is for evidence generation, not production inference.

The activation boundary validates identity and completeness only. It must not
judge whether a threshold, background estimator, baseline window, channel-role
mapping, or provisional segmentation profile is scientifically appropriate.

## Authority preflight before source access

Before listing, hashing, opening, or otherwise reading any file under the
acquisition root, the future implementation must:

1. validate the exact plan schema and canonical SHA-256;
2. validate a separate explicit activation statement against the plan
   identifier and hash;
3. require `evidence_generation_only`, `not_approved`, exactly one D099 call,
   and no retry;
4. verify that the output and attempt-audit directories do not already exist;
5. verify the snapshot and configuration-bundle hashes without changing them;
6. reject path aliasing and any plan that requests inspection, approval,
   scientific-default selection, source modification, or ROI/mask editing; and
7. atomically reserve the unique attempt identifier with an immutable
   `attempt_started` receipt before source access.

A failed authority preflight performs zero acquisition-root reads and zero
D095/D099 calls. A previously started, completed, or failed activation
identifier is never reusable.

## Real-source and application preflight

Only after the authority preflight succeeds may the one attempt read the
acquisition. It must then:

- inventory and SHA-256 every planned TIFF and auxiliary source before D099;
- reject missing, additional, renamed, duplicate, or out-of-root planned
  sources rather than silently narrowing the acquisition;
- confirm that the ordered filename-derived scope matches the plan;
- preserve source files read-only and record their pre-run sizes and hashes;
- load the unchanged D090 snapshot and verify its path/hash again;
- require exact configuration coverage for the planned positions; and
- perform the existing D095-D097 fail-closed scope, assignment, D088 manual-
  target, and D046 coverage checks before the first Module 15 analysis.

The future wrapper must not weaken or duplicate D097's scientific-review
coverage semantics. In `review_all`, each required field still needs its own
inspection. In `review_selected`, any remaining field still needs the existing
experiment-isolated D046 approval recorded before activation. An activation
statement itself never satisfies either condition.

Any mismatch ends the attempt without a D099 call. The boundary must not
repair the snapshot, add an inspection, call approval, substitute a profile,
drop a field, regenerate configuration, or select a nearby source.

## Exactly authorized execution

If and only if both preflights pass, the future boundary may invoke
`run_reviewed_application(...)` exactly once with the plan-bound acquisition
root, assignment rules, snapshot, per-position configurations, and a private
staging destination. D099 remains unchanged and retains all D095-D099 checks.

The activation layer permits no automatic retry. If D099 raises or returns
incoherent evidence, the attempt stops. A retry requires a new plan, new
activation identifier, new explicit statement, and new output/audit paths.

No alternate runner, direct module call, partial-experiment run, fallback
engine, changed configuration, or additional output is authorized by the same
statement.

## Postflight, receipts, and publication

Before final publication, the future boundary must:

- require one coherent D099 result covering the exact planned ordered scope;
- verify the unchanged D090 and configuration-bundle hashes;
- re-hash every raw and auxiliary source and require equality with the pre-run
  inventory;
- verify the D098 package receipt and hash every D094 workbook;
- record the exact review statuses already present, including whether a field
  was manually inspected, explicitly overridden, or accepted by a pre-existing
  experiment-scoped global policy;
- record all explicit scientific configurations and preserve
  `scientific_status = not_approved`;
- write an immutable `attempt_completed` receipt binding the plan hash, source
  inventory, snapshot/configuration hashes, D099 evidence, artifact hashes,
  start/completion provenance, and actual call count of one; and
- atomically publish the activation directory only after every postflight
  condition passes.

The published layout must keep the unchanged D099 output as one contained
application payload and the D100 plan/receipts as a separate activation-audit
area. A future implementation may reconstruct only relocated path-bearing
D099 receipt objects after the final rename; it must retain the exact typed
analysis and review objects and may not rewrite their scientific provenance.

If preflight, D099, or postflight fails, no completed output may appear at the
planned final destination. The audit area must receive an immutable
`attempt_failed` receipt with the stage, actionable error, and actual D099 call
count. Any unpublished application payload is quarantined as failed evidence,
never presented as a completed result and never reused by another attempt.

## Required future activation statement

Real activation requires a later user statement substantively equivalent to:

> Authorize exactly one D100 real-data attempt for activation plan
> `<activation_id>` with SHA-256 `<plan_sha256>`. Permit the acquisition reads
> and exactly one D099 call bound to that plan, with no retry, substitution,
> repair, approval action, or ROI/mask edit. The run is for evidence generation
> only and its scientific status remains not approved.

The statement must be made after the concrete plan and implementation-only
contracts have been reviewed. "Continue," "run the pipeline," a path alone,
D099 alone, passing tests, or this design alone are insufficient authority.

## Explicit exclusions

D100 does not:

- implement a Module 23 entry point or data contract;
- list, read, hash, validate, segment, analyze, or export `raw_data/`;
- create a plan for the currently available fields or reserve an activation ID;
- authorize a real-data attempt, D099 call, or retry;
- add, infer, or modify a D046 inspection or approval;
- approve D074's provisional working profile or any Module 15 configuration;
- infer accuracy, whole-cell coverage, representativeness, sample sufficiency,
  biological meaning, or production readiness;
- change D044/D046/D089-D099, a schema, workbook layout, profile, parameter,
  raw file, saved artifact, or production dependency; or
- create, delete, draw, relabel, edit, or persist a changed ROI/mask.

Interactive or manual ROI editing remains a separate future task with its own
contracts, provenance, review, and authorization boundary.

## D101 implementation-only outcome

D101 implements the typed boundary described above and validates it exclusively
with small synthetic TIFFs and temporary paths. It adds no concrete real plan,
reserves no real activation ID, and grants no authority to access `raw_data/`.
One later reviewed concrete plan plus a separate explicit statement naming that
plan's exact ID and SHA-256 are still required before any real attempt.

The implementation preserves D044/D046/D089-D100 unchanged, exposes no review
approval or ROI/mask mutation operation, and records every synthetic receipt as
`evidence_generation_only` with `scientific_status = not_approved`.
