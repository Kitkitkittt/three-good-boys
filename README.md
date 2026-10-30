# LifeMate: speech to grounded actions

Three Good Boys is working on the [LifeMate challenge](https://challenge.zalo.ai/portal/lifemate): given a spoken request, conversation history and the user's available apps, choose and execute appropriate actions in the organizer's simulated tool environment. The result must contain the actions actually executed and the final state hash from the same session.

**Illustrative request, not a dataset example or a demonstrated result:** “Remind me tomorrow at 9 to pay the rent.” A successful assistant would use the available context and tool schemas to decide whether it can create the reminder or needs clarification; the actual tools and inputs depend on the sample.

## Current candidate pipeline

The existing handoff contains a Mac/Apple Silicon MLX baseline. A separate **private**, partially exercised Linux/NVIDIA CUDA candidate reuses its controller and exporter:

1. Transcribe the latest request and relevant history audio with Whisper large-v3-turbo.
2. Give Qwen3-4B-Instruct-2507 the permitted transcript, context, history and available tool schemas to plan actions or request missing information.
3. Validate proposed tool calls; execute appropriate calls through the official ToolEnv, using observed results for dependent actions.
4. Export the actual ordered calls and final state hash from that same ToolEnv session.

These are candidate stages, not a claim that every request succeeds or that model selection is finished. Training labels and reference transcripts are not production policy inputs. See the [SDK contract](docs/sdk-contract.md) and [private candidate status](docs/working-baseline.md#private-linuxnvidia-candidate).

## Status and evidence — 2026-10-30

- The original MLX baseline remains in restricted local material; it is **not included in a public clone**. The separate CUDA candidate has run real audio through the organizer simulator on a private proxy GPU, not an A30. [Ticket 03](.scratch/lifemate/issues/03-linux-nvidia-pipeline.md) records the remaining port and comparison gates.
- Small frozen training diagnostics and proxy-GPU timing exist; the local score is an approximation, not an official result or representative accuracy estimate. Some proxy cases exceeded the challenge's 30-second limit. See [training evaluation](docs/training-evaluation.md#exercised-evidence) for methods and limits; no proxy result certifies target hardware.
- A network-disabled private CUDA container exercised the real path using mounted weights on proxy hardware. It does not establish the final organizer launcher, embedded-assets image, A30 timing, deterministic release or submission readiness. The [SDK contract](docs/sdk-contract.md#official-scoring-and-release-requirements-checked-2026-10-28) records the known rules and unresolved guidance.
- An existing Google Cloud project is accessible, requested platform API enablement succeeded, and global/Singapore L4 quotas were observed unused. Sanitized API, dispatcher, dashboard, worker-adapter and deployment source exist with local CPU/mocked checks; no persistent foundation, deployed service or GPU workload has been applied by this work. The worker's real competition launcher remains private. See [cloud connection](docs/cloud-connection.md), [operations](docs/cloud-operations.md) and the [implementation tickets](.scratch/lifemate/README.md) for approval gates and unchecked acceptance criteria.

## Getting started

**Public readers:** browse this overview, the linked specifications and runbooks. This repository is a sanitized planning and review surface, not a runnable distribution of the competition baseline, organizer SDK/data, model weights or submissions.

**Authorized registered teammates:** obtain the original handoff and any private CUDA candidate only through an approved private channel, preserving existing work. Follow the [working-baseline runbook](docs/working-baseline.md) for private setup and [cloud connection runbook](docs/cloud-connection.md) for project-scoped access. Cloud access does not itself authorize uploading restricted source, data, models or traces; the organizer's rules and the separate transfer and spending approvals still apply.

Do not commit or publish competition code, data, credentials, model artifacts, submissions or private traces. Git ignore rules are not access control. Raw environment files may be accessed only by the official SDK, not by the agent; follow the [privacy and access guidance](context/README.md#privacy-and-access).

## Repository guide

- [Offline solution spec #1](https://github.com/huyxdang/three-good-boys/issues/1) and [Google Cloud platform spec #3](https://github.com/huyxdang/three-good-boys/issues/3).
- [Integrated Google Cloud implementation plan](docs/google-cloud-implementation-plan.md), [cloud connection](docs/cloud-connection.md) and [foundation plan/runbook](docs/cloud-foundation.md).
- [Working baseline](docs/working-baseline.md), [SDK contract](docs/sdk-contract.md) and [training evaluation](docs/training-evaluation.md).
- [Decision order: measure → ground → post-train](docs/decision-order.md) and [accepted grounding-gate ADR](docs/adr/0001-grounding-gate-before-post-training.md).
- [Local implementation tickets](.scratch/lifemate/README.md) and [team context](context/README.md). GitHub Issues holds large specs; routine tickets remain local.