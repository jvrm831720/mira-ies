"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, ChevronDown, Copy, History, Plus, X } from "@/components/ui/icons";
import { Dialog } from "@/components/ui/dialog";
import type { ObjectField, ObjectKind, ObjectViewSpec, SavedObjectView } from "./object-index-types";
import {
  ViewApiError, createSavedObjectView, deleteSavedObjectView, duplicateSavedObjectView,
  favoriteSavedObjectView, getObjectSchema, listObjectViewRevisions, listSavedObjectViews,
  restoreSavedObjectView, shareSavedObjectView, updateSavedObjectView,
} from "@/lib/object-index-api";
import { cn } from "@/lib/utils";

type Props<T> = {
  objectKey: ObjectKind;
  fields: ObjectField<T>[];
  tenantId?: string | null;
  userId?: string | null;
  activeId?: string | null;
  currentConfig: ObjectViewSpec;
  onApply: (view: SavedObjectView) => void;
};

function failMessage(error: unknown): string {
  if (error instanceof ViewApiError && error.status === 409) {
    return "Conflito de edição (409). Recarregue a visualização para não sobrescrever as alterações de outra pessoa.";
  }
  if (error instanceof Error) return error.message;
  return "Não foi possível concluir a operação.";
}

/**
 * Manages metadata, not rows. Workspace scopes never override object RBAC.
 * The server is authoritative about who may see, edit, or share each view.
 */
export function ViewManager<T>({
  objectKey, fields, tenantId, userId, activeId, currentConfig, onApply,
}: Props<T>) {
  const client = useQueryClient();
  const queryKey = ["object-views", tenantId, userId, objectKey];
  const saved = useQuery({
    queryKey, queryFn: () => listSavedObjectViews(objectKey),
    enabled: Boolean(tenantId && userId), retry: false, staleTime: 20_000,
  });
  const schema = useQuery({
    queryKey: ["object-view-schema", tenantId, userId, objectKey],
    queryFn: () => getObjectSchema(objectKey),
    enabled: Boolean(tenantId && userId), retry: false, staleTime: 60_000,
  });
  const [menuOpen, setMenuOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [manageId, setManageId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [draftLabels, setDraftLabels] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const views = saved.data?.views || [];
  const active = views.find(view => view.id === activeId) || null;
  const managed = views.find(view => view.id === manageId) || null;
  const history = useQuery({
    queryKey: ["object-view-revisions", tenantId, userId, manageId],
    queryFn: () => listObjectViewRevisions(manageId!),
    enabled: dialogOpen && Boolean(manageId && managed?.can_edit), staleTime: 0, retry: false,
  });

  const sections: Array<{ name: string; entries: SavedObjectView[] }> = [
    { name: "Favoritas", entries: views.filter(view => view.favorite) },
    { name: "Minhas visualizações", entries: views.filter(view => view.scope === "personal") },
    { name: "Compartilhadas no workspace", entries: views.filter(view => view.scope === "workspace") },
  ];

  function begin(view: SavedObjectView | null = null) {
    setMenuOpen(false);
    setManageId(view?.id || null);
    setDraftName(view?.name || "");
    setDraftLabels({ ...(view?.config?.property_labels || (view ? {} : currentConfig.property_labels) || {}) });
    setError("");
    setDialogOpen(true);
  }

  async function refresh() {
    await client.invalidateQueries({ queryKey });
    if (manageId) await client.invalidateQueries({ queryKey: ["object-view-revisions", tenantId, userId, manageId] });
  }

  async function perform(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (e) {
      const message = failMessage(e);
      setError(message);
      toast.error(message);
      if (e instanceof ViewApiError && e.status === 409) await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function toggleFavorite(view: SavedObjectView) {
    await perform(async () => {
      await favoriteSavedObjectView(view.id, !view.favorite);
      toast.success(view.favorite ? "Favorito removido." : "Visualização favoritada.");
    });
  }

  async function save() {
    const name = draftName.trim();
    if (name.length < 2 || name.length > 80) { setError("Informe um nome de 2 a 80 caracteres."); return; }
    await perform(async () => {
      if (!managed) {
        const config = { ...currentConfig, property_labels: Object.fromEntries(
          Object.entries(draftLabels).filter(([, label]) => label.trim().length >= 2)
            .map(([key, label]) => [key, label.trim()])
        ) };
        const created = await createSavedObjectView(objectKey, name, config);
        onApply(created);
        toast.success("Visualização pessoal criada.");
      } else {
        if (!managed.can_edit || !managed.config || managed.schema_status === "unsupported") {
          throw new Error("Visualização sem permissão de edição ou com formato incompatível.");
        }
        // When the active index is this view, save its unsaved presentation
        // adjustments. Otherwise edit the persisted view, never unrelated state.
        const source = activeId === managed.id ? currentConfig : managed.config;
        const config = { ...source, property_labels: Object.fromEntries(
          Object.entries(draftLabels).filter(([, label]) => label.trim().length >= 2)
            .map(([key, label]) => [key, label.trim()])
        ) };
        const updated = await updateSavedObjectView(managed.id, name, config, managed.revision);
        if (activeId === managed.id) onApply(updated);
        toast.success("Visualização salva com nova revisão.");
      }
      setDialogOpen(false);
    });
  }

  async function duplicate() {
    if (!managed) return;
    await perform(async () => {
      const name = (managed.name.slice(0, 70) + " (cópia)").slice(0, 80);
      const copy = await duplicateSavedObjectView(managed.id, name);
      onApply(copy);
      setDialogOpen(false);
      toast.success("Cópia pessoal criada. Nenhum registro foi duplicado.");
    });
  }

  async function toggleShare() {
    if (!managed?.can_share) return;
    await perform(async () => {
      await shareSavedObjectView(managed.id,
        managed.scope === "workspace" ? "personal" : "workspace", managed.revision);
      toast.success(managed.scope === "workspace" ? "Compartilhamento encerrado." : "Visualização compartilhada.");
    });
  }

  async function restore(revision: number) {
    if (!managed?.can_edit) return;
    await perform(async () => {
      const updated = await restoreSavedObjectView(managed.id, revision, managed.revision);
      if (activeId === managed.id) onApply(updated);
      setDraftName(updated.name);
      setDraftLabels(updated.config?.property_labels || {});
      toast.success("Revisão " + revision + " restaurada como nova revisão.");
    });
  }

  async function remove() {
    if (!managed?.can_edit || !window.confirm('Excluir a visualização "' + managed.name + '"?')) return;
    await perform(async () => {
      await deleteSavedObjectView(managed.id, managed.revision);
      setDialogOpen(false);
      toast.success("Visualização excluída.");
    });
  }

  const config = managed?.config || currentConfig;
  const authorized = new Set(schema.data?.fields?.map(field => field.key) ||
    fields.map(field => field.key));

  return <div className="relative ml-2">
    <button type="button" onClick={() => setMenuOpen(!menuOpen)}
      aria-expanded={menuOpen} aria-haspopup="menu"
      className={cn("inline-flex h-8 shrink-0 items-center gap-1.5 rounded-[var(--radius-md)] px-2.5 text-xs hover:bg-[var(--color-panel)]",
        active ? "font-semibold text-[var(--color-ink)]" : "text-[var(--color-slate-600)]")}>
      {active ? active.name : activeId ? "View indisponível" : "Visualizações"}
      <ChevronDown className="h-3.5 w-3.5" />
    </button>
    {menuOpen && <div className="absolute left-0 top-[calc(100%+6px)] z-40 w-[min(90vw,360px)] rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-2 shadow-[var(--shadow-overlay)]"
      role="menu" aria-label="Visualizações salvas">
      {saved.isLoading && <p role="status" className="px-2 py-2 text-xs">Carregando visualizações…</p>}
      {saved.isError && <p role="alert" className="px-2 py-2 text-xs text-[var(--color-red)]">Não foi possível carregar as visualizações.</p>}
      {sections.map(section => section.entries.length > 0 && <div key={section.name} className="pb-1">
        <p className="px-2 pt-2 pb-1 text-[length:var(--type-overline)] font-semibold uppercase text-[var(--color-muted)]">{section.name}</p>
        {section.entries.map(view => <div key={view.id} className="flex items-center gap-1 rounded-md hover:bg-[var(--color-panel)]">
          <button type="button" role="menuitem" disabled={view.schema_status === "unsupported"}
            onClick={() => { onApply(view); setMenuOpen(false); }}
            className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-2 text-left text-xs disabled:opacity-40">
            <span className="min-w-0 flex-1 truncate">{view.name}</span>
            {view.id === activeId && <Check className="h-3.5 w-3.5 shrink-0 text-[var(--color-blue)]" />}
            {view.schema_status !== "current" && <span className="text-[length:var(--type-overline)] text-[var(--color-muted)]">{view.schema_status === "upgraded" ? "v1" : "incompatível"}</span>}
          </button>
          <button type="button" aria-label={(view.favorite ? "Desfavoritar " : "Favoritar ") + view.name}
            aria-pressed={view.favorite} onClick={() => void toggleFavorite(view)}
            className="rounded p-1.5 text-xs text-[var(--color-blue)] hover:bg-white">
            {view.favorite ? "★" : "☆"}
          </button>
          <button type="button" aria-label={"Gerenciar " + view.name}
            onClick={() => begin(view)}
            className="rounded px-1.5 py-1 text-xs text-[var(--color-muted)] hover:bg-white">•••</button>
        </div>)}
      </div>)}
      {!saved.isLoading && !views.length && <p className="px-2 py-3 text-xs text-[var(--color-muted)]">Nenhuma visualização salva.</p>}
      <div className="mt-1 border-t border-[var(--color-border)] pt-1">
        <button type="button" role="menuitem" onClick={() => begin()}
          className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-xs hover:bg-[var(--color-panel)]">
          <Plus className="h-3.5 w-3.5" /> Salvar visualização atual
        </button>
      </div>
    </div>}

    <Dialog open={dialogOpen} onOpenChange={open => { if (!open && !busy) setDialogOpen(false); }}
      title={managed ? "Gerenciar visualização" : "Criar visualização pessoal"}
      description="Salva apenas a configuração de consulta e apresentação. Não copia registros."
      className="max-w-[610px]">
      <div className="max-h-[70vh] space-y-4 overflow-y-auto p-1">
        {managed && <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--color-muted)]">
          <span>{managed.scope === "workspace" ? "Compartilhada no workspace" : "Pessoal"}</span>
          <span>·</span><span>Revisão {managed.revision}</span>
          {managed.schema_status === "upgraded" && <span>· Schema v1 convertido apenas para leitura</span>}
          {managed.schema_status === "unsupported" && <p role="alert">Configuração antiga incompatível; dados preservados no banco. Não aplique nem sobrescreva.</p>}
        </div>}
        <label className="block text-xs font-medium">Nome
          <input value={draftName} onChange={event => setDraftName(event.target.value)} maxLength={80}
            disabled={busy || Boolean(managed && !managed.can_edit)}
            className="mt-1 h-10 w-full rounded-md border border-[var(--color-border)] bg-white px-3 text-sm disabled:opacity-50" />
        </label>
        {(!managed || managed.can_edit && !!managed.config) && <div className="space-y-2 rounded-md border border-[var(--color-border)] p-3">
          <p className="text-xs font-semibold">Rótulos das propriedades</p>
          <p className="text-[length:var(--type-caption)] text-[var(--color-muted)]">Personalize nomes na view, sem alterar dados, tipos ou permissões.</p>
          {config.columns.filter(key => authorized.has(key)).map(key => {
            const field = fields.find(item => item.key === key);
            return <label key={key} className="flex items-center gap-2 text-xs">
              <span className="w-32 shrink-0 truncate text-[var(--color-muted)]">{field?.title || key}</span>
              <input value={draftLabels[key] || ""} placeholder={field?.title || key}
                maxLength={80} onChange={event => setDraftLabels(old => ({ ...old, [key]: event.target.value }))}
                disabled={busy} className="h-9 min-w-0 flex-1 rounded-md border border-[var(--color-border)] px-2 text-xs" />
            </label>;
          })}
        </div>}
        {schema.data?.custom_properties?.length ? <div className="rounded-md border border-[var(--color-border)] p-3">
          <p className="text-xs font-semibold">Propriedades customizadas do workspace</p>
          <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">
            Registradas na Importação Inteligente. Não podem ser incluídas em filtros ou colunas
            deste índice até existir consulta remota validada pelo backend.
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {schema.data.custom_properties.map(item =>
              <span key={item.key} title={item.reason}
                className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-1 text-xs text-[var(--color-slate-600)]">
                {item.label}
              </span>)}
          </div>
        </div> : null}
        {managed?.can_edit && <div className="space-y-2 rounded-md border border-[var(--color-border)] p-3">
          <div className="flex items-center gap-2 text-xs font-semibold"><History className="h-4 w-4" /> Histórico de revisões</div>
          {history.isLoading && <p role="status" className="text-xs">Carregando histórico…</p>}
          {history.isError && <p role="alert" className="text-xs text-[var(--color-red)]">Falha ao consultar revisões.</p>}
          {history.data?.revisions.map(item => <div key={item.revision}
            className="flex items-center gap-2 border-t border-[var(--color-border-subtle)] py-2 text-xs">
            <span className="flex-1 truncate">#{item.revision} · {item.name} · {item.scope === "workspace" ? "Workspace" : "Pessoal"}</span>
            <span className="shrink-0 text-[var(--color-muted)]">{new Date(item.created_at).toLocaleDateString("pt-BR")}</span>
            <button type="button" disabled={busy || item.revision === managed.revision || item.schema_version !== 1}
              onClick={() => void restore(item.revision)}
              className="rounded px-2 py-1 font-medium text-[var(--color-blue)] disabled:opacity-40">
              Restaurar
            </button>
          </div>)}
        </div>}
        {error && <p role="alert" className="rounded-md border border-[var(--color-red)] p-2 text-xs text-[var(--color-red)]">{error}</p>}
        <div className="flex flex-wrap items-center gap-2 border-t border-[var(--color-border)] pt-3">
          {(!managed || managed.can_edit && managed.schema_status !== "unsupported") &&
            <button type="button" disabled={busy} onClick={() => void save()}
              className="h-9 rounded-md bg-[var(--color-ink)] px-4 text-xs font-semibold text-white disabled:opacity-40">
              {busy ? "Salvando…" : managed ? "Salvar revisão" : "Criar"}
            </button>}
          {managed && <button type="button" disabled={busy || managed.schema_status === "unsupported"} onClick={() => void duplicate()}
            className="inline-flex h-9 items-center gap-1.5 rounded-md border border-[var(--color-border)] px-3 text-xs disabled:opacity-40">
            <Copy className="h-3.5 w-3.5" /> Duplicar
          </button>}
          {managed?.can_share && <button type="button" disabled={busy || managed.schema_status === "unsupported"} onClick={() => void toggleShare()}
            className="h-9 rounded-md border border-[var(--color-border)] px-3 text-xs disabled:opacity-40">
            {managed.scope === "workspace" ? "Tornar pessoal" : "Compartilhar"}
          </button>}
          {managed?.can_edit && <button type="button" disabled={busy} onClick={() => void remove()}
            className="h-9 rounded-md px-3 text-xs text-[var(--color-red)] disabled:opacity-40">Excluir</button>}
          <button type="button" disabled={busy} onClick={() => setDialogOpen(false)}
            className="ml-auto inline-flex h-9 items-center gap-1 rounded-md px-3 text-xs text-[var(--color-muted)] disabled:opacity-40">
            <X className="h-3.5 w-3.5" /> Fechar
          </button>
        </div>
      </div>
    </Dialog>
  </div>;
}
