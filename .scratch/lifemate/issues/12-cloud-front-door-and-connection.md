# 12: Explain LifeMate and verify the cloud connection

**Parent spec:** [Shared Google Cloud platform #3](https://github.com/huyxdang/three-good-boys/issues/3).

**What to build:** A public-facing project overview and authorized-team cloud connection runbook that distinguish existing Mac baseline, privately exercised CUDA candidate, deployed resources, proposed stack and unfinished A30/offline gates.

**Blocked by:** None.

**Status:** ready-for-agent

**Owner:** omp-cloud-onboarding

**Progress:** done

## Acceptance criteria

- [x] README leads with the problem, an explicitly illustrative example, current candidate pipeline, dated evidence limits, public vs authorized setup paths and repository navigation.
- [x] Preserve all restricted material exclusions; no private traces, credentials or code copied into docs. Aggregate evaluation claims link existing evidence and stay explicitly approximate/non-official.
- [x] Document real project-scoped read-only connection checks, CLI vs ADC identity, current API/quota observations, and named spending/data/IAM approval gates.
- [x] Record current cloud operations accurately: platform APIs enabled, global/Singapore L4 quotas 1 and unused, authorized Cloud Shell reached, no GPU or persistent foundation apply.
- [x] Verify Markdown navigation and actual rendered README content without claiming infrastructure is running.

## Verification

Coordinator evidence, 2026-10-30: local `/home/dev-01/google-cloud-sdk/bin/gcloud` authenticated `ttbeta8386@gmail.com`; `projects describe` returned active project `project-cc6075c8-508b-491d-98d`/`388717445849`. A project IAM query returned `roles/owner`; billing describe returned enabled and the linked account reported open. CLI was absent from PATH, while the default ADC file and explicit credential override were absent on the workstation.

After the quota increase, `compute project-info describe` returned global `GPUS_ALL_REGIONS` limit 1 / usage 0; `compute regions describe asia-southeast1` returned regional `NVIDIA_L4_GPUS` limit 1 / usage 0. The coordinator's project-scoped `services enable` operation for the listed platform services completed successfully; the complete service IDs are in the [connection runbook](../../../docs/cloud-connection.md#observed-state--2026-10-30). The earlier read-only inventory returned no VMs, persistent disks, reserved IPs or buckets.

The coordinator's `gcloud cloud-shell ssh --authorize-session ... --project=project-cc6075c8-508b-491d-98d --quiet` reached an authorized shell: the account matched, default project was unset and Terraform was not then installed. No GPU or persistent resource/IAM apply was performed. Credit balance/expiry, price and physical capacity were not established.

Cloud Shell rendered README with Python-Markdown 3.9 and verified 30 local links across README, the connection runbook and the foundation runbook. The generated README was visually inspected in Chromium; the problem statement, pipeline, evidence limits, setup paths and navigation rendered correctly. No deployed service was claimed. The initial navigation check stopped because the sanitized upload omitted the existing `context/` directory; transferring that public documentation completed the check without a repository link change.

## Comments

Keep detailed Terraform commands in the foundation runbook owned by ticket 13. Keep measurement order in docs/decision-order.md. Reuse existing integration branch and draft PR; no duplicate competing backlog or inference implementation.
