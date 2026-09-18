# request-review — brain

Source: plugins/sulis-brain/instances/request-review/workflow.jsonld
Purpose: Open a real integration request (PR) for a change that was already committed and pushed, so a person can review it, while being structurally unable to synchronize, verify or merge.
Use cases: UC-IN-TYPED, UC-IN-AMBIENT, UC-OPTIONAL-BRANCH, UC-PRECONDITION, UC-RETRY, UC-STOP-NAMED, UC-FAILURE-MODES, UC-SIDE-EFFECT-CLAIM, UC-TOOL-EFFECT, UC-TOOL-RUNNER, UC-CAPABILITY, UC-CRITICALITY, UC-MECHANISM, UC-CALL (as a callee of change-lifecycle `publish`)

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| declare-release-intent | deterministic | Ensures the release artifact (changeset) is present; skips its action when `release_trigger == manual` → `release-intent-ref` | api-declare-release-intent (subprocess `request_review_cli declare`, side-effect) |
| stage-release-intent | deterministic | Stages the artifact (no-op pass-through in the API flow) → `release-intent-staged` | api-stage-release-intent (subprocess `request_review_cli stage`) |
| commit-release-intent | deterministic | Builds commit + branch via the GitHub tree API; idempotent on an existing branch → `release-intent-committed` | api-commit-release-intent (subprocess `request_review_cli commit`) |
| request-integration | deterministic | Opens the PR against integration-branch resolved from the profile; idempotent on an existing PR → `integration-request-ref`, `final-outcome` | api-request-integration (subprocess `request_review_cli request`) |

No parallel starts, fan-out or joins: a straight line. No triggers: it is only ever called by change-lifecycle's `publish` step (via workflow_dispatch tool `dna:tool:01KYS6RMMJ7ZY6NDJN0E9BA4C0`).

## Routes as declared
- `declare-release-intent -> stage-release-intent [always proceeds; declare-release-intent's own agent_instructions skip its action entirely when release_trigger == manual, matching land-change's identical convention]` → unconditional; the optional branch is a skip inside the step on GitWorkflowProfile `release_trigger` (not a state key).
- `stage-release-intent -> commit-release-intent [always proceeds; skipped identically when release_trigger == manual]` → unconditional; skip inside the step.
- `commit-release-intent -> request-integration [always proceeds; skipped identically when release_trigger == manual]` → unconditional; skip inside the step.
- `request-integration -> [terminal:review-requested] [a PR is open against integration-branch -- final-outcome == review-requested; NO further step exists in this Workflow, so integration/merge is structurally unreachable]` → terminal verdict `review-requested`.
- Failure mode empty-diff-nothing-to-publish (abort, precondition on request-integration) → short-circuit before request-integration; reports `final-outcome = proven` to the caller (state enum offers `no-changes`).
- Failure mode gh-pr-create-transient-failure (retry) → retry request-integration, budget 3 attempts with short backoff; exhaustion → block (verdict `blocked`, in the state enum only).

## Scenarios
### S1 — Changeset flow, PR opened
- Inputs: `change-ref = "feat/csv-export"`, `git-workflow-profile-ref` → `{release_trigger: changeset-release-on-merge, integration_branch: main}`; caller supplies `branch_name`, `user`, `message`, `slug`
- Scripted: declare → changeset present; stage → pass-through; commit → branch built; request-integration → PR #412 opened
- Expect visited: [declare-release-intent, stage-release-intent, commit-release-intent, request-integration]
- Expect gates: []
- Expect terminal: review-requested

### S2 — Manual release trigger
- Inputs: profile `{release_trigger: manual, integration_branch: main}`
- Scripted: first three steps run and skip their action; request-integration → PR opened
- Expect visited: [declare-release-intent, stage-release-intent, commit-release-intent, request-integration]
- Expect gates: []
- Expect terminal: review-requested

### S3 — Empty diff, nothing to publish
- Inputs: as S1, branch has no diff against `main`
- Scripted: first three steps succeed; request-integration precondition (non-empty diff) fails
- Expect visited: [declare-release-intent, stage-release-intent, commit-release-intent]
- Expect gates: []
- Expect terminal: no-changes (best reading of the state enum; the failure mode says report `proven` to the caller)

### S4 — Transient PR failure, recovered on retry
- Inputs: as S1
- Scripted: request-integration attempt 1 → API 502; attempt 2 → PR opened
- Expect visited: [declare-release-intent, stage-release-intent, commit-release-intent, request-integration, request-integration]
- Expect gates: []
- Expect terminal: review-requested

### S5 — Transient failures exhaust the retry budget
- Inputs: as S1
- Scripted: request-integration attempts 1, 2, 3 → rate limited
- Expect visited: [declare-release-intent, stage-release-intent, commit-release-intent, request-integration, request-integration, request-integration]
- Expect gates: []
- Expect terminal: blocked

## Ambiguities for the process owner
- The optional release-intent branch is expressed as "the step runs and skips itself", not as a route. An engine cannot tell a skipped step from a completed one.
- The empty-diff outcome has three names: `no-changes` (state enum), `proven` (failure-mode recovery text), and no terminal verdict in transitions. It is deliberately not a terminal step because the dispatcher only resolves `terminal_steps[0]`.
- `blocked` appears only in the state enum; no route or terminal declares it.
- Steps read `recorded-revision-ref` and `published-ref`, which are not in `state_contract`; tool arguments `branch_name`, `user`, `message`, `slug`, `integration_branch` are not declared inputs.
- Step text says tools are `python_import`; tools.jsonld binds `subprocess`. The failure mode names `gh pr create`, but the tool is an API CLI.
- Retry backoff duration is "short", i.e. UNSTATED.
- `release_trigger` values other than manual / changeset / tag are unrouted.
- Idempotency is claimed in tool prose (existing branch, existing PR) but no claim or idempotency key is declared.
