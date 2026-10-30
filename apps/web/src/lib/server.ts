// Server-only wiring: builds the API client from headers and environment.
// Never import this module from a client component.
import "server-only";
import { headers } from "next/headers";
import { createApiClient, IAP_ASSERTION_HEADER, type ApiClient } from "./api.ts";
import { createMetadataTokenProvider } from "./metadata-token.ts";

const metadataToken = createMetadataTokenProvider((input, init) => globalThis.fetch(input, init));

/** Placeholder assertion used only when IAP is not in front of the web tier. */
export const LOCAL_ASSERTION = "local-development-no-iap";

export async function apiClientFromRequest(): Promise<ApiClient> {
  const incoming = await headers();
  const baseUrl = process.env.LIFEMATE_API_URL;
  if (!baseUrl) throw new Error("LIFEMATE_API_URL is not configured");
  const localToken = process.env.LIFEMATE_API_ID_TOKEN;
  if (localToken && process.env.NODE_ENV === "production") {
    throw new Error("Static API ID tokens are not permitted in production");
  }
  const idToken = localToken ?? await metadataToken(process.env.LIFEMATE_API_AUDIENCE ?? "");
  return createApiClient({
    baseUrl,
    iapAssertion: incoming.get(IAP_ASSERTION_HEADER) ?? LOCAL_ASSERTION,
    serviceIdToken: idToken,
    fetch: globalThis.fetch,
  });
}
