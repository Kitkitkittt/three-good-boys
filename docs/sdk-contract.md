# Observed LifeMate SDK contract

Inspected and exercised the supplied organizer release v3.2.0, built 2026-10-24T23:35:25+0700, and checked the rendered official portal's Evaluation, Rule and Submission Guidance sections on 2026-10-28. Private source paths below are relative to the extracted `work/data/train+public_test/` root unless stated otherwise. Do not publish the organizer source or data with this note.

## Inputs and catalogs

| Split | Samples / unique IDs | Catalog apps, including sys | Tools | Catalog schema | Labels / reference transcripts |
| --- | --- | --- | --- | --- | --- |
| train | 1,545 / 1,545 | 46 | 147 | 2.7.0 | Present on all rows |
| public_test | 634 / 634 | 36 | 122 | 2.7.0 | Absent on all rows |

Observed by enumerating split JSONL rows and catalogs, without inspecting raw environment files. These two catalogs differ; do not hard-code their counts or reuse one split's package for another.

- The technical README sections 2.1–2.2 define each row's `id`, `audio`, `context`, and `history`. Context includes current time/timezone, location, profile and installed apps/tools.
- The latest request's audio is the task. History user turns may also have audio; earlier assistant actions are already reflected in initial simulator state. Do not execute history calls again.
- Training additionally supplies `audio_text` and `label` with reference calls/results and changed-app final states. Keep those separate from model input. An oracle-transcript diagnostic is legitimate only when explicitly identified, not presented as actual ASR performance.
- Tool parameters use JSON schemas with `required`, type/enum/range/format constraints, `x-one-of`, `x-ref`, and `x-match`. Inspect the actual split catalog; a generic validator alone may not implement organizer extensions.

## Official environment lifecycle

Primary sources: `<split>/zaic_tools/__init__.py` (`ToolEnv`, `catalog_path`), `executor.py` (`Simulator`, `Session`), and technical README section 3.

1. Import `zaic_tools` from the intended split's package. Set the data root to the directory containing the split directories, not to the split itself.
2. Create one ToolEnv for a sample. Only the official package loads its private environment file; application code must not open or parse that file.
3. Use `env.validate(name, arguments)` for a schema-only check. It returns an ok/error result and changes neither calls nor state.
4. Use `env.call(name, arguments)` to execute. Read the actual result before binding dependent arguments. Every call that reaches this interface is logged, including rejected calls.
5. Export `env.get_tool_calls()` in actual execution order and `env.get_state_hash()` from the same session. Do not recreate a session to discard failed attempts or synthesize a replacement hash.

The SDK adds `sys.ask_missing_info` to allowed tools. Calls outside the sample's installed tools, unknown catalog names, missing required/grouped arguments or invalid values are rejected. Schema-valid but semantically unsuccessful actions may instead return ok with a false done flag or an empty result; ok alone does not prove request fulfillment.

A rejected call remains in the call log but does not change application state. The call log itself is not hashed. Therefore, do not infer that merely logging a rejected call changes the state hash. `env.validate` also does not check every possible simulator/runtime condition; an actual call can still fail after a validation pass.

`env.get_state()` is the official debug/training comparison interface. The SDK docstring explicitly permits comparing its changed app states with supplied training `label.final_state`. This does not authorize direct raw-file inspection or using labels as policy observations.

## Clarification and unsupported requests

The catalog has one system tool, `sys.ask_missing_info`. Its required arguments are `tool_name` (string) and `params` (array of strings). The descriptions require an intended tool and the exact names of missing required parameters from its schema. The SDK checks argument shapes, not whether the named target/parameters are a sensible clarification; policy quality must be evaluated separately.

The existing runner already supports this call and stops after executing it. Improvements should address premature or incorrect clarification using permitted training evidence, not invent a missing system capability or a new unsupported-request tool.

No separate unsupported system tool is shipped. The technical README describes an out-of-scope output example; the baseline finishes with no calls for unsupported or cancelled requests. Keep independent-action/partial-fulfillment decisions tied to authoritative requirements and training cases rather than a new hard-coded global rule.

## Hash semantics

Primary source: `<split>/zaic_tools/utils.py`, `canon` and `state_hash`.

The official hash canonicalizes current application state, removes metadata, specified live-information apps and designated free-text keys recursively, normalizes scalar strings, sorts lists containing only scalar values, and preserves dictionary-list order. It then hashes sorted compact ASCII JSON. Free-text argument matching is separate from state canonicalization.

The integration helper obtains the final value only through `env.get_state_hash()`. It does not reimplement this algorithm or infer a reference hash from partial changed-app labels.

## Validation is not scoring

Primary sources: `<split>/zaic_tools/validate.py` and `__main__.py`.

- `schema_validate` returns per-call ok/error results against the catalog and allowed set. It does not score intent, compare final hashes against gold, or compute precision/recall/F1.
- The organizer CLI's validate mode schema-checks provided calls and reports the number of lines/errors. It does not guarantee complete input coverage, validate all result fields, or establish correct task execution. Its summary must be inspected because errors do not reliably produce a nonzero exit status.
- No official task-scoring evaluator was found in the supplied archive/technical README. The archive has tool runtime helpers, including a public app search matcher, not a competition F1 evaluator. The portal supplies the specification below, not an executable local scorer. Name a locally implemented metric as local and document unresolved tokenization/matching details.
- The SDK's free-text search normalization is not proof of evaluator tokenization. Use the portal's scoring specification rather than copying the app search matcher into an alleged official evaluator.

## Official scoring and release requirements, checked 2026-10-28

Source: [official LifeMate portal](https://challenge.zalo.ai/portal/lifemate), rendered Evaluation, Rule and Submission Guidance sections. Local snapshots are under `work/official-portal/2026-10-28/`; the formula image was also visually inspected. These sections are dynamic and were not visible in a static HTML read.

- A call matches only with the same tool name, identical non-fuzzy arguments, and token-F1 strictly greater than 0.6 for each fuzzy argument after lowercasing and Unicode NFC. Matching is one-to-one and ignores call order; replay still executes calls in order.
- For an empty gold call list, sample score is 1 only if the submitted list is also empty, otherwise 0. This explicit branch must not be replaced by a blanket hash-gate rule.
- For nonempty gold calls, score is 0 if hashes differ or no calls match; otherwise it is harmonic precision/recall F1. With M matched calls, U unmatched submitted calls (including rejected calls), and G gold calls: P = M/(M+U), R = M/|G|, and sample score = 2M/(M+U+|G|). Final score is 100 times mean sample score.
- Missing-information calls are scored like other tools. Organizer replay with the matching SDK is authoritative if submitted hashes/results disagree. Ties use call F1 without the hash check, then lower average processing time.
- All learned models combined must be below 6B parameters; the LLM must be below 5B; effective context is at most 16,384 tokens. Eligible public data/open models must be released before October 26, 2026 and appropriately licensed. External synthetic-data services may be used during development, not inference; labeling public/private tests for training/tuning is prohibited.
- Offline runtime: one NVIDIA A30, 16-core Xeon Gold 6442Y and 64 GB RAM; each sample within 30 seconds. Fix random seeds and deterministic ASR/LLM decoding. If reproduced results differ, organizers may run the image five times and use mean score.
- Docker receives the private folder, structured like public_test, at `/data`; the inference script must write `result/submission.jsonl`, fully offline. Detailed packaging/launch guidelines remain separate; do not invent the exact entrypoint or CUDA image contract.
- On 2026-10-29 the rendered Rule and Submission Guidance sections still stated the same mount/output, A30/30-second limits and separate Docker guidelines. The Rule explicitly prohibits reading, copying or parsing any file under `<split>_environment/`; only `zaic_tools` may access app data, with exactly one ToolEnv per sample and every actual call exported. Neither rendered section linked the separate Docker guide.
- Public submissions: at most five per day. Solution package: November 16, 2026, 23:59 GMT+7; up to two submissions, last evaluated. Private release: November 20 at 09:00; result deadline November 23 at 23:59 GMT+7. Recheck before acting because organizers may change instructions.
- Submission Guidance explicitly requests a checksum and public Google Drive package link, while the handoff restricts general public distribution. Do not publish a package link in this repository: a registered team member must resolve approved sharing/access with the organizer and record the decision before uploading.

## Observed reference replay

Command from the repository root: `python3 scripts/sdk_smoke.py`.

For `train_0864`, one real official environment executed the two supplied reference calls. Actual ordered calls matched the reference; schema errors and rejected calls were zero; every labeled changed-app state matched `env.get_state()`; final hash was retrieved from that session. A separate organizer CLI schema check reported one line and zero errors. Evidence is in `work/sdk-smoke/train_0864/` and remains local/restricted.

This replay uses supplied reference calls deliberately. It proves SDK loading/execution/export, not ASR, planning accuracy, target-machine timing or a competition score. A second replay requires a fresh evidence directory; the helper refuses to overwrite a previous run.

## Unresolved external requirements

- No executable official scorer in the bundle; exact fuzzy tokenization and ambiguous one-to-one matching behavior are not specified in the visible portal prose. Record local choices explicitly or obtain organizer clarification.
- The precise timing boundary (for example model-load treatment) still needs confirmation despite the verified 30-second cap and hardware.
- Detailed Docker entrypoint/base image/model packaging guidance is still separate. The input/output mount convention is now verified from the portal, not a proposal.
- Team target-GPU access and legal redistribution/private sharing of selected model/dependency artifacts.

See the [working runbook](working-baseline.md) and [local execution plan](../.scratch/lifemate/README.md). These gaps do not block SDK replay, baseline code inspection or permitted-training evaluation preparation.
