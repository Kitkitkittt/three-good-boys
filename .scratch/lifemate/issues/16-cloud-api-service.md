# 16: Private cloud API service

**Parent spec:** [Shared Google Cloud platform #3](https://github.com/huyxdang/three-good-boys/issues/3).

**What to build:** A FastAPI service that authenticates the signed IAP identity, authorizes application roles, accepts immutable run requests and exposes run status to the web service.

**Blocked by:** [15](15-cloud-run-contracts-and-domain.md). Deployment needs [14](14-apply-google-cloud-foundation.md) and reviewed IAM.

**Status:** ready-for-agent

**Owner:** omp-impl-api

**Progress:** done

## Implementation steps

1. Implement the endpoints from [implementation plan §4](../../../docs/google-cloud-implementation-plan.md#4-minimum-api-and-job-contracts) over the shared domain library.
2. Verify the forwarded signed IAP assertion (issuer, audience, expiry, signature) rather than trusting an email header; map the identity to an app role.
3. Return `202` for durable acceptance and enqueue outside the transaction; leave dispatch repair to the reconciler.
4. Keep machine routes out of this service: dispatch and reconciliation belong to the separate machine service.

## Acceptance criteria

- [x] Unauthenticated, unsigned-header and wrong-audience requests are rejected.
- [x] Viewer cannot submit; the shared role policy denies approved-artifact management to researcher and grants it to owner/maintainer. An artifact-management HTTP workflow is explicitly out of scope: approved artifacts remain owner-registered deployment configuration.
- [x] Same idempotency key returns the existing run; different request conflicts.
- [x] No arbitrary image, tier, region or URI is accepted from the client.
- [x] Status reads expose only approved metadata, never restricted inputs or traces.

## Verification
Environment: Linux x64 CPU host, Python 3.14.4, FastAPI 0.118.0 / Starlette 0.50.0, PyJWT 2.10.1. No Google client, credentials or network calls: Firestore and Cloud Tasks adapters are injected and imported lazily; tests drive the real ASGI app through an in-process harness (`services/asgi_client.py`) because `httpx`/`TestClient` is not installed offline.
Command:
```
cd .worktrees/ticket-16-cloud-api && python3 -m unittest discover -s services -p 'test_*.py' -v
```
Result after the integration merge: `Ran 155 tests ... OK` (exit 0), covering tickets 15–19; 76 are this ticket's API/auth/catalog/acceptance/asgi tests.
Historical coverage: unsigned/missing assertion, wrong audience/issuer and expired assertions are rejected; viewers cannot submit/cancel; accepted run/request/coverage/enqueue intent commit atomically; lost enqueue leaves `PENDING` while returning 202; machine routes stay 404. Integration repair adds authenticated, allowlist-bound idempotent experiment creation, pins benchmark content identity/case count at run acceptance, returns a digest of the complete immutable request configuration, and exposes only verified persisted artifact metadata on run detail. No raw decoding, input object identities or traces are returned.
Limits: no real IAP JWKS fetch, Firestore emulator or Cloud Tasks call was exercised; the Firestore adapter's transaction callback runs only against an injected fake. No deployment evidence.
Evidence: `services/lifemate_api/` (`auth`, `catalog`, `acceptance`, `store`, `tasks`, `views`, `app`, `server`) and tests `services/test_iap.py`, `test_catalog.py`, `test_api.py`, `test_acceptance.py`, `services/asgi_client.py`.

## Comments
- Machine routes stay out of this service by design; dispatch/reconcile belong to ticket 17.
- `GET /api/runs` (list, scoped to the caller except owner) is an additive read the dashboard (ticket 18) requires; it is not in the plan's §4 list but returns only `RunMeta`.
- Acceptance persists the canonical request, `experiment_id`, `expected_names` (result coverage) and `accepted_at`/`deadline_seconds` so ticket 17 reads pinned server data, never a caller payload. Repository read surface: `get_run`, `get_request`, `get_intent`, `all_intents`, `get_expected_names`, `experiment_id`, `accepted_at`, `deadline_seconds`.
- Creation stores real experiment instances and user-scoped idempotency records atomically. `POST /api/experiments` accepts only approved `template_id`, `dataset_id`, `model_id` and optional `label`; it does not author benchmarks or approve artifacts. Created-instance runs pin their selected dataset/model; configured template IDs remain supported for existing callers.
- Artifact metadata is persisted by dispatcher finalization only after exact coverage and object verification, then read through API `put_artifacts`/`get_artifacts` adapters. Detail returns name, pinned generation, checksum and optional size; no content/download route exists. Benchmark hash/case count are pinned on acceptance so later catalog changes do not rewrite past run identity; pre-change records without that metadata report unknown.
- Acceptance audit: artifact-management authorization is a shared role-policy contract only (`test_roles.py` explicitly denies researcher management/approval); there is no claimed artifact-management HTTP workflow. Experiment instance list/read and benchmark-authoring endpoints are not in this ticket's minimum route contract.
- Integration acceptance (2026-10-30): `python3 -m unittest discover -s services -p 'test_*.py' -v` passed `Ran 226 tests ... OK`. This includes authenticated experiment creation/validation, user-scoped idempotent replay/conflict and concurrent creation winner, pinned benchmark/configuration identity (including replay after a catalog edit), real API-store/dispatcher lifecycle and verified-artifact metadata reads. Integration failures (an omitted header constant/model ID, an accidental catalog return-type change and a new hash assertion) were corrected without removing the original acceptance expectations. No live Google service was exercised.
