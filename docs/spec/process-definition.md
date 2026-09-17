# Process definition format — v1

**Status:** draft for review · **Decision:** sulis-ai/platform ADR-227 · **Requirement:** [`docs/use-cases/CATALOGUE.md`](../use-cases/CATALOGUE.md) (65 needs) proven against [`docs/use-cases/corpus.md`](../use-cases/corpus.md) (50 processes, 415 scenarios)

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119.

## 0. In one page

A process is built from **four primitives**:

| Primitive | What it is | IDEF0 / BPMN |
|---|---|---|
| **Tool** | A typed contract for one unit of work: typed **inputs**, the **controls** its output is held to, a typed **output**, and the **mechanism** that does the work (code, a skill, an agent, another process, a composite of Tools, an external service). | ICOM box: I, C, O, M |
| **Step** | Binds one Tool into a process: maps run state onto the Tool's inputs and its output back into state. A step has no behaviour of its own. | Activity |
| **Gateway** | A flow node between steps: choose a route, go round a loop, split and join parallel work, repeat for each item, or wait for a person's decision. | Gateway |
| **Process** | Typed inputs and state, the steps and gateways, and its named endings (verdicts). A Process can be used as a Tool's mechanism, which is how one process calls another. | Process |

Five rules hold everything together:

1. **The engine only acts on data.** Routes, limits, preconditions and endings are expressions over typed state. Prose is for people and agents to read.
2. **Every Tool has controls, and they are checked.** After each step the output is checked by the deterministic checker registered for each control; the result is routed on.
3. **A person's decision is `permit`, `deny` or `indeterminate`.** What happens next is a route; who decided and why is provenance.
4. **Every loop is bounded.** A loop allows **10 passes by default**, unless the process or the loop sets another limit.
5. **Supported means as designed.** A process is supported only when each of its corpus scenarios visits exactly the expected steps, gates and verdict.

---

## 1. Documents, identity and versions

1.1 A definition is a YAML (or JSON) document with a header:

```yaml
apiVersion: sulis.workflows/v1
kind: Profile | Tool | Control | Process
id: grounded-inquiry          # kebab-case, unique per kind
version: 1.2.0                # semantic version
title: Grounded inquiry       # for people
summary: >-                   # for people; one or two sentences
  ...
```

1.2 A reference to another definition is `id@version`. The version MAY be a caret range (`^1.2`); it is resolved **once, when a run starts**, and the run records the exact versions it pinned. A run MUST NOT change definition versions while it is in flight. *(UC-VERSION)*

1.3 A published version is immutable. A change is a new version.

1.4 Every object in every schema is closed (`additionalProperties: false`). An unknown field is a validation error, not a silently ignored one.

1.5 Every closed value set in this format names the standard it comes from, or says none applies (§15).

---

## 2. Types and state

### 2.1 Types

A **type** is one of:

| Type | Meaning |
|---|---|
| `string`, `integer`, `number`, `boolean` | JSON primitives |
| `enum[a, b, c]` | one of the listed strings |
| `list<T>` | an ordered list of `T` |
| `map<T>` | string keys to `T` |
| `profile:<id>@<version>` | a value that conforms to a Profile (§3) |
| `any` | untyped; allowed only for host-provided inputs, and a Tool input of type `any` MUST NOT be read by an expression |

### 2.2 Run state

A run's state has four namespaces. Expressions and mappings address them by path.

| Path | Holds | Written by |
|---|---|---|
| `inputs.<name>` | The run's declared inputs | The caller, once, at start |
| `host.<name>` | Declared host-provided values (e.g. a topology index) | The host, at start *(UC-IN-AMBIENT)* |
| `state.<channel>` | Declared state channels | Step output mappings |
| `steps.<node>` | The latest attempt of a step: `.output.<name>`, `.verdict`, `.controls.<control>.passed`, `.attempt`, `.decided_by` (gates) | The engine |

A path that does not exist evaluates to *absent* (see `exists`, §8).

### 2.3 State channels

```yaml
state:
  findings:     { type: "list<profile:finding@1>", reducer: append }
  insights:     { type: "list<profile:insight@1>", reducer: upsert_by_id, key: id }
  confidence:   { type: "enum[grounded, partial, insufficient]", reducer: replace }
  revise_notes: { type: "list<string>", reducer: append, default: [] }
```

Reducers *(UC-STATE-CHANNELS)*: `replace` (last write wins), `merge` (maps, shallow), `append` (lists), `upsert_by_id` (lists of objects, replaced by `key`). A write whose value does not match the channel type is refused and recorded as a failed attempt.

---

## 3. Profile

A **Profile** is a named, versioned JSON Schema (2020-12) for a value that flows between Tools: a finding, an insight, a recommendation, an Instruction, a verdict. Profiles are the type system.

```yaml
apiVersion: sulis.workflows/v1
kind: Profile
id: finding
version: 1.0.0
title: Finding
grounded_in: W3C PROV (wasDerivedFrom) — every finding carries its source
schema:                      # JSON Schema 2020-12
  type: object
  required: [id, claim, source]
  properties:
    id: { type: string }
    claim: { type: string, minLength: 10 }
    source: { type: string }
  additionalProperties: false
checker: profile-conformance@1   # default; any code Tool registered as a profile checker
```

A Profile is also a **control** (§5): declaring an output of a profile type holds that output to the profile.

---

## 4. Tool

### 4.1 Shape

```yaml
apiVersion: sulis.workflows/v1
kind: Tool
id: interrogate
version: 1.0.0
title: Attack the claims, keep what survives
inputs:                                   # I
  candidates: { type: "list<profile:finding@1>", required: true }
  question:   { type: string, required: true }
output:                                   # O — one or more named outputs
  insights:  { type: "list<profile:insight@1>" }
  verdict:   { type: "enum[survived, dropped, revised]" }
controls:                                 # C — at least one
  - profile: insight@1
  - conventions: faithful-generation@1
mechanism:                                # M
  kind: agentic
  ref: skills/interrogate                 # the skill or agent definition the host runs
  allowed_tools: [ground-citations@1]
effect: query                             # query | mutation | side_effect
errors:
  - { code: source_unreachable, class: transient }
  - { code: brief_unanswerable, class: permanent }
evaluation:
  strategy: controls                      # derived from mechanism; see 4.4
```

### 4.2 Inputs and outputs *(UC-TOOL-TYPED-IO, UC-OUT-MULTI)*

- `inputs.<name>`: `type`, `required` (default `true`), `default`, `description`.
- `output.<name>`: `type`, `description`. A Tool MAY have several named outputs.
- A Tool that ends a process call (`mechanism.kind: process`) also has a `verdict` output (§9).

### 4.3 Mechanism kinds *(UC-TOOL-KINDS, UC-MECHANISM)*

| `kind` | What does the work | Deterministic | `ref` names |
|---|---|---|---|
| `code` | A function the host can call | yes | an importable callable, `module:function` |
| `skill` | A model following written instructions, no tool choice | no | a skill document |
| `agentic` | An agent session following instructions, free to choose its route within `allowed_tools` | no | a skill or agent definition |
| `process` | Another Process, run as a child | as the child | `process-id@version` |
| `tool` | A composite: child Tools run in order over a shared set of values | as its children | — (uses `composes`) |
| `external` | A service outside Sulis, through a host adapter | declared by the adapter | an adapter id |
| `human` | A person, through a gate | no | — (used only by gates, §7.5) |

`composes` (for `kind: tool`):

```yaml
mechanism:
  kind: tool
  composes:
    - tool: challenge-claims@1
      inputs: { candidates: candidates }
      output: { claims: claims }
    - tool: promote-survivors@1
      inputs: { claims: claims, candidates: candidates }
      output: { insights: insights, verdict: verdict }
```

`allowed_tools` belongs to the mechanism; the policy permitting the Tool to hold that set is a control.

### 4.4 Controls *(UC-TOOL-CONTROLS, UC-OUT-TYPED, UC-FIDELITY)*

- A Tool MUST declare at least one control.
- A control is `profile: <id@v>` or a reference to a **Control** document (§5): `conventions: <id@v>`, `fitness: <id@v>`, `policy: <id@v>`.
- Every control MUST resolve at validation **and** at run start. A control that does not resolve **refuses to run**.
- Every control MUST have a registered checker (§5.2).
- A Tool whose mechanism is `skill` or `agentic` and which has no control other than a policy is refused: its output varies, so without a bar it cannot be evaluated.

**Evaluation strategy** is derived, not chosen: `code` → exact output (examples with expected results); `skill`/`agentic` → conformance to its controls; `process` → the child's corpus scenarios; `tool` → its children's strategies; `external` → the adapter's contract tests.

### 4.5 Effect *(UC-TOOL-EFFECT, UC-SIDE-EFFECT-CLAIM)*

`query` reads only; `mutation` changes Sulis-held state; `side_effect` changes something outside (a repository, a message, a deploy). A step whose Tool is `mutation` or `side_effect` is **claimed before it runs** (§12.3).

### 4.6 Errors *(UC-RETRY, UC-FAILURE-MODES)*

`errors[]` lists expected error codes, each `transient` (worth retrying) or `permanent`. An unlisted error is `permanent`.

---

## 5. Control

### 5.1 Shape

A **Control** is a bar an output is held to, other than its profile.

```yaml
apiVersion: sulis.workflows/v1
kind: Control
id: faithful-generation
version: 1.0.0
type: conventions          # conventions | fitness | policy
title: Recommendations are entailed by the insights they cite
applies_to: output.insights
checker: check-entailment@1
grounded_in: Ji et al. intrinsic/extrinsic hallucination (arXiv:2202.03629)
```

- `conventions` — rules the content must follow.
- `fitness` — a measured threshold (e.g. a coverage score ≥ 0.8), with a severity `error | warning` (RFC 5424 subset).
- `policy` — who or what may do or permit something; evaluated by the host's `PolicyPort`, not by a code checker (§10).

### 5.2 Checkers

A checker is a `code` Tool that declares what it checks:

```yaml
kind: Tool
id: profile-conformance
mechanism: { kind: code, ref: sulis_workflows.checkers:profile_conformance }
checker_for: { control: profile }       # or { control: conventions, ref: faithful-generation@1 }
inputs:  { value: { type: any }, control: { type: string } }
output:  { result: { type: "profile:control-result@1" } }
controls: [ { profile: control-result@1 } ]
```

`control-result@1` is `{ control, passed: boolean, findings: [ { path, message, severity } ] }`.

**Checkers are built before the Tools they grade**: a checker is the evaluation of every non-deterministic Tool that names its control.

---

## 6. Process

```yaml
apiVersion: sulis.workflows/v1
kind: Process
id: grounded-inquiry
version: 1.0.0
title: Grounded inquiry
inputs:
  brief: { type: "profile:brief@1", required: true }
host_inputs:
  topology_index: { type: any }
state: { ... }                 # §2.3
defaults:
  loop_budget: 10              # passes per loop; this is also the format default
  repair_budget: 1
  retry: { max: 3, backoff: exponential, base_seconds: 2 }
  max_depth: 4
  criticality: standard
start: frame
nodes: { ... }                 # steps and gateways, by id (§7)
verdicts:                      # every way this process can end
  complete:     { outcome: success }
  insufficient: { outcome: success, description: "the evidence does not support an answer" }
  dropped:      { outcome: success }
  denied:       { outcome: stopped }
  escalated:    { outcome: stopped }
  failed:       { outcome: failure }
triggers: [ ... ]              # §11
execution_policy: guided       # strict | guided
```

- `verdicts` *(UC-STOP-NAMED, UC-STOP-HONEST)*: every ending is named; `outcome` is `success`, `stopped` (ended on purpose, needs a person to continue) or `failure`. An honest "insufficient" is a `success`.
- `execution_policy` *(UC-EXEC-POLICY)*: `strict` — the engine hands out only the declared route; `guided` — a person with permission MAY skip a step whose `criticality` is `trivial` or, with a recorded reason, `standard`. `critical` steps are never skipped *(UC-CRITICALITY)*.
- The engine adds three verdicts every process has: `escalated` (a limit ran out with no route), `failed` (a permanent error with no route), `cancelled` (a person stopped the run).

---

## 7. Nodes

Every node has an `id` (its key in `nodes`) and a `type`: `step`, `route`, `parallel`, `join`, `for_each`, `gate`. A node leaves by `next: <node-id>` or `end: <verdict>`.

### 7.1 Step

```yaml
nodes:
  interrogate:
    type: step
    tool: interrogate@1
    in:
      candidates: state.findings
      question: [state.framed_question, inputs.brief.question]   # ordered fallback (UC-IN-FALLBACK)
    out:
      insights: state.insights
      verdict: state.interrogation_verdict
    precondition: len(state.findings) > 0
    criticality: critical
    retry: { max: 2 }
    on_control_fail: { repair: 1, then: { end: failed } }
    on_error:
      brief_unanswerable: { end: insufficient }
    next: after-interrogate
```

- `in` *(UC-IN-OPTIONAL, UC-IN-FALLBACK)*: every **required** Tool input MUST be mapped. A mapping is a path or an ordered list of paths; the first present and non-empty value is used. An optional input MAY be unmapped. The validator type-checks each path against the input's type.
- `out`: maps Tool outputs to state channels. An unmapped output is still recorded under `steps.<id>.output`.
- `precondition` *(UC-PRECONDITION)*: an expression. When false the step is not run and the run takes `on_precondition_false` (default: `end: escalated`). A step whose Tool has `effect: side_effect` and that is marked `destructive: true` MUST have a precondition.
- `retry`: applies to `transient` errors only; defaults from `defaults.retry`.
- `on_error`: routes per error code; an unrouted permanent error ends the run `failed`.
- `on_control_fail` (§10.3): `repair` attempts (default `defaults.repair_budget`), then a route.
- A step MUST NOT have instructions of its own. Instructions belong to the Tool's mechanism (its skill or agent definition).

### 7.2 Route *(UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-DECIDE, UC-VERDICT-ROUTE, UC-PATHS)*

```yaml
  after-interrogate:
    type: route
    when:
      - if: state.interrogation_verdict == "survived"
        next: converge
      - if: state.interrogation_verdict == "revised"
        next: gather                         # a back-route: a loop (§7.3)
        loop: { budget: 2, counter: revise, on_exhausted: { next: converge } }
        invalidates: [synthesise]            # UC-COMPENSATE
      - if: state.interrogation_verdict == "dropped"
        end: dropped
    otherwise: { end: escalated }
```

- Options are evaluated in order; the first true one is taken.
- A route MUST have `otherwise`, **unless** every option tests one enum-typed path for equality and together they cover every value (the validator proves this).
- A **decision** is a step whose Tool returns a typed verdict, followed by a route on it. There is no separate "decide" node.
- **Alternative paths** are routes whose options lead into separate sub-graphs.

### 7.3 Loops *(UC-LOOP-BUDGET, UC-LOOP-MANY, UC-LOOP-WHILE, UC-TERMINATES-WHEN)*

A **loop** is any route option, gate route or `on_control_fail` route whose target can reach the node it leaves from (the validator detects this).

- Every loop has a budget: **`loop.budget`, else `defaults.loop_budget`, else 10.** The budget is the most times this loop may be taken in one run scope.
- Each loop has its own counter (`loop.counter`, default: `<from-node>-><to-node>`). Several loops in one process each count separately. Counters are rebuilt from durable records and survive a crash.
- `on_exhausted`: a route (`next` or `end`). Default: `end: escalated`.
- `counts`: `passes` (default — every time the loop is taken) or `failures` (only when the option was taken because a check failed).
- A check-first loop ("while") is a route before the body with the exit as one option and the body as the other.
- "Terminates when" is the exit condition written as a route option.

### 7.4 Parallel and join *(UC-PARALLEL, UC-JOIN)*

```yaml
  lenses:
    type: parallel
    branches: [market-lens, customer-lens, coherence-lens]
    join: lens-join
  lens-join:
    type: join
    policy: all_success          # all_success | any_success | all_complete
    next: lead-lens
```

- Every branch start is handed out; each branch runs until it reaches the join.
- The join runs **once**, when its policy is satisfied or can no longer be. `all_success` fails (→ `on_join_failed`, default `end: failed`) as soon as one branch fails.
- Branches write through channel reducers; two branches writing one `replace` channel is a validation error.

### 7.5 For each *(UC-FOREACH)*

```yaml
  per-sub-brief:
    type: for_each
    over: state.sub_briefs          # MUST be list-typed
    as: sub_brief
    do: run-sub-inquiry              # a step node; its `in` may read `item.sub_brief`
    max_concurrency: 4               # default 1
    collect: { output: insights, into: state.insights }
    join: all_complete
    next: synthesise
```

Each item runs in its own isolated scope. `collect` writes each item's output through the channel's reducer. Nesting `for_each` deeper than `defaults.max_depth` is refused.

### 7.6 Gate — a person decides *(UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-HANDOFF, UC-REFUSAL-MODE, UC-APPROVAL-AUTO, UC-GATE-CRITERIA, UC-GATE-AUDIT)*

```yaml
  sign-off:
    type: gate
    kind: approval                   # approval | input
    criteria: >-
      Every recommendation rests on a surviving insight and serves the brief's outcome.
    reviewing: [state.recommendations, state.confidence]
    policy: grounded-inquiry-sign-off@1     # who may decide; may permit automatically
    note_into: state.revise_notes
    on:
      permit:        { next: decompose-to-work }
      deny:          { next: recommend, loop: { budget: 3 } }     # send back within a limit
      indeterminate: { pause: true }                              # wait for a later decision
```

- **Verdicts are `permit`, `deny`, `indeterminate`** (OASIS XACML 3.0). Every verdict MUST have a route. There is no `revise` or `send back` verdict; sending back is a `deny` routed to an earlier node, and it is a loop (§7.3).
- A route on a verdict is one of: `next` (continue or send back), `end: <verdict>` (**halt**), `pause: true` (**pause** — the gate reopens and waits for a new decision), or `call: <process-id@v>` then `end` (**hand off** to another process).
- `kind: input`: the person gives an answer of `answer_type` (a type), written through `answer_into`; routes are on `answered` and `indeterminate`.
- `policy`: resolved by the host `PolicyPort` (§10.2) before the gate opens. The policy MAY return `permit` automatically. It MUST NOT permit automatically while any path named in `never_auto_when` is true (e.g. `state.confidence == "insufficient"`).
- **Provenance** is recorded on every decision: the verdict, `decided_by` (a person, or the policy and its basis), the note, the time, and which asking of the gate it was.
- A gate inside a called process is surfaced to the person through the top-level run (§9.3).

---

## 8. Expressions

Expressions appear in `if`, `precondition`, `never_auto_when` and fitness thresholds. They are pure: no calls, no I/O, no side effects.

```
expr     := or
or       := and ( "or" and )*
and      := not ( "and" not )*
not      := "not" not | cmp
cmp      := value ( ( "==" | "!=" | "<" | "<=" | ">" | ">=" | "in" ) value )?
value    := path | literal | "exists(" path ")" | "len(" path ")" | "(" expr ")"
path     := ident ( "." ident | "[" integer "]" )*
literal  := string | number | "true" | "false" | "null" | "[" literal ( "," literal )* "]"
```

- Paths are type-checked at validation against inputs, host inputs, state channels and step outputs. A path the validator cannot type is an error — **an expression that cannot be evaluated is refused**.
- `exists(p)` is true when `p` is present and not null. Comparing an absent value is false, never an error.
- An enum comparison against a value outside the enum is a validation error.

---

## 9. Calling a process *(UC-CALL, UC-CALL-RESULT, UC-CALL-DEPTH, UC-CALL-PATH, UC-CALL-NESTING, UC-CALL-GATES)*

### 9.1 As a Tool

```yaml
kind: Tool
id: run-grounded-inquiry
inputs:  { brief: { type: "profile:brief@1" } }
output:
  recommendations: { type: "list<profile:recommendation@1>" }
  verdict: { type: "enum[complete, insufficient, dropped, denied, escalated, failed]" }
controls: [ { profile: recommendation@1 } ]
mechanism:
  kind: process
  ref: grounded-inquiry@1
  path: null                         # optional: a route option the caller forces at the child's first route
  inputs:  { brief: brief }
  result:
    outputs: { recommendations: state.recommendations }
    verdicts:                        # child verdict -> this Tool's verdict
      complete: complete
      insufficient: insufficient
      dropped: dropped
      denied: denied
      escalated: escalated
      failed: failed
effect: query
```

- `result.verdicts` MUST map **every** verdict the child can end with (including the engine's `escalated`, `failed`, `cancelled`). The step that calls it MUST route every value of `verdict`. Either gap is a validation error.
- `path` MAY force the child's first route to a named option; otherwise the child decides.

### 9.2 Depth

A call runs the child in a child scope. Depth counts calls on the current chain. At `defaults.max_depth` (default 4) a further call is not made; the step takes `on_depth_exhausted` (default `end: escalated`). A process that can call itself MUST declare `on_depth_exhausted` explicitly.

### 9.3 Nesting and gates

Every answer the engine gives names the scope and definition it belongs to, at any depth. A gate in a child is surfaced to the person as a gate of the top-level run; deciding it resumes the child. A child MUST NOT permit its gates automatically unless its own policy says so.

---

## 10. Controls at run time *(UC-TOOL-CONTROLS, UC-OUT-TYPED, UC-OUT-REPAIR)*

### 10.1 After every step

1. The Tool returns its output (or an error, §7.1).
2. Each output is checked against its declared type (profile outputs by the profile's checker).
3. Each control's checker runs, producing a `control-result`.
4. If every result passed, the output is recorded, mapped into state, and the step leaves by `next`.
5. If any failed, the output is recorded **with its failed results** and is **not** mapped into state; the step takes `on_control_fail`.

### 10.2 Policy controls

A `policy` control is evaluated by the host's `PolicyPort` with the subject, the permission `<process>:<node>`, and the values named by the policy. It returns `permit`, `deny` or `indeterminate` and a basis. Trust tiers, thresholds and human grants are the host's; the format only names the policy.

### 10.3 `on_control_fail`

- `repair: n` (default `defaults.repair_budget`, 1): the Tool is invoked again with the failed results as additional input, at most `n` times.
- `then`: a route when repairs are used up (default `end: failed`). A `then` that goes back to an earlier node is a loop (§7.3).

---

## 11. Triggers *(UC-TRIGGER)*

```yaml
triggers:
  - { kind: timer, rrule: "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9", inputs: { ... } }
  - { kind: event, event: instruction.confirmed, inputs: { brief: event.instruction } }
  - { kind: state_entry, process: land-change@1, verdict: complete }
  - { kind: webhook, adapter: github, event: pull_request.opened }
  - { kind: branch_push, repository: host.repository, branch: main }
```

The library validates triggers; the host schedules and fires them through its `TriggerPort`. Timer rules use iCalendar RRULE (RFC 5545).

---

## 12. Engine semantics

This section is normative for any engine that runs `v1`.

### 12.1 Driving a run

A run is driven from outside, one call at a time:

- `next(run, scope)` → the next thing to do: `tool_step` (a non-deterministic step for the caller's agent session, with its resolved inputs, instructions ref and controls), `awaiting_decision` (a gate), `step_running` (claimed by another caller), or `ended` (a verdict). Deterministic steps (`code`, `external`, `process` whose child is deterministic) are run by the engine itself before answering.
- `report(run, scope, node, output | error)` → records the attempt, runs controls, and answers with `next`.
- `decide(run, scope, gate, verdict, note, decided_by)` → records the decision and answers with `next`.

Starting and resuming are the same call *(UC-RESUME)*. Nothing is held in memory between calls.

### 12.2 Records

Every attempt of every node is one write-once record keyed by `(run, scope, node, attempt)`, holding the inputs used, the output, control results, the verdict or error, who or what performed it, and start and end times. The engine numbers attempts; a caller never does. Loop counters, retry counts and progress are derived from records.

### 12.3 Claims *(UC-SIDE-EFFECT-CLAIM, UC-LEASE)*

Before a `mutation` or `side_effect` step runs, the engine writes an in-progress claim with a lease (default 15 minutes) under the same write-once guard. A running step renews its lease. A second caller finds the claim and is told `step_running`. An expired claim MAY be taken over; the takeover is logged as "may already have run".

### 12.4 Failures *(UC-RETRY, UC-FAILURE-MODES)*

Transient errors retry within `retry`; permanent errors take `on_error`, else end `failed`. A failure that needs a person is a gate, not a note.

### 12.5 Observers

The engine notifies observers (step recorded, gate opened, decision recorded, loop taken, run ended) only **after** the record is durable, and an observer failure MUST NOT fail the run.

---

## 13. Templates

Templates are patterns authors use often. Each expands into the four primitives before validation; `sulis-workflows expand` shows the result.

| Template | Expands to | Catalogue |
|---|---|---|
| `revise_loop` | step → gate (`deny` sends back with a budget) | UC-GATE-SENDBACK |
| `control_repair` | step with `on_control_fail` repair and a route | UC-OUT-REPAIR |
| `verification_spiral` | verify step (fitness controls per dimension) → route (pass / loop back / irreducible blocker → `end`) with a budget | UC-SPIRAL |
| `lens_triad` | parallel lens steps → join `all_complete` → lead-lens step → route on composite verdict | UC-LENS-TRIAD |
| `sequence_with_gates` | process-call steps in order, a gate after each marked `gate_after`, tail calls after the final gate, `optional` calls behind a flag route | UC-SEQUENCE, UC-OPTIONAL-BRANCH |
| `honest_stop` | route on a confidence verdict to `end: insufficient` | UC-STOP-HONEST |
| `handoff_contract` | a route after a step checking required outputs exist, with `block` → `end`, `warn` → record and continue, `skip` → continue | UC-HANDOFF |

---

## 14. Validation

A definition is valid only when all of these hold. Each rule has a conformance case.

| Rule | Refuses |
|---|---|
| V1 schema | unknown fields, wrong types |
| V2 references | any `id@version` that does not resolve: Tools, Profiles, Controls, checkers, policies, processes |
| V3 controls | a Tool with no control; a control with no checker; a `skill`/`agentic` Tool with only policy controls |
| V4 mappings | an unmapped required input; a mapping whose type does not match; an output mapped into an incompatible channel |
| V5 expressions | an expression that does not parse or whose paths cannot be typed |
| V6 routes | a route without `otherwise` that is not proven exhaustive |
| V7 reachability | a node that cannot be reached; a node with no way to end |
| V8 loops | a loop budget that is not a positive integer (a missing budget takes the default of 10) |
| V9 gates | a gate verdict with no route |
| V10 calls | a child verdict not mapped; a call verdict not routed; a self-reachable call with no `on_depth_exhausted` |
| V11 parallel | two branches writing one `replace` channel; a join not reachable from every branch |
| V12 for-each | `over` not list-typed; nesting deeper than `max_depth` |
| V13 side effects | a `destructive` step with no precondition |
| V14 verdicts | an `end` naming an undeclared verdict |
| V15 grounding | a closed value set with no `grounded_in` |

---

## 15. Defaults

| Setting | Default | Override |
|---|---|---|
| Loop budget (passes per loop, per scope) | **10** | `defaults.loop_budget` on the process; `loop.budget` on the loop |
| Loop exhausted | `end: escalated` | `loop.on_exhausted` |
| Repair attempts after a failed control | 1 | `defaults.repair_budget`; `on_control_fail.repair` |
| Control failure after repairs | `end: failed` | `on_control_fail.then` |
| Retries for transient errors | 3, exponential from 2 s | `defaults.retry`; `step.retry` |
| Unrouted permanent error | `end: failed` | `step.on_error` |
| Call depth | 4 | `defaults.max_depth` |
| Depth exhausted | `end: escalated` | `on_depth_exhausted` (required for self-reachable calls) |
| Precondition false | `end: escalated` | `on_precondition_false` |
| Join policy | `all_success` | `join.policy` |
| For-each concurrency | 1 | `max_concurrency` |
| Criticality | `standard` | `step.criticality` |
| Claim lease | 15 minutes, renewed while running | host setting |

There is **no default** for a route's `otherwise`, a gate's verdict routes or a call's verdict mapping: those are decisions an author must make.

---

## 16. Standards this format rests on

| Part | Standard |
|---|---|
| Tool as four arrows | IDEF0 / ICOM (FIPS 183) |
| Gateways, parallel, join | BPMN 2.0 (ISO/IEC 19510) |
| Decision verdicts | OASIS XACML 3.0 |
| Records and who did what | W3C PROV-O |
| Profiles | JSON Schema 2020-12 |
| Versions | Semantic Versioning 2.0.0 |
| Fitness severity | RFC 5424 §6.2.1 (two-value subset) |
| Timer triggers | RFC 5545 RRULE |
| Normative keywords | RFC 2119 |

---

## 17. Catalogue coverage

| Catalogue id | Section |
|---|---|
| UC-IN-TYPED, UC-IN-AMBIENT | 2.2, 6 |
| UC-STATE-CHANNELS | 2.3 |
| UC-IN-OPTIONAL, UC-IN-FALLBACK | 7.1 |
| UC-OUT-MULTI, UC-TOOL-TYPED-IO | 4.2 |
| UC-OUT-TYPED, UC-TOOL-CONTROLS, UC-FIDELITY | 3, 4.4, 5, 10 |
| UC-OUT-REPAIR | 10.3, 13 |
| UC-OUT-MODE | host: a `side_effect` Tool (e.g. `propose-change`) selected by a route on an input |
| UC-HANDOFF | 13 `handoff_contract` |
| UC-SEED-ARTIFACTS | 6 `inputs` typed as artifact profiles |
| UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-DECIDE, UC-PATHS, UC-VERDICT-ROUTE | 7.2 |
| UC-PREPHASE | 7.1 (a step before the first route) |
| UC-STOP-NAMED, UC-STOP-HONEST | 6, 13 |
| UC-LOOP-BUDGET, UC-LOOP-MANY, UC-LOOP-WHILE, UC-TERMINATES-WHEN | 7.3 |
| UC-OPTIONAL-BRANCH, UC-CYCLE-POLICY | 7.2 (route on a flag; route on a loop counter `steps.<node>.attempt`) |
| UC-PARALLEL, UC-JOIN | 7.4 |
| UC-FOREACH | 7.5 |
| UC-CALL, UC-CALL-RESULT, UC-CALL-DEPTH, UC-CALL-PATH, UC-CALL-NESTING, UC-CALL-GATES | 9 |
| UC-SEQUENCE, UC-EXEC-POLICY | 13, 6 |
| UC-GATE-* , UC-REFUSAL-MODE, UC-APPROVAL-AUTO | 7.6, 10.2 |
| UC-RETRY, UC-FAILURE-MODES, UC-COMPENSATE | 7.1, 7.2 `invalidates`, 12.4 |
| UC-PRECONDITION, UC-CRITICALITY | 7.1, 6 |
| UC-SIDE-EFFECT-CLAIM, UC-LEASE, UC-RESUME | 12 |
| UC-TOOL-RUNNER | V2 (a mechanism `ref` that does not resolve) |
| UC-TOOL-KINDS, UC-TOOL-EFFECT, UC-MECHANISM, UC-CAPABILITY | 4.3, 4.5; capability matching is the host's Tool registry resolving `id@version` |
| UC-SPIRAL, UC-LENS-TRIAD | 13 |
| UC-TRIGGER | 11 |
| UC-VERSION | 1.2 |

---

## Appendix A — grounded inquiry, single path, in v1

Abbreviated: Tool and Profile documents are referenced, not shown.

```yaml
apiVersion: sulis.workflows/v1
kind: Process
id: grounded-inquiry
version: 1.0.0
title: Grounded inquiry
inputs:
  brief: { type: "profile:brief@1" }
state:
  framed_question: { type: string, reducer: replace }
  path:            { type: "enum[single, recursive]", reducer: replace }
  findings:        { type: "list<profile:finding@1>", reducer: append }
  insights:        { type: "list<profile:insight@1>", reducer: upsert_by_id, key: id }
  verdict:         { type: "enum[survived, dropped, revised]", reducer: replace }
  confidence:      { type: "enum[grounded, partial, insufficient]", reducer: replace }
  conclusion:      { type: "profile:conclusion@1", reducer: replace }
  recommendations: { type: "list<profile:recommendation@1>", reducer: replace }
  fidelity:        { type: "enum[entailed, dropped, revised]", reducer: replace }
  notes:           { type: "list<string>", reducer: append, default: [] }
defaults: { loop_budget: 10, max_depth: 4 }
start: frame
verdicts:
  complete:     { outcome: success }
  insufficient: { outcome: success }
  dropped:      { outcome: success }
  denied:       { outcome: stopped }
nodes:
  frame:
    type: step
    tool: frame-question@1
    in: { brief: inputs.brief }
    out: { framed_question: state.framed_question }
    next: classify
  classify:
    type: step
    tool: classify-inquiry@1
    in: { question: state.framed_question }
    out: { path: state.path }
    next: choose-path
  choose-path:
    type: route
    when:
      - { if: state.path == "single", next: gather }
      - { if: state.path == "recursive", next: decompose }   # recursive path not shown
  gather:
    type: step
    tool: grounded-recon@1
    in: { question: [state.framed_question, inputs.brief.question], topology_index: host.topology_index }
    out: { findings: state.findings }
    next: interrogate
  interrogate:
    type: step
    tool: interrogate@1
    in: { candidates: state.findings, question: state.framed_question }
    out: { insights: state.insights, verdict: state.verdict }
    next: after-interrogate
  after-interrogate:
    type: route
    when:
      - { if: state.verdict == "survived", next: converge }
      - { if: state.verdict == "revised", next: gather, loop: { budget: 2, on_exhausted: { next: converge } } }
      - { if: state.verdict == "dropped", end: dropped }
  converge:
    type: step
    tool: converge-confidence@1
    in: { insights: state.insights }
    out: { confidence: state.confidence }
    next: conclude
  conclude:
    type: step
    tool: conclude@1
    in: { insights: state.insights, confidence: state.confidence }
    out: { conclusion: state.conclusion }
    next: honest-stop
  honest-stop:
    type: route
    when:
      - { if: state.confidence == "insufficient", end: insufficient }
    otherwise: { next: recommend }
  recommend:
    type: step
    tool: recommend@1
    in: { insights: state.insights, brief: inputs.brief }
    out: { recommendations: state.recommendations }
    next: check-fidelity
  check-fidelity:
    type: step
    tool: check-recommendation-fidelity@1
    in: { recommendations: state.recommendations, insights: state.insights }
    out: { recommendations: state.recommendations, verdict: state.fidelity }
    next: after-fidelity
  after-fidelity:
    type: route
    when:
      - { if: state.fidelity == "entailed", next: sign-off }
      - { if: state.fidelity == "revised", next: recommend, loop: { budget: 2, on_exhausted: { end: dropped } } }
      - { if: state.fidelity == "dropped", end: dropped }
  sign-off:
    type: gate
    kind: approval
    criteria: Every recommendation rests on a surviving insight and serves the brief's outcome.
    reviewing: [state.conclusion, state.recommendations, state.confidence]
    policy: grounded-inquiry-sign-off@1
    never_auto_when: state.confidence == "insufficient"
    note_into: state.notes
    on:
      permit:        { end: complete }
      deny:          { next: gather }          # send back; takes the default loop budget of 10
      indeterminate: { pause: true }
```

What this shows against the corpus walk: only one path runs; the revise and fidelity loops are bounded (2); a deny sends back within the default 10; "insufficient" ends honestly; no condition is prose; every step's output is checked by its Tool's controls before it reaches state.

## Appendix B — open points for review

1. **Default loop budget 10 applies to human send-backs too.** A person could be asked to re-decide ten times. Proposed: keep 10 as the single default, and templates such as `revise_loop` set their own (e.g. 3).
2. **`guided` execution policy lets a person skip `standard` steps with a reason.** Proposed as the default for methodology sequences; `strict` for content processes.
3. **Lease length (15 minutes) is a host setting**, not in the format, because it depends on the host's session model.
