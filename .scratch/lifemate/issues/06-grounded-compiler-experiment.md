# 06: Evaluate grounded compiler versus native tool calling

**Parent spec:** [LifeMate competition solution](https://github.com/huyxdang/three-good-boys/issues/1)

**What to build:** The team has a controlled, reproducible answer to whether structured decisions plus grounded reference binding improve this task compared with the working native tool-calling baseline. A measured rejection is a completed experiment, not an unfinished feature.

**Blocked by:** [02: Labeled-training evaluation](02-labeled-training-evaluation.md).

**Status:** ready-for-agent

**Owner:** Unclaimed

**Progress:** not-started

**Release gate:** No. No submission ticket depends on this experiment.

## Implementation steps

1. Write the hypothesis and freeze the native baseline, training cases, model/runtime settings and evaluation method, pointing at the ticket 02 benchmark and baseline report.
2. Build the smallest real compiler candidate: model emits a structured decision, authorized observations supply dependent values, catalog schemas validate arguments, one official environment executes and returns the hash. No agent framework.
3. Exercise unsupported tools, unresolved references, missing input and invalid arguments; confirm no fabricated responses and that every actual call is preserved.
4. Run native and compiler candidates on identical permitted inputs and tabulate task outcomes, invalid-argument rate, tokens, latency and peak memory, marking unavailable measurements.
5. Record failure cases and decide retain or reject from evidence; on reject, delete the experimental path and keep only the decision report.

## Acceptance criteria

- [ ] State the specific hypothesis and freeze the native baseline, permitted training cases, model/runtime settings and evaluation method before changing the decision path. No broad agent framework is required.
- [ ] Exercise a minimal real end-to-end candidate: model emits a structured decision, authorized observations supply dependent values, actual catalog schemas validate arguments, and the official environment executes calls and returns the exported hash.
- [ ] Test unsupported tools, unresolved references, missing required input and invalid arguments without fabricated responses or silent guessing. Preserve every actual call and use exactly one environment per sample.
- [ ] Run native and compiler candidates on identical permitted inputs. Report task score/outcomes, invalid-argument rate, generated tokens, end-to-end latency and peak memory; label unavailable measurements rather than implying a proven speedup.
- [ ] Record failure cases and the measured retain/reject decision. Keep the native path if the compiler has no supported benefit or a material unexplained regression; do not declare success from shorter JSON alone.
- [ ] If retained, finish its integration, observable-behavior regressions and documentation before selecting it for release. If rejected, remove experimental scaffolding and retain only the decision/evidence report, not an unused alternate runtime path.

## Verification

No implementation verification yet. Record matched comparison commands, observed metrics, real simulator output evidence, and the retain/reject rationale.

## Comments

The planning handoff proposes this architecture; it does not prove benefit. Work independently from required baseline fixes, and coordinate any shared controller edits with the relevant ticket owner.
