"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertCircle,
  FileSpreadsheet,
  History,
  LoaderCircle,
  Plug,
  UploadCloud,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Tabs, TabPanel } from "@/components/ui/tabs";
import { api } from "@/lib/api";

export default function DadosIntegracoesPage() {
  const [tab, setTab] = useState("overview");
  const [selected, setSelected] = useState<string>("generic");
  const [payload, setPayload] = useState('{\n  "students": []\n}');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const catalog = useQuery({
    queryKey: ["connectors"],
    queryFn: () => api.listConnectors(),
    retry: false,
  });

  const history = useQuery({
    queryKey: ["upload-history"],
    queryFn: () => api.uploadHistory(10, 0),
    retry: false,
  });

  const students = useQuery({
    queryKey: ["students-home"],
    queryFn: () => api.students({ limit: 1 }),
    retry: false,
  });

  const items = catalog.data?.connectors ?? [];
  const historyItems = history.data?.items ?? history.data?.batches ?? [];
  const studentTotal =
    typeof students.data?.total === "number"
      ? students.data.total
      : students.data?.students?.length;

  const overviewCards = useMemo(
    () => [
      {
        label: "Fontes no catálogo",
        value: catalog.isLoading ? "—" : String(items.length || 0),
        hint: catalog.isError ? "Catálogo indisponível" : "Conectores listados pela API",
      },
      {
        label: "Alunos na base",
        value: students.isLoading ? "—" : studentTotal != null ? String(studentTotal) : "—",
        hint: students.isError ? "Não foi possível consultar alunos" : "Total retornado pela API",
      },
      {
        label: "Importações recentes",
        value: history.isLoading ? "—" : String(Array.isArray(historyItems) ? historyItems.length : 0),
        hint: history.isError ? "Histórico indisponível" : "Últimos lotes de upload",
      },
    ],
    [catalog.isError, catalog.isLoading, history.isError, history.isLoading, historyItems, items.length, studentTotal, students.isError, students.isLoading]
  );

  async function onIngest() {
    setLoading(true);
    setResult(null);
    try {
      const json = JSON.parse(payload);
      const res = await api.ingestConnector(selected, json, true);
      setResult(JSON.stringify(res, null, 2));
      toast.success("Dados recebidos pelo conector");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Falha na ingestão");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Header
        title="Dados e integrações"
        subtitle="Fontes da instituição, conectores ERP/LMS e histórico de importações."
      />
      <main className="mira-page mx-auto w-full max-w-5xl space-y-6 px-4 pb-10 pt-5 md:px-9 md:pt-7">
        <Tabs
          value={tab}
          onValueChange={setTab}
          items={[
            { id: "overview", label: "Visão geral" },
            { id: "sources", label: "Fontes de dados" },
            { id: "history", label: "Histórico" },
            { id: "ingest", label: "Ingestão JSON" },
          ]}
        />

        <TabPanel when="overview" active={tab} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            {overviewCards.map((card) => (
              <Card key={card.label}>
                <CardHeader className="pb-2">
                  <CardDescription>{card.label}</CardDescription>
                  <CardTitle className="text-2xl tabular-nums">{card.value}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground">{card.hint}</p>
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Ações disponíveis</CardTitle>
              <CardDescription>Somente fluxos com implementação real no backend.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <Link href="/importar">
                <Button type="button" size="sm">
                  <UploadCloud className="h-4 w-4" /> Importar planilhas
                </Button>
              </Link>
              <Link href="/importacoes">
                <Button type="button" size="sm" variant="outline">
                  <History className="h-4 w-4" /> Histórico de importações
                </Button>
              </Link>
              <Button type="button" size="sm" variant="secondary" onClick={() => setTab("ingest")}>
                <Plug className="h-4 w-4" /> Enviar payload JSON
              </Button>
            </CardContent>
          </Card>
          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            Status de “conexão ativa”, frequência de sync e alertas de integração só aparecem quando a
            API expuser esses campos. Não há simulação de conectores online.
          </p>
        </TabPanel>

        <TabPanel when="sources" active={tab} className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Arquivos</CardTitle>
              <CardDescription>Importação guiada de CSV/Excel com preview e confirmação.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm">
                <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
                <span>Planilhas institucionais</span>
              </div>
              <Link href="/importar">
                <Button type="button" size="sm" variant="outline">
                  Abrir importação
                </Button>
              </Link>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Conectores API</CardTitle>
              <CardDescription>Catálogo retornado por GET /api/v1/connectors.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {catalog.isLoading && (
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> Carregando catálogo…
                </p>
              )}
              {!catalog.isLoading && items.length === 0 && (
                <EmptyState
                  icon={<Plug className="h-5 w-5" />}
                  title="Nenhum conector no catálogo"
                  description="Você ainda pode usar o conector genérico na aba Ingestão JSON."
                />
              )}
              {items.map((c) => (
                <div
                  key={c.id}
                  className="flex items-start gap-2 rounded-xl border border-border px-3 py-2.5 text-sm"
                >
                  <Plug className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">{c.name}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {c.category || "—"} · {c.description || c.id}
                    </p>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Status de sincronização: não informado pela API
                    </p>
                  </div>
                  <Button type="button" size="sm" variant="ghost" onClick={() => { setSelected(c.id); setTab("ingest"); }}>
                    Usar
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabPanel>

        <TabPanel when="history" active={tab}>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-base">Histórico de processamentos</CardTitle>
                <CardDescription>Importações recentes via upload/history.</CardDescription>
              </div>
              <Link href="/importacoes">
                <Button type="button" size="sm" variant="outline">
                  Ver tudo
                </Button>
              </Link>
            </CardHeader>
            <CardContent>
              {history.isLoading && (
                <p className="text-xs text-muted-foreground">Carregando histórico…</p>
              )}
              {history.isError && (
                <EmptyState
                  title="Histórico indisponível"
                  description="A API não retornou o histórico de importações neste momento."
                />
              )}
              {!history.isLoading && !history.isError && (!Array.isArray(historyItems) || historyItems.length === 0) && (
                <EmptyState
                  icon={<History className="h-5 w-5" />}
                  title="Nenhuma importação registrada"
                  description="Quando houver lotes processados, eles aparecerão aqui."
                  action={
                    <Link href="/importar">
                      <Button type="button" size="sm">
                        Importar dados
                      </Button>
                    </Link>
                  }
                />
              )}
              {Array.isArray(historyItems) && historyItems.length > 0 && (
                <ul className="divide-y divide-border">
                  {historyItems.slice(0, 10).map((item: Record<string, unknown>, index: number) => {
                    const id = String(item.id ?? item.batch_id ?? index);
                    const label = String(item.filename ?? item.name ?? item.source ?? "Lote");
                    const when = item.created_at ?? item.imported_at;
                    return (
                      <li key={id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                        <span className="min-w-0 truncate font-medium">{label}</span>
                        <span className="shrink-0 text-xs text-muted-foreground">
                          {when ? new Date(String(when)).toLocaleString("pt-BR") : "—"}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabPanel>

        <TabPanel when="ingest" active={tab}>
          <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Conector</CardTitle>
                <CardDescription>Escolha o destino da ingestão.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {(items.length
                  ? items
                  : [{ id: "generic", name: "Genérico", category: "generic", description: "JSON canônico" }]
                ).map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setSelected(c.id)}
                    className={`flex w-full items-start gap-2 rounded-xl border px-3 py-2.5 text-left text-sm transition ${
                      selected === c.id
                        ? "border-primary/40 bg-secondary"
                        : "border-border hover:bg-muted/40"
                    }`}
                  >
                    <Plug className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    <span>
                      <span className="block font-semibold">{c.name}</span>
                      <span className="mt-0.5 block text-[11px] text-muted-foreground">
                        {c.category || "—"} · {c.description || c.id}
                      </span>
                    </span>
                  </button>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Enviar payload · {selected}</CardTitle>
                <CardDescription>
                  Cole o JSON do ERP/LMS. A pontuação ocorre após a ingestão bem-sucedida.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <textarea
                  value={payload}
                  onChange={(e) => setPayload(e.target.value)}
                  rows={14}
                  className="w-full rounded-xl border border-input bg-background p-3 font-mono text-xs outline-none focus:ring-2 focus:ring-primary/25"
                />
                <Button onClick={onIngest} disabled={loading}>
                  {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
                  {loading ? "Processando…" : "Ingerir e pontuar"}
                </Button>
                {result && (
                  <pre className="overflow-x-auto rounded-xl bg-muted/40 p-3 text-[11px]">{result}</pre>
                )}
              </CardContent>
            </Card>
          </div>
        </TabPanel>
      </main>
    </>
  );
}
