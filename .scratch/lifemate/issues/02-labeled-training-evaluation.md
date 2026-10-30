# 02: Establish labeled-training evaluation

**Parent spec:** [LifeMate competition solution](https://github.com/huyxdang/three-good-boys/issues/1)

**What to build:** A teammate can run a fixed permitted-training benchmark, compare changes against a saved baseline, and tell whether a failure came from speech recognition, tool planning, execution, or export.

**Blocked by:** [01: SDK contract and training replay](01-sdk-contract-and-training-replay.md).

**Status:** ready-for-agent

**Owner:** kitkitkittt

**Progress:** in-progress

## Implementation steps

1. Freeze a training sample set (IDs, counts, seeds, audio and label identities) drawn only from organizer-permitted training material; write the benchmark invocation and record ASR/model revisions and hardware.
2. Keep three distinct run modes: supplied reference-call replay for SDK integration, a planner diagnostic using legitimate reference transcripts, and actual audio-path ASR plus planning. The planner diagnostic may receive the transcript, never reference calls/results/final states; label its metrics separately from audio inference and identify cached predictions.
3. Give the policy only an explicit input allowlist: request transcript, context, permitted history and schemas. Keep reference calls and final states in the evaluator, even if they are loaded from the same training row; assert they never enter the prompt or tool observations. Mark any locally implemented matching metric as approximate until the official evaluator/specification is verified.
4. Emit a per-sample trace (calls, tool results, final state hash, latency, tokens) and a report with counts, tool-call matching rules and per-category failure assignment. Keep traces in restricted storage outside public commits.
5. Save one baseline report; rerun the evaluator on saved predictions to confirm identical metrics, then perform a fresh live model-driven training run through the working runner. A supplied-reference SDK replay cannot substitute for policy evaluation.

## Acceptance criteria

- [ ] Define fixed training cases, artifact/runtime identities, seeds, and a documented invocation. Never feed labels, reference calls, final states, or oracle answers into the policy under evaluation.
- [ ] Evaluate the same cases with legitimately supplied reference transcripts and with actual ASR transcripts. Report transcript-only and audio-path results separately; cached inference may bootstrap evaluation but must be identified.
- [x] Use the official evaluator when available. Otherwise identify precisely which diagnostics are local approximations and why; never turn schema-valid coverage or the historical portal score into a new accuracy claim.
- [ ] Report evaluated/successful sample counts, official score when available, final-state outcomes, tool-call precision/recall/F1 under documented matching rules, missing-information and unsupported-request outcomes, invalid/unknown calls, execution failures, unnecessary calls, and output failures. Explain unavailable metrics rather than substituting invented values.
- [ ] Report end-to-end latency distribution including p50, p95, maximum and timeout count, plus peak memory and generation-token counts when supported. Identify hardware and whether timings meet target-equivalent evidence requirements.
- [ ] Record ASR WER and critical-slot outcomes on labeled training audio where permitted, without normalizing away identifiers, amounts, names, or dates that change the intended action.
- [ ] Assign a primary failure category per failing case: ASR, intent, tool choice, argument value, dependency, order, unnecessary call, clarification, unsupported request, runtime, or submission/hash. Keep authorized diagnostic events available for investigation.
- [ ] Save one stable baseline report with the exact sample set and configuration. Re-running the evaluator on the same saved predictions produces the same metrics; a fresh live integration run also demonstrates the evaluation path.

## Verification

Saved-artifact evaluation slice implemented locally in `baseline/evaluate_training.py`, with behavior regressions in `baseline/test_evaluate_training.py`. See [the evaluation runbook](../../../docs/training-evaluation.md) for commands, mode/provenance requirements, local matching choices and metric limits. These competition-code paths remain Git-ignored; only safe documentation and status changes are committed to the public-repository branch.

- Frozen seed-0 benchmark of 12 permitted training IDs; input JSONL/catalog/SDK and selected latest/history audio are fingerprinted. Existing evidence is never overwritten.
- Real SDK replay of supplied reference-call artifacts: all 12 intended canonical states and local full-credit outcomes matched, zero schema errors. This is evaluator integration evidence, not ASR/LLM inference or an official score.
- No-action artifacts on the same cases: two full-credit empty-gold cases, four matching final states. Correct-state/schema checks alone did not produce full task credit.
- Repeated saved-prediction evaluation produced identical aggregate and per-sample output. Artifact-hash mismatch saves diagnostics and exits nonzero; missing IDs, changed identities, missing model provenance and nonempty output destinations fail explicitly.
- Regression coverage exercises strict fuzzy threshold/Unicode/multiset behavior, maximum one-to-one matching and duplicate calls, exact argument types, canonical scalar serialization, empty-gold precedence, malformed JSON/IDs and ASR-versus-reference-transcript diagnostic precedence.
- Local evidence under `work/evaluation/`; no raw environment files or public/private evaluation labels were inspected to solve tasks.

At the time of the saved-artifact evaluator work, paired live reference-transcript/actual-ASR model runs, measured inference metrics, critical-slot evaluation and causal failure classification remained open. Subsequent coordination evidence is linked in Comments; the owner has not closed the remaining acceptance criteria.

## Comments

The existing public validation report checks coverage/schema/session consistency, not task success. Do not manually label public/private samples for training or tuning.

2026-10-29 coordination from omp: paired live 12-case reference-transcript and actual-ASR runs, deterministic saved-output reevaluation, proxy per-case time and PyTorch GPU-memory measurements, and exploratory failure triage and critical-span analysis are documented in [the evaluation runbook](../../../docs/training-evaluation.md). Actual-ASR failure categories are single-reviewer primary judgments, not evaluator-generated causal classifications; the critical-span check is incomplete and measures exact text recall, not complete semantic slot accuracy. Restricted traces remain in private workspaces. This evidence does not establish the critical-slot or failure-category acceptance criteria or close the ticket; the owner retains control of its Progress and acceptance fields.

2026-10-29 coordination from omp: the same frozen cases were evaluated with a fresh planner using separately cached large-v3 ASR transcripts; aggregate and per-sample saved-output evaluation were byte-identical on repeat. See the [evaluation runbook](../../../docs/training-evaluation.md) for metrics and provenance limits. This supplementary comparison does not change ownership, completion or the outstanding acceptance criteria.
