import assert from "node:assert/strict";
import test from "node:test";
import { normalizeVerificationCode } from "../src/lib/verification-code.mjs";

test("email code accepts exactly six ASCII digits", () => {
  assert.equal(normalizeVerificationCode("123456"), "123456");
  assert.equal(normalizeVerificationCode("123456789"), "123456");
  assert.equal(normalizeVerificationCode(""), "");
});

test("OTP autofill and paste remove separators and non-numeric characters", () => {
  assert.equal(normalizeVerificationCode(" 123-456 "), "123456");
  assert.equal(normalizeVerificationCode("12 34 56"), "123456");
  assert.equal(normalizeVerificationCode("12a34b56"), "123456");
  assert.equal(normalizeVerificationCode("１２３４５６"), "");
});
