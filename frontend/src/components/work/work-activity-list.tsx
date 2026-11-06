"use client";

import { CalendarClock, CheckCircle2, ClipboardList, History, Play, RotateCcw, XCircle } from "@/components/ui/icons";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { WorkActivity, WorkActivityStatus } from "@/types/work";
import { formatDate, STATUS_LABEL, TYPE_LABEL, PRIORITY_LABEL, ORIGIN_LABEL } from "./work-activity-labels";

type ActiveMember = Awaited<ReturnType<typeof api.listMembers>>["members"][number];
type PatchBody = Parameters<typeof import("@/lib/work-api").workApi.patch>[1];
type Props = {
  rows: WorkActivity[];
  view: "all" | "mine" | "overdue";
  selectedId: string | null;
  activeMembers: ActiveMember[];
  loading: boolean; error: boolean; errorMessage?: string;
  patchPending: boolean;
  onRetry: () => void;
  onToggle: (id: string) => void;
  onPatch: (payload: {id: string; body: PatchBody}) => void;
};

export function WorkActivityList({rows, view, selectedId, activeMembers, loading, error, errorMessage,
  patchPending, onRetry, onToggle, onPatch}: Props) {
  return <>
        {error ? (
          <div
            role="alert"
            className="rounded-xl border border-[var(--color-red-tint-border)] bg-[var(--color-red-tint)] p-4 text-sm text-[var(--color-red)]"
          >
            <p className="font-semibold">Não foi possível carregar atividades.</p>
            <p className="mt-1 text-xs">{errorMessage}</p>
            <button
              type="button"
              onClick={() => void onRetry()}
              className="mt-2 font-semibold underline"
            >
              Tentar novamente
            </button>
          </div>
        ) : loading ? (
          <div className="space-y-3" aria-label="Carregando atividades">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-14 animate-pulse rounded-xl bg-[var(--color-panel)]" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-source-f9fafb)] px-5 py-10 text-center">
            <div className="mx-auto grid h-10 w-10 place-items-center rounded-full bg-white text-[var(--color-slate-600)] ring-1 ring-[var(--color-border)]">
              <ClipboardList className="h-5 w-5" />
            </div>
            <p className="mt-3 text-sm font-semibold text-[var(--color-ink)]">
              {view === "mine"
                ? "Nenhuma atividade atribuída a você"
                : view === "overdue"
                  ? "Nenhuma atividade vencida"
                  : "Nenhuma atividade operacional"}
            </p>
            <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-[var(--color-slate-600)]">
              Atividades são independentes dos logs de intervenção. Use &quot;Criar atividade&quot; nas
              filas de logs ou o botão acima para atribuir responsável e prazo.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[880px] text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-slate-600)]">
                  <th className="px-3 py-3 font-medium">Título</th>
                  <th className="px-3 py-3 font-medium">Status</th>
                  <th className="px-3 py-3 font-medium">Responsável</th>
                  <th className="px-3 py-3 font-medium">Prazo</th>
                  <th className="px-3 py-3 font-medium">Ações</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item: WorkActivity) => (
                  <tr key={item.id} className="border-b border-[var(--color-panel)]">
                    <td className="px-3 py-3.5">
                      <button
                        type="button"
                        onClick={() => onToggle(item.id)}
                        className="text-left font-semibold text-[var(--color-ink)] hover:text-[var(--color-blue)]"
                      >
                        {item.title}
                      </button>
                      <p className="mt-0.5 text-xs text-[var(--color-slate-600)]">
                        {TYPE_LABEL[item.activity_type] ?? item.activity_type}
                        {` · ${ORIGIN_LABEL[item.origin_type] ?? item.origin_type}`}
                        {` · prioridade ${PRIORITY_LABEL[item.priority] ?? item.priority}`}
                        {item.intervention_log_id ? " · vinculada a log" : ""}
                        {item.student_id ? " · com aluno" : ""}
                      </p>
                      {item.campaign_id && (
                        <p className="mt-1 text-[10px] font-medium text-[var(--color-source-3538cd)]">
                          Campanha · {item.campaign_id.slice(0, 8)}…
                        </p>
                      )}
                    </td>
                    <td className="px-3 py-3.5">
                      <span
                        className={cn(
                          "inline-flex rounded-full px-2.5 py-1 text-xs font-medium",
                          item.status === "completed"
                            ? "bg-[var(--color-source-ecfdf3)] text-[var(--color-source-027a48)]"
                            : item.status === "cancelled"
                              ? "bg-[var(--color-panel)] text-[var(--color-slate-600)]"
                              : item.overdue
                                ? "bg-[var(--color-red-tint)] text-[var(--color-red)]"
                                : "bg-[var(--color-source-eff4ff)] text-[var(--color-source-3538cd)]"
                        )}
                      >
                        {STATUS_LABEL[item.status] ?? item.status}
                        {item.overdue ? " · vencida" : ""}
                      </span>
                    </td>
                    <td className="px-3 py-3.5 text-[var(--color-slate-600)]">
                      {item.assignee?.display_name || item.assignee?.email || (
                        <span className="text-[var(--color-muted)]">Sem responsável</span>
                      )}
                    </td>
                    <td className="px-3 py-3.5">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 text-xs",
                          item.overdue ? "font-semibold text-[var(--color-red)]" : "text-[var(--color-slate-600)]"
                        )}
                      >
                        <CalendarClock className="h-3.5 w-3.5" />
                        {formatDate(item.due_at)}
                      </span>
                    </td>
                    <td className="px-3 py-3.5">
                      <div className="flex flex-wrap gap-1">
                        {item.status !== "completed" && item.status !== "cancelled" && (
                          <>
                            {item.status === "open" ? (
                              <button
                                type="button"
                                title="Iniciar atividade"
                                aria-label={`Iniciar ${item.title}`}
                                disabled={patchPending}
                                onClick={() =>
                                  onPatch({
                                    id: item.id,
                                    body: { status: "in_progress" as WorkActivityStatus },
                                  })
                                }
                                className="rounded-lg border border-[var(--color-border)] bg-white p-1.5 text-[var(--color-slate-600)]"
                              >
                                <Play className="h-4 w-4" />
                              </button>
                            ) : (
                              <button
                                type="button"
                                title="Retomar como aberta"
                                aria-label={`Retomar ${item.title}`}
                                disabled={patchPending}
                                onClick={() =>
                                  onPatch({
                                    id: item.id,
                                    body: { status: "open" as WorkActivityStatus },
                                  })
                                }
                                className="rounded-lg border border-[var(--color-border)] bg-white p-1.5 text-[var(--color-slate-600)]"
                              >
                                <RotateCcw className="h-4 w-4" />
                              </button>
                            )}
                            <button
                              type="button"
                              title="Concluir"
                              disabled={patchPending}
                              onClick={() =>
                                onPatch({
                                  id: item.id,
                                  body: { status: "completed" as WorkActivityStatus },
                                })
                              }
                              className="rounded-lg border border-[var(--color-source-abefc6)] bg-[var(--color-source-ecfdf3)] p-1.5 text-[var(--color-source-027a48)]"
                            >
                              <CheckCircle2 className="h-4 w-4" />
                            </button>
                            <button
                              type="button"
                              title="Cancelar"
                              disabled={patchPending}
                              onClick={() =>
                                onPatch({
                                  id: item.id,
                                  body: { status: "cancelled" as WorkActivityStatus },
                                })
                              }
                              className="rounded-lg border border-[var(--color-red-tint-border)] bg-[var(--color-red-tint)] p-1.5 text-[var(--color-red)]"
                            >
                              <XCircle className="h-4 w-4" />
                            </button>
                            <select
                              aria-label="Alterar prioridade"
                              value={item.priority}
                              disabled={patchPending}
                              onChange={(e) =>
                                onPatch({
                                  id: item.id,
                                  body: {
                                    priority: e.target.value as "low" | "normal" | "high" | "urgent",
                                  },
                                })
                              }
                              className="h-8 rounded-lg border border-[var(--color-border)] bg-white px-2 text-xs"
                            >
                              <option value="urgent">Urgente</option>
                              <option value="high">Alta</option>
                              <option value="normal">Normal</option>
                              <option value="low">Baixa</option>
                            </select>
                            <select
                              aria-label="Atribuir responsável"
                              value={item.assignee_user_id ?? ""}
                              disabled={patchPending}
                              onChange={(e) => {
                                const v = e.target.value;
                                if (!v) {
                                  onPatch({ id: item.id, body: { clear_assignee: true } });
                                } else {
                                  onPatch({
                                    id: item.id,
                                    body: { assignee_user_id: v },
                                  });
                                }
                              }}
                              className="h-8 max-w-[140px] rounded-lg border border-[var(--color-border)] bg-white px-2 text-xs"
                            >
                              <option value="">Sem resp.</option>
                              {activeMembers.map((m) => (
                                <option key={m.id} value={m.id}>
                                  {m.display_name || m.email}
                                </option>
                              ))}
                            </select>
                          </>
                        )}
                        <button
                          type="button"
                          title="Detalhe e histórico"
                          onClick={() => onToggle(item.id)}
                          className="rounded-lg border border-[var(--color-border)] bg-white p-1.5 text-[var(--color-slate-600)]"
                        >
                          <History className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}


  </>;
}
