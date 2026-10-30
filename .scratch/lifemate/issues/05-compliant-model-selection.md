# 05: Select compliant ASR and language models

**Parent spec:** [LifeMate competition solution](https://github.com/huyxdang/three-good-boys/issues/1)

**What to build:** The team can select and reproduce an ASR/language-model pair from measured training outcomes and a documented eligibility/resource inventory, rather than committing to an unbenchmarked recommendation.

**Blocked by:** [02: Labeled-training evaluation](02-labeled-training-evaluation.md); [03: Linux/NVIDIA pipeline](03-linux-nvidia-pipeline.md).

**Status:** ready-for-agent

**Owner:** Unclaimed

**Progress:** not-started

## Implementation steps

1. Inventory locally available candidate ASR and language models with exact revisions; record the Spark reference from the handoff as excluded unless its identity and eligibility can be evidenced.
2. Check each candidate's release eligibility, license, redistribution terms, parameter count (all learned parameters) and effective context against primary docs and current organizer caps; record the source for each figure.
3. Run the ticket 02 ASR A/B on identical permitted Vietnamese training audio and frozen benchmark cases, reporting critical-slot outcomes, WER where references exist, downstream outcomes, latency and peak memory; keep ASR and planner comparisons separable.
4. Run every language-model candidate on the same fixed multi-case training benchmark using legitimate reference transcripts, identical available tools and the same evaluator. Record invalid calls, outcomes and tokens; a single successful replay is a smoke check, not sufficient evidence for model selection.
5. Choose the primary pair on measured outcomes and document the tradeoff and exclusions. On the same frozen benchmark, run and report the selected baseline pair in separately labeled reference-transcript and actual-ASR modes using ticket 02's paired evaluation. Run the selected pair through the ticket 03 Linux/NVIDIA path and save artifact checksums and reproduction instructions for the release owner.

## Acceptance criteria

- [ ] Establish a small candidate matrix using the existing baseline and eligible alternatives. Include the handoff's Qwen-versus-Spark comparison only if the actual candidate is identifiable, available and permitted; record an exclusion with evidence rather than inventing its model identity or eligibility.
- [ ] Verify each model's exact revision, release eligibility, license and redistribution terms against current organizer rules and primary model documentation. Do not assume a quantized derivative inherits an earlier release date or that quantization reduces parameter count.
- [ ] Count all deployed learned parameters, including ASR and auxiliary models; verify the current total-model, LLM-only and effective-context caps. The handoff reports less than 6B total, less than 5B LLM and at most 16,384 context tokens; confirm before treating those as final eligibility checks.
- [ ] Compare ASR with the same permitted Vietnamese training audio and frozen benchmark cases using critical-slot outcomes, WER where legitimate references exist, downstream task outcomes, latency and memory. Compare language models on the same reference transcripts, tools, runtime settings and evaluator.
- [ ] Record the fixed sample set, revisions, decoding/context configuration, quantization, hardware, runtime versions, task metrics, invalid calls, end-to-end latency and peak memory. Keep ASR and planner comparisons separable.
- [ ] Select a primary pair using measured competition outcomes within constraints; explain the quality/latency tradeoff and excluded candidates. For the selected baseline pair, report paired reference-transcript and actual-ASR runs on the same frozen benchmark as separate, explicitly labeled results. Do not invent a required percentage improvement or promote a model from marketing claims.
- [ ] Run the selected pair through a real Linux/NVIDIA training audio-to-submission sample. Save local artifact checksums and reproduction instructions, with licenses and access restrictions available to the release owner.

## Verification

No implementation verification yet. Completion evidence includes candidate reports, source-backed eligibility/parameter inventory, selected revisions, ASR A/B and paired baseline results on the same frozen cases, and an actual selected-pair run.

## Comments

Model choice stays reversible until this evidence exists. Do not use external inference services or manually labeled public/private test samples to choose a model.

Ordering authority: [decision-order.md](../../../docs/decision-order.md) (measure → ground → post-train); do not restate its table here.

2026-10-29 prerequisite research (selection remains blocked and unclaimed): the [Qwen3-4B-Instruct-2507 pinned registry](https://huggingface.co/api/models/Qwen/Qwen3-4B-Instruct-2507/revision/cdbee75f17c01a7cc42f958dc650907174af0554) reports 4,022,468,096 BF16 stored parameters and Apache-2.0; the [Whisper Turbo pinned registry](https://huggingface.co/api/models/openai/whisper-large-v3-turbo/revision/41f01f3fe87f28c78e2fbf8b568835947dd65ed9) reports 808,878,080 FP16 stored parameters and MIT. These are stored-tensor counts, not a completed inventory of all deployed learned parameters. Verify tied tensors and auxiliary models before assessing compliance. Both repositories were created before the recorded cutoff; repository creation alone does not establish each pinned revision's release eligibility. The CUDA candidate imposes a 16,384-token budget, while [Qwen's native config](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/raw/cdbee75f17c01a7cc42f958dc650907174af0554/config.json) declares 262,144 positions. Check current rules and licenses before selection or redistribution.

[SmolLM3-3B](https://huggingface.co/HuggingFaceTB/SmolLM3-3B/tree/a07cc9a04f16550a088caea529712d1d335b0ac1) is an unmeasured alternative, not a selected model: its [pinned registry](https://huggingface.co/api/models/HuggingFaceTB/SmolLM3-3B/revision/a07cc9a04f16550a088caea529712d1d335b0ac1) reports 3,075,098,624 BF16 stored parameters and Apache-2.0, while its [config](https://huggingface.co/HuggingFaceTB/SmolLM3-3B/raw/a07cc9a04f16550a088caea529712d1d335b0ac1/config.json) ties embeddings and declares 65,536 positions. Its model card documents tool calling and requires Transformers 4.53.0 or later. The `compute-01` candidate environment uses 4.52.3 and did not recognize `smollm3` in `CONFIG_MAPPING`; no SmolLM weights or same-input performance were verified. The local default Hugging Face cache contains only faster-whisper-large-v3. An eligible exact revision, supported isolated runtime, Vietnamese task behavior and full license/parameter inventory still require verification; do not alter the pinned candidate environment merely to make this alternative load.

2026-10-29 prerequisite comparison: the frozen 12-case ASR WER, exploratory critical spans and cached-alternate-transcript planner outcomes are recorded in [the evaluation runbook](../../../docs/training-evaluation.md). Alternate ASR was reproduced on the frozen audio with byte-identical transcripts, but this remains preliminary evidence, not a completed or claimed model selection: initial simulator states were not fingerprinted, alternate ASR ran on different hardware/runtime, and critical-slot coverage, candidate eligibility and target-equivalent latency/memory remain incomplete. Tickets 02 and 03 remain blockers.
