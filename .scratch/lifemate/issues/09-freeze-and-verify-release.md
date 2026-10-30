# 09: Freeze and verify the release artifact

**Parent spec:** [LifeMate competition solution](https://github.com/huyxdang/three-good-boys/issues/1)

**What to build:** The team has one auditable final solution package that combines the selected behavior, models and performance configuration, runs offline, and reproduces identical results for fixed inputs before submission.

**Blocked by:** [04: Grounded agent behavior](04-grounded-agent-behavior.md); [05: Compliant model selection](05-compliant-model-selection.md); [07: A30 execution budget](07-a30-execution-budget.md); [08: Offline Docker execution](08-offline-docker-execution.md).

**Status:** ready-for-agent

**Owner:** Unclaimed

**Progress:** not-started

## Implementation steps

Before final freeze, record the Phase 5 decision and its evidence in ticket 05 or a new ticket in dependency order: retain a fine-tune only when it passes the decision-order gates, reject it with the required evidence, or skip training if baseline and grounding solve the measured categories. Weight training is not mandatory. Ticket 08 may prepare the baseline image in parallel.

1. Combine the selected behavior (ticket 04), model artifacts (ticket 05) and measured performance config (ticket 07) into the offline image from ticket 08; exclude the optional compiler path unless it passed these same checks.
2. Write a freeze manifest in authorized team storage: source revision, image digest, dependency locks/checksums, model revision hashes, simulator release, configuration and seeds. No weights or restricted files in public commits.
3. Check parameter counts, context limit, licenses and redistribution terms against current organizer requirements and confirm the release location is reachable by registered teammates.
4. Run replay A on the permitted split with frozen inputs/config; archive ordered calls, args, final hashes and the JSONL.
5. Run replay B identically; diff calls, arguments, hashes and output versus A and explain every difference.
6. Validate coverage, schema, duplicates/extras, executed calls and env-derived hashes with the official validator where available, labeling local checks as local; retain full-split target timing for the frozen image.
7. Compute the package checksum, verify it after transfer to the authorized location, record clean invocation/mounts/expected output, and record portal requirements and deadline with source and check date.

## Acceptance criteria

- [ ] Before final freeze, record the Phase 5 decision (fine-tune retained, rejected, or skipped) and supporting evidence in ticket 05 or a new ticket in dependency order. Skipping is permitted when baseline and grounding solve the measured categories; weight training is not mandatory.
- [ ] Integrate the completed selected behavior, exact model artifacts and measured performance configuration into the final offline container. The optional compiler experiment is excluded unless its retained implementation has passed the same release checks.
- [ ] Record a freeze manifest covering source revision, image/package identity, artifact/dependency versions and checksums, model revisions, simulator release, configuration and seeds. Do not place restricted files or model weights in public commits or releases.
- [ ] Verify all model and auxiliary parameter counts, effective context limit, target hardware/memory, release eligibility, open-source licenses and redistribution rules against current official requirements. Confirm authorized registered-team access to the release location.
- [ ] Run two complete local offline replays of the same permitted evaluation split using identical frozen inputs, artifacts and configuration. Compare actual ordered calls, arguments, final hashes and serialized output; investigate every unexplained difference.
- [ ] Validate full ID coverage, schema, no duplicate/extra records, all actually executed calls, environment-derived hashes and absence of hidden online dependencies. Use the official validator/evaluator where available and label local diagnostics accurately.
- [ ] Retain full-split target-equivalent timing/resource evidence for the frozen image under the current timing convention. Confirm every observed sample meets the required cap, not merely the average.
- [ ] Compute the final package checksum and verify it after transfer to the authorized submission location. Document the clean-machine invocation, required mounts, expected output and failure/recovery behavior without relying on private home paths.
- [ ] Record current portal submission requirements and deadline with source/check date; resolve discrepancies with historical handoffs before calling the artifact ready.

## Verification

No implementation verification yet. Record the Phase 5 decision and evidence, both full replay commands/results, comparison outcome, final image timing, compliance inventory, package checksum and reproduction instructions. Do not mark complete from toy tests or a successful image build.

## Comments

Do not update the submitted solution during private evaluation outside the organizer's permitted process. Package distribution and any repository visibility change require the owner's explicit authorization.

Ordering authority: [decision-order.md](../../../docs/decision-order.md) (measure → ground → post-train); do not restate its table here.
