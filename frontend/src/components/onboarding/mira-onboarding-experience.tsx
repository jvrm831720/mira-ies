"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import {
  Activity, ArrowLeft, ArrowRight, BookOpen, Building2, Check, CheckCircle2,
  ChevronRight, GraduationCap, Layers3, Loader2, LockKeyhole,
  MapPin, ShieldCheck, Sparkles, Users,
} from "lucide-react";
import { api } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";

type Draft = {
  person: { first_name: string; last_name: string; job_title: string };
  institution: {
    legal_name: string; trade_name: string; cnpj: string; website_url: string;
    workspace_slug: string; country_code: string;
  };
  context: {
    description: string; institution_type: string; student_count_band: string;
    campus_count: string; systems: string[]; goals: string[];
  };
  workspace: { objects: string[] };
};

const INITIAL_DRAFT: Draft = {
  person: { first_name: "", last_name: "", job_title: "" },
  institution: {
    legal_name: "", trade_name: "", cnpj: "", website_url: "",
    workspace_slug: "", country_code: "BR",
  },
  context: {
    description: "", institution_type: "Universidade",
    student_count_band: "Até 5 mil alunos", campus_count: "1",
    systems: [], goals: ["Reduzir evasão", "Aumentar permanência"],
  },
  workspace: {
    objects: ["Alunos", "Cursos", "Unidades", "Matrículas", "Intervenções"],
  },
};

const STEPS = [
  { label: "Sobre você", hint: "Vamos começar por você." },
  { label: "Sua instituição", hint: "Agora, vamos identificar sua instituição." },
  { label: "Confirme os dados", hint: "Revise as informações que vão identificar seu espaço." },
  { label: "Conheça sua operação", hint: "Quero entender como sua instituição funciona." },
  { label: "Estrutura do workspace", hint: "Com base no que você contou, esta é uma primeira proposta." },
];

const OBJECTS = [
  { id: "Alunos", description: "Perfis, vínculos e histórico dos estudantes", icon: Users },
  { id: "Cursos", description: "Cursos, programas e modalidades", icon: BookOpen },
  { id: "Unidades", description: "Campi, polos e unidades acadêmicas", icon: MapPin },
  { id: "Matrículas", description: "Matrículas, períodos e situação acadêmica", icon: GraduationCap },
  { id: "Intervenções", description: "Ações de permanência e acompanhamento", icon: Activity },
  { id: "Equipes", description: "Times e responsáveis pelas ações", icon: Layers3 },
];

const SYSTEMS = ["TOTVS RM", "Lyceum", "Sponte", "Sophia", "JACAD", "Moodle", "Canvas", "Planilhas", "Outro"];
const GOALS = ["Reduzir evasão", "Aumentar permanência", "Priorizar alunos em risco", "Organizar intervenções", "Acompanhar resultados"];

function slugify(value: string) {
  return value.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 72);
}

function formatCnpj(value: string) {
  const d = value.replace(/\D/g, "").slice(0, 14);
  return d.replace(/^(\d{2})(\d)/, "$1.$2")
    .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1/$2")
    .replace(/(\d{4})(\d)/, "$1-$2");
}

function Field({ label, value, onChange, placeholder, type = "text", hint, readOnly = false }: {
  label: string; value: string; onChange?: (value: string) => void; placeholder?: string;
  type?: string; hint?: string; readOnly?: boolean;
}) {
  return (
    <label className="block space-y-2">
      <span className="text-[12px] font-medium text-[#c4c8d0]">{label}</span>
      <input
        type={type}
        value={value}
        readOnly={readOnly}
        onChange={(event) => onChange?.(event.target.value)}
        placeholder={placeholder}
        className="h-11 w-full rounded-[7px] border border-[#343840] bg-[#17191e] px-3 text-[13px] text-[#f4f5f7] outline-none transition placeholder:text-[#737985] focus:border-[#3577f1] focus:ring-2 focus:ring-[#3577f1]/20 read-only:text-[#9ba1ac] read-only:cursor-default"
      />
      {hint ? <span className="block text-[11px] text-[#858b96]">{hint}</span> : null}
    </label>
  );
}

function SelectField({ label, value, options, onChange }: {
  label: string; value: string; options: string[]; onChange: (value: string) => void;
}) {
  return (
    <label className="block space-y-2">
      <span className="text-[12px] font-medium text-[#c4c8d0]">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}
        className="h-11 w-full rounded-[7px] border border-[#343840] bg-[#17191e] px-3 text-[13px] text-[#f4f5f7] outline-none focus:border-[#3577f1]">
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  );
}

export function MiraOnboardingExperience({ email, initialToken }: { email: string; initialToken: string }) {
  const router = useRouter();
  const [token, setToken] = useState(initialToken);
  const [draft, setDraft] = useState<Draft>(INITIAL_DRAFT);
  const [step, setStep] = useState(0);
  const [restored, setRestored] = useState(false);
  const [slugTouched, setSlugTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");
  const [error, setError] = useState("");
  const [mfaMode, setMfaMode] = useState<"enroll" | "verify" | null>(null);
  const [mfaTicket, setMfaTicket] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [mfaEnrollment, setMfaEnrollment] = useState<{ secret: string; qr_code: string } | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);

  useEffect(() => {
    if (initialToken) {
      window.sessionStorage.setItem("mira_onboarding_token", initialToken);
      setToken(initialToken);
      router.replace(`/onboarding?email=${encodeURIComponent(email)}`);
    } else {
      setToken(window.sessionStorage.getItem("mira_onboarding_token") || "");
    }
    try {
      const saved = window.sessionStorage.getItem("mira_onboarding_draft");
      if (saved) {
        const parsed = JSON.parse(saved) as { draft?: Draft; step?: number };
        if (parsed.draft) setDraft({ ...INITIAL_DRAFT, ...parsed.draft });
        if (typeof parsed.step === "number") setStep(Math.min(4, Math.max(0, parsed.step)));
      }
    } catch {
      window.sessionStorage.removeItem("mira_onboarding_draft");
    }
    setRestored(true);
  }, [email, initialToken, router]);

  useEffect(() => {
    if (!slugTouched && draft.institution.trade_name) {
      setDraft((current) => ({
        ...current,
        institution: { ...current.institution, workspace_slug: slugify(current.institution.trade_name) },
      }));
    }
  }, [draft.institution.trade_name, slugTouched]);

  const serializedDraft = useMemo(() => ({
    person: draft.person,
    institution: draft.institution,
    context: draft.context,
    workspace: draft.workspace,
  }), [draft]);

  useEffect(() => {
    if (!restored) return;
    window.sessionStorage.setItem("mira_onboarding_draft", JSON.stringify({ draft, step }));
    if (!token) return;
    setSaveState("saving");
    const timer = window.setTimeout(() => {
      api.saveOnboardingDraft(token, step, serializedDraft)
        .then(() => setSaveState("saved"))
        .catch(() => setSaveState("error"));
    }, 700);
    return () => window.clearTimeout(timer);
  }, [draft, step, restored, token, serializedDraft]);

  const updatePerson = (key: keyof Draft["person"], value: string) =>
    setDraft((current) => ({ ...current, person: { ...current.person, [key]: value } }));
  const updateInstitution = (key: keyof Draft["institution"], value: string) =>
    setDraft((current) => ({ ...current, institution: { ...current.institution, [key]: value } }));
  const updateContext = (key: keyof Draft["context"], value: string | string[]) =>
    setDraft((current) => ({ ...current, context: { ...current.context, [key]: value } }));

  const canContinue = (() => {
    if (step === 0) return Boolean(draft.person.first_name.trim() && draft.person.last_name.trim());
    if (step === 1) return Boolean(draft.institution.trade_name.trim() && draft.institution.cnpj.replace(/\D/g, "").length === 14);
    if (step === 2) return Boolean(draft.institution.legal_name.trim() && draft.institution.workspace_slug.trim());
    if (step === 3) return Boolean(draft.context.description.trim().length >= 10);
    return draft.workspace.objects.length > 0;
  })();

  async function finishOnboarding() {
    if (!token) {
      setError("Sua sessão de cadastro não foi encontrada. Volte ao acesso e confirme seu e-mail novamente.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await api.completeSelfServeOnboarding(token, serializedDraft);
      if ("challenge_token" in response && response.challenge_token) {
        setMfaTicket(response.challenge_token);
        if ("mfa_enrollment_required" in response && response.mfa_enrollment_required) {
          const enrollment = await api.beginRequiredMfaEnrollment(response.challenge_token);
          setMfaEnrollment(enrollment);
          setMfaMode("enroll");
        } else {
          setMfaMode("verify");
        }
      } else if ("access_token" in response && response.access_token) {
        setAccessToken(response.access_token);
        router.replace("/");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível criar seu workspace.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmMfa(event: FormEvent) {
    event.preventDefault();
    if (!mfaTicket || mfaCode.length !== 6) return;
    setBusy(true);
    setError("");
    try {
      const response = mfaMode === "enroll"
        ? await api.confirmRequiredMfaEnrollment(mfaTicket, mfaCode)
        : await api.verifyMfaLogin(mfaTicket, mfaCode);
      setAccessToken(response.access_token);
      if (mfaMode === "enroll" && "recovery_codes" in response) {
        setRecoveryCodes(response.recovery_codes);
        setMfaCode("");
      } else {
        window.sessionStorage.removeItem("mira_onboarding_token");
        window.sessionStorage.removeItem("mira_onboarding_draft");
        router.replace("/");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Código inválido ou expirado.");
    } finally {
      setBusy(false);
    }
  }

  const currentInstitution = draft.institution.trade_name || "Sua instituição";
  const fullName = [draft.person.first_name, draft.person.last_name].filter(Boolean).join(" ") || "Seu nome";
  const progress = mfaMode ? 100 : ((step + 1) / STEPS.length) * 100;

  if (!email || !token) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#101112] px-6 text-white">
        <div className="max-w-md text-center">
          <Image src="/mira-logo.svg" alt="MIRA" width={100} height={26} className="mx-auto mb-8" />
          <h1 className="text-xl font-semibold">Vamos retomar seu cadastro.</h1>
          <p className="mt-3 text-sm leading-6 text-[#a0a3aa]">Para proteger sua conta, precisamos confirmar novamente seu e-mail antes de continuar.</p>
          <button onClick={() => router.replace("/login")} className="mt-6 rounded-md bg-[#3577f1] px-5 py-3 text-sm font-medium">Voltar ao acesso</button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#101112] text-[#f1f2f3]">
      <div className="mx-auto grid min-h-screen w-full max-w-[1680px] grid-cols-1 lg:grid-cols-[minmax(460px,0.92fr)_minmax(560px,1.08fr)]">
        <section className="flex min-h-screen flex-col border-b border-[#292c32] px-5 py-6 sm:px-10 lg:border-b-0 lg:border-r lg:px-12 lg:py-8">
          <header className="flex items-center justify-between">
            <Image src="/mira-logo.svg" alt="MIRA" width={100} height={26} priority />
            <div className="flex items-center gap-2 text-[11px] text-[#8e949e]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#3577f1]" />
              Configuração da instituição
            </div>
          </header>

          <div className="mx-auto flex w-full max-w-[560px] flex-1 flex-col py-10 sm:py-14">
            <div className="mb-8">
              <div className="mb-3 flex items-center justify-between text-[11px] text-[#858b96]">
                <span>{mfaMode ? "Segurança da conta" : `${step + 1} de ${STEPS.length} etapas`}</span>
                <span>{mfaMode ? "Última etapa" : saveState === "saving" ? "Salvando…" : saveState === "error" ? "Não foi possível salvar" : "Progresso salvo"}</span>
              </div>
              <div className="h-[3px] overflow-hidden rounded-full bg-[#292c32]">
                <div className="h-full rounded-full bg-[#3577f1] transition-all duration-300" style={{ width: `${progress}%` }} />
              </div>
            </div>

            <div className="mb-7 flex items-start gap-3">
              <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[#343840] bg-[#1b1e23] text-[#8fb4ff]">
                <Sparkles className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8fb4ff]">MIRA · Assistente de configuração</p>
                <h1 className="mt-2 text-[22px] font-semibold leading-tight tracking-[-0.035em] text-[#f4f5f7]">
                  {mfaMode ? "Proteja seu acesso à MIRA." : STEPS[step].label}
                </h1>
                <p className="mt-2 max-w-[470px] text-[13px] leading-6 text-[#a0a3aa]">
                  {mfaMode
                    ? "Sua instituição foi cadastrada. Antes de entrar, configure a autenticação em duas etapas."
                    : step === 0
                      ? "Vou preparar seu ambiente de trabalho. Primeiro, quero conhecer a pessoa que vai administrar a instituição."
                      : step === 1
                        ? "Vou identificar sua instituição para organizar os dados e preparar um workspace adequado à sua operação."
                        : step === 2
                          ? "Encontrei as informações que você forneceu. Revise os dados antes de avançar."
                          : step === 3
                            ? "Com um pouco mais de contexto, consigo preparar uma estrutura que faça sentido para sua realidade."
                            : "Com base nas suas respostas, esta é a estrutura inicial que a MIRA recomenda. Você poderá ajustar tudo depois."}
                </p>
              </div>
            </div>

            {error ? <div role="alert" className="mb-5 rounded-lg border border-[#713b3b] bg-[#2b191b] px-4 py-3 text-[12px] leading-5 text-[#ffb4ae]">{error}</div> : null}

            {mfaMode ? (
              <form onSubmit={confirmMfa} className="space-y-5 rounded-xl border border-[#30343b] bg-[#15171b] p-5">
                {recoveryCodes ? (
                  <>
                    <div className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck className="h-4 w-4 text-[#8fb4ff]" /> Guarde seus códigos de recuperação</div>
                    <p className="text-xs leading-5 text-[#a0a3aa]">Use um destes códigos se perder acesso ao aplicativo autenticador. Cada código pode ser usado uma vez.</p>
                    <div className="grid grid-cols-2 gap-2">{recoveryCodes.map((code) => <code key={code} className="rounded-md border border-[#343840] bg-[#101112] px-2 py-2 text-center text-xs">{code}</code>)}</div>
                    <button type="button" onClick={() => navigator.clipboard.writeText(recoveryCodes.join("\n"))} className="text-xs font-medium text-[#8fb4ff]">Copiar códigos</button>
                    <button type="button" onClick={() => { window.sessionStorage.removeItem("mira_onboarding_token"); window.sessionStorage.removeItem("mira_onboarding_draft"); router.replace("/"); }} className="flex h-11 w-full items-center justify-center rounded-md bg-[#3577f1] text-sm font-medium text-white">Já guardei — entrar</button>
                  </>
                ) : (
                  <>
                    {mfaEnrollment ? (
                      <div className="space-y-3">
                        <p className="text-sm font-medium">1. Escaneie o QR Code no seu aplicativo autenticador.</p>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={mfaEnrollment.qr_code} alt="QR Code para configurar o autenticador" className="mx-auto h-44 w-44 rounded-lg bg-white p-2" />
                        <p className="break-all rounded-md bg-[#101112] p-3 font-mono text-[11px] text-[#c7cbd2]">{mfaEnrollment.secret}</p>
                        <p className="text-xs text-[#a0a3aa]">2. Digite o código de seis dígitos gerado pelo aplicativo.</p>
                      </div>
                    ) : <p className="text-sm text-[#a0a3aa]">Digite o código de seis dígitos do seu aplicativo autenticador.</p>}
                    <input value={mfaCode} onChange={(event) => setMfaCode(event.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" placeholder="000000" className="h-12 w-full rounded-md border border-[#343840] bg-[#101112] px-4 text-center text-xl tracking-[0.45em] outline-none focus:border-[#3577f1]" />
                    <button disabled={busy || mfaCode.length !== 6} className="flex h-11 w-full items-center justify-center gap-2 rounded-md bg-[#3577f1] text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Confirmar e entrar</button>
                  </>
                )}
              </form>
            ) : (
              <div className="space-y-5">
                {step === 0 ? (
                  <div className="grid gap-4 rounded-xl border border-[#30343b] bg-[#15171b] p-5 sm:grid-cols-2">
                    <Field label="Primeiro nome" value={draft.person.first_name} onChange={(v) => updatePerson("first_name", v)} placeholder="Seu primeiro nome" />
                    <Field label="Sobrenome" value={draft.person.last_name} onChange={(v) => updatePerson("last_name", v)} placeholder="Seu sobrenome" />
                    <div className="sm:col-span-2"><Field label="Cargo" value={draft.person.job_title} onChange={(v) => updatePerson("job_title", v)} placeholder="Ex.: Diretor de operações" hint="Opcional" /></div>
                    <div className="sm:col-span-2"><Field label="E-mail profissional confirmado" value={email} readOnly hint="Este e-mail foi confirmado e será usado como administrador inicial." /></div>
                  </div>
                ) : null}

                {step === 1 ? (
                  <div className="space-y-4 rounded-xl border border-[#30343b] bg-[#15171b] p-5">
                    <div className="rounded-lg border border-[#343840] bg-[#101112] px-3 py-3">
                      <p className="text-[11px] text-[#858b96]">Domínio do e-mail confirmado</p>
                      <p className="mt-1 text-sm font-medium text-[#e7e9ed]">{email.split("@")[1] || email}</p>
                      <p className="mt-1 text-[11px] leading-5 text-[#858b96]">Usaremos esse dado como pista para identificar a instituição. Ele não será tratado como comprovação de vínculo institucional.</p>
                    </div>
                    <Field label="Nome conhecido da instituição" value={draft.institution.trade_name} onChange={(v) => updateInstitution("trade_name", v)} placeholder="Ex.: Universidade Exemplo" />
                    <Field label="CNPJ" value={formatCnpj(draft.institution.cnpj)} onChange={(v) => updateInstitution("cnpj", v.replace(/\D/g, ""))} placeholder="00.000.000/0000-00" hint="Informe o CNPJ da mantenedora ou entidade responsável pelo cadastro." />
                    <Field label="Site institucional" value={draft.institution.website_url} onChange={(v) => updateInstitution("website_url", v)} placeholder="https://www.sua-instituicao.edu.br" />
                  </div>
                ) : null}

                {step === 2 ? (
                  <div className="space-y-4 rounded-xl border border-[#30343b] bg-[#15171b] p-5">
                    <div className="flex items-center gap-2 text-xs text-[#8fb4ff]"><CheckCircle2 className="h-4 w-4" /> Dados preparados para revisão</div>
                    <Field label="Razão social" value={draft.institution.legal_name} onChange={(v) => updateInstitution("legal_name", v)} placeholder="Razão social registrada" />
                    <Field label="Nome de exibição" value={draft.institution.trade_name} onChange={(v) => updateInstitution("trade_name", v)} placeholder="Nome da instituição" />
                    <Field label="Endereço do workspace" value={draft.institution.workspace_slug} onChange={(v) => { setSlugTouched(true); updateInstitution("workspace_slug", slugify(v)); }} placeholder="minha-instituicao" hint="Será usado no endereço interno do workspace." />
                    <Field label="País de faturamento" value="Brasil" readOnly />
                    <p className="text-[11px] leading-5 text-[#858b96]">A razão social e o CNPJ serão salvos como dados informados por você. A validação cadastral externa poderá ser feita depois.</p>
                  </div>
                ) : null}

                {step === 3 ? (
                  <div className="space-y-4 rounded-xl border border-[#30343b] bg-[#15171b] p-5">
                    <label className="block space-y-2">
                      <span className="text-[12px] font-medium text-[#c4c8d0]">Descreva sua instituição</span>
                      <textarea value={draft.context.description} onChange={(event) => updateContext("description", event.target.value)} rows={4} placeholder="Conte um pouco sobre a instituição, seus cursos, unidades e como acompanha a jornada dos alunos." className="w-full resize-y rounded-[7px] border border-[#343840] bg-[#17191e] px-3 py-3 text-[13px] leading-6 text-[#f4f5f7] outline-none placeholder:text-[#737985] focus:border-[#3577f1]" />
                    </label>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <SelectField label="Tipo de instituição" value={draft.context.institution_type} options={["Universidade", "Centro universitário", "Faculdade", "Grupo educacional", "Outra"]} onChange={(v) => updateContext("institution_type", v)} />
                      <SelectField label="Quantidade de alunos" value={draft.context.student_count_band} options={["Até 5 mil alunos", "5 mil a 20 mil", "20 mil a 50 mil", "50 mil a 100 mil", "Mais de 100 mil", "Não sei informar"]} onChange={(v) => updateContext("student_count_band", v)} />
                      <SelectField label="Quantidade de unidades/campi" value={draft.context.campus_count} options={["1", "2 a 5", "6 a 10", "11 a 25", "Mais de 25", "Não sei informar"]} onChange={(v) => updateContext("campus_count", v)} />
                    </div>
                    <div>
                      <p className="mb-2 text-[12px] font-medium text-[#c4c8d0]">Quais sistemas sua instituição utiliza?</p>
                      <div className="flex flex-wrap gap-2">{SYSTEMS.map((system) => {
                        const selected = draft.context.systems.includes(system);
                        return <button key={system} type="button" onClick={() => updateContext("systems", selected ? draft.context.systems.filter((v) => v !== system) : [...draft.context.systems, system])} className={`rounded-full border px-3 py-2 text-[11px] transition ${selected ? "border-[#3577f1] bg-[#1d3154] text-[#b8d0ff]" : "border-[#343840] bg-[#17191e] text-[#a0a3aa] hover:border-[#596171]"}`}>{selected ? "✓ " : ""}{system}</button>;
                      })}</div>
                    </div>
                    <div>
                      <p className="mb-2 text-[12px] font-medium text-[#c4c8d0]">O que você quer melhorar primeiro?</p>
                      <div className="space-y-2">{GOALS.map((goal) => {
                        const selected = draft.context.goals.includes(goal);
                        return <button key={goal} type="button" onClick={() => updateContext("goals", selected ? draft.context.goals.filter((v) => v !== goal) : [...draft.context.goals, goal])} className="flex w-full items-center justify-between rounded-lg border border-[#343840] bg-[#17191e] px-3 py-2.5 text-left text-xs text-[#d8dbe1]"><span>{goal}</span><span className={`flex h-4 w-4 items-center justify-center rounded border ${selected ? "border-[#3577f1] bg-[#3577f1] text-white" : "border-[#5a606b]"}`}>{selected ? <Check className="h-3 w-3" /> : null}</span></button>;
                      })}</div>
                    </div>
                  </div>
                ) : null}

                {step === 4 ? (
                  <div className="space-y-4 rounded-xl border border-[#30343b] bg-[#15171b] p-5">
                    <div>
                      <p className="text-sm font-semibold text-[#f1f2f3]">Estrutura proposta para o workspace</p>
                      <p className="mt-1 text-xs leading-5 text-[#a0a3aa]">Adaptada a {currentInstitution}. Você poderá ajustar os módulos e campos depois.</p>
                    </div>
                    <div className="space-y-2">{OBJECTS.map(({ id, description, icon: Icon }) => {
                      const selected = draft.workspace.objects.includes(id);
                      return <button key={id} type="button" onClick={() => setDraft((current) => ({ ...current, workspace: { objects: selected ? current.workspace.objects.filter((v) => v !== id) : [...current.workspace.objects, id] } }))} className={`flex w-full items-center gap-3 rounded-lg border px-3 py-3 text-left transition ${selected ? "border-[#3a5d9d] bg-[#1a2434]" : "border-[#343840] bg-[#17191e] hover:border-[#596171]"}`}>
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[#242933] text-[#9ebcff]"><Icon className="h-4 w-4" /></span>
                        <span className="min-w-0 flex-1"><span className="block text-xs font-semibold text-[#e7e9ed]">{id}</span><span className="mt-0.5 block text-[11px] text-[#9299a4]">{description}</span></span>
                        <span className={`flex h-4 w-4 items-center justify-center rounded border ${selected ? "border-[#3577f1] bg-[#3577f1] text-white" : "border-[#5a606b]"}`}>{selected ? <Check className="h-3 w-3" /> : null}</span>
                      </button>;
                    })}</div>
                    <div className="rounded-lg border border-[#343840] bg-[#101112] p-3">
                      <div className="flex items-center gap-2 text-xs font-semibold text-[#dce4f2]"><ShieldCheck className="h-4 w-4 text-[#8fb4ff]" /> Configuração segura</div>
                      <p className="mt-1 text-[11px] leading-5 text-[#858b96]">Sua organização terá um workspace isolado. A primeira pessoa cadastrada será administradora e poderá convidar outros membros.</p>
                    </div>
                  </div>
                ) : null}

                <div className="flex items-center justify-between gap-3 border-t border-[#292c32] pt-5">
                  <button type="button" onClick={() => step === 0 ? router.replace("/login") : setStep((value) => Math.max(0, value - 1))} className="inline-flex h-10 items-center gap-2 rounded-md px-3 text-xs font-medium text-[#a0a3aa] hover:bg-[#1b1e23] hover:text-white">
                    <ArrowLeft className="h-3.5 w-3.5" /> {step === 0 ? "Voltar ao acesso" : "Voltar"}
                  </button>
                  {step < STEPS.length - 1 ? (
                    <button type="button" disabled={!canContinue} onClick={() => setStep((value) => Math.min(STEPS.length - 1, value + 1))} className="inline-flex h-10 items-center gap-2 rounded-md bg-[#3577f1] px-4 text-xs font-semibold text-white transition hover:bg-[#266df0] disabled:cursor-not-allowed disabled:opacity-40">
                      Continuar <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  ) : (
                    <button type="button" disabled={!canContinue || busy} onClick={() => void finishOnboarding()} className="inline-flex h-10 items-center gap-2 rounded-md bg-[#3577f1] px-4 text-xs font-semibold text-white transition hover:bg-[#266df0] disabled:cursor-not-allowed disabled:opacity-40">
                      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                      Criar workspace
                    </button>
                  )}
                </div>
              </div>
            )}
            <p className="mt-auto pt-10 text-center text-[10px] text-[#666d78]">Seus dados são usados para configurar seu ambiente na MIRA. <span className="text-[#8fb4ff]">Privacidade e segurança</span></p>
          </div>
        </section>

        <aside className="hidden min-h-screen flex-col bg-[#f7f8fa] text-[#17191d] lg:flex">
          <div className="flex h-[68px] items-center justify-between border-b border-[#e7e9ed] px-8">
            <div className="flex items-center gap-2"><div className="flex h-7 w-7 items-center justify-center rounded-md bg-[#17191d] text-white"><Sparkles className="h-3.5 w-3.5" /></div><span className="text-sm font-semibold tracking-tight">MIRA</span><ChevronRight className="h-3.5 w-3.5 text-[#a0a4ac]" /><span className="text-xs text-[#737985]">Workspace</span></div>
            <span className="rounded-full border border-[#dce0e6] bg-white px-2.5 py-1 text-[10px] font-medium text-[#737985]">Prévia ao vivo</span>
          </div>
          <div className="flex flex-1 items-center justify-center p-8 xl:p-12">
            <div className="w-full max-w-[760px] overflow-hidden rounded-xl border border-[#e2e5e9] bg-white shadow-[0_12px_42px_rgba(20,30,50,0.08)]">
              <div className="flex items-center justify-between border-b border-[#eceef1] px-6 py-5">
                <div><p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8a9099]">Visão geral</p><h2 className="mt-1 text-lg font-semibold tracking-tight">{currentInstitution}</h2><p className="mt-1 text-[11px] text-[#858b96]">Seu ambiente está sendo preparado</p></div>
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#f0f3f8] text-[#4050cd]"><Building2 className="h-5 w-5" /></div>
              </div>
              <div className="grid grid-cols-3 gap-3 px-6 py-5">
                {[
                  { label: "Alunos acompanhados", value: "—", note: "Aguardando dados" },
                  { label: "Risco identificado", value: "—", note: "Aguardando análise" },
                  { label: "Intervenções", value: "—", note: "Aguardando configuração" },
                ].map((metric) => <div key={metric.label} className="rounded-lg border border-[#eceef1] p-3"><p className="text-[10px] text-[#858b96]">{metric.label}</p><p className="mt-3 text-2xl font-semibold text-[#22252b]">{metric.value}</p><p className="mt-1 text-[9px] text-[#9ba1aa]">{metric.note}</p></div>)}
              </div>
              <div className="grid grid-cols-[155px_1fr] border-t border-[#eceef1]">
                <nav className="space-y-1 border-r border-[#eceef1] p-3">
                  {["Visão geral", "Alunos", "Central de trabalho", "Intervenções", "Resultados", "Dados e integrações"].map((item, index) => <div key={item} className={`rounded-md px-2.5 py-2 text-[10px] ${index === 0 ? "bg-[#f0f3f8] font-semibold text-[#273b79]" : "text-[#777e88]"}`}>{item}</div>)}
                </nav>
                <div className="min-w-0 p-4">
                  <div className="flex items-center justify-between"><p className="text-xs font-semibold">Prioridades da instituição</p><span className="text-[9px] text-[#9ba1aa]">Prévia</span></div>
                  <div className="mt-3 space-y-2">
                    {["Alunos que precisam de atenção", "Intervenções em andamento", "Qualidade e atualização dos dados"].map((item, index) => <div key={item} className="flex items-center gap-2 rounded-md border border-[#eceef1] px-3 py-3"><span className={`h-2 w-2 rounded-full ${index === 0 ? "bg-[#e2a14a]" : index === 1 ? "bg-[#6f88ce]" : "bg-[#aeb5c0]"}`} /><span className="text-[10px] text-[#646b75]">{item}</span><span className="ml-auto text-[9px] text-[#a3a8b0]">—</span></div>)}
                  </div>
                  <div className="mt-4 rounded-md bg-[#f7f8fa] p-3"><p className="text-[10px] font-semibold">Estrutura do workspace</p><div className="mt-2 flex flex-wrap gap-1.5">{draft.workspace.objects.map((item) => <span key={item} className="rounded-full border border-[#e0e4e9] bg-white px-2 py-1 text-[9px] text-[#5d6570]">{item}</span>)}</div></div>
                </div>
              </div>
              <div className="flex items-center justify-between border-t border-[#eceef1] bg-[#fbfcfd] px-6 py-3 text-[10px] text-[#9299a4]"><span>{fullName} · Administrador</span><span className="inline-flex items-center gap-1"><LockKeyhole className="h-3 w-3" /> Ambiente isolado</span></div>
            </div>
          </div>
          <div className="flex items-center justify-between px-8 pb-6 text-[10px] text-[#969ca5]"><span>Prévia ilustrativa — indicadores reais após a conexão dos dados.</span><span>{Math.round(progress)}% configurado</span></div>
        </aside>
      </div>
    </main>
  );
}
