"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft, ArrowRight, Building2, Check, CheckCircle2,
  Database, GraduationCap, LockKeyhole, ShieldCheck, UploadCloud,
} from "@/components/ui/icons";
import { api } from "@/lib/api";
import { getAccessToken, setAccessToken } from "@/lib/auth";
import { OnboardingIntegrationSetup } from "./onboarding-integration-setup";
import { completeOrganizationOnboarding, enrichOnboarding, type OnboardingEnrichment } from "@/lib/onboarding-api";
import { corporateDomain, isValidCnpj, maskCnpj, publicCompanyDescription, plausiblePublicWebsite } from "@/lib/onboarding-flow.mjs";

type Step = "workspace" | "description" | "name" | "provision" | "integrations";
type SecurityStep = "enroll" | "verify" | null;
type FormData = {
  organizationName: string;
  tradeName: string;
  cnpj: string;
  website: string;
  description: string;
  firstName: string;
  lastName: string;
  dataSources: string[];
};
const EMPTY: FormData = {
  organizationName: "", tradeName: "", cnpj: "", website: "",
  description: "", firstName: "", lastName: "", dataSources: [],
};
const STEPS: Step[] = ["workspace", "description", "name", "provision", "integrations"];


function InputField({ id, label, children, note }: {
  id: string; label: string; children: React.ReactNode; note?: string;
}) {
  return (
    <div className="mira-flow-field">
      <label htmlFor={id}>{label}</label>
      {children}
      {note && <p className="mira-flow-note">{note}</p>}
    </div>
  );
}

function SearchingOrb() {
  const dots = Array.from({ length: 32 }, (_, index) => {
    const y = 1 - 2 * ((index + 0.5) / 32);
    const r = Math.sqrt(1 - y * y);
    const angle = index * Math.PI * (3 - Math.sqrt(5));
    return { x: 18 + r * Math.cos(angle) * 14, y: 18 + y * 14, opacity: 0.3 + 0.7 * ((r * Math.sin(angle) + 1) / 2) };
  });
  return <svg className="mira-flow-thinking-orb" viewBox="0 0 36 36" width="36" height="36" aria-hidden="true">
    <g>{dots.map((dot, i) => <circle key={i} cx={dot.x} cy={dot.y} r={0.7} fill="currentColor" opacity={dot.opacity} />)}</g>
  </svg>;
}
function TypingText({ text }: { text: string }) {
  const [visible, setVisible] = useState("");
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setVisible(text); return;
    }
    setVisible("");
    let at = 0;
    const timer = window.setInterval(() => { at += 1; setVisible(text.slice(0, at)); if (at >= text.length) window.clearInterval(timer); }, 34);
    return () => window.clearInterval(timer);
  }, [text]);
  return <><span aria-hidden="true">{visible}<span className="mira-flow-type-caret" /></span><span className="sr-only">{text}</span></>;
}

export function ConversationalOnboarding() {
  const router = useRouter();
  const params = useSearchParams();
  const email = (params.get("email") || "").trim().toLowerCase();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [token, setToken] = useState("");
  const [connectedPhase, setConnectedPhase] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [step, setStep] = useState<Step>("workspace");
  const [form, setForm] = useState<FormData>(EMPTY);
  const [enrichment, setEnrichment] = useState<OnboardingEnrichment | null>(null);
  const [siteRevealed, setSiteRevealed] = useState(false);
  const [siteStatus, setSiteStatus] = useState<"idle" | "searching" | "done" | "error" | "manual">("idle");
  const [logoDataUrl, setLogoDataUrl] = useState("");
  const lookupSequence = useRef(0);
  const lastCnpjLookup = useRef("");
  const cnpjLookupSequence = useRef(0);
  const [searchWarning, setSearchWarning] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [logoPreview, setLogoPreview] = useState("");
  const [securityStep, setSecurityStep] = useState<SecurityStep>(null);
  const [mfaTicket, setMfaTicket] = useState("");
  const [enrollment, setEnrollment] = useState<{ secret: string; qr_code: string } | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);

  const domain = corporateDomain(email);
  const previewName = form.tradeName.trim() || form.organizationName.trim() || "Seu workspace";
  const currentIndex = Math.max(0, STEPS.indexOf(step));
  const draftKey = "mira_onboarding_draft_v3:" + email;

  useEffect(() => {
    if (!email) { setInitialized(true); return; }
    // Restore the workspace preview even when MFA enrollment is resumed after a refresh.
    const saved = window.sessionStorage.getItem("mira_onboarding_draft_v3:" + email);
    if (saved) {
      try {
        const draft = JSON.parse(saved) as { step?: Step | "trial"; form?: Partial<FormData>; siteRevealed?: boolean };
        if (draft.form) setForm({ ...EMPTY, ...draft.form });
        const recoveredStep = draft.step === "trial" ? "provision" : draft.step;
        if (recoveredStep && STEPS.includes(recoveredStep)) setStep(recoveredStep);
        if (draft.siteRevealed) { setSiteRevealed(true); setSiteStatus("manual"); }
      } catch { window.sessionStorage.removeItem("mira_onboarding_draft_v3:" + email); }
    }
    const pendingMfa = window.sessionStorage.getItem("mira_onboarding_pending_mfa:" + email);
    if (pendingMfa) {
      try {
        const pending = JSON.parse(pendingMfa) as { mode: SecurityStep; ticket: string };
        if ((pending.mode === "verify" || pending.mode === "enroll") && pending.ticket) {
          setMfaTicket(pending.ticket);
          setSecurityStep(pending.mode);
          setInitialized(true);
          return;
        }
      } catch { /* Expired or invalid local recovery state is ignored. */ }
      window.sessionStorage.removeItem("mira_onboarding_pending_mfa:" + email);
    }
    const verifiedToken = window.sessionStorage.getItem("mira_onboarding_token") || "";
    const resumedConnections = window.sessionStorage.getItem("mira_onboarding_connect_email") === email && !!getAccessToken();
    if (!verifiedToken && !resumedConnections) { setInitialized(true); return; }
    if (resumedConnections) setConnectedPhase(true);
    setToken(verifiedToken);
    if (resumedConnections) setStep("integrations");
    setInitialized(true);
  }, [email]);

  useEffect(() => {
    if (!initialized || !token || securityStep || step !== "workspace" || siteRevealed) return;
    const website = form.website.trim();
    if (!plausiblePublicWebsite(website)) return;
    const id = ++lookupSequence.current;
    const timer = window.setTimeout(() => {
      setSiteStatus("searching"); setSearchWarning("");
      void enrichOnboarding({ onboarding_token: token, email, website, cnpj: "" }).then(result => {
        if (lookupSequence.current !== id) return;
        const company = result.company;
        const suggestedName = company?.legal_name || (result.website?.title || "").split(" | ")[0].trim();
        setEnrichment(result);
        setForm(prev => ({
          ...prev,
          organizationName: prev.organizationName || suggestedName,
          tradeName: prev.tradeName || company?.trade_name || "",
          cnpj: prev.cnpj || company?.cnpj || result.website?.detected_cnpj || "",
          description: prev.description || publicCompanyDescription(result),
        }));
        if (result.website?.logo_url && !logoDataUrl) setLogoPreview(result.website.logo_url);
        setSearchWarning(result.warnings.join(" "));
        setSiteStatus(result.website ? "done" : "error");
        setSiteRevealed(true);
      }).catch(error => {
        if (lookupSequence.current !== id) return;
        setSearchWarning(error instanceof Error ? error.message : "Não foi possível consultar o site. Continue manualmente.");
        setSiteStatus("error"); setSiteRevealed(true);
      });
    }, 800);
    return () => { window.clearTimeout(timer); lookupSequence.current += 1; };
  }, [initialized, token, email, step, securityStep, siteRevealed, form.website, logoDataUrl]);

  useEffect(() => {
    if (!initialized || !siteRevealed || !token || securityStep || step !== "workspace") return;
    const digits = form.cnpj.replace(/\D/g, "");
    if (digits.length !== 14 || !isValidCnpj(digits)) return;
    if (enrichment?.company?.cnpj === digits || lastCnpjLookup.current === digits) return;
    const lookupId = ++cnpjLookupSequence.current;
    const timer = window.setTimeout(() => {
      lastCnpjLookup.current = digits;
      void enrichOnboarding({ onboarding_token: token, email, cnpj: digits, website: "" }).then(result => {
        if (!result.company) return;
        setEnrichment(prev => ({ company: result.company, website: prev?.website || null, warnings: result.warnings }));
        setForm(prev => ({ ...prev, organizationName: prev.organizationName || result.company?.legal_name || "",
          tradeName: prev.tradeName || result.company?.trade_name || "" }));
      }).catch(() => { /* A pesquisa cadastral não bloqueia o formulário. */ });
    }, 650);
    return () => { window.clearTimeout(timer); cnpjLookupSequence.current += 1; };
  }, [initialized, token, email, step, securityStep, siteRevealed, form.cnpj, enrichment?.company?.cnpj]);

  useEffect(() => {
    if (!initialized || !token || securityStep || connectedPhase) return;
    window.sessionStorage.setItem(draftKey, JSON.stringify({ step, form, siteRevealed }));
  }, [initialized, token, draftKey, form, step, securityStep, siteRevealed]);
  useEffect(() => { if (initialized && !securityStep) headingRef.current?.focus(); }, [initialized, securityStep, step]);

  function update<K extends keyof FormData>(key: K, value: FormData[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setError("");
  }

  function navigate(next: Step) {
    setError("");
    setStep(next);
  }

  function back() {
    if (busy || siteStatus === "searching" || connectedPhase) return;
    if (currentIndex === 0) { router.replace("/login"); return; }
    navigate(STEPS[currentIndex - 1]);
  }

  function next() {
    if (step === "workspace") {
      if (!siteRevealed || siteStatus === "searching") return;
      if (form.organizationName.trim().length < 2) {
        setError("Informe o nome da organização para continuar.");
        return;
      }
      if (form.cnpj.trim() && !isValidCnpj(form.cnpj)) {
        setError("Confira o CNPJ informado ou deixe-o em branco.");
        return;
      }
    }
    if (step === "description" && form.description.trim().length < 10) {
      setError("Descreva em poucas palavras o que sua organização faz.");
      return;
    }
    if (step === "name" && (!form.firstName.trim() || !form.lastName.trim())) {
      setError("Informe seu nome de preferência e sobrenome para criar a conta.");
      return;
    }
    navigate(STEPS[currentIndex + 1]);
  }

  function updateWebsite(value: string) {
    lookupSequence.current += 1;
    setSiteRevealed(false); setSiteStatus("idle");
    setSearchWarning(""); setEnrichment(null);
    update("website", value);
  }
  function skipWebsite() {
    lookupSequence.current += 1;
    setSiteRevealed(true); setSiteStatus("manual");
    setForm(prev => ({ ...prev, website: "" }));
    setSearchWarning("Sem site? Tudo bem. Preencha os dados da organização manualmente.");
  }

  function chooseLogo(file?: File) {
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 2_000_000) {
      setError("Selecione uma imagem PNG, JPG ou WebP de até 2 MB."); return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") { setLogoPreview(reader.result); setLogoDataUrl(reader.result); }
    };
    reader.readAsDataURL(file);
    setError("");
  }

  async function finish() {
    if (!token || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await completeOrganizationOnboarding({
        onboarding_token: token, email,
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
        job_title: "",
        organization_name: form.organizationName.trim(),
        trade_name: form.tradeName.trim(),
        cnpj: form.cnpj.replace(/\D/g, ""),
        website: form.website.trim(),
        institution_type: "higher_education",
        student_range: "", campuses: "",
        description: form.description.trim(),
        data_sources: form.dataSources,
        logo_data_url: logoDataUrl,
        auto_logo: !logoDataUrl && siteStatus === "done" && !!form.website,
      });
      window.sessionStorage.setItem("mira_onboarding_connect_email", email);
      setConnectedPhase(true);
      window.sessionStorage.removeItem("mira_onboarding_token");
      if ("challenge_token" in result) {
        setMfaTicket(result.challenge_token);
        const nextSecurityStep = "mfa_enrollment_required" in result && result.mfa_enrollment_required
          ? "enroll" : "verify";
        window.sessionStorage.setItem("mira_onboarding_pending_mfa:" + email, JSON.stringify({
          ticket: result.challenge_token, mode: nextSecurityStep,
        }));
        if ("mfa_enrollment_required" in result && result.mfa_enrollment_required) {
          setSecurityStep("enroll");
          try {
            setEnrollment(await api.beginRequiredMfaEnrollment(result.challenge_token));
          } catch {
            setError("O workspace foi criado, mas o autenticador não pôde ser carregado. Tente novamente.");
          }
        } else {
          setSecurityStep("verify");
        }
      } else {
        setStep("integrations");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível criar seu workspace. Tente novamente.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmMfa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!securityStep) return;
    setBusy(true);
    setError("");
    try {
      const result = securityStep === "enroll"
        ? await api.confirmRequiredMfaEnrollment(mfaTicket, mfaCode)
        : await api.verifyMfaLogin(mfaTicket, mfaCode);
      setAccessToken(result.access_token);
      setConnectedPhase(true);
      window.sessionStorage.removeItem("mira_onboarding_pending_mfa:" + email);
      if ("recovery_codes" in result && Array.isArray(result.recovery_codes) && result.recovery_codes.length) {
        setRecoveryCodes(result.recovery_codes);
      } else {
        setSecurityStep(null);
        setStep("integrations");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Código inválido ou expirado.");
    } finally {
      setBusy(false);
    }
  }

  const Icon = () => logoPreview ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={logoPreview} alt="" className="mira-flow-logo-preview" />
  ) : (
    <span className="mira-flow-workspace-initial" aria-hidden="true">
      {(form.organizationName.trim() || "W").slice(0, 1).toUpperCase()}
    </span>
  );

  if (!initialized) {
    return <main className="mira-flow-page"><div className="mira-flow-initial" role="status">Preparando seu workspace…</div></main>;
  }
  if (!email || (!token && !securityStep && !connectedPhase)) {
    return (
      <main className="mira-flow-page">
        <div className="mira-flow-expired">
          <Image src="/mira-logo.svg" alt="MIRA" width={94} height={25} priority />
          <h1>Vamos confirmar seu e-mail novamente?</h1>
          <p>O acesso para criar um workspace não está mais disponível. Confirme seu e-mail para continuar com segurança.</p>
          <button className="mira-flow-primary" onClick={() => router.replace("/login")}>Voltar ao acesso</button>
        </div>
      </main>
    );
  }

  return (
    <main className="mira-flow-page">
      <header className="mira-flow-header">
        <Image src="/mira-logo.svg" alt="MIRA" width={94} height={25} priority />
        <span className="mira-flow-security"><LockKeyhole size={13} /> Configuração segura</span>
      </header>
      <div className="mira-flow-frame">
        <section className="mira-flow-left" aria-label="Configuração do workspace">
          <div className="mira-flow-left-inner">
            {securityStep ? (
              <div className="mira-flow-security-flow" key="security">
                {recoveryCodes ? (
                  <>
                    <CheckCircle2 size={28} />
                    <h1>Códigos de recuperação</h1>
                    <p>Guarde esses códigos em um local seguro. Eles serão mostrados apenas uma vez.</p>
                    <div className="mira-flow-recovery">{recoveryCodes.map((item) => <code key={item}>{item}</code>)}</div>
                    <button type="button" className="mira-flow-secondary" onClick={() => void navigator.clipboard.writeText(recoveryCodes.join("\n"))}>Copiar códigos</button>
                    <button type="button" className="mira-flow-primary" onClick={() => { setRecoveryCodes(null); setSecurityStep(null); setStep("integrations"); }}>Já guardei — continuar</button>
                  </>
                ) : (
                  <>
                    <p className="mira-flow-eyebrow">Última etapa</p>
                    <h1>{securityStep === "enroll" ? "Proteja seu acesso." : "Confirme seu acesso."}</h1>
                    <p>Use o aplicativo autenticador para concluir a criação do workspace.</p>
                    {securityStep === "enroll" && enrollment && (
                      <div className="mira-flow-mfa-setup">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={enrollment.qr_code} alt="QR Code para configurar o autenticador" />
                        <code>{enrollment.secret}</code>
                      </div>
                    )}
                    {securityStep === "enroll" && !enrollment && (
                      <button type="button" className="mira-flow-secondary" onClick={async () => {
                        try { setEnrollment(await api.beginRequiredMfaEnrollment(mfaTicket)); setError(""); }
                        catch { setError("Não foi possível carregar o autenticador."); }
                      }}>Tentar carregar novamente</button>
                    )}
                    <form onSubmit={confirmMfa} className="mira-flow-fields">
                      <InputField id="mira-flow-mfa" label="Código do aplicativo">
                        <input id="mira-flow-mfa" required inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={mfaCode} onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="000000" />
                      </InputField>
                      <button type="submit" className="mira-flow-primary" disabled={busy || mfaCode.length !== 6 || (securityStep === "enroll" && !enrollment)}>{busy ? "Verificando…" : "Confirmar"}</button>
                    </form>
                  </>
                )}
                {error && <p className="mira-flow-error" role="alert">{error}</p>}
              </div>
            ) : (
              <>
                <div className="mira-flow-progress">
                  <span>{currentIndex === 0 ? "Vamos começar" : String(currentIndex) + (currentIndex === 1 ? " etapa concluída" : " etapas concluídas")}</span>
                  <span>{String(currentIndex + 1).padStart(2, "0")} / 05</span>
                </div>
                <div className="mira-flow-message" key={step}>
                  <h1 ref={headingRef} tabIndex={-1}>
                    {step === "workspace" ? <TypingText text="Criar seu workspace" /> :
                      step === "description" ? (publicCompanyDescription(enrichment) ? "Encontramos informações sobre sua empresa." : "Conte um pouco sobre sua empresa.") :
                      step === "name" ? "E como você prefere que te chamem?" :
                      step === "integrations" ? (form.firstName || "Agora") + ", vamos conectar suas ferramentas." :
                      "Vamos proteger seu workspace."}
                  </h1>
                  <p>
                    {step === "workspace" ? "Qual é o site da sua organização? Vamos encontrar os dados automaticamente." :
                      step === "description" ? "Esta descrição ajuda a entender a operação. Confirme ou edite antes de continuar." :
                      step === "name" ? "Assim, podemos deixar sua experiência mais pessoal, sem formulários longos." :
                      step === "integrations" ? "Autorize suas conexões agora ou continue sem elas. Você poderá adicionar mais contas depois." :
                      "Crie sua organização e confirme o MFA antes de conectar seus aplicativos. Nenhuma cobrança será iniciada."}
                  </p>
                </div>

                <div className="mira-flow-interaction" key={"card-" + step}>
                  {step === "workspace" && (
                    <>
                      <div className="mira-flow-card-heading">Vamos conhecer sua organização</div>
                      <div className="mira-flow-fields">
                        <InputField id="org-site" label="Site da organização"
                          note="A pesquisa em fontes públicas é uma sugestão, não uma prova de vínculo.">
                          <input id="org-site" autoFocus type="text" inputMode="url" autoComplete="url" maxLength={255}
                            placeholder={domain ? "https://" + domain : "https://suaorganizacao.edu.br"}
                            value={form.website} onChange={event => updateWebsite(event.target.value)} />
                        </InputField>

                        {!siteRevealed && <div className="mira-flow-site-progress" role="status" aria-live="polite">
                          {siteStatus === "searching" ? <>
                            <SearchingOrb />
                            <div>
                              <strong><TypingText text={"Buscando " + form.website.trim() + "…"} /></strong>
                              <p>Consultando o site, CNPJ, cadastro público e logotipo.</p>
                            </div>
                          </> : <div>
                            <strong>Primeiro, informe o site da sua organização.</strong>
                            <p>Quando o endereço estiver completo, a pesquisa começa automaticamente.</p>
                          </div>}
                        </div>}
                        {!siteRevealed && <button type="button" className="mira-flow-inline-action mira-flow-skip-site"
                          onClick={skipWebsite} disabled={siteStatus === "searching"}>
                          Minha organização não tem site
                        </button>}
                        {siteRevealed && <div className="mira-flow-discovered">
                          {searchWarning && <p className="mira-flow-inline-notice" role="status">{searchWarning}</p>}
                          {siteStatus === "done" && <p className="mira-flow-discovery-success" role="status">
                            <CheckCircle2 size={15} /> Site consultado. Confira os dados sugeridos.
                          </p>}
                          <div className="mira-flow-logo-upload">
                            <Icon />
                            <div>
                              <label htmlFor="mira-flow-logo">Logotipo do workspace</label>
                              <input id="mira-flow-logo" type="file" accept="image/png,image/jpeg,image/webp"
                                onChange={event => chooseLogo(event.target.files?.[0])} />
                              <p>{logoDataUrl ? "Imagem selecionada. Será salva no workspace ao concluir." :
                                logoPreview ? "Ícone sugerido pelo site. Envie uma imagem para substituir." :
                                "PNG, JPG ou WebP (até 2 MB). Será salvo no workspace."}</p>
                            </div>
                          </div>
                          <InputField id="org-name" label="Nome da organização">
                            <input id="org-name" required maxLength={255} placeholder="Razão social ou nome institucional"
                              value={form.organizationName} onChange={event => update("organizationName", event.target.value)} />
                          </InputField>
                          <div className="mira-flow-two-fields">
                            <InputField id="org-trade" label="Nome de exibição">
                              <input id="org-trade" maxLength={255} placeholder="Nome do workspace"
                                value={form.tradeName} onChange={event => update("tradeName", event.target.value)} />
                            </InputField>
                            <InputField id="org-cnpj" label="CNPJ">
                              <input id="org-cnpj" inputMode="numeric" placeholder="00.000.000/0000-00"
                                value={maskCnpj(form.cnpj)}
                                onChange={event => update("cnpj", event.target.value.replace(/\D/g, "").slice(0, 14))} />
                            </InputField>
                          </div>
                          <p className="mira-flow-note">O CNPJ pode ser identificado no rodapé do site e verificado em fonte pública. Revise antes de continuar.</p>
                          <div className="mira-flow-field">
                            <p className="mira-flow-static-label">Tipo de operação</p>
                            <div className="mira-flow-profiles" role="group" aria-label="Tipo de operação disponível">
                              <span className="mira-flow-profile-selected"><GraduationCap size={15} /> Educação <Check size={15} /></span>
                              <span className="mira-flow-profile-unavailable">Cobrança <small>Módulo adicional</small></span>
                              <span className="mira-flow-profile-unavailable">Outro <small>Em preparação</small></span>
                            </div>
                          </div>
                        </div>}
                      </div>
                    </>
                  )}

                  {step === "description" && (
                    <>
                      <p className="mira-flow-card-label">Descrição da organização</p>
                      {enrichment?.website?.description && <p className="mira-flow-source">Sugestão de fonte pública — revise antes de confirmar.</p>}
                      {!enrichment?.website?.description && !enrichment?.company?.primary_activity && (
                        <p className="mira-flow-source">Ainda não encontramos uma descrição confiável. Escreva como sua organização atua.</p>
                      )}
                      <textarea aria-label="Descrição da organização" rows={8} maxLength={2000} value={form.description} onChange={(e) => update("description", e.target.value)} placeholder="Em poucas palavras, o que sua organização faz?" />
                    </>
                  )}

                  {step === "name" && (
                    <div className="mira-flow-fields">
                      <InputField id="person-first" label="Como prefere ser chamado?">
                        <input id="person-first" autoFocus maxLength={80} autoComplete="given-name" value={form.firstName} onChange={(e) => update("firstName", e.target.value)} placeholder="Seu primeiro nome" />
                      </InputField>
                      <InputField id="person-last" label="Sobrenome" note="Necessário para completar seu perfil de acesso.">
                        <input id="person-last" autoComplete="family-name" maxLength={80} value={form.lastName} onChange={(e) => update("lastName", e.target.value)} placeholder="Seu sobrenome" />
                      </InputField>
                      <p className="mira-flow-verified"><CheckCircle2 size={16} /> E-mail confirmado: {email}</p>
                    </div>
                  )}

                  {step === "integrations" && (
                    <OnboardingIntegrationSetup onComplete={() => {
                      window.sessionStorage.removeItem("mira_onboarding_connect_email");
                      window.sessionStorage.removeItem(draftKey);
                      router.replace("/");
                    }} />
                  )}

                  {step === "provision" && (
                    <>
                      <p className="mira-flow-card-label">Tudo pronto para começar</p>
                      <div className="mira-flow-finish-summary">
                        <span><CheckCircle2 size={16} /> Empresa: {previewName}</span>
                        <span><CheckCircle2 size={16} /> Perfil de acesso: {form.firstName} {form.lastName}</span>
                        <span><CheckCircle2 size={16} /> Conexões opcionais após o MFA</span>
                      </div>
                      <div className="mira-flow-trial-note">
                        <strong>Segurança antes das conexões</strong>
                        <p>Crie o workspace e configure o autenticador. Em seguida, autorize as conexões reais sem ativar sincronizações automaticamente.</p>
                      </div>
                    </>
                  )}

                  {error && <p className="mira-flow-error" role="alert">{error}</p>}
                  {step !== "integrations" && <div className="mira-flow-card-actions">
                    <button type="button" className="mira-flow-back" onClick={back} disabled={busy || siteStatus === "searching"}><ArrowLeft size={14} /> Voltar</button>
                    {step === "provision" ? (
                      <button type="button" className="mira-flow-primary" disabled={busy} onClick={() => void finish()}>
                        {busy ? "Criando…" : "Criar e proteger workspace"} <ArrowRight size={14} />
                      </button>
                    ) : (
                      <button type="button" className="mira-flow-primary" disabled={busy || siteStatus === "searching" || (step === "workspace" && !siteRevealed)} onClick={next}>
                        {"Continuar"} <ArrowRight size={14} />
                      </button>
                    )}
                  </div>}
                </div>
              </>
            )}
          </div>
        </section>

        <aside className="mira-flow-preview" aria-label="Prévia do workspace">
          <div className="mira-flow-preview-window">
            <div className="mira-flow-preview-top"><Icon /> <strong>{previewName}</strong><span>Prévia</span></div>
            <div className="mira-flow-preview-search">Pesquisar no workspace <kbd>Ctrl K</kbd></div>
            <div className="mira-flow-preview-body">
              <nav className="mira-flow-preview-nav" aria-label="Seções de exemplo">
                {["Visão geral", "Alunos", "Central de trabalho", "Intervenções", "Resultados", "Dados e integrações"].map((label, i) => (
                  <span key={label} className={i === 0 ? "active" : ""}>{label}</span>
                ))}
              </nav>
              <div className="mira-flow-preview-content">
                <p className="mira-flow-preview-kicker">Seu ambiente</p>
                <h2>{previewName}</h2>
                {form.description.trim() && <p className="mira-flow-preview-description">{form.description.slice(0, 170)}</p>}
                <div className="mira-flow-empty">
                  <Building2 size={22} />
                  <strong>Workspace ainda sem dados</strong>
                  <p>Os indicadores aparecerão quando houver dados reais e integrações autorizadas.</p>
                </div>
                <div className="mira-flow-preview-skeleton"><span /><span /><span /></div>
              </div>
            </div>
          </div>
          <p className="mira-flow-preview-caption">{connectedPhase ? "Workspace criado. Conexões autorizadas individualmente, sem sincronização automática." : "Esta é uma prévia de estrutura. Nenhum dado ou conexão foi criado ainda."}</p>
        </aside>
      </div>
    </main>
  );
}
