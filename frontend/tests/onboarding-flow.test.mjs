import test from "node:test";
import assert from "node:assert/strict";
import { corporateDomain, maskCnpj, isValidCnpj, publicCompanyDescription, plausiblePublicWebsite } from "../src/lib/onboarding-flow.mjs";

test("corporate domain discovery excludes personal email providers", () => {
  assert.equal(corporateDomain("person@gmail.com"), null);
  assert.equal(corporateDomain("person@outlook.com"), null);
  assert.equal(corporateDomain("person@ddm.adv.br"), "ddm.adv.br");
  assert.equal(corporateDomain("bad-email"), null);
  assert.equal(corporateDomain("person@company.test"), null);
});

test("CNPJ mask and check digits are validated before public consultation", () => {
  assert.equal(maskCnpj("11222333000181"), "11.222.333/0001-81");
  assert.ok(isValidCnpj("11.222.333/0001-81"));
  assert.equal(isValidCnpj("11.222.333/0001-82"), false);
  assert.equal(isValidCnpj("11111111111111"), false);
});

test("company description is only derived from retrieved public data", () => {
  assert.equal(publicCompanyDescription(null), "");
  assert.equal(publicCompanyDescription({company:{primary_activity:"Educação"}}), "Educação");
  assert.equal(publicCompanyDescription({website:{description:"Serviços de cobrança"}}), "Serviços de cobrança");
});

test("website discovery starts only after a plausible public address is entered", () => {
  assert.equal(plausiblePublicWebsite(""), false);
  assert.equal(plausiblePublicWebsite("https://"), false);
  assert.equal(plausiblePublicWebsite("cruzeirodosul.edu.br"), true);
  assert.equal(plausiblePublicWebsite("https://www.cruzeirodosul.edu.br/"), true);
  assert.equal(plausiblePublicWebsite("http://localhost"), false);
  assert.equal(plausiblePublicWebsite("example.test"), false);
  assert.equal(plausiblePublicWebsite("https://example.com@127.0.0.1"), false);
});

