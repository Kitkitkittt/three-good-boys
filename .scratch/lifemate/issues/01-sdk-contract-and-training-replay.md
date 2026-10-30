# 01: Verify the SDK contract and replay a training sample

**Parent spec:** [LifeMate competition solution](https://github.com/huyxdang/three-good-boys/issues/1)

**What to build:** A registered teammate can explain the actual organizer contract and reproduce one real labeled-training sample from input through simulator execution to a valid submission record. Reuse the existing baseline and kit rather than rebuilding from the planning handoff's outdated assumptions.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

**Owner:** kitkitkittt

**Progress:** done

## Implementation steps

1. Verify the original bundle checksum list, then import the runner/tests/manifest and organizer reference docs into the Git-ignored working layout. Preserve the original bundle and historical submission unchanged.
2. Extract the unchanged organizer release under `work/data/`; inventory row/catalog contracts and inspect SDK source without opening raw environment files. Document primary sources in [the SDK note](../../../docs/sdk-contract.md).
3. Run the original control-flow tests and imported CLI help, then use `scripts/sdk_smoke.py` for one explicitly reference-driven training session. Record actual calls/results, changed-app comparison and the environment-derived hash locally.
4. Check the replay output with `schema_validate` and the organizer schema-only CLI. Distinguish this SDK replay from ASR/planner inference and from competition scoring.
5. Read the rendered official portal's Evaluation, Rule and Submission Guidance sections, including the score-formula image. Record matching/empty-reference/hash-gate rules, caps, mount/output convention and deadlines from that source; distinguish the published specification from an unavailable executable official scorer.

## Acceptance criteria

- [x] Record the organizer release/version and sources for sample loading, audio, history, installed-tool catalogs, schema extensions, ToolEnv creation, validation, execution, call retrieval, final hash, scoring, and output format. Separate SDK-observed behavior from portal claims that still need confirmation.
- [x] Resolve the exact missing-information and unsupported-request contracts from the actual tool catalog. Record that history actions are already applied and only the latest request is executed.
- [x] Identify the official evaluator and its availability; document exact matching, fuzzy matching, empty-reference-call, and hash rules from authoritative material. Label any local approximation rather than calling it official scoring.
- [x] Preserve bundled baseline artifacts before a smoke run can overwrite them. Record trusted model revisions, runtime dependencies, and whether the available machine can run the Mac baseline or must use the NVIDIA port.
- [x] Replay a permitted real training sample using exactly one official environment for that execution. Observe at least one genuine tool result and emit its actual ordered call log and environment-derived final hash in an organizer-compatible record. A supplied training transcript may isolate simulator integration; label that run as transcript-only, not an audio inference result.
- [x] Check the exported record against that session's call log and hash and the organizer's available validator. Include actual rejected calls, distinguish validation-only proposals, and never directly read raw environment files or fabricate responses.
- [x] Publish a concise contract/replay note with the exact command, machine/runtime, sample reference, observed result, and any unresolved organizer packaging questions. Keep restricted evidence in team-authorized storage.

## Verification

- `sha256sum --check SHA256SUMS` from the original bundle: all 12 entries passed. Material copies preserve the baseline; output goes under the repository's ignored `work/`/`outputs/`, not into the original bundle.
- `python3 -m unittest discover -s baseline -p 'test_lifemate_v1.py' -v`: six tests passed on Linux/Python 3.14.4. `python3 baseline/lifemate_v1.py --help` succeeded. This is not model inference.
- `python3 scripts/sdk_smoke.py`: `train_0864`, two actual reference calls, zero schema/rejected calls, exact call and changed-app final-state match, one SDK environment and its authoritative hash. Evidence: `work/sdk-smoke/train_0864/` (ignored/private).
- Organizer CLI validate mode: one line checked, zero schema errors. It does not compute a task score or guarantee whole-split coverage.
- [Working runbook](../../../docs/working-baseline.md) and [SDK contract](../../../docs/sdk-contract.md) record source locations, exact commands, hardware limits and unresolved details.
- Rendered [official portal](https://challenge.zalo.ai/portal/lifemate) checked on 2026-10-28: observed scoring prose and formula image, technical limits, offline mount/output contract and submission schedule. Local snapshots: `work/official-portal/2026-10-28/`. No executable official scorer is supplied; exact tokenizer/tie-matching implementation and detailed Docker launch guidance remain documented follow-up questions, not unobserved claims.

## Comments

The handoff already contains a Mac/MLX baseline and a historical public run. This ticket establishes what is reusable and proves the SDK lifecycle; it does not claim target-machine compatibility or task accuracy.
