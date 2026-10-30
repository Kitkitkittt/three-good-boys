// Client-generated idempotency key (plan §4: user-scoped). The web tier mints one
// per form submission, outside the browser, and sends it as `Idempotency-Key`;
// the API owns same-key/same-request and conflict semantics.
const KEY_PATTERN = /^[A-Za-z0-9_-]{16,128}$/;

export function newIdempotencyKey(randomUuid: () => string = () => crypto.randomUUID()): string {
  return randomUuid();
}

export function isValidIdempotencyKey(value: string | undefined | null): value is string {
  return !!value && KEY_PATTERN.test(value);
}
