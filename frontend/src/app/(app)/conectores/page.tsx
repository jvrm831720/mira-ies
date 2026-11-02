"use client";

import { useEffect, useMemo, useState } from "react";
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
import type { UploadHistoryItem } from "@/types/api";

export default function DadosIntegracoesPage() {
  const [tab, setTab] = useState("overview");
  const [selected, setSelected] = useState<string>("generic");
  const [payload, setPayload] = useState('{\n  "students": []\n}');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [jacadBaseUrl, setJacadBaseUrl] = useState("");
  const [jacadToken, setJacadToken] = useState("");
  const [jacadOrgId, setJacadOrgId] = useState("");
  const [jacadBusy, setJacadBusy] = useState(false);
  const [jacadAction, setJacadAction] = useState<"test" | "sync" | null>(null);

  const catalog = useQuery({
    queryKey: ["connectors"],
    queryFn: () => api.listConnectors(),
    retry: false,
  });

  const jacadConnection = useQuery({
    queryKey: ["jacad-connection"],
    queryFn: () => api.jacadConnection(),
    retry: false,
  });

  useEffect(() => {
    if (!jacadConnection.data?.configured) return;
    setJacadBaseUrl(jacadConnection.data.base_url || "");
    setJacadOrgId(jacadConnection.data.default_org_id ? String(jacadConnection.data.default_org_id) : "");
  }, [jacadConnection.data?.configured, jacadConnection.data?.base_url, jacadConnection.data?.default_org_id]);

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

  // UploadHistoryResponse exposes `items` only (no `batches` in types/api.ts)
  const historyItems = useMemo<UploadHistoryItem[]>(
    () => history.data?.items ?? [],
    [history.data?.items]
  );

  // StudentsResponse has `students` array; no guaranteed total field
  const studentSampleCount = students.data?.students?.length;

  const overviewCards = useMemo(
    () => [
      {
        label: "Fontes no catálogo",
        value: catalog.isLoading ? "—" : String(items.length || 0),
        hint: catalog.isError ? "Catálogo indisponível" : "Conectores listados pela API",
      },
      {
        label: "Amostra de alunos",
        value: students.isLoading
          ? "—"
          : studentSampleCount != null
            ? String(studentSampleCount)
            : "—",
        hint: students.isError
          ? "Não foi possível consultar alunos"
          : "Tamanho da amostra retornada (limit=1); total agregado não está no contrato",
      },
      {
        label: "Importações recentes",
        value: history.isLoading ? "—" : String(historyItems.length),
        hint: history.isError ? "Histórico indisponível" : "Últimos lotes de upload",
      },
    ],
    [
      catalog.isError,
      catalog.isLoading,
      history.isError,
      history.isLoading,
      historyItems.length,
      items.length,
      studentSampleCount,
      students.isError,
      students.isLoading,
    ]
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
            { id: "jacad", label: "JACAD" },
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
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setSelected(c.id);
                      setTab("ingest");
                    }}
                  >
                    Usar
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabPanel>


        <TabPanel when="jacad" active={tab} className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Conexão nativa · JACAD</CardTitle>
              <CardDescription>Conecte a MIRA diretamente ao ambiente JACAD da instituição. A conexão é somente leitura.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1.5 text-sm">
                  <span className="font-medium">URL do ambiente JACAD</span>
                  <input value={jacadBaseUrl} onChange={(e) => setJacadBaseUrl(e.target.value)}
                    placeholder="https://sua-instituicao.jacad.com.br" autoComplete="url"
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/25" />
                </label>
                <label className="space-y-1.5 text-sm">
                  <span className="font-medium">ID da organização (obrigatório para sincronização completa)</span>
                  <input value={jacadOrgId} onChange={(e) => setJacadOrgId(e.target.value.replace(/[^0-9]/g, ""))}
                    placeholder="Ex.: 1" inputMode="numeric"
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/25" />
                </label>
              </div>
              <label className="block space-y-1.5 text-sm">
                <span className="font-medium">Token de acesso da API JACAD</span>
                <input type="password" value={jacadToken} onChange={(e) => setJacadToken(e.target.value)}
                  placeholder={jacadConnection.data?.credential_configured ? "Token salvo. Informe outro apenas para substituir." : "Cole o token gerado no JACAD"}
                  autoComplete="new-password" maxLength={40}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/25" />
                <span className="block text-xs text-muted-foreground">O token é cifrado no banco. A MIRA não o exibe novamente nem o registra em logs.</span>
              </label>
              <div className="flex flex-wrap gap-2">
                <Button type="button" disabled={jacadBusy || !jacadBaseUrl.trim() || !jacadToken.trim()}
                  onClick={async () => {
                    setJacadBusy(true);
                    try {
                      await api.configureJacad({ base_url: jacadBaseUrl.trim(), api_token: jacadToken.trim(),
                        default_org_id: jacadOrgId ? Number(jacadOrgId) : null });
                      setJacadToken("");
                      await jacadConnection.refetch();
                      toast.success("Configuração JACAD salva com segurança");
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Não foi possível salvar a conexão");
                    } finally { setJacadBusy(false); }
                  }}>
                  {jacadBusy && !jacadAction ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Plug className="h-4 w-4" />}
                  Salvar conexão
                </Button>
                <Button type="button" variant="outline" disabled={jacadBusy || !jacadConnection.data?.configured}
                  onClick={async () => {
                    setJacadBusy(true); setJacadAction("test");
                    try {
                      const response = await api.testJacad();
                      await jacadConnection.refetch();
                      toast.success("Conexão validada · " + response.sample_records + " registro(s) na amostra");
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Falha no teste JACAD");
                      await jacadConnection.refetch();
                    } finally { setJacadBusy(false); setJacadAction(null); }
                  }}>
                  {jacadAction === "test" ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <AlertCircle className="h-4 w-4" />}
                  Testar conexão
                </Button>
                <Button type="button" variant="secondary"
                  disabled={jacadBusy || !jacadConnection.data?.configured || !jacadConnection.data?.default_org_id || jacadConnection.data?.status !== "connected"}
                  onClick={async () => {
                    setJacadBusy(true); setJacadAction("sync");
                    try {
                      const response = await api.syncJacad();
                      await jacadConnection.refetch();
                      toast.success("Sync concluído · " + response.students_imported + " alunos · " + response.enrollments_received + " matrículas · " + response.students_with_financial_status + " com status financeiro");
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Falha na sincronização JACAD");
                      await jacadConnection.refetch();
                    } finally { setJacadBusy(false); setJacadAction(null); }
                  }}>
                  {jacadAction === "sync" ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
                  Sincronizar dados acadêmicos e financeiros
                </Button>
              </div>
              <div className="rounded-xl border border-border bg-muted/20 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">Estado da integração</span>
                  <span className="text-xs text-muted-foreground">
                    {jacadConnection.isLoading ? "Consultando…" : jacadConnection.data?.status || (jacadConnection.data?.configured ? "configured" : "não configurada")}
                  </span>
                </div>
                {jacadConnection.data?.last_tested_at && <p className="mt-1 text-xs text-muted-foreground">Último teste: {new Date(jacadConnection.data.last_tested_at).toLocaleString("pt-BR")}</p>}
                {jacadConnection.data?.last_sync_at && <p className="mt-1 text-xs text-muted-foreground">Última sincronização: {new Date(jacadConnection.data.last_sync_at).toLocaleString("pt-BR")} · {jacadConnection.data.last_sync_records || 0} registros</p>}
                {jacadConnection.data?.last_error && <p className="mt-2 text-xs text-destructive">{jacadConnection.data.last_error}</p>}
              </div>
              <p className="text-xs text-muted-foreground">
                A sincronização importa alunos, matrículas e resumo financeiro por matrícula. O status financeiro e os dias de atraso derivados da parcela vencida são armazenados com rastreabilidade. Recorrência de atrasos, saldo total, notas, frequência e acesso não são inferidos. O score automático permanece desativado até a cobertura preditiva estar completa.
              </p>
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
              {!history.isLoading && !history.isError && historyItems.length === 0 && (
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
              {historyItems.length > 0 && (
                <ul className="divide-y divide-border">
                  {historyItems.slice(0, 10).map((item) => {
                    const when = item.uploaded_at || item.processed_at;
                    return (
                      <li key={item.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                        <span className="min-w-0 truncate font-medium">{item.filename || "Lote"}</span>
                        <span className="shrink-0 text-xs text-muted-foreground">
                          {when ? new Date(when).toLocaleString("pt-BR") : "—"}
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
