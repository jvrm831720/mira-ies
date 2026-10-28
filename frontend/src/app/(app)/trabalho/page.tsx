"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, ClipboardList, Clock3, RefreshCw, Search, XCircle } from "lucide-react";
import { Header } from "@/components/layout/header";
import { CriticalList } from "@/components/risk/critical-list";
import { StudentDrawer } from "@/components/students/student-drawer";
import { api } from "@/lib/api";

type WorkTab = "planned" | "critical";

function formatDate(value?: string | null) {
  if (!value) return "Data indisponível";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Data indisponível";
  return new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", dateStyle: "short", timeStyle: "short" }).format(date);
}

function isOverdue(value?: string | null) {
  if (!value) return false;
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) && Date.now() - timestamp > 48 * 60 * 60 * 1000;
}

export default function WorkCenterPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<WorkTab>("planned");
  const [search, setSearch] = useState("");
  const summary = useQuery({ queryKey: ["risk-summary"], queryFn: () => api.riskSummary() });
  const work = useQuery({ queryKey: ["retention-work-summary"], queryFn: () => api.retentionWorkSummary(), retry: false });
  const planned = useQuery({ queryKey: ["retention-logs", "planned", "work-center"], queryFn: () => api.retentionLogs({ limit: 100, status: "planned" }), retry: false });
  const critical = useQuery({ queryKey: ["risk-critical", "work-center"], queryFn: () => api.riskCritical(50) });
  const plannedItems = planned.data?.logs ?? [];
  const students = critical.data?.students ?? [];
  const filteredItems = useMemo(() => {
    const term = search.trim().toLocaleLowerCase("pt-BR");
    if (!term) return plannedItems;
    return plannedItems.filter((item) => [item.matricula, item.student_id, item.channel, item.status, item.risk_level].filter(Boolean).some((value) => String(value).toLocaleLowerCase("pt-BR").includes(term)));
  }, [plannedItems, search]);
  const refreshing = summary.isFetching || work.isFetching || planned.isFetching || critical.isFetching;
  const refreshAll = () => { void summary.refetch(); void work.refetch(); void planned.refetch(); void critical.refetch(); };

  return (
    <>
      <Header title="Central de trabalho" subtitle="Priorize as pendências operacionais e encontre o próximo passo." />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-6 px-4 pb-10 pt-5 md:px-8 md:pt-7 xl:px-10">
        <section className="flex flex-col justify-between gap-4 border-b border-[#E5E7EB] pb-5 sm:flex-row sm:items-center">
          <div className="max-w-2xl">
            <p className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#2563EB]"><ClipboardList className="h-3.5 w-3.5" /> Operação diária</p>
            <h2 className="text-xl font-semibold tracking-[-0.035em] text-[#111827] sm:text-2xl">O que precisa de atenção agora</h2>
            <p className="mt-1.5 text-sm leading-relaxed text-[#667085]">Revise decisões planejadas, acompanhe atrasos e abra os casos prioritários. Os registros são dados operacionais reais, não tarefas atribuídas.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={refreshAll} disabled={refreshing} className="inline-flex h-10 items-center gap-2 rounded-xl border border-[#D0D5DD] bg-white px-4 text-sm font-semibold text-[#344054] transition hover:bg-[#F9FAFB] disabled:opacity-50"><RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} /> Atualizar</button>
            <Link href="/retencao" className="inline-flex h-10 items-center gap-2 rounded-xl bg-[#2563EB] px-4 text-sm font-semibold text-white transition hover:bg-[#1D4ED8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB] focus-visible:ring-offset-2">Abrir Intervenções <ArrowRight className="h-4 w-4" /></Link>
          </div>
        </section>

        <section aria-label="Indicadores operacionais" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Pendentes" value={work.isLoading || work.isError ? "—" : work.data.pending.toLocaleString("pt-BR")} description="Decisões planejadas aguardando execução" icon={<ClipboardList className="h-5 w-5" />} />
          <Metric label="Há mais de 48 horas" value={work.isLoading || work.isError ? "—" : work.data.overdue_48h.toLocaleString("pt-BR")} description={work.data?.overdue_policy_hours ? `Política atual: ${work.data.overdue_policy_hours}h` : "Pendências acima do prazo operacional"} icon={<Clock3 className="h-5 w-5" />} tone="warning" />
          <Metric label="Falhas registradas" value={work.isLoading || work.isError ? "—" : work.data.failed.toLocaleString("pt-BR")} description="Falhas sinalizadas pelo backend" icon={<XCircle className="h-5 w-5" />} tone="danger" />
          <Metric label="Alunos em risco crítico" value={summary.isLoading || summary.isError ? "—" : (summary.data?.summary.critico ?? 0).toLocaleString("pt-BR")} description="Casos para revisão prioritária" icon={<AlertCircle className="h-5 w-5" />} tone="critical" />
        </section>

        {work.isError && <div role="alert" className="flex flex-col gap-2 rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-4 text-sm text-[#B42318] sm:flex-row sm:items-center sm:justify-between"><div><p className="font-semibold">Não foi possível carregar os indicadores operacionais.</p><p className="mt-1 text-xs">Pendências, atrasos e falhas estão indisponíveis. Tente atualizar.</p></div><button type="button" onClick={() => void work.refetch()} className="shrink-0 font-semibold underline">Tentar novamente</button></div>}

        <section className="overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-sm">
          <div className="space-y-4 border-b border-[#EAECF0] px-4 py-4 sm:px-5">
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><h2 className="text-base font-semibold tracking-[-0.02em] text-[#101828]">Fila operacional</h2><p className="mt-1 text-sm text-[#667085]">Revise os registros e continue a operação no módulo apropriado.</p></div><span className="w-fit rounded-full bg-[#F2F4F7] px-2.5 py-1 text-xs font-medium text-[#475467]">Dados da instituição</span></div>
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div role="tablist" aria-label="Filas de trabalho" className="flex flex-wrap gap-1 rounded-xl bg-[#F2F4F7] p-1">
                <button type="button" role="tab" aria-selected={activeTab === "planned"} onClick={() => setActiveTab("planned")} className={`inline-flex min-h-9 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${activeTab === "planned" ? "bg-white text-[#101828] shadow-sm" : "text-[#667085] hover:text-[#344054]"}`}>Decisões planejadas <span className="rounded-md bg-[#F2F4F7] px-1.5 py-0.5 text-xs tabular-nums">{work.isError ? "—" : (work.data?.pending ?? 0)}</span></button>
                <button type="button" role="tab" aria-selected={activeTab === "critical"} onClick={() => setActiveTab("critical")} className={`inline-flex min-h-9 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${activeTab === "critical" ? "bg-white text-[#101828] shadow-sm" : "text-[#667085] hover:text-[#344054]"}`}>Alunos críticos <span className="rounded-md bg-[#F2F4F7] px-1.5 py-0.5 text-xs tabular-nums">{summary.isError ? "—" : (summary.data?.summary.critico ?? 0)}</span></button>
              </div>
              {activeTab === "planned" && <label className="relative block w-full sm:max-w-xs"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#98A2B3]" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar matrícula, canal ou ID" aria-label="Buscar intervenções planejadas" className="h-10 w-full rounded-xl border border-[#D0D5DD] bg-white pl-9 pr-3 text-sm text-[#101828] outline-none placeholder:text-[#98A2B3] focus:border-[#84ADFF] focus:ring-4 focus:ring-[#EFF4FF]" /></label>}
            </div>
          </div>

          {activeTab === "planned" ? <div role="tabpanel" className="p-4 sm:p-5">
            {planned.isError ? <div role="alert" className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-4 text-sm text-[#B42318]"><p className="font-semibold">Não foi possível carregar as decisões planejadas.</p><p className="mt-1 text-xs">Os dados não foram substituídos por exemplos.</p><button type="button" onClick={() => void planned.refetch()} className="mt-2 font-semibold underline">Tentar novamente</button></div>
            : planned.isLoading ? <div className="space-y-3" aria-label="Carregando decisões planejadas">{[1,2,3,4].map((item) => <div key={item} className="h-14 animate-pulse rounded-xl bg-[#F2F4F7]" />)}</div>
            : filteredItems.length === 0 ? <div className="rounded-xl border border-dashed border-[#D0D5DD] bg-[#F9FAFB] px-5 py-10 text-center"><div className="mx-auto grid h-10 w-10 place-items-center rounded-full bg-white text-[#667085] ring-1 ring-[#EAECF0]"><ClipboardList className="h-5 w-5" /></div><p className="mt-3 text-sm font-semibold text-[#101828]">{search.trim() ? "Nenhum registro encontrado" : "Nenhuma decisão planejada"}</p><p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-[#667085]">{search.trim() ? "Tente outra matrícula, canal ou identificador." : "Quando a API retornar decisões planejadas para esta instituição, elas aparecerão nesta fila."}</p>{search.trim() && <button type="button" onClick={() => setSearch("")} className="mt-3 text-xs font-semibold text-[#2563EB] hover:underline">Limpar busca</button>}</div>
            : <><div className="overflow-x-auto"><table className="w-full min-w-[680px] text-left text-sm"><thead><tr className="border-b border-[#EAECF0] text-xs text-[#667085]"><th scope="col" className="px-3 py-3 font-medium">Aluno / identificação</th><th scope="col" className="px-3 py-3 font-medium">Canal</th><th scope="col" className="px-3 py-3 font-medium">Criada em</th><th scope="col" className="px-3 py-3 font-medium">Situação</th><th scope="col" className="px-3 py-3 font-medium">Próximo passo</th></tr></thead><tbody>{filteredItems.map((item) => { const overdue = isOverdue(item.created_at); return <tr key={item.id} className="border-b border-[#F2F4F7] last:border-0 hover:bg-[#F9FAFB]"><td className="px-3 py-3.5">{item.student_id ? <button type="button" onClick={() => setSelectedId(item.student_id!)} className="text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"><span className="block font-semibold text-[#101828] hover:text-[#2563EB]">{item.matricula || "Abrir ficha do aluno"}</span><span className="mt-0.5 block max-w-[180px] truncate text-xs text-[#667085]">{item.student_id}</span></button> : <><span className="block font-medium text-[#344054]">{item.matricula || "Aluno não identificado"}</span><span className="mt-0.5 block text-xs text-[#98A2B3]">Sem identificador para abrir a ficha</span></>}</td><td className="px-3 py-3.5 text-[#475467]">{item.channel || "Não informado"}</td><td className="whitespace-nowrap px-3 py-3.5 text-[#475467]">{formatDate(item.created_at)}</td><td className="px-3 py-3.5"><span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium ${overdue ? "bg-[#FEF3F2] text-[#B42318]" : "bg-[#FFFAEB] text-[#B54708]"}`}>{overdue ? "Mais de 48h" : "Planejada"}</span></td><td className="px-3 py-3.5"><Link href="/retencao" className="inline-flex items-center gap-1 whitespace-nowrap text-xs font-semibold text-[#2563EB] hover:text-[#1D4ED8]">Ver intervenção <ArrowRight className="h-3.5 w-3.5" /></Link></td></tr>; })}</tbody></table></div><p className="mt-3 text-xs leading-relaxed text-[#667085]">Exibindo até 100 registros recentes. O prazo de 48 horas é uma política operacional provisória, não um SLA individual. Ainda não há atribuição de responsáveis nesta fila.</p></>}
          </div> : <div role="tabpanel" className="p-4 sm:p-5">{critical.isError ? <div role="alert" className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-4 text-sm text-[#B42318]"><p className="font-semibold">Não foi possível carregar os alunos críticos.</p><button type="button" onClick={() => void critical.refetch()} className="mt-2 font-semibold underline">Tentar novamente</button></div> : <><CriticalList students={students} loading={critical.isLoading} onSelect={setSelectedId} /><p className="mt-3 text-xs text-[#667085]">A classificação crítica não confirma, por si só, ausência de contato ou intervenção recente.</p></>}</div>}
        </section>

        <div className="flex flex-col justify-between gap-3 rounded-xl border border-[#D1E0FF] bg-[#EFF4FF] p-4 sm:flex-row sm:items-center"><div><p className="text-sm font-semibold text-[#194185]">Precisa executar ou acompanhar uma intervenção?</p><p className="mt-1 text-xs leading-relaxed text-[#3538CD]">Continue em Intervenções para revisar campanhas, execuções e registros de retenção.</p></div><Link href="/retencao" className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-lg border border-[#B2CCFF] bg-white px-3 text-xs font-semibold text-[#1849A9] hover:bg-[#F5F8FF]">Ir para Intervenções <ArrowRight className="h-3.5 w-3.5" /></Link></div>
      </main>
      <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
    </>
  );
}

function Metric({ label, value, description, icon, tone = "neutral" }: { label: string; value: string; description: string; icon: React.ReactNode; tone?: "neutral" | "warning" | "danger" | "critical" }) {
  const tones = { neutral: "bg-[#F2F4F7] text-[#475467]", warning: "bg-[#FFFAEB] text-[#B54708]", danger: "bg-[#FEF3F2] text-[#B42318]", critical: "bg-[#FFF1F3] text-[#C01048]" };
  return <article data-mira-card="true" className="rounded-2xl border border-[#E5E7EB] bg-white p-4 shadow-sm sm:p-5"><div className="flex items-center gap-3"><span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${tones[tone]}`}>{icon}</span><p className="text-sm font-medium text-[#475467]">{label}</p></div><p className="mt-4 text-3xl font-semibold tracking-tight tabular-nums text-[#101828]">{value}</p><p className="mt-1 text-xs leading-relaxed text-[#667085]">{description}</p></article>;
}
