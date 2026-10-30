# 19: Batch worker adapter

**Parent spec:** [Shared Google Cloud platform #3](https://github.com/huyxdang/three-good-boys/issues/3).

**What to build:** A thin Batch entrypoint that turns approved artifacts into the existing inference/evaluation path, commits only validated completed results and never imports cloud libraries into offline inference.

**Blocked by:** None for adapter code. Real execution needs [03](03-linux-nvidia-pipeline.md), permitted artifact provisioning and GPU/spend approval.

**Status:** ready-for-agent

**Owner:** omp-impl-worker

**Progress:** blocked

## Implementation steps

1. Read the run manifest, verify input/model identities, and invoke the existing runner and evaluator through their current seams rather than reimplementing ASR, planning or scoring.
2. Commit each completed sample conditionally and fail closed on a sample that may already have started.
3. Keep the offline image independent of cloud clients and telemetry.

## Acceptance criteria

- [ ] Adapter fails closed on every identity mismatch, incomplete coverage or conflicting output. Coverage/output and resume checks are exercised; materialized dataset identity and checksum-name binding still need the audit gaps below fixed.
- [x] No cloud or network requirement leaks into the inference path.
- [ ] Timing is recorded correctly for cold load, ASR, planning/execution and total across multiple samples; cold-load aggregation remains an audited gap.
- [x] Real execution remains explicitly blocked until ticket 03 and the GPU/data approvals are satisfied.

## Verification

`cd /home/dev-01/Projects/ZaloChallenge/three-good-boys/.worktrees/ticket-19-cloud-worker && python3 -m unittest discover -s workers -p 'test_*.py' -v` → `Ran 30 tests in 0.142s` / `OK` (22 original plus 8 new: launcher missing, incomplete, flag-absent refusal; CLI end-to-end over a synthetic manifest plus a synthetic launcher module written to a tmp dir; restart without `--accept-restart`; restart with the marker attempt; restart with a distinct attempt recording superseded markers).

Real CLI invocation against a temp directory (synthetic manifest `{"ids": ["a","b"], ...}`, synthetic `pinned.json`, synthetic `launcher.py` defining the five seams), `python3 -m workers.gpu_eval.main <manifest> --pinned <pinned.json> [flags]`:

```
no --launcher                                    exit 2  error: the following arguments are required: --launcher
--launcher L --run-id run-1                      exit 0  outcome=complete attempt=complete-0 ids=['a','b'] results/manifest.json=True
markers present, no --resume                     exit 1  fails closed; reuse may adopt committed samples only; interrupted samples require explicit restart
--resume restart --accept-restart --attempt 0    exit 1  worker: AmbiguousExecution: attempt '0' (failed-0) already started sample(s) ['a', 'b']; restart needs a new attempt label, e.g. --resume restart --accept-restart --attempt 0-1
--resume restart --accept-restart --attempt 1    exit 0  outcome=complete attempt=restart-1 superseded_markers=['a','b']
--resume reuse                                   exit 0  adopts byte-identical committed artifacts, executes nothing
```

- Adapter source is `workers/gpu_eval/main.py` (entrypoint, check-in, sample loop, conditional commit, recovery markers, timing) and `workers/gpu_eval/manifest.py` (run-manifest check-in, including the runner's `manifest_for(...)` identity shape). Both import the standard library only; `test_adapter_imports_no_cloud_or_network_sdk` imports the module in a fresh interpreter and asserts no `google`/`requests`/`urllib3`/`httpx`/`pandas` module is loaded.
- Effects are injected callables, so the adapter is exercised on synthetic manifests with no network, GPU or restricted data: `read_identities`, `fetch`, `read`, `execute` and `commit` seams are supplied by the launcher; `execute` receives one `Sample` and returns `(submission_row, stages)` for the existing inference/evaluation path (ASR, planner, ToolEnv and scoring are not reimplemented here).
- Commit follows the shared artifact contract from [ticket 15](15-cloud-run-contracts-and-domain.md): create-only conditional commit, identical content reused, differing content raises `ConflictError`, and the final manifest is the generation-pinned `{run_id, required, entries:[{name, generation, checksum}]}` shape with coverage `{expected, committed, unique}`.
- A result is committable only when it is this sample's own complete session: `check_result` requires `id` match, `stop_reason ∈ {model_finished, asked_missing_info}` and a 64-hex `state_hash` with a list of `tool_calls`.
- Recovery prerequisite honoured: a start marker is written before a sample can execute. A sample with a marker and no committed artifact fails closed even under `--resume reuse`; only `--resume restart --accept-restart --attempt <new>` authorizes a distinct attempt. `run.json` preserves failed attempts and errors. A partial run never leaves `results/manifest.json`; a reuse-completed run conditionally commits that generation-pinned manifest before reporting completion.
- Entrypoint: `main()` requires `--launcher <path.py>`, dynamically imports it and refuses (exit 2, clear message, no marker or network call) when the module or any of `read_identities`/`fetch`/`read`/`execute`/`commit` is missing. The launcher is operator-supplied; no ASR, planning or scoring is implemented here. `Adapter` stays injectable for tests.
- Fail-closed recovery: a sample with markers and no committed artifact is never executed automatically. `--resume reuse` adopts only byte-identical committed artifacts; `--resume restart` is refused unless `--accept-restart` is given and the attempt label differs from the marker attempt, and `run.json` records `superseded_markers`.
- Timing is recorded per sample and per run for `cold_load`, `asr`, `planning_execution` and `total`.
- `baseline/` was not modified. No new dependencies.

Tests: `workers/gpu_eval/test_adapter.py` (22 tests) covering manifest rejection (unknown fields, path escape, duplicate ids, missing/short checksums, changed bytes, runner shape), identity mismatch/checksum mismatch before any fetch or execution, smoke-artifact refusal, conditional-commit reuse/conflict/wrong-id, incomplete coverage, one-shot mid-loop failure with fail-closed evidence, start-marker ambiguity, explicit restart, per-stage timing, and that the committed manifest parses as a complete ticket-15 `ResultManifest` while the adapter still imports when `services/` is absent.

## Comments

The adapter is the offline/cloud-independent half of the plan's worker slice (`docs/google-cloud-implementation-plan.md` §4, "Worker and checkpoint contract"). Real execution still requires ticket 03's Linux/NVIDIA runtime gate plus permitted artifact provisioning and GPU/spend approval; nothing here claims a model run, cloud deployment or recovery of an interrupted ToolEnv. The shared artifact/manifest contract is provided by ticket 15 (`services/lifemate_cloud/artifacts.py`, `manifest.py`); a real GCS adapter and dispatcher binding remain in tickets 16-18.

Review findings fixed (ticket reopened after the first merge): (1) `main()` called `run(args)` with no seams while `Adapter.__init__` requires them, so every real invocation raised `TypeError` — the entrypoint now loads an operator-supplied `--launcher <path.py>` module whose five required callables are explicit and validated, exiting 2 with a clear error when absent or incomplete; (2) `--resume restart` silently re-executed marked, uncommitted samples — restart is now an explicit new attempt requiring `--accept-restart` and an attempt label distinct from the marker attempt (else exit 1 with command guidance), recording `superseded_markers` in `run.json`, and no flag combination executes such a sample automatically. The launcher (real inference, ASR, planning, scoring) is operator-supplied and not implemented here.

Integration review corrections (2026-10-30): reuse no longer re-executes a marked, uncommitted sample. `test_reuse_refuses_a_marked_sample_without_a_committed_artifact` asserts the exact restart remediation and zero execution; the mid-loop regression now requires a new explicit restart. `test_reuse_completion_publishes_the_manifest_without_a_second_execution` proves a fully committed run with a missing final manifest conditionally publishes it with pinned generations and complete coverage, without executing any sample again. This is completed-boundary artifact reuse, not arbitrary interrupted ToolEnv recovery.

Acceptance audit blockers (distinct from the repaired reuse/manifest bugs): `Adapter.check_in` compares hash membership rather than binding each expected checksum name to its materialized artifact, and does not independently validate the materialized dataset identity. Existing same-digest fixtures do not establish swapped-artifact refusal. Run-level cold-load timing is overwritten for each sample rather than retaining/aggregating the actual load, and the existing timing fixture omits execution stages. Identity and timing criteria remain unchecked until those production paths have discriminating tests and fixes. The operator-supplied real launcher, cloud deployment and real GPU qualification remain explicitly outside this source-only ticket.

Integration acceptance (2026-10-30): `python3 -m unittest discover -s workers -p 'test_*.py' -v` from the integration repository passed `Ran 32 tests ... OK`. The first run exposed a new fixture helper argument error; correcting the fixture path (without changing assertions) produced the passing run. This proves the repaired resume/manifest behaviors, not the unchecked identity/timing criteria or real GPU/SDK continuation.
