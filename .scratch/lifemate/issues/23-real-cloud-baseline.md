# 23: Real cloud baseline and dashboard evidence

**Parent spec:** [Shared Google Cloud platform #3](https://github.com/huyxdang/three-good-boys/issues/3).

**What to build:** The existing frozen 12-case diagnostic executed through the real cloud path in both reference-transcript and ASR modes, observed and compared in the dashboard.

**Blocked by:** [21](21-approved-deployment-slice.md), [22](22-failure-injection-and-recovery.md), approved artifact provisioning and GPU allocation, and [02](02-labeled-training-evaluation.md)/[03](03-linux-nvidia-pipeline.md) acceptance satisfied or explicitly revised.

**Status:** ready-for-human

**Owner:** Unclaimed

**Progress:** blocked

## Implementation steps

1. Provision only the approved permitted inputs using the approved mechanism; no bulk organizer upload.
2. Run the frozen `benchmark-12-v2` set in both modes with fixed configurations.
3. Publish through the dashboard: manifests, per-case outcomes, local-score caveats, ASR/critical-slot results, timings and VRAM, and the billed-resource report.
4. Scale to a predeclared larger permitted training set before generalising.

## Acceptance criteria

- [ ] Both modes run on identical frozen cases and configurations with distinguishable manifests.
- [ ] The dashboard shows per-case outcomes, latency distribution and VRAM, with the local-approximation label visible.
- [ ] No label, reference call/result or held-out material is exposed to the agent or through the dashboard.
- [ ] Results carry provenance, benchmark identity and observed resource cost.
- [ ] Any result that is proxy-hardware or synthetic is labelled as such.

## Verification

No implementation verification yet. This ticket does not certify A30 timing or competition accuracy.
