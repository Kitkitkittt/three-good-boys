// Client for the private API (services/lifemate_api, plan §4). Server-side only.
// Every call forwards the signed IAP assertion header it received plus a service
// ID token, and nothing else: no request/response body or header is logged here.
import type {
  ExperimentCreateRequest,
  ExperimentInstance,
  Me,
  ModelsResponse,
  RunDetail,
  RunMeta,
  RunRequest,
  RunsResponse,
} from "./types.ts";

export const IAP_ASSERTION_HEADER = "x-goog-iap-jwt-assertion";
export const IDEMPOTENCY_HEADER = "idempotency-key";

/** Injectable for tests; mirrors the parts of `fetch` this client uses. */
export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface ApiClientOptions {
  /** Private API base URL, e.g. https://lifemate-api-xxxx.run.app */
  baseUrl: string;
  /** Forwarded signed IAP assertion. Never rendered. */
  iapAssertion: string;
  /** Google service ID token for Cloud Run IAM. Always server-side. */
  serviceIdToken: string;
  fetch: FetchLike;
}

export interface ApiResult<T> {
  ok: boolean;
  status: number;
  data: T | null;
  /** Safe, non-payload error category for rendering. */
  error: string | null;
}

export interface ApiClient {
  getMe(): Promise<ApiResult<Me>>;
  getModels(): Promise<ApiResult<ModelsResponse>>;
  listRuns(): Promise<ApiResult<RunMeta[]>>;
  getRun(runId: string): Promise<ApiResult<RunDetail>>;
  submitRun(
    experimentId: string,
    request: RunRequest,
    idempotencyKey: string,
  ): Promise<ApiResult<RunMeta>>;
  createExperiment(
    request: ExperimentCreateRequest,
    idempotencyKey: string,
  ): Promise<ApiResult<ExperimentInstance>>;
  cancelRun(runId: string): Promise<ApiResult<RunMeta>>;
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const baseUrl = options.baseUrl.replace(/\/+$/, "");

  async function call<T>(
    path: string,
    init: { method?: string; body?: string; idempotencyKey?: string } = {},
  ): Promise<ApiResult<T>> {
    const headers: Record<string, string> = {
      authorization: `Bearer ${options.serviceIdToken}`,
      [IAP_ASSERTION_HEADER]: options.iapAssertion,
      "content-type": "application/json",
    };
    if (init.idempotencyKey) headers[IDEMPOTENCY_HEADER] = init.idempotencyKey;

    let response: Response;
    try {
      response = await options.fetch(`${baseUrl}${path}`, {
        method: init.method ?? "GET",
        body: init.body,
        cache: "no-store",
        headers,
      });
    } catch {
      // Network errors can embed URLs; surface the category only.
      return { ok: false, status: 0, data: null, error: "network_error" };
    }

    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        data: null,
        error: extractErrorCode(body) ?? defaultErrorFor(response.status),
      };
    }
    return { ok: true, status: response.status, data: body as T, error: null };
  }

  return {
    getMe: () => call<Me>("/api/me"),
    getModels: () => call<ModelsResponse>("/api/models"),
    listRuns: async () => {
      const result = await call<RunsResponse>("/api/runs");
      return { ...result, data: result.data?.runs ?? null };
    },
    getRun: (runId) => call<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`),
    submitRun: (experimentId, request, idempotencyKey) =>
      call<RunMeta>(`/api/experiments/${encodeURIComponent(experimentId)}/runs`, {
        method: "POST",
        body: JSON.stringify(request),
        idempotencyKey,
      }),
    createExperiment: (request, idempotencyKey) =>
      call<ExperimentInstance>("/api/experiments", {
        method: "POST",
        body: JSON.stringify(request),
        idempotencyKey,
      }),
    cancelRun: (runId) =>
      call<RunMeta>(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" }),
  };
}

const ERROR_CODE_PATTERN = /^[a-z0-9_]{1,64}$/;

function extractErrorCode(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  if ("code" in body && typeof body.code === "string" && ERROR_CODE_PATTERN.test(body.code)) {
    return body.code;
  }
  if ("detail" in body && typeof body.detail === "string" && ERROR_CODE_PATTERN.test(body.detail)) {
    return body.detail;
  }
  return null;
}

function defaultErrorFor(status: number): string {
  if (status === 401) return "unauthenticated";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  return "api_error";
}
