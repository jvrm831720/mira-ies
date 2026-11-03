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
  const [jacadJobId, setJacadJobId] = useState<string | null>(null);
  const [sponteApiKey, setSponteApiKey] = useState("");
  const [sponteClientCode, setSponteClientCode] = useState("");
  const [sponteInitialDate, setSponteInitialDate] = useState("2025-01-01");
  const [sponteBusy, setSponteBusy] = useState(false);
  const [sponteJobId, setSponteJobId] = useState<string | null>(null);

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

  const sponteConnection = useQuery({
    queryKey: ["sponte-connection"],
    queryFn: () => api.sponteConnection(),
    retry: false,
  });
  const sponteCurrentSync = useQuery({
    queryKey: ["sponte-sync-current"],
    queryFn: () => api.sponteSyncCurrent(),
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ["queued", "running", "retrying"].includes(status) ? 2000 : false;
    },
  });
  const sponteSyncJob = useQuery({
    queryKey: ["sponte-sync-job", sponteJobId],
    queryFn: () => api.sponteSyncStatus(sponteJobId!),
    enabled: Boolean(sponteJobId),
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ["queued", "running", "retrying"].includes(status) ? 2000 : false;
    },
  });
  useEffect(() => {
    if (sponteCurrentSync.data?.job_id) setSponteJobId(sponteCurrentSync.data.job_id);
  }, [sponteCurrentSync.data?.job_id]);
  const activeSponteJob = sponteSyncJob.data || sponteCurrentSync.data;
  const sponteJobRunning = ["queued", "running", "retrying"].includes(activeSponteJob?.status || "");
  const sponteStageLabels: Record<string, string> = {
    queued: "Na fila", extracting: "Extraindo dados incrementais", completed: "Concluída",
  };

  const jacadCurrentSync = useQuery({
    queryKey: ["jacad-sync-current"],
    queryFn: () => api.jacadSyncCurrent(),
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ["queued", "running", "retrying"].includes(status) ? 2000 : false;
    },
  });

  const jacadSyncJob = useQuery({
    queryKey: ["jacad-sync-job", jacadJobId],
    queryFn: () => api.jacadSyncStatus(jacadJobId!),
    enabled: Boolean(jacadJobId),
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ["queued", "running", "retrying"].includes(status) ? 2000 : false;
    },
  });

  useEffect(() => {
    if (jacadCurrentSync.data?.job_id) setJacadJobId(jacadCurrentSync.data.job_id);
  }, [jacadCurrentSync.data?.job_id]);

  const activeJacadJob = jacadSyncJob.data || jacadCurrentSync.data;
  const jacadJobRunning = ["queued", "running", "retrying"].includes(activeJacadJob?.status || "");
  const jacadStageLabels: Record<string, string> = {
    queued: "Na fila", base: "Alunos, matrículas e resumo financeiro",
    financial_details: "Parcelas e contratos", academic_disciplines: "Disciplinas, notas e frequência",
    assessment_details: "Notas por avaliação", completed: "Concluída",
  };

  useEffect(() => {
    if (!jacadConnection.data?.configured) return;
    setJacadBaseUrl(jacadConnection.data.base_url || "");
    setJacadOrgId(jacadConnection.data.default_org_id ? String(jacadConnection.data.default_org_id) : "");
  }, [jacadConnection.data?.configured, jacadConnection.data?.base_url, jacadConnection.data?.default_org_id]);

  useEffect(() => {
    if (!sponteConnection.data?.configured) return;
    setSponteClientCode(sponteConnection.data.client_code ? String(sponteConnection.data.client_code) : "");
    setSponteInitialDate(sponteConnection.data.initial_extraction_date || "2025-01-01");
  }, [sponteConnection.data?.configured, sponteConnection.data?.client_code, sponteConnection.data?.initial_extraction_date]);

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
            { id: "sponte", label: "Sponte" },
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
              <Link href="/conectores/totvs-rm">
                <Button type="button" size="sm" variant="outline">
                  <History className="h-4 w-4" /> Operações TOTVS RM
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


        <TabPanel when="sponte" active={tab} className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Conexão nativa · Sponte BI</CardTitle>
              <CardDescription>
                API oficial Sponte BI. A MIRA consulta dados em modo somente leitura, com extração incremental por endpoint.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1.5 text-sm">
                  <span className="font-medium">Código do cliente Sponte</span>
                  <input value={sponteClientCode} onChange={(e) => setSponteClientCode(e.target.value.replace(/[^0-9]/g, ""))}
                    placeholder="CodCliSponte" inputMode="numeric"
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/25" />
                </label>
                <label className="space-y-1.5 text-sm">
                  <span className="font-medium">Data inicial do histórico</span>
                  <input type="date" value={sponteInitialDate} onChange={(e) => setSponteInitialDate(e.target.value)}
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/25" />
                </label>
              </div>
              <label className="block space-y-1.5 text-sm">
                <span className="font-medium">API Key Sponte BI</span>
                <input type="password" value={sponteApiKey} onChange={(e) => setSponteApiKey(e.target.value)}
                  placeholder={sponteConnection.data?.credential_configured ? "Chave salva. Deixe vazio para manter ou informe outra para substituir." : "Cole a API Key fornecida pela Sponte"}
                  autoComplete="new-password" maxLength={512}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/25" />
                <span className="block text-xs text-muted-foreground">
                  A API Key é cifrada no banco e nunca é exibida novamente. A URL oficial é fixa; a MIRA não aceita hosts externos nesta integração.
                </span>
              </label>
              <div className="flex flex-wrap gap-2">
                <Button type="button" disabled={sponteBusy || sponteJobRunning || !sponteClientCode || !sponteInitialDate || (!sponteApiKey.trim() && !sponteConnection.data?.credential_configured) || (Boolean(sponteConnection.data?.client_code) && Number(sponteClientCode) !== sponteConnection.data?.client_code && !sponteApiKey.trim())}
                  onClick={async () => {
                    setSponteBusy(true);
                    try {
                      await api.configureSponte({
                        ...(sponteApiKey.trim() ? { api_key: sponteApiKey.trim() } : {}),
                        client_code: Number(sponteClientCode),
                        initial_extraction_date: sponteInitialDate,
                      });
                      setSponteApiKey("");
                      await sponteConnection.refetch();
                      toast.success("Configuração Sponte salva.");
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Falha ao salvar conexão Sponte.");
                    } finally { setSponteBusy(false); }
                  }}>Salvar conexão</Button>
                <Button type="button" variant="outline" disabled={sponteBusy || !sponteConnection.data?.configured}
                  onClick={async () => {
                    setSponteBusy(true);
                    try {
                      await api.testSponte();
                      await sponteConnection.refetch();
                      toast.success("API Sponte autenticada com sucesso.");
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Falha no teste da API Sponte.");
                    } finally { setSponteBusy(false); }
                  }}>Testar conexão</Button>
                <Button type="button" variant="secondary"
                  disabled={sponteBusy || sponteJobRunning || !sponteConnection.data?.configured || sponteConnection.data?.status !== "connected"}
                  onClick={async () => {
                    setSponteBusy(true);
                    try {
                      const response = await api.syncSponte();
                      setSponteJobId(response.job_id);
                      await sponteCurrentSync.refetch();
                      toast.success(response.deduplicated ? "Já existe uma sincronização Sponte em andamento." : "Extração incremental Sponte adicionada à fila.");
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Falha ao iniciar sincronização Sponte.");
                    } finally { setSponteBusy(false); }
                  }}>
                  {sponteJobRunning ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
                  {sponteJobRunning ? "Sincronização em andamento" : "Iniciar sincronização incremental"}
                </Button>
              </div>
              {activeSponteJob && (
                <div className="space-y-3 rounded-xl border border-border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium">Sincronização Sponte BI</p>
                      <p className="text-xs text-muted-foreground">
                        {sponteStageLabels[activeSponteJob.progress?.stage || ""] || activeSponteJob.progress?.endpoint || "Aguardando worker"}
                        {activeSponteJob.progress?.endpoint ? " · " + activeSponteJob.progress.endpoint : ""}
                      </p>
                    </div>
                    <span className="text-xs font-medium">{activeSponteJob.status}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-primary transition-all" style={{ width: String(Math.max(0, Math.min(100, activeSponteJob.progress?.percent || 0))) + "%" }} />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Endpoint {activeSponteJob.progress?.endpoint_index ?? 0}/{activeSponteJob.progress?.endpoint_count ?? 11}
                    {" · "}Páginas {activeSponteJob.progress?.pages_done ?? 0}/{activeSponteJob.progress?.pages_total ?? 0}
                  </p>
                  {activeSponteJob.last_error && <p className="text-xs text-destructive">{activeSponteJob.last_error}</p>}
                  {activeSponteJob.status === "failed" && (
                    <Button size="sm" variant="outline" disabled={sponteBusy} onClick={async () => {
                      try {
                        await api.retrySponteSync(activeSponteJob.job_id);
                        await sponteSyncJob.refetch();
                        toast.success("Sincronização retomada do último checkpoint.");
                      } catch (e) {
                        toast.error(e instanceof Error ? e.message : "Não foi possível retomar a sincronização.");
                      }
                    }}>Retomar do último checkpoint</Button>
                  )}
                  {activeSponteJob.status === "completed" && activeSponteJob.result && (
                    <div className="space-y-1 text-xs text-muted-foreground">
                      <p>{activeSponteJob.result.students_updated ?? 0} alunos consolidados.</p>
                      <p>{Object.entries(activeSponteJob.result.endpoints || {}).map(([name, count]) => name + ": " + count).join(" · ")}</p>
                    </div>
                  )}
                </div>
              )}
              <div className="rounded-xl border border-border p-3">
                <p className="text-sm font-medium">Dados consultados</p>
                <ul className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                  <li>• Cadastro e situação dos alunos</li>
                  <li>• Contratos, cursos, turmas e estágios</li>
                  <li>• Contas a receber, parcelas e pagamentos</li>
                  <li>• Notas, avaliações, semestre e ano</li>
                  <li>• Snapshots de frequência e faltas</li>
                  <li>• Histórico de follow-ups</li>
                </ul>
                <p className="mt-2 text-xs text-muted-foreground">
                  A primeira extração começa na data configurada. Depois, cada endpoint usa seu próprio watermark com sobreposição de um dia para evitar lacunas. A API tem defasagem D-1; a MIRA usa sobreposição de um dia para reduzir lacunas. O limite interno é 900 requisições/minuto por API Key, abaixo do teto documentado de 1.000. Os dados são deduplicados por identificadores do fornecedor.
                  O score permanece desativado até homologar escala de notas e situações didáticas. A MIRA não infere último login nem reprovações.
                </p>
              </div>
              {Object.keys(sponteConnection.data?.sync_watermarks || {}).length > 0 && (
                <div className="rounded-xl border border-border p-3">
                  <p className="text-sm font-medium">Última extração por fonte</p>
                  <div className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                    {Object.entries(sponteConnection.data?.sync_watermarks || {}).map(([name, watermark]) => (
                      <p key={name}>{name}: {watermark}</p>
                    ))}
                  </div>
                </div>
              )}
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
                  placeholder={jacadConnection.data?.credential_configured ? "Token salvo. Deixe vazio para manter o token atual ou informe outro para substituir." : "Cole o token gerado no JACAD"}
                  autoComplete="new-password" maxLength={40}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/25" />
                <span className="block text-xs text-muted-foreground">O token é cifrado no banco. A MIRA não o exibe novamente nem o registra em logs. Se a conexão já estiver configurada, você pode atualizar a URL ou o ID da organização sem reenviar o token.</span>
              </label>
              <div className="flex flex-wrap gap-2">
                <Button type="button" disabled={jacadBusy || !jacadBaseUrl.trim() || (!jacadToken.trim() && !jacadConnection.data?.credential_configured)}
                  onClick={async () => {
                    setJacadBusy(true);
                    try {
                      await api.configureJacad({ base_url: jacadBaseUrl.trim(), ...(jacadToken.trim() ? { api_token: jacadToken.trim() } : {}),
                        default_org_id: jacadOrgId ? Number(jacadOrgId) : null });
                      setJacadToken("");
                      await jacadConnection.refetch();
                      toast.success("Configuração JACAD salva com segurança");
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Não foi possível salvar a conexão");
                    } finally { setJacadBusy(false); }
                  }}>
                  {jacadBusy && !jacadAction ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Plug className="h-4 w-4" />}
                  {jacadConnection.data?.configured ? "Salvar alterações" : "Salvar conexão"}
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
                  disabled={jacadBusy || jacadJobRunning || !jacadConnection.data?.configured || !jacadConnection.data?.default_org_id || jacadConnection.data?.status !== "connected"}
                  onClick={async () => {
                    setJacadBusy(true); setJacadAction("sync");
                    try {
                      const response = await api.syncJacad();
                      setJacadJobId(response.job_id);
                      await jacadCurrentSync.refetch();
                      toast.success(response.deduplicated ? "Já existe uma sincronização em andamento." : "Sincronização completa adicionada à fila.");
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Falha ao iniciar sincronização JACAD");
                    } finally { setJacadBusy(false); setJacadAction(null); }
                  }}>
                  {jacadAction === "sync" || jacadJobRunning ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
                  {jacadJobRunning ? "Sincronização em andamento" : "Iniciar sincronização completa"}
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
              {activeJacadJob && (
                <div className="rounded-xl border border-border p-3 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium">Sincronização completa</p>
                      <p className="text-xs text-muted-foreground">{jacadStageLabels[activeJacadJob.progress?.stage || ""] || activeJacadJob.progress?.stage || "Aguardando worker"}</p>
                    </div>
                    <span className="text-xs font-medium">{activeJacadJob.status === "completed" ? "Concluída" : activeJacadJob.status === "failed" ? "Falhou" : activeJacadJob.status === "retrying" ? "Nova tentativa agendada" : activeJacadJob.status === "queued" ? "Na fila" : "Em execução"}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.max(0, Math.min(100, activeJacadJob.progress?.percent || 0))}%` }} />
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                    <div><p className="text-lg font-semibold tabular-nums">{activeJacadJob.progress?.students ?? activeJacadJob.result?.students_imported ?? "—"}</p><p className="text-muted-foreground">Alunos</p></div>
                    <div><p className="text-lg font-semibold tabular-nums">{activeJacadJob.progress?.contracts_done ?? 0}/{activeJacadJob.progress?.contracts_total ?? 0}</p><p className="text-muted-foreground">Contratos cobertos</p></div>
                    <div><p className="text-lg font-semibold tabular-nums">{activeJacadJob.progress?.discipline_pairs_done ?? 0}/{activeJacadJob.progress?.discipline_pairs_total ?? 0}</p><p className="text-muted-foreground">Disciplinas/turmas cobertas</p></div>
                    <div><p className="text-lg font-semibold tabular-nums">{activeJacadJob.progress?.assessment_groups_done ?? 0}/{activeJacadJob.progress?.assessment_groups_total ?? 0}</p><p className="text-muted-foreground">Avaliações cobertas</p></div>
                  </div>
                  {activeJacadJob.last_error && <p className="text-xs text-destructive">{activeJacadJob.last_error}</p>}
                  {activeJacadJob.status === "failed" && (
                    <Button size="sm" variant="outline" disabled={jacadBusy} onClick={async () => {
                      try {
                        await api.retryJacadSync(activeJacadJob.job_id);
                        await jacadSyncJob.refetch();
                        toast.success("Sincronização retomada do último checkpoint.");
                      } catch (e) {
                        toast.error(e instanceof Error ? e.message : "Não foi possível retomar a sincronização.");
                      }
                    }}>Retomar do último checkpoint</Button>
                  )}
                  {activeJacadJob.status === "completed" && activeJacadJob.result && (
                    <p className="text-xs text-muted-foreground">
                      {activeJacadJob.result.students_imported ?? 0} alunos · {activeJacadJob.result.contracts_consulted ?? 0} contratos cobertos · {activeJacadJob.result.discipline_pairs_consulted ?? 0} combinações turma/disciplina cobertas · {activeJacadJob.result.assessment_groups ?? 0} grupos de avaliações cobertos.
                    </p>
                  )}
                </div>
              )}
              <div className="rounded-xl border border-border p-3">
                <p className="text-sm font-medium">Dados buscados automaticamente</p>
                <ul className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                  <li>• Cadastro do aluno e identificadores JACAD</li>
                  <li>• Matrícula, situação e curso</li>
                  <li>• Período letivo, matriz, turma e campus</li>
                  <li>• Identificador e entrega do contrato</li>
                  <li>• Situação financeira por matrícula</li>
                  <li>• Histórico de parcelas, pagamentos e vencimentos por contrato</li>
                  <li>• Disciplinas, médias, notas finais e frequência reportada</li>
                  <li>• Notas individuais por avaliação, quando disponíveis</li>
                </ul>
                <p className="mt-2 text-xs text-muted-foreground">
                  A sincronização consulta a API JACAD diretamente em segundo plano. Não é necessário enviar planilha ou JSON; você pode sair desta tela e acompanhar o processamento ao voltar.
                  Parcelas e notas detalhadas são buscadas em segundo plano, em lotes com limite de concorrência e checkpoints para retomada. Para evitar chamadas repetidas, os detalhes são reutilizados por até 24 horas; alterações no resumo financeiro invalidam o cache do contrato.
                  Os valores de frequência, notas e faltas são preservados por disciplina. A MIRA ainda não os converte em score ou média institucional sem homologar escala, pesos e regras acadêmicas.
                  Os dados são preservados por contrato, disciplina e avaliação. A MIRA não inventa médias, saldo total ou recorrência e mantém o score automático desativado até validar a cobertura preditiva.
                </p>
              </div>
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
