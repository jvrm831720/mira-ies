"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  History,
  Loader2,
  UserPlus,
  XCircle,
} from "lucide-react";
import { workApi } from "@/lib/work-api";
import { api } from "@/lib/api";
import type { WorkActivity, WorkActivityStatus } from "@/types/work";
import { cn } from "@/lib/utils";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

const STATUS_LABEL: Record<string, string> = {
  open: "Aberta",
  in_progress: "Em andamento",
  completed: "Concluída",
  cancelled: "Cancelada",
};

const TYPE_LABEL: Record<string, string> = {
  follow_up: "Follow-up",
  contact: "Contato",
  review: "Revisão",
  other: "Outro",
};

const EVENT_LABEL: Record<string, string> = {
  created: "Criação",
  assignee_changed: "Responsável",
  due_changed: "Prazo",
  status_changed: "Status",
  completed: "Conclusão",
  cancelled: "Cancelamento",
};

export function WorkActivitiesPanel() {
  const qc = useQueryClient();
  const [view, setView] = useState<"all" | "mine" | "overdue">("all");
  const [assigneeFilter, setAssigneeFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [activityType, setActivityType] = useState("follow_up");
  const [assigneeId, setAssigneeId] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const members = useQuery({
    queryKey: ["org-members", "work"],
    queryFn: () => api.listMembers(),
    retry: false,
  });

  const listParams = useMemo(() => {
    if (view === "mine") return { assignee: "me" as const, limit: 100 };
    if (view === "overdue") return { overdue_only: true, limit: 100 };
    if (assigneeFilter === "unassigned") return { assignee: "unassigned", limit: 100 };
    if (assigneeFilter) return { assignee: assigneeFilter, limit: 100 };
    return { limit: 100 };
  }, [view, assigneeFilter]);

  const activitiesQuery = useQuery({
    queryKey: ["work-activities", listParams],
    queryFn: () =>
      view === "mine" ? workApi.mine(100) : workApi.list(listParams),
    retry: false,
  });

  const eventsQuery = useQuery({
    queryKey: ["work-activity-events", selectedId],
    queryFn: () => workApi.events(selectedId!),
    enabled: Boolean(selectedId),
    retry: false,
  });

  const createMut = useMutation({
    mutationFn: () =>
      workApi.create({
        title: title.trim(),
        description: description.trim() || null,
        activity_type: activityType as "follow_up" | "contact" | "review" | "other",
        assignee_user_id: assigneeId || null,
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
      }),
    onSuccess: () => {
      setShowCreate(false);
      setTitle("");
      setDescription("");
      setAssigneeId("");
      setDueAt("");
      setFormError(null);
      void qc.invalidateQueries({ queryKey: ["work-activities"] });
    },
    onError: (err: Error) => setFormError(err.message),
  });

  const patchMut = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: Parameters<typeof workApi.patch>[1];
    }) => workApi.patch(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["work-activities"] });
      void qc.invalidateQueries({ queryKey: ["work-activity-events"] });
    },
  });

  const rows = activitiesQuery.data?.activities ?? [];
  const activeMembers =
    members.data?.members?.filter((m) => m.status === "active") ?? [];

  return (
    <section className="overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-sm">
      <div className="space-y-4 border-b border-[#EAECF0] px-4 py-4 sm:px-5">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
          <div>
            <h2 className="text-base font-semibold tracking-[-0.02em] text-[#101828]">
              Atividades operacionais
            </h2>
            <p className="mt-1 text-sm text-[#667085]">
              Atribuição, prazos e histórico persistidos · GET/POST /api/v1/work/activities · isolado por
              tenant
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowCreate((v) => !v)}
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-[#2563EB] px-4 text-sm font-semibold text-white hover:bg-[#1D4ED8]"
          >
            <UserPlus className="h-4 w-4" /> Nova atividade
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div role="tablist" className="flex flex-wrap gap-1 rounded-xl bg-[#F2F4F7] p-1">
            {(
              [
                { id: "all" as const, label: "Todas" },
                { id: "mine" as const, label: "Minhas" },
                { id: "overdue" as const, label: "Vencidas" },
              ] as const
            ).map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={view === tab.id}
                onClick={() => {
                  setView(tab.id);
                  setAssigneeFilter("");
                }}
                className={cn(
                  "inline-flex min-h-9 items-center rounded-lg px-3 py-2 text-sm font-medium",
                  view === tab.id
                    ? "bg-white text-[#101828] shadow-sm"
                    : "text-[#667085] hover:text-[#344054]"
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
          {view === "all" && (
            <select
              value={assigneeFilter}
              onChange={(e) => setAssigneeFilter(e.target.value)}
              aria-label="Filtrar por responsável"
              className="h-10 rounded-xl border border-[#D0D5DD] bg-white px-3 text-sm text-[#344054]"
            >
              <option value="">Todos os responsáveis</option>
              <option value="unassigned">Sem responsável</option>
              {activeMembers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name || m.email}
                </option>
              ))}
            </select>
          )}
        </div>

        {showCreate && (
          <form
            className="space-y-3 rounded-xl border border-[#D0D5DD] bg-[#F9FAFB] p-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!title.trim()) {
                setFormError("Informe um título.");
                return;
              }
              createMut.mutate();
            }}
          >
            <p className="text-sm font-semibold text-[#101828]">Criar atividade</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-xs font-medium text-[#475467]">
                Título *
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={200}
                  className="mt-1 h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-sm"
                  required
                />
              </label>
              <label className="block text-xs font-medium text-[#475467]">
                Tipo
                <select
                  value={activityType}
                  onChange={(e) => setActivityType(e.target.value)}
                  className="mt-1 h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-sm"
                >
                  <option value="follow_up">Follow-up</option>
                  <option value="contact">Contato</option>
                  <option value="review">Revisão</option>
                  <option value="other">Outro</option>
                </select>
              </label>
              <label className="block text-xs font-medium text-[#475467]">
                Responsável
                <select
                  value={assigneeId}
                  onChange={(e) => setAssigneeId(e.target.value)}
                  className="mt-1 h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-sm"
                >
                  <option value="">Sem responsável</option>
                  {activeMembers.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.display_name || m.email}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs font-medium text-[#475467]">
                Prazo
                <input
                  type="datetime-local"
                  value={dueAt}
                  onChange={(e) => setDueAt(e.target.value)}
                  className="mt-1 h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-sm"
                />
              </label>
            </div>
            <label className="block text-xs font-medium text-[#475467]">
              Descrição
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                maxLength={4000}
                className="mt-1 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 py-2 text-sm"
              />
            </label>
            {formError && (
              <p role="alert" className="text-sm text-[#B42318]">
                {formError}
              </p>
            )}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={createMut.isPending}
                className="inline-flex h-9 items-center gap-2 rounded-lg bg-[#2563EB] px-3 text-sm font-semibold text-white disabled:opacity-50"
              >
                {createMut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                Salvar
              </button>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="h-9 rounded-lg border border-[#D0D5DD] bg-white px-3 text-sm font-medium text-[#344054]"
              >
                Cancelar
              </button>
            </div>
          </form>
        )}
      </div>

      <div className="p-4 sm:p-5">
        {activitiesQuery.isError ? (
          <div role="alert" className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-4 text-sm text-[#B42318]">
            <p className="font-semibold">Não foi possível carregar atividades.</p>
            <p className="mt-1 text-xs">{(activitiesQuery.error as Error)?.message}</p>
            <button
              type="button"
              onClick={() => void activitiesQuery.refetch()}
              className="mt-2 font-semibold underline"
            >
              Tentar novamente
            </button>
          </div>
        ) : activitiesQuery.isLoading ? (
          <div className="space-y-3" aria-label="Carregando atividades">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-14 animate-pulse rounded-xl bg-[#F2F4F7]" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[#D0D5DD] bg-[#F9FAFB] px-5 py-10 text-center">
            <div className="mx-auto grid h-10 w-10 place-items-center rounded-full bg-white text-[#667085] ring-1 ring-[#EAECF0]">
              <ClipboardList className="h-5 w-5" />
            </div>
            <p className="mt-3 text-sm font-semibold text-[#101828]">
              {view === "mine"
                ? "Nenhuma atividade atribuída a você"
                : view === "overdue"
                  ? "Nenhuma atividade vencida"
                  : "Nenhuma atividade operacional"}
            </p>
            <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-[#667085]">
              Atividades são independentes dos logs de intervenção. Crie uma tarefa para atribuir
              responsável e prazo.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[880px] text-left text-sm">
              <thead>
                <tr className="border-b border-[#EAECF0] text-xs text-[#667085]">
                  <th className="px-3 py-3 font-medium">Título</th>
                  <th className="px-3 py-3 font-medium">Status</th>
                  <th className="px-3 py-3 font-medium">Responsável</th>
                  <th className="px-3 py-3 font-medium">Prazo</th>
                  <th className="px-3 py-3 font-medium">Ações</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item: WorkActivity) => (
                  <tr key={item.id} className="border-b border-[#F2F4F7]">
                    <td className="px-3 py-3.5">
                      <button
                        type="button"
                        onClick={() => setSelectedId(selectedId === item.id ? null : item.id)}
                        className="text-left font-semibold text-[#101828] hover:text-[#2563EB]"
                      >
                        {item.title}
                      </button>
                      <p className="mt-0.5 text-xs text-[#667085]">
                        {TYPE_LABEL[item.activity_type] ?? item.activity_type}
                      </p>
                    </td>
                    <td className="px-3 py-3.5">
                      <span
                        className={cn(
                          "inline-flex rounded-full px-2.5 py-1 text-xs font-medium",
                          item.status === "completed"
                            ? "bg-[#ECFDF3] text-[#027A48]"
                            : item.status === "cancelled"
                              ? "bg-[#F2F4F7] text-[#475467]"
                              : item.overdue
                                ? "bg-[#FEF3F2] text-[#B42318]"
                                : "bg-[#EFF4FF] text-[#3538CD]"
                        )}
                      >
                        {STATUS_LABEL[item.status] ?? item.status}
                        {item.overdue ? " · vencida" : ""}
                      </span>
                    </td>
                    <td className="px-3 py-3.5 text-[#475467]">
                      {item.assignee?.display_name || item.assignee?.email || (
                        <span className="text-[#98A2B3]">Sem responsável</span>
                      )}
                    </td>
                    <td className="px-3 py-3.5">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 text-xs",
                          item.overdue ? "font-semibold text-[#B42318]" : "text-[#475467]"
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
                            <button
                              type="button"
                              title="Concluir"
                              disabled={patchMut.isPending}
                              onClick={() =>
                                patchMut.mutate({
                                  id: item.id,
                                  body: { status: "completed" as WorkActivityStatus },
                                })
                              }
                              className="rounded-lg border border-[#ABEFC6] bg-[#ECFDF3] p-1.5 text-[#027A48]"
                            >
                              <CheckCircle2 className="h-4 w-4" />
                            </button>
                            <button
                              type="button"
                              title="Cancelar"
                              disabled={patchMut.isPending}
                              onClick={() =>
                                patchMut.mutate({
                                  id: item.id,
                                  body: { status: "cancelled" as WorkActivityStatus },
                                })
                              }
                              className="rounded-lg border border-[#FECDCA] bg-[#FEF3F2] p-1.5 text-[#B42318]"
                            >
                              <XCircle className="h-4 w-4" />
                            </button>
                            <select
                              aria-label="Atribuir responsável"
                              value={item.assignee_user_id ?? ""}
                              disabled={patchMut.isPending}
                              onChange={(e) => {
                                const v = e.target.value;
                                if (!v) {
                                  patchMut.mutate({ id: item.id, body: { clear_assignee: true } });
                                } else {
                                  patchMut.mutate({
                                    id: item.id,
                                    body: { assignee_user_id: v },
                                  });
                                }
                              }}
                              className="h-8 max-w-[140px] rounded-lg border border-[#D0D5DD] bg-white px-2 text-xs"
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
                          title="Histórico"
                          onClick={() => setSelectedId(selectedId === item.id ? null : item.id)}
                          className="rounded-lg border border-[#D0D5DD] bg-white p-1.5 text-[#475467]"
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

        {selectedId && (
          <div className="mt-4 rounded-xl border border-[#EAECF0] bg-[#F9FAFB] p-4">
            <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#101828]">
              <History className="h-4 w-4" /> Histórico da atividade
            </p>
            {eventsQuery.isLoading ? (
              <p className="text-xs text-[#667085]">Carregando eventos…</p>
            ) : eventsQuery.isError ? (
              <p className="text-xs text-[#B42318]">Não foi possível carregar o histórico.</p>
            ) : (eventsQuery.data?.events?.length ?? 0) === 0 ? (
              <p className="text-xs text-[#667085]">Sem eventos registrados.</p>
            ) : (
              <ul className="space-y-2">
                {eventsQuery.data!.events.map((ev) => (
                  <li key={ev.id} className="text-xs text-[#475467]">
                    <span className="font-medium text-[#101828]">
                      {EVENT_LABEL[ev.event_type] ?? ev.event_type}
                    </span>{" "}
                    · {formatDate(ev.created_at)}
                    {ev.payload ? (
                      <span className="ml-1 text-[#98A2B3]">
                        {JSON.stringify(ev.payload)}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <p className="mt-3 text-xs text-[#667085]">
          Prazo individual da atividade é independente da política global de 48h das intervenções
          planejadas. Status da atividade ≠ status de envio de InterventionLog.
        </p>
      </div>
    </section>
  );
}
