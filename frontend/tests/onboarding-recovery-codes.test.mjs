import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";

const component = readFileSync(
  new URL("../src/components/onboarding/onboarding-recovery-codes.tsx", import.meta.url), "utf8",
);
const flow = readFileSync(
  new URL("../src/components/onboarding/conversational-onboarding.tsx", import.meta.url), "utf8",
);
const styles = readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");

test("recovery codes are numbered, selectable and displayed in a dedicated panel", () => {
  assert.match(component, /<ol className="mira-flow-recovery-codes"/);
  assert.match(component, /codes\.map\(\(code, index\)/);
  assert.match(component, /String\(index \+ 1\)\.padStart\(2, "0"\)/);
  assert.match(component, /<code>\{code\}<\/code>/);
  assert.match(styles, /\.mira-flow-recovery-codes\s*\{/);
  assert.match(styles, /\.mira-flow-recovery-code code/);
});

test("copy is inside codes card; continuation is a separate primary action requiring acknowledgment", () => {
  const cardStart = component.indexOf('<section className="mira-flow-recovery-panel"');
  const footerStart = component.indexOf('<div className="mira-flow-recovery-footer"');
  assert.ok(cardStart >= 0 && footerStart > cardStart);
  const card = component.slice(cardStart, footerStart);
  const footer = component.slice(footerStart);
  assert.match(card, /mira-flow-recovery-copy/);
  assert.match(card, /navigator\.clipboard\.writeText\(codes\.join\("\\n"\)\)/);
  assert.doesNotMatch(card, /mira-flow-recovery-continue/);
  assert.match(footer, /type="checkbox"/);
  assert.match(footer, /checked=\{acknowledged\}/);
  assert.match(footer, /disabled=\{!acknowledged\}/);
  assert.match(footer, /Continuar para as integrações/);
  assert.match(component, /aria-live="polite"/);
});

test("recovery codes stay in memory and existing onboarding continuation is preserved", () => {
  assert.match(flow, /<OnboardingRecoveryCodes/);
  assert.match(flow, /codes=\{recoveryCodes\}/);
  assert.match(flow, /setRecoveryCodes\(null\)/);
  assert.match(flow, /setSecurityStep\(null\)/);
  assert.match(flow, /setStep\("integrations"\)/);
  assert.doesNotMatch(component, /localStorage|sessionStorage|fetch\(|console\.log/);
});
