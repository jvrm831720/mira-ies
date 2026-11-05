"use client";

import { Suspense, useEffect, useMemo, useState, type FormEvent } from "react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Activity, ArrowLeft, ArrowRight, BookOpen, Building2, Check, CheckCircle2,
  ChevronRight, CircleHelp, Database, GraduationCap, Layers3, Loader2,
  LockKeyhole, Mail, Plus, ShieldCheck, Sparkles, Users, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import { completeOrganizationOnboarding } from "@/lib/onboarding-api";

type FormState = {
  firstName: string;
  lastName: string;
  jobTitle: string;
  organizationName: string;
  tradeName: string;
  cnpj: string;
  website: string;
  institutionType: string;
  studentRange: string;
  campuses: string;
  description: string;
  dataSources: string[];
};

const INITIAL: FormState = {
  firstName: "",
  lastName: "",
  jobTitle: "",
  organizationName: "",
  tradeName: "",
  cnpj: "",
  website: "",
  institutionType: "higher_education",
  studentRange: "",
  campuses: "",
  description: "",
  dataSources: [],
};

const SOURCE_OPTIONS = [
  { id: "totvs_rm", label: "TOTVS RM", detail: "ERP acadêmico" },
  { id: "lyceum", label: "Lyceum", detail: "ERP acadêmico" },
  { id: "sponte", label: "Sponte", detail: "Gestão acadêmica" },
  { id: "sophia", label: "Sophia", detail: "Gestão acadêmica" },
  { id: "moodle", label: "Moodle", detail: "Ambiente virtual" },
  { id: "canvas", label: "Canvas", detail: "Ambiente virtual" },
  { id: "omie", label: "Omie", detail: "Financeiro" },
  { id: "spreadsheets", label: "Planilhas", detail: "Excel ou CSV" },
  { id: "other", label: "Outro sistema", detail: "Integração ou API" },
];

const STEP_LABELS = ["Sobre você", "Instituição", "Contexto", "Estrutura"];

function OnboardingExperience() {
  const router = useRouter();
  const params = useSearchParams();
  const email = (params.get("email") || "").trim().toLowerCase();
  const [onboardingToken, setOnboardingToken] = useState("");
  const [form, setForm] = useState<FormState>(INITIAL);
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mfaTicket, setMfaTicket] = useState("");
  const [mfaEnrollment, setMfaEnrollment] = useState<{ secret: string; qr_code: string } | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [mfaLoading, setMfaLoading] = useState(false);

  useEffect(() => {
    const ticket = window.sessionStorage.getItem("mira_onboarding_token") || "";
    setOnboardingToken(ticket);
  }, []);

  const progress = step === 0 ? 0 : step === 1 ? 1 : step === 2 ? 2 : 3;
  const institutionLabel = form.tradeName.trim() || form.organizationName.trim() || "Sua instituição";
  const descriptionPreview = form.description.trim() ||
    "A MIRA vai organizar os dados acadêmicos e operacionais da instituição para apoiar decisões de permanência estudantil.";

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setError("");
  }

  function toggleSource(id: string) {
    setForm((current) => ({
      ...current,
      dataSources: current.dataSources.includes(id)
        ? current.dataSources.filter((item) => item !== id)
        : [...current.dataSources, id],
    }));
  }

  function canContinue() {
    if (step === 0) return form.firstName.trim().length > 0 && form.lastName.trim().length > 0;
    if (step === 1) return form.organizationName.trim().length >= 2;
    if (step === 2) return true;
    return true;
  }

  async function finish() {
    setError("");
    if (!onboardingToken) {
      setError("Sua validação de e-mail não está mais disponível. Volte ao acesso e confirme seu e-mail novamente.");
      return;
    }
    setLoading(true);
    try {
      const result = await completeOrganizationOnboarding({
        onboarding_token: onboardingToken,
        email,
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
        job_title: form.jobTitle.trim(),
        organization_name: form.organizationName.trim(),
        trade_name: form.tradeName.trim(),
        cnpj: form.cnpj.replace(/\D/g, ""),
        website: form.website.trim(),
        institution_type: form.institutionType,
        student_range: form.studentRange,
        campuses: form.campuses,
        description: form.description.trim(),
        data_sources: form.dataSources,
      });
      window.sessionStorage.removeItem("mira_onboarding_token");
      if ("mfa_enrollment_required" in result || "mfa_required" in result) {
        const challenge = result.challenge_token;
        setMfaTicket(challenge);
        const enrollment = await api.beginRequiredMfaEnrollment(challenge);
        setMfaEnrollment(enrollment);
        return;
      }
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível criar seu workspace. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }

  async function confirmMfa(event: FormEvent) {
    event.preventDefault();
    setError("");
    setMfaLoading(true);
    try {
      const result = await api.confirmRequiredMfaEnrollment(mfaTicket, mfaCode);
      setAccessToken(result.access_token);
      setRecoveryCodes(result.recovery_codes || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível confirmar o autenticador.");
    } finally {
      setMfaLoading(false);
    }
  }

  const selectedSources = useMemo(
    () => SOURCE_OPTIONS.filter((source) => form.dataSources.includes(source.id)),
    [form.dataSources],
  );

  if (!email) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-white px-6">
        <section className="max-w-md text-center">
          <Image src="/mira-logo.svg" alt="MIRA" width={100} height={26} className="mx-auto mb-8 brightness-0" />
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-950">Vamos recomeçar?</h1>
          <p className="mt-3 text-sm leading-6 text-neutral-500">Para iniciar a configuração da sua instituição, confirme seu e-mail profissional.</p>
          <Button className="mt-6" onClick={() => router.replace("/login")}>Voltar ao acesso</Button>
        </section>
      </main>
    );
  }

  if (mfaEnrollment && !recoveryCodes) {
    return (
      <main className="min-h-screen bg-white px-5 py-10 text-neutral-950">
        <div className="mx-auto max-w-lg">
          <Image src="/mira-logo.svg" alt="MIRA" width={100} height={26} className="mb-12 brightness-0" />
          <div className="rounded-2xl border border-neutral-200 p-7">
            <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-xl bg-neutral-100"><ShieldCheck className="h-5 w-5" /></div>
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-neutral-400">Última etapa de segurança</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight">Proteja seu acesso.</h1>
            <p className="mt-2 text-sm leading-6 text-neutral-500">A MIRA exige autenticação em duas etapas para todas as contas. Escaneie o QR Code com seu aplicativo autenticador.</p>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={mfaEnrollment.qr_code} alt="QR Code para configurar o autenticador" className="mx-auto my-6 h-48 w-48 rounded-xl border border-neutral-200 bg-white p-2" />
            <p className="mb-2 text-xs text-neutral-500">Ou insira esta chave manualmente</p>
            <code className="block break-all rounded-lg bg-neutral-50 p-3 text-xs text-neutral-700">{mfaEnrollment.secret}</code>
            <form onSubmit={confirmMfa} className="mt-6 space-y-4">
              <label htmlFor="mfa-code" className="block text-sm font-medium">Código do aplicativo</label>
              <Input id="mfa-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={mfaCode} onChange={(event) => setMfaCode(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="000000" className="h-12 text-center text-xl tracking-[0.5em]" required />
              {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
              <Button type="submit" disabled={mfaLoading || mfaCode.length !== 6} className="h-12 w-full">{mfaLoading ? "Verificando…" : "Confirmar e entrar"}</Button>
            </form>
          </div>
        </div>
      </main>
    );
  }

  if (recoveryCodes) {
    return (
      <main className="min-h-screen bg-white px-5 py-10 text-neutral-950">
        <div className="mx-auto max-w-lg">
          <Image src="/mira-logo.svg" alt="MIRA" width={100} height={26} className="mb-12 brightness-0" />
          <div className="rounded-2xl border border-neutral-200 p-7">
            <CheckCircle2 className="h-8 w-8 text-emerald-600" />
            <h1 className="mt-3 text-2xl font-semibold">Sua instituição está pronta.</h1>
            <p className="mt-2 text-sm leading-6 text-neutral-500">Guarde estes códigos de recuperação em um local seguro. Cada código pode ser usado uma única vez.</p>
            <div className="my-5 grid grid-cols-2 gap-2">{recoveryCodes.map((code) => <code key={code} className="rounded-lg bg-neutral-50 p-3 text-center text-xs">{code}</code>)}</div>
            <Button variant="outline" className="w-full" onClick={() => void navigator.clipboard.writeText(recoveryCodes.join("\n"))}>Copiar códigos</Button>
            <Button className="mt-3 w-full" onClick={() => router.replace("/")}>Entrar na MIRA <ArrowRight className="ml-2 h-4 w-4" /></Button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#fafafa] text-neutral-950 lg:h-screen lg:overflow-hidden">
      <header className="flex h-[68px] items-center justify-between border-b border-neutral-200 bg-white px-5 lg:px-8">
        <Image src="/mira-logo.svg" alt="MIRA" width={94} height={25} className="brightness-0" priority />
        <div className="flex items-center gap-2 text-xs text-neutral-400"><LockKeyhole className="h-3.5 w-3.5" /> Configuração segura</div>
      </header>

      <div className="grid min-h-[calc(100vh-68px)] lg:h-[calc(100vh-68px)] lg:grid-cols-[minmax(420px,0.9fr)_minmax(560px,1.1fr)]">
        <section className="flex min-h-[700px] flex-col border-r border-neutral-200 bg-white lg:min-h-0">
          <div className="mx-auto flex w-full max-w-[620px] flex-1 flex-col px-6 pb-8 pt-8 sm:px-10 lg:overflow-y-auto lg:px-14 lg:pt-10">
            <div className="mb-8 flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-medium text-neutral-500"><Sparkles className="h-4 w-4 text-neutral-800" /> Configuração da MIRA</div>
              <span className="text-xs text-neutral-400">{step + 1} de 4</span>
            </div>
            <div className="mb-10 flex gap-1.5" aria-label="Progresso do onboarding">
              {STEP_LABELS.map((label, index) => <div key={label} className={`h-1 flex-1 rounded-full ${index <= progress ? "bg-neutral-950" : "bg-neutral-200"}`} />)}
            </div>

            {step === 0 && (
              <div className="animate-in fade-in duration-300">
                <p className="mb-3 text-xs font-medium uppercase tracking-[0.13em] text-neutral-400">Sobre você</p>
                <h1 className="max-w-lg text-[30px] font-semibold leading-[1.12] tracking-[-0.045em] sm:text-[34px]">Vamos começar por você.</h1>
                <p className="mt-3 max-w-md text-sm leading-6 text-neutral-500">Quero entender quem está configurando a MIRA para sua instituição.</p>
                <div className="mt-8 space-y-5">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Nome" required><Input autoFocus value={form.firstName} onChange={(e) => update("firstName", e.target.value)} placeholder="Seu primeiro nome" className="h-11" /></Field>
                    <Field label="Sobrenome" required><Input value={form.lastName} onChange={(e) => update("lastName", e.target.value)} placeholder="Seu sobrenome" className="h-11" /></Field>
                  </div>
                  <Field label="Cargo" hint="Opcional"><Input value={form.jobTitle} onChange={(e) => update("jobTitle", e.target.value)} placeholder="Ex.: Diretor de operações" className="h-11" /></Field>
                  <Field label="E-mail profissional"><div className="flex h-11 items-center gap-3 rounded-lg border border-neutral-200 bg-neutral-50 px-3 text-sm text-neutral-500"><Mail className="h-4 w-4" /><span className="truncate">{email}</span><Check className="ml-auto h-4 w-4 text-emerald-600" /></div></Field>
                </div>
                <p className="mt-6 text-xs leading-5 text-neutral-400">Seu e-mail foi confirmado. Ele será usado como identidade principal da sua conta.</p>
              </div>
            )}

            {step === 1 && (
              <div className="animate-in fade-in duration-300">
                <p className="mb-3 text-xs font-medium uppercase tracking-[0.13em] text-neutral-400">Sua instituição</p>
                <h1 className="max-w-lg text-[30px] font-semibold leading-[1.12] tracking-[-0.045em] sm:text-[34px]">Vamos identificar sua instituição.</h1>
                <p className="mt-3 max-w-md text-sm leading-6 text-neutral-500">Com essas informações, vamos preparar o espaço de trabalho correto para sua operação.</p>
                <div className="mt-8 space-y-5">
                  <Field label="Nome da instituição" required><Input autoFocus value={form.organizationName} onChange={(e) => update("organizationName", e.target.value)} placeholder="Ex.: Universidade Exemplo" className="h-11" /></Field>
                  <Field label="Nome de exibição" hint="Opcional"><Input value={form.tradeName} onChange={(e) => update("tradeName", e.target.value)} placeholder="Como sua instituição é conhecida" className="h-11" /></Field>
                  <Field label="Site institucional" hint="Opcional"><Input value={form.website} onChange={(e) => update("website", e.target.value)} placeholder="www.sua instituicao.edu.br" className="h-11" /></Field>
                  <Field label="CNPJ" hint="Opcional nesta etapa"><Input value={form.cnpj} onChange={(e) => update("cnpj", e.target.value.replace(/[^\d./-]/g, "").slice(0, 18))} placeholder="00.000.000/0000-00" className="h-11" /></Field>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Quantidade aproximada de alunos"><select value={form.studentRange} onChange={(e) => update("studentRange", e.target.value)} className="h-11 w-full rounded-lg border border-neutral-200 bg-white px-3 text-sm outline-none focus:border-neutral-500"><option value="">Selecione</option><option value="under_1000">Até 1.000</option><option value="1000_5000">1.000 a 5.000</option><option value="5000_15000">5.000 a 15.000</option><option value="15000_50000">15.000 a 50.000</option><option value="over_50000">Mais de 50.000</option></select></Field>
                    <Field label="Unidades ou campi"><select value={form.campuses} onChange={(e) => update("campuses", e.target.value)} className="h-11 w-full rounded-lg border border-neutral-200 bg-white px-3 text-sm outline-none focus:border-neutral-500"><option value="">Selecione</option><option value="1">1 unidade</option><option value="2_5">2 a 5</option><option value="6_20">6 a 20</option><option value="over_20">Mais de 20</option></select></Field>
                  </div>
                </div>
                <p className="mt-5 text-xs leading-5 text-neutral-400">O CNPJ não é obrigatório para conhecer a MIRA. Ele poderá ser validado e complementado posteriormente.</p>
              </div>
            )}

            {step === 2 && (
              <div className="animate-in fade-in duration-300">
                <p className="mb-3 text-xs font-medium uppercase tracking-[0.13em] text-neutral-400">Contexto institucional</p>
                <h1 className="max-w-lg text-[30px] font-semibold leading-[1.12] tracking-[-0.045em] sm:text-[34px]">Agora, vamos entender como sua instituição funciona.</h1>
                <p className="mt-3 max-w-md text-sm leading-6 text-neutral-500">Revise o perfil inicial e conte um pouco sobre a operação. Você poderá ajustar essas informações depois.</p>
                <div className="mt-7 rounded-xl border border-neutral-200 bg-neutral-50 p-4">
                  <div className="flex items-center gap-2 text-sm font-medium"><Building2 className="h-4 w-4 text-neutral-500" /> {institutionLabel}</div>
                  <p className="mt-2 text-xs leading-5 text-neutral-500">Perfil inicial criado com as informações que você forneceu. A MIRA não consulta fontes externas nesta etapa.</p>
                </div>
                <div className="mt-6 space-y-5">
                  <Field label="Tipo de instituição">
                    <select value={form.institutionType} onChange={(e) => update("institutionType", e.target.value)} className="h-11 w-full rounded-lg border border-neutral-200 bg-white px-3 text-sm outline-none focus:border-neutral-500">
                      <option value="higher_education">Instituição de Ensino Superior</option>
                      <option value="university_center">Centro universitário</option>
                      <option value="university">Universidade</option>
                      <option value="college">Faculdade</option>
                      <option value="technical">Ensino técnico e profissionalizante</option>
                      <option value="other">Outro tipo de instituição</option>
                    </select>
                  </Field>
                  <Field label="Descreva sua instituição e seus principais desafios" hint="Opcional">
                    <textarea value={form.description} onChange={(e) => update("description", e.target.value)} rows={5} maxLength={2000} placeholder="Ex.: Somos uma instituição com cursos presenciais e EAD. Queremos identificar alunos com risco de evasão, organizar ações de permanência e acompanhar os resultados..." className="w-full resize-y rounded-lg border border-neutral-200 bg-white px-3 py-3 text-sm leading-6 outline-none transition focus:border-neutral-500" />
                  </Field>
                </div>
              </div>
            )}

            {step === 3 && (
              <div className="animate-in fade-in duration-300">
                <p className="mb-3 text-xs font-medium uppercase tracking-[0.13em] text-neutral-400">Estrutura do workspace</p>
                <h1 className="max-w-lg text-[30px] font-semibold leading-[1.12] tracking-[-0.045em] sm:text-[34px]">Esta é a estrutura inicial da sua MIRA.</h1>
                <p className="mt-3 max-w-md text-sm leading-6 text-neutral-500">Com base no contexto informado, propomos uma estrutura para organizar a operação. Você poderá ajustar as integrações e os dados depois.</p>
                <div className="mt-7 space-y-3">
                  <StructureItem icon={<GraduationCap className="h-4 w-4" />} title="Alunos" description="Pessoas acompanhadas pela instituição e seus históricos." />
                  <StructureItem icon={<BookOpen className="h-4 w-4" />} title="Cursos e matrículas" description="Vínculos acadêmicos, cursos, períodos e situação de matrícula." />
                  <StructureItem icon={<Activity className="h-4 w-4" />} title="Sinais e indicadores" description="Informações que ajudam a compreender risco e permanência." />
                  <StructureItem icon={<Layers3 className="h-4 w-4" />} title="Intervenções" description="Ações realizadas, responsáveis, status e resultados." />
                </div>
                <div className="mt-6">
                  <div className="mb-3 flex items-center justify-between"><p className="text-sm font-medium">Onde estão seus dados hoje?</p><span className="text-xs text-neutral-400">Opcional</span></div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {SOURCE_OPTIONS.map((source) => {
                      const selected = form.dataSources.includes(source.id);
                      return <button type="button" key={source.id} onClick={() => toggleSource(source.id)} className={`flex items-center gap-3 rounded-lg border p-3 text-left transition ${selected ? "border-neutral-900 bg-neutral-50" : "border-neutral-200 bg-white hover:border-neutral-400"}`}>
                        <span className={`flex h-5 w-5 items-center justify-center rounded border ${selected ? "border-neutral-900 bg-neutral-900 text-white" : "border-neutral-300 text-transparent"}`}><Check className="h-3 w-3" /></span>
                        <span className="min-w-0"><span className="block text-sm font-medium">{source.label}</span><span className="block text-xs text-neutral-400">{source.detail}</span></span>
                      </button>;
                    })}
                  </div>
                </div>
                <div className="mt-5 rounded-lg border border-neutral-200 p-3 text-xs leading-5 text-neutral-500">
                  <CircleHelp className="mr-1 inline h-3.5 w-3.5" /> Selecionar um sistema não cria uma conexão. As integrações serão configuradas depois, com autorização da instituição.
                </div>
              </div>
            )}

            {error && <p role="alert" className="mt-6 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

            <div className="mt-auto flex items-center justify-between gap-3 border-t border-neutral-100 pt-6">
              <Button type="button" variant="ghost" onClick={() => step === 0 ? router.replace("/login") : setStep((current) => current - 1)} className="text-neutral-500">
                <ArrowLeft className="mr-2 h-4 w-4" /> {step === 0 ? "Voltar" : "Anterior"}
              </Button>
              {step < 3 ? (
                <Button type="button" disabled={!canContinue()} onClick={() => { setError(""); setStep((current) => current + 1); }} className="h-11 px-5">
                  Continuar <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              ) : (
                <Button type="button" disabled={loading} onClick={() => void finish()} className="h-11 px-5">
                  {loading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Criando workspace…</> : <>Criar workspace <ArrowRight className="ml-2 h-4 w-4" /></>}
                </Button>
              )}
            </div>
          </div>
          <p className="px-6 pb-5 text-center text-[11px] text-neutral-400">Seus dados são usados para configurar seu ambiente institucional na MIRA.</p>
        </section>

        <aside className="hidden min-h-0 flex-col bg-[#f7f7f7] p-7 lg:flex xl:p-10">
          <div className="mb-6 flex items-center justify-between">
            <div><p className="text-xs font-medium uppercase tracking-[0.12em] text-neutral-400">Prévia do workspace</p><p className="mt-1 text-sm font-medium text-neutral-800">{institutionLabel}</p></div>
            <span className="rounded-full border border-neutral-200 bg-white px-3 py-1 text-[11px] text-neutral-500">Visualização</span>
          </div>
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-[0_12px_40px_rgba(0,0,0,0.04)]">
            <div className="flex h-12 items-center gap-2 border-b border-neutral-100 px-4">
              <div className="flex gap-1.5"><span className="h-2 w-2 rounded-full bg-neutral-200" /><span className="h-2 w-2 rounded-full bg-neutral-200" /><span className="h-2 w-2 rounded-full bg-neutral-200" /></div>
              <div className="ml-3 flex items-center gap-2 text-xs font-medium text-neutral-700"><span className="flex h-5 w-5 items-center justify-center rounded bg-neutral-950 text-[9px] font-semibold text-white">{institutionLabel.slice(0,1).toUpperCase()}</span>{institutionLabel}</div>
              <div className="ml-auto flex h-7 w-7 items-center justify-center rounded-full bg-neutral-100 text-[10px] font-medium">{form.firstName.slice(0,1).toUpperCase() || "U"}</div>
            </div>
            <div className="flex min-h-0 flex-1">
              <nav className="hidden w-[170px] shrink-0 border-r border-neutral-100 bg-[#fcfcfc] p-3 xl:block">
                <p className="mb-3 px-2 text-[9px] font-semibold uppercase tracking-[0.12em] text-neutral-400">Workspace</p>
                {["Visão geral", "Alunos", "Central de trabalho", "Intervenções", "Resultados", "Dados e integrações"].map((item, index) => <div key={item} className={`mb-1 flex items-center gap-2 rounded-md px-2 py-2 text-[10px] ${index === 0 ? "bg-neutral-100 font-semibold text-neutral-900" : "text-neutral-400"}`}><span className="h-1.5 w-1.5 rounded-full bg-current" />{item}</div>)}
              </nav>
              <div className="min-w-0 flex-1 overflow-hidden p-5 xl:p-7">
                <div className="flex items-start justify-between gap-3"><div><p className="text-[9px] font-medium uppercase tracking-[0.12em] text-neutral-400">Visão geral</p><h2 className="mt-1 text-lg font-semibold tracking-tight">Bom dia{form.firstName ? `, ${form.firstName}` : ""}.</h2><p className="mt-1 text-[10px] text-neutral-400">Sua operação de permanência em um só lugar.</p></div><span className="rounded-md border border-neutral-200 px-2 py-1 text-[9px] text-neutral-400">Prévia</span></div>
                <div className="mt-5 grid grid-cols-2 gap-2 xl:grid-cols-4">
                  {[{label:"Alunos",icon:<Users className="h-3 w-3" />},{label:"Em atenção",icon:<Activity className="h-3 w-3" />},{label:"Intervenções",icon:<Layers3 className="h-3 w-3" />},{label:"Resultados",icon:<CheckCircle2 className="h-3 w-3" />}].map((item) => <div key={item.label} className="rounded-lg border border-neutral-100 p-3"><div className="flex items-center gap-1.5 text-[9px] text-neutral-400">{item.icon}{item.label}</div><div className="mt-3 text-lg font-semibold text-neutral-300">—</div><p className="mt-1 text-[8px] text-neutral-300">Aguardando dados</p></div>)}
                </div>
                <div className="mt-4 grid gap-3 xl:grid-cols-[1.2fr_0.8fr]">
                  <div className="rounded-lg border border-neutral-100 p-3"><div className="flex items-center justify-between"><p className="text-[10px] font-semibold">Prioridades da operação</p><span className="text-[8px] text-neutral-300">Prévia</span></div><div className="mt-4 space-y-3">{["Sinais de risco", "Ações pendentes", "Acompanhamento"].map((item) => <div key={item} className="flex items-center gap-2"><span className="h-6 w-6 rounded-md bg-neutral-100" /><div className="flex-1"><div className="h-2 w-24 rounded bg-neutral-100" /><p className="mt-1 text-[8px] text-neutral-300">{item}</p></div><ChevronRight className="h-3 w-3 text-neutral-300" /></div>)}</div></div>
                  <div className="rounded-lg border border-neutral-100 p-3"><p className="text-[10px] font-semibold">Qualidade dos dados</p><div className="mt-4 flex h-20 items-center justify-center rounded-md bg-neutral-50"><Database className="h-5 w-5 text-neutral-200" /></div><p className="mt-2 text-[8px] text-neutral-300">Aguardando primeira conexão</p></div>
                </div>
                <div className="mt-4 rounded-lg border border-dashed border-neutral-200 bg-neutral-50/60 p-4">
                  <div className="flex items-center gap-2"><Sparkles className="h-3.5 w-3.5 text-neutral-400" /><p className="text-[10px] font-semibold">Seu ambiente está tomando forma</p></div>
                  <p className="mt-2 text-[9px] leading-4 text-neutral-400">{descriptionPreview}</p>
                  {selectedSources.length > 0 && <div className="mt-3 flex flex-wrap gap-1">{selectedSources.slice(0,4).map((source) => <span key={source.id} className="rounded-full border border-neutral-200 bg-white px-2 py-1 text-[8px] text-neutral-500">{source.label}</span>)}</div>}
                </div>
              </div>
            </div>
            <div className="flex h-9 items-center justify-between border-t border-neutral-100 px-4 text-[8px] text-neutral-300"><span>MIRA · Inteligência para permanência estudantil</span><span>Dados demonstrativos não exibidos</span></div>
          </div>
          <p className="mt-4 text-center text-[10px] text-neutral-400">A prévia será preenchida com dados reais após a configuração e a conexão das fontes.</p>
        </aside>
      </div>
    </main>
  );
}

function Field({ label, hint, required, children }: { label: string; hint?: string; required?: boolean; children: React.ReactNode }) {
  return <div className="space-y-2"><div className="flex items-center justify-between gap-2"><label className="text-[13px] font-medium text-neutral-800">{label}{required && <span className="ml-1 text-red-500">*</span>}</label>{hint && <span className="text-[11px] text-neutral-400">{hint}</span>}</div>{children}</div>;
}

function StructureItem({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  return <div className="flex items-start gap-3 rounded-xl border border-neutral-200 bg-white p-3.5"><div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-neutral-100 text-neutral-600">{icon}</div><div className="min-w-0"><p className="text-sm font-medium">{title}</p><p className="mt-1 text-xs leading-5 text-neutral-500">{description}</p></div><Check className="ml-auto mt-1 h-4 w-4 shrink-0 text-neutral-400" /></div>;
}

export default function OnboardingPage() {
  return <Suspense fallback={<main className="min-h-screen bg-white" />}><OnboardingExperience /></Suspense>;
}
