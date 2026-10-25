"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ClipboardList, RefreshCw, Users } from "lucide-react";
import { Header } from "@/components/layout/header";
import { CriticalList } from "@/components/risk/critical-list";
import { StudentDrawer } from "@/components/students/student-drawer";
import { api } from "@/lib/api";

export default function WorkCenterPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const summary = useQuery({ queryKey: ["risk-summary"], queryFn: () => api.riskSummary() });
  const critical = useQuery({ queryKey: ["risk-critical", "work-center"], queryFn: () => api.riskCritical(50) });
  const students = critical.data?.students ?? [];

  return (
    <>
      <Header title="Central de trabalho" subtitle="Priorize os alunos sinalizados e abra cada ficha para decidir o próximo acompanhamento." />
      <main className="mx-auto w-full max-w-[1440px] space-y-6 px-4 pb-10 pt-5 md:px-8 md:pt-7 xl:px-10">
        <section className="grid gap-3 sm:grid-cols-2">
          <article className="rounded-2xl border border-neutral-200 bg-white p-5">
            <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#fff0ed] text-[#b84336]"><ClipboardList className="h-5 w-5" /></span><p className="text-sm font-medium text-neutral-500">Alunos em risco crítico</p></div>
            <p className="mt-4 text-3xl font-semibold tracking-tight text-neutral-950">{summary.isLoading ? "—" : (summary.data?.summary.critico ?? 0).toLocaleString("pt-BR")}</p>
            <p className="mt-1 text-xs text-neutral-500">Priorize a revisão individual dos casos sinalizados.</p>
          </article>
          <article className="rounded-2xl border border-neutral-200 bg-white p-5">
            <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-neutral-100 text-neutral-700"><Users className="h-5 w-5" /></span><p className="text-sm font-medium text-neutral-500">Base monitorada</p></div>
            <p className="mt-4 text-3xl font-semibold tracking-tight text-neutral-950">{summary.isLoading ? "—" : (summary.data?.total_students ?? 0).toLocaleString("pt-BR")}</p>
            <p className="mt-1 text-xs text-neutral-500">Total informado pelo resumo de risco.</p>
          </article>
        </section>
        <section className="rounded-2xl border border-neutral-200 bg-white p-4 sm:p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div><h2 className="text-base font-semibold text-neutral-950">Fila de prioridade</h2><p className="mt-1 text-sm text-neutral-500">Lista de alunos classificados como risco crítico pela API atual.</p></div>
            <button type="button" onClick={() => void critical.refetch()} disabled={critical.isFetching} className="inline-flex h-9 items-center gap-2 rounded-xl border border-neutral-200 px-3 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50"><RefreshCw className={`h-3.5 w-3.5 ${critical.isFetching ? "animate-spin" : ""}`} /> Atualizar</button>
          </div>
          {critical.isError ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">Não foi possível carregar a fila. <button type="button" onClick={() => void critical.refetch()} className="font-semibold underline">Tentar novamente</button></div> : <CriticalList students={students} loading={critical.isLoading} onSelect={setSelectedId} />}
          {!critical.isLoading && !critical.isError && students.length === 0 && <p className="mt-3 text-sm text-neutral-500">Não há casos críticos nesta resposta. Isso não significa, por si só, que não existam tarefas pendentes ou atrasadas.</p>}
        </section>
        <Link href="/alunos" className="inline-flex items-center gap-2 text-sm font-semibold text-neutral-800 hover:underline">Abrir base completa de alunos <ArrowRight className="h-4 w-4" /></Link>
      </main>
      <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
    </>
  );
}
