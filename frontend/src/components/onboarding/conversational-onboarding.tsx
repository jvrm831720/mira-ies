"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft, ArrowRight, Building2, Check, CheckCircle2,
  Database, GraduationCap, LockKeyhole, ShieldCheck, UploadCloud,
} from "@/components/ui/icons";
import { api } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import { completeOrganizationOnboarding, enrichOnboarding, type CompanyEnrichment, type OnboardingEnrichment } from "@/lib/onboarding-api";
import { corporateDomain, isValidCnpj, maskCnpj, publicCompanyDescription } from "@/lib/onboarding-flow.mjs";

type Step = "search" | "workspace" | "description" | "name" | "integrations" | "trial";
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
const STEPS: Step[] = ["workspace", "description", "name", "integrations", "trial"];
const SOURCE_OPTIONS = [
  { id: "sponte", name: "Sponte", category: "Gestão acadêmica" },
  { id: "sophia", name: "Sophia", category: "Gestão acadêmica" },
  { id: "totvs_rm", name: "TOTVS RM", category: "Gestão e ERP" },
  { id: "moodle", name: "Moodle", category: "Ambiente de aprendizagem" },
  { id: "omie", name: "Omie", category: "Financeiro" },
  { id: "spreadsheets", name: "Planilhas", category: "Importação de dados" },
] as const;

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
  return (
    <div className="mira-flow-orb" aria-hidden="true">
      <span /><span /><span />
    </div>
  );
}

export function ConversationalOnboarding() {
  const router = useRouter();
  const params = useSearchParams();
  const email = (params.get("email") || "").trim().toLowerCase();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [token, setToken] = useState("");
  const [initialized, setInitialized] = useState(false);
  const [step, setStep] = useState<Step>("workspace");
  const [form, setForm] = useState<FormData>(EMPTY);
  const [enrichment, setEnrichment] = useState<OnboardingEnrichment | null>(null);
  const [suggestion, setSuggestion] = useState<CompanyEnrichment | null>(null);
  const [lookupBusy, setLookupBusy] = useState(false);
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
  const draftKey = "mira_onboarding_draft_v2:" + email;

  useEffect(() => {
    if (!email) { setInitialized(true); return; }
    const verifiedToken = window.sessionStorage.getItem("mira_onboarding_token") || "";
    if (!verifiedToken) { setInitialized(true); return; }
    setToken(verifiedToken);
    let cancelled = false;
    const saved = window.sessionStorage.getItem("mira_onboarding_draft_v2:" + email);
    if (saved) {
      try {
        const draft = JSON.parse(saved) as { step?: Step; form?: Partial<FormData> };
        if (draft.form) setForm({ ...EMPTY, ...draft.form });
        if (draft.step && STEPS.includes(draft.step)) setStep(draft.step);
      } catch { window.sessionStorage.removeItem("mira_onboarding_draft_v2:" + email); }
      setInitialized(true);
      return;
    }
    if (!domain) { setStep("workspace"); setInitialized(true); return; }
    // The searching state is shown only while this real, authenticated
    // server-side enrichment request is outstanding.
    setStep("search");
    setForm((v) => ({ ...v, website: "https://" + domain }));
    setInitialized(true);
    enrichOnboarding({
      onboarding_token: verifiedToken,
      email,
      cnpj: "",
      website: "https://" + domain,
    }).then((result) => {
      if (cancelled) return;
      setEnrichment(result);
      const name = result.company?.trade_name || result.company?.legal_name ||
        (result.website?.title || "").split(" | ")[0].trim();
      const description = publicCompanyDescription(result);
      setForm((prev) => ({
        ...prev,
        organizationName: name || prev.organizationName,
        description: description || prev.description,
      }));
      if (result.warnings.length) setSearchWarning(result.warnings.join(" "));
    }).catch(() => {
      if (!cancelled) setSearchWarning("Não foi possível consultar o site. Você pode preencher os dados manualmente.");
    }).finally(() => {
      if (!cancelled) setStep("workspace");
    });
    return () => { cancelled = true; };
  }, [domain, email]);

  useEffect(() => {
    if (!initialized || !token || step === "search" || securityStep) return;
    window.sessionStorage.setItem(draftKey, JSON.stringify({ step, form }));
  }, [initialized, token, draftKey, form, step, securityStep]);

  useEffect(() => {
    if (initialized && !securityStep && step !== "search") headingRef.current?.focus();
  }, [initialized, securityStep, step]);

  function update<K extends keyof FormData>(key: K, value: FormData[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setError("");
  }

  function navigate(next: Step) {
    setError("");
    setStep(next);
  }

  function back() {
    if (busy || lookupBusy) return;
    if (currentIndex === 0) { router.replace("/login"); return; }
    navigate(STEPS[currentIndex - 1]);
  }

  function next() {
    if (step === "workspace") {
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

  async function consultCnpj() {
    if (!token) return;
    if (!isValidCnpj(form.cnpj)) {
      setError("Informe um CNPJ válido para consultar os dados cadastrais.");
      return;
    }
    setError("");
    setLookupBusy(true);
    try {
      const result = await enrichOnboarding({
        onboarding_token: token,
        email,
        cnpj: form.cnpj.replace(/\D/g, ""),
        website: "",
      });
      setSuggestion(result.company);
      setEnrichment((prev) => ({
        company: result.company || prev?.company || null,
        website: prev?.website || null,
        warnings: result.warnings,
      }));
      if (!result.company) setError(result.warnings.join(" ") || "Nenhuma informação cadastral encontrada. Continue manualmente.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível consultar o CNPJ. Continue manualmente.");
    } finally {
      setLookupBusy(false);
    }
  }

  function acceptSuggestion() {
    if (!suggestion) return;
    setForm((prev) => ({
      ...prev,
      organizationName: suggestion.legal_name || prev.organizationName,
      tradeName: suggestion.trade_name || prev.tradeName,
      cnpj: suggestion.cnpj || prev.cnpj,
      description: prev.description || suggestion.primary_activity || "",
    }));
    setSuggestion(null);
  }

  function chooseLogo(file?: File) {
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 2_000_000) {
      setError("Selecione uma imagem PNG, JPG ou WebP de até 2 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setLogoPreview(typeof reader.result === "string" ? reader.result : "");
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
      });
      window.sessionStorage.removeItem("mira_onboarding_token");
      window.sessionStorage.removeItem(draftKey);
      if ("challenge_token" in result) {
        setMfaTicket(result.challenge_token);
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
        router.replace("/");
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
      if ("recovery_codes" in result && Array.isArray(result.recovery_codes) && result.recovery_codes.length) {
        setRecoveryCodes(result.recovery_codes);
      } else {
        router.replace("/");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Código inválido ou expirado.");
    } finally {
      setBusy(false);
    }
  }

  const Icon = () => logoPreview ? (
    // User-provided local preview only; no upload to the server.
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
  if (!email || (!token && !securityStep)) {
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
                    <button type="button" className="mira-flow-primary" onClick={() => router.replace("/")}>Já guardei — entrar</button>
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
            ) : step === "search" ? (
              <div className="mira-flow-searching" role="status" aria-live="polite">
                <h1>Olá, estamos buscando sua empresa...</h1>
                <p>Estamos verificando as informações públicas do domínio {domain}.</p>
                <SearchingOrb />
              </div>
            ) : (
              <>
                <div className="mira-flow-progress">
                  <span>{currentIndex === 0 ? "Vamos começar" : String(currentIndex) + (currentIndex === 1 ? " etapa concluída" : " etapas concluídas")}</span>
                  <span>{String(currentIndex + 1).padStart(2, "0")} / 05</span>
                </div>
                <div className="mira-flow-message" key={step}>
                  <h1 ref={headingRef} tabIndex={-1}>
                    {step === "workspace" ? "Criar seu workspace" :
                      step === "description" ? "Conhecemos um pouco da sua empresa." :
                      step === "name" ? "E como você prefere que te chamem?" :
                      step === "integrations" ? (form.firstName || "Agora") + ", vamos falar das suas ferramentas." :
                      "Seu workspace está quase pronto."}
                  </h1>
                  <p>
                    {step === "workspace" ? "Revise os dados da sua organização. Você poderá ajustar as informações mais tarde." :
                      step === "description" ? "Esta descrição ajuda a entender a operação. Confirme ou edite antes de continuar." :
                      step === "name" ? "Assim, podemos deixar sua experiência mais pessoal, sem formulários longos." :
                      step === "integrations" ? "Indique os sistemas que já utiliza. As conexões são configuradas depois, com sua autorização." :
                      "Vamos criar seu ambiente com as informações confirmadas. Nenhuma cobrança será iniciada."}
                  </p>
                </div>

                <div className="mira-flow-interaction" key={"card-" + step}>
                  {step === "workspace" && (
                    <>
                      <div className="mira-flow-card-heading">Detalhes do workspace</div>
                      {searchWarning && <p className="mira-flow-inline-notice" role="status">{searchWarning}</p>}
                      <div className="mira-flow-logo-upload">
                        <Icon />
                        <div>
                          <label htmlFor="mira-flow-logo">Adicionar logotipo</label>
                          <input id="mira-flow-logo" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => chooseLogo(event.target.files?.[0])} />
                          <p>Prévia local. O envio definitivo será feito em Configurações.</p>
                        </div>
                      </div>
                      <div className="mira-flow-fields">
                        <InputField id="org-name" label="Nome da organização">
                          <input id="org-name" autoFocus required maxLength={255} placeholder="Nome da sua empresa" value={form.organizationName} onChange={(e) => update("organizationName", e.target.value)} />
                        </InputField>
                        <div className="mira-flow-two-fields">
                          <InputField id="org-trade" label="Nome de exibição">
                            <input id="org-trade" maxLength={255} placeholder="Opcional" value={form.tradeName} onChange={(e) => update("tradeName", e.target.value)} />
                          </InputField>
                          <InputField id="org-cnpj" label="CNPJ">
                            <input id="org-cnpj" inputMode="numeric" placeholder="00.000.000/0000-00" value={maskCnpj(form.cnpj)} onChange={(e) => { update("cnpj", e.target.value.replace(/\D/g, "").slice(0, 14)); setSuggestion(null); }} />
                          </InputField>
                        </div>
                        {form.cnpj.replace(/\D/g, "").length === 14 && (
                          <button type="button" className="mira-flow-inline-action" onClick={() => void consultCnpj()} disabled={lookupBusy}>
                            {lookupBusy ? "Consultando cadastro…" : "Consultar dados cadastrais"}
                          </button>
                        )}
                        {suggestion && (
                          <div className="mira-flow-suggestion" role="status">
                            <strong>Dados encontrados para revisão</strong>
                            <p>{suggestion.legal_name || "Sem razão social"} · {suggestion.status || "Situação não informada"}</p>
                            <button type="button" onClick={acceptSuggestion}>Aplicar sugestão</button>
                          </div>
                        )}
                        <InputField id="org-site" label="Site da organização" note="A descoberta por domínio é apenas uma sugestão, não prova de vínculo.">
                          <input id="org-site" type="text" maxLength={255} placeholder="https://suaempresa.com.br" value={form.website} onChange={(e) => update("website", e.target.value)} />
                        </InputField>
                        <InputField id="org-profile" label="Tipo de operação">
                          <div className="mira-flow-profiles" id="org-profile">
                            <span className="mira-flow-profile-selected"><GraduationCap size={15} /> Educação <Check size={15} /></span>
                            <span className="mira-flow-profile-unavailable">Cobrança <small>Em preparação</small></span>
                            <span className="mira-flow-profile-unavailable">Outro <small>Em preparação</small></span>
                          </div>
                        </InputField>
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
                    <>
                      <p className="mira-flow-card-label">Ferramentas da sua organização</p>
                      <div className="mira-flow-tool-list">
                        {SOURCE_OPTIONS.map((source) => {
                          const selected = form.dataSources.includes(source.id);
                          return (
                            <button type="button" key={source.id} aria-pressed={selected} className={"mira-flow-tool" + (selected ? " selected" : "")}
                              onClick={() => update("dataSources", selected ? form.dataSources.filter((v) => v !== source.id) : [...form.dataSources, source.id])}>
                              <span className="mira-flow-tool-icon"><Database size={15} /></span>
                              <span className="mira-flow-tool-copy"><strong>{source.name}</strong><small>{source.category}</small></span>
                              <span className="mira-flow-tool-indicator">{selected ? <Check size={15} /> : "+"}</span>
                            </button>
                          );
                        })}
                      </div>
                      <p className="mira-flow-note">A seleção não conecta nem sincroniza dados. As integrações e seus escopos serão configurados no workspace.</p>
                    </>
                  )}

                  {step === "trial" && (
                    <>
                      <p className="mira-flow-card-label">Tudo pronto para começar</p>
                      <div className="mira-flow-finish-summary">
                        <span><CheckCircle2 size={16} /> Empresa: {previewName}</span>
                        <span><CheckCircle2 size={16} /> Perfil de acesso: {form.firstName} {form.lastName}</span>
                        <span><CheckCircle2 size={16} /> Fontes selecionadas: {form.dataSources.length}</span>
                      </div>
                      <div className="mira-flow-trial-note">
                        <strong>Sobre os 7 dias de Pro</strong>
                        <p>A oferta de boas-vindas ainda não foi habilitada para concessão automática. Nenhum trial ou cobrança será ativado nesta etapa.</p>
                      </div>
                    </>
                  )}

                  {error && <p className="mira-flow-error" role="alert">{error}</p>}
                  <div className="mira-flow-card-actions">
                    <button type="button" className="mira-flow-back" onClick={back} disabled={busy || lookupBusy}><ArrowLeft size={14} /> Voltar</button>
                    {step === "trial" ? (
                      <button type="button" className="mira-flow-primary" disabled={busy} onClick={() => void finish()}>
                        {busy ? "Criando…" : "Criar workspace"} <ArrowRight size={14} />
                      </button>
                    ) : (
                      <button type="button" className="mira-flow-primary" disabled={busy || lookupBusy} onClick={next}>
                        {step === "integrations" && !form.dataSources.length ? "Fazer isso depois" : "Confirmar"} <ArrowRight size={14} />
                      </button>
                    )}
                  </div>
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
          <p className="mira-flow-preview-caption">Esta é uma prévia de estrutura. Nenhum dado ou conexão foi criado ainda.</p>
        </aside>
      </div>
    </main>
  );
}
