"use client";

import { useEffect, useState } from "react";

type Consent = { grant_id: string; created_at: string; creditor_name: string; record_count: number; scope: string };
type Debt = {
  id: string; workspace_id: string; creditor_name: string; label: string; amount: string;
  remaining: string; currency: string; state: string; observed_at: string;
  grant_id: string; due_at: string | null;
};
async function api<T>(path: string, method: "GET" | "POST" = "GET"): Promise<T> {
  const response = await fetch("/api/v1/global-portal/debts" + path, {
    method, credentials: "same-origin", cache: "no-store",
    headers: method === "POST" ? { "X-Mira-Global-Portal-Action": "1" } : {},
  });
  if (!response.ok) {
    throw new Error(response.status === 403 ? "É necessário comprovar a titularidade do CPF."
      : response.status === 503 ? "Agregador ainda em homologação."
      : response.status === 401 ? "Faça login para continuar." : "Não foi possível consultar suas pendências.");
  }
  return response.json() as Promise<T>;
}
export default function PendenciasPage() {
  const [consents, setConsents] = useState<Consent[]>([]);
  const [debts, setDebts] = useState<Debt[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  async function refresh() {
    const [pending, result] = await Promise.all([
      api<{items: Consent[]}>("/consents"), api<{items: Debt[]}>(""),
    ]);
    setConsents(pending.items); setDebts(result.items);
  }
  useEffect(() => { void refresh().catch(reason => setError(String(reason.message ?? reason))); }, []);
  async function accept(id: string) {
    setBusy(id); setError("");
    try { await api("/consents/" + encodeURIComponent(id) + "/accept", "POST"); await refresh(); }
    catch (reason) { setError(String(reason instanceof Error ? reason.message : reason)); }
    finally { setBusy(null); }
  }
  const money = (amount: string, currency: string) =>
    new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(Number(amount));
  return (
    <main className="min-h-dvh bg-slate-50 px-5 py-10 text-slate-900">
      <div className="mx-auto max-w-4xl">
        <a className="text-sm text-blue-700 hover:underline" href="/portal/acesso">Portal MIRA</a>
        <h1 className="mt-6 text-3xl font-semibold tracking-tight">Minhas pendências</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
          Informações financeiras autorizadas por você e compartilhadas por instituições participantes.
          Os valores são registros históricos, não substituem o saldo atualizado do credor.
        </p>
        {error && <p role="alert" className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">{error}</p>}
        {consents.length > 0 && <section className="mt-9 rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="text-lg font-semibold">Autorizações pendentes</h2>
          <p className="mt-2 text-sm text-slate-600">Ao aceitar, você autoriza a exibição das informações financeiras associadas a esta solicitação.</p>
          <div className="mt-5 space-y-3">
            {consents.map(item => <div key={item.grant_id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 p-4">
              <span className="text-sm text-slate-600"><strong>{item.creditor_name}</strong> · {item.record_count} registros · {item.scope} · {new Date(item.created_at).toLocaleDateString("pt-BR")}</span>
              <button type="button" disabled={busy === item.grant_id} onClick={() => void accept(item.grant_id)}
                className="rounded-xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-50">
                {busy === item.grant_id ? "Confirmando…" : "Autorizar exibição"}
              </button>
            </div>)}
          </div>
        </section>}
        <section className="mt-9 space-y-4">
          <h2 className="text-lg font-semibold">Registros autorizados</h2>
          {debts.length === 0 && <div className="rounded-2xl border border-slate-200 bg-white p-8 text-sm text-slate-600">
            Nenhuma pendência autorizada disponível. Isso não significa inexistência de dívidas.
          </div>}
          {debts.map(item => <article key={item.id} className="rounded-2xl border border-slate-200 bg-white p-6">
            <div className="flex flex-wrap justify-between gap-4">
              <div><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-blue-700">{item.creditor_name}</p><h3 className="font-semibold">{item.label}</h3>
                <p className="mt-2 text-xs text-slate-500">Referência da instituição: {item.workspace_id}</p>
                <p className="mt-1 text-xs text-slate-500">Observado em {new Date(item.observed_at).toLocaleDateString("pt-BR")}</p>
              </div>
              <div className="text-right"><p className="text-xs text-slate-500">Saldo observado</p>
                <p className="mt-1 text-xl font-semibold">{money(item.remaining, item.currency)}</p></div>
            </div>
            <p className="mt-4 text-xs text-slate-500">Estado registrado: {item.state}. Pagamentos e atualizações posteriores podem não estar refletidos.</p>
          </article>)}
        </section>
      </div>
    </main>
  );
}
