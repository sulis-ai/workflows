# WP-05 — Remaining WP-02 loose ends: `GATE kind: INPUT`, claim renewal, ending-routing exhaustiveness

**Follows:** WP-02 (execution engine), D26 (`kind: INPUT` refused), D37 (`ClaimsPort.renew` built
but never called, WP-03a), D40 (the narrower half of §9.1's "route every value of `ending`"
closed; the fuller half left open). Three smaller, independent gaps, bundled into one work package
because each is small enough that its own dedicated one would be disproportionate — the same
reasoning WP-02 itself used when it absorbed calling-a-process as a late addition rather than
spinning up a separate work package for it. **Keep each as its own PR** (below) even though they
share a document.
**Spec:** §7.6 (gate, `kind: INPUT`), §9.1 (calling a process, the routing sentence), §12.3
(claims/leases). **Needs:** WP-02 unmodified.

## Part 1 — `GATE kind: INPUT`

### Why this shape

§7.6 already states the shape precisely: "`kind: INPUT`: the decider gives an answer of
`answer_type`, written through `answer_into`; `on` has `ANSWERED` and the decision passes on
`INDETERMINATE` as above." Reading `resolve_gate` (`engine/gates.py`) directly: it is built
entirely around ADR-028's own three-value `Verdict` (`PERMIT`/`DENY`/`INDETERMINATE`) —
`policy.py`'s own `Verdict` enum carries a comment stating outright, "No fourth value, no boolean
stand-in." `ANSWERED` is not a fourth `Verdict` value to add there — ADR-028 governs *decisions*
(may this proceed), and an `INPUT` gate is not deciding whether something may proceed, it is
collecting a value. This needs its own, separate decider-outcome vocabulary
(`{ANSWERED, INDETERMINATE}`), not a bent version of `Verdict`.

### Design

A new `AnswerOutcome` type (parallel to the existing `DeciderOutcome`), carrying `answered: bool`
and, when true, the `value` given (already type-checked against `answer_type` by the validator,
the same way an agent decider's `decision@1` shape is checked today). A new, small
`resolve_input_gate(node, outcomes, *, person_required) -> GateDecision`-shaped function, sitting
alongside `resolve_gate` rather than inside it (the branching logic — "first non-INDETERMINATE
outcome decides" — is genuinely the same shape, but the per-decider *outcome* type differs enough,
and the two are cheap enough to keep separate, that forcing one function to handle both would mean
threading an `Optional[value]` through every branch of the existing, already-tested `resolve_gate`
for a kind it does not otherwise touch). `_advance_gate` (`engine/run.py`) branches once, at its
own top (`if node.kind == "INPUT": ...`), to the new function; everything downstream of resolution
— provenance recording, `on.ANSWERED` routing, `answer_into`'s own state write — reuses the
existing GATE machinery unchanged (`_record_step_result`-equivalent, `apply_output`).

A person decider for an `INPUT` gate hands off via the *existing* `AWAITING_DECISION` answer kind
(§12.1's own vocabulary already names this for "a gate whose current decider is a person" — no new
`AnswerKind` needed, since giving an answer to a question is not a operationally distinct hand-off
shape from deciding permit/deny, just a different payload `decide()` accepts). `decide()`
(`engine/run.py`) gains the ability to carry a `value` alongside (or instead of) a `verdict`,
validated against `answer_type` before being recorded.

### Acceptance criteria

- **A1.** An `INPUT` gate with a single `person` decider hands off as `AWAITING_DECISION`;
  `decide(..., value=<matching answer_type>)` resolves it, routes via `on.ANSWERED`, and writes
  the value to `answer_into`'s own state path.
- **A2.** An `INPUT` gate with a `policy`/`agent` decider that returns `INDETERMINATE` (the only
  outcome those decider kinds can meaningfully give for a "collect a value" question, absent a
  policy/agent convention this spec does not define for *producing* an answer) passes to the next
  decider, exactly as `resolve_gate` already does for `PERMIT`/`DENY`/`INDETERMINATE`.
- **A3.** `V9` (`definition/validate.py`) no longer refuses `kind: INPUT` outright — its refusal is
  replaced by real shape checks (`answer_type`/`answer_into` present, `on.ANSWERED` present).

## Part 2 — claim renewal (`ClaimsPort.renew`)

### Why this shape, and why now

`ClaimsPort.renew` is not merely designed — reading `domain/ports/claims.py` directly found it
already fully implemented and unit-tested at the port/adapter level (`StubClaimsAdapter.renew`,
real wall-clock expiry). The entire gap is one layer up: no public call in this format's own
`next`/`report`/`decide`/`skip` vocabulary (§12.1) lets an in-flight caller invoke it, so a
correctly-built, already-paid-for capability sits permanently dark. Between D37's own two named
options (build a new public call, or tell hosts to set `lease_seconds` generously enough that
renewal is never needed) — the second is cheaper today but does not scale: a host cannot know in
advance how long every future `MUTATION`/`SIDE_EFFECT` Tool's real-world completion will take, and
setting `lease_seconds` too generously to be safe directly weakens §12.3's own at-most-once
guarantee (a longer lease is a longer window where a genuinely-dead attempt is still treated as
"someone else is handling it"). Given the lower layer is already built and tested, the marginal
cost of exposing it is small relative to the risk the "just set it generously" alternative
accepts permanently.

### Design

A fifth public call, `heartbeat(process, run_id, scope, node_id, ctx)`, mirroring `report()`'s own
signature shape minus `output`/`error_code` (nothing about the STEP's own result changes — only
its lease). It resolves the current claim for that `(run, scope, node)` (the same
`AttemptKey`-shaped lookup `_claim_if_effectful` already does before dispatch), calls
`ctx.claims.renew(claim, lease_seconds=ctx.lease_seconds, ...)`, and returns a small
acknowledgement (not a full `NextAnswer` — nothing about the run's own position changes). A caller
whose hand-off is legitimately still in progress calls this periodically (its own polling
interval, well under `lease_seconds`, is the caller's business, mirroring how Kubernetes' lease
objects and etcd's lease API — both well-documented, widely-used conventions for exactly this
"still alive, extend my hold" pattern — leave the renewal *cadence* to the client holding the
lease, not the server issuing it).

### Acceptance criteria

- **A1.** A claimed `MUTATION` step's lease, renewed via `heartbeat()` before it expires, is not
  taken over by a second `next()` call arriving after the *original* `lease_seconds` window but
  before the *renewed* one — proving renewal genuinely extends the deadline, not merely resets an
  internal counter nothing reads.
- **A2.** `heartbeat()` against a claim that has already expired and been taken over by another
  caller fails cleanly (the same `TAKEN_OVER` signal `acquire()` already surfaces), never silently
  re-granting a lease to a caller who may have already lost the race.

## Part 3 — ending-routing exhaustiveness (the fuller half of D40)

### Why this is closeable after all

D40 left this open, reasoning it needed "exhaustiveness-proof machinery comparable to V6's own
ROUTE-coverage check." Re-reading `_route_is_exhaustive` (`definition/validate.py`, backing `V6`)
directly for this design found that machinery already exists and is directly reusable: it proves
a `RouteNode`'s own `when` options cover every member of an enum-typed path. The only new work is
finding *which* `RouteNode`, if any, is the one that reads the path a `PROCESS`-mechanism call's
own `out:` mapping wrote `"ending"` into — not a guess, since `_all_targets` (`validate.py`'s own
reachability walker, already built) already knows how to follow a `StepNode.next` forward.

### Design

For every `PROCESS`-mechanism-calling `STEP` node that `D40`'s own check now requires to capture
`"ending"` into some `state.<path>`: walk forward from `node.next` (reusing `_all_targets`'s own
traversal, or a narrower purpose-built walk if `_all_targets`'s general shape doesn't fit
cleanly) until reaching either a `RouteNode` that tests `state.<path>` in every `when` option, or
exhaust the walk without finding one. If a `RouteNode` is found: apply `_route_is_exhaustive`'s
own logic, but against the *known, closed* value set from `mechanism.result.endings.values()`
(not a generically-declared enum's own members — the exact set this specific call can produce),
refusing if any mapped ending value has no corresponding `when` option and no `otherwise`. If no
such `RouteNode` is ever reached (the walk ends at another `STEP`, or an `end:`, without ever
testing the path): refuse — the captured value is provably never read at all downstream, the same
"dead data" signal this design's own D40 predecessor already refuses for the "never captured"
case, one hop further out.

**A genuinely open design choice, not resolved here:** should `state.<path>`'s own channel be
*required* to be declared `enum[...]`-typed (so the exhaustiveness proof is always attempted), or
should a plain `string`-typed channel be accepted, with this check simply unable to prove
anything and forced to always refuse absent an explicit `otherwise`? The former is stricter and
catches a typo'd ending value at validation time (matching `V6`'s own existing behaviour for a
plain `ROUTE`); the latter is more permissive of an author who genuinely doesn't want to enumerate
the type. This work package's own recommendation is the former (require `enum[...]`, consistent
with `V6`'s own precedent, and with what `examples/recursive-refinement/`'s own `inquiry_ending`
channel already does) — but flagged explicitly as a call worth revisiting once real authors have
used it, not a closed question.

### Acceptance criteria

- **A1.** A `PROCESS`-mechanism call whose captured `state.<path>` channel is `enum`-typed, and
  whose reachable `ROUTE` covers every value `mechanism.result.endings` can produce, is accepted.
- **A2.** The same shape missing exactly one mapped value from its `ROUTE`'s own `when` options
  (and no `otherwise`) is refused — the bad-but-conformant case this check exists for.
- **A3.** A capture with no reachable `ROUTE` reading it at all (an unconditional `next:`/`end:`
  regardless of the captured value) is refused — the exact shape D39's own minimal reproduction
  used, now closed for real rather than merely documented as a residual risk.

## Suggested PR sequence

Three independent PRs, in any order — `GATE kind: INPUT`, then claim renewal, then ending-routing
exhaustiveness is the order of decreasing urgency (an unresolvable open gate blocks a whole run
category today; the other two are narrower correctness/completeness gaps). Each carries its own
principal summary and run record (see `CLAUDE.md`).

## If the spec is wrong or silent

Part 3's `enum[...]`-required recommendation is proposed, not decided — the implementing PR is
where it becomes a real `Vn` rule with its own accepted/refused fixtures, and its own Dn entry
records whichever way it actually goes once tested against a real fixture.
