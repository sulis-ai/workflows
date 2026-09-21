# Process definition format — v1

**Status:** draft · **Decision:** sulis-ai/platform ADR-227 (accepted) · **Governed by:** sulis-ai/platform ADR-028 (decision vocabulary, accepted), ADR-022 (engine adoption and its authorization blocker, accepted) · **Requirement:** [`docs/use-cases/CATALOGUE.md`](../use-cases/CATALOGUE.md) (65 needs), proven against [`docs/use-cases/corpus.md`](../use-cases/corpus.md) (50 processes, 415 scenarios)

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119.

## 0. In one page

A process is built from **four primitives**:

| Primitive | What it is |
|---|---|
| **Tool** | A typed contract for one unit of work: typed **inputs**, the **controls** its output is held to, a typed **output**, and the **mechanism** that does the work (code, a skill, an agent, another process, a composite of Tools, an external service). |
| **Step** | Binds one Tool into a process: maps run state onto the Tool's inputs and its output back into state. A step has no behaviour of its own. |
| **Gateway** | A flow node between steps: choose a route, go round a loop, split and join parallel work, repeat for each item, or reach a decision by a policy, an agent or a person. |
| **Process** | Typed inputs and state, the steps and gateways, and its named endings. A Process can be a Tool's mechanism, which is how one process calls another. |

Seven rules hold everything together:

1. **The engine only acts on data.** Routes, limits, preconditions and endings are expressions over typed state. Prose is for people and agents to read.
2. **Permission is checked before anything runs.** Starting a run, invoking any Tool and accepting any decision are authorized through the host first; a refusal stops the step (§10.1).
3. **Every Tool has controls, and they are checked.** After each step the output is checked by the deterministic checker registered for each control; the result is routed on.
4. **A decision answers one question: may this proceed?** `PERMIT`, `DENY` or `INDETERMINATE`, per ADR-028, whoever decides — a policy, an agent or a person. Where the run goes next is separate data.
5. **Every loop is bounded.** The default is in §15; a process or a loop may set its own.
6. **Every state is a sentence.** Every ending, gate and answer the engine gives carries a sentence a person can act on.
7. **Supported means as designed.** A process is supported only when each of its corpus scenarios visits exactly the expected steps, gates and ending.

---

## 1. Documents, identity and versions

1.1 A definition is a YAML (or JSON) document with a header:

```yaml
api_version: sulis.workflows/v1
kind: PROCESS                  # PROFILE | TOOL | CONTROL | PROCESS
id: grounded-inquiry           # kebab-case, unique per kind
version: 1.2.0                 # Semantic Versioning 2.0.0
title: Grounded inquiry        # for people
summary: >-                    # for people; one or two sentences
  ...
```

1.2 A reference to another definition is `id@version`. `version` is a full `major.minor.patch` (an exact pin: `interrogate@1.0.0` matches only that version) or a partial `major[.minor]`, with or without a leading `^` (`interrogate@1`, `interrogate@^1.2`) — a partial reference resolves like a caret range of that precision (§18, D10, D11): the highest registered version whose leading components match. `^` only changes anything in front of a full three-component version, where it turns an exact pin into a compatible range; in front of a partial version it is redundant, which is why every reference elsewhere in this spec is written the short way (`frame-question@1`, not `frame-question@^1`). Resolution happens **once, when a run starts**, and the run records the exact versions it pinned. A run MUST NOT change definition versions while in flight. *(UC-VERSION)*

1.3 A published version is immutable. A change is a new version.

1.4 Every object is closed: an unknown field is a validation error, not silently ignored.

1.5 **Casing is not restated here.** Field names are `snake_case` in definitions (they are stored documents); every closed value is `SCREAMING_SNAKE_CASE`, following the wire enum convention that sulis-ai/platform ADR-028 adopted from the Focaldata data conventions. Where those change, this format follows them.

1.6 Every closed value set names the standard it comes from, or says plainly that it is this format's own convention (§16).

---

## 2. Types and state

### 2.1 Types

| Type | Meaning |
|---|---|
| `string`, `integer`, `number`, `boolean` | JSON primitives |
| `enum[A, B, C]` | one of the listed values |
| `list<T>` | an ordered list of `T` |
| `map<T>` | string keys to `T` |
| `profile:<id>@<version>` | a value conforming to a Profile (§3) |
| `any` | untyped; allowed only for host-provided inputs, and MUST NOT be read by an expression |

### 2.2 Run state

| Path | Holds | Written by |
|---|---|---|
| `inputs.<name>` | The run's declared inputs | The caller, once, at start |
| `host.<name>` | Declared host-provided values | The host, at start *(UC-IN-AMBIENT)* |
| `state.<channel>` | Declared state channels | Step output mappings |
| `steps.<node>` | The latest attempt: `.output.<name>`, `.verdict`, `.controls.<control>.passed`, `.attempt`, `.decided_by` | The engine |

A path that does not exist evaluates to *absent* (§8).

### 2.3 State channels *(UC-STATE-CHANNELS)*

```yaml
state:
  findings:   { type: "list<profile:finding@1>", reducer: APPEND }
  insights:   { type: "list<profile:insight@1>", reducer: UPSERT_BY_ID, key: id }
  confidence: { type: "enum[GROUNDED, PARTIAL, INSUFFICIENT]", reducer: REPLACE }
  notes:      { type: "list<string>", reducer: APPEND, default: [] }
```

Reducers: `REPLACE` (last write wins), `MERGE` (maps, shallow), `APPEND` (lists), `UPSERT_BY_ID` (lists of objects, replaced by `key`). A write that does not match the channel type is refused and recorded as a failed attempt.

---

## 3. Profile

A **Profile** is a named, versioned JSON Schema (2020-12) for a value that flows between Tools. Profiles are the type system.

```yaml
api_version: sulis.workflows/v1
kind: PROFILE
id: finding
version: 1.0.0
title: Finding
grounded_in: W3C PROV-O prov:wasDerivedFrom — every finding names its source
schema:
  type: object
  required: [id, claim, source]
  properties:
    id: { type: string }
    claim: { type: string, minLength: 10 }
    source: { type: string }
  additionalProperties: false
checker: profile-conformance@1
```

Declaring an output of a profile type holds that output to the profile: a Profile is also a control (§5).

---

## 4. Tool

### 4.1 Shape

```yaml
api_version: sulis.workflows/v1
kind: TOOL
id: interrogate
version: 1.0.0
title: Attack the claims, keep what survives
inputs:                                    # I
  candidates: { type: "list<profile:finding@1>" }
  question:   { type: string }
output:                                    # O — one or more named outputs
  insights: { type: "list<profile:insight@1>" }
  verdict:  { type: "enum[SURVIVED, DROPPED, REVISED]" }
controls:                                  # C — at least one
  - profile: insight@1
  - conventions: faithful-generation@1
mechanism:                                 # M
  kind: SKILL
  ref: skills/interrogate
  allowed_tools: [ground-citations@1]
effect: QUERY
errors:
  - { code: SOURCE_UNREACHABLE, class: TRANSIENT }
  - { code: BRIEF_UNANSWERABLE, class: PERMANENT }
```

### 4.2 Inputs and outputs *(UC-TOOL-TYPED-IO, UC-OUT-MULTI)*

- `inputs.<name>`: `type`, `required` (default `true`), `default`, `description`.
- `output.<name>`: `type`, `description`. A Tool MAY have several named outputs.

### 4.3 Mechanism kinds *(UC-TOOL-KINDS, UC-MECHANISM)*

| `kind` | What does the work | Deterministic | `ref` names | Verified by |
|---|---|---|---|---|
| `CODE` | A function the host can call | yes | `module:function` | Exact output on examples |
| `SKILL` | A model following written instructions, one hand-off — with bounded discretion (`allowed_tools`) if declared | no | a skill or agent definition | Conformance to its controls |
| `PROCESS` | Another process, run as a child (§9): a separately authored, separately versioned artifact (`ref: process-id@version`), or an anonymous sequence declared inline, belonging only to this Tool (`process: { start, nodes, endings, ... }`, D18) | as the child | `process-id@version`, or none (inline) | The child's corpus scenarios (external) or this Tool's own controls (inline) |
| `TOOL` | A composite: child Tools in order over shared values (`composes`) | as its children | — | Its children |
| `EXTERNAL` | A service outside Sulis, through a host adapter | per adapter | an adapter id | The adapter's contract tests |

`composes` lists `{ tool, inputs, output }` per child. `allowed_tools` belongs to the mechanism; the policy allowing the Tool to hold that set is a control.

A non-deterministic `PROCESS` call (either form) surfaces its inner hand-offs through the top-level run at a nested `scope` — §9.3's "every answer names the scope and definition it belongs to, at any depth" is not only about a called Process's gates; it is the general rule an inline sequence's own steps follow too. It is not opaque to the caller the way a `CODE` dispatch is: the same top-level caller drives it, one hand-off at a time, exactly as it drives the outer run. What the two `PROCESS` forms differ on is identity, not who drives them or how: `ref` names a process with its own id, version, endings and corpus scenarios, reusable anywhere; the inline form has none of that — no `id`, no `version`, no independent `permission` — and simply produces this Tool's own declared `output` directly, with no `result.outputs`/`result.endings` translation to perform (D18).

These kinds follow fd-product-architecture ADR-0074's mechanism vocabulary (read on its published step-contract page); `SKILL` absorbing what this register calls out as bounded tool choice, and `PROCESS` gaining an anonymous form, are this format's own convention on top of it (D18), not a further claim about ADR-0074 itself.

### 4.4 Controls *(UC-TOOL-CONTROLS, UC-OUT-TYPED, UC-FIDELITY)*

- A Tool MUST declare at least one control.
- A control is `profile: <id@v>`, or a reference to a CONTROL document (§5): `conventions:`, `fitness:` or `policy:`.
- Every control MUST resolve at validation **and** at run start; one that does not **refuses to run**.
- Every non-policy control MUST have a registered checker (§5.2).
- A `SKILL` Tool MUST have at least one non-policy control: its output varies, so without a checkable bar it cannot be evaluated.

### 4.5 Effect *(UC-TOOL-EFFECT, UC-SIDE-EFFECT-CLAIM)*

`QUERY` reads only; `MUTATION` changes Sulis-held state; `SIDE_EFFECT` changes something outside Sulis. A `MUTATION` or `SIDE_EFFECT` step is claimed before it runs (§12.3).

### 4.6 Errors *(UC-RETRY, UC-FAILURE-MODES)*

`errors[]` lists expected codes as `TRANSIENT` or `PERMANENT`. An unlisted error is `PERMANENT`.

---

## 5. Control

### 5.1 Shape

```yaml
api_version: sulis.workflows/v1
kind: CONTROL
id: faithful-generation
version: 1.0.0
type: CONVENTIONS              # CONVENTIONS | FITNESS | POLICY
title: Recommendations are entailed by the insights they cite
applies_to: output.insights
checker: check-entailment@1
grounded_in: Ji et al., "Survey of Hallucination in Natural Language Generation", arXiv:2202.03629 (intrinsic/extrinsic)
```

- `CONVENTIONS` — rules the content must follow.
- `FITNESS` — a measured threshold, with `severity: ERROR | WARNING` (a two-value subset of RFC 5424 §6.2.1 severities) and a `threshold`:
  ```yaml
  threshold: { metric: coverage_ratio, op: GTE, value: 0.8 }
  ```
  `metric` names what the checker measures — the checker Tool registered for this control (§5.2) interprets it, the same way it interprets `applies_to`. `op` is one of `GTE | GT | LTE | LT | EQ`. This shape is this format's own convention (§16, D8) — no external standard defines a generic fitness-threshold shape to adopt instead.
- `POLICY` — who or what may do or permit something; evaluated by the host's `PolicyPort` (§10.1), not by a checker.

### 5.2 Checkers

A checker is a `CODE` Tool that declares what it checks and returns `profile:control-result@1` — `{ control, passed, findings: [ { path, message, severity } ] }`:

```yaml
kind: TOOL
id: profile-conformance
mechanism: { kind: CODE, ref: sulis_workflows.checkers:profile_conformance }
checker_for: { control: PROFILE }
inputs:  { value: { type: any }, control: { type: string } }
output:  { result: { type: "profile:control-result@1" } }
controls: [ { profile: control-result@1 } ]
examples:
  - { name: conforming finding passes, inputs: { ... }, expect: { result: { passed: true } } }
  - { name: finding without a source fails, inputs: { ... }, expect: { result: { passed: false } } }
```

- A checker MUST ship at least one example that **passes** and at least one that **fails**. A checker that has only ever been shown passing values would also pass a checker that returns `passed: true` unconditionally.
- Checkers are built before the Tools they grade: a checker is the evaluation of every non-deterministic Tool that names its control.

---

## 6. Process

```yaml
api_version: sulis.workflows/v1
kind: PROCESS
id: grounded-inquiry
version: 1.0.0
title: Grounded inquiry
inputs:
  brief: { type: "profile:brief@1" }
host_inputs:
  topology_index: { type: any }
state: { ... }
defaults: { loop_budget: 10 }            # any setting in §15 may be overridden here
start: frame
nodes: { ... }
endings:
  COMPLETE:     { outcome: SUCCESS, says: "Done: recommendations are signed off." }
  INSUFFICIENT: { outcome: SUCCESS, says: "Stopped honestly: the evidence does not support an answer." }
  DROPPED:      { outcome: SUCCESS, says: "Nothing survived review, so there is nothing to recommend." }
  DENIED:       { outcome: STOPPED, says: "Stopped: the recommendations were not approved." }
triggers: [ ... ]
skip_policy: STRICT                      # STRICT | ADVISORY
```

- **Endings** *(UC-STOP-NAMED, UC-STOP-HONEST)*: every ending is named, has an `outcome` (`SUCCESS`, `STOPPED` — ended on purpose, a person may need to act — or `FAILURE`), and a `says` sentence. An honest `INSUFFICIENT` is a `SUCCESS`.
- The engine adds four endings every process has, each with its own sentence: `ESCALATED` (a limit ran out with no route), `FAILED` (a permanent error with no route), `FORBIDDEN` (a permission was refused, §10.1), `CANCELLED` (a person stopped the run).
- **Skip policy** *(UC-EXEC-POLICY, UC-CRITICALITY)*: `STRICT` — only declared routes run. `ADVISORY` — a person with permission MAY skip a step whose `criticality` is `TRIVIAL`, recording a reason. `STANDARD` and `CRITICAL` steps are never skipped. The default is in §15. A `STEP` MAY declare `skip_permission: <host permission string>` (ADR-024's grammar, same shape as D12-D14); absent means the engine refuses every skip of that step, `ADVISORY` or not (D15) — skip authority is per-step, distinct from the Tool's own dispatch `permission` (§10.1). This field is named `skip_policy`, not `execution_policy` (D16): every run is driven step by step by whatever agent calls `next()`/`report()` (§12.1) regardless of this setting, so "guided" describes that whole engine, not this one field — `skip_policy` only ever governs whether a `TRIVIAL` step may be skipped.

---

## 7. Nodes

Every node has an `id` (its key in `nodes`) and a `type`: `STEP`, `ROUTE`, `PARALLEL`, `JOIN`, `FOR_EACH`, `GATE`. A node leaves by `next: <node-id>` or `end: <ENDING>`.

### 7.1 Step

```yaml
nodes:
  interrogate:
    type: STEP
    tool: interrogate@1
    in:
      candidates: state.findings
      question: [state.framed_question, inputs.brief.question]
    out:
      insights: state.insights
      verdict: state.interrogation_verdict
    precondition: len(state.findings) > 0
    criticality: CRITICAL
    on_control_fail: { repair: 1, then: { end: FAILED } }
    on_error: { BRIEF_UNANSWERABLE: { end: INSUFFICIENT } }
    next: after-interrogate
```

- `in` *(UC-IN-OPTIONAL, UC-IN-FALLBACK)*: every required Tool input MUST be mapped, to a path or an ordered list of paths (the first present, non-empty value is used). Each path is type-checked against the input.
- `out`: maps Tool outputs to channels. Unmapped outputs are still recorded under `steps.<id>.output`.
- `precondition` *(UC-PRECONDITION)*: when false, the step does not run and the run takes `on_precondition_false`. A step marked `destructive: true` MUST have a precondition.
- `retry` applies to `TRANSIENT` errors only, and MAY override the format default (§15):
  ```yaml
  retry: { max: 5, backoff_seconds: 4 }
  ```
  `max` is the greatest number of additional attempts; `backoff_seconds` is the starting delay before exponential backoff. `defaults.retry` (§6) takes the same shape. This format's own convention (§16, D9) — no external retry-policy standard is adopted, since the established ones (e.g. AWS SDK retry configuration, gRPC service config) are transport/SDK-specific, not a document-format concern. `on_error` routes by error code. `on_control_fail` is in §10.2. `on_forbidden` is in §10.1. Defaults for all of these are in §15.
- A step MUST NOT carry instructions; they belong to the Tool's mechanism.

### 7.2 Route *(UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-DECIDE, UC-VERDICT-ROUTE, UC-PATHS)*

```yaml
  after-interrogate:
    type: ROUTE
    when:
      - if: state.interrogation_verdict == "SURVIVED"
        next: converge
      - if: state.interrogation_verdict == "REVISED"
        next: gather
        loop: { budget: 2, on_exhausted: { next: converge } }
        invalidates: [synthesise]
      - if: state.interrogation_verdict == "DROPPED"
        end: DROPPED
```

- Options are evaluated in order; the first true one is taken.
- A route MUST have `otherwise`, unless every option tests one enum-typed path for equality and together they cover every value — as above, which the validator proves.
- A judgement ("is there a context gap?") is a step whose Tool returns a typed verdict, followed by a route on it. There is no separate decide node.

### 7.3 Loops *(UC-LOOP-BUDGET, UC-LOOP-MANY, UC-LOOP-WHILE, UC-TERMINATES-WHEN, UC-COMPENSATE)*

A **loop** is any route, gate route or `on_control_fail` route whose target can reach the node it leaves from. The validator detects every loop.

- Every loop is bounded: `loop.budget`, else the process's `defaults.loop_budget`, else the format default (§15). The budget is the most times the loop may be taken in one run scope.
- Each loop has its own counter (default name `<from>-><to>`), rebuilt from durable records so it survives a crash.
- `on_exhausted` is a route; its default is in §15.
- `counts`: `PASSES` (every time taken) or `FAILURES` (only when taken because a check failed). Default in §15.
- `invalidates`: nodes whose recorded outputs stop counting when the loop is taken, so later steps cannot read superseded work.

### 7.4 Parallel and join *(UC-PARALLEL, UC-JOIN)*

```yaml
  lenses:    { type: PARALLEL, branches: [market-lens, customer-lens, coherence-lens], join: lens-join }
  lens-join: { type: JOIN, policy: ALL_SUCCESS, next: lead-lens }   # ALL_SUCCESS | ANY_SUCCESS | ALL_COMPLETE
```

Every branch start is handed out. The join runs **exactly once**, when its policy is met or can no longer be (then `on_join_failed`). Two branches writing one `REPLACE` channel is refused.

### 7.5 For each *(UC-FOREACH)*

```yaml
  per-sub-brief:
    type: FOR_EACH
    over: state.sub_briefs
    as: sub_brief
    do: run-sub-inquiry
    max_concurrency: 4
    collect: { output: insights, into: state.insights }
    join: ALL_COMPLETE
    next: synthesise
```

`over` MUST be list-typed. Each item runs in an isolated scope; `collect` writes through the channel's reducer.

### 7.6 Gate — reaching a decision

A gate is where something must be decided before the run continues. **ADR-028 governs the decision vocabulary; this section applies it and does not restate its reasoning.**

```yaml
  sign-off:
    type: GATE
    kind: APPROVAL                         # APPROVAL | INPUT; absent means APPROVAL; anything else is refused
    asks: "Can these recommendations go ahead as work?"
    criteria: Every recommendation rests on a surviving insight and serves the brief's outcome.
    reviewing: [state.recommendations, state.confidence]
    deciders:
      - policy: grounded-inquiry-sign-off@1
      - agent: review-recommendations@1
      - person: { permission: agents.recommendation.approve }
    person_required_when: state.confidence == "INSUFFICIENT"
    note_into: state.notes
    on:
      PERMIT: { next: decompose-to-work }
      DENY:   { next: recommend, loop: { budget: 3 } }
```

**Verdicts** *(UC-GATE-VOCAB, UC-GATE-ROUTE)*:

| Verdict | Means | Routes |
|---|---|---|
| `PERMIT` | May proceed | MUST have a route: `next` to continue, or `next` + a different step to resubmit |
| `DENY` | May not proceed as it stands | MUST have a route: `next` to an earlier node (**send back** — a loop, §7.3), `end: <ENDING>` (**halt**), or `call: <process>@v` then `end` (**hand off**, UC-GATE-HANDOFF) |
| `INDETERMINATE` | Not this decider's call | MUST NOT have a route. It passes the decision to the next decider; after the last, the gate stays open for a person with the gate's permission (**pause**, UC-REFUSAL-MODE) |

**Deciders** *(UC-APPROVAL-AUTO, UC-GATE-KINDS)* are asked in order; the first `PERMIT` or `DENY` decides:

| Decider | Decides by | Declared as |
|---|---|---|
| `policy` | The host's `PolicyPort` evaluates the policy (trust earned, thresholds, grants) | `policy: <control-id@v>` |
| `agent` | A `SKILL` Tool that receives `criteria` and the `reviewing` values and returns `profile:decision@1` — `{ verdict, rationale, evidence: [ { path, claim } ] }` | `agent: <tool-id@v>` |
| `person` | A person holding the named permission or role, through the host's decision surface | `person: { permission: <host permission> }` or `{ role: <host role> }` |

- A gate MAY declare `permission: <host permission string>` (ADR-024's grammar, same shape as a Tool's, §10.1, D12). If `deciders` is absent, the gate is decided by a person holding the gate's permission; that permission is this field. It is also who may decide the gate once every declared decider has answered `INDETERMINATE` (the **pause** state above) when the last decider is not itself a `person` (D13).
- A decider that cannot run, or gives a verdict outside its `may` list (the three ADR-028 verdicts themselves — no decider kind may answer with a fourth value), counts as `INDETERMINATE` rather than erroring (D13).
- `person_required_when`: while true, deciders before the first `person` are still asked and recorded, but only a person's verdict counts.
- **An agent decision is checked before it counts.** `decision@1`'s checker requires every `evidence[].path` to be one of the gate's `reviewing` paths and to resolve to a value in the run; a decision whose evidence cites nothing reviewed, or fails its controls, counts as `INDETERMINATE`. An agent that returns `PERMIT` with no grounded evidence cannot pass.
- **No deciding on your own work** (ANSI INCITS 359-2004, static separation of duty — *known, not re-read*): an agent decider MUST NOT be the Tool or agent session that produced a value in `reviewing`; the engine treats its verdict as `INDETERMINATE`.
- `kind: INPUT`: the decider gives an answer of `answer_type`, written through `answer_into`; `on` has `ANSWERED` and the decision passes on `INDETERMINATE` as above.
- **Provenance** *(UC-GATE-AUDIT)*: from every decider asked, the engine records the verdict, `decided_by` (`POLICY:<id>`, `AGENT:<tool>@<v>` and its session, or `PERSON:<subject>`), the rationale or note, the evidence, the time, and which asking of the gate it was.
- Permission strings are the host's (for the platform, ADR-024's `<service>.<resource>.<verb>` grammar); the format carries them opaquely and the host validates them at publish.

---

## 8. Expressions

Expressions appear in `if`, `precondition`, `person_required_when` and fitness thresholds. They are pure.

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

- Every path is type-checked; **an expression that cannot be evaluated is refused.**
- `exists(p)` is true when `p` is present and not null. Comparing an absent value is false, never an error.
- Comparing an enum path with a value outside the enum is refused.

This grammar is this format's own convention; no external expression standard was adopted, because the candidates carry function calls and I/O this format forbids.

---

## 9. Calling a process *(UC-CALL, UC-CALL-RESULT, UC-CALL-DEPTH, UC-CALL-PATH, UC-CALL-NESTING, UC-CALL-GATES)*

### 9.1 As a Tool

```yaml
kind: TOOL
id: run-grounded-inquiry
inputs: { brief: { type: "profile:brief@1" } }
output:
  recommendations: { type: "list<profile:recommendation@1>" }
  ending: { type: "enum[COMPLETE, INSUFFICIENT, DROPPED, DENIED, ESCALATED, FAILED, FORBIDDEN, CANCELLED]" }
controls: [ { profile: recommendation@1 } ]
mechanism:
  kind: PROCESS
  ref: grounded-inquiry@1
  inputs: { brief: brief }
  result:
    outputs: { recommendations: state.recommendations }
    endings:
      COMPLETE: COMPLETE
      INSUFFICIENT: INSUFFICIENT
      DROPPED: DROPPED
      DENIED: DENIED
      ESCALATED: ESCALATED
      FAILED: FAILED
      FORBIDDEN: FORBIDDEN
      CANCELLED: CANCELLED
effect: QUERY
```

- `result.endings` MUST map every ending the child can reach, including the engine's four. The calling step MUST route every value of `ending`. Either gap is refused — the defence against parents and children disagreeing about result names.
- `path` MAY name the option the child's first route must take; otherwise the child decides.

`ref` names a separately authored, separately versioned Process. A Tool MAY instead declare `process:` — the same shape (`start`, `nodes`, `state`, `endings`), inline, with no `id`/`version`/`permission` of its own (D18):

```yaml
kind: TOOL
id: interrogate
inputs: { candidates: { type: "list<profile:finding@1>" }, question: { type: string } }
output:
  insights: { type: "list<profile:insight@1>" }
  verdict:  { type: "enum[SURVIVED, DROPPED, REVISED]" }
controls: [ { profile: insight@1 }, { conventions: faithful-generation@1 } ]
mechanism:
  kind: PROCESS
  process:
    start: attack
    nodes:
      attack:
        { type: STEP, tool: attack-claim@1, in: { candidate: state.current }, out: { survived: state.survived }, next: keep-or-drop }
      keep-or-drop:
        type: ROUTE
        when:
          - { if: 'state.survived == true', next: attack }
        otherwise: { end: DONE }
    endings:
      DONE: { outcome: SUCCESS, says: "Every candidate has been attacked." }
  result:
    outputs: { insights: state.insights, verdict: state.verdict }
    endings: { DONE: SURVIVED }
effect: QUERY
```

`process:` and `ref` are mutually exclusive — exactly one, never both, never neither. An inline `process:` has no `permission` field of its own: it is not a separately startable run, only a sequence fused into this Tool's own dispatch, which is already permission-gated (§10.1) before the mechanism runs at all.

### 9.2 Depth

Depth counts calls on the current chain. At the depth limit (§15) no further call is made and the step takes `on_depth_exhausted`. A process that can reach itself MUST declare `on_depth_exhausted`.

### 9.3 Nesting and gates

Every answer names the scope and definition it belongs to, at any depth. A gate in a child is surfaced through the top-level run and decided by the child's own deciders; a parent never decides a child's gate implicitly.

---

## 10. At run time: permission, then controls

### 10.1 Permission first

Before the engine starts a run, dispatches any Tool, or accepts any decision, it asks the host's `PolicyPort` whether the acting identity (the person, the agent session, or the service acting for the run) holds the required permission. The run carries that identity; the engine never runs a step without one.

- A Process MAY declare `permission: <host permission string>` (ADR-024's grammar, same shape as D12/D13), checked once before the engine starts a run of it. Absent means the engine refuses to start the run, not that starting is unchecked (D14).
- A Tool MAY declare `permission: <host permission string>` (ADR-024's grammar, carried opaquely, same shape as a gate decider's `person.permission`, §7.6). When present, the engine checks it via `PolicyPort` before every dispatch of that Tool. A Tool with no `permission` declared refuses to dispatch — the same fail-closed treatment §4.4 already gives an unresolved control, not a silent skip (D12).
- A refusal records the attempt as `FORBIDDEN` and takes `on_forbidden` (default in §15). It is never retried.
- This is the seam sulis-ai/platform ADR-022 found missing: the platform's in-app engine enforces an action's declared permission before dispatch and the published engine does not, so adopting it without this port would remove a privilege check. The port is part of the engine contract, not an option.

### 10.2 Controls after every step *(UC-TOOL-CONTROLS, UC-OUT-TYPED, UC-OUT-REPAIR)*

1. The Tool returns its output, or an error (§7.1).
2. Each output is checked against its type.
3. Each non-policy control's checker runs and returns a `control-result`.
4. All passed: the output is recorded, mapped into state, and the step leaves by `next`.
5. Any failed: the output is recorded **with its failed results** and is **not** mapped into state; the step takes `on_control_fail` — up to `repair` further invocations with the failures as input, then `then` (defaults in §15). A `then` that goes back is a loop.

---

## 11. Triggers *(UC-TRIGGER)*

```yaml
triggers:
  - { kind: TIMER, rrule: "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9" }
  - { kind: EVENT, event: instruction.confirmed, inputs: { brief: event.instruction } }
  - { kind: STATE_ENTRY, process: land-change@1, ending: COMPLETE }
  - { kind: WEBHOOK, adapter: github, event: pull_request.opened }
  - { kind: BRANCH_PUSH, repository: host.repository, branch: main }
```

The library validates triggers; the host fires them through its `TriggerPort` and must hold permission to start the run (§10.1). Timer rules use iCalendar RRULE (RFC 5545 §3.3.10).

---

## 12. Engine semantics

### 12.1 Driving a run *(UC-RESUME)*

- `next(run, scope)` answers with one of: `TOOL_STEP` (a non-deterministic step for the caller's agent session: resolved inputs, instructions ref, controls), `DECISION_STEP` (a gate whose current decider is an agent; reported like a tool step), `AWAITING_DECISION` (a gate whose current decider is a person), `STEP_RUNNING` (claimed by another caller), or `ENDED`. Every answer carries a `says` sentence. `CODE`, `EXTERNAL` and deterministic `PROCESS` steps and policy deciders are run by the engine before it answers.
- `report(run, scope, node, output | error)` records the attempt, checks controls, and answers with `next`.
- `decide(run, scope, gate, verdict, note)` records a person's decision (identity from the caller) and answers with `next`.

Starting and resuming are the same call. Nothing is held in memory between calls.

### 12.2 Records

Every attempt of every node is one write-once record keyed by `(run, scope, node, attempt)`: inputs used, output, control results, verdict or error, who or what performed it (W3C PROV-O `prov:wasAssociatedWith`, *known, not re-read*), and start and end times. The engine numbers attempts. Loop counters, retry counts and progress are derived from records.

### 12.3 Claims *(UC-SIDE-EFFECT-CLAIM, UC-LEASE)*

Before a `MUTATION` or `SIDE_EFFECT` step runs, the engine writes an in-progress claim with a lease, under the same write-once guard. A running step renews its lease. A second caller is told `STEP_RUNNING`. An expired claim MAY be taken over, and the takeover is logged as "may already have run". Lease length is a host setting.

### 12.4 Failures *(UC-RETRY, UC-FAILURE-MODES)*

`TRANSIENT` errors retry within `retry`; `PERMANENT` errors take `on_error`, else end `FAILED`. A failure that needs a person is a gate, not a note.

### 12.5 Observers

Observers are notified only after the record is durable; an observer failure MUST NOT fail the run.

---

## 13. Templates

Each template expands into the four primitives before validation; `sulis-workflows expand` shows the result. They add no semantics of their own.

| Template | Expands to | Catalogue |
|---|---|---|
| `revise_loop` | step → gate whose `DENY` sends back to the step | UC-GATE-SENDBACK |
| `control_repair` | step with `on_control_fail` repair and a route | UC-OUT-REPAIR |
| `verification_spiral` | verify step (FITNESS controls per dimension) → route: pass, loop back, or irreducible blocker → `end` | UC-SPIRAL |
| `lens_triad` | PARALLEL lens steps → JOIN `ALL_COMPLETE` → lead-lens step → route on the composite verdict | UC-LENS-TRIAD |
| `sequence_with_gates` | process-call steps in order, a gate after each marked `gate_after`, tail calls after the final gate, optional calls behind a flag route | UC-SEQUENCE, UC-OPTIONAL-BRANCH |
| `honest_stop` | route on a confidence verdict to `end: INSUFFICIENT` | UC-STOP-HONEST |
| `handoff_contract` | route after a step checking required outputs exist: `BLOCK` → `end`, `WARN` → record and continue, `SKIP` → continue | UC-HANDOFF |

---

## 14. Validation

A definition is valid only when every rule holds. Each rule has a conformance case that includes a definition that must be **refused**.

| Rule | Refuses |
|---|---|
| V1 schema | unknown fields; wrong types; values not in `SCREAMING_SNAKE_CASE` |
| V2 references | any `id@version` that does not resolve |
| V3 controls | a Tool with no control; a non-policy control with no checker; a `SKILL` Tool with only policy controls; a checker without both a passing and a failing example |
| V4 mappings | an unmapped required input; a type mismatch in `in`, `out` or `collect` |
| V5 expressions | an unparseable expression; an untyped path; an enum compared with a value outside it |
| V6 routes | a route without `otherwise` that is not proven exhaustive |
| V7 reachability | an unreachable node; a node with no way to end |
| V8 loops | a budget that is not a positive integer |
| V9 gates | a `PERMIT` or `DENY` with no route; an `INDETERMINATE` with a route; an unknown `kind`; `kind: INPUT` (spec-legal, not yet engine-executed, D26); an agent decider not returning `decision@1`; an agent decider that could review its own output; `person_required_when` with no `person` decider; a gate with no `asks` |
| V10 calls | a child ending not mapped; a call ending not routed; a self-reachable call without `on_depth_exhausted` |
| V11 parallel | two branches writing one `REPLACE` channel; a join not reachable from every branch |
| V12 for-each | `over` not list-typed |
| V13 side effects | a `destructive` step with no precondition |
| V14 endings | an `end` naming an undeclared ending; an ending with no `says` |
| V15 grounding | a closed value set with no `grounded_in` |
| V16 state channels | a channel declaring `reducer: UPSERT_BY_ID` with no `key` |

---

## 15. Defaults

**This table is the only place defaults are stated.** Every other section refers here.

| Setting | Default | Override |
|---|---|---|
| Loop budget (passes per loop, per scope) — applies to every loop, including send-backs at gates | **10** | `defaults.loop_budget`; `loop.budget` |
| Loop counts | `PASSES` | `loop.counts` |
| When a loop runs out | `end: ESCALATED` | `loop.on_exhausted` |
| Repairs after a failed control | 1 | `defaults.repair_budget`; `on_control_fail.repair` |
| After repairs run out | `end: FAILED` | `on_control_fail.then` |
| Retries for `TRANSIENT` errors | 3, exponential backoff from 2 s | `defaults.retry`; `step.retry` (shape: §7.1) |
| Unrouted `PERMANENT` error | `end: FAILED` | `step.on_error` |
| Permission refused | `end: FORBIDDEN` | `step.on_forbidden` |
| Call depth | 4 | `defaults.max_depth` |
| Depth reached | `end: ESCALATED` | `on_depth_exhausted` (required for self-reachable calls) |
| Precondition false | `end: ESCALATED` | `on_precondition_false` |
| Join policy | `ALL_SUCCESS` | `join.policy` |
| Join cannot be met | `end: FAILED` | `on_join_failed` |
| For-each concurrency | 1 | `max_concurrency` |
| Step criticality | `STANDARD` | `criticality` |
| Skip policy | `STRICT` | `skip_policy` |
| Gate kind | `APPROVAL` (ADR-028) | `kind` |
| Gate deciders | a person holding the gate's permission | `deciders` |

**No default** exists for a route's `otherwise`, a gate's `PERMIT`/`DENY` routes, a call's ending mapping, an ending's `says` or a gate's `asks` — those are an author's decisions.

---

## 16. What this format rests on

Tags: **VERIFIED** — read in this work; **KNOWN** — precisely nameable, not re-read in this work; **OWN** — this format's convention, no external standard applies.

| Part | Source | Tag |
|---|---|---|
| Decision vocabulary and its semantics | sulis-ai/platform ADR-028 (accepted), which adopts OASIS XACML 3.0 decisions via fd-product-architecture `schemas/process.schema.json` `$defs/approval_gate` | VERIFIED (ADR-028); XACML itself KNOWN — ADR-028 records it was not read |
| Enum and field casing | sulis-ai/platform ADR-028; Focaldata `conventions/data.conventions.yaml` (enums, casing) | VERIFIED |
| Permission seam in the engine | sulis-ai/platform ADR-022 (accepted), "Why the swap is deferred" | VERIFIED |
| Permission strings | sulis-ai/platform ADR-024 (proposed) — host grammar, carried opaquely | VERIFIED (status: proposed) |
| Tool as inputs, controls, output, mechanism | IDEF0, FIPS PUB 183; fd-product-architecture ADR-0074 step contract (its published page) | FIPS 183 KNOWN; ADR-0074 page VERIFIED |
| Mechanism kinds | fd-product-architecture's own vocabulary, adopted | VERIFIED (page); OWN (no external standard) |
| Gateways, parallel, join | BPMN 2.0 (ISO/IEC 19510:2013) | KNOWN |
| Separation of duty for deciders | ANSI INCITS 359-2004 (RBAC), static separation of duty | KNOWN |
| Records, who did what | W3C PROV-O | KNOWN |
| Profiles | JSON Schema 2020-12 | KNOWN |
| Versions | Semantic Versioning 2.0.0 | KNOWN |
| Fitness severity | RFC 5424 §6.2.1 (two-value subset) | KNOWN |
| Timer triggers | RFC 5545 §3.3.10 RRULE | KNOWN |
| Normative keywords | RFC 2119 | KNOWN |
| Expression grammar, endings, templates, validation rules, defaults | this format | OWN |
| FITNESS control threshold shape (`metric`/`op`/`value`) | this format (D8) | OWN |
| `retry` override shape (`max`/`backoff_seconds`) | this format (D9) | OWN |
| Caret-range (`^`) reference semantics (§1.2) | node-semver (github.com/npm/node-semver), "Caret Ranges" (D10) | KNOWN — not part of Semantic Versioning 2.0.0 itself, which defines version precedence and format but no range syntax |
| Accessibility of any surface that shows these states | WCAG 2.2 SC 1.4.1 (use of colour) — the `says`/`asks` sentences exist so no surface has to rely on colour | KNOWN; applies to host UIs |

---

## 17. Catalogue coverage

| Catalogue id | Section |
|---|---|
| UC-IN-TYPED, UC-IN-AMBIENT | 2.2, 6 |
| UC-STATE-CHANNELS | 2.3 |
| UC-IN-OPTIONAL, UC-IN-FALLBACK | 7.1 |
| UC-OUT-MULTI, UC-TOOL-TYPED-IO | 4.2 |
| UC-OUT-TYPED, UC-TOOL-CONTROLS, UC-FIDELITY | 3, 4.4, 5, 10.2 |
| UC-OUT-REPAIR | 10.2, 13 |
| UC-OUT-MODE | a `SIDE_EFFECT` Tool (e.g. propose a change) selected by a route on an input |
| UC-HANDOFF | 13 |
| UC-SEED-ARTIFACTS | 6 (inputs typed as artifact profiles) |
| UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-DECIDE, UC-PATHS, UC-VERDICT-ROUTE | 7.2 |
| UC-PREPHASE | 7.1 (a step before the first route) |
| UC-STOP-NAMED, UC-STOP-HONEST | 6, 13 |
| UC-LOOP-BUDGET, UC-LOOP-MANY, UC-LOOP-WHILE, UC-TERMINATES-WHEN, UC-COMPENSATE | 7.3 |
| UC-OPTIONAL-BRANCH, UC-CYCLE-POLICY | 7.2 (route on a flag; route on `steps.<node>.attempt`) |
| UC-PARALLEL, UC-JOIN | 7.4 |
| UC-FOREACH | 7.5 |
| UC-CALL, UC-CALL-RESULT, UC-CALL-DEPTH, UC-CALL-PATH, UC-CALL-NESTING, UC-CALL-GATES | 9 |
| UC-SEQUENCE, UC-EXEC-POLICY, UC-CRITICALITY | 13, 6 |
| UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-HANDOFF, UC-REFUSAL-MODE, UC-APPROVAL-AUTO, UC-GATE-CRITERIA, UC-GATE-AUDIT | 7.6 |
| UC-RETRY, UC-FAILURE-MODES | 7.1, 12.4 |
| UC-PRECONDITION | 7.1 |
| UC-SIDE-EFFECT-CLAIM, UC-LEASE, UC-RESUME | 12 |
| UC-TOOL-RUNNER | V2 (a mechanism `ref` that does not resolve) |
| UC-TOOL-KINDS, UC-TOOL-EFFECT, UC-MECHANISM | 4.3, 4.5 |
| UC-CAPABILITY | the host's Tool registry resolving `id@version`; no capability matching in the format |
| UC-SPIRAL, UC-LENS-TRIAD | 13 |
| UC-TRIGGER | 11 |
| UC-VERSION | 1.2 |

---

## 18. Decisions taken in this draft

Recorded in MADR form (context, options, outcome, consequences) so each can be audited and reversed.

**D1 — One loop default of 10, everywhere.** *Context:* the principal set 10 as the default loop size. *Options:* 10 everywhere; 10 with lower defaults inside templates such as `revise_loop`. *Outcome:* 10 everywhere, including send-backs at gates. A second default in templates would state a convention twice and let the two drift. *Consequences:* a person or agent could be sent back up to 10 times unless the author sets less; authors of revise loops SHOULD set a budget. *Reversal:* change one value in §15 before any process is converted — minutes; after conversion, a re-validation of converted processes.

**D2 — `STRICT` by default; `ADVISORY` may skip only `TRIVIAL` steps.** *Context:* methodology sequences allow deviation; fail closed. *Options:* allow skipping `STANDARD` steps with a reason; allow only `TRIVIAL`. *Outcome:* only `TRIVIAL`, by a person with permission, with a recorded reason. Skipping `STANDARD` work with a reason is the bad-but-conformant path — a reason field is always fillable. *Reversal:* one rule; widening later is additive. (Renamed from `GUIDED` by D16.)

**D3 — Claim lease length is a host setting.** *Context:* how long a running step holds its claim depends on how the host runs sessions. *Outcome:* not in the format. *Reversal:* adding a field later is additive.

**D4 — `INDETERMINATE` passes the decision on and never routes.** *Context:* ADR-028 (accepted) defines it as "not my call" and refuses it with a step. *Outcome:* the format follows ADR-028; "pause on refusal" is expressed as `INDETERMINATE` reaching the last decider. *Reversal:* governed by ADR-028; change there first.

**D5 — Permission is checked by the engine before every start, dispatch and decision.** *Context:* ADR-022 found the published engine lacks the permission check the platform's engine performs. *Outcome:* a `PolicyPort` call is part of the engine contract. *Reversal:* removing it would reintroduce the privilege gap ADR-022 describes; not reversible safely.

**D6 — Every ending, gate and engine answer carries a sentence.** *Context:* states a person acts on must read as sentences, and never by colour alone (WCAG 2.2 SC 1.4.1). *Outcome:* `says` on endings and answers, `asks` on gates, refused when missing. *Reversal:* additive to relax; costly to add after processes are converted.

**D24 — A gate's `note_into` is written on the decision's own replay, and the latest note wins.** *Context:* `note_into` was in the schema, the model and the validator from v1's first draft and was never written to state, so a `DENY` sent work back with the decider's reason silently dropped — the instruction for the next attempt, lost (found by a consumer driving a real revise loop, 2026-09-20). *Options:* write it when `decide()` records the decision; write it where the decision is replayed, with the rest of the gate's state. *Outcome:* the latter — replay is the only place that holds for a resumed run, since nothing is kept between calls; a gate asked twice carries its most recent note, or a second send-back would re-run the step with the previous round's words. *Consequences:* a step reading `state.<note channel>` sees the decider's words on the attempt that follows the send-back. *Reversal:* one branch in `_advance_gate`.

**D7 — Agent decisions and checkers must be able to fail.** *Context:* an agent that always permits, or a checker that always passes, would satisfy a naive check. *Outcome:* agent decisions must cite reviewed evidence that resolves; checkers must ship failing examples. *Reversal:* relaxing is a one-line rule change; not recommended.

**D8 — FITNESS threshold shape is `{ metric, op, value }`.** *Context:* §5.1 named FITNESS as "a measured threshold" without ever giving the field(s) that carry it — a gap found while building the v1 JSON Schemas (WP-01). *Options:* leave `threshold` untyped (accepts anything, refuses nothing — fails closed on nothing); a single numeric `threshold: 0.8` field with the comparison implied (ambiguous: GTE? GT?); `{ metric, op, value }` naming what is measured, how, and against what. *Outcome:* `{ metric, op, value }`, `op` a closed `GTE | GT | LTE | LT | EQ` set — consistent with how this format already names comparisons in kind (`ROUTE` expressions, §8) rather than leaving them implicit. *Consequences:* a checker Tool for a FITNESS control reads `control.threshold` the same way it reads `applies_to`; existing FITNESS controls authored before this decision (none yet exist in this repo's fixtures) are unaffected. *Reversal:* additive — a two-way door; changing the shape means updating `control.v1.schema.json` and any FITNESS control definitions, not a migration.

**D9 — `retry` override shape is `{ max, backoff_seconds }`.** *Context:* §15 named the retry default ("3, exponential backoff from 2 s") and its override points (`defaults.retry`, `step.retry`) without giving their field shape — the same class of gap as D8, found at the same time. *Options:* leave `retry` untyped; adopt an external retry-policy standard (rejected — AWS SDK and gRPC service-config retry shapes are transport/SDK-specific, not something a document format should couple to); `{ max, backoff_seconds }`, naming exactly the two numbers §15's own default already states. *Outcome:* `{ max, backoff_seconds }`; `step.retry` and `defaults.retry` (§6) share the shape, so the override and the default it overrides are stated the same way. *Consequences:* none yet — no process definition in this repository overrides retry today. *Reversal:* additive — a two-way door, same cost as D8.

**D10 — Caret-range references resolve by node-semver's caret semantics.** *Context:* §1.2 gives one example (`^1.2`) of a caret-range reference but never states the range semantics precisely — WP-01's registry (step 2) has to resolve one to an exact version, so the rule needs to be exact, not just illustrated. *Options:* invent a bespoke range rule; adopt node-semver's caret semantics (the convention the `^` syntax is drawn from — SemVer 2.0.0 itself defines only version precedence and format, no range syntax). *Outcome:* node-semver's caret rule verbatim, including its zero-major special cases (`^0.2.3`, `^0.0.3`), because the version numbers this format's own definitions carry (§1.1, `version: 1.2.0`) are themselves plain SemVer 2.0.0 and node-semver is the widely-used convention for ranges over exactly that version grammar — inventing a different rule over the same numbers would be a gratuitous divergence from the nearest fitting convention. *Consequences:* a definition versioned below `1.0.0` gets node-semver's narrower zero-major treatment, which authors coming from npm or Cargo will already expect. *Reversal:* changing the range algorithm is a two-way door local to `registry.py`; no reference in this repository's fixtures yet depends on the zero-major special cases.

**D11 — A bare (non-`^`) partial reference (`interrogate@1`) resolves exactly like a caret range of the same precision, not as an error and not as an implicit `.0.0` pin.** *Context:* every worked reference in this spec — Appendix A included — is written the short way (`frame-question@1`, `insight@1`, `grounded-inquiry-sign-off@1`), never `@1.0.0` and never `@^1`; §1.2 as first drafted only defined the caret form, which would have made every one of the spec's own examples an invalid reference (WP-01's registry work, building the first real resolver against these examples, is what surfaced this). *Options:* refuse any reference that isn't a full three-component version or an explicit `^`-prefixed one (rejected — invalidates every reference this spec itself has ever shown); treat a bare partial reference as shorthand for `major.minor.0` or `major.0.0` exactly (rejected — silently picks the *lowest* matching version even when a newer compatible one is registered, the opposite of what a reference author almost always wants, and inconsistent with how `^` is defined to behave at the same precision); treat it identically to a caret range of the same precision (adopted). *Outcome:* the `^` sigil only changes behaviour in front of a full three-component version (exact pin vs. compatible range); in front of a partial version it is redundant, so this spec's authors have always been free to omit it. *Consequences:* `interrogate@1` and `interrogate@^1` are now defined to mean exactly the same thing; a reference author who wants a true single-version pin must write all three components. *Reversal:* two-way door, local to `registry.py`'s `Registry.resolve` (the branch between "exact pin" and "range resolve" moves from "no `^`" to "fewer than three components"); every reference in this repository's fixtures is already written the short way, so no fixture needs to change if this is reversed to the opposite convention (require `^` and treat bare partial as pin-to-zero) — only the resolution result would.

**D12 — A Tool's dispatch permission is an optional, opaque `permission` field; absent means refuse to dispatch, not "no check needed."** *Context:* §10.1 requires the engine to check permission "before it ... dispatches any Tool" but, as first drafted, named no field carrying which permission a given Tool's dispatch requires — a gap found while building WP-02's engine (the `PolicyPort` call has to name *something* to check). *Options:* derive a permission string automatically from the Tool's own id (rejected — invents a naming scheme ADR-024 reserves to the host, and two hosts would derive two different strings from the same Tool); make `permission` a required field on every Tool now, enforced by the JSON Schema (rejected for this draft — would invalidate every Tool fixture already written against v1, a large, unrelated blast radius for a field this decision can add without it); an optional field that, when absent, means the dispatch proceeds unchecked (rejected — silently defeats §10.1's own "before it dispatches any Tool," the bad-but-conformant path this format's own principles ask every rule to defeat). *Outcome:* `permission` is optional in the schema (so no existing fixture needs to change), but the *engine* treats its absence as a refusal to dispatch, mirroring §4.4's existing rule that a Tool with an unresolved control refuses to run. *Consequences:* every Tool that should actually run needs `permission` declared; a future draft should tighten this to a schema-level requirement (a new validator rule, V-something) once real Tool fixtures exist to migrate. *Reversal:* two-way door — tightening `permission` to schema-required is additive once fixtures are updated; the engine-side refusal-on-absence rule is local to `engine/steps.py` and can be relaxed in one place.

**D13 — A gate's own `permission` is likewise an optional, opaque field (mirroring D12); a decider's "`may` list" is exactly the three ADR-028 verdicts.** *Context:* two related gaps found while building WP-02's GATE execution (step 4). First, §7.6 twice refers to "the gate's permission" (deciding a gate with no `deciders` declared; deciding a gate once every decider has answered `INDETERMINATE` and the last is not a `person`) without GATE ever declaring a `permission` field, the same shape of gap as D12's. Second, §7.6 says a decider "gives a verdict outside its `may` list" counts as `INDETERMINATE`, but no `may` field or list is defined anywhere for any decider kind. *Options, first gap:* the same three considered for D12, with the same reasoning; adopted the same outcome for consistency ("hold conventions once" — two gates of the same shape should not get two different answers). *Options, second gap:* invent a new per-decider `may:` field naming which verdicts that decider is allowed to give (rejected — no worked example in the spec ever shows such a field, and inventing new schema surface from a single, isolated phrase risks guessing wrong about what was meant); read `may list` as referring to the fixed, already-existing ADR-028 vocabulary itself — i.e. the phrase is reinforcing that a decider's raw answer must be one of `PERMIT`/`DENY`/`INDETERMINATE` and nothing else, not introducing a new declared field (adopted — the reading that adds no new schema surface and is consistent with `decision@1`'s own verdict already being drawn from that same enum). *Outcome:* GATE gains an optional `permission` field, engine-refused-when-absent exactly as D12; "outside its `may` list" means "not one of PERMIT/DENY/INDETERMINATE." *Consequences:* a gate with no `deciders` and no `permission` cannot be decided by anyone until `permission` is added — the same fail-closed shape D12 already accepted for Tools. *Reversal:* two-way door for both halves, local to `model.py`'s `GateNode` and `engine/gates.py`'s `may`-list check respectively.

**D14 — A Process's own `permission`, checked once before the engine starts a run, is the third and final field of this shape (D12, D13).** *Context:* §10.1 requires the engine to check permission "before it starts a run" but, like D12/D13's fields, named no place a Process declares which permission that is — found while building WP-02's `next()` (step 5), the first code that actually has to start a run rather than dispatch a step or a gate already inside one. *Options:* the same three considered for D12/D13. *Outcome:* the same answer, for the same reason: `permission` is optional on Process, and the engine refuses to start a run of a Process that has none, rather than starting it unchecked. *Consequences:* every real Process needs `permission` declared before any run can start, same as D12/D13's Tools and Gates. *Reversal:* two-way door, additive, local to `model.py`'s `Process` and `engine/run.py`'s start-of-run check.

**D15 — A `STEP`'s skip authority under `ADVISORY` skip policy is its own field, `skip_permission`, distinct from the Tool's dispatch `permission` (D12).** *Context:* §6 says `ADVISORY` (then named `GUIDED`) lets "a person with permission" skip a `TRIVIAL` step, but names no field carrying which permission — the same shape of gap as D12-D14, found while building the engine's own support for this policy (a capability the engine had validated and stored since WP-01 but never acted on at runtime until now). *Options:* reuse the Tool's own `permission` (D12) for skip authority too: rejected — dispatching a Tool and overriding the process's own declared flow are different privileges a host may reasonably grant to different roles (e.g. anyone who may run a step at all, versus only a supervisor who may skip one), and collapsing them removes a distinction a host may need; the same three options D12-D14 considered for a fresh field, with the same reasoning. *Outcome:* `STEP` gains an optional `skip_permission`; absent means the engine refuses every skip of that step (fail closed, same shape as D12-D14), whether or not the policy is `ADVISORY`. *Consequences:* a `TRIVIAL` step is only actually skippable once its author declares `skip_permission`; an `ADVISORY` process with no such declarations behaves identically to `STRICT` in practice, which is the safe default. *Reversal:* two-way door, additive, local to `model.py`'s `StepNode` and `engine/run.py`'s skip path.

**D16 — `execution_policy`/`GUIDED` renamed to `skip_policy`/`ADVISORY`.** *Context:* the principal's own working definition of "guided" is a different, unrelated concept already true of the whole engine — an agent calling `next()`/`report()` to get the current step and record its outcome, one step at a time, as opposed to a session (the deprecated `compiler/` path) that runs a process internally in one go. That property holds for every run under this v1 format regardless of `execution_policy`/D2's setting, so naming the skip-a-`TRIVIAL`-step setting `GUIDED` collided with a more fundamental, already-true meaning of the same word. *Options:* keep the field name and only rename the value (`GUIDED` → something else, field stays `execution_policy`): rejected — the field name itself is what invites the confusion, since "execution policy" reads as governing how the process is run in general, not narrowly whether a step may be skipped. Rename only in prose/docs, keep `execution_policy`/`GUIDED` in the machine format: rejected — the two channels would then disagree, and any process definition or fixture written against the docs would fail to validate. *Outcome:* field renamed to `skip_policy`; enum value renamed `GUIDED` → `ADVISORY` (paired with `STRICT`, both describing the same axis — how strictly the declared flow is followed); `STRICT` unchanged. *Consequences:* every prior reference to `execution_policy: GUIDED` across the spec, schema, model and engine is updated in the same change (D2, D15, §15's defaults table, `StepNode`/`Process` fields, `skip()`'s guard clauses); no process definitions exist yet outside this repository's own fixtures, so there is no external migration. *Reversal:* two-way door — a field/enum rename, no semantic change to what is or is not skippable.

**D17 — `AGENTIC` means an agent led step by step through an automated sequence, not free choice of route; distinguished from `PROCESS` by having no identity of its own, not by who drives it. SUPERSEDED BY D18 — the principal's own follow-up question ("wouldn't `AGENTIC` just be another workflow that's defined as guided?") showed the identity-based distinction drawn here still didn't need a separate mechanism kind to hold it; kept for the record of how D18 was reached, not as the standing rule.** *Context:* building the engine's `TOOL_STEP` hand-off (closing its own gap against §12.1, same session) raised the question of what `AGENTIC` actually hands an agent, which exposed that this table's prior wording — "free to choose its route within `allowed_tools`" — was never what the principal meant by the word: their own working model is an agent *led* through a declared, automated sequence, the same step-by-step hand-off discipline as the outer run, not given free rein. Checking that reading against the rest of the spec found it already fits: §9.3 ("every answer names the scope and definition it belongs to, at any depth... a gate in a child is surfaced through the top-level run") already generalizes past `PROCESS` calls to any nested scope, so an `AGENTIC` sub-sequence surfacing its own hand-offs to the same top-level caller needs no new mechanic invented, only correct wording. *Options:* leave `AGENTIC` meaning free route choice and introduce a new mechanism kind for a led sequence: rejected — a seventh kind duplicates most of what `AGENTIC` already is (non-deterministic, controls-checked, `allowed_tools`-capable) for one behavioural difference, and ADR-0074's own vocabulary (§4.3's grounding) is the register of kinds this format already commits to holding to, not extending on a single Tool's say-so. Merge `AGENTIC` into `PROCESS` entirely, since both now surface nested hand-offs the same way: rejected — collapses a real distinction (an independently versioned, independently governed artifact with its own corpus scenarios, vs. a sequence with no identity of its own belonging to exactly one Tool) that authors need, and would force every simple, single-step `AGENTIC` Tool already in this repository's own corpus (`grounded-recon`, `interrogate`, `recommend`, `review-recommendations`, Appendix A) to be rewritten as a separately versioned child Process for no behavioural gain. Design the full multi-step authoring grammar (an inline node graph in the mechanism block, or something else) in this same pass: rejected — no fixture or corpus scenario yet exercises a multi-step `AGENTIC` Tool, so inventing its concrete shape now would be exactly the speculative guess this format's own working practice (`docs/runs/`, this session repeatedly) refuses to make without something real to check it against; "adopt the cheap seam now, defer the expensive guess" (CLAUDE.md). *Outcome:* the table description of `AGENTIC` is corrected now (this is wording, not new schema — no fixture changes, no validator changes, nothing to migrate); every existing single-step `AGENTIC` Tool remains valid as the trivial case of a one-step "sequence." The concrete authoring grammar for a genuine multi-step sequence is left undecided, to be settled against a real corpus scenario that needs one. *Consequences:* until that follow-up is settled, `AGENTIC` and `SKILL` remain operationally identical in this engine (both hand off once, as `TOOL_STEP`, per the current WP-02 implementation) — the distinction drawn here is conceptual and forward-looking, not yet load-bearing in code. *Reversal:* two-way door — a corrected table description commits nothing that a later, differently-shaped authoring grammar would need to unwind.

**D18 — `AGENTIC` is removed; `SKILL` absorbs its single-step, bounded-discretion case (`allowed_tools`), and `PROCESS` gains an anonymous, inline form for the multi-step, automated-sequence case D17 was trying to hold onto its own kind.** *Context:* D17 kept `AGENTIC` distinct from `PROCESS` on the strength of one difference — identity (an independently versioned artifact vs. a sequence belonging to one Tool). Asked directly whether that difference earns a whole mechanism kind, the answer is no: "guided" (an agent driving hand-offs one at a time via `next()`/`report()`) is not a per-kind property to begin with — it is what this engine already does with anything non-deterministic, `PROCESS` calls included (§9.3). There was never a distinct "guided workflow" mechanic to invent; a multi-step `AGENTIC` sequence and a `PROCESS` call are the same mechanic wearing two names. Once that is seen, the only real difference left — identity — decides which of `SKILL` or `PROCESS` a Tool needs, not whether a third kind should exist. *Options:* keep D17's three kinds (`SKILL`, `AGENTIC`, `PROCESS`) with `AGENTIC`'s authoring grammar still to be designed: rejected — D17 already conceded `AGENTIC` and `SKILL` were "operationally identical... not yet load-bearing in code"; a kind that is not operationally distinct from another kind, with no authoring grammar of its own, is not earning its place, and the moment `PROCESS` gains an inline form (needed regardless, to give a multi-step sequence *some* home), `AGENTIC` has nothing left to do that `PROCESS` cannot. Give `AGENTIC` its own inline multi-step grammar instead of extending `PROCESS`: rejected — it would duplicate `PROCESS`'s own `nodes`/`start`/`endings`/`result` shape under a different kind name for no reason once identity is the only distinguishing property remaining. Drop `allowed_tools` (bounded discretion) entirely rather than move it to `SKILL`: rejected — nothing else in this reasoning calls that capability itself into question, only which kind's name it lives under; every fixture that used it keeps exactly the same behaviour under `SKILL`. *Outcome:* the mechanism vocabulary is five kinds — `CODE`, `SKILL`, `PROCESS`, `TOOL`, `EXTERNAL` — not six. `SKILL` MAY declare `allowed_tools` (previously `AGENTIC`-only). `PROCESS` MAY declare `process:` (§9.1) as an alternative to `ref:` — the same `start`/`nodes`/`state`/`endings` shape a top-level Process uses, with no `id`/`version`/`permission` of its own, mutually exclusive with `ref:`. Every existing single-step `AGENTIC` Tool in this repository's own corpus (`grounded-recon`, `interrogate`, `recommend`, `review-recommendations`) becomes `SKILL` with the same `ref`/`allowed_tools` unchanged — a one-word migration, not a rewrite, since none of them were ever more than one hand-off. *Consequences:* a genuinely multi-step, agent-led sequence is now authored as `PROCESS` with an inline `process:` block rather than a bespoke `AGENTIC` grammar that was never designed; §9.3's nested-scope hand-off rule, already written for a called Process's gates, is confirmed (not extended) to already cover an inline sequence's own steps the same way, since nothing about that rule was ever specific to `ref`-based calls. No fixture in this repository exercised a genuinely multi-step inline `process:` at the time of this decision — its own worked example (§9.1) was the first, written only to prove the shape parses and reads sensibly, not as a claim that the engine could run one (§9, "calling a process," was scoped to WP-03 at the time this decision was made; unaffected by this decision, which was schema/model/spec only). **Update:** §9 was in fact built as a WP-02 follow-up, not WP-03 (see `docs/work-packages/WP-02-execution-engine.md`'s own "Outcome" addendum) — both `ref` and inline `process:` calls, including a genuinely multi-step one, now run end to end (`tests/engine/test_run.py`); only §9.1's `path` override remains unimplemented. *Reversal:* two-way door for the removal itself (additive to reverse — `AGENTIC` could be reintroduced as sugar for a `SKILL`-shaped `PROCESS` call without breaking anything this decision produces); harder to reverse cheaply once real process definitions outside this repository start using the inline `process:` form, since removing it again would need a real migration rather than a one-word rename.

**D19 — A state write that does not fit its channel's reducer shape (§2.3) is checked before the attempt is durably recorded, and recorded as that refusal, not as `SUCCESS`; it routes the same way `INPUT_UNRESOLVED`/`NOT_DISPATCHABLE` already do — no dedicated `on_x` field, since §2.3 names none, ending the run cleanly (not a route) if nothing declared otherwise handles it.** *Context:* pressure-testing this spec's own Appendix A worked example (`tests/definition/fixtures/accepted/process-appendix-a.yaml`) against a real run for the first time — the `gather` step's `out: { findings: state.findings }`, where `findings` is an `APPEND` channel — found that `MERGE`/`APPEND`/`UPSERT_BY_ID` (§2.3) had never actually been implemented in the engine (`engine/state.py` only ever applied `REPLACE`), and that the one write path that existed did not check first: it recorded the attempt as `SUCCESS`, then raised an uncaught exception applying the write, crashing `report()` itself rather than returning any answer at all — not "refused and recorded as a failed attempt" (§2.3's own words), a raw crash. *Options:* record `SUCCESS` first, then let a mismatched write fail the *next* call somehow: rejected — the attempt is already durably `SUCCESS` by then, an unrecoverable false record, and there is no "next call" shape for un-recording an attempt (write-once, §12.2). Invent a dedicated `on_state_mismatch` route field: rejected — §2.3 names no such field, and `INPUT_UNRESOLVED`/`NOT_DISPATCHABLE` (`engine/steps.py`) already establish the precedent for a structural engine failure with no natural route: no dedicated field, falls through to a clean ended run. Silently coerce the value to fit (e.g. wrap a bare value in a list for `APPEND`): rejected — invents a coercion rule nothing in the spec states, exactly the "quietly do something the process never asked for" this format's own routing philosophy (§7.2) already refuses for an unmatched route. *Outcome:* `apply_output` (`engine/state.py`) now implements all four reducers exactly as §2.3 states them (`MERGE`: maps, shallow; `APPEND`: lists, extended; `UPSERT_BY_ID`: lists of objects, replaced by `key`) and raises `ReducerMismatch` — caught in `engine/run.py`'s `_record_step_result`, before the attempt is recorded, turning it into a new `StepOutcome.STATE_MISMATCH` verdict that IS what gets recorded, then routed exactly like `INPUT_UNRESOLVED` (no dedicated field, ends the run). A related gap found in the same pass — nothing checked that an `UPSERT_BY_ID` channel actually declares the `key` §2.3 requires it to upsert by — is closed as **V16** (§14), refusing that shape at validation time rather than only at runtime. *Consequences:* every real process using `APPEND`/`UPSERT_BY_ID`/`MERGE` (grounded-inquiry's own `findings`/`insights`, not just a hypothetical) can now actually run past the step that writes to it; a Tool whose output shape drifts from its channel's declared reducer fails that one attempt cleanly instead of crashing the caller. *Reversal:* two-way door — the four reducer implementations are a direct, literal reading of §2.3's own sentence (not a judgement call to unwind); the routing choice (no dedicated field) is local to `_route_for_step_failure` and could gain one later without disturbing this decision's own reducer semantics.

**D20 — A replayed scope's per-node attempt baseline advances by exactly the attempts that node's own current visit consumed, never by the attempt store's running total for that node.** *Context:* continuing the same pressure-test pass that found D19, a loop body with two hand-off nodes in sequence (`gather` then `interrogate`, Appendix A's own shape) got stuck permanently re-dispatching `gather` and never reached `interrogate` a second time, so the loop could never exhaust its own budget or make progress — found first with a minimal synthetic two-`SKILL`-step loop, then confirmed against the real grounded-inquiry process's `gather`/`interrogate` REVISED cycle. Root cause: `_drive_scope`'s replay walk re-derives, on every call, how many attempts each node has "already used" this visit by reading the attempt store; it read the store's *total* count for the node (`len(refreshed)`, every attempt across every past visit), not the count this one visit consumed, and `_advance_step` separately looked only at `attempts[-1]` (the latest attempt overall) rather than the earliest attempt still unresolved within this visit. Together, once a loop revisited a node it had already visited before, the baseline jumped straight to "however many attempts exist in total," which — depending on the node ordering — either skipped a node's own next visit entirely or, in this shape, pinned the walk to re-deriving the same first node forever. *Options:* recompute the whole scope's replay state from scratch on every call, walking attempts in original chronological order rather than per-node counts: rejected — a much larger change to `_drive_scope`'s existing incremental design, for a bug that has a local fix once the actual mechanism is understood. Have every node-advancing branch report its own attempt count and thread it through: adopted. Change `_advance_step` to look at `attempts[-1]` from a corrected slice instead of fixing the baseline itself: rejected on its own — `attempts[-1]` still picks the latest attempt across every past visit, not the earliest unresolved one belonging to the visit currently being walked, so it does not by itself stop a stale later attempt from being read as this visit's own. *Outcome:* two additive, local mechanisms. `_visit_prefix` (`engine/run.py`) takes a node's full attempt list and returns only the prefix belonging to the *earliest* unresolved visit — continuing through `TRANSIENT ERROR`/`CONTROL_FAILED` retries, stopping at and including the first genuinely terminal attempt — so a later revisit's attempts are never mistaken for the current one's; `_advance_step` now truncates to this prefix before deciding anything. `_Advance` gains `visit_attempts_used: int | None`, set by every one of `_advance_step`'s resolving branches to exactly how many attempts (relative to its own baseline) that branch consumed; `_drive_scope`'s baseline-bump uses `baseline + advance.visit_attempts_used` when a branch reports it, falling back to the old store-count read (`None`) only for `ROUTE` and external hand-offs, which were never affected by this bug. *Consequences:* any loop body with more than one hand-off-capable node (STEP with a TOOL/SKILL mechanism) now advances and exhausts its budget correctly across separate `report()` calls; confirmed against the real grounded-inquiry `gather`→`interrogate` REVISED loop (attempts land at `gather:3, interrogate:2` for budget=2, then proceeds) and its `sign-off` GATE DENY-then-PERMIT loop-back through `gather`/`interrogate`/`recommend`. That GATE case needed no GATE-specific code change and was confirmed to already work before this fix — a `policy` decider resolves synchronously within one call, so it was never exposed to the multi-call replay path this bug lives in; an `agent`/`person` decider revisited through a multi-hand-off loop body was **not** exercised by this pass and is left as an open, untested edge case (same failure mode is plausible there, since those deciders do span external hand-offs, but this has not been measured). *Evidence:* `tests/engine/test_run.py::test_multi_step_loop_body_spanning_separate_report_calls_advances_correctly` is the committed regression fixture (a synthetic two-`SKILL`-step loop, budget 2, driven through 10 `next()`/`report()` calls, asserting `a_dispatches == 3`, `b_dispatches == 2`, `ending == "DONE"`); the real-process confirmations above were run as ad hoc scripts, not (yet) committed fixtures. *Reversal:* two-way door — `visit_attempts_used` is additive and defaults to `None` (old behaviour) everywhere it isn't set; `_visit_prefix` is a pure function with no state of its own and could be dropped without touching the attempt record schema. **Update:** both the "ROUTE... never affected by this bug" claim and the `gather:3, interrogate:2`/`a_dispatches == 3, b_dispatches == 2` counts were wrong — D21 found and fixed a second, ROUTE-specific instance of this exact bug class that this decision's own reasoning missed; see D21 for the corrected counts and the committed fixture (`tests/engine/test_grounded_inquiry_e2e.py`) that first caught it.

**D21 — `_advance_route`'s own replay branch resolves exactly one visit's worth of attempt at a time, the same discipline D20 gave STEP nodes, not the node's single latest attempt regardless of how many past visits are still unconsumed.** *Context:* writing the committed regression suite D20 called for (`tests/engine/test_grounded_inquiry_e2e.py`) — driving the real grounded-inquiry process's `after-interrogate` REVISED loop (budget 2) all the way to exhaustion, rather than D20's own ad hoc script, which had only ever pushed it through two loop-backs — found that on the third pass, `interrogate` was never asked again at all: `gather` ran a third time, but the very next answer was already past `converge`, and the durable record showed `after-interrogate`'s third attempt matching a decision with no corresponding third `interrogate` attempt behind it. Root cause: `_advance_route`'s reuse branch (taken when this walk finds an attempt for the route already recorded) read `attempts[-1]` — the single latest attempt the store holds for that node, across every past visit — exactly the same mistake D20 fixed in `_advance_step`, but D20 never touched `_advance_route`, reasoning "a ROUTE's own visit is always exactly one attempt" (true of any *individual* visit, but not of how many unconsumed past visits' attempts can be sitting in the slice `_drive_scope` hands this function when a loop has looped back more than once before the walk catches up). Once `after-interrogate` had two past attempts unconsumed by this walk, its single call jumped straight to the second (`attempts[-1]`), replaying that later visit's own routing decision in place of the earlier one this walk should have resolved first — silently skipping the `interrogate` re-ask in between, and applying the loop-budget check against `baseline + len(attempts) - 1`, a count that (for the same reason) over-counted by however many unconsumed attempts happened to be sitting in the slice, not the one this call actually resolved. D20's own synthetic regression test (a two-`SKILL`-step loop, `check` ROUTE, budget 2) turns out to hit the identical bug at its own third iteration — it passed only because its assertions (`b_dispatches == 2`) had, without either of us noticing at the time, encoded the bug's own wrong behaviour (skipping the second node's third ask) as the expected one. *Options:* give `_advance_route` its own `_visit_prefix`-shaped truncation function, mirroring `_advance_step`'s: rejected as unnecessary machinery — a ROUTE's own recorded decision is always exactly one attempt (never a multi-attempt retry sequence the way a STEP's error-then-success run can be), so there is no "prefix of an unresolved visit" to compute; the fix only needs to pick the *earliest* item in the unconsumed slice, not walk it. Use `attempts[0]` instead of `attempts[-1]`, and report `visit_attempts_used=1` on every one of this function's resolving returns so `_drive_scope`'s baseline-bump advances by exactly one attempt per call, never by however many are left in the slice: adopted — minimal, and it makes the loop-budget's own `taken_count` computation exact too (simplifying `baseline + len(attempts) - 1` to plain `baseline`, since `attempts` here is now always understood to contribute exactly one to this visit regardless of the slice's actual length). *Outcome:* `_advance_route` (`engine/run.py`) now resolves one route-attempt per call in both its fresh-evaluation and reuse branches, always reporting `visit_attempts_used=1`; the loop-budget check uses `baseline` directly as the prior-taken count. D20's own regression test's expected counts were corrected (`b_dispatches` 2 → 3, comment updated to explain why) once this fix made its true, previously-masked behaviour visible. *Consequences:* any REVISED/DENY-style loop mediated by a ROUTE (not a GATE) and taken more than once before an intervening hand-off's own reply now asks every node in its body exactly as many times as the loop's own semantics require, instead of silently dropping the last one; confirmed against the real grounded-inquiry `after-interrogate` loop driven all the way to its `budget: 2` exhaustion (`interrogate` and `gather` both asked exactly 3 times, falling through to `converge` on the third REVISED) and its `after-fidelity` loop driven all the way to its own exhaustion (`recommend`/`check-recommendation-fidelity` both run 3 times, then `DROPPED`). *Evidence:* `tests/engine/test_grounded_inquiry_e2e.py::test_interrogate_revised_loop_exhausts_its_budget_and_still_converges` and `::test_fidelity_revised_loop_exhausts_its_budget_and_drops` are the committed regression fixtures against the real process; `tests/engine/test_run.py::test_multi_step_loop_body_spanning_separate_report_calls_advances_correctly`'s corrected counts are the synthetic one. *Reversal:* two-way door, same shape as D20 — `visit_attempts_used=1` is additive to what `_advance_route` already returned, and the `attempts[0]`-vs-`attempts[-1]` change is local to this one function. **Update:** "any REVISED/DENY-style loop mediated by a ROUTE (not a GATE)" undersold it — D22 found and fixed a third instance of this exact bug class, this time in `_advance_gate`, so "not a GATE" is no longer true either.

**D22 — `_advance_gate` now replays `resolve_gate` itself to find exactly one resolution's own attempts before deciding anything, rather than feeding every unconsumed attempt in the slice to it at once.** *Context:* verifying, rather than merely reasoning about, the one open question D20/D21 both left behind — whether `_advance_gate` has the identical replay-baseline bug class STEP (D20) and ROUTE (D21) both turned out to have — found that it does, and worse than either: a synthetic `sign-off` GATE (policy decider only) whose `DENY` route loops back through two `SKILL` hand-offs (`work-a`, `work-b`, matching D20/D21's own two-hand-off shape) before reaching the gate again recorded **five** `sign-off` attempts for a `budget: 2` loop that should have produced exactly three resolutions, one of them landing out of order relative to `work-b`'s own report. Root cause, structurally distinct from D20/D21 though the same class: `_advance_gate` builds `outcomes` from the ENTIRE unconsumed `attempts` slice unconditionally and feeds it straight to `resolve_gate`; when that slice happens to hold two already-decided PAST resolutions' worth of deciders (the same "a loop taken more than once before a replay catches up" precondition D20/D21 both hit), `resolve_gate` treats them as if they were sequential deciders of ONE resolution and returns `DECIDED` on the FIRST non-`INDETERMINATE` verdict it finds — silently discarding every attempt after it. Unlike D20/D21, which either stalled a node or skipped one, this can misread the ACTUAL decision: a `DENY` recorded first and a genuinely later `PERMIT` recorded second would never be seen, since `resolve_gate` stops at the `DENY`. It surfaced here only as duplicate, wastefully-repeated `DENY` dispatches (this test's policy decider always answers the same way), but a differently-scripted decider confirmed the sharper failure directly (see Evidence). *Options:* give `_advance_gate` a fixed-size truncation the way D21 gave `_advance_route` (`attempts[0]`/`visit_attempts_used=1`): rejected — a GATE resolution's own attempt count is not fixed at one, the way a ROUTE's always is; it varies from one attempt (a single decider that decides outright) up to `len(node.deciders)` (every decider asked, `INDETERMINATE`, gate `PAUSED`), so there is no single fixed size to take. Recompute the whole resolution from scratch some other way: rejected as unneeded complexity once `resolve_gate` itself, being pure, could simply be replayed. *Outcome:* `_gate_visit_prefix` (`engine/run.py`) replays `resolve_gate` one attempt at a time over the unconsumed slice and returns the earliest prefix it calls `DECIDED` (the whole slice, unchanged, if none of it decides — matching the existing `NEEDS_*`/`PAUSED` handling, which never accumulates this way since a `PAUSED` resolution always ends the call rather than being silently passed over). `_advance_gate` now truncates to this prefix before building `outcomes`, and reports `visit_attempts_used=len(attempts)` (the truncated count) on every one of its `DECIDED`-branch returns, mirroring D20/D21's own additive mechanism. *Consequences:* any `DENY`/loop-back GATE whose loop body spans more than one hand-off before returning to the gate now asks its decider exactly as many times as the loop's own semantics require, and a later resolution's verdict is never shadowed by an earlier one's; confirmed both by dispatch counts (three resolutions, not five, for `budget: 2`) and by a decider that answers `DENY` then `PERMIT`, correctly reaching `PERMIT`'s own route rather than getting stuck on the discarded `DENY`. *Evidence:* `tests/engine/test_run.py::test_gate_loop_body_spanning_separate_report_calls_asks_the_decider_once_per_resolution` (the count/order fixture) and `::test_gate_loop_body_spanning_separate_report_calls_uses_each_resolutions_own_verdict` (the verdict-shadowing fixture) are the committed regression tests. *Reversal:* two-way door — `_gate_visit_prefix` is a pure function with no state of its own, and `visit_attempts_used` is additive exactly as D20/D21's own. **Update:** "any `DENY`/loop-back GATE ... now asks its decider exactly as many times as the loop's own semantics require" overstated it for the `person` decider specifically — `decide()` (§12.1's third call, the one a `person` uses) never went through `_advance_gate` at all and had its OWN, separately broken copy of this exact bug class, untouched by this fix; see D23.

**D23 — `decide()` no longer computes which decider slot it is satisfying itself; it hands the verdict to `_drive_scope` as a `pending_decision`, the same channel `report()`'s own agent-decider path (§12.1) already used, and lets `_advance_gate`'s own already-correct replay (D22) apply it at the point it is actually reached.** *Context:* driving a `person`-only `GATE` by hand (WP-03a Fault 1) — `STEP draft (SKILL)` looping into `GATE approve` (one `person` decider, no gate-level `permission`), `DENY` looping back to `draft` — found `decide(DENY)` then `decide(PERMIT)` on the second visit ends the run `FORBIDDEN` instead of `COMPLETE`. Root cause: `decide()` computed `decider_index = len(get_attempts(...))` — the gate's TOTAL attempt count across every PAST visit, not this still-open visit's own — a bug D20/D21/D22 already named and fixed for STEP, ROUTE and GATE's OWN internal replay, but `decide()` was never touched by any of those three fixes because it never went through `_advance_gate`'s replay at all: it independently pre-computed `decider_index`/`permission`, recorded the attempt, and only THEN called `_drive_scope` to continue. On the gate's second visit the store already held one attempt from the first, so `decider_index` came out `1`, overshot `len(node.deciders) == 1`, and fell through to D13's gate-level-permission fallback — refusing a real, correctly-permissioned person decision because the process (by design) declares no gate-level `permission` at all. *Options:* give `decide()` its own local replay of the gate's attempt history (mirroring `_gate_visit_prefix`, repeated to find the current open visit's start): rejected — `resolve_gate`'s own interpretation of past attempts depends on `person_required_when`, which is a function of the run's accumulated `state`, and `decide()` has no state to evaluate it against (only `_drive_scope`'s own walk builds `state` up from records) — a `decide()`-local replay would need to either ignore `person_required_when` (silently wrong the moment a process actually uses it, which nothing in this pass could rule out) or duplicate a materially complete second copy of `_drive_scope`'s own state-building walk. Route `decide()` through `_drive_scope` via `pending_decision`, mirroring `_report_gate_decision`'s already-established pattern for the `agent` decider case: adopted — reuses the ALREADY-correct machinery (state, baseline, `person_required`) rather than re-deriving a second, now-proven-fallible copy of it. *Outcome:* `pending_decision` is now a 3-tuple, `(node_id, kind, payload)` — `kind` is `"agent"` (§7.6's `report()`-completed `DECISION_STEP`, `payload` shaped `verdict`/`evidence`/`rationale`) or `"person"` (`decide()`, `payload` shaped `verdict`/`note`/`subject`) — so a gate that turns out to actually be awaiting the OTHER decider kind can never misread one payload's fields as the other's; each of `_advance_gate`'s `NEEDS_AGENT`/`NEEDS_PERSON`/`PAUSED` branches only ever consumes the kind matching its own shape. `decide()` itself is now a thin wrapper: resolve the node, type-check it is a `GATE`, hand the verdict to `_drive_scope`. The `role`-declared-instead-of-`permission` refusal and the D13 gate-level-permission fallback are unchanged in substance, just relocated to where the correct `decider_index`/`permission` are now actually known. *Consequences:* a `person`-decided `GATE` looped back on `DENY` (or any other verdict routed back through it) now decides correctly on every subsequent visit, not only the first; confirmed both for a single always-person-decider gate and for a `[policy, person]` gate whose resolution length genuinely differs between visits (policy decides outright on one visit, falls through to the person on another) — proving the fix replays each visit's own resolution rather than assuming a fixed offset. *Evidence:* `tests/engine/test_run.py::test_decide_after_a_deny_loop_back_still_uses_the_person_deciders_permission` and `::test_decide_after_a_policy_indeterminate_loop_uses_the_correct_decider_index` are the committed regression fixtures; the three pre-existing `decide()` tests (no permission declared, permission denied, gate-level fallback) pass unchanged, confirming no regression to the single-visit case. *Reversal:* two-way door — the 3-tuple `pending_decision` shape is a mechanical widening of the existing 2-tuple one (every current caller already updated); `decide()`'s own new body is a handful of lines with no durable-record shape change (`AttemptRecord` itself is untouched).

**D25 — Appendix A's own worked example is corrected to a `person_required_when` condition it can actually reach (`state.confidence == "PARTIAL"`, not `"INSUFFICIENT"`); the mirrored fixture and its engine test follow, closing a coverage gap the earlier session left as a finding rather than fixed.** *Context:* WP-03a's verification pass (checking a set of reported-but-unverified items by hand rather than trusting the earlier report) re-examined `tests/engine/test_grounded_inquiry_e2e.py`'s own module docstring, which already documented this precisely: `sign-off.person_required_when: state.confidence == "INSUFFICIENT"` can never evaluate true in a real run of this process, because `honest-stop` (the ROUTE immediately before `recommend`) already diverts any `INSUFFICIENT` confidence straight to the `INSUFFICIENT` ending before `sign-off` is ever reached — so by the time a run reaches `sign-off`, `state.confidence` is provably never `INSUFFICIENT`. This was the spec's own choice of illustrative value, reproduced verbatim into the fixture (`tests/definition/fixtures/accepted/process-appendix-a.yaml`, "spec Appendix A ... verbatim") and therefore into the engine's own regression corpus, silently leaving the entire person-required decider path of `sign-off` — one of its three decider kinds — never actually exercised end to end. *Options:* leave it as a documented, permanent gap: rejected — this pass exists specifically to close reported-but-unverified gaps rather than re-file the same finding a second time; CLAUDE.md's "survive the bad-but-conformant attack" applies here too, since an untested code path is exactly the kind of thing that silently rots. Rewrite the example around a different field entirely (e.g. gate on `state.fidelity` instead): rejected — changes what the worked example is illustrating for no reason; the fix needed is narrower than that. Change the condition's value to one `sign-off` can actually be reached with: adopted. Of the two reachable confidence values at `sign-off` (`GROUNDED`, `PARTIAL`), `PARTIAL` was chosen as the one a process author would plausibly want a person's own sign-off for — "the evidence points somewhere but isn't fully grounded" is exactly the shape of judgement call ADR-028's `person` decider exists for; `GROUNDED` would make `person_required_when` trivially always-true whenever confidence is anything but fully grounded, which is a valid choice but a different (and less illustrative) one than what the worked example is showing. *Outcome:* the `§7.6` field-example snippet was left untouched (a standalone syntax illustration, not embedded in a full routing context — no proof it is unreachable the way Appendix A's full worked example is provably unreachable); Appendix A's own worked example (§18's neighbour, `docs/spec/process-definition.md`) and the mirrored fixture both now read `state.confidence == "PARTIAL"`. A new end-to-end test, `test_sign_off_requires_person_when_confidence_is_partial`, drives `confidence: PARTIAL` through to `sign-off` and asserts the policy and agent deciders are both asked and recorded (§7.6: "still asked and recorded") but that only the person's own `PERMIT`, via `decide()`, ends the run — proven by counting each decider kind's own invocation, not merely checking the final ending (a first draft of this test asserted only `ending == "COMPLETE"`, which the OLD, unreachable condition also produced, via the policy decider alone, since `person_required` was silently `False`; the counters are what actually distinguishes "the person path ran" from "the gate happened to end the same way for an unrelated reason"). One existing test (`test_interrogate_revised_loop_exhausts_its_budget_and_still_converges`) incidentally used `confidence: PARTIAL` for a scenario about the `after-interrogate` loop, not about `sign-off`; changed to `confidence: GROUNDED` to keep it decoupled from `sign-off`'s decider requirements, which are outside what that test is about. *Consequences:* Appendix A's `sign-off` gate now has all three decider kinds (policy alone, policy→agent, and now policy+agent-recorded→person-decides) covered end to end by the regression corpus; a future change to `resolve_gate`'s `person_required` filtering, or to how `decide()` threads a person's verdict through a multi-decider gate, would be caught here rather than only in the narrower, synthetic `tests/engine/test_gates.py` fixtures. *Reversal:* two-way door — a one-line spec/fixture value change and one additive test; nothing about the engine's own behaviour changed, only which branch of already-existing, already-correct code a worked example exercises.

**D26 — `kind: INPUT` gates (§7.6) are refused, at both validation (V9) and — in case validation is bypassed — engine runtime, rather than implemented in this pass.** *Context:* WP-03a Fault 2 — an `INPUT` gate passes validation (the schema and model already accept `kind`, `answer_type`, `answer_into`; V9 already required an `ANSWERED` route) and then fails at runtime with a genuinely confusing message: `"gate 'x': no route declared for verdict 'PERMIT'"`, naming a verdict the gate's own author never wrote into `on` anywhere. Root cause: `_advance_gate` has never read `node.kind` (or `answer_type`/`answer_into`/`ANSWERED`) at all — every gate is resolved as if it were `APPROVAL`, so a decider's ordinary `PERMIT`/`DENY` answer is looked up against an `on` map that only ever declares `ANSWERED`. The work package offered two paths: implement `INPUT` properly, or refuse it cleanly until it is. *Options considered for real implementation, and why each hits a genuinely open spec question rather than an engineering-effort one:* §7.6's own text is one sentence — "the decider gives an answer of `answer_type`, written through `answer_into`; `on` has `ANSWERED` and the decision passes on `INDETERMINATE` as above" — and does not say what shape a `policy` or `agent` decider's own answer takes. A `policy` decider's only port method, `PolicyPort.evaluate_policy`, returns a `PolicyDecision(verdict, rationale)` — the ADR-028 vocabulary, with no field for an arbitrary typed value — so either `PolicyPort` needs a new method, or `policy` deciders need to be read as excluded from `INPUT` gates entirely; §7.6 states neither. An `agent` decider's output contract is pinned to `profile:decision@1` (`verdict`/`rationale`/`evidence`) by V9 for every gate regardless of kind, but `decision@1`'s own shape has nowhere to carry an `answer_type`-typed value either — so an `INPUT` gate's `agent` decider needs either a different profile or a differently-shaped one, again unstated. A `person`'s own answer has no entry point at all: `decide()`'s public signature takes `verdict: Verdict` (the three ADR-028 values only), and §12.1 names exactly three calls (`next`/`report`/`decide`) plus `skip` — no fourth call for a person to submit an arbitrary typed value. Any one of these three gaps, guessed at rather than specified, would be exactly the "quietly do something the process never asked for" this format's own principles already refuse elsewhere (D19's own reasoning, §7.2's routing philosophy). *Outcome:* `INPUT` is refused, not implemented, in two places: V9 (`definition/validate.py`) refuses any gate declaring `kind: INPUT` outright — deliberately unconditional, so even an otherwise well-formed one (a real `answer_type`, `answer_into`, an `ANSWERED` route, no stray `INDETERMINATE` route) is still refused, since the gap is engine support, not gate shape; and `_advance_gate` (`engine/run.py`) raises a correctly-worded `EngineRefusal` the moment it sees `kind: INPUT`, the same defence-in-depth `PARALLEL`/`JOIN`/`FOR_EACH` already have against a caller that hands the engine a `Process` built directly rather than validated first. The existing `ANSWERED`-route shape check in V9 is left in place, now provably unreachable (only `APPROVAL` gates reach it, since `INPUT` returns earlier) — dormant, ready for whichever future pass actually implements `INPUT`, rather than deleted. *Proposed spec clarification (for a future PR, not decided here):* §7.6 should name, for `kind: INPUT`: (1) which decider kinds may answer it at all — `PolicyPort` cannot carry a typed value today, so either it gains a method or `policy` deciders are spec-excluded from `INPUT`; (2) the exact output shape an `agent` decider's Tool must return (a new profile, or `decision@1` extended with an `answer` field); (3) the public engine call a `person` uses to submit an answer — a fourth §12.1 call (e.g. `answer(run, scope, gate, value, subject)`) alongside `next`/`report`/`decide`/`skip`, or an extension to `decide()` itself. *Consequences:* an `INPUT` gate no longer reaches a confusing runtime failure — authors get a clear, correctly-worded refusal at validation time, and the engine itself refuses just as clearly if validation is skipped. No real `INPUT` gate can be built with this engine yet; that gap is unchanged from before this pass, only now honestly declared rather than silently crashing. *Evidence:* `tests/definition/test_validate.py::test_v9_refused_input_gate_not_yet_supported` (an otherwise well-formed `INPUT` gate, refused) and `tests/engine/test_run.py::test_input_gate_is_refused_cleanly_rather_than_misrouted` (the validator-bypass case, asserting the OLD confusing message is gone and the new one names `INPUT` specifically) are the committed regression fixtures. *Reversal:* two-way door — both refusals are simple early returns; removing either the moment real `INPUT` support lands costs nothing already written elsewhere (the dormant V9 route-shape check is ready to matter again immediately).

**D28 — `_advance_route` and `_advance_gate` now pass the process's own `defaults.loop_budget` to `check_loop_budget`, not a hardcoded `None`.** *Context:* WP-03a verification pass, item (i) — spec §7.3/§15's own 3-tier fallback for a loop's budget is `loop.budget`, else the process's `defaults.loop_budget`, else the format default (10, `definition/defaults.py`). `definition/cli.py`'s `explain` command already implemented all three tiers correctly, but both engine call sites (`engine/run.py`) hardcoded `process_default_budget=None` — `_advance_gate` already received `process: Process` as a parameter and simply never read `.defaults.loop_budget` from it; `_advance_route` did not even take `process` as a parameter, though its one caller (`_drive_scope`) already had it in scope. The practical effect: any loop that relied on a process-level default rather than its own explicit `budget:` silently used the format default (10) instead — `explain` would report one number, the engine would enforce a different one. *Options:* none seriously considered — this is a straightforward wiring gap (the value was already available at every call site), not a design question. *Outcome:* `_advance_route` gained a `process: Process` parameter, threaded from its one call site in `_drive_scope`; both call sites now pass `process.defaults.loop_budget if process.defaults is not None else None` instead of a bare `None`. *Consequences:* a process's own `defaults.loop_budget` is now honoured by both `ROUTE` and `GATE` loops that omit their own `budget:`, matching what `explain` has always reported. *Evidence:* `tests/engine/test_run.py::test_route_loop_with_no_own_budget_uses_the_process_declared_default` and `::test_gate_deny_loop_with_no_own_budget_uses_the_process_declared_default` — both confirmed failing (11 attempts, the format default, instead of the expected 3) before the fix, passing after. *Reversal:* two-way door — an additive parameter and a one-line value change at each of two call sites; no schema or durable-record shape change.

---

## Appendix A — grounded inquiry, single path, in v1

Tools and Profiles are referenced, not shown.

```yaml
api_version: sulis.workflows/v1
kind: PROCESS
id: grounded-inquiry
version: 1.0.0
title: Grounded inquiry
inputs:
  brief: { type: "profile:brief@1" }
host_inputs:
  topology_index: { type: any }
state:
  framed_question: { type: string, reducer: REPLACE }
  path:            { type: "enum[SINGLE, RECURSIVE]", reducer: REPLACE }
  findings:        { type: "list<profile:finding@1>", reducer: APPEND }
  insights:        { type: "list<profile:insight@1>", reducer: UPSERT_BY_ID, key: id }
  verdict:         { type: "enum[SURVIVED, DROPPED, REVISED]", reducer: REPLACE }
  confidence:      { type: "enum[GROUNDED, PARTIAL, INSUFFICIENT]", reducer: REPLACE }
  conclusion:      { type: "profile:conclusion@1", reducer: REPLACE }
  recommendations: { type: "list<profile:recommendation@1>", reducer: REPLACE }
  fidelity:        { type: "enum[ENTAILED, DROPPED, REVISED]", reducer: REPLACE }
  notes:           { type: "list<string>", reducer: APPEND, default: [] }
start: frame
endings:
  COMPLETE:     { outcome: SUCCESS, says: "Done: the recommendations are signed off." }
  INSUFFICIENT: { outcome: SUCCESS, says: "Stopped honestly: the evidence does not support an answer." }
  DROPPED:      { outcome: SUCCESS, says: "Nothing survived review, so there is nothing to recommend." }
  DENIED:       { outcome: STOPPED, says: "Stopped: the recommendations were not approved." }
nodes:
  frame:
    { type: STEP, tool: frame-question@1, in: { brief: inputs.brief },
      out: { framed_question: state.framed_question }, next: classify }
  classify:
    { type: STEP, tool: classify-inquiry@1, in: { question: state.framed_question },
      out: { path: state.path }, next: choose-path }
  choose-path:
    type: ROUTE
    when:
      - { if: state.path == "SINGLE", next: gather }
      - { if: state.path == "RECURSIVE", next: decompose }    # recursive path not shown
  gather:
    { type: STEP, tool: grounded-recon@1,
      in: { question: [state.framed_question, inputs.brief.question], topology_index: host.topology_index },
      out: { findings: state.findings }, next: interrogate }
  interrogate:
    { type: STEP, tool: interrogate@1,
      in: { candidates: state.findings, question: state.framed_question },
      out: { insights: state.insights, verdict: state.verdict }, next: after-interrogate }
  after-interrogate:
    type: ROUTE
    when:
      - { if: state.verdict == "SURVIVED", next: converge }
      - { if: state.verdict == "REVISED", next: gather, loop: { budget: 2, on_exhausted: { next: converge } } }
      - { if: state.verdict == "DROPPED", end: DROPPED }
  converge:
    { type: STEP, tool: converge-confidence@1, in: { insights: state.insights },
      out: { confidence: state.confidence }, next: conclude }
  conclude:
    { type: STEP, tool: conclude@1, in: { insights: state.insights, confidence: state.confidence },
      out: { conclusion: state.conclusion }, next: honest-stop }
  honest-stop:
    type: ROUTE
    when:
      - { if: state.confidence == "INSUFFICIENT", end: INSUFFICIENT }
    otherwise: { next: recommend }
  recommend:
    { type: STEP, tool: recommend@1, in: { insights: state.insights, brief: inputs.brief },
      out: { recommendations: state.recommendations }, next: check-fidelity }
  check-fidelity:
    { type: STEP, tool: check-recommendation-fidelity@1,
      in: { recommendations: state.recommendations, insights: state.insights },
      out: { recommendations: state.recommendations, verdict: state.fidelity }, next: after-fidelity }
  after-fidelity:
    type: ROUTE
    when:
      - { if: state.fidelity == "ENTAILED", next: sign-off }
      - { if: state.fidelity == "REVISED", next: recommend, loop: { budget: 2, on_exhausted: { end: DROPPED } } }
      - { if: state.fidelity == "DROPPED", end: DROPPED }
  sign-off:
    type: GATE
    kind: APPROVAL
    asks: "Can these recommendations go ahead as work?"
    criteria: Every recommendation rests on a surviving insight and serves the brief's outcome.
    reviewing: [state.conclusion, state.recommendations, state.confidence]
    deciders:
      - policy: grounded-inquiry-sign-off@1
      - agent: review-recommendations@1
      - person: { permission: agents.recommendation.approve }
    person_required_when: state.confidence == "PARTIAL"
    note_into: state.notes
    on:
      PERMIT: { end: COMPLETE }
      DENY:   { next: gather }        # send back; loop budget from §15
```

Against the corpus walk of the platform's current engine: one path runs, not both; the revise and fidelity loops stop at 2; sign-off is asked of the policy, then an agent reviewer, then a person; an agent cannot permit without grounded evidence; a denial sends back within the default budget; `INSUFFICIENT` ends honestly; no condition is prose; every output is checked before it reaches state; every ending reads as a sentence.
