# WP-04 — External and composite dispatch: `EXTERNAL` and `TOOL` (composite) mechanisms

**Follows:** WP-02 (execution engine), D34 (WP-03a) — both mechanism kinds are refused today
(`V17`; `_advance_step` raises `EngineRefusal`), by design, until this work package answers the
two questions D34 explicitly left open.
**Spec:** `docs/spec/process-definition.md` §4.3 (mechanism kinds), §12.1 (dispatch-or-defer
split). **Needs:** WP-02 unmodified (`_advance_step`'s existing CODE-dispatch branch is the
template both new branches below follow).

## Why this shape

§4.3's own table is explicit about where each kind sits: `CODE` — "A function the host can call" —
`ref` a `module:function` path, checked by unit tests; `EXTERNAL` — "A service outside Sulis,
through a host adapter" — `ref` "an adapter id", checked by "the adapter's own contract tests".
§12.1 puts both on the same side of the dispatch-or-defer split ("`CODE`, `EXTERNAL` and
deterministic `PROCESS` steps ... are run by the engine before it answers"). The difference the
spec draws is not in *shape* (both are `ref: <string>`, resolved and called before the engine
answers) but in *what the string names* — a Python dotted path the engine's own process can
import directly, versus an opaque identifier a host-supplied adapter interprets however it likes.
That is exactly the difference `CodeToolPort` vs. a new, identically-shaped `ExternalToolPort`
already exists to express in this codebase's own port convention (`domain/ports/`, one Protocol
per distinct *kind* of external call, not one Protocol per call *shape* — `PolicyPort`/
`RecordsPort`/`ClaimsPort` are all "ask a yes/no or read/write a durable record" shape-wise, and
are still three separate ports because they answer three separate questions).

`TOOL` (composite) is unrelated in mechanism but adjacent in status: §4.3 calls it "child Tools in
order over shared values" (`composes: [{tool, inputs, output}, ...]`). D34 found two genuinely
open questions rather than one: what "shared values" means operationally, and whether a
non-deterministic composed child's own hand-off should surface transparently to the caller or stay
opaque. Both are answered below by pointing at machinery this repository has already built,
tested, and proven for the *same* underlying question elsewhere (§9.1's `result.outputs` mapping;
§9.3's nested-scope hand-off bubbling) — reuse, not invention, is available for both.

## Design: `EXTERNAL`

**New port, `domain/ports/external_tool.py`, `ExternalToolPort`** — the exact same shape as
`CodeToolPort` (`async def call(self, ref: str, inputs: dict[str, Any], *, platform_id: str,
run_id: str) -> dict[str, Any]`, the same `ToolTransientError`/`ToolPermanentError` pair carrying
the Tool's own declared error `code`), wired into `EngineContext` as its own field
(`external_tool: ExternalToolPort`), not reused as a second name for `CodeToolPort` itself — kept
distinct because the *compliance bar* differs (§4.3's own words: a `CODE` ref's contract is
"unit tests" the engine's own test suite could in principle exercise; an `EXTERNAL` ref's contract
is "the adapter's own contract tests," owned entirely by whichever host adapter interprets that
id — a boundary worth keeping visible in the type system, not just in a docstring, so a future
reader cannot accidentally wire a `CodeToolPort` stub where an `EXTERNAL` call was meant, or vice
versa). `_advance_step` gains an `EXTERNAL` branch immediately alongside the existing `CODE`
branch — same shape, different port, same "run before the engine answers" placement in the
dispatch-or-defer `if`.

**"Per adapter" is not "per-adapter-id port."** The single `ExternalToolPort.call(ref, ...)` is
one port, one method — the host's own adapter implementation is free to be a dispatch table
keyed on `ref` internally (routing "adapter:notify" one way and "adapter:crm-lookup" another), or
several concrete adapter classes composed behind one facade, or anything else; that routing is the
*host's* own business, exactly as `CodeToolPort`'s single `call(ref, ...)` already lets a host
route `mod:classify` and `mod:frame_question` to two entirely different Python functions without
the engine ever knowing or caring. Proposing a *port per adapter id* was the option D34 rejected
implicitly by naming it a spec-silent guess; this design closes that gap by choosing the option
that mirrors `CodeToolPort`'s own already-settled precedent instead of inventing a second shape.

## Design: `TOOL` (composite)

Walk `composes` in declared order. Each `ComposeItem(tool, inputs, output)` dispatches its own
named `tool` through the *ordinary* mechanism dispatch that Tool itself declares — `CODE` runs
inline, `SKILL` hands off, another `PROCESS` call recurses — reusing `_advance_step`'s own
dispatch-or-defer decision for each composed child rather than a bespoke composite-only dispatch
path. This is what makes "shared values" answerable without inventing new semantics: a new,
composite-call-scoped namespace, `compose.*` (parallel to `item.*` in WP-03, `steps.*` already in
every scope), holds each earlier `ComposeItem`'s own mapped `output` under the name it wrote it
under — `ComposeItem.output: Mapping[str, str]` maps ITS OWN Tool's output fields to
`compose.<name>` paths (mirroring exactly how a `STEP`'s own `out:` maps a Tool's output into
`state.*`, just into `compose.*` instead), and a *later* `ComposeItem.inputs` mapping may read
`compose.<name>` alongside the composite Tool's own `inputs.*`/`state.*`/`host.*` — the composed
sequence's own private, ordered scratch space, discarded once the composite dispatch finishes.

The composite Tool's own top-level `output:` (what the *whole* `TOOL`-composite Tool returns to
whatever `STEP` dispatched it) is filled the same way §9.1's own `mechanism.result.outputs`
already fills a `PROCESS` call's output — a `result.outputs: { name: compose.<path> }` mapping
(reusing `CallResult`'s own shape, or a `Mechanism.compose_result`-named sibling field with the
identical structure), evaluated against the final `compose.*` state once every `ComposeItem` has
run. This is the same pattern twice, not two patterns — the spec's own §4.3 vocabulary for `TOOL`
never needed its own `result:` field name invented; reusing `CallResult`'s shape verbatim (or
naming a field that is structurally identical) is the two-way door.

**A composed child's own hand-off surfaces transparently**, exactly as a nested `PROCESS` call's
does (§9.3) — decided here, closing D34's own second open question, rather than left for a future
pass: a composite Tool with a `SKILL` child hands off with its own nested scope
(`{scope}/{node_id}.compose[{i}]`, mirroring WP-03's own branch/item scope-suffix convention) so
`report()` can resume it directly. The alternative D34 named — staying opaque, as if the whole
composite were one atomic `CODE`-like unit — was rejected here because it has no real analogue
anywhere else in this format: every other multi-step construct this engine runs (`PROCESS` calls,
and WP-03's own `PARALLEL`/`FOR_EACH`) already bubbles a hand-off up transparently: treating
`TOOL`-composite as the one exception would be new, unprecedented behaviour invented for this one
mechanism kind alone, exactly what CLAUDE.md's "do not invent a rule in code" already refuses.

## Scope

1. `domain/ports/external_tool.py` — `ExternalToolPort` Protocol + `StubExternalToolAdapter`,
   contract tests only, mirroring `domain/ports/code_tool.py`'s own file shape exactly.
2. `engine/run.py` — `_advance_step` gains the `EXTERNAL` branch (dispatch via
   `ctx.external_tool.call`, otherwise identical to the existing `CODE` branch's own error
   classification / retry / control-check flow) and a `TOOL`-composite branch (`_advance_compose`,
   walking `composes`, threading `compose.*`, reusing `_advance_step`'s own per-child dispatch
   recursively for `CODE`/`SKILL`/`PROCESS` children).
3. `definition/model.py` — `Mechanism` gains (or reuses) a `compose_result: CallResult | None`
   field for the composite's own top-level output mapping (name TBD in the implementing PR; shape
   is `CallResult`'s existing one).
4. `definition/validate.py` — `V17`'s own refusal is *removed* for both kinds once real dispatch
   exists (it becomes dead code the moment this ships); new checks take its place: every
   `ComposeItem.tool` resolves (`V2`-style); the composite's own `result`-equivalent mapping is
   present when `output:` is non-empty (mirroring `V4`'s existing "unmapped required input/output"
   discipline).

## Out of scope

Any change to the `EXTERNAL` adapter's own internal routing (a host's own concern — this work
package builds the port, not any specific adapter behind it, exactly as `CodeToolPort` ships with
only a stub adapter). A composed child that is itself a `TOOL`-composite (nesting composites) —
the spec does not name this shape either way; refuse it explicitly at validation time until it is
asked for, rather than silently allow untested recursion.

## Acceptance criteria

Each is a test.

- **A1.** An `EXTERNAL`-mechanism `STEP` dispatches through `ExternalToolPort.call` before the
  engine answers (no `TOOL_STEP` hand-off ever produced for it) — the exact shape `CODE` already
  has, proven the same way WP-02's own A1 proved `CODE`.
- **A2.** A `TOOL`-composite with 2 `CODE` children: the second child's own `inputs` mapping reads
  a `compose.*` value the first child's own `output` mapping wrote; the composite's own top-level
  `output:` correctly reflects the final `compose.*` state.
- **A3.** A `TOOL`-composite whose one child is `SKILL` hands off with its own nested scope; a
  `report()` against that scope resumes the composite and continues to its own remaining children
  — the same shape `test_process_call_inline_hands_off_and_resumes_via_report` already proves for
  §9.
- **A4.** A composed child that fails (`PERMANENT` error / control failure) routes the *whole*
  composite Tool's own dispatch through the calling `STEP`'s own `on_error`/`on_control_fail` —
  proving a composite failure is not silently swallowed partway through `composes`.
- **A5.** `pytest`, `ruff` and `mypy` pass on Python 3.10–3.12 in CI for every new/changed module.

## Suggested PR sequence

1. `ExternalToolPort` + `EXTERNAL` dispatch (A1) — the smaller, more self-contained half; removes
   `V17`'s refusal for `EXTERNAL` only.
2. `TOOL`-composite dispatch (A2-A4) — removes `V17`'s refusal for `TOOL` once shipped.

Each PR carries its own principal summary and run record (see `CLAUDE.md`).

## If the spec is wrong or silent

§4.3 does not currently name `compose.*`, the composite's own top-level result-mapping field, or
the composed-child-hand-off-is-transparent rule — all three are proposed here, to be adopted as
real spec text (with their own Dn entries) only once the implementing PR has a working, tested
version to point at, not decided as final in this document.
