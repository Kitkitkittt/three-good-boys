# 14: Apply and verify the reviewed cloud foundation

**Parent spec:** [Shared Google Cloud platform #3](https://github.com/huyxdang/three-good-boys/issues/3).

**What to build:** Apply the exact reviewed bootstrap/dev Terraform plans and verify remote state, private storage, registry, Firestore, queue and identities in the approved project.

**Blocked by:** Explicit owner approval of the real resource/IAM plan and cost categories. [13: Reviewed foundation plan](13-google-cloud-foundation-plan.md) is done.

**Status:** ready-for-human

**Owner:** Unclaimed

**Progress:** blocked

## Acceptance criteria

- [ ] Owner approves the named project/region, persisted resource/IAM changes, retention/cleanup and permitted spend after reading the real plan.
- [ ] Apply state bootstrap, migrate its state into the reviewed remote backend, then apply canonical dev without destroying or replacing existing resources; do not use reconfiguration as a substitute for state migration.
- [ ] Verify bucket privacy/region/versioning, registry, regional Firestore, dispatch queue limits and least-privilege identity bindings.
- [ ] Re-plan the unchanged configuration and observe no drift; verify state access and no secret/plan publication.
- [ ] Record actual recurring-cost inventory and rollback/cleanup instructions. Do not claim budget alerts are hard caps.

## Verification

Ticket 13 completed Cloud Shell validation and real read-only plans: one bootstrap addition; 13 dev additions and 18 no-op imports; no updates or deletions. Owner approval of the exact fresh plans, retention and permitted spend is still absent. No persistent resource/IAM apply is authorized by the API enablement or GPU quota change alone.

## Comments

Dashboard, dispatcher and real GPU evaluation follow this foundation and their own contracts/tickets. No placeholder application deployment or synthetic success is acceptable.
