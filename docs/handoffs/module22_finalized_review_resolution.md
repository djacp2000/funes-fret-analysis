# Module 22 finalized-review artifact resolution

## Scope

This isolated change extends `run_reviewed_application(...)` with the optional
`roi_revision_artifact_paths` mapping. It preserves the pre-existing
in-memory `roi_revisions` mapping; a position may use one route only.

## Behavior

- Every supplied path is explicit, limited to the loaded acquisition scope,
  hashed before and after loading, and replay-validated through Module 24's
  strict artifact loader against its automatic Module 7/8 provenance.
- Module 24 requires those automatic objects for deterministic verification.
  Module 22 therefore runs an unpublished automatic preflight only when path
  inputs are present, then sends the verified root revisions into the existing
  Module 20 in-memory route for the one published analysis.
- The Module 22 result retains position, resolved absolute path, file SHA-256,
  and revision SHA-256 for every artifact route. The persisted Module 21 v2
  package continues to retain the mixed automatic/revised graph.
- Chains remain rejected by existing Module 20 validation. No Module 23,
  activation, UI, raw-data access, exporter change, or scientific decision is
  added.

## Files and verification

- `src/funes/reviewed_application.py`
- `tests/test_reviewed_application.py`

`python -m unittest tests.test_position_analysis tests.test_experiment_analysis tests.test_acquisition_analysis tests.test_reviewed_analysis_persistence tests.test_reviewed_application -v` passed: 37 tests.

## Integration note

Integrate this commit after the Module 24 human-finalization producer commit.
Resolve only documentary consolidation centrally; this branch intentionally
does not edit `MODULE_PLAN.md`, `DECISIONS.md`, or `SESSION_HANDOFF.md`.
