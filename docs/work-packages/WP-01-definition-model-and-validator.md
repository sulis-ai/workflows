# WP-01 — Definition model, schemas and validator

**Plan step:** A2 (schemas) + A3 (model, loader, expressions, validator, checkers) of sulis-ai/platform ADR-227's plan.
**Spec:** `docs/spec/process-definition.md` (v1 draft). **Needs:** `docs/use-cases/CATALOGUE.md`.

## Outcome

A definition written to the v1 spec can be loaded, type-checked and **refused for every reason the
spec lists**, with a clear message naming the rule, the node and the fix. Nothing executes yet.

## Scope

1. **JSON Schemas** (JSON Schema 2020-12) in `src/sulis_workflows/definition/schema/`:
   `profile.v1.schema.json`, `tool.v1.schema.json`, `control.v1.schema.json`,
   `process.v1.schema.json`, plus the three built-in profiles the spec names:
   `control-result@1`, `decision@1`. Closed objects everywhere (spec §1.4); closed values
   `SCREAMING_SNAKE_CASE` (§1.5).
2. **Model** `src/sulis_workflows/definition/model.py`: frozen dataclasses (or pydantic models) for
   Profile, Tool, Control, Process, and each node type (§4–§7).
3. **Loader** `load.py`: YAML and JSON, using the existing safe input limits in
   `src/sulis_workflows/domain/yaml_input_limits.py`; a document that fails its schema is refused
   with the schema path.
4. **Registry** `registry.py`: resolves `id@version` and caret ranges (§1.2) over an in-memory set
   of documents; an unresolved reference is refused.
5. **Expressions** `expressions.py`: the §8 grammar — a parser, a type checker against declared
   inputs, host inputs, state channels and step outputs, and a pure evaluator (the evaluator is
   used by tests now and by the engine later).
6. **Validator** `validate.py`: rules **V1–V15** (§14), each a separate, named function returning
   structured findings `{ rule, node, message, fix }`.
7. **Built-in checkers** `checkers.py` as `CODE` Tools (§5.2): `profile-conformance@1` and the
   `decision@1` evidence checker (§7.6: every `evidence[].path` is one of the gate's `reviewing`
   paths). Each with a passing and a failing example.
8. **CLI** `cli.py`: `sulis-workflows validate <files...>` (exit non-zero on any finding) and
   `sulis-workflows explain <file>` (lists nodes, loops with their budgets, gates with deciders,
   endings with their sentences). Register as a console script.
9. **CI:** add `ruff check`, `ruff format --check` and `mypy` on `src/sulis_workflows/definition/`
   to `.github/workflows/ci.yml`.

## Out of scope

The engine (next, runs, records, claims), converters, templates' expansion (validate only that a
template name is recognised is **also** out — templates come with the engine), changes to
`compiler/`, releases.

## Acceptance criteria

Each is a test.

- **A1.** For every rule V1–V15: at least one fixture that is accepted and one that is refused,
  and the refusal names that rule.
- **A2.** Spec Appendix A (grounded-inquiry) validates once fixtures exist for the Tools, Profiles
  and Controls it references; removing any one of them makes V2 refuse it.
- **A3.** Bad-but-conformant fixtures, each refused:
  - a route whose options look exhaustive but miss one enum value (V6);
  - a gate with `INDETERMINATE: { next: … }` (V9);
  - a `SKILL` Tool whose only control is a policy (V3);
  - a checker with only passing examples (V3);
  - a call that maps every child ending except `FORBIDDEN` (V10);
  - a loop with `budget: 0` (V8);
  - an ending with `says: ""` (V14);
  - an expression comparing an enum path with a value outside the enum (V5);
  - an enum value written in lower case (V1).
- **A4.** A loop with no `budget` validates and `explain` shows the default from §15 (10), read
  from one constant, not repeated.
- **A5.** The domain package imports nothing from `sulis.` and no vendor SDK (a test asserts this).
- **A6.** `pytest`, `ruff` and `mypy` pass on Python 3.10–3.12 in CI.

## Suggested PR sequence

1. Schemas + model + loader (A1 for V1).
2. Registry + expressions (V2, V5).
3. Validator rules V3–V15 with fixtures (A1, A3).
4. Checkers + CLI + Appendix A fixture (A2, A4).
5. CI lint and type checking (A6).

Each PR carries its own principal summary and run record (see `CLAUDE.md`).

## If the spec is wrong or silent

Do not resolve it in code. Propose the spec change in the PR, keep the code to the spec as written,
and flag it in the run record.
