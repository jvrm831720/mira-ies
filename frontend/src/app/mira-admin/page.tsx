"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, Database, FileCheck2, History, Layers3, RefreshCw, ShieldCheck } from "lucide-react";

type Row = Record<string, unknown>;
type Section = "modalities" | "authorizations" | "datasets" | "runs" | "audit";

const sections: { id: Section; label: string; icon: typeof Layers3; endpoint: string; key: string }[] = [
  { id: "modalities", label: "Modalidades", icon: Layers3, endpoint: "/api/mira-admin/modalities", key: "modalities" },
  { id: "authorizations", label: "Autorizações", icon: FileCheck2, endpoint: "/api/mira-admin/authorizations", key: "" },
  { id: "datasets", label: "Conjuntos de dados", icon: Database, endpoint: "/api/mira-admin/datasets", key: "datasets" },
  { id: "runs", label: "Treinamentos e modelos", icon: Activity, endpoint: "/api/mira-admin/runs", key: "runs" },
  { id: "audit", label: "Trilha de auditoria", icon: History, endpoint: "/api/mira-admin/audit", key: "events" },
];

function label(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function prettyKey(key: string): string {
  return key.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function MiraAdminGovernancePage() {
  const [active, setActive] = useState<Section>("modalities");
  const [data, setData] = useState<Record<Section, Row[]>>({
    modalities: [], authorizations: [], datasets: [], runs: [], audit: [],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.all(sections.map(async (section) => {
        const response = await fetch(section.endpoint, { credentials: "same-origin", cache: "no-store" });
        if (!response.ok) {
          if (response.status === 401) throw new Error("Sessão administrativa ausente ou expirada. Entre novamente no MIRA Control Center.");
          if (response.status === 403) throw new Error("Seu perfil não possui permissão para consultar a governança de modelos.");
          throw new Error(`Falha ao carregar ${section.label.toLowerCase()} (HTTP ${response.status}).`);
        }
        const payload = await response.json() as Record<string, unknown>;
        if (section.id === "authorizations") {
          const policies = Array.isArray(payload.shared_data_policies) ? payload.shared_data_policies as Row[] : [];
          const local = Array.isArray(payload.institutional_training) ? payload.institutional_training as Row[] : [];
          return [section.id, [...policies.map((r) => ({ ...r, authorization_type: "Uso de dados compartilhados" })), ...local.map((r) => ({ ...r, authorization_type: "Treinamento institucional" }))]] as const;
        }
        const rows = section.key ? payload[section.key] : [];
        return [section.id, Array.isArray(rows) ? rows as Row[] : []] as const;
      }));
      setData((current) => ({ ...current, ...Object.fromEntries(results) }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível carregar os dados administrativos.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const selected = sections.find((section) => section.id === active)!;
  const rows = data[active];

  return (
    <main className="min-h-screen bg-[#f7f7f5] px-4 py-6 text-[#202126] md:px-8 md:py-10">
      <div className="mx-auto max-w-7xl space-y-7">
        <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-800">
              <ShieldCheck size={14} /> Área interna · acesso administrativo
            </div>
            <h1 className="text-3xl font-semibold tracking-tight">MIRA Admin</h1>
            <p className="mt-2 max-w-3xl text-sm text-neutral-600">
              Governança de dados e modelos: modalidades de uso, autorizações vigentes, inventário de dados,
              execuções de treinamento, versões e trilhas de auditoria.
            </p>
          </div>
          <button onClick={() => void load()} disabled={loading} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-neutral-300 bg-white px-4 text-sm font-medium hover:bg-neutral-50 disabled:opacity-60">
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Atualizar
          </button>
        </header>

        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {sections.map((section) => {
            const Icon = section.icon;
            return (
              <button key={section.id} onClick={() => setActive(section.id)} className={`rounded-xl border p-4 text-left transition ${active === section.id ? "border-indigo-300 bg-white shadow-sm ring-1 ring-indigo-100" : "border-neutral-200 bg-white/70 hover:bg-white"}`}>
                <div className="flex items-center justify-between gap-3">
                  <Icon size={18} className={active === section.id ? "text-indigo-700" : "text-neutral-500"} />
                  <span className="text-xs text-neutral-500">{data[section.id].length} itens</span>
                </div>
                <div className="mt-4 text-sm font-semibold">{section.label}</div>
              </button>
            );
          })}
        </section>

        {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>}

        <section className="overflow-hidden rounded-xl border border-neutral-200 bg-white">
          <div className="flex flex-col gap-1 border-b border-neutral-200 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="font-semibold">{selected.label}</h2>
              <p className="mt-1 text-xs text-neutral-500">Consulta somente leitura. Ações de aprovação e ativação continuam nos fluxos administrativos específicos.</p>
            </div>
            <span className="text-xs text-neutral-500">{rows.length} registros</span>
          </div>
          {loading && rows.length === 0 ? (
            <div className="p-8 text-sm text-neutral-500">Carregando dados autorizados…</div>
          ) : rows.length === 0 ? (
            <div className="p-8 text-sm text-neutral-500">Nenhum registro disponível nesta seção.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] border-collapse text-left text-sm">
                <thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500">
                  <tr>{Object.keys(rows[0]).map((key) => <th key={key} className="whitespace-nowrap border-b border-neutral-200 px-4 py-3 font-semibold">{prettyKey(key)}</th>)}</tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={label(row.id ?? row.run_id ?? row.tenant_id ?? index)} className="align-top hover:bg-neutral-50/80">
                      {Object.keys(rows[0]).map((key) => (
                        <td key={key} className="max-w-[360px] border-b border-neutral-100 px-4 py-3 text-neutral-700">
                          <span className="break-words">{label(row[key])}</span>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <p className="text-xs leading-5 text-neutral-500">
          As contagens de eventos são inventário operacional, não autorização de uso. Elegibilidade para treinamento
          compartilhado deve ser confirmada pela política aprovada e vigente; dados pessoais e segredos não são exibidos nesta área.
        </p>
      </div>
    </main>
  );
}
