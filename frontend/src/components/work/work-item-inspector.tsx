"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { workApi } from "@/lib/work-api";
import { WorkPriorityReason } from "./work-priority-reason";
import type { WorkActivity, WorkResultKind } from "@/types/work";

const OUTCOMES: Array<{ value: WorkResultKind; label: string; detail: string }> = [
  { value: "done", label: "Realizado", detail: "O trabalho humano foi executado" },
  { value: "unreachable", label: "Sem contato", detail: "A tentativa humana foi encerrada sem alcançar a pessoa" },
  { value: "referred", label: "Encaminhado", detail: "O trabalho foi encaminhado ao fluxo apropriado" },
  { value: "deferred", label: "Adiar", detail: "Manter atividade aberta com um novo prazo" },
];

function displayDate(value: string | null | undefined): string {
  if (!value || !Number.isFinite(Date.parse(value))) return "Não informado";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo",
  }).format(new Date(value));
}

export function WorkItemInspector({
  activity, activeUserId, canEdit, canOpenStudent, kind, setKind, note, setNote,
  deferUntil, setDeferUntil, busy, error, onClaim, onResolve, onDismiss,
}: {
  activity: WorkActivity; activeUserId: string; canEdit: boolean; canOpenStudent: boolean;
  kind: WorkResultKind; setKind: (value: WorkResultKind) => void;
  note: string; setNote: (value: string) => void;
  deferUntil: string; setDeferUntil: (value: string) => void;
  busy: boolean; error: string | null; onClaim: () => void;
  onResolve: () => void; onDismiss: () => void;
}) {
  const mine = activity.assignee_user_id === activeUserId;
  const canResolve = canEdit && mine && ["open", "in_progress"].includes(activity.status);
  const claimable = canEdit && !activity.assignee_user_id &&
    ["open", "in_progress"].includes(activity.status);
  const events = useQuery({
    queryKey: ["work-activity-events", activity.tenant_id, activeUserId, activity.id],
    queryFn: () => workApi.events(activity.id),
    enabled: Boolean(activity.id && activity.tenant_id && activeUserId),
    staleTime: 15_000, retry: false,
  });
  const history = events.data?.events || [];
  return <aside aria-label={"Inspecionar atividade: " + activity.title}
    className="min-w-0 space-y-4 border-t border-[var(--color-border)] bg-white p-4 lg:border-l lg:border-t-0 lg:p-5">
    <header className="flex items-start justify-between gap-3">
      <div>
        <p className="text-[length:var(--type-overline)] font-medium uppercase text-[var(--color-muted)]">
          Atividade humana · {activity.origin_type === "campaign" ? "Origem campanha" : "Origem manual"}
        </p>
        <h3 className="mt-1 text-base font-semibold leading-snug text-[var(--color-ink)]">{activity.title}</h3>
        <p className="mt-2 text-xs text-[var(--color-slate-600)]">Revisão {activity.revision || "não informada"} · {activity.status === "completed" ? "Concluída" :
          activity.status === "cancelled" ? "Cancelada" : activity.status === "in_progress" ? "Em execução" : "Aberta"}</p>
      </div>
      <button type="button" aria-label="Fechar inspeção" onClick={onDismiss}
        className="rounded-md border border-[var(--color-border)] px-2.5 py-1.5 text-xs">Fechar</button>
    </header>
    {activity.description && <p className="whitespace-pre-wrap rounded-md bg-[var(--color-panel)] p-3 text-xs leading-relaxed">
      {activity.description}
    </p>}
    <dl className="grid grid-cols-2 gap-3 text-xs">
      <div><dt className="text-[var(--color-muted)]">Responsável</dt><dd className="mt-1 font-medium">{activity.assignee?.display_name ||
        (mine ? "Você" : activity.assignee_user_id ? "Membro da equipe" : "Sem responsável")}</dd></div>
      <div><dt className="text-[var(--color-muted)]">Prazo</dt><dd className="mt-1 font-medium">{displayDate(activity.due_at)}</dd></div>
      <div><dt className="text-[var(--color-muted)]">Prioridade atribuída</dt><dd className="mt-1 font-medium">{activity.priority}</dd></div>
      <div><dt className="text-[var(--color-muted)]">Criada em</dt><dd className="mt-1 font-medium">{displayDate(activity.created_at)}</dd></div>
    </dl>
    <WorkPriorityReason activity={activity} />
    {activity.student_id && <p className="text-xs text-[var(--color-slate-600)]">
      Vínculo: aluno <span className="font-mono">{activity.student_id}</span>.{" "}
      {canOpenStudent && <Link href={"/alunos/" + encodeURIComponent(activity.student_id)}
        className="font-semibold text-[var(--color-blue)] hover:underline">Abrir ficha 360</Link>}
    </p>}
    {claimable && <button type="button" disabled={busy || !activity.revision} onClick={onClaim}
      className="w-full rounded-md bg-[var(--color-ink)] px-4 py-2.5 text-xs font-semibold text-white disabled:opacity-50">
      {busy ? "Atribuindo…" : "Assumir atividade"}
    </button>}
    {canResolve ? <form onSubmit={event => { event.preventDefault(); onResolve(); }}
      className="space-y-3 rounded-[var(--radius-card)] border border-[var(--color-border)] p-3">
      <h4 className="text-xs font-semibold">Registrar resultado e prosseguir</h4>
      <label className="block text-xs font-medium">Resultado da execução humana
        <select value={kind} onChange={event => setKind(event.target.value as WorkResultKind)} disabled={busy}
          className="mt-1.5 w-full rounded-md border border-[var(--color-border)] bg-white p-2.5 text-xs">
          {OUTCOMES.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
        <span className="mt-1 block text-[length:var(--type-caption)] text-[var(--color-muted)]">
          {OUTCOMES.find(item => item.value === kind)?.detail}
        </span>
      </label>
      {kind === "deferred" && <label className="block text-xs font-medium">Novo prazo
        <input type="datetime-local" required value={deferUntil} onChange={event => setDeferUntil(event.target.value)}
          disabled={busy} className="mt-1.5 block w-full rounded-md border border-[var(--color-border)] p-2.5 text-xs" />
      </label>}
      <label className="block text-xs font-medium">Observação auditável
        <textarea value={note} onChange={event => setNote(event.target.value)} maxLength={4000}
          required disabled={busy} rows={3}
          placeholder="Descreva o que foi feito ou o motivo do adiamento."
          className="mt-1.5 block w-full rounded-md border border-[var(--color-border)] p-2.5 text-xs" />
      </label>
      {error && <p role="alert" className="text-xs text-[var(--color-red)]">{error}</p>}
      <button type="submit" disabled={busy || !note.trim() || !activity.revision || (kind === "deferred" && !deferUntil)}
        className="w-full rounded-md bg-[var(--color-blue)] px-4 py-2.5 text-xs font-semibold text-white disabled:opacity-40">
        {busy ? "Registrando…" : kind === "deferred" ? "Registrar adiamento" : "Registrar e concluir atividade"}
      </button>
      <p className="text-[length:var(--type-caption)] text-[var(--color-muted)]">
        Esta operação registra apenas o trabalho humano. Não envia mensagem,
        confirma recuperação financeira nem altera a intervenção vinculada.
      </p>
    </form> : !claimable && <p className="rounded-md bg-[var(--color-panel)] p-3 text-xs text-[var(--color-slate-600)]">
      {activity.status === "completed" || activity.status === "cancelled"
        ? "Atividade encerrada. Histórico disponível somente para consulta."
        : "Para processar esta atividade, é necessário ser seu responsável e possuir permissão de edição."}
    </p>}
    <section aria-label="Auditoria da atividade">
      <h4 className="text-xs font-semibold">Histórico auditável</h4>
      {events.isLoading && <p role="status" className="mt-2 text-xs">Carregando eventos…</p>}
      {events.isError && <div role="alert" className="mt-2 text-xs">
        Não foi possível consultar eventos. <button type="button" onClick={() => void events.refetch()}
          className="font-semibold text-[var(--color-blue)]">Tentar novamente</button>
      </div>}
      {events.data && <ol className="mt-2 max-h-64 space-y-2 overflow-y-auto">
        {history.slice(-50).reverse().map(event => {
          const note = event.payload?.note;
          return <li key={event.id} className="border-l-2 border-[var(--color-border)] py-1 pl-3 text-xs">
            <span className="font-semibold">{event.event_type === "human_result_resolved"
              ? "Resultado humano registrado" : event.event_type.replaceAll("_", " ")}</span>
            <span className="ml-2 text-[var(--color-muted)]">{displayDate(event.created_at)}</span>
            {typeof note === "string" && <p className="mt-1 whitespace-pre-wrap text-[var(--color-slate-600)]">{note}</p>}
          </li>;
        })}
      </ol>}
      {history.length > 50 && <p className="mt-2 text-[length:var(--type-caption)] text-[var(--color-muted)]">
        Mostrando apenas os 50 últimos eventos recebidos nesta consulta.
      </p>}
    </section>
  </aside>;
}
