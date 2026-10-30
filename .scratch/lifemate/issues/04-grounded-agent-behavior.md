# 04: Correct grounded multi-step and clarification behavior

**Parent spec:** [LifeMate competition solution](https://github.com/huyxdang/three-good-boys/issues/1)

**What to build:** The agent completes supported latest-request actions using real observations and context, resolves dependent tool arguments, asks only for genuinely missing user information, and avoids invented or prohibited actions.

**Blocked by:** [02: Labeled-training evaluation](02-labeled-training-evaluation.md); [05: Compliant model selection](05-compliant-model-selection.md).

**Status:** ready-for-agent

**Owner:** Unclaimed

**Progress:** not-started

## Implementation steps

1. After tickets 02 and 05 are done, take observed failures from their fixed benchmark on permitted training cases; record baseline per-case outcomes for the selected model pair before touching the decision path.
2. In the existing `baseline/lifemate_v1.py` controller, validate tool arguments against the sample's actual catalog schemas and bind dependent values from prior tool results; keep the current invalid-proposal handling and simulator call log.
3. Route genuinely missing user input to `sys.ask_missing_info` and unsupported requests to the official behavior; leave lookup-available data to tools.
4. Cover the listed scenarios with training fixtures, then add deterministic behavior-level regressions (calls, clarification, ordering, final outcome) in the existing test convention beside `baseline/test_lifemate_v1.py`.
5. Rerun the ticket 02 benchmark after each single change and report deltas in reference-transcript and actual-ASR modes; retain a change only for measured improvement without regression.

## Acceptance criteria

- [ ] Select only tools available to the sample and validate their actual schemas, including organizer extensions. Bind identifiers from authorized context or observed tool results rather than invented names, IDs, or responses.
- [ ] Execute dependency reads before writes that need their results, feed real results into subsequent decisions, and preserve independent supported actions where the official contract permits partial completion.
- [ ] Distinguish data available through a lookup from input the user must supply. Use the actual sys.ask_missing_info contract for missing/ambiguous required information; follow the official unsupported-request behavior rather than a guessed system tool.
- [ ] Use profile, current time/timezone and relevant conversation references for the latest request without replaying actions already represented in initial state. Respect negation and installed-app boundaries.
- [ ] Retain invalid-proposal handling without deleting any call that actually reached the simulator. Verify rejected actual calls remain in the ordered export and that hashes come from the same live session.
- [ ] Demonstrate official-schema training scenarios for: one light; AC device resolution; multiple devices; ride home; missing ride destination; known-contact transfer; ambiguous recipient; incomplete food request; email recipient/content; smart-home plus ride; unsupported app; negation; history reference; invalid proposed tool; and an identifier returned by a prior tool.
- [ ] Keep deterministic behavior-level regressions for plausible failures fixed here, using existing test conventions and permitted fixtures. Assertions cover observable calls, clarification, ordering, or final outcomes rather than prompt wording or implementation structure.
- [ ] Run the fixed benchmark before and after each single change in both modes. Report score/outcome changes and new failures; retain the change only for measured improvement without regression.

## Verification

No implementation verification yet. Record the real training sessions used, expected versus observed behavior, benchmark deltas, and regression command. Restricted fixtures/traces remain in authorized storage.

## Comments

Improve the existing native baseline first. A compiler is an optional independently evaluated experiment, not a prerequisite for grounded behavior. Coordinate shared controller changes with the runtime owner through ticket comments.

Ordering authority: [decision-order.md](../../../docs/decision-order.md) (measure → ground → post-train); do not restate its table here.
