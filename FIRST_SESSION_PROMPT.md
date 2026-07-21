# Recommended first Codex session

Read `AGENTS.md`, `docs/PROJECT_SPEC.md`, `docs/MODULE_PLAN.md`, and `docs/DECISIONS.md` before doing anything else.

Work only on **Module 0: Repository scaffold and shared contracts**.

The goal is to create a minimal, clean Python project structure that will support the later modules without implementing TIFF reading, segmentation, background correction, FRET calculations, visualization, or export.

Before coding:

1. Inspect the repository.
2. Propose a compact package and test layout.
3. Identify only decisions that truly need my input now.
4. Ask no more than three concise questions. Avoid premature choices about GUI, Cellpose, Excel layout, or scientific thresholds.

Implementation constraints:

- Keep the scaffold minimal.
- Define only shared data contracts that are already justified by the specification.
- Do not create a giant universal data class.
- Do not add heavy scientific dependencies yet.
- Set up a test runner and at least one smoke test.
- Add basic formatting/linting only if it remains simple and explain the choice.
- Do not implement Module 1.
- Update the module plan and decision log after implementation.
- Run the tests.
- Finish with a clear summary and a ready-to-copy prompt for Module 1.
