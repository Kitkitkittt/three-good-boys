# 11: Run and submit private evaluation

**Parent spec:** [LifeMate competition solution](https://github.com/huyxdang/three-good-boys/issues/1)

**What to build:** After the organizer releases private input, the registered team runs that input through the same frozen submitted solution, validates complete output, and submits results through the official process without tuning on private answers.

**Blocked by:** [10: Submit the frozen solution](10-submit-frozen-solution.md). Also requires organizer release of private input and registered-team access; these are external gates, not extra ticket dependencies.

**Status:** ready-for-human

**Owner:** Unclaimed

**Progress:** not-started

## Implementation steps

1. A registered member fetches private input via the authorized channel and records the release identity, current instructions and result deadline/timezone; keep input off public issues/commits.
2. Confirm the submitted package checksum matches ticket 10's record and use its documented clean invocation unchanged.
3. Run the frozen container offline with the private input and required hardware/mounts; log per-sample completion and timings.
4. Validate output: one record per ID, schema/types, no duplicates/extras, session calls/hash consistency, all executed and rejected calls; use official validation if provided.
5. Record package identity, input release identity, invocation, completion count, validation outcome and output checksum in authorized team storage.
6. Submit results through the official channel before the deadline; record acceptance time/timezone and later the official result, keeping acceptance distinct from score.

## Acceptance criteria

- [ ] A registered team member obtains private input through the authorized release channel and verifies current instructions, result deadline/timezone and any organizer-specific execution requirements. Do not redistribute the input or request private reference labels.
- [ ] Verify the exact submitted frozen package checksum and runtime invocation before execution. Use its existing split/catalog handling; do not change model weights, prompts or runtime for private data unless explicitly permitted by the organizer and recorded through the official process.
- [ ] Execute the frozen container offline with the supplied input and required hardware/mounts. Preserve exactly one official environment per sample, every actual executed call and each environment-derived final hash; never inspect raw environment files to solve requests.
- [ ] Validate one result per supplied ID, schema/types, no duplicates or extra output fields, session call/hash consistency and recorded execution timing. Use available official validation without manually labeling or tuning on private cases.
- [ ] Record package identity, input release identity, invocation, completion count, validation result and submission-file checksum in authorized team storage. Keep private inputs, outputs, traces and access links out of public issues/commits.
- [ ] Submit results through the official channel before the verified deadline. Record human-observed acceptance, submission time/timezone and the official result when available; do not conflate format acceptance with a score.

## Verification

No private input obtained or execution/submission performed. Completion requires observed frozen-package execution, complete output validation, checksum and official receipt. Record any unreleased input or missing access as the exact external blocker.

## Comments

The planning handoff reports a November 20 private release and November 23 result deadline. Recheck the live organizer schedule; do not build against invented private schemas or claim those dates were verified by this setup.
