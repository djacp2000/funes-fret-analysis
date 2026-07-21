# AGENTS.md

## Project purpose

Build a modular Python application for analyzing two-channel FRET time-series exported from SlideBook as TIFF files.

The program must be developed incrementally, one small module at a time. Maintainability and traceability are more important than rapid feature accumulation.

## Required project context

Before changing code, read:

1. `docs/PROJECT_SPEC.md`
2. `docs/MODULE_PLAN.md`
3. `docs/DECISIONS.md`
4. Any module-specific documentation and tests relevant to the requested task

Treat these files as the current project specification. Do not silently contradict them.

## Core data hierarchy

The logical hierarchy is:

`Experiment > Capture > Position > C0 / C1 > temporal frames`

Each `Capture + Position` has one paired C0/C1 acquisition.

Each TIFF contains a temporal sequence. SlideBook may internally label the pages as Z planes, time frames, pages, or another TIFF axis. Regardless of that internal labeling, this project treats the ordered images inside each TIFF as temporal frames.

Filename fields such as `XY`, `Z`, and `T` must be preserved as metadata, but they do not define the temporal sequence for the analysis.

## Engineering rules

- Keep modules small, cohesive, and independently testable.
- Work on only one requested module or tightly related module group per session.
- Do not implement later modules “while already here.”
- Avoid large files, large classes, and long functions.
- Prefer explicit data flow over hidden global state.
- Use typed data structures and clear interfaces between modules.
- Separate image I/O, metadata, segmentation, quality control, numerical analysis, visualization, and export.
- A replaceable component must be behind a stable interface. This especially applies to TIFF readers, background estimation, segmentation engines, ROI review, and exporters.
- Do not hard-code microscope-, camera-, objective-, or cell-specific thresholds in analysis logic. Put them in configuration profiles.
- Preserve raw filenames, metadata, auxiliary text, parameters, warnings, exclusions, and exclusion reasons.
- Never modify or overwrite raw TIFF or auxiliary source files.
- Keep raw measurements separate from corrected, ratio, and normalized measurements.
- Do not make scientific assumptions that are not recorded in `docs/DECISIONS.md`.
- Do not add a production dependency without explaining why it is needed and recording it.
- Prefer deterministic behavior. Record random seeds when a library uses randomness.
- Add unit tests for each module. Use small synthetic fixtures when real data are unavailable.
- Keep tests for earlier modules passing before completing a new module.
- Do not build the optional GUI/interactive ROI editor unless the active session explicitly requests it.
- Do not finalize Module 14 export formatting until example workbooks have been generated and reviewed.

## Session protocol

At the start of every coding session:

1. Inspect the repository and read the required project context.
2. State which single module is in scope.
3. Summarize the existing relevant implementation.
4. Identify unresolved decisions that materially affect this module.
5. Ask concise questions only when a decision is genuinely required. Prefer no more than three questions at once.
6. Do not ask the user to decide implementation details that can be safely encapsulated behind an interface or configuration option.

During implementation:

1. Make the smallest coherent change that satisfies the module’s acceptance criteria.
2. Keep changes localized.
3. Add or update tests.
4. Do not refactor unrelated working code unless necessary.
5. Do not continue into the next module.

Before ending the session:

1. Run the relevant tests.
2. Summarize files changed and behavior implemented.
3. Report tests run and any failures or limitations honestly.
4. Update `docs/MODULE_PLAN.md` status.
5. Add confirmed decisions to `docs/DECISIONS.md`.
6. Add unresolved questions to the pending-decisions section.
7. Provide a short suggested prompt for the next session.
8. Stop after the requested module is complete.

## Definition of done for a module

A module is complete only when:

- Its public responsibility and interface are clear.
- It does not depend on unfinished later modules.
- Expected and failure cases are tested.
- Errors contain actionable context.
- Relevant metadata and provenance are preserved.
- Documentation and decision records are updated.
- Existing tests still pass.

## Current scientific constraints

- Segment cells from the first temporal frame.
- Automatically choose the segmentation channel using a robust comparison of C0 and C1 signal; C1 will often be selected, but this must not be assumed.
- The same fixed ROIs apply to every temporal frame in both paired TIFFs.
- ROI size limits vary by objective, camera setup, and cell type, so they must be configurable.
- Saturation limits vary by camera mode; examples may be approximately 4095 or 65535, but the program must use metadata or a camera profile rather than infer the limit solely from TIFF dtype.
- Low-signal criteria must be background-aware rather than based only on a universal absolute intensity.
- Automatic drift correction is deferred. A later quality-control module may compare early and late frames and flag a cell or field.
- Interactive ROI inspection and deletion are desirable but optional and deferred from the initial version.
- Module 14 output format remains pending until example Excel layouts are reviewed.
