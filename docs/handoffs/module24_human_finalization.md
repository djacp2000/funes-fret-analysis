# Module 24 human finalization handoff

## Scope

This isolated change adds a backend-only completion flow for one prepared
Module 24 human ROI revision draft. It uses no UI, `raw_data`, real activation,
scientific approval, Module 23 work, Module 22 consumption, or Module 14/17
presentation.

## Behaviour

`finalize_human_roi_revision_artifact` finalizes a caller-supplied draft at a
timezone-aware timestamp, deterministically replays it against the exact
Module 7/8 provenance, writes a new strict v1 JSON artifact, reloads it, and
compares its trace, masks, and hashes. It refuses to overwrite an existing
artifact. Failed post-write validation removes only the newly created,
unverified destination.

Completion is an administrative audit record, not scientific acceptance or a
Module 9/D046 review-state mutation.

## Integration

The change is confined to `roi_revision_finalization.py`, its synthetic test,
and this handoff. No shared planning or decision documents were edited.
