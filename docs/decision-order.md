# Decision order: measure → ground → post-train

Ordering authority for measurement-before-weights. Tickets 04, 05 and 09 point here instead of
restating this table; keep it the only copy.

The path is fixed: a frozen benchmark and a real Linux run, then measured model selection and
grounding for the measured failure categories, then post-training only for categories that grounding
leaves broken. No fine-tuning starts before a measured baseline and a grounding plateau exist.

## Decision order

| Step | Change | Evidence required to proceed |
| --- | --- | --- |
| 1 | Freeze the benchmark and run the baseline for real on Linux | A baseline score exists for the frozen case set from an actual run, not a historical report or a smoke replay |
| 2 | A/B the ASR and select models on the same cases | WER and critical-slot deltas on identical audio; separate ASR and planner effects, measure both reference-transcript and ASR modes, and select an eligible ASR/LLM pair |
| 3 | Grounding: schemas, prompt, lookup broadening, dependency ordering, clarification | Assess every available lever against the measured failures; retain a change only if it measurably improves the frozen benchmark without regression |
| 4 | Grounding plateau | Document exhausted or unavailable levers and measured outcomes; no attempted change yields a further measured gain without regression |
| 5 | LoRA SFT for the remaining categories | Retain only if gain exceeds variance measured on two identical control runs, with no regression |
| 6 | ASR LoRA only if critical-slot failures dominate | Retain only with WER improvement plus critical-slot improvement, not WER alone |

Steps run in order. Test one grounding change per benchmark run; revert or drop changes that do not
improve the benchmark without regression, then assess the next lever. Documented exhaustion permits
Phase 5 even if no grounding attempt helped. Missing baseline or measurement evidence still blocks
progression; a failed experiment is not evidence of a gain. Planner SFT may be skipped or rejected
without preventing a separately gated ASR adaptation; record each skip or rejection.

## Phase 3–7 sequence

The original prompt already placed post-training after a measured Phase 3 baseline and explicitly
said not to start with fine-tuning. This order adds a grounding plateau as an additional gate and
inserts grounding before the original post-training work; packaging and submission still follow it.

- **Phase 3 — measure and select models.** On the real Linux runtime, establish the frozen-benchmark
  baseline and run ticket 05 model selection and ASR A/B using ticket 02 evaluation. Measure the same
  cases separately in explicitly labeled reference-transcript and actual-ASR modes, separating ASR
  and planner effects. Select an eligible ASR/LLM pair and report per-category failures. No grounding
  behavior edit or weight change is part of this phase.
- **Phase 4 — ground before weights** ([ticket 04](../.scratch/lifemate/issues/04-grounded-agent-behavior.md),
  after [ticket 05](../.scratch/lifemate/issues/05-compliant-model-selection.md)). Attack the measured
  categories with the four levers in this order:
  1. Schema/grammar-constrained decoding for tool calls — compiler-side, no weight change.
  2. Prompt/system-prompt corrections.
  3. Lookup broadening plus dependency and ordering rules.
  4. Clarification and unsupported-request policy.

  Assess every lever for applicability, attempt and benchmark each available lever, and document any
  unavailable lever with the reason. Change one thing per benchmark run and retain it only if it
  shows an improvement with no regression; revert or drop non-improving changes. Record the measured
  outcomes and the grounding plateau, even if no attempt helped, before considering post-training.

### Phase 5 — post-train only what measurements leave broken

Consider post-training only for measured categories that remain broken after the grounding plateau.
It may be skipped or rejected when the criteria are not met. Record the Phase 5 decision and evidence
in ticket 05 or a new ticket in dependency order before final freeze. The following are proposed
settings, not verified model eligibility or validated hyperparameters; ticket 05 and current official
rules must establish eligible models and data before training.

- **Data firewall.** Use only permitted training-split examples. Select failure *categories* from the
  held-out frozen benchmark, but obtain training examples from distinct permitted non-benchmark IDs.
  Exclude benchmark IDs and every example or variant derived from them, including ASR-transcript and
  augmented variants. Use an assertion script that diffs the frozen benchmark ID set against both
  training IDs and every example's source/provenance IDs, failing on any overlap. Record counts, the
  assertion command and its evidence in the training ticket.
- **Planner SFT.** The proposed target is `Qwen/Qwen3-4B-Instruct-2507`, subject to ticket 05's
  measured selection, eligibility and official rules. Use LoRA, or QLoRA if VRAM-limited; proposed
  settings are rank 16–32, alpha twice the rank, dropout 0.05, learning rate 1e-4–2e-4 with cosine
  scheduling, 1–3 epochs, bf16, and a fixed seed. Train on distinct permitted examples in the measured
  intent, tool-choice, argument-value, dependency, or order failure categories, not the entire dataset.
  Construct targets from actual reference calls using exactly the tool-call serialization parsed by
  the runner's `parse_calls`; do not introduce another format. Planner inputs are context, installed-tool
  schemas and the reference transcript, never `label`, reference calls/results, or `final_state` as
  inputs. Reference calls are training targets only.
- **Mandatory ASR-robustness variant.** Train and report the same targets with actual Phase 1 ASR
  transcripts from the distinct permitted training examples, as well as the reference-transcript
  variant, to measure the inference-time distribution. Both variants obey the same ID firewall.
- **Merge and compliance.** Merge adapters into one checkpoint; verify merged-versus-adapter output
  equality on 20 samples and record merged weight hashes. Recheck the parameter count after merging
  (the model must not change parameter class), total learned parameters, effective context configuration,
  and applicable official limits and eligibility.
- **Optional ASR adaptation.** Consider LoRA on a Whisper/PhoWhisper encoder-decoder only when
  measured critical-slot failures dominate, with the same held-out firewall. Preserve Vietnamese
  diacritics and evaluate WER and critical-slot exactness before and after; WER alone is insufficient.
- **Acceptance or rejection.** Measure variance with two identical control runs on the frozen benchmark.
  Ship a fine-tune only if its local score improves beyond that variance without regression, including
  clarification and unsupported-request behavior. Otherwise document rejection, keep the base model,
  and delete the rejected training scaffolding. Record data counts, hyperparameters, GPU, wall time,
  assertion evidence, before/after metrics, and all other relevant evidence under Verification in
  ticket 05 or a new ticket in dependency order. Do not publish restricted examples or traces.

### Phase 6 — package and freeze

After the Phase 5 decision is recorded, finalize [ticket 07](../.scratch/lifemate/issues/07-a30-execution-budget.md),
[ticket 08](../.scratch/lifemate/issues/08-offline-docker-execution.md), and
[ticket 09](../.scratch/lifemate/issues/09-freeze-and-verify-release.md). Ticket 08 may prepare a
baseline image in parallel before that decision. Build the offline Docker
image with weights baked in, `/data` mounted and `result/submission.jsonl` written, with no network or
downloads; pin CUDA/base image, driver assumptions and entrypoint, and obtain the exact organizer
packaging instructions rather than inventing them. Measure the integrated configuration's latency
distribution, timeouts, peak VRAM, total parameter inventory and licenses. Perform two complete matching
replays with identical artifacts and byte-identical outputs, then freeze the image, checksums and config
manifest. Preserve the original handoff separately.

### Phase 7 — human submission and private evaluation

[Ticket 10](../.scratch/lifemate/issues/10-submit-frozen-solution.md) and
[ticket 11](../.scratch/lifemate/issues/11-private-evaluation-and-results.md) are human-only gates.
Prepare the package, checksums and reproduction instructions, but do not submit autonomously or publish
a public package link without an explicit recorded decision from the registered owner. The original
solution-package deadline remains 2026-11-16 23:59 GMT+7; recheck the live portal for changes.

## Constraints

Grounding is not free:

- Preserve input/label isolation: gold labels, reference calls/results and final states are never
  policy inputs during evaluation or inference. A reference transcript is allowed as planner input
  only in explicitly labeled diagnostic runs or training; actual-ASR mode uses the actual transcript.
- Stay within the effective context budget of 16,384 tokens; the full tool catalog competes with the
  conversation for it.
- Re-run the frozen benchmark after each single change, and change one thing per run. Two edits in
  one run cannot be attributed.
- A dataset estimated at about 1,500 rows can overfit rapidly; verify its actual size and measure any
  gain rather than assuming either the count or the outcome.
- Training examples come from non-benchmark IDs in measured failing categories, as specified above.

Schema-constrained decoding is a grounding/compiler-side lever, not post-training:

- It changes decoding, not weights, so it belongs to Phase 4.
- Schema validation stays mandatory even when decoding is constrained; constrained generation must
  not hide semantic errors.

## Gate

No fine-tuning step may start before both:

1. A measured baseline score and model selection exist for the frozen benchmark, from real runs.
2. Available Phase 4 levers have been assessed and benchmarked, unavailable levers explained, and a
   grounding plateau documented, even if no attempted change helped. Missing evidence is not a plateau.

Until both hold, the answer to "should we fine-tune?" is no.
