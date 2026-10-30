# 18: Team dashboard

**Parent spec:** [Shared Google Cloud platform #3](https://github.com/huyxdang/three-good-boys/issues/3).

**What to build:** The Next.js team UI that authenticates teammates, submits experiment runs through the private API and shows run status, comparison and redacted failure summaries.

**Blocked by:** [15](15-cloud-run-contracts-and-domain.md). Deployment needs [14](14-apply-google-cloud-foundation.md), reviewed IAM and IAP configuration.

The API provides caller-scoped `GET /api/runs` for the run list and comparison; owner reads may span callers. Experiment/run creation remains bounded by the server's approved catalog.

**Status:** ready-for-agent

**Owner:** omp-impl-web

**Progress:** done

## Implementation steps

1. Build the smallest useful pages: run list, new run, run detail with status and artifact metadata.
2. Keep all model execution, GCP credentials and restricted payloads out of the browser; the web tier only calls the API.
3. Show the benchmark and configuration identity side by side so comparisons are explicit.

## Acceptance criteria

- [x] Source-level submit flow and queued/active/terminal rendering are exercised through injected real API-shaped responses; live deployed teammate access is explicitly out of scope for this source ticket and remains ticket 21's gate.
- [x] Denied-user responses and role limits are exercised in the client/UI policy; live IAP front-door enforcement remains deployment-gated in ticket 21, not claimed here.
- [x] No sample audio, transcript, label or trace content is rendered or logged.
- [x] Comparison view keys on benchmark and configuration identity.

## Verification

Implemented in `apps/web/` on branch `ticket/18-cloud-dashboard`. No deployment is claimed: nothing was built into an image, pushed to a registry, or run against a live API, IAP front end or GCP project. The client was written against the real route set and shapes in `services/lifemate_api/` (ticket 16) and exercised against injected `fetch` responses only.

Commands run on 2026-10-30, node v24.20.0, npm 11.19.0, in `apps/web/`:

- `npm test` → `ℹ tests 29`, `ℹ pass 29`, `ℹ fail 0` (`node --test "test/**/*.test.ts"`; Node strips TS types, so there is no test framework). Covers the API client (experiment path, method, `idempotency-key` header, IAP assertion and bearer headers, `no-store`, the three-field submit body, 401→`unauthenticated`, 403→`forbidden`, 409 conflict code, non-JSON body, network failure without leaking the URL), formatting/terminal-state helpers, comparison and selection, payload scrubbing, role limits against the shared policy, and idempotency-key validation.
- `npx tsc --noEmit` → exit 0.
- `npm run build` → exit 0; Next.js 16.4.3 (Turbopack) compiled, 2 static pages, dynamic routes `ƒ /`, `ƒ /compare`, `ƒ /runs/[id]`, `ƒ /runs/new`.

Scope as built:

- Pages: run list (`src/app/page.tsx`), new run (`runs/new`), run detail (`runs/[id]`), compare (`compare`). All server components; the only client JS is Next's runtime.
- `src/lib/api.ts` is a server-only client with injectable `fetch`. It forwards `x-goog-iap-jwt-assertion` and a service ID token, reads caller-scoped `GET /api/runs`, creates approved-template experiment instances via `POST /api/experiments` when offered, then submits via `POST /api/experiments/{id}/runs`. Detail and cancel retain the same API routes; no model executes and no GCP SDK or credential reaches the browser.
- Submission sends exactly the API's three client fields (`dataset_id`, `model_id`, `decoding`); mode, machine, region, timeout, retries and source/image pins are server policy and are never sent from the browser. The idempotency key is minted server-side with `crypto.randomUUID()` per form submission; the API owns conflict semantics.
- Run state renders as a badge; terminal states are also labelled `terminal: <STATE>`; cancellation intent (`cancel_requested`) is shown separately from the terminal `CANCELED` state. The cancel button appears only for roles whose policy grants it (`owner`, `maintainer`, `researcher` — matching `services/lifemate_cloud/roles.py`).
- Artifact metadata is limited to actual API-returned name, pinned generation, checksum and size. The server client preserves `artifacts` rather than dropping them; payload scrubbing still excludes audio/transcript/label/trace/prompt/gold/prediction/raw decoding/input objects.
- Role limits are visible for every visitor (`RolePanel`) and a `viewer` is refused in the UI, not only by the API.

Limits:

- Comparison keys on the API's actual immutable benchmark and configuration identities, displayed side by side. Status/owner differences do not establish comparability; missing identity is explicitly unknown, never treated as a same-benchmark guarantee. No task-score, WER, latency or cost metrics are invented when the API does not provide them.
- `GET /api/runs` is an additive ticket-16 route used by list/compare; configured experiment templates come from the API catalog. Benchmark authorship and artifact uploads remain owner-registered configuration, not browser creation privileges.
- Not verified against a live service: real responses, IAP assertion validation, denied-user behaviour at the front door, and role enforcement (ticket 16 owns the API). Header forwarding is pass-through only; there is no assertion parsing or auth implementation.
- Artifact metadata is supported; there is no artifact-content/download endpoint. The UI renders only the real metadata list and does not manufacture a URL or imply that content is downloadable. Live deployment/IAP/GCS behavior remains unverified.
- `npm install` reached the registry here; `node_modules/` and `.next/` stay untracked. Packages are `next`, `react`, `react-dom`, `server-only` and dev-only `typescript`/`@types*`; no UI framework.
- Benchmark content hash and case count are pinned when runs are accepted and included in comparison identity; old records without a pin report unknown. Configuration identity covers the complete immutable execution request (including source/image/input generations and runtime policy) via a digest, not a partial owner/status proxy. Artifact size remains unknown when the verified manifest does not supply it.
- Integration acceptance (2026-10-30): `npm test --prefix apps/web` passed `42` tests, `0` failures. `npm exec --prefix apps/web tsc -- --project apps/web/tsconfig.json --noEmit` exited 0 after removing an unused undeclared comparison field. Tests cover benchmark/configuration identity matching/mismatch/unknown values, real artifact metadata preservation, approved-template creation requests and authenticated API transport; no live browser/IAP deployment or artifact-content download is claimed.

