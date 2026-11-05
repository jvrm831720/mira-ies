"use client";

import { useEffect, useState } from "react";
import {
  ArrowRight, BookOpen, CheckCircle2, GraduationCap, LockKeyhole,
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
  const [records, setRecords] = useState<AcademicRecord[]>([]);
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

  async function claim(event: React.FormEvent<HTMLFormElement>) {
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
  return <div className="min-h-screen bg-[#F9FAFB] text-[#101828]">
    <header className="border-b border-[#E4E7EC] bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-5">
        <div className="flex items-center gap-3">
          <span className="text-[23px] font-bold tracking-[-0.08em]">mira<span className="text-[#2563EB]">.</span></span>
          <span className="mx-2 h-5 w-px bg-[#E4E7EC]" />
          <span className="text-[12px] font-semibold text-[#344054]">Portal do Aluno</span>
        </div>
        <button type="button" disabled={busy} onClick={() => void logout()}
          className="inline-flex items-center gap-2 rounded-lg border border-[#E4E7EC] px-3 py-2 text-[12px] font-semibold text-[#667085] hover:bg-[#F9FAFB]">
          <LogOut className="h-4 w-4" /> Sair
        </button>
      </div>
    </header>
    <main className="mx-auto max-w-6xl space-y-7 px-5 py-9 md:py-14">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">{student.institution}</div>
          <h1 className="text-[30px] font-semibold tracking-[-0.045em] md:text-[37px]">Olá, {student.name.split(" ")[0]}.</h1>
          <p className="mt-2 text-[13px] text-[#667085]">Acompanhe suas informações acadêmicas disponíveis na instituição.</p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-lg border border-[#D1FADF] bg-[#ECFDF3] px-3 py-2 text-[11px] font-medium text-[#067647]">
          <CheckCircle2 className="h-4 w-4" /> Sessão individual
        </span>
      </div>

      <section className="grid gap-3 md:grid-cols-4" aria-label="Resumo acadêmico">
        {[
          ["Curso", value(student.course)],
          ["Matrícula", student.registration],
          ["Semestre", student.semester != null ? student.semester + "º" : "Não informado"],
          ["Unidade", value(student.campus)],
        ].map(([label, item]) =>
          <div key={label} className="rounded-xl border border-[#E4E7EC] bg-white p-5">
            <p className="text-[11px] text-[#667085]">{label}</p>
            <p className="mt-3 break-words text-[14px] font-semibold text-[#101828]">{item}</p>
          </div>
        )}
      </section>

      <div className="overflow-hidden rounded-xl border border-[#E4E7EC] bg-white">
        <div className="border-b border-[#E4E7EC] p-5 md:p-7">
          <div className="flex items-center gap-3">
            <GraduationCap className="h-5 w-5 text-[#2563EB]" />
            <div>
              <h2 className="text-[16px] font-semibold">Registros da instituição</h2>
              <p className="mt-1 text-[12px] text-[#98A2B3]">Informações recebidas e registradas pela equipe acadêmica.</p>
            </div>
          </div>
        </div>
        <div role="tablist" aria-label="Registros acadêmicos" className="flex flex-wrap gap-2 border-b border-[#E4E7EC] px-5 pt-3 md:px-7">
          {sections.map(({ id, label, icon: Icon }) =>
            <button key={id} type="button" role="tab" aria-selected={tab === id}
              onClick={() => setTab(id)}
              className={"inline-flex items-center gap-2 border-b-2 px-3 py-3 text-[12px] font-semibold transition " +
                (tab === id ? "border-[#2563EB] text-[#2563EB]" : "border-transparent text-[#667085] hover:text-[#344054]")}>
              <Icon className="h-4 w-4" /> {label}
            </button>
          )}
        </div>
        <div className="min-h-[220px] p-5 md:p-7">
          <h3 className="mb-4 text-[13px] font-semibold">{current.label}</h3>
          {tab === "fee" && <p className="mb-5 rounded-lg border border-[#FEDF89] bg-[#FFFAEB] px-4 py-3 text-[11px] leading-5 text-[#93370D]">
            Os valores são informações de origem ainda não conciliadas e não comprovam
            pagamento, quitação ou dívida exigível. Para esclarecimentos, consulte sua instituição.
          </p>}
          {recordsLoading && <div className="flex items-center gap-2 text-[12px] text-[#667085]"><Loader2 className="h-4 w-4 animate-spin" /> Consultando registros…</div>}
          {!recordsLoading && recordsError && <p role="alert" className="rounded-lg bg-[#FFF5F5] p-4 text-[12px] text-[#B42318]">{recordsError}</p>}
          {!recordsLoading && !recordsError && records.length === 0 &&
            <div className="rounded-lg bg-[#F9FAFB] px-6 py-9 text-center">
              <p className="text-[13px] font-medium text-[#344054]">Nenhum registro disponível nesta categoria.</p>
              <p className="mt-2 text-[11px] text-[#98A2B3]">A ausência de dados não significa uma situação favorável ou desfavorável.</p>
            </div>}
          {!recordsLoading && !recordsError && records.length > 0 &&
            <ul className="divide-y divide-[#EAECF0] rounded-lg border border-[#EAECF0]">
              {records.map((record) => <li key={record.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
                <div>
                  <strong className="text-[12px] text-[#344054]">{record.title}</strong>
                  <p className="mt-1.5 text-[11px] text-[#98A2B3]">{recordDescription(record)}</p>
                </div>
                <span className="rounded-md bg-[#F2F4F7] px-2.5 py-1 text-[11px] text-[#475467]">{value(record.status)}</span>
              </li>)}
            </ul>}
        </div>
      </div>
      <div className="flex items-start gap-3 rounded-xl border border-[#E4E7EC] bg-white p-5">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-[#2563EB]" />
        <p className="text-[12px] leading-6 text-[#667085]">
          Seu portal exibe apenas informações associadas à sua matrícula.
          Indicadores internos de risco, campanhas e dados de outros estudantes não são disponibilizados.
          As informações podem ser atualizadas pela instituição.
        </p>
      </div>
    </main>
  </div>;
}
