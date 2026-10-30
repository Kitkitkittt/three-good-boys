# 08: Execute real input in an offline Docker image

**Parent spec:** [LifeMate competition solution](https://github.com/huyxdang/three-good-boys/issues/1)

**What to build:** A registered teammate can launch the solution container with networking disabled and the organizer's required mounted input, then obtain a complete organizer-compatible JSONL result without access to the developer's home directory or online services.

**Blocked by:** [03: Linux/NVIDIA pipeline](03-linux-nvidia-pipeline.md).

**Status:** ready-for-agent

**Owner:** Unclaimed

**Progress:** not-started

## Implementation steps

1. Look for the current official Docker instructions (entrypoint, base image/runtime restrictions, model packaging, mount and output paths). Record what was found with source; if absent, record the gap and keep working paths as provisional rather than official.
2. Write the Dockerfile/image build from the ported pipeline (ticket 03): pinned Python deps, baked model artifacts, no download/install/telemetry/auth steps at runtime.
3. Wire dynamic sample IDs/catalogs to the portal-confirmed input mount /data and output result/submission.jsonl. Obtain the separate organizer launch instructions for the exact entrypoint and image/model-packaging requirements; do not invent those remaining details.
4. Verify the Docker daemon and GPU passthrough on the host; build the image and prepare a permitted sample input for a smoke run.
5. Run `docker run --network none --gpus all -v <input>:<mount> …` on that input and exercise ASR, planner, real simulator calls and output generation end to end.
6. Validate the output: one UTF-8 JSONL record per ID, types, no duplicates/extras, all executed and rejected calls, session final hash; check the container needs no home paths or network.
7. Record the exact launch command, image id, mounted artifacts and validation result; define explicit success/failure signaling so a partial run cannot look finished.

## Acceptance criteria

- [ ] Locate and record the current official container entrypoint, base/runtime restrictions, model packaging rules, data mount and output location. The bundled SDK README says Docker instructions are separate; do not invent an authoritative CLI when that document is unavailable.
- [ ] Pin dependencies and approved model artifacts so runtime needs no downloads, package installation, external API, telemetry or authentication. Verify model/license eligibility before distribution; keep restricted artifacts within authorized team channels.
- [ ] Process supplied sample IDs and dynamic catalogs without a fixed public count or split name. Use /data and result/submission.jsonl as confirmed by the rendered official Rule section on 2026-10-28; follow the separately confirmed launch contract for the final image.
- [ ] Run the actual GPU container with --network none on permitted input. Exercise ASR, the selected current planner, real simulator execution, and output generation rather than using a bundled completed submission as a shortcut.
- [ ] Validate exactly one UTF-8 JSONL record per input ID, no duplicates or extra submission fields, correct types, complete actual calls including rejected calls, and the same session's final hash. Do not directly inspect raw environment files to produce results.
- [ ] Confirm the image does not rely on unmounted home paths, online caches or credentials. Record the exact launch command, image identifier, mounted artifacts, observed results and output validation.
- [ ] Make output completion/failure explicit so a partial or failed run cannot masquerade as a finished submission. Document how invocation resumes only compatible trusted checkpoints if supported by the official contract.

## Verification

No implementation verification yet. Completion requires a real network-disabled container run and inspected output/call/hash validation. A successful build alone is insufficient.

## Comments

Container scaffolding can proceed after the NVIDIA pipeline and in parallel with quality/model/latency work. Final release integration and full replay evidence belong to ticket 09; unavailable official packaging instructions must be recorded precisely, not replaced with fake compliance.

2026-10-28 preparation: Docker client and daemon 29.1.3 are reachable on this host. No nvidia-smi binary is installed, and GPU passthrough/image execution are unverified. Current portal mount/output requirements are recorded in [the SDK source note](../../../docs/sdk-contract.md); no Docker implementation is claimed complete.

2026-10-29 source search: official-site and GitHub-scoped searches did not reveal the separately referenced Docker guide. A fresh rendered [LifeMate Rule and Submission Guidance](https://challenge.zalo.ai/portal/lifemate) check confirms `/data`, `result/submission.jsonl`, the A30/30-second limit and the separate-guidelines reference; neither displayed section linked the guide. Exact entrypoint, base/CUDA image restrictions, launch command, model packaging and private SDK layout remain unverified; this search does not establish that the separate guide does not exist.

2026-10-29 preparation from omp, not a ticket claim: an offline `linux/amd64` image (`lifemate-runtime:local`, `sha256:72f927f17ea1a8cb28300b357f5cd7fdc22d7406faaf993f63dea4220503f361`) installed the 38 already-pinned packages from a pre-downloaded wheelhouse with `--network none` and ran the real ASR/planner/ToolEnv path on `train_0097` under a read-only root filesystem, producing one schema-valid JSONL record with a matching session hash. See [ticket 03](03-linux-nvidia-pipeline.md) Verification for the command shape and limits. This does not satisfy the criteria above: the mount points are the candidate's own rather than `/data` and `result/submission.jsonl`, the base image is the team's own rather than a permitted official choice, and resume behavior was only exercised outside the container. Ticket 08 stays unstarted until ticket 03 is done.
