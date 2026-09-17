# sulis-workflows — agent instructions

This library is becoming the single process format and engine for every governed Sulis process
(sulis-ai/platform ADR-227, accepted). You are working for a principal with no technical
background. Technical decisions are yours: research, decide, record, proceed. Ask the principal
only about their world (users, business, risk appetite, budget, timeline), never about
implementation.

## Where authority lives

In descending order. Precedent in code is measured current state, never authority.

1. **`docs/spec/process-definition.md`** — the v1 format. Normative. It already applies the
   platform decisions below; follow the spec rather than re-deriving them.
2. **`docs/use-cases/CATALOGUE.md`** — the 65 needs the format must meet, with stable ids.
3. **`docs/use-cases/corpus.md` and `docs/use-cases/scenarios/`** — 50 real processes and 415
   declared-path scenarios. "Supported" means a process's scenarios run exactly as written.
4. **Platform decisions** (in sulis-ai/platform; read them if you have access, otherwise rely on
   the spec's application of them): `architecture/decisions/ADR-028` (decision vocabulary
   `PERMIT | DENY | INDETERMINATE`, gate kinds `APPROVAL | INPUT`), `ADR-022` (the published engine
   lacks the platform's permission check; a global Prometheus registry collision), `ADR-024`
   (permission strings are the host's grammar), `.architecture/sulis-concierge/adrs/ADR-227`.
5. **`docs/work-packages/`** — the current task. Do exactly its scope.

If the spec is silent or wrong, do not invent a rule in code: write the gap as a proposed spec
change in your PR and flag it in the run record.

## Principles (apply by name)

- **Ports and adapters.** The domain owns its ports and imports nothing outside itself. No
  platform (`sulis.*`) imports, no vendor SDKs in the domain.
- **Fail closed.** An incomplete definition is invalid, not a TODO. Unknown fields, unresolved
  references and unevaluable expressions are refused.
- **Survive the bad-but-conformant attack.** For every rule, write the definition that would pass
  a naive check and still be wrong, and make the rule refuse it. Every validation rule ships a
  fixture that must be refused; every checker ships a failing example.
- **Permission first.** Nothing runs, dispatches or decides without an authorization call through
  the policy port.
- **States are sentences.** Endings `says`, gates `asks`; never colour alone.
- **Hold conventions once.** Defaults live only in spec §15. Cite, don't restate.
- **Measure, don't author.** Claim conformance only where a test proves it.
- **Ground honestly.** Name a standard only if you read it or can name it precisely; otherwise say
  it is this format's own convention. Never cite "best practice".
- **Adopt the cheap seam now; defer the expensive guess.** Prefer reversible choices; keep data in
  portable formats.

## Working rules

- Tests first. Every change has tests; a validation rule has at least one accepted and one refused
  fixture.
- `pip install -e ".[dev]"` then `pytest`. CI runs pytest on Python 3.10–3.12; keep 3.10 compatible.
- Do not change `src/sulis_workflows/compiler/` (the LangGraph path, being deprecated) unless the
  work package says so.
- Do not add runtime dependencies without recording why in the run record; prefer the standard
  library, `pydantic` and `pyyaml`, which are already dependencies.
- **Open pull requests; never merge them. Never create tags or releases.** Both need the
  principal's approval.
- Keep PRs to one reviewable concern.

## Reporting

Two channels, never collapsed:

- **To the principal (PR description, top section):** at most 200 words, plain language, bullets.
  What changed, what it means, what is still open, and what happens if nothing is done. End with
  numbered actions: things only they can decide first, then what you found and left, then your
  recommendation labelled as opinion.
- **To the system:** a run record at `docs/runs/<ULID>.agent-run.json` that validates against
  `docs/runs/agent-run.schema.json` (decisions in MADR form with evidence tags, flags, what you
  measured, what you found and deliberately left, lessons, and one `conformance_claim`). Every
  numbered action in the PR resolves to an entry in the record.
