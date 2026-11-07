"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { workApi } from "@/lib/work-api";
import { hasNavigationPermission } from "@/components/layout/navigation";
import { WorkItemInspector } from "./work-item-inspector";
import type { WorkActivity, WorkPerspective, WorkResultKind } from "@/types/work";

const VIEWS: Array<{ id: WorkPerspective; label: string; description: string }> = [
  { id: "mine", label: "Para mim", description: "Atividades abertas sob sua responsabilidade" },
  { id: "team", label: "Equipe", description: "Pendências atribuídas a outras pessoas" },
  { id: "unassigned", label: "Sem responsável", description: "Atividades disponíveis para assumir" },
  { id: "history", label: "Histórico", description: "Atividades humanas concluídas ou canceladas" },
];
const PAGE_SIZE = 25;

function dateLabel(date: string | null | undefined): string {
  if (!date || !Number.isFinite(Date.parse(date))) return "Sem prazo";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo",
  }).format(new Date(date));
}
function statusLabel(item: WorkActivity): string {
  return ({ open: "Aberta", in_progress: "Em andamento", completed: "Concluída",
    cancelled: "Cancelada" } as Record<string, string>)[item.status] || item.status;
}
function errorText(error: unknown): string {
  if (error instanceof Error) {
    return (error instanceof ApiError && error.status === 409) ||
      error.message.includes("409") || error.message.includes("revisão") ||
      error.message.includes("alterada em outra")
      ? "Conflito de edição (409). A fila foi atualizada; revise a atividade antes de continuar."
      : error.message;
  }
  return "Não foi possível registrar esta decisão.";
}

/** Same WorkActivity queue as the legacy Work Center; no mirrored tasks or financial outcomes. */
export function WorkInbox() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["org-me"], queryFn: api.me, retry: false, staleTime: 60_000 });
  const tenant = me.data?.tenant_id || "";
  const user = me.data?.user_id || "";
  const allowed = Boolean(tenant && user && hasNavigationPermission(me.data, "students.view") &&
    hasNavigationPermission(me.data, "students.edit"));
  const [view, setView] = useState<WorkPerspective>("mine");
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [kind, setKind] = useState<WorkResultKind>("done");
  const [note, setNote] = useState("");
  const [deferUntil, setDeferUntil] = useState("");
  const [error, setError] = useState<string | null>(null);
  const pendingOperation = useRef<{ signature: string; key: string } | null>(null);
  const lastScope = useRef<string>("");

  useEffect(() => {
    const scope = tenant + ":" + user;
    if (lastScope.current && lastScope.current !== scope) {
      setView("mine"); setOffset(0); setSelectedId(null);
      setKind("done"); setNote(""); setDeferUntil(""); pendingOperation.current = null;
    }
    if (tenant && user) lastScope.current = scope;
  }, [tenant, user]);

  const queue = useQuery({
    queryKey: ["work-inbox", tenant, user, view, offset],
    queryFn: () => workApi.inbox(view, offset, PAGE_SIZE),
    enabled: allowed, retry: false, staleTime: 10_000,
  });
  const counts = useQuery({
    queryKey: ["work-inbox-counts", tenant, user],
    queryFn: () => workApi.inboxCounts(),
    enabled: allowed, retry: false, staleTime: 10_000,
  });
  const rows = queue.data?.items || [];
  const selected = rows.find(item => item.id === selectedId) || null;
  const selectedDetails = useQuery({
    queryKey: ["work-activity", tenant, user, selectedId],
    queryFn: () => workApi.get(selectedId!),
    enabled: allowed && Boolean(selectedId) && !selected,
    staleTime: 10_000, retry: false,
  });
  const inspector = selected || selectedDetails.data || null;

  function select(item: WorkActivity) {
    setSelectedId(item.id);
    setError(null); setNote(""); setKind("done"); setDeferUntil("");
    pendingOperation.current = null;
  }

  function changeView(next: WorkPerspective) {
    if (next === view) return;
    setView(next); setOffset(0); setSelectedId(null);
    setNote(""); setDeferUntil(""); setError(null); pendingOperation.current = null;
  }

  /** Preserve the exact operation key for retries of the identical human decision. */
  function operationKey(signature: string): string {
    if (pendingOperation.current?.signature === signature) return pendingOperation.current.key;
    const key = crypto.randomUUID().replaceAll("-", "");
    pendingOperation.current = { signature, key };
    return key;
  }

  async function refreshAll() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["work-inbox", tenant, user] }),
      qc.invalidateQueries({ queryKey: ["work-inbox-counts", tenant, user] }),
      qc.invalidateQueries({ queryKey: ["work-activities"] }),
      qc.invalidateQueries({ queryKey: ["work-activity"] }),
      qc.invalidateQueries({ queryKey: ["work-activity-events"] }),
      qc.invalidateQueries({ queryKey: ["work-activity-summary"] }),
    ]);
  }

  const claim = useMutation({
    mutationFn: (activity: WorkActivity) => workApi.claim(activity.id, {
      expected_revision: activity.revision!,
      operation_key: operationKey("claim:" + activity.id + ":" + activity.revision),
    }),
    onSuccess: async result => {
      pendingOperation.current = null;
      await refreshAll();
      setView("mine"); setOffset(0);
      setSelectedId(result.activity.id); setError(null);
      toast.success("Atividade atribuída a você; alteração registrada no histórico.");
    },
    onError: async reason => {
      setError(errorText(reason)); await refreshAll();
    },
  });
  const resolve = useMutation({
    mutationFn: (activity: WorkActivity) => {
      const next_due_at = kind === "deferred" && deferUntil ?
        new Date(deferUntil).toISOString() : undefined;
      return workApi.resolve(activity.id, {
        expected_revision: activity.revision!, kind, note: note.trim(), next_due_at,
        operation_key: operationKey([
          "resolve", activity.id, String(activity.revision), kind, note.trim(), next_due_at || "",
        ].join("|")),
      });
    },
    onSuccess: async (result, activity) => {
      pendingOperation.current = null;
      setNote(""); setDeferUntil(""); setError(null);
      const next = rows.find(item => item.id !== activity.id &&
        (view === "history" || ["open", "in_progress"].includes(item.status)));
      setSelectedId(next?.id || null);
      if (!next && offset > 0) setOffset(value => Math.max(0, value - PAGE_SIZE));
      await refreshAll();
      toast.success(result.idempotent_replay ? "Resultado já registrado." :
        kind === "deferred" ? "Adiamento registrado. Próxima atividade pronta." :
          "Trabalho humano concluído e auditado. Próxima atividade pronta.");
    },
    onError: async reason => {
      setError(errorText(reason));
      await refreshAll();
    },
  });

  const busy = claim.isPending || resolve.isPending;
  if (me.isLoading) return <section role="status" className="rounded-xl border p-5 text-xs">Verificando acesso ao Meu Trabalho…</section>;
  if (!allowed || me.isError) return <section role="alert" className="rounded-xl border p-5 text-xs text-[var(--color-slate-600)]">
    Meu Trabalho exige sessão humana e permissão para ler e operar atividades. Nenhuma fila foi carregada.
  </section>;

  return <section aria-label="Meu Trabalho operacional"
    className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white shadow-sm">
    <header className="border-b border-[var(--color-border)] p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[length:var(--type-overline)] font-semibold uppercase tracking-[0.08em] text-[var(--color-blue)]">Fila humana central</p>
          <h2 className="mt-1 text-xl font-semibold text-[var(--color-ink)]">Meu Trabalho</h2>
          <p className="mt-1 text-xs text-[var(--color-slate-600)]">
            Prioridade explicada, decisões em sequência e resultado auditado — sem confundir trabalho com envios ou pagamentos.
          </p>
        </div>
        <button type="button" onClick={() => void refreshAll()} disabled={busy || queue.isFetching}
          className="rounded-md border border-[var(--color-border)] px-3 py-2 text-xs font-semibold disabled:opacity-50">
          Atualizar fila
        </button>
      </div>
      <div role="tablist" aria-label="Perspectivas de Meu Trabalho" className="mt-4 flex gap-1 overflow-x-auto border-b border-[var(--color-border)]">
        {VIEWS.map(item => <button key={item.id} type="button" role="tab"
          aria-selected={view === item.id} title={item.description}
          onClick={() => changeView(item.id)}
          className={"shrink-0 border-b-2 px-3 py-2.5 text-xs font-semibold " +
            (view === item.id ? "border-[var(--color-blue)] text-[var(--color-ink)]" :
              "border-transparent text-[var(--color-slate-600)] hover:text-[var(--color-blue)]")}>
          {item.label} <span className="ml-1 tabular-nums text-[var(--color-muted)]">
            {counts.isError ? "—" : counts.data?.counts[item.id] ?? "…"}
          </span>
        </button>)}
      </div>
    </header>
    <div className={selectedId ? "grid min-h-[420px] lg:grid-cols-[minmax(0,1fr)_minmax(300px,0.88fr)]" : "grid min-h-[420px]"}>
      <div role="tabpanel" aria-label={VIEWS.find(item => item.id === view)?.label} className="min-w-0">
        <div className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3">
          <p className="text-xs text-[var(--color-slate-600)]">{VIEWS.find(item => item.id === view)?.description}</p>
          <p className="whitespace-nowrap text-xs font-medium tabular-nums">{queue.data ? queue.data.total.toLocaleString("pt-BR") + " registros" : "—"}</p>
        </div>
        {queue.isLoading && <p role="status" className="p-5 text-xs">Carregando atividades…</p>}
        {queue.isError && <div role="alert" className="space-y-2 p-5 text-xs">
          <p>Não foi possível consultar a fila.</p>
          <button type="button" onClick={() => void queue.refetch()} className="font-semibold text-[var(--color-blue)]">Tentar novamente</button>
        </div>}
        {queue.data && rows.length === 0 && <p className="p-5 text-xs text-[var(--color-muted)]">
          Nenhuma atividade nesta perspectiva. Não há resultados parciais exibidos como totais.
        </p>}
        <ul className="divide-y divide-[var(--color-border-subtle)]">
          {rows.map(item => <li key={item.id}>
            <button type="button" onClick={() => select(item)} aria-current={selectedId === item.id ? "true" : undefined}
              className={"flex w-full min-w-0 items-start justify-between gap-3 px-4 py-3.5 text-left hover:bg-[var(--color-panel)] " +
                (selectedId === item.id ? "bg-[var(--color-blue-tint)]" : "")}>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-semibold text-[var(--color-ink)]">{item.title}</p>
                <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-slate-600)]">
                  {statusLabel(item)} · {item.assignee?.display_name || (item.assignee_user_id ? "Equipe" : "Sem responsável")}
                </p>
                <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">
                  {item.priority_reasons?.slice(0, 2).map(reason => reason.label).join(" · ") || "Priorização indisponível"}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1 text-right">
                <span className="text-[length:var(--type-caption)] font-semibold">{item.priority}</span>
                <span className="text-[length:var(--type-caption)] text-[var(--color-muted)]">{dateLabel(item.due_at)}</span>
              </div>
            </button>
          </li>)}
        </ul>
        {queue.data && <div className="flex items-center justify-between gap-3 border-t border-[var(--color-border)] p-3">
          <span className="text-xs text-[var(--color-muted)]">Exibindo {rows.length ? offset + 1 : 0}–{offset + rows.length} de {queue.data.total}</span>
          <div className="flex items-center gap-2">
            <button type="button" disabled={offset === 0 || busy} onClick={() => { setOffset(Math.max(0, offset - PAGE_SIZE)); setSelectedId(null); }}
              className="rounded-md border px-3 py-1.5 text-xs disabled:opacity-40">Anterior</button>
            <button type="button" disabled={!queue.data.has_more || busy}
              onClick={() => { setOffset(offset + PAGE_SIZE); setSelectedId(null); }}
              className="rounded-md border px-3 py-1.5 text-xs disabled:opacity-40">Próxima</button>
          </div>
        </div>}
      </div>
      {selectedId && <div className="min-w-0">
        {inspector ? <WorkItemInspector key={inspector.id} activity={inspector}
          activeUserId={user} canEdit={allowed}
          canOpenStudent={hasNavigationPermission(me.data, "students.sensitive.view")} kind={kind} setKind={value => {setKind(value); setError(null);}}
          note={note} setNote={value => {setNote(value); setError(null);}}
          deferUntil={deferUntil} setDeferUntil={value => {setDeferUntil(value); setError(null);}}
          error={error} busy={busy}
          onClaim={() => {if (!busy && inspector.revision) claim.mutate(inspector);}}
          onResolve={() => {
            if (busy || !note.trim() || !inspector.revision) return;
            if (kind === "deferred" && (!deferUntil || Number.isNaN(Date.parse(deferUntil)) ||
              new Date(deferUntil).getTime() <= Date.now())) {
              setError("O adiamento exige uma nova data futura."); return;
            }
            resolve.mutate(inspector);
          }}
          onDismiss={() => {setSelectedId(null); setError(null);}} />
          : <p role={selectedDetails.isError ? "alert" : "status"} className="p-5 text-xs text-[var(--color-slate-600)]">
            {selectedDetails.isError ? "Atividade não encontrada ou indisponível neste workspace." : "Carregando detalhes…"}
          </p>}
      </div>}
    </div>
    <footer className="border-t border-[var(--color-border)] bg-[var(--color-panel)] p-3 text-[length:var(--type-caption)] text-[var(--color-muted)]">
      Resolver uma atividade não executa disparos, não altera InterventionLog e não confirma pagamento ou recuperação financeira.
    </footer>
  </section>;
}

