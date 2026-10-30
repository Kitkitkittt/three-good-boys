import assert from "node:assert/strict";
import { test } from "node:test";
import { isValidIdempotencyKey, newIdempotencyKey } from "../src/lib/idempotency.ts";
import { ROLE_LIMITS, roleLimits } from "../src/lib/roles.ts";

test("idempotency keys are generated from the injected source", () => {
  assert.equal(newIdempotencyKey(() => "fixed-key-0123456789"), "fixed-key-0123456789");
  assert.equal(isValidIdempotencyKey(newIdempotencyKey()), true);
});

test("idempotency key validation rejects missing, short and unsafe values", () => {
  assert.equal(isValidIdempotencyKey(null), false);
  assert.equal(isValidIdempotencyKey(""), false);
  assert.equal(isValidIdempotencyKey("short"), false);
  assert.equal(isValidIdempotencyKey("has spaces in the key value"), false);
  assert.equal(isValidIdempotencyKey("a".repeat(129)), false);
  assert.equal(isValidIdempotencyKey("550e8400-e29b-41d4-a716-446655440000"), true);
});

// Mirrors services/lifemate_cloud/roles.py::_PERMISSIONS. If the shared policy
// changes, this table and src/lib/roles.ts must change with it.
test("role limits match the shared API permissions", () => {
  assert.deepEqual(Object.keys(ROLE_LIMITS).sort(), [
    "maintainer",
    "owner",
    "researcher",
    "viewer",
  ]);
  assert.deepEqual(
    {
      submit: ROLE_LIMITS.viewer.canSubmit,
      cancel: ROLE_LIMITS.viewer.canCancel,
    },
    { submit: false, cancel: false },
  );
  // Researcher may submit and cancel, but not approve artifacts or cost policy.
  assert.deepEqual(
    {
      submit: ROLE_LIMITS.researcher.canSubmit,
      cancel: ROLE_LIMITS.researcher.canCancel,
      approve: ROLE_LIMITS.researcher.canApprove,
      cost: ROLE_LIMITS.researcher.canSetCostPolicy,
    },
    { submit: true, cancel: true, approve: false, cost: false },
  );
  assert.equal(ROLE_LIMITS.maintainer.canApprove, true);
  assert.equal(ROLE_LIMITS.maintainer.canSetCostPolicy, false);
  assert.equal(ROLE_LIMITS.owner.canSetCostPolicy, true);
  assert.equal(roleLimits("viewer").label, "Viewer");
});
