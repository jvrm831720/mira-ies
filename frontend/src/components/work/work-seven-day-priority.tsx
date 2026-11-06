"use client";

import Link from "next/link";
import type { NoContactPriority } from "@/lib/work-api";

export function WorkSevenDayPriority({ data, loading, error }: {
  data?: NoContactPriority; loading: boolean; error: boolean;
}) {
  return <section aria-label="Priorização de alunos sem contato há sete dias"
    className="rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] p-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 className="text-sm font-semibold text-[var(--color-ink)]">Críticos sem contato confirmado · 7 dias</h3>
        <p className="mt-1 text-xs text-[var(--color-slate-600)]">
          A contagem cobre todos os alunos ativos com risco crítico do workspace, não apenas a página da fila.
        </p>
      </div>
      <p aria-live="polite" className="text-2xl font-semibold tabular-nums text-[var(--color-red)]">
        {loading || error || !data ? "—" : data.without_contact_7d.toLocaleString("pt-BR")}
      </p>
    </div>
    {loading && <p role="status" className="mt-3 text-xs text-[var(--color-muted)]">Conferindo registros de contato…</p>}
    {error && <p role="alert" className="mt-3 text-xs text-[var(--color-red)]">Não foi possível validar os contatos. Nenhuma contagem foi presumida.</p>}
    {data && !error && <div className="mt-3 space-y-3">
      <p className="text-xs text-[var(--color-slate-600)]">
        Base: <strong>{data.critical_total.toLocaleString("pt-BR")}</strong> críticos ·
        <strong> {data.contacted_7d.toLocaleString("pt-BR")}</strong> com contato confirmado ·
        <strong> {data.pending_verification.toLocaleString("pt-BR")}</strong> aguardando verificação.
      </p>
      <p className="text-xs text-[var(--color-slate-600)]">
        Sem contato confirmado significa sem envio registrado como enviado e sem atividade humana de contato concluída
        nos últimos 7 dias. Casos em envio ou contato em andamento ficam fora da fila até verificação.
      </p>
      {data.candidates.length > 0 ? <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {data.candidates.map(student => <li key={student.id}>
          <Link href={"/alunos/" + encodeURIComponent(student.id)}
            className="flex items-center justify-between gap-2 rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-xs hover:border-[var(--color-blue)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]">
            <span className="min-w-0 truncate font-semibold">{student.nome || student.matricula}</span>
            <span className="shrink-0 tabular-nums">{Number(student.risk_score).toLocaleString("pt-BR",{maximumFractionDigits:1})}</span>
          </Link>
        </li>)}
      </ul> : <p className="text-xs text-[var(--color-slate-600)]">Nenhum aluno confirmado para priorização.</p>}
      <p className="text-[11px] text-[var(--color-muted)]">Apuração: {new Date(data.as_of).toLocaleString("pt-BR")}. Priorizar não dispara mensagens.</p>
    </div>}
  </section>;
}
