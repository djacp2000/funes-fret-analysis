# Session prompt template

Read `AGENTS.md`, `docs/PROJECT_SPEC.md`, `docs/MODULE_PLAN.md`, and `docs/DECISIONS.md` before doing anything else.

Work only on **Module [NUMBER]: [NAME]** in this session.

First:

1. Inspect the current repository and existing tests.
2. Summarize the relevant current state in a few sentences.
3. Compare the requested module with its acceptance criteria in `docs/MODULE_PLAN.md`.
4. Identify any decision that genuinely blocks correct implementation.
5. Ask me no more than three concise questions if a scientific or user-facing decision is required. Do not ask about details that can safely remain configurable or hidden behind an interface.

Then implement only the smallest coherent version of this module.

Requirements:

- Do not implement later modules.
- Keep files, classes, and functions small.
- Use typed interfaces and explicit data flow.
- Preserve provenance, metadata, warnings, and error context.
- Add focused unit tests, including failure cases.
- Use synthetic test data where possible.
- Do not overwrite raw data.
- Do not add a major dependency without explaining and documenting it.
- Run the relevant tests before finishing.
- Update `docs/MODULE_PLAN.md` and `docs/DECISIONS.md`.
- Tell me exactly what changed, what was tested, and what remains unresolved.
- End with a ready-to-copy prompt for the next recommended session, but do not begin that next module.

Additional instructions for this session:

[PASTE ANY SESSION-SPECIFIC DETAILS HERE]
