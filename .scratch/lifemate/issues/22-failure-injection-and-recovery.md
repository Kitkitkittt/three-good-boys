# 22: Failure injection and recovery qualification

**Parent spec:** [Shared Google Cloud platform #3](https://github.com/huyxdang/three-good-boys/issues/3).

**What to build:** Evidence that the orchestration fails closed: injected faults never produce a false success, duplicate spend or silently lost work, and real mid-sample interruption behaviour is either qualified or explicitly blocked.

**Blocked by:** [17](17-cloud-dispatch-reconciliation.md), [19](19-cloud-worker-adapter.md), [21](21-approved-deployment-slice.md). Real session interruption additionally needs organizer-approved semantics and authorized artifacts/GPU.

**Status:** ready-for-human

**Owner:** Unclaimed

**Progress:** blocked

## Implementation steps

1. Inject: crash after durable accept before enqueue, duplicate task, ambiguous Batch create, competing runs, lost reconciliation event, cancellation/create race, missing and conflicting chunk, Batch success with absent manifest, worker death during a sample.
2. Record the actual observed outcome and the state that remains held.
3. Separate synthetic orchestration recovery from real ToolEnv interruption; never present the former as the latter.

## Acceptance criteria

- [ ] Every injected fault produces a recorded, non-success outcome or a verified recovery; none becomes a false success.
- [ ] An ambiguous create or cancel keeps the GPU slot held and alerts.
- [ ] Conflicting or missing results fail closed.
- [ ] Real mid-sample interruption is either exercised under an organizer-approved mechanism or recorded as an explicit blocker with the requirement decision.

## Verification

No implementation verification yet.
