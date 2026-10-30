import assert from "node:assert/strict";
import { test } from "node:test";
import { createMetadataTokenProvider } from "../src/lib/metadata-token.ts";

function token(audience: string, expires: number): string {
  return `header.${Buffer.from(JSON.stringify({ aud: audience, exp: expires })).toString("base64url")}.signature`;
}

function metadata(value: string, status = 200): Response {
  return new Response(value, { status, headers: { "Metadata-Flavor": "Google" } });
}

test("metadata ID tokens use the selected audience and refresh before expiry", async () => {
  let now = 1_000_000;
  const calls: Array<{ url: string; init: RequestInit | undefined }> = [];
  const provider = createMetadataTokenProvider(async (url, init) => {
    calls.push({ url, init });
    return metadata(token(new URL(url).searchParams.get("audience")!, now / 1_000 + 100));
  }, () => now);
  const first = await provider("https://api.example.test");
  assert.equal(await provider("https://api.example.test"), first);
  assert.equal(calls.length, 1);
  const url = new URL(calls[0].url);
  assert.equal(url.hostname, "metadata.google.internal");
  assert.equal(url.searchParams.get("audience"), "https://api.example.test");
  assert.equal(url.searchParams.get("format"), "full");
  assert.deepEqual(calls[0].init?.headers, { "Metadata-Flavor": "Google" });
  assert.equal(calls[0].init?.cache, "no-store");
  assert.equal(calls[0].init?.redirect, "error");
  now += 71_000;
  assert.notEqual(await provider("https://api.example.test"), first);
  assert.equal(calls.length, 2);
  await provider("https://other-api.example.test");
  assert.equal(calls.length, 3);
});

test("metadata rejects missing audience, unavailable responses and invalid tokens", async () => {
  const audience = "https://api.example.test";
  const provider = createMetadataTokenProvider(async () => metadata(token(audience, 2_000)), () => 1_000_000);
  await assert.rejects(provider(""), /AUDIENCE/);
  for (const value of ["bad-token", token("other", 2_000), token(audience, 999)]) {
    const invalid = createMetadataTokenProvider(async () => metadata(value), () => 1_000_000);
    await assert.rejects(invalid(audience), /invalid/);
  }
  const denied = createMetadataTokenProvider(async () => metadata("do not leak this", 403));
  await assert.rejects(denied(audience), /^Error: Service identity metadata request failed$/);
  const untrusted = createMetadataTokenProvider(async () => new Response(token(audience, 2_000)));
  await assert.rejects(untrusted(audience), /request failed/);
  const unreachable = createMetadataTokenProvider(async () => { throw new Error("private URL"); });
  await assert.rejects(unreachable(audience), /^Error: Service identity metadata is unavailable$/);
});
