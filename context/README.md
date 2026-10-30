# Three Good Boys: working context

Start here when resuming LifeMate work. This folder records project context and per-person progress; it is not a second issue tracker or a new domain-document layout.

## Work and ownership

- [Large LifeMate spec: GitHub #1](https://github.com/huyxdang/three-good-boys/issues/1).
- [Local implementation tickets](../.scratch/lifemate/README.md): authoritative for ownership, blockers, completion and verification evidence.
- [Tracker rules](../docs/agents/issue-tracker.md), [triage vocabulary](../docs/agents/triage-labels.md), and [domain rules](../docs/agents/domain.md).
- [Working baseline and commands](../docs/working-baseline.md), [SDK contract and live official requirements](../docs/sdk-contract.md).
- [Saved-output evaluation commands and limits](../docs/training-evaluation.md); kitkitkittt owns the in-progress local evaluation ticket, not the project or team submission account.
- [Decision order: measure → ground → post-train](../docs/decision-order.md): the ordering authority for measurement-before-weights (tickets 04, 05 and 09).

| Person / space | Progress file | Suggested lane, not an assignment |
| --- | --- | --- |
| kitkitkittt, collaborator | [kitkitkittt.md](kitkitkittt.md) | SDK contract and initial training evaluation |
| Teammate 1, unclaimed | [teammate-1.md](teammate-1.md) | Training evaluation and agent quality |
| Teammate 2, unclaimed | [teammate-2.md](teammate-2.md) | Linux/NVIDIA runtime, latency and Docker |

Each person fills in their identity in their own file. Claim an actionable ticket before implementation by setting its Owner and Progress; suggestions above do not reserve work. Different files reduce conflicts in progress notes, but shared code changes still require owner coordination through ticket Comments.

## Session protocol

1. Read this file, your own progress file and the ticket you intend to work on. Read another person's notes only when a dependency or shared change needs coordination.
2. Confirm every ticket blocker is done and the ticket is unclaimed; set Owner and Progress before changing implementation.
3. Record real commands, machine/artifact identities, observed results and authorized evidence locations in the ticket. Mark Progress done only when all acceptance criteria hold.
4. Update your own progress file with completed work/evidence, current work, blockers and the next concrete step. Link the ticket instead of copying its acceptance checklist or maintaining another backlog.
5. Change shared context only for a durable team-wide fact or agreed decision. Keep superseded experimental details in ticket history, not this entry point.

## Starting state: reviewed 2026-10-28

- The local handoff bundle contains organizer v3.2.0, a Mac/MLX baseline, toy control-flow tests, pinned baseline settings and a historical public result. It is not a blank repository and is not a verified final Docker solution.
- The bundle's historical report records 634 unique output IDs, zero schema errors and 634 session-log/hash checks. Its README reports a public portal score of 11.80000. These are historical source claims, not a newly executed benchmark, independently verified score or A30 timing result.
- The Mac runner needs a Linux/NVIDIA port for the intended runtime. Training accuracy, model comparisons, target-equivalent latency, offline Docker execution and deterministic final replay still require evidence.
- The initial setup created work tracking only. Subsequent material preparation imported the unchanged runner/tests and organizer references, extracted the official kit locally, passed six control-flow tests and executed a two-call real training-reference replay. This was not ASR/model inference, a quality benchmark or a final submission.
- The older planning handoff says implementation was unverified; the bundled runner and reports resolve that inventory gap, not all competition-readiness requirements. Reuse the baseline and validate it rather than restarting.

## Source-of-truth order

1. Current official organizer portal, regulations, technical instructions and unchanged SDK. Resolve conflicts with historical summaries before implementation or release.
2. Local restricted team bundle, relative to the repository root: `lifemate-handoff/lifemate-team-handoff/README.md`, `organizer/README-LifeMate.md`, `organizer/zalo-ai-challenge-regulations-en.pdf`, `baseline-manifest.json`, and `outputs/lifemate-v1-public_test/validation.json` beneath that bundle root.
3. Planning handoff: `../handoff.md` relative to the repository root. Treat architectural/model recommendations as proposals, not observed implementation or current official requirements.
4. Approved [large spec](https://github.com/huyxdang/three-good-boys/issues/1), local tickets and recorded evidence. The tickets translate the plan into work; they do not supersede organizer rules.

Public sources: [LifeMate portal](https://challenge.zalo.ai/portal/lifemate) and [regulations](https://challenge.zalo.ai/regulations). The rendered portal's Evaluation, Rule and Submission Guidance sections were checked on 2026-10-28; the SDK note records the verified formula, limits, mount/output convention and dates, with unresolved detailed launch/timing questions kept separate. Private source paths above are local references, intentionally not links to public copies.

## Privacy and access

The repository was PUBLIC at setup. The handoff limits its material to authorized registered teammates. Git ignore rules now cover the original bundle, baseline working copies, organizer references, work/data/models/evidence, runtime outputs and the SDK replay helper. They prevent ordinary new adds, not prior publication or unauthorized forced adds; they do not replace access control. Ignored material is not transferred by an ordinary public clone.

Keep organizer data, competition code, model artifacts, submissions, private traces and credentials out of public commits, issues and releases. Do not copy the handoff into this folder. Confirm private repository/storage access before sharing restricted artifacts; changing repository visibility remains an owner action, not something this setup did.

The authenticated GitHub account at setup was `Kitkitkittt`, with READ repository permission. GitHub issue #1 was successfully created, but attempts to create the four missing default triage labels returned HTTP 404. `wontfix` already exists. The repo owner must create `needs-triage`, `needs-info`, `ready-for-agent` and `ready-for-human`, then label the umbrella spec as appropriate, or grant authorized write access. Local ticket Status values do not depend on this permission.

## Decisions from setup

- Only large specs belong in GitHub Issues; fine-grained tickets stay in local Markdown.
- Use default triage role strings and a single-context domain layout. Create glossary/ADRs lazily when real terms or decisions resolve.
- Keep one personal progress file per collaborator; do not assume teammates' identities or mark planned implementation complete.
- The grounded-compiler experiment is optional and does not gate the final submission.

## Working-material handoff

The local working layout is documented in the runbook. Original bundle hashes all passed; no original handoff file was changed. Root baseline copies keep source byte identity and existing parent-parent path semantics. Historical submissions remain in the bundle, not copied into a fresh run's outputs.

Ticket 01 records SDK/portal evidence. Read ticket Progress fields to select the frontier; evaluation and the Linux/NVIDIA port are the next parallel workstreams when their shared contract prerequisite is done. Every local ticket now has ordered Implementation steps, and the index defines work waves and shared-code ownership seams.

Host preparation observed Python 3.14.4, reachable Docker client/daemon 29.1.3 and no nvidia-smi binary. Team GPU access is not established by that probe. Do not install Mac MLX requirements here as a pretend NVIDIA backend or call the reference replay a model result.

The portal requests a public Google Drive solution-package link while the bundle prohibits general public distribution. The registered owner must resolve approved organizer access/submission exceptions before upload; this preparation publishes no package or restricted working material.
