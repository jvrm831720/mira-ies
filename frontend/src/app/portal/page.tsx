"use client";

import { useEffect, useState, type FormEvent } from "react";
import { StudentServicesPanel } from "./student-services-panel";
import { AcademicOperationsPanel } from "./academic-operations-panel";
import { PortalShell, type PortalSection } from "./components/portal-shell";
import { serviceStatusLabel, serviceStatusTone } from "./lib/service-status";
import {
  ArrowRight, BookOpen, GraduationCap, LockKeyhole,
  LogOut, ShieldCheck, Wallet, CalendarDays, AlertCircle, Loader2,
} from "@/components/ui/icons";

type StudentProfile = {
  student_id: string;
  name: string;
  registration: string;
  course: string | null;
  campus: string | null;
  semester: number | null;
  class_name: string | null;
  academic_status: string | null;
  attendance_percentage: number | null;
  grade_average: number | null;
  institution: string;
};
type RecordKind = "enrollment" | "attendance" | "assessment" | "fee";
type RecentServiceRequest = { id: string; subject: string; status: string; created_at: string };
type ExtraTab = "schedule" | "calendar" | "report-card" | "attendance";
type AcademicItem = {
  id?: string;
  class_id?: string;
  class_code?: string;
  title?: string;
  topic?: string | null;
  subject?: string;
  teacher_name?: string | null;
  starts_at?: string;
  ends_at?: string;
  location?: string | null;
  room?: string | null;
  assessment?: string;
  score?: string;
  max_score?: string;
  term_label?: string;
  present?: number;
  absent?: number;
  excused?: number;
  unrecorded?: number;
};
type ExtraResponse = { items: AcademicItem[]; note?: string };
type AcademicRecord = {
  id: string;
  kind: RecordKind;
  source: string;
  title: string;
  academic_period: string | null;
  status: string | null;
  event_date: string | null;
  grade: string | null;
  max_grade: string | null;
  amount: string | null;
  due_date: string | null;
  currency: string | null;
  financial_snapshot_only: boolean;
};

const sections: { id: RecordKind; label: string; icon: typeof GraduationCap }[] = [
  { id: "enrollment", label: "Matrículas", icon: GraduationCap },
  { id: "attendance", label: "Frequência", icon: CalendarDays },
  { id: "assessment", label: "Avaliações", icon: BookOpen },
  { id: "fee", label: "Mensalidades", icon: Wallet },
];

async function portalFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch("/api/v1/student-portal" + path, {
    ...init,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.method && init.method !== "GET" ? { "X-Mira-Portal-Action": "1" } : {}),
    },
  });
  if (!response.ok) {
    throw Object.assign(new Error(
      response.status === 503
        ? "O Portal do Aluno está em homologação nesta instituição."
        : response.status === 401
          ? "Convite ou sessão inválida ou expirada."
          : "Não foi possível concluir a solicitação."
    ), { status: response.status });
  }
  return response.json() as Promise<T>;
}
function value(raw: string | number | null | undefined): string {
  if (raw === null || raw === undefined || raw === "") return "Não informado";
  return String(raw);
}
function money(amount: string | null, currency: string | null): string {
  if (amount === null || currency !== "BRL") return "Não informado";
  const number = Number(amount);
  if (!Number.isFinite(number)) return "Não informado";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(number);
}
function formatTimestamp(raw?: string): string {
  if (!raw) return "Data não informada";
  const time = new Date(raw);
  if (Number.isNaN(time.getTime())) return "Data não informada";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo", dateStyle: "medium", timeStyle: "short",
  }).format(time);
}
function academicDescription(tab: ExtraTab, item: AcademicItem): string {
  if (tab === "report-card") return "Nota: " + value(item.score) + " / " + value(item.max_score) + " · " + value(item.term_label);
  if (tab === "attendance") return (
    "Presentes: " + value(item.present) + " · Faltas registradas: " + value(item.absent) +
    " · Justificadas: " + value(item.excused) + " · Sem registro: " + value(item.unrecorded)
  );
  return formatTimestamp(item.starts_at) + (item.room || item.location ? " · " + (item.room || item.location) : "");
}
function academicTitle(tab: ExtraTab, item: AcademicItem): string {
  if (tab === "schedule") return item.subject || "Aula" ;
  if (tab === "report-card") return (item.subject ? item.subject + " · " : "") + (item.assessment || "Avaliação");
  if (tab === "attendance") return (item.subject || "Disciplina") + (item.class_code ? " · Turma " + item.class_code : "");
  return item.title || "Evento acadêmico";
}
function date(raw: string | null): string {
  if (!raw || !/^\d{4}-\d{2}-\d{2}$/.test(raw)) return "Não informado";
  const [year, month, day] = raw.split("-");
  return day + "/" + month + "/" + year;
}
function recordDescription(record: AcademicRecord): string {
  if (record.kind === "attendance") return "Data: " + date(record.event_date);
  if (record.kind === "assessment") {
    return "Nota: " + value(record.grade) + " / " + value(record.max_grade);
  }
  if (record.kind === "fee") return money(record.amount, record.currency) + " · Vencimento: " + date(record.due_date);
  return record.academic_period ? "Período " + record.academic_period : "Período não informado";
}

export default function StudentPortalPage() {
  const [student, setStudent] = useState<StudentProfile | null>(null);
  const [token, setToken] = useState("");
  const [tab, setTab] = useState<RecordKind>("enrollment");
  const [activeSection, setActiveSection] = useState<PortalSection>("home");
  const [records, setRecords] = useState<AcademicRecord[]>([]);
  const [recentRequests, setRecentRequests] = useState<RecentServiceRequest[] | null>(null);
  const [extraTab, setExtraTab] = useState<ExtraTab>("schedule");
  const [extraRecords, setExtraRecords] = useState<AcademicItem[]>([]);
  const [extraMessage, setExtraMessage] = useState<string | null>(null);
  const [extraLoading, setExtraLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recordsError, setRecordsError] = useState<string | null>(null);

  useEffect(() => {
    // Invitation fragments are never sent to the server as part of an HTTP URL.
    const fragment = window.location.hash.match(/^#invite=([A-Za-z0-9._-]+)$/);
    if (fragment) {
      setToken(fragment[1]);
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
    let alive = true;
    portalFetch<{ student: StudentProfile }>("/me")
      .then((data) => { if (alive) setStudent(data.student); })
      .catch((cause: unknown) => {
        if (alive && (cause as { status?: number }).status === 503) {
          setError("Portal em homologação. O acesso ainda não foi habilitado.");
        }
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!student) return;
    let active = true;
    setRecords([]);
    setRecordsError(null);
    setRecordsLoading(true);
    portalFetch<{ items: AcademicRecord[] }>("/records?kind=" + tab)
      .then((result) => { if (active) setRecords(result.items); })
      .catch((cause: unknown) => {
        if (active) {
          setRecordsError("Não foi possível consultar os registros agora.");
          if ((cause as { status?: number }).status === 401) setStudent(null);
        }
      })
      .finally(() => { if (active) setRecordsLoading(false); });
    return () => { active = false; };
  }, [student, tab]);

  useEffect(() => {
    if (!student) return;
    let active = true;
    setExtraRecords([]);
    setExtraMessage(null);
    setExtraLoading(true);
    portalFetch<ExtraResponse>("/" + extraTab)
      .then((result) => {
        if (active) {
          setExtraRecords(result.items);
          setExtraMessage(result.note || null);
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setExtraMessage((cause as { status?: number }).status === 503
            ? "Este recurso acadêmico ainda está em homologação."
            : "Não foi possível consultar esta seção.");
          if ((cause as { status?: number }).status === 401) setStudent(null);
        }
      })
      .finally(() => { if (active) setExtraLoading(false); });
    return () => { active = false; };
  }, [student, extraTab]);

  useEffect(() => {
    if (!student || activeSection !== "home") return;
    let active = true;
    setRecentRequests(null);
    fetch("/api/v1/student-portal/services/requests", {
      credentials: "same-origin", cache: "no-store",
    }).then(response => response.ok ? response.json() as Promise<{items: RecentServiceRequest[]}> : null)
      .then(result => {
        if (active) setRecentRequests(Array.isArray(result?.items) ? result.items.slice(0, 3) : null);
      })
      .catch(() => { if (active) setRecentRequests(null); });
    return () => { active = false; };
  }, [student, activeSection]);

  async function claim(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await portalFetch<{ student: StudentProfile }>("/claim", {
        method: "POST", body: JSON.stringify({ token: token.trim() }),
      });
      setToken("");
      setStudent(result.student);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível entrar no portal.");
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    setBusy(true);
    try {
      await portalFetch("/logout", { method: "POST" });
    } catch {
      // The session may already be expired; the browser must not retain data.
    } finally {
      setStudent(null); setRecords([]); setToken(""); setBusy(false);
    }
  }

  if (loading) {
    return <main className="flex min-h-screen items-center justify-center bg-[#F9FAFB] text-[#667085]">
      <Loader2 className="mr-3 h-5 w-5 animate-spin" /> Verificando acesso seguro…
    </main>;
  }

  if (!student) {
    return <div className="min-h-screen bg-[#F8FAFC] text-[#101828]">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-7">
        <span className="text-[24px] font-bold tracking-[-0.08em]">mira<span className="text-[#2563EB]">.</span></span>
        <span className="inline-flex items-center gap-2 rounded-full border border-[#E5E7EB] bg-white px-3 py-1.5 text-[11px] text-[#667085]">
          <ShieldCheck className="h-3.5 w-3.5" /> Acesso estudantil
        </span>
      </header>
      <main className="mx-auto grid max-w-6xl items-center gap-12 px-5 pb-20 pt-10 md:grid-cols-2 md:pt-24">
        <div>
          <div className="mb-5 inline-flex items-center gap-2 rounded-md bg-[#EDF3FF] px-3 py-2 text-[11px] font-semibold text-[#2563EB]">
            <GraduationCap className="h-4 w-4" /> PORTAL DO ALUNO
          </div>
          <h1 className="max-w-[480px] text-[38px] font-semibold leading-[1.12] tracking-[-0.05em] md:text-[53px]">
            Sua jornada acadêmica, em um só lugar.
          </h1>
          <p className="mt-6 max-w-[450px] text-[15px] leading-7 text-[#667085]">
            Consulte seu vínculo institucional, frequência, avaliações e informações
            financeiras disponíveis, com privacidade e clareza.
          </p>
          <div className="mt-9 flex items-center gap-3 text-[12px] text-[#667085]">
            <LockKeyhole className="h-4 w-4 text-[#2563EB]" /> Somente os seus dados. Nenhuma cobrança automática.
          </div>
        </div>
        <section className="rounded-2xl border border-[#E4E7EC] bg-white p-7 shadow-[0_16px_48px_rgba(16,24,40,0.05)] md:p-9">
          <div className="mb-7 flex h-11 w-11 items-center justify-center rounded-xl border border-[#DCE8FF] bg-[#F5F8FF] text-[#2563EB]">
            <LockKeyhole className="h-5 w-5" />
          </div>
          <h2 className="text-[21px] font-semibold tracking-[-0.025em]">Entrar no Portal do Aluno</h2>
          <p className="mt-2 text-[13px] leading-6 text-[#667085]">
            Informe o código individual fornecido pela sua instituição. Ele tem validade limitada
            e só pode ser usado uma vez.
          </p>
          <form onSubmit={claim} className="mt-7 space-y-5">
            <div>
              <label htmlFor="portal-token" className="mb-2 block text-[12px] font-semibold text-[#344054]">Código de acesso</label>
              <input id="portal-token" type="password" autoComplete="off" required
                value={token} onChange={(e) => setToken(e.target.value)}
                placeholder="Cole seu código de convite"
                className="h-12 w-full rounded-lg border border-[#D0D5DD] px-4 text-[13px] outline-none focus:border-[#2563EB] focus:ring-2 focus:ring-[#D6E4FF]" />
            </div>
            {error && <p role="alert" className="flex gap-2 rounded-lg bg-[#FFF5F5] p-3 text-[12px] text-[#B42318]"><AlertCircle className="h-4 w-4 shrink-0" /> {error}</p>}
            <button type="submit" disabled={busy} className="flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-[#101828] text-[13px] font-semibold text-white transition hover:bg-[#344054] disabled:opacity-50">
              {busy ? "Validando convite…" : "Acessar portal"} <ArrowRight className="h-4 w-4" />
            </button>
          </form>
          <p className="mt-7 border-t border-[#E4E7EC] pt-5 text-[11px] leading-5 text-[#98A2B3]">
            Esta primeira versão depende de habilitação institucional. Não compartilhe
            seu código com outras pessoas.
          </p>
        </section>
      </main>
    </div>;
  }

  const current = sections.find((section) => section.id === tab)!;

  function navigate(next: PortalSection) {
    setActiveSection(next);
    setRecordsError(null);
    if (next === "home") setExtraTab("schedule");
    if (next === "journey") setTab("enrollment");
    if (next === "disciplines") { setTab("assessment"); setExtraTab("report-card"); }
    if (next === "calendar") setExtraTab("calendar");
    if (next === "financial") setTab("fee");
    // Changing sections never changes the student identity or authorizations.
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  const field = (label: string, item: string | number | null | undefined) => (
    <div key={label} className="min-w-0 py-3">
      <dt className="text-[11px] font-medium text-[#75777C]">{label}</dt>
      <dd className="mt-1 break-words text-[13px] font-semibold text-[#101112]">{value(item)}</dd>
    </div>
  );

  const viewHeader = (eyebrow: string, title: string, description: string) => (
    <header className="mb-7">
      <p className="text-[11px] font-semibold uppercase tracking-[0.09em] text-[#75777C]">{eyebrow}</p>
      <h1 className="mt-2 text-[25px] font-semibold tracking-[-0.035em] text-[#101112] sm:text-[29px]">{title}</h1>
      <p className="mt-2 max-w-[660px] text-[13px] leading-6 text-[#505967]">{description}</p>
    </header>
  );

  const recordsPanel = (title: string) => (
    <section aria-label={title} className="overflow-hidden rounded-xl border border-[#E6E7EA] bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#E6E7EA] px-4 py-4 sm:px-6">
        <div>
          <h2 className="text-[14px] font-semibold">{title}</h2>
          <p className="mt-1 text-[11px] text-[#75777C]">Registros associados à sua matrícula, enviados pela instituição.</p>
        </div>
        {(activeSection === "disciplines") && <div role="group" aria-label="Tipo de registro" className="flex gap-1">
          {sections.filter(s => s.id === "assessment" || s.id === "attendance").map(section =>
            <button key={section.id} type="button" aria-pressed={tab === section.id} onClick={() => setTab(section.id)}
              className={`rounded-lg px-3 py-2 text-[11px] font-medium focus-visible:ring-2 focus-visible:ring-[#266DF0] ${tab === section.id ? "bg-[#EFF4FF] text-[#1E58C7]" : "text-[#505967] hover:bg-[#F8F9FA]"}`}>{section.label}</button>)}
        </div>}
      </div>
      {tab === "fee" && <p className="mx-4 mt-4 rounded-lg border border-[#FEE0C8] bg-[#FFF8F1] p-3 text-[11px] leading-5 text-[#7A3C14] sm:mx-6">
        Estes são snapshots não conciliados. Não representam quitação, dívida exigível ou confirmação de pagamento.
      </p>}
      <div className="min-h-[110px]">
        {recordsLoading && <p role="status" className="flex items-center gap-2 p-6 text-[12px] text-[#505967]"><Loader2 className="h-4 w-4 animate-spin" /> Consultando registros…</p>}
        {!recordsLoading && recordsError && <div role="alert" className="m-4 rounded-lg bg-[#FFF6F6] p-4 text-[12px] text-[#772322]">
          {recordsError}
        </div>}
        {!recordsLoading && !recordsError && records.length === 0 && <p className="p-7 text-[12px] leading-6 text-[#75777C]">Nenhum registro disponível nesta categoria. Ausência de dados não confirma situação regular nem irregular.</p>}
        {!recordsLoading && !recordsError && records.length > 0 && <ul className="divide-y divide-[#EEEFF1]">
          {records.map(record => <li key={record.id} className="flex flex-wrap items-start justify-between gap-3 px-4 py-3.5 sm:px-6">
            <div className="min-w-0">
              <p className="text-[12px] font-semibold text-[#101112]">{record.title}</p>
              <p className="mt-1.5 text-[11px] leading-5 text-[#505967]">{recordDescription(record)}</p>
            </div>
            {record.status && <span className="max-w-[220px] rounded-md border border-[#E6E7EA] bg-[#F8F9FA] px-2 py-1 text-[11px] text-[#505967]">{record.status}</span>}
          </li>)}
        </ul>}
      </div>
      <p className="border-t border-[#EEEFF1] px-4 py-2.5 text-[11px] text-[#75777C] sm:px-6">{current.label} · somente dados fornecidos pela instituição</p>
    </section>
  );

  const academicRows = activeSection === "home" && extraTab === "schedule"
    ? extraRecords.filter(item => item.starts_at && Number.isFinite(Date.parse(item.starts_at)) && Date.parse(item.starts_at) >= Date.now())
      .sort((a, b) => Date.parse(a.starts_at || "") - Date.parse(b.starts_at || "")).slice(0, 5)
    : extraRecords;

  const academicPanel = (title: string, description: string) => (
    <section aria-label={title} className="overflow-hidden rounded-xl border border-[#E6E7EA] bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#E6E7EA] px-4 py-4 sm:px-6">
        <div>
          <h2 className="text-[14px] font-semibold">{title}</h2>
          <p className="mt-1 text-[11px] text-[#75777C]">{description}</p>
        </div>
        {activeSection === "calendar" && <div role="group" aria-label="Visão do calendário" className="flex gap-1">
          {([["calendar", "Eventos"], ["schedule", "Aulas"]] as [ExtraTab,string][]).map(([id,label]) =>
            <button type="button" key={id} onClick={() => setExtraTab(id)} aria-pressed={extraTab === id}
              className={`rounded-lg px-3 py-2 text-[11px] font-medium focus-visible:ring-2 focus-visible:ring-[#266DF0] ${extraTab === id ? "bg-[#EFF4FF] text-[#1E58C7]" : "text-[#505967] hover:bg-[#F8F9FA]"}`}>{label}</button>)}
        </div>}
        {activeSection === "disciplines" && <div role="group" aria-label="Desempenho por disciplina" className="flex gap-1">
          {([["report-card", "Notas"], ["attendance", "Frequência"]] as [ExtraTab,string][]).map(([id,label]) =>
            <button type="button" key={id} onClick={() => setExtraTab(id)} aria-pressed={extraTab === id}
              className={`rounded-lg px-3 py-2 text-[11px] font-medium focus-visible:ring-2 focus-visible:ring-[#266DF0] ${extraTab === id ? "bg-[#EFF4FF] text-[#1E58C7]" : "text-[#505967] hover:bg-[#F8F9FA]"}`}>{label}</button>)}
        </div>}
      </div>
      {extraLoading ? <div role="status" className="flex items-center gap-2 p-6 text-[12px] text-[#505967]"><Loader2 className="h-4 w-4 animate-spin" /> Consultando registros publicados…</div>
        : academicRows.length ? <ul className="divide-y divide-[#EEEFF1]">
          {academicRows.map((item,index) => <li key={(item.id || item.class_id || "academic") + "-" + index} className="px-4 py-4 sm:px-6">
            <p className="text-[12px] font-semibold">{academicTitle(extraTab, item)}</p>
            <p className="mt-1.5 text-[11px] leading-5 text-[#505967]">{academicDescription(extraTab, item)}</p>
            {item.teacher_name && <p className="mt-1 text-[11px] text-[#75777C]">Docente: {item.teacher_name}</p>}
          </li>)}
        </ul> : <p className="p-7 text-[12px] leading-6 text-[#75777C]">{extraMessage || (activeSection === "home" ? "Nenhuma próxima aula publicada foi encontrada." : "Nenhuma informação publicada nesta seção.")}</p>}
      {extraMessage && academicRows.length > 0 && <p className="border-t border-[#E6E7EA] px-4 py-3 text-[11px] text-[#505967] sm:px-6">{extraMessage}</p>}
      {extraTab === "report-card" && <p className="border-t border-[#EEEFF1] px-4 py-3 text-[11px] text-[#75777C] sm:px-6">Somente notas publicadas. Resultados finais dependem de homologação institucional.</p>}
      {extraTab === "attendance" && <p className="border-t border-[#EEEFF1] px-4 py-3 text-[11px] text-[#75777C] sm:px-6">Aulas sem chamada não são contadas como presença.</p>}
    </section>
  );

  return <PortalShell section={activeSection} onNavigate={navigate}
    institution={student.institution} studentName={student.name}
    busy={busy} onLogout={() => void logout()}>
    {activeSection === "home" && <>
      {viewHeader(student.institution, "Olá, " + (student.name.split(" ")[0] || "estudante") + ".",
        "Sua vida acadêmica, solicitações e informações importantes em um só lugar.")}
      <section className="rounded-xl border border-[#E6E7EA] bg-white px-5 py-4 sm:px-6" aria-label="Seu resumo">
        <div className="flex items-center gap-2"><GraduationCap className="h-4 w-4 text-[#266DF0]" /><h2 className="text-[14px] font-semibold">Seu vínculo acadêmico</h2></div>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 border-t border-[#EEEFF1] sm:grid-cols-4">
          {field("Curso", student.course)}
          {field("Matrícula", student.registration)}
          {field("Situação acadêmica", student.academic_status)}
          {field("Semestre", student.semester != null ? student.semester + "º" : null)}
          {field("Frequência geral", student.attendance_percentage != null ? student.attendance_percentage + "%" : null)}
          {field("Média informada", student.grade_average)}
        </dl>
      </section>
      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_290px]">
        <div>{academicPanel("Próximas aulas", "Somente aulas futuras com data confirmada pelo sistema acadêmico.")}</div>
        <section aria-label="Acesso rápido" className="self-start rounded-xl border border-[#E6E7EA] bg-[#F8F9FA] p-5">
          <h2 className="text-[14px] font-semibold">O que você precisa fazer?</h2>
          <p className="mt-2 text-[12px] leading-5 text-[#505967]">Acesse seu histórico ou acompanhe um pedido sem procurar por diferentes portais.</p>
          <div className="mt-4 space-y-2">
            {([["journey", "Ver minha jornada"], ["requests", "Acompanhar solicitações"], ["financial", "Consultar financeiro"]] as [PortalSection,string][]).map(([id,label]) =>
              <button key={id} type="button" onClick={() => navigate(id)} className="flex w-full items-center justify-between gap-2 rounded-lg border border-[#E6E7EA] bg-white px-3 py-3 text-left text-[12px] font-medium hover:border-[#B6CDFE] focus-visible:ring-2 focus-visible:ring-[#266DF0]">
                {label}<ArrowRight className="h-4 w-4 text-[#75777C]" />
              </button>)}
          </div>
          <div className="mt-5 border-t border-[#E6E7EA] pt-4">
            <h3 className="text-[12px] font-semibold">Solicitações recentes</h3>
            {recentRequests === null
              ? <p className="mt-2 text-[11px] leading-5 text-[#75777C]">Informações de solicitações ainda não disponíveis nesta consulta.</p>
              : recentRequests.length === 0
                ? <p className="mt-2 text-[11px] text-[#75777C]">Nenhuma solicitação registrada.</p>
                : <ul className="mt-2 divide-y divide-[#E6E7EA]">
                  {recentRequests.map(request => <li key={request.id} className="py-2">
                    <p className="truncate text-[11px] font-medium" title={request.subject}>{request.subject}</p>
                    <span className={"mt-1 inline-flex rounded-md border px-1.5 py-0.5 text-[10px] " + serviceStatusTone(request.status)}>{serviceStatusLabel(request.status)}</span>
                  </li>)}
                </ul>}
            <button type="button" onClick={() => navigate("requests")}
              className="mt-3 text-[11px] font-semibold text-[#266DF0] hover:underline focus-visible:ring-2 focus-visible:ring-[#266DF0]">
              Ver todas as solicitações
            </button>
          </div>
        </section>
      </div>
      <p className="mt-4 text-[11px] leading-5 text-[#75777C]">Notas, frequência e valores não informados permanecem desconhecidos — não são tratados como situação regular.</p>
    </>}
    {activeSection === "journey" && <>
      {viewHeader("Vida acadêmica", "Minha jornada", "Acompanhe seu vínculo, os períodos cursados e a situação das solicitações de matrícula.")}
      <section className="mb-5 rounded-xl border border-[#E6E7EA] px-5 py-3 sm:px-6">
        <dl className="grid grid-cols-2 gap-x-4 sm:grid-cols-4">
          {field("Curso", student.course)}
          {field("Matrícula", student.registration)}
          {field("Campus", student.campus)}
          {field("Situação", student.academic_status)}
        </dl>
      </section>
      <div className="space-y-5">
        {recordsPanel("Matrículas registradas")}
        <AcademicOperationsPanel />
      </div>
    </>}
    {activeSection === "disciplines" && <>
      {viewHeader("Ensino", "Disciplinas e desempenho", "Consulte avaliações, notas publicadas e frequência, sem confundir registros parciais com resultados finais.")}
      <div className="space-y-5">
        {academicPanel("Resultados publicados", "Informações oficiais disponibilizadas pelo sistema acadêmico.")}
        {recordsPanel("Registros adicionais da instituição")}
      </div>
    </>}
    {activeSection === "calendar" && <>
      {viewHeader("Organização", "Calendário acadêmico", "Encontre aulas e eventos institucionais registrados, com horários e locais quando informados.")}
      {academicPanel("Agenda acadêmica", "Selecione eventos ou aulas para consultar a lista cronológica.")}
    </>}
    {activeSection === "requests" && <>
      {viewHeader("Secretaria", "Solicitações", "Registre requerimentos, acompanhe decisões e troque mensagens somente nos canais autorizados.")}
      <StudentServicesPanel key="requests" initialView="requests" standalone />
    </>}
    {activeSection === "documents" && <>
      {viewHeader("Secretaria", "Documentos", "Consulte documentos disponibilizados e verifique sua integridade quando o serviço estiver habilitado.")}
      <StudentServicesPanel key="documents" initialView="documents" standalone />
    </>}
    {activeSection === "financial" && <>
      {viewHeader("Pagamentos", "Financeiro", "Acompanhe registros informativos e cobranças oficiais, sem confundir tentativas e confirmações de pagamento.")}
      <div className="space-y-5">
        <StudentServicesPanel key="financial" initialView="financial" standalone />
        {recordsPanel("Outros registros financeiros da instituição")}
      </div>
    </>}
    {activeSection === "account" && <>
      {viewHeader("Privacidade", "Minha conta", "Consulte os dados vinculados à sua sessão estudantil e encerre o acesso com segurança.")}
      <section className="rounded-xl border border-[#E6E7EA] p-5 sm:p-6">
        <div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-[#266DF0]" /><h2 className="text-[14px] font-semibold">Identidade acadêmica</h2></div>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 border-t border-[#EEEFF1] sm:grid-cols-3">
          {field("Nome", student.name)}
          {field("Instituição", student.institution)}
          {field("Matrícula", student.registration)}
          {field("Curso", student.course)}
          {field("Turma", student.class_name)}
          {field("Unidade", student.campus)}
        </dl>
        <p className="mt-3 border-t border-[#EEEFF1] pt-4 text-[11px] leading-5 text-[#505967]">O Portal apresenta apenas dados da sessão estudantil. Para corrigir informações cadastrais, procure sua instituição.</p>
        <button type="button" onClick={() => void logout()} disabled={busy} className="mt-5 inline-flex items-center gap-2 rounded-lg border border-[#E6E7EA] px-4 py-2.5 text-[12px] font-medium hover:bg-[#F8F9FA] focus-visible:ring-2 focus-visible:ring-[#266DF0] disabled:opacity-50">
          <LogOut className="h-4 w-4" /> Encerrar sessão
        </button>
      </section>
    </>}
    <footer className="mt-9 flex items-start gap-2 border-t border-[#EEEFF1] pt-5 text-[11px] leading-5 text-[#75777C]">
      <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
      Seus dados são vinculados à sessão individual. Nenhum indicador interno de risco é exibido neste portal.
    </footer>
  </PortalShell>;
}
