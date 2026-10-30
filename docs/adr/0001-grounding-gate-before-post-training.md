# 0001: Grounding gate before post-training

**Status:** accepted

## Context

The original prompt explicitly required a measured Phase 3 baseline before post-training and said not
to start with fine-tuning. It did not require a grounding plateau first. Tool selection, dependent
identifiers, clarification and unsupported requests are possible failure categories to measure, not
established dominant failures. An estimated dataset of about 1,500 rows can overfit rapidly, and an
apparent gain can be indistinguishable from run-to-run noise; verify the count and measure outcomes.

## Decision

Order the work measure → ground → post-train, as recorded in [decision-order.md](../decision-order.md).
No fine-tuning starts before two conditions hold: a measured baseline score and model selection exist
for the frozen benchmark from real runs, and a grounding plateau is documented. Assess all available
Phase 4 levers and benchmark each usable lever, retaining a change only for measured improvement
without regression. A documented plateau can exist even if no attempt helps; missing evidence does
not establish one. Post-training then applies only to categories still broken and ships only on a
measured gain beyond two-control-run variance without regression. ASR LoRA follows the same gate and
only when critical-slot failures dominate.

## Consequences

- Measurement and evaluation infrastructure is on the critical path; a baseline is a prerequisite,
  not a nice-to-have.
- Each grounding change is assessed one-change-per-run against the frozen benchmark and is retained
  only for a measured improvement without regression.
- The team may finish without any fine-tuning. That is an acceptable outcome, not an incomplete one.
- Reconsidering this ADR requires evidence, not an assumption that a grounding or post-training lever
  will succeed.
