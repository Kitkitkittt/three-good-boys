# 00: Grounding gate before post-training, and one ordered decision path

**Parent spec:** [LifeMate competition solution](https://github.com/huyxdang/three-good-boys/issues/1)

**What to build:** A single public decision runbook that orders the remaining work — measure → ground → post-train — with an explicit gate before any fine-tuning. Grounding (ticket 04) addresses measured failures before LoRA SFT, which is entered only for categories that measurements still show broken after grounding plateaus.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

**Owner:** claude-implementer

**Progress:** done

## Implementation steps

1. Create `docs/decision-order.md`: the consolidated decision order table (step, change, evidence required to proceed) and the corrected Phase 3–5 sequence with grounding as Phase 4 and post-training as Phase 5. State that no fine-tuning starts before a measured baseline and a grounding plateau exist.
2. Record the grounding levers in cost order: schema/grammar-constrained decoding for tool calls (compiler-side, no weight change), prompt/system-prompt corrections, lookup broadening plus dependency/ordering rules, clarification/unsupported-request policy. One change per benchmark run.
3. Record the constraints: input/label isolation, context ≤ 16,384, frozen benchmark after each single change, training on measured failing categories from non-benchmark IDs, and schema-constrained decoding as grounding rather than post-training.
4. Record the post-training entry and rejection criteria: score gain must exceed normal run-to-run noise with no regression; ASR LoRA only when critical-slot failures dominate.
5. Add ADRs under `docs/adr/` for (a) grounding gate before post-training, (b) schema-constrained decoding as a grounding lever with validation still mandatory.
6. Link the runbook from `README.md` and `context/README.md`, and point tickets 04, 05 and 09 at it as the ordering authority. Do not restate the table in more than one place.

## Acceptance criteria

- [x] One public runbook states the ordered path measure → ground → post-train and the evidence required to advance each step.
- [x] Every fine-tuning step is gated behind a measured baseline and a grounding plateau; the prompt-side ordering is explicit.
- [x] Grounding levers are listed in cost order with schema-constrained decoding included as a grounding lever, not a post-training step.
- [x] The input/label isolation invariant, the context budget, and the frozen-benchmark-per-change rule are stated as constraints on grounding.
- [x] Post-training entry/rejection criteria and the ASR-LoRA condition are recorded.
- [x] No ticket or document describes fine-tuning as an early or first step.

## Verification

Created: `docs/decision-order.md`; `docs/adr/0001-grounding-gate-before-post-training.md`; `docs/adr/0002-schema-constrained-decoding-as-grounding-lever.md`. Linked from `README.md` and `context/README.md`; tickets 04, 05 and 09 each carry one ordering-authority line under Comments.

Checks run on branch `ticket/01-grounding-runbook` (worktree `.worktrees/01-grounding-runbook`):

- `rg -o '\(docs/[^)]+\)' README.md` → `docs/working-baseline.md`, `docs/sdk-contract.md`, `docs/training-evaluation.md`, `docs/decision-order.md`; all four paths exist (`ls`).
- `rg -o '\(\.\./docs/[^)]+\)' context/README.md` → all targets exist.
- `rg -o '\(\.\./\.\./\.\./docs/[^)]+\)' .scratch/lifemate/issues/*.md` → `../../../docs/decision-order.md` exists.
- `rg -c 'run-to-run variance' docs .scratch` → one hit only, in `docs/decision-order.md` (the table's wording). No ticket restates the table.

Correction: the original prompt already required a measured Phase 3 baseline and explicitly deferred
fine-tuning; it did not require a grounding plateau. This review restored its detailed post-training
requirements, corrected unsupported outcome claims, and made ticket 05 a blocker of ticket 04. The
checks above predate that correction; they are not evidence of a live model benchmark.

## Comments

Origin: review of the planning handoff's Phase 3–5 sequencing. The handoff already requires a measured baseline and says not to begin with fine-tuning; this decision adds a grounding-plateau gate. Tickets 04, 05 and 09 use the runbook as ordering authority.
