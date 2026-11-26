# Upsert a content type

## What it is

`upsert-a-content-type` is a general Process: it takes a request and a type name and ends with a content type saved, found unchanged, or a person told what is in the way. It reads what is stored, has the host draft the manifest and its output Profile, checks the draft by computation (including the add-only rule: a customer's version of a system type may add Profile properties, never remove or retype one), tries the type's own Process, asks for approval, and only then saves. The library holds the Process, its Tools as contracts, its Profiles, one pure reference module and tests that use the engine's own stubs; it holds no prompt text, no storage and nothing from the platform.

## Files

- `upsert-a-content-type.process.yaml`: the Process (eight steps from the brief, plus `tell` and `after-upsert`).
- `upsert-a-content-type-standing-rule.control.yaml`: the standing rule the host evaluates before a person is asked at the gate.
- `read-content-type.tool.yaml`, `draft-content-type.tool.yaml`, `check-content-type.tool.yaml`, `try-content-type.tool.yaml`, `upsert-content-type.tool.yaml`, `tell-what-is-in-the-way.tool.yaml`: the six Tool contracts; `upsert-content-type` is the only one that changes anything.
- `finding`, `manifest-draft`, `content-type-snapshot`, `trial`, `upsert-result`, `telling` (each `.profile.yaml`): six closed Profiles.
- `checks.py`: the reference bodies of `check` and `tell` (the add-only rule, the reference checks, the hash). Pure, standard library plus `jsonschema`, no platform import.
- `../../tests/examples/test_upsert_a_content_type.py`: the tests, driven through the real engine.

## Validate it

```
sulis-workflows validate src/sulis_workflows/definition/builtin/*.yaml examples/upsert-a-content-type/*.yaml
```

Expected: every line `OK`.

## What a host binds

| Ref | Kind | Duty |
|---|---|---|
| `upsert_a_content_type.hooks:read_content_type` | CODE | Answer the stored type and the system Profile; a foreign type reads as unknown. |
| `upsert_a_content_type.hooks:check_content_type` | CODE | Bind `checks.check_content_type` as it is, or wrap it. |
| `upsert_a_content_type.hooks:upsert_content_type` | CODE | Recompute the hash, same hash first, then compare-and-set on the base hash; refuse a draft that is not add-only over a system Profile the host holds. |
| `upsert_a_content_type.hooks:tell_what_is_in_the_way` | CODE | Bind `checks.tell_what_is_in_the_way` as it is, or wrap it. |
| `content-type-tester` | EXTERNAL | Run the type's own Process in isolation; only `PASSED` with no findings passes. |
| `needs/draft-content-type-manifest` | SKILL (a need) | The host supplies the instructions; the library ships none. |

Eight permission strings, all `workflows.upsert-a-content-type.<verb>`: `start`, `read`, `draft`, `check`, `try`, `upsert`, `tell`, `approve`. The grammar is the host's. Each duty is written in the Tool's own contract.

## What is proven

Each line is a claim and the test that proves it. Where a claim depends on how the host drives the engine, the condition is in the line.

- CLAIM: Every definition in the example validates with the built-in set. (proof: test_every_definition_in_the_example_validates_with_the_builtin_set)
- CLAIM: Removing any supporting file makes validation refuse. (proof: test_removing_any_supporting_file_makes_validation_refuse)
- CLAIM: The reference checks import nothing from the platform or a vendor. (proof: test_the_reference_checks_import_nothing_from_the_platform_or_a_vendor)
- CLAIM: A clean run reaches UPSERTED by read-existing, draft, check, try, approve, upsert. (proof: test_c2_a_clean_run_reaches_upserted)
- CLAIM: A draft that drops a system Profile property is refused before the trial, although a naive manifest check passes it. (proof: test_c3_a_dropped_property_never_reaches_try_or_upsert)
- CLAIM: Fourteen drafts that pass a naive add-only rule are each refused. (proof: test_bad_but_conformant_is_refused)
- CLAIM: Annotation-only changes (title, description, examples, a `default` where the system Profile has none, a 2020-12 `$schema`) are accepted at any path. (proof: test_annotation_only_changes_are_accepted)
- CLAIM: The other changes beside those annotations are still refused. (proof: test_the_other_changes_are_still_refused)
- CLAIM: A `$ref` with sibling keywords is judged as the target and its siblings together, so a sibling cannot hide a retype or a tightening. (proof: test_a_descending_sibling_beside_a_ref_is_judged)
- CLAIM: A `default` is free only where the system Profile has none. (proof: test_a_default_is_free_only_where_the_system_profile_has_none)
- CLAIM: The check loop ends after three send-backs, saying what failed. (proof: test_c4_the_check_loop_ends_after_three_send_backs)
- CLAIM: The trial loop ends after three send-backs, saying what failed. (proof: test_c4_the_trial_loop_ends_after_three_send_backs)
- CLAIM: Nothing is saved without passing the gate, for a caller that reports the offered node. (proof: test_every_path_to_upsert_passes_the_gate)
- CLAIM: An INDETERMINATE standing rule waits for a person, for a caller that reports the offered node. (proof: test_c5_an_indeterminate_standing_rule_waits_for_a_person)
- CLAIM: Every step asks the policy port before it runs, for a caller that reports the offered node. (proof: test_c6_every_step_asks_the_policy_port_before_it_runs)
- CLAIM: A denied upsert leaves the type unsaved, for a caller that reports the offered node. (proof: test_c6_a_denied_upsert_leaves_the_type_unsaved)
- CLAIM: The definitions hold no prompt text. (proof: test_the_definitions_hold_no_prompt_text)
- CLAIM: The draft step hands the host a need and its inputs only. (proof: test_the_draft_step_hands_the_host_a_need_and_its_inputs_only)
- CLAIM: Every claim in this README names a test that exists. (proof: test_every_claim_in_the_readme_names_a_test_that_exists)

## Host duties

Report to the engine only the node `next` offered: the engine records a `report` for any node, even one that is not current (gap G8), and a forged report of `upsert` before the gate ends the run `UPSERTED` with nothing saved; two strict-xfail tests pin this (`test_an_action_out_of_turn_records_nothing`, `test_a_run_never_ends_upserted_without_a_save`) and will fail the day the engine fixes it. An identity that runs the Process and holds the approve permission can approve its own draft, so a host that wants two people maps them to different roles. A host that answers PERMIT for the standing rule saves with nobody asked.

## What is not proven

- G1: a SKILL ref that is a need the host resolves has no words in the spec; the validator does not resolve SKILL refs.
- G2: an empty string or an empty list from a single mapped path counts as not present, so optional inputs carry defaults and "nothing stored" is the word `NONE`.
- G3: a route on an error cannot carry the error code into state, so a stop cannot name which Tool failed.
- G4: loop counters are per route and cannot be shared, so there are three counters of three, not one pool.
- G5: an expression may read a field of a profile-typed value and a mapping may not; the Process is shaped around that.
- G6 and C8: the content-type tester refuses every non-SKILL Tool, so running the read-only nodes through it, and repeating the model grid, belong to the operations repository and are not proven here.
- G7: the engine did not refuse a wrong-typed primitive output (a `boolean` that came back as a string); nothing here relies on it, and no test pins it.
- G8: the engine accepts a `report` for a node that is not current (see Host duties).
- Known limit: the add-only rule compares JSON values exactly, so a `const` of `1` against `1.0` is refused although they are equal in JSON Schema; the refusal fails closed.
- Known limit: a customer's version may not tighten a system Profile (a longer minimum length, a field made required) and may not drop a property it added itself in an earlier version; the first is refused, the second is not checked.
- Known limit: a `$id` on a referenced `$defs` entry is accepted as an annotation, although it can make a local `$ref` dangle for a consumer.
- Known limit: a `$schema` written `http://...` or with a trailing `#` is refused although it names the same dialect; only the exact 2020-12 URI, or the system Profile's own value, passes.
- Known limit: a draft nested more than about 100 levels raises `RecursionError` out of `check_schema`, so the run ends `FAILED`; that fails closed.
- Known limit: a schema that can never be satisfied, by design of its author, is not judged by the add-only rule; the trial would catch it.
- The add-only rule: annotations (`title`, `description`, `examples`, `$comment`, `$id`, `deprecated`) are free at any path; `$schema` is free only when it names 2020-12 or equals the system Profile's; `default` is free only where the system Profile has none at that node (a changed or removed default changes what a consumer is handed). A `$ref` with siblings is judged as the allOf of its target and the siblings, so a sibling `required`, `properties` or `items` is compared, never dropped. A `$ref` must still be local, resolvable and acyclic; a `$dynamicRef` is refused.
- Decision D-i: a draft may add a `default` where the system Profile has none. Open question O4 for the principal: if nothing is done, consumers that fill defaults may fill values the platform did not choose.
- Python 3.10 to 3.12 run the tests; the library's CI matrix is the proof for those versions.

## The proposed spec change

For `docs/spec/process-definition.md` (not made here): section 4.3, the SKILL row, add "A SKILL Tool's `ref` MAY name a need, written `needs/<kebab-name>`: instructions the host supplies, which the library that declares the Tool does not hold. The hand-off (section 12.1) carries the ref as `instructions_ref`. A host that cannot resolve a need MUST refuse the hand-off with a permanent error and MUST NOT run the step with empty or default instructions." Section 14: "V2 refuses a need ref that is not of the form `needs/<kebab-name>`." Section 18: a decision recording that a need is a ref the library cannot check and the host must. Also, for G8, section 12.1: a `report` for a node that is not the one handed off is refused and recorded as nothing.
