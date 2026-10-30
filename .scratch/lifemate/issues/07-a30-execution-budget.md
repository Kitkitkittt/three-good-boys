# 07: Meet the A30 execution budget

**Parent spec:** [LifeMate competition solution](https://github.com/huyxdang/three-good-boys/issues/1)

**What to build:** The selected Linux/NVIDIA audio-to-action solution has measured target-equivalent latency and memory behavior and meets the organizer's per-sample execution limit without hiding task-quality regressions.

**Blocked by:** [03: Linux/NVIDIA pipeline](03-linux-nvidia-pipeline.md); [04: Grounded agent behavior](04-grounded-agent-behavior.md); [05: Compliant model selection](05-compliant-model-selection.md).

**Status:** ready-for-agent

**Owner:** Unclaimed

**Progress:** not-started

## Implementation steps

1. Re-check organizer hardware, per-sample cap and timing boundaries; record source and check date here and note differences from the historical A30/30 s summary.
2. Collect coarse full-path timing as soon as the ported baseline runs, without waiting for final model selection. Once tickets 04/05 settle, profile the selected configuration on representative cases: audio handling, ASR, prompt preparation, generation, validation, simulator calls and output. This preparation does not bypass final ticket blockers.
3. Run that profile over the fixed evaluation set, capturing count, mean, p50, p95, max, timeouts, peak VRAM/RAM, runtime/config and cold start under the official timing convention.
4. Change only measured bottlenecks, one at a time; re-run the fixed quality baseline (ticket 02) after every retained change and revert material regressions or nondeterminism.
5. Re-profile the full set on target-equivalent hardware until every sample is within the cap, then record the reproducible invocation and final performance config for tickets 08/09.
6. Until tickets 03, 04 and 05 and target access are ready, keep work at preparation (small-sample profiling, harness, proxy measurements labeled as proxy); closure still waits for full target-equivalent evidence.

## Acceptance criteria

- [ ] Confirm current hardware, timing boundaries and caps from organizer requirements. The rendered official Rule section on 2026-10-28 confirms one A30, 16-core Xeon Gold 6442Y, 64 GB RAM and 30 seconds per sample; recheck before certification and resolve the exact timing boundary/model-load treatment.
- [ ] Profile the selected full audio path on representative permitted training cases and the full fixed evaluation set. Include audio handling, ASR, prompt preparation, generation, schema validation, simulator calls and output work; disclose cold start/model loading under the official timing convention.
- [ ] Report count, mean, p50, p95, maximum, timeouts, peak VRAM/RAM and hardware/runtime/configuration. A Mac elapsed time, CPU smoke, proxy GPU or generation-only measurement is not A30 certification; state the limit of proxy evidence.
- [ ] Optimize only measured bottlenecks with the smallest justified change. Test prompt simplification, caching, quantization or bounded repair only when profiling and model support justify them; speculative decoding is not mandatory.
- [ ] Compare against the fixed quality baseline after each retained optimization. Preserve complete execution logs, final hashes and all required clarification/dependency behavior; investigate material score loss or nondeterminism before retaining the change.
- [ ] Demonstrate every measured sample within the confirmed limit and resource caps on target-equivalent hardware. A hardware or organizer-access blocker must identify exactly what remains unmeasured; do not mark latency certified from an estimate.
- [ ] Record a reproducible target invocation and the final selected performance configuration for containerization and freeze.

## Verification

No implementation verification yet. Completion requires actual end-to-end target-equivalent timing evidence, memory observations, fixed benchmark comparison, and the exact runtime configuration.

## Comments

A per-sample cap is not satisfied by a good average. Do not add arbitrary retries or cut off required actions merely to report a faster runtime.

2026-10-28 source check: the [SDK source note](../../../docs/sdk-contract.md) records the live portal's hardware/cap, determinism and tie-break requirements. This is source verification only; no target inference timing was performed.
