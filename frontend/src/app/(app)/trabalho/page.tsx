"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, ClipboardList, RefreshCw, Users, Clock3 } from "lucide-react";
import { Header } from "@/components/layout/header";
import { CriticalList } from "@/components/risk/critical-list";
import { StudentDrawer } from "@/components/students/student-drawer";
import { api } from "@/lib/api";

export default function WorkCenterPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const summary = useQuery({ queryKey: ["risk-summary"], queryFn: () => api.riskSummary() });
  const work = useQuery({ queryKey: ["retention-work-summary"], queryFn: () => api.retentionWorkSummary(), retry: false });
  const planned = useQuery({ queryKey: ["retention-logs", "planned", "work-center"], queryFn: () => api.retentionLogs({ limit: 100, status: "planned" }), retry: false });
  const critical = useQuery({ queryKey: ["risk-critical", "work-center"], queryFn: () => api.riskCritical(50) });
  const students = critical.data?.students ?? [];
  const plannedItems = planned.data?.logs ?? [];

  return (
    <>
      <Header title="Central de trabalho" subtitle="Acompanhe intervenções planejadas e priorize os alunos sinalizados." />
      <main className="mx-auto w-full max-w-[1440px] space-y-[var(--space-6)] px-4 pb-10 pt-5 md:px-8 md:pt-7 xl:px-10 mira-page">
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Alunos em risco crítico" value={summary.isLoading ? "—" : (summary.data?.summary.critico ?? 0).toLocaleString("pt-BR")} description="Casos sinalizados para revisão" icon={<AlertCircle className="h-5 w-5" />} />
          <Metric label="Base monitorada" value={summary.isLoading ? "—" : (summary.data?.total_students ?? 0).toLocaleString("pt-BR")} description="Total informado pelo resumo de risco" icon={<Users className="h-5 w-5" />} />
          <Metric label="Intervenções pendentes" value={work.isLoading || work.isError ? "—" : (work.data?.pending ?? 0).toLocaleString("pt-BR")} description="Decisões planejadas sem conclusão" icon={<ClipboardList className="h-5 w-5" />} />
          <Metric label="Planejadas há +48h" value={work.isLoading || work.isError ? "—" : (work.data?.overdue_48h ?? 0).toLocaleString("pt-BR")} description="Registros que excedem a política provisória" icon={<Clock3 className="h-5 w-5" />} />
        </section>
        <section className="rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-4 sm:p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div><h2 className="text-lg font-semibold tracking-[-0.03em] text-neutral-950">Intervenções aguardando execução</h2><p className="mt-1 text-sm text-neutral-500">Registros planejados persistidos pela MIRA. Ainda não são tarefas atribuídas a responsáveis.</p></div>
            <button type="button" onClick={() => { void planned.refetch(); void work.refetch(); }} disabled={planned.isFetching || work.isFetching} className="inline-flex h-10 items-center gap-2 rounded-[var(--radius-control)] border border-[var(--border-subtle)] bg-white px-4 text-sm font-semibold text-neutral-700 shadow-sm transition hover:bg-neutral-50 disabled:opacity-50"><RefreshCw className={`h-3.5 w-3.5 ${planned.isFetching || work.isFetching ? "animate-spin" : ""}`} /> Atualizar</button>
          </div>
          {planned.isError ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">Não foi possível carregar as intervenções planejadas. <button type="button" onClick={() => void planned.refetch()} className="font-semibold underline">Tentar novamente</button></div> : planned.isLoading ? <p className="p-4 text-sm text-neutral-500">Carregando intervenções…</p> : plannedItems.length === 0 ? <p className="rounded-[var(--radius-control)] border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)] p-5 text-sm text-neutral-600">Nenhuma intervenção planejada foi retornada pela API.</p> : <div className="overflow-x-auto"><table className="w-full min-w-[620px] text-left text-sm"><thead><tr className="border-b border-neutral-200 text-xs text-neutral-500"><th className="px-3 py-3 font-medium">Matrícula</th><th className="px-3 py-3 font-medium">Canal</th><th className="px-3 py-3 font-medium">Criada em</th><th className="px-3 py-3 font-medium">Situação</th></tr></thead><tbody>{plannedItems.map((item) => { const isOverdue = Boolean(item.created_at && Date.now() - new Date(item.created_at).getTime() > 48 * 60 * 60 * 1000); return <tr key={item.id} className="border-b border-neutral-100 last:border-0"><td className="px-3 py-3 font-medium text-neutral-900">{item.matricula || item.student_id || "Aluno não identificado"}</td><td className="px-3 py-3 text-neutral-600">{item.channel || "Não informado"}</td><td className="px-3 py-3 text-neutral-600">{item.created_at ? new Date(item.created_at).toLocaleString("pt-BR") : "Data indisponível"}</td><td className="px-3 py-3"><span className={isOverdue ? "rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700" : "rounded-full bg-neutral-100 px-2.5 py-1 text-xs font-medium text-neutral-600"}>{isOverdue ? "Mais de 48h" : "Planejada"}</span></td></tr>; })}</tbody></table><p className="mt-3 text-xs text-neutral-500">A lista mostra até 100 registros recentes. O indicador agregado vem do backend e considera todo o tenant. A política de 48h é provisória e não substitui prazos individuais.</p></div>}
        </section>
        <section data-mira-card="true" className="rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-white p-5 shadow-sm sm:p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-base font-semibold text-neutral-950">Fila de prioridade de alunos</h2><p className="mt-1 text-sm text-neutral-500">Alunos classificados como risco crítico pela API atual.</p></div><button type="button" onClick={() => void critical.refetch()} disabled={critical.isFetching} className="inline-flex h-9 items-center gap-2 rounded-xl border border-neutral-200 px-3 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50"><RefreshCw className={`h-3.5 w-3.5 ${critical.isFetching ? "animate-spin" : ""}`} /> Atualizar</button></div>
          {critical.isError ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">Não foi possível carregar a fila. <button type="button" onClick={() => void critical.refetch()} className="font-semibold underline">Tentar novamente</button></div> : <CriticalList students={students} loading={critical.isLoading} onSelect={setSelectedId} />}
          {!critical.isLoading && !critical.isError && students.length === 0 && <p className="mt-3 text-sm text-neutral-500">Nenhum caso crítico nesta resposta; isso não garante ausência de tarefas pendentes.</p>}
        </section>
        <Link href="/alunos" className="inline-flex items-center gap-2 text-sm font-semibold text-neutral-800 hover:underline">Abrir base completa de alunos <ArrowRight className="h-4 w-4" /></Link>
      </main>
      <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
    </>
  );
}

function Metric({ label, value, description, icon }: { label: string; value: string; description: string; icon: React.ReactNode }) {
  return <article data-mira-card="true" className="rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-white p-5 shadow-sm transition-shadow sm:p-6"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-neutral-100 text-neutral-700">{icon}</span><p className="text-sm font-medium text-neutral-500">{label}</p></div><p className="mt-4 text-3xl font-semibold tracking-tight text-neutral-950">{value}</p><p className="mt-1 text-xs text-neutral-500">{description}</p></article>;
}
