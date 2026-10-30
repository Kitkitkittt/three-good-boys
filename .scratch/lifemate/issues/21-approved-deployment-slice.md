# 21: Approved deployment and synthetic vertical slice

**Parent spec:** [Shared Google Cloud platform #3](https://github.com/huyxdang/three-good-boys/issues/3).

**What to build:** Deploy the reviewed services and prove the whole path with permitted synthetic inputs: authorized acceptance, one admitted Batch job, Scheduler repair, cancellation and verified results.

**Blocked by:** [14](14-apply-google-cloud-foundation.md) and [20](20-deployment-and-build-source.md), plus explicit approval of the specific service/IAM/workload plan and spend.

**Status:** ready-for-human

**Owner:** Unclaimed

**Progress:** blocked

## Implementation steps

1. Apply the reviewed service configuration and deploy immutable image digests.
2. Exercise the real surface: authorized teammate submits, unauthorized user is denied, a viewer is read-only, duplicate submissions converge on one run.
3. Run one synthetic Batch job end to end; force a lost enqueue and let the reconciler repair it; cancel a run and reconcile the outcome.
4. Record observed resource inventory, billed categories and cleanup status.

## Acceptance criteria

- [ ] Authorized submission returns `202` and reaches a verified terminal state through one admitted job.
- [ ] Denied user, insufficient role and duplicate task delivery produce the documented outcomes on the deployed surface.
- [ ] Stream/action logic is exercised against real Batch, not only fakes, for enqueue repair, cancel and deadline handling.
- [ ] No organizer data, model weights or private traces are used; synthetic only.
- [ ] Cost and resource inventory are recorded; budget alerts are not described as hard caps.

## Verification

No implementation verification yet. Synthesis-only evidence does not prove model execution or offline competition readiness.
