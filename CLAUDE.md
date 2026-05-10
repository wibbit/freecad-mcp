# FreeCAD MCP — Developer Guide

Full operational documentation lives in `docs/`:

- **`docs/session_guide.md`** — session startup, workflow selection, sketch workflow order, `execute_code` patterns, RPC recovery, log file locations
- **`docs/freecad_concepts.md`** — document model, Part:: vs PartDesign:: vs Draft::, topology naming, placement, recompute
- **`docs/api_gotchas.md`** — API surprises with wrong/right examples (pad.Profile, ViewObject.Visibility, BSplineCurve, arc radians, etc.)
- **`docs/errors_and_workarounds.md`** — error index by symptom with log guidance and grep patterns

Start every session by reading `docs/session_guide.md`.

---

## Development Rules

**Update docs and tests alongside every change — not at the end.**

For every bug fix:
- Add an entry to `docs/errors_and_workarounds.md` (symptom → cause → fix → log to check).
- Add an entry to the `[Unreleased]` section of `CHANGELOG.md`.
- If the fix corrects a gotcha or API misuse, add or update the relevant entry in `docs/api_gotchas.md`.
- Do NOT add fixed bugs to `tests/INTEGRATION_TEST_PLAN.md` Known Bugs — that table is for open issues only.

For every new tool or feature:
- Add the tool to `docs/API_REFERENCE.md` with signature, parameters, and a JSON example.
- Add test cases to the appropriate `tests/test_plans/*.md` file.
- Add an entry to the `[Unreleased]` section of `CHANGELOG.md`.
- If the feature introduces new workflow order requirements, update `docs/session_guide.md`.

Commit doc and test updates in the same commit as the code change, or immediately after it.
