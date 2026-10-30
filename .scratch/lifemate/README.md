# LifeMate local implementation backlog

**Large specs:** [Offline solution #1](https://github.com/huyxdang/three-good-boys/issues/1) and [shared Google Cloud platform #3](https://github.com/huyxdang/three-good-boys/issues/3).

Routine implementation tickets stay here, not in GitHub Issues. Read the [tracker rules](../../docs/agents/issue-tracker.md) before claiming or updating work. Each ticket owns its status, progress, owner, blockers and acceptance evidence; this index is navigation, not a duplicate status board.

## Tickets

| Ticket | Delivery | Depends on |
| --- | --- | --- |
| [00](issues/00-grounding-gate-and-decision-order.md) | Grounding gate and decision order | None |
| [01](issues/01-sdk-contract-and-training-replay.md) | Verify SDK/scoring contracts and replay a real training sample | None |
| [02](issues/02-labeled-training-evaluation.md) | Reproducible labeled-training evaluation and failure analysis | 01 |
| [03](issues/03-linux-nvidia-pipeline.md) | Complete audio-to-action pipeline on Linux/NVIDIA | 01 |
| [04](issues/04-grounded-agent-behavior.md) | Grounded dependencies, history, clarification and unsupported requests | 02, 05 |
| [05](issues/05-compliant-model-selection.md) | Evidence-backed compliant ASR and language-model selection | 02, 03 |
| [06](issues/06-grounded-compiler-experiment.md) | Optional controlled compiler/native comparison | 02 |
| [07](issues/07-a30-execution-budget.md) | Target-equivalent latency and resource proof | 03, 04, 05 |
| [08](issues/08-offline-docker-execution.md) | Real network-disabled container execution | 03 |
| [09](issues/09-freeze-and-verify-release.md) | Integrated frozen artifact, compliance and matching full replays | 04, 05, 07, 08 |
| [10](issues/10-submit-frozen-solution.md) | Human-verified solution submission | 09 |
| [11](issues/11-private-evaluation-and-results.md) | Frozen-solution private execution and result submission | 10; organizer release/access |
| [12](issues/12-cloud-front-door-and-connection.md) | Public overview and authorized cloud connection guidance | None |
| [13](issues/13-google-cloud-foundation-plan.md) | Terraform foundation with real read-only plan | None; approved project access |
| [14](issues/14-apply-google-cloud-foundation.md) | Apply and verify reviewed persistent cloud resources/IAM | 13; owner approval |
| [15](issues/15-cloud-run-contracts-and-domain.md) | Shared run/request domain and persistence contracts | None |
| [16](issues/16-cloud-api-service.md) | Private API service and authorization | 15 |
| [17](issues/17-cloud-dispatch-reconciliation.md) | Dispatcher, reconciliation, admission and cancellation | 15 |
| [18](issues/18-cloud-team-dashboard.md) | Next.js team dashboard | 15 |
| [19](issues/19-cloud-worker-adapter.md) | Batch worker adapter and offline image integration | None for adapter code; 03 plus data/GPU approval for real execution |
| [20](issues/20-deployment-and-build-source.md) | Containers, service Terraform, IAM/WIF and operations source | 16-19 for real interfaces; no apply |
| [21](issues/21-approved-deployment-slice.md) | Approved deployment and synthetic vertical slice | 14, 20; owner approval |
| [22](issues/22-failure-injection-and-recovery.md) | Failure injection and recovery qualification | 17, 19, 21; organizer semantics for real interruption |
| [23](issues/23-real-cloud-baseline.md) | Real cloud 12-case baseline and dashboard evidence | 21, 22, approved provisioning/GPU, 02/03 gates |
| [24](issues/24-grounded-compiler.md) | Private-only schema-constrained tool-call experiment (grounding lever 1) | Authorized private workspace/review; 02/05 for measured benchmark evidence |

Work the frontier: an unclaimed unfinished ticket with every listed blocker done. Ticket 01's SDK/contract evidence is recorded in that ticket; after it, evaluation and the NVIDIA port can proceed independently. Derive the current frontier from ticket Progress fields, not a second status board. Ticket 06 is optional and never gates submission.

Existing ticket identifiers and links are intentionally retained despite 04 now depending on 05; the measurement gate, not numeric order, controls execution.

## Detailed execution order

Each ticket now contains ordered Implementation steps, acceptance criteria and a Verification section. This index defines team sequencing; check the ticket for its current owner/progress.

### Wave 1: establish quality evidence and a usable target runtime

1. Claim [02](issues/02-labeled-training-evaluation.md) and [03](issues/03-linux-nvidia-pipeline.md) with separate owners. They share the proven SDK contract, not an implementation dependency on each other.
2. Evaluation owner freezes permitted training IDs and implements input/label isolation, saved-prediction comparison and explicit reference-transcript versus actual-ASR modes. Evaluation infrastructure can start on this host; a live model benchmark requires an Apple Silicon baseline machine or the completed NVIDIA port.
3. Runtime owner inventories actual team GPU access and pinned model availability, replaces only Mac inference-specific code, and reuses the existing controller/checkpoints where correct. Demonstrate one real audio sample, then interrupt/resume a small run without constructing a second session for an existing sample.
4. Coordinator verifies current organizer questions, authorized artifact sharing and GPU access while the two owners work. Do not make missing labels or an unavailable official scorer a false blocker for code that can be prepared and measured locally.

### Wave 2: compare models, then improve grounded behavior

1. After evaluation and the port, [05](issues/05-compliant-model-selection.md) benchmarks a small permitted candidate matrix on identical cases, including reference-transcript and actual-ASR modes, and records revisions, eligibility, parameter inventory, quality, latency and memory. No model identity is invented to satisfy a speculative comparison.
2. After both [02](issues/02-labeled-training-evaluation.md) and [05](issues/05-compliant-model-selection.md), [04](issues/04-grounded-agent-behavior.md) addresses measured failures in lookup, dependent IDs, history, negation, clarification and unsupported requests. Preserve the fixed benchmark and use the [decision order](../../docs/decision-order.md) for one-change-per-run selection and regression gates.
3. After the port, [08](issues/08-offline-docker-execution.md) can package the working baseline while quality/model work continues. Mount/output convention is verified; obtain the separate exact launch/model-packaging instructions before claiming compliance.
4. Collect coarse latency/profile evidence as part of port/model runs immediately; do not wait to discover a performance problem at freeze. Final [07](issues/07-a30-execution-budget.md) certification still waits for its listed behavior/model blockers and measures the integrated configuration on target-equivalent hardware.
5. [06](issues/06-grounded-compiler-experiment.md) is optional research after the evaluation baseline. It does not consume the release critical path; a documented rejection with removed scaffolding is a completed experiment.

### Wave 3: prove and freeze the integrated solution

Before final freeze, record the [Phase 5](../../docs/decision-order.md#phase-5--post-train-only-what-measurements-leave-broken) decision and evidence: retain, reject or skip post-training. Preparing the baseline image under ticket 08 may proceed in parallel.

1. Finish [07](issues/07-a30-execution-budget.md) with full end-to-end timings, per-sample timeout evidence and fixed-benchmark quality comparison. A quick CPU or proxy-GPU run is not an A30 compliance result.
2. [09](issues/09-freeze-and-verify-release.md) integrates the exact behavior/models/performance configuration into the offline image, inventories licenses and eligibility, and performs two complete matching replays with fixed artifacts.
3. Freeze the image/package and checksum only after actual output coverage, session trace/hash, determinism and timing evidence exist. Preserve the original handoff separately from evolving working code.
4. [10](issues/10-submit-frozen-solution.md) and [11](issues/11-private-evaluation-and-results.md) require registered-team portal actions and receipts. Private evaluation uses the frozen solution, not ad hoc prompt/model changes on private inputs.

## Three-person work lanes and shared edits

| Suggested lane | Main tickets | Handoff to the next lane |
| --- | --- | --- |
| kitkitkittt: collaborator | 01, initial evaluation 02 | SDK/source note, fixed training inputs and evaluation evidence |
| Teammate 1: quality/models | 04, joint model evaluation 05 | Permitted training failure cases and selected quality settings |
| Teammate 2: runtime/release | 03, 08, joint model runtime 05, 07 | CUDA smoke/resume proof, pinned runtime, actual latency, offline image invocation |

These are suggestions, not assignments. Claim in each ticket and use the same Owner name in your personal context file. A coordinator can take evaluation preparation while another teammate obtains GPU access; only real blockers determine sequencing.
Release integration and registered-team submission duties are unassigned until the team chooses an authorized coordinator; they are not implied by kitkitkittt's contribution or GitHub placeholder.

- The working runner is one file. Before port or quality edits, agree one integration owner in ticket Comments; avoid concurrent conflicting edits to Agent/SYSTEM, model_input, Store or validate_and_export.
- Evaluation owns metric/report semantics and input/label isolation. Runtime owns native inference and checkpoint compatibility. Quality owns decision behavior. Reuse the existing runner seam; do not create a general framework merely to split ownership.
- After source/model/runtime/config changes, use a new run directory. Do not compare results silently resumed from an incompatible checkpoint.
- Before merging any candidate into the selected solution, run its real training path and the fixed benchmark, then record the commands/results in the ticket. Personal context files link that evidence rather than copying status.

## External gates and dates

Checked the rendered [official portal](https://challenge.zalo.ai/portal/lifemate) on 2026-10-28. Current published dates: solution package November 16 at 23:59 GMT+7; private input November 20 at 09:00; private results November 23 at 23:59 GMT+7. Recheck before submission. Use the [SDK/source note](../../docs/sdk-contract.md) for verified caps and score rules, not historical handoff summaries.

- Target GPU/driver: this host lacks `nvidia-smi`. The private `compute-01` RTX 4060 Ti has exercised CUDA inference and a network-disabled GPU container; it is proxy hardware, not A30 certification. Global and Singapore L4 quotas were observed available, but actual GCP capacity and A30 access remain unverified. See [ticket 03](issues/03-linux-nvidia-pipeline.md) and the [cloud connection guide](../../docs/cloud-connection.md).
- Official scorer: no executable task scorer in the archive. The portal publishes the formula/matching specification; label local approximations and resolve ambiguous tokenization/tie matching when required.
- Container: /data and result/submission.jsonl are portal-confirmed. Exact entrypoint/base image/model packaging and timing boundaries still need the separate organizer guidance.
- Sharing: public-repository distribution remains prohibited by the handoff. The portal requests a public Google Drive package link; a registered owner must resolve the approved exception/access method with the organizer before upload. No visibility change or package publication is authorized by this plan.
- Human-only items: model/data access where authentication is required, target-GPU provisioning, final portal acceptance and private input/result submission. Finish all reachable engineering work before treating these as blockers.

## Sources and evidence

The [shared context](../../context/README.md) records source locations, baseline evidence limits, privacy rules and per-person progress spaces. The official kit and current organizer instructions override historical handoff proposals. Tickets do not mandate a speculative model, compiler or optimization.

Keep restricted datasets, competition code, submissions and traces out of public commits and issues. Ticket acceptance boxes describe future work; unchecked boxes and Verification text must not be mistaken for completed implementation.
