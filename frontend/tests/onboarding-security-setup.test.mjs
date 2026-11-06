import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";

const setup = fs.readFileSync(new URL("../src/components/onboarding/onboarding-security-setup.tsx", import.meta.url), "utf8");
const flow = fs.readFileSync(new URL("../src/components/onboarding/conversational-onboarding.tsx", import.meta.url), "utf8");
const styles = fs.readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");

test("guided MFA enrollment displays instructional steps and the API-issued QR code", () => {
  for (const step of ["Abra um aplicativo autenticador", "Escaneie o QR Code", "Digite o código gerado"]) {
    assert.ok(setup.includes(step), "Missing MFA step: " + step);
  }
  assert.match(setup, /src=\{enrollment\.qr_code\}/);
  assert.doesNotMatch(setup, /cdn\.21st\.dev|http:\/\/|https:\/\//);
  assert.match(setup, /aria-expanded=\{showManual\}/);
  assert.match(setup, /\{showManual && \(/);
  assert.match(setup, /navigator\.clipboard\.writeText\(enrollment\.secret\)/);
  assert.match(setup, /Não o compartilhe/);
});

test("six visual slots use one accessible, paste-friendly native TOTP input", () => {
  assert.match(setup, /Array\.from\(\{ length: 6 \}/);
  assert.match(setup, /inputMode="numeric"/);
  assert.match(setup, /autoComplete="one-time-code"/);
  assert.match(setup, /maxLength=\{6\}/);
  assert.match(setup, /onChange=\{event => onCodeChange\(event\.target\.value\.replace/);
  assert.match(setup, /type="submit" disabled=\{!canConfirm\}/);
  assert.match(setup, /aria-describedby=\{id \+ "-help"\}/);
  assert.match(styles, /\.mira-flow-otp-control:focus-within/);
});

test("MFA redesign keeps the original authenticated backend enrollment and verification", () => {
  assert.match(flow, /<OnboardingSecuritySetup/);
  assert.match(flow, /onConfirm=\{confirmMfa\}/);
  assert.match(flow, /api\.confirmRequiredMfaEnrollment\(mfaTicket, mfaCode\)/);
  assert.match(flow, /api\.verifyMfaLogin\(mfaTicket, mfaCode\)/);
  assert.match(flow, /setAccessToken\(result\.access_token\)/);
  assert.match(flow, /setRecoveryCodes\(result\.recovery_codes\)/);
  assert.doesNotMatch(flow, /className="mira-flow-mfa-setup"/);
});
