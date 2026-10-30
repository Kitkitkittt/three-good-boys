# Saved-output training evaluation

A stdlib evaluator is available locally at `baseline/evaluate_training.py`. It freezes a permitted training benchmark and evaluates an existing submission artifact through the real organizer SDK. It does not load an ASR/LLM, generate predictions or claim an official competition score.

Competition code, data, fixtures and reports remain in Git-ignored local paths because the remote repository is public. Transfer these files only through an authorized private channel. The GitHub placeholder `kitkitkittt` identifies this collaborator, not the project owner or competition account holder.

## Freeze input identity

From the repository root:

```bash
python3 baseline/evaluate_training.py freeze --limit 12 \
  --output work/evaluation/benchmark-12.json
```

Omit `--limit` for the full training split, or use `--sample-ids train_0864,...` for an explicit set. Sampling uses seed 0. The manifest preserves ordered IDs plus training JSONL, catalog, SDK source and all selected latest/history audio checksums. Existing manifest files are never overwritten. Keep a fixed manifest for candidate comparisons; changed data/catalog/SDK/audio fails evaluation rather than silently creating a new benchmark.

## Evaluate saved model predictions

Use the complete prediction JSONL for exactly the frozen IDs. Records must have only `id`, `tool_calls` and `state_hash`; hashes must be SDK-derived SHA256 strings from the generating run.

```bash
python3 baseline/evaluate_training.py evaluate \
  --manifest work/evaluation/benchmark-12.json \
  --predictions outputs/train-benchmark/submission.jsonl \
  --mode asr \
  --run-manifest outputs/train-benchmark/run-manifest.json \
  --output-dir work/evaluation/audio-report
```

Modes describe how the supplied predictions were generated:

- `asr`: actual ASR transcripts used by the policy.
- `reference-transcript`: legitimate training reference text supplied to a planner diagnostic, not actual ASR performance.
- `reference-replay`: supplied gold calls replayed for SDK/evaluator verification, never a model benchmark. This mode does not need a model run manifest.

Model modes require a nonempty run-provenance JSON object. Use the generating runner's manifest, recording model revisions, source/runtime/configuration, seed and machine. The evaluator records that object and its own source/input identities. A mode flag is a provenance declaration, not proof that the generating policy excluded labels. The existing runner explicitly excludes labels and provided transcripts from its audio model input; any new diagnostic path must preserve equivalent separation.

Use a new output directory for every evaluation. It writes:

- `report.json`: aggregate local metrics, input/artifact identities and declared run provenance.
- `samples.jsonl`: each sample's actual call log/results, state/hash consistency, score and failure signals. Restricted diagnostic evidence stays local.

## Optional real diagnostics

Pass `--diagnostics <file.jsonl>` with exactly one record per benchmark ID. Supported fields are `id`, `end_to_end_seconds` and `transcript`. Times must be actual finite nonnegative measurements from the generating inference run, including the full sample path; evaluator replay time is not inference latency. Transcripts must be the actual ASR output when mode is `asr`.

The report computes measured count, mean, nearest-rank p50/p95, maximum and samples exceeding 30 seconds. WER uses NFC/lowercase whitespace tokens, preserving punctuation and Vietnamese accents, and is emitted only for `asr` mode with supplied transcripts. Missing measurements stay null, never fabricated as zeros. Critical-slot accuracy, peak memory, token metrics and causal ASR/intent/dependency attribution remain unavailable without appropriate recorded evidence.

## Local scoring choices and safeguards

- Replays each submitted call verbatim through exactly one real training ToolEnv per sample. Rejected actual calls remain in the trace; validation never filters them out.
- Constructs the intended complete state from `env.get_state()` before execution plus every whole changed-app state from the supplied training label. This preserves unchanged apps and cross-app effects, rather than checking only apps named in calls.
- Compares SDK-canonical states through the SDK's sorted JSON serialization. It never reads raw environment files, constructs a second session for the same evaluation sample or synthesizes a submission hash.
- Records whether the supplied hash matches that replay session. A mismatch preserves the diagnostic report and makes the CLI exit nonzero. Replay-based task score and artifact-integrity failure are separate fields.
- Uses exact tool names/non-fuzzy argument keys and values, with bool distinct from numeric arguments. Each catalog-marked fuzzy argument must independently exceed token-F1 0.6.
- **Local approximation:** fuzzy tokens are NFC/lowercase whitespace-split multisets; punctuation and accents remain. Two normalized empty values match. Maximum-cardinality bipartite matching preserves duplicate call instances and avoids greedy undercounting. These tokenization/empty-token/ambiguous-matching choices are not an official executable scorer.
- Preserves the official empty-gold branch: full credit only for an empty submitted call list. Nonempty gold additionally requires the intended canonical replay state and uses sample F1; report mean is on a 0–100 scale. Ungated micro call precision/recall/F1 is reported separately.
- Rejects duplicate IDs/JSON keys, invalid/nonfinite JSON numbers, malformed records, coverage mismatches and changed benchmark identities. It refuses nonempty output directories to protect earlier evidence.
- Failure signals identify hash integrity, schema rejection, final-state difference or call mismatch. They do not guess a root cause. Failed samples remain `unclassified` until investigation supplies causal evidence.

The [SDK/source note](sdk-contract.md) records the official formula and remaining specification gaps. A perfect reference replay is not an accuracy result.

## Exercised evidence

- Frozen seed-0 set of 12 permitted training cases.
- Reference replay artifact: 12/12 local full-credit outcomes, 12 canonical state matches and zero schema errors. This validates the evaluator against supplied references, not a model.
- No-action diagnostic artifact on the same set: two full-credit empty-gold outcomes and four state matches. It demonstrates that state/schema validity alone does not establish task completion.
- Repeated saved-output evaluation produced identical aggregate reports and per-sample evidence.
- Wrong supplied hash preserved diagnostics and exited nonzero. Missing IDs, altered catalog identity, absent model provenance and output overwrite failed explicitly.
- Evaluator regression checks cover strict fuzzy boundaries, Vietnamese Unicode, repeated-token counts, maximum one-to-one matching, exact argument types, state serialization, empty-reference precedence, JSON identity and ASR metric mode separation.
- On `compute-01` (RTX 4060 Ti, CUDA 12.4), fresh paired runs used the same frozen 12 training cases and the isolated private diagnostic documented in `work/paired-training-20261028/INSTRUCTIONS.txt`. Both reference-transcript and actual-ASR planner modes produced one local full-credit case, three matching final states and an approximate local score of 8.33/100; neither is an official score. Re-evaluating each saved output produced byte-identical reports and sample records.
- The same frozen set's no-action diagnostic scored 16.67/100 locally versus 8.33/100 for either live mode; it matched zero calls and is not a viable solution. The two empty-gold cases make this small-set aggregate misleading on its own, so compare call F1 and per-case outcomes as well as score.
- Reference-transcript micro call precision/recall/F1 were 0.250/0.208/0.227; actual-ASR values were 0.188/0.125/0.150. Both had zero executed schema errors or hash mismatches; reference mode had two validation-only rejected proposals, actual-ASR mode had none. These are distinct from executed calls.
- Actual-ASR latest-request WER was 99/267 = 37.08%, with the normalization defined above. End-to-end per-case latency and target-equivalent memory were not measured by the paired diagnostic. Model-generation-only median/maximum were 20.35/70.26 s for reference mode and 23.93/37.77 s for ASR mode on the proxy GPU; they are not end-to-end or A30 results. Private traces and reports remain on `compute-01` under `work/paired-training-20261028/`.
- An independent ASR-only comparison on the same training audio measured `Systran/faster-whisper-large-v3` int8 on CPU at 101/267 = 37.83% local WER, versus Whisper Turbo's 37.08% on GPU. The archived generation command used Vietnamese, beam size 1, no previous-text conditioning and no VAD; its report does not bind the saved transcript bytes, which were hashed separately. Repeating that command on the frozen audio produced byte-identical transcript files and identical per-sample WER results; the private script and comparison are in `work/paired-training-20261028/alternative-asr-frozen-reproduction-20261029/`. Different models, runtimes and hardware mean the reported times are not a hardware-controlled comparison.
- A fresh pinned planner on `compute-01` consumed those 21 cached large-v3 transcripts for the same 12 cases; ASR did not run during planning. Its approximate local score was 14.58/100, call precision/recall/F1 0.250/0.208/0.227, and four final states matched, versus 8.33/100, 0.188/0.125/0.150 and three matches for the Turbo-ASR planner run. Each had one full-credit case, zero executed schema errors and 12 matching session logs/hashes. The manifests matched on benchmark and input identities, SDK, planner source and weights, runtime, system prompt, seed, planner sampling and token/turn/call limits. The adapter requested ASR-mode policy inputs and inference but explicitly overwrote its manifest mode and ASR fields; the ASR models and decoding settings were not matched. Initial simulator state was not fingerprinted. This small, non-hardware-controlled comparison does not establish causal ASR superiority, statistical significance, model eligibility or an official score. The restricted adapter and evidence are at `work/paired-training-20261028/alternate-planner-20261029/`; the completed run and evaluation are on `compute-01` under the same relative path.
- Re-evaluating the cached-alternate planner's saved output on `compute-01` reproduced both aggregate and per-sample reports byte-for-byte. Manifest artifact hashes matched, and validation recorded 12 unique samples with 12 session-log/hash checks; this repeats evaluation, not ASR or planner inference. The second report is `work/paired-training-20261028/alternate-planner-20261029/evaluation-02/` on `compute-01`.
- On 25 manually selected critical reference spans in the same 12 training cases, exact transcript-span recall was 7/25 for Turbo and 8/25 for large-v3; all selected spans matched in 1/12 and 2/12 cases respectively. This is a single-reviewer, incomplete annotation: five cases have unresolved fields, and reference spans were not independently checked against audio. Exact contiguous NFC/lowercase whitespace-token matching retains punctuation and accents; it is not semantic slot accuracy or downstream success. The analysis and restricted annotations are under `work/paired-training-20261028/critical-slots-20261029/`; rerunning the analyzer reproduced its saved results byte-for-byte.
- A private manual review attributed the 11 reference-transcript local-score failures to primary categories: tool choice 2, argument value 3, dependency 3, unnecessary call 1 and clarification 2. These are analyst judgments from the recorded training references and traces, not mutually exclusive causal proof or actual-ASR attribution. Restricted per-case evidence is in `work/paired-training-20261028/reference-triage-20261029/triage.json`.
- The same manual process attributed the 11 actual-ASR failures to ASR 3, intent 1, tool choice 3, argument value 2 and dependency 2. These are uncertain single-primary judgments, not mutually exclusive causes; the saved traces do not expose separately transcribed historical audio. Restricted evidence is under `work/paired-training-20261028/asr-triage-20261029/`.
- A fresh ASR-mode run on the same 12 cases measured the full individual path on the RTX 4060 Ti: mean 25.68 s, nearest-rank p50 24.56 s, p95/max 37.86 s, with 3/12 over 30 s. The per-case timer includes fresh ASR and planner loads, all latest/history audio, the real simulator and per-case export; it excludes shared preflight, planner teardown, checkpoint close and aggregate writes. OS/process/CUDA caches may be warm. It is neither official timing nor A30-equivalent evidence. The runner's recorded model/runtime/settings identities match the prior ASR diagnostic; transcript text matched case by case and submission bytes matched, with the same 8.33/100 local score. Its 12 saved traces contain 1,388 generated tokens and 314,597 prompt tokens summed across turns, not unique-context tokens. Per-case peak GPU memory was not measured in this run. Restricted artifacts and timings are on `compute-01` in `work/full-path-latency-20261029/run-02/`, with evaluator report `report-02/`.
- A second fresh, independently instrumented run on the same 12 cases recorded PyTorch GPU allocator peaks per case: allocated 10,648–11,001 MiB and reserved 11,488–12,524 MiB on the RTX 4060 Ti. Synchronization and peak reset occurred before each timed case; peaks include both sequential model stages and the allocator baseline, but not non-PyTorch or device-wide allocations. Mean/p50/p95/max elapsed were 25.90/23.90/37.76/37.76 s, with 3/12 above 30 s. Token totals and output bytes matched the first timed run; the evaluator again reported 8.33/100 locally. Timing boundaries are as above, with CUDA peak sampling included; these are not official or A30 measurements. Restricted artifacts: `compute-01` `work/full-path-latency-20261029/v2-run-01/` and `v2-report-01/`.
- The private v2 profiling runner is `work/full-path-latency-20261029/full_path_latency_v2.py`, SHA-256 `2517fe0f9881e51a6908ea2fc2f927155e761ae9d5df1f16e40fafcdc3c5ba97`. On `compute-01`, with `$ROOT=/home/compute_01/.local/share/lifemate-20261028.nqCvPJ4O`, it was run as `"$ROOT/.venv/bin/python" "$ROOT/work/full-path-latency-20261029/full_path_latency_v2.py" --diagnostic-dir "$ROOT/work/paired-training-20261028/baseline" --benchmark "$ROOT/work/evaluation/benchmark-12-v2.json" --data-root "$ROOT/work/data/train+public_test" --models-root "$ROOT/work/models" --output-dir "$ROOT/work/full-path-latency-20261029/v2-run-01"`; use a new output directory for another run. A separate synthetic CPU-only smoke exercised an incomplete first case followed by complete cases: timings survived and no aggregate submission was exported. This is control-flow verification, not model-performance evidence.
- A preliminary `run-01` profiler mistakenly opened raw simulator-state files to hash them, contrary to the SDK-only state-access rule. It was stopped and is invalid; its results were not used. The invalid digest-bearing manifests and checkpoint were removed, leaving a private invalid-attempt note. `run-02` used the corrected wrapper, which leaves state access to the official ToolEnv. Do not reuse `run-01` artifacts.

Ticket 02 remains in progress: paired artifacts, proxy per-case timings and PyTorch memory, exploratory failure triage and critical-span analysis exist, but complete semantic critical-slot outcomes, independently established failure categorization and target-equivalent measurements remain incomplete. No synthetic diagnostics are presented as observed model performance.

Run the existing and new regression checks without model dependencies:

```bash
python3 -m unittest discover -s baseline -p 'test_*.py' -v
```
