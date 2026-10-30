// Internal to server.ts. No environment reads; the server owns the token cache.
import type { FetchLike } from "./api.ts";

export function createMetadataTokenProvider(fetch: FetchLike, now = Date.now) {
  let cached: { audience: string; token: string; expires: number } | undefined;

  return async (audience: string): Promise<string> => {
    if (!audience) throw new Error("LIFEMATE_API_AUDIENCE is not configured");
    if (cached?.audience === audience && cached.expires > now() + 30_000) return cached.token;

    const url = new URL("http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity");
    url.searchParams.set("audience", audience);
    url.searchParams.set("format", "full");
    let response: Response;
    try {
      response = await fetch(url.toString(), {
        headers: { "Metadata-Flavor": "Google" },
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(5_000),
      });
    } catch {
      throw new Error("Service identity metadata is unavailable");
    }
    if (!response.ok || response.headers.get("Metadata-Flavor") !== "Google") {
      throw new Error("Service identity metadata request failed");
    }
    const token = (await response.text()).trim();
    let claims: { aud?: unknown; exp?: unknown };
    try {
      const parts = token.split(".");
      if (parts.length !== 3) throw new Error();
      claims = JSON.parse(Buffer.from(parts[1], "base64url").toString("utf8"));
      if (!claims || typeof claims !== "object") throw new Error();
    } catch {
      throw new Error("Service identity metadata returned an invalid token");
    }
    // The trusted metadata endpoint supplies the token; the private API verifies
    // its signature. Decode expiry only to avoid caching beyond its lifetime.
    if (claims.aud !== audience || typeof claims.exp !== "number" ||
        !Number.isSafeInteger(claims.exp) || claims.exp * 1_000 <= now()) {
      throw new Error("Service identity token has an invalid audience or expiry");
    }
    cached = { audience, token, expires: claims.exp * 1_000 };
    return token;
  };
}
