# Working baseline

The repository retains the original Apple Silicon/MLX working baseline and unchanged handoff. A CUDA port exists only in authorized private workspaces; it has run a real training sample but is not a verified submission.

## Private Linux/NVIDIA candidate

The shared `baseline/` remains the original MLX runner. The authoritative private candidate handoff is the ignored `work/ticket-03-port-20261028/`, containing `lifemate-cuda-candidate.patch`, full candidate files, checksum lists and `INSTRUCTIONS.txt`. It has been applied only in a separate owner-only workspace, `/home/dev-01/.local/share/lifemate-integration-20261029`, and executed on authorized `compute-01`. These files contain restricted competition code; use an approved private transfer, never a public Git repository or a force-add.

On this machine the patch SHA-256 is `2829aca85e4709d9a5f7619562540957bc349765111664a6452031b055d44c4c`. It applies to the original runner SHA-256 `0a5e508c392a49bee879bfd06bc20d693d9c76e19d5d229d68b202d15deffc7f` and test SHA-256 `16eeb25473822676877ec4e8fe10b53c5882a7a50d293a33464a0a19a0cf2b40`. Expected candidate hashes are runner `938a9a0915f61fbc7fdc4df062ae4c5a2a0176544bf1e71d6a95f9219672f1b5`, tests `2bf1c18ba15fa3d893384db3b724230bb66905a93b347fe2b1b70f7d14a84739`, and Linux requirements `3b322f1973c680c3cef5ee9c57d435c3ddf2d0d84f379c0e95ce1a81c7dfb22e`. Replaying the patch in a separate temporary copy produced those three hashes; the main baseline was not edited.

The handoff directory is owner-only; an authorized teammate needs read access granted through an approved mechanism, or an owner-made copy under that teammate's account, before verifying the transfer.

To apply only in a **new authorized private workspace**, copy the entire private handoff directory by an approved channel, preserve local edits and read its `INSTRUCTIONS.txt`. From the new workspace, with `HANDOFF_DIR` set to that copied directory:

```bash
(cd "$HANDOFF_DIR" && sha256sum -c SHA256SUMS)
sha256sum -c "$HANDOFF_DIR/BASELINE-SHA256SUMS"
test ! -e baseline/requirements-linux.txt
git apply --check "$HANDOFF_DIR/lifemate-cuda-candidate.patch"
git apply "$HANDOFF_DIR/lifemate-cuda-candidate.patch"
sha256sum -c "$HANDOFF_DIR/CANDIDATE-SHA256SUMS"
```

The private candidate uses local Transformers/PyTorch CUDA loaders. On `compute-01`, the pinned runtime and models completed a real offline training audio-to-simulator sample and a controlled same-session checkpoint resume. See ticket 03 for exact commands, revisions, local quality results and resource measurements. An offline wheelhouse install, Mac-baseline comparison, organizer private-input contract and A30-equivalent timing remain unverified. The Mac directions below apply only to the unchanged handoff/main baseline.

The candidate uses Whisper Turbo only; the requested Qwen3-ASR/PhoWhisper comparison remains unmeasured. A separate Whisper large-v3 ASR and cached-transcript planner comparison is documented in the training-evaluation runbook; it is preliminary evidence, not a model selection. Schema-constrained decoding is not implemented and remains subject to the grounding gate.

A separate, private `--data-root` experiment is under `work/ticket03-portable-root-20261029/`; its existing-layout regression and real GPU smoke are recorded in ticket 03. It has not replaced the authoritative private candidate and does not establish support for the eventual private split or launcher.

## Material layout

Paths are relative to the repository root.

| Local path | Material / purpose | Publication |
| --- | --- | --- |
| `baseline/lifemate_v1.py` | Byte-identical working copy of the existing resumable Mac runner | Git-ignored, restricted competition code |
| `baseline/test_lifemate_v1.py` | Six existing control-flow tests | Git-ignored, restricted competition code |
| `baseline/requirements-mac.txt` | Original pinned Mac dependencies, renamed for clarity | Git-ignored; not Linux requirements |
| `baseline/baseline-manifest.json` | Historical model revisions, runtime and checksums | Git-ignored historical reference |
| `baseline/HANDOFF.md`, `baseline/SOURCE-SHA256SUMS` | Original team instructions and bundle checksums | Git-ignored historical reference |
| `organizer/README-LifeMate.md`, `organizer/VERSION` | Unchanged technical documentation and release identity | Git-ignored organizer material |
| `organizer/train+public_test.zip.sha256` | Original archive checksum | Git-ignored provenance |
| `work/data/train+public_test/` | Extracted unchanged train/public kit: audio, catalogs, SDK and environments | Git-ignored restricted data |
| `scripts/sdk_smoke.py` | Stdlib real-SDK training-reference replay; not inference or scoring | Git-ignored competition helper |
| `work/sdk-smoke/<sample>/` | Replay record, report and actual tool results | Git-ignored private evidence |
| `work/models/`, `work/lifemate-v1-<split>/` | Future local weights and trusted checkpoints | Git-ignored; not supplied |
| `outputs/` | Future working-run results; separate from original bundle results | Git-ignored |

The restricted regulations PDF, archive, historical submission and validation report remain in `lifemate-handoff/lifemate-team-handoff/`; they were not needlessly duplicated. The working runner keeps its parent-parent root calculation: from `baseline/` it resolves the repository root, so its existing `work/` and `outputs/` paths work without editing source.

Nothing was committed, pushed or uploaded by material preparation. A public repo is not an authorized distribution channel for this code/data. Ignored files will not appear in an ordinary clone; teammates need the original bundle and approved private material transfer, or owner-approved private repository access. `.gitignore` is not access control and does not remove old history.

## Local checks: no model dependencies

Run from the repository root:

```bash
python3 -m unittest discover -s baseline -p 'test_lifemate_v1.py' -v
python3 baseline/lifemate_v1.py --help
python3 scripts/sdk_smoke.py
```

The last command reads a supplied training label and executes those reference calls through exactly one real SDK session. It never runs ASR or a language model, never reads raw environment files, and never computes a substitute final hash. It checks the actual call log, schema validation and changed-app final states through the SDK. Treat its output as integration evidence only.

Evidence is saved to `work/sdk-smoke/train_0864/`. The command refuses a nonempty output directory to preserve prior evidence. To run another independent reference replay, use a fresh destination:

```bash
python3 scripts/sdk_smoke.py --sample-id train_0864 --output-dir work/sdk-smoke/train_0864-second
```

Schema-only validation using the organizer CLI:

```bash
env PYTHONPATH=work/data/train+public_test/train python3 -m zaic_tools \
  --split train --root work/data/train+public_test \
  --validate work/sdk-smoke/train_0864/submission.jsonl
```

That CLI creates its own session only to identify allowed tools; it does not execute calls or score the output. It prints errors but does not provide a reliable failing exit status, so inspect its summary. The replay helper also checks schema results in-process and exits unsuccessfully on a failed replay.

## Recreate material from the original bundle

The existing imported files are intentionally unchanged. On a fresh authorized workspace, obtain the bundle privately, verify its `SHA256SUMS` from the bundle root, then place the named runner/test/dependency and reference-document files at the paths above. Do not overwrite someone else's modified working baseline with another import.

Extract the original release without replacing existing files:

```bash
mkdir -p work/data
unzip -q -n lifemate-handoff/lifemate-team-handoff/organizer/train+public_test.zip \
  -d work/data -x '__MACOSX/*' '*/.DS_Store'
```

Only the organizer SDK may load environment state. Extraction copies those files without inspecting them. Do not browse, parse, transform or use them directly to solve requests. An existing mixed-version extraction must be replaced in a new clean workspace rather than silently accepted as the current release.

## Actual model inference: Apple Silicon only

The original handoff used Python 3.11.7 on Apple Silicon/macOS. Do not install the Mac requirements into the current Linux environment expecting a CUDA runtime.

On an authorized Apple Silicon machine, from the repository root:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r baseline/requirements-mac.txt
```

Use the exact online model-download instructions/revisions in `baseline/HANDOFF.md` and verify them against `baseline/baseline-manifest.json`. Keep weights under `work/models/`; the imported manifest is historical, not a manifest for a new run. Then run real training audio with a new run/output directory:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -u baseline/lifemate_v1.py \
  --split train --sample-ids train_0864 \
  --run-dir work/lifemate-v1-train-smoke --output-dir outputs/train-smoke
```

The runner fingerprints source, inputs, SDK, weights and runtime. Reuse a run directory only with identical configuration; after source/model/runtime changes, start a new directory. Checkpoints contain pickle: only load trusted local files. The supplied historical submission has no checkpoint database and cannot be resumed or session-revalidated on its own.

The train catalog is larger than the public catalog. The original runner sends the entire split catalog and can reject a prompt that leaves insufficient context. This has not been exercised with models on this host; measure before assuming the training model smoke fits.

## Observed preparation evidence, 2026-10-28

- All 12 original `SHA256SUMS` entries verified, including the archive, runner, tests, historical submission and manifest.
- Imported text material retains source contents. The complete organizer archive was extracted under `work/data/`, excluding macOS metadata.
- Host: Linux x64, Python 3.14.4. Docker client and reachable daemon version 29.1.3. `nvidia-smi` is not installed; GPU/driver/container-GPU capability is not established by this workspace.
- Six original control-flow tests passed; the imported runner's `--help` works without loading MLX.
- `train_0864` training-reference replay: two real calls, no schema errors or rejected calls, exact reference call sequence and changed-app final state match. Final hash came from `ToolEnv.get_state_hash()`; report and tool results are in the ignored evidence directory.
- Organizer CLI reported `1 lines checked, 0 schema errors`. This is not an accuracy or competition-score result.
- No model weights were downloaded, no model inference/benchmark was run, and no final Docker image was built.

See the [SDK contract](sdk-contract.md) for primary-source behavior and the [detailed execution plan](../.scratch/lifemate/README.md) for the next work.
