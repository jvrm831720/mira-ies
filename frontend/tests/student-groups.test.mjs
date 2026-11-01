import assert from "node:assert/strict";
import test from "node:test";
import {
  cursorErrorKind,
  hasCursorContinuation,
  signalStatusPresentation,
} from "../src/lib/student-groups.mjs";

test("TRUE is presented as a confirmed signal", () => {
  assert.equal(signalStatusPresentation("TRUE").label, "Confirmado");
  assert.equal(signalStatusPresentation("TRUE").tone, "success");
});

test("FALSE is presented as not confirmed", () => {
  assert.equal(signalStatusPresentation("FALSE").label, "Não confirmado");
  assert.equal(signalStatusPresentation("FALSE").tone, "muted");
});

test("INDETERMINATE is presented as insufficient data", () => {
  assert.equal(signalStatusPresentation("INDETERMINATE").label, "Dados insuficientes");
  assert.equal(signalStatusPresentation("INDETERMINATE").tone, "warning");
});

test("HTTP 400 and 410 produce different cursor recovery states", () => {
  assert.equal(cursorErrorKind(400), "invalid");
  assert.equal(cursorErrorKind(410), "expired");
  assert.equal(cursorErrorKind(401), null);
  assert.equal(cursorErrorKind(403), null);
});

test("pagination follows only a cursor returned by the API", () => {
  assert.equal(hasCursorContinuation({ next_cursor: "opaque-token" }), true);
  assert.equal(hasCursorContinuation({ next_cursor: null }), false);
  assert.equal(hasCursorContinuation({}), false);
  assert.equal(hasCursorContinuation(null), false);
});

test("truncated pages continue only when API returns a cursor", () => {
  assert.equal(
    hasCursorContinuation({
      count: 0,
      has_more: null,
      truncated: true,
      next_cursor: "signed-checkpoint",
    }),
    true
  );
});

test("pagination ends when next_cursor is absent", () => {
  assert.equal(
    hasCursorContinuation({
      count: 3,
      has_more: false,
      truncated: false,
      next_cursor: null,
    }),
    false
  );
});
