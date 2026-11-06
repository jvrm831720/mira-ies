import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";

const flow = readFileSync(new URL("../src/components/onboarding/conversational-onboarding.tsx", import.meta.url), "utf8");
const overview = readFileSync(new URL("../src/components/onboarding/onboarding-pro-overview.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");

test("workspace provisioning displays MIRA Pro introduction rather than trial placeholder", () => {
  assert.match(flow, /step === "provision"[\s\S]*?<OnboardingProOverview/);
  assert.match(flow, /Criar meu workspace/);
  assert.doesNotMatch(flow, /Sobre os 7 dias de Pro|A oferta de boas-vindas|Nenhum trial ou cobrança será ativado/);
  assert.match(overview, /MIRA <strong>Pro<\/strong>/);
  assert.match(overview, /O que você encontra no Pro/);
  assert.match(overview, /A disponibilidade|Os recursos disponíveis dependem do plano habilitado/);
  assert.doesNotMatch(overview, /gratuito|teste grátis|ativado automaticamente|7 dias/);
});

test("premium benefits cover prediction, student context, interventions, work and measurement", () => {
  const names = ["Antecipe riscos", "Entenda cada aluno", "Transforme análise em ação", "Coordene sua equipe", "Acompanhe o impacto"];
  for (const name of names) assert.ok(overview.includes(name), "Missing capability: " + name);
  assert.match(overview, /aria-labelledby="mira-pro-title"/);
  assert.match(overview, /Conectar na próxima etapa/);
  assert.match(css, /\.mira-flow-pro-showcase\s*\{/);
  assert.match(css, /@media \(max-width: 400px\)/);
});
