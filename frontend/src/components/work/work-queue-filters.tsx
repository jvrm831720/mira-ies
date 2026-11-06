"use client";
import { cn } from "@/lib/utils";
import type { OrgMember } from "@/types/api";
export type WorkQueueView = "all" | "mine" | "overdue";
export type WorkQueueFiltersProps = {
  view: WorkQueueView; setView: (next: WorkQueueView) => void;
  assigneeFilter: string; setAssigneeFilter: (value: string) => void;
  statusFilter: string; setStatusFilter: (value: string) => void;
  originFilter: string; setOriginFilter: (value: string) => void;
  priorityFilter: string; setPriorityFilter: (value: string) => void;
  activeMembers: Array<Pick<OrgMember, "id" | "display_name" | "email">>;
};
export function WorkQueueFilters({ view, setView, assigneeFilter, setAssigneeFilter,
  statusFilter, setStatusFilter, originFilter, setOriginFilter, priorityFilter,
  setPriorityFilter, activeMembers }: WorkQueueFiltersProps) {
  return (
<div className="flex flex-wrap items-center gap-2">
          <div role="tablist" className="flex flex-wrap gap-1 rounded-xl bg-[var(--color-panel)] p-1">
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
                    ? "bg-white text-[var(--color-ink)] shadow-sm"
                    : "text-[var(--color-slate-600)] hover:text-[var(--color-slate-600)]"
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
              className="h-10 rounded-xl border border-[var(--color-border)] bg-white px-3 text-sm text-[var(--color-slate-600)]"
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
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filtrar por status"
            className="h-10 rounded-xl border border-[var(--color-border)] bg-white px-3 text-sm text-[var(--color-slate-600)]"
          >
            <option value="">Todos os status</option>
            <option value="open">Aberta</option>
            <option value="in_progress">Em andamento</option>
            <option value="completed">Concluída</option>
            <option value="cancelled">Cancelada</option>
          </select>
          <select
            value={originFilter}
            onChange={(e) => setOriginFilter(e.target.value)}
            aria-label="Filtrar por origem"
            className="h-10 rounded-xl border border-[var(--color-border)] bg-white px-3 text-sm text-[var(--color-slate-600)]"
          >
            <option value="">Todas as origens</option>
            <option value="manual">Equipe</option>
            <option value="campaign">Campanha</option>
          </select>
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            aria-label="Filtrar por prioridade"
            className="h-10 rounded-xl border border-[var(--color-border)] bg-white px-3 text-sm text-[var(--color-slate-600)]"
          >
            <option value="">Todas as prioridades</option>
            <option value="urgent">Urgente</option>
            <option value="high">Alta</option>
            <option value="normal">Normal</option>
            <option value="low">Baixa</option>
          </select>
        </div>
  );
}