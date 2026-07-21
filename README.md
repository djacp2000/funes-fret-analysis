# FUNES FRET Analysis

FUNES is a modular Python project for analyzing two-channel FRET time-series
exported from SlideBook as TIFF files. The implementation is intentionally
incremental: each module should be small, testable, and documented before moving
to the next one.

## Current implementation

Modules 0-22 have validated bounded implementations. Module 22 composes an
explicitly supplied, already reviewed acquisition through analysis, workbook
export, and integrity-checked package persistence without granting review
approval or choosing scientific defaults. Manual ROI editing and explicit
real-data activation remain separate. The detailed responsibilities, current
scientific boundaries, and pending decisions are maintained in
`docs/MODULE_PLAN.md` and `docs/DECISIONS.md`.

Install the core package, including the classical segmentation dependencies:

```powershell
python -m pip install -e .
```

Cellpose CP-SAM is optional and loaded only when selected:

```powershell
python -m pip install -e ".[cellpose]"
```

The CP-SAM model weights are separate from the core install. Missing Cellpose,
model, or weights block that explicitly selected engine; FUNES does not silently
substitute a classical method.

## Tests

Run the current unit tests from the repository root:

```powershell
python -m unittest discover -s tests
```

## Session prompts

Initial project prompts are retained for traceability:

```text
AGENTS.md
SESSION_PROMPT.md
FIRST_SESSION_PROMPT.md
```

Recommended future use:

1. Start Codex from the repository root.
2. Confirm that it has read `AGENTS.md`.
3. For each session, copy `SESSION_PROMPT.md`, replace the module number/name,
   and add any session-specific instructions.
4. Start a new session for each module or small inseparable module group.
5. Keep `MODULE_PLAN.md` and `DECISIONS.md` updated so a new session does not
   need the full prior chat history.

The detailed specification intentionally lives under `docs/` while `AGENTS.md`
stays focused on durable working rules.
