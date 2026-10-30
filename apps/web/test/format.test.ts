import assert from "node:assert/strict";
import { test } from "node:test";
import {
  attemptPhaseLabel,
  describeCancellation,
  formatBytes,
  formatTimestamp,
  isAppRole,
  isRunState,
  isTerminal,
  runTitle,
  shortHash,
  stateBadge,
} from "../src/lib/format.ts";

test("isRunState accepts the contract states and rejects others", () => {
  assert.equal(isRunState("ACTIVE"), true);
  assert.equal(isRunState("PENDING"), false);
  assert.equal(isRunState("active"), false);
});

test("isAppRole covers the four domain roles", () => {
  for (const role of ["owner", "maintainer", "researcher", "viewer"]) {
    assert.equal(isAppRole(role), true);
  }
  assert.equal(isAppRole("admin"), false);
});

test("terminal states are exactly succeeded/failed/canceled", () => {
  assert.equal(isTerminal("QUEUED"), false);
  assert.equal(isTerminal("SUBMITTING"), false);
  assert.equal(isTerminal("ACTIVE"), false);
  assert.equal(isTerminal("SUCCEEDED"), true);
  assert.equal(isTerminal("FAILED"), true);
  assert.equal(isTerminal("CANCELED"), true);
});

test("attempt labels mark terminal states distinctly", () => {
  assert.equal(attemptPhaseLabel("ACTIVE"), "ACTIVE");
  assert.equal(attemptPhaseLabel("FAILED"), "terminal: FAILED");
  assert.equal(stateBadge("SUBMITTING"), "submitting");
});

test("cancellation intent is not terminal cancellation", () => {
  assert.equal(describeCancellation("ACTIVE", false), "no cancellation requested");
  assert.equal(describeCancellation("CANCELED", true), "canceled");
  assert.match(describeCancellation("ACTIVE", true), /not yet terminal/);
  assert.match(describeCancellation("SUCCEEDED", true), /already SUCCEEDED/);
});

test("formatTimestamp is stable and handles null/invalid", () => {
  assert.equal(formatTimestamp(null), "—");
  assert.equal(formatTimestamp("not-a-date"), "invalid date");
  assert.equal(formatTimestamp("2026-10-30T12:34:56.000Z"), "2026-10-30 12:34:56Z");
});

test("formatBytes scales and reports unknown", () => {
  assert.equal(formatBytes(null), "unknown size");
  assert.equal(formatBytes(512), "512 B");
  assert.equal(formatBytes(2048), "2.0 KB");
  assert.equal(formatBytes(5 * 1024 * 1024), "5.0 MB");
});

test("shortHash truncates without losing short hashes", () => {
  assert.equal(shortHash("abc"), "abc");
  assert.equal(shortHash("0123456789abcdef", 8), "01234567");
});

test("runTitle joins the run id and owner", () => {
  assert.equal(runTitle({ run_id: "r1", owner: "a@example.com" }), "r1 · a@example.com");
  assert.equal(runTitle({ run_id: "r1", owner: "" }), "r1");
});
