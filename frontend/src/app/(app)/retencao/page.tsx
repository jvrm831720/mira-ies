"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Activity,
  Check,
  CircleAlert,
  Layers,
  Mail,
  MessageCircle,
  Play,
  ShieldCheck,
  Smartphone,
} from "lucide-react";
import Link from "next/link";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { loadGroupMemberIds } from "@/lib/retention-audience";
import type { RiskLevel, RetentionRunResult } from "@/types/api";

const levelOptions: { value: RiskLevel; title: string; detail: string; color: string }[] = [
  { value: "critico", title: "Crítico", detail: "Prioridade imediata", color: "var(--brand-coral)" },
  { value: "medio", title: "Médio", detail: "Acompanhamento próximo", color: "var(--brand-indigo)" },
  { value: "baixo", title: "Baixo", detail: "Baixa prioridade na régua", color: "var(--brand-blue)" },
];
const channelItems = [
  { key: "whatsapp", label: "WhatsApp", icon: MessageCircle },
  { key: "email", label: "E-mail", icon: Mail },
  { key: "sms", label: "SMS", icon: Smartphone },
] as const;

function RetencaoContent() {
  const searchParams = useSearchParams();
  const groupFromUrl = searchParams.get("group")?.trim() || "";
  const dryRunFromUrl = searchParams.get("dry_run") === "1" || searchParams.get("dry_run") === "true";
  const campaignFromUrl = searchParams.get("campaign")?.trim() || "";

  const queryClient = useQueryClient();
  const [limit, setLimit] = useState(50);
  const [levels, setLevels] = useState<RiskLevel[]>(["critico"]);
  const [campaign, setCampaign] = useState(campaignFromUrl);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RetentionRunResult | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [dryRun, setDryRun] = useState(true);
  const [groupAudienceApplied, setGroupAudienceApplied] = useState(false);

  const status = useQuery({ queryKey: ["agents-status"], queryFn: () => api.agentsStatus() });
  const critical = useQuery({
    queryKey: ["risk-critical-retention"],
    queryFn: () => api.riskCritical(30),
  });
  const groupDetail = useQuery({
    queryKey: ["student-groups", "detail", groupFromUrl],
    queryFn: () => api.studentGroupDetail(groupFromUrl),
    enabled: Boolean(groupFromUrl),
    retry: false,
  });
  const groupMembers = useQuery({
    queryKey: ["retention-audience", "group", groupFromUrl],
    queryFn: () => loadGroupMemberIds(groupFromUrl),
    enabled: Boolean(groupFromUrl),
    retry: false,
  });

  useEffect(() => {
    if (dryRunFromUrl || groupFromUrl) setDryRun(true);
  }, [dryRunFromUrl, groupFromUrl]);

  useEffect(() => {
    if (!groupFromUrl || !groupMembers.data || groupAudienceApplied) return;
    const ids = groupMembers.data.ids;
    setSelectedIds(ids);
    setLimit(Math.min(500, Math.max(1, ids.length || 50)));
    if (!campaign.trim() && groupDetail.data?.name) {
      setCampaign(`Grupo · ${groupDetail.data.name}`);
    } else if (!campaign.trim() && campaignFromUrl) {
      setCampaign(campaignFromUrl);
    }
    setGroupAudienceApplied(true);
    if (groupMembers.data.truncated) {
      toast.message("Público do grupo carregado parcialmente (limite de páginas)."
      );
    }
  }, [
    groupFromUrl,
    groupMembers.data,
    groupDetail.data,
    groupAudienceApplied,
    campaign,
    campaignFromUrl,
  ]);

  const students = critical.data?.students ?? [];

  function toggleLevel(level: RiskLevel) {
    setLevels((previous) =>
      previous.includes(level) ? previous.filter((item) => item !== level) : [...previous, level]
    );
  }

  function toggleStudent(id: string) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function run() {
    if (!selectedIds.length && levels.length === 0) {
      toast.error("Selecione níveis de risco ou alunos do público.");
      return;
    }
    if (groupFromUrl && !dryRun) {
      const okConfirm = window.confirm(
        "Este público veio de um grupo. A primeira execução recomendada é dry-run. Deseja enviar de verdade mesmo assim?"
      );
      if (!okConfirm) return;
    } else {
      const ok = window.confirm(
        dryRun
          ? "Simular a régua (dry-run) para o público selecionado? Nenhuma mensagem real será enviada."
          : "A régua será executada para os alunos elegíveis, respeitando anti-spam e opt-out. Continuar?"
      );
      if (!ok) return;
    }

    setLoading(true);
    try {
      const campaignId =
        campaign.trim() ||
        `campanha-${new Date().toISOString().slice(0, 10)}-${Math.random().toString(36).slice(2, 7)}`;
      const response = await api.retentionRun(
        {
          risk_levels: selectedIds.length ? undefined : levels,
          limit,
          campaign_id: campaignId,
          campaign_name: campaign.trim() || undefined,
          dry_run: dryRun,
          student_ids: selectedIds.length ? selectedIds : undefined,
        },
        crypto.randomUUID()
      );
      setResult(response);
      toast.success(
        response.message || (dryRun ? "Simulação concluída." : "Régua concluída.")
      );
      void queryClient.invalidateQueries({ queryKey: ["retention-logs"] });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível executar a régua.");
    } finally {
      setLoading(false);
    }
  }

  const totals = result?.totals;
  const resultItems = [
    { label: "Contatados", value: (totals?.sent ?? 0) + (totals?.dry_run ?? 0), color: "#348b65" },
    { label: "Ignorados", value: totals?.skipped ?? 0, color: "#73758a" },
    { label: "Falhas", value: (totals?.failed ?? 0) + (totals?.unknown ?? 0), color: "var(--brand-coral)" },
  ];
  const resultTotal = resultItems.reduce((sum, item) => sum + item.value, 0);

  const humanSummary = useMemo(() => {
    if (!result) return null;
    const contacted = (totals?.sent ?? 0) + (totals?.dry_run ?? 0);
    const skipped = totals?.skipped ?? 0;
    const failed = (totals?.failed ?? 0) + (totals?.unknown ?? 0);
    const evaluated = result.students_evaluated ?? resultTotal;
    return `A equipe processou ${evaluated} alunos nesta campanha. ${contacted} receberam contato, ${skipped} foram ignorados pelas regras e ${failed} tiveram falha de entrega.`;
  }, [result, totals, resultTotal]);

  return (
    <>
      <Header
        title="Retenção ativa"
        subtitle="Defina o público, nomeie a campanha e execute a régua de contato."
      />
      <main className="mx-auto w-full max-w-6xl space-y-6 px-4 pb-10 pt-5 md:px-9 md:pt-7">
        {groupFromUrl ? (
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-[#BFDBFE] bg-[#EFF6FF] px-4 py-3 text-[13px] text-[#1D4ED8]">
            <Layers className="h-4 w-4 shrink-0" />
            <span className="font-semibold">
              Público originado do grupo{" "}
              {groupDetail.data?.name || groupFromUrl}
            </span>
            {groupMembers.isLoading ? (
              <span className="text-[#667085]">Carregando integrantes…</span>
            ) : null}
            {groupMembers.isError ? (
              <span className="text-[#B42318]">Falha ao carregar membros do grupo.</span>
            ) : null}
            {groupMembers.data ? (
              <span className="text-[#344054]">
                {groupMembers.data.ids.length.toLocaleString("pt-BR")} alunos pré-selecionados
                {groupMembers.data.truncated ? " (carga parcial)" : ""}
              </span>
            ) : null}
            <Link
              href={"/alunos/grupos/" + encodeURIComponent(groupFromUrl)}
              className="ml-auto font-semibold underline underline-offset-2"
            >
              Voltar ao grupo
            </Link>
          </div>
        ) : null}

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
          <Card>
            <CardHeader>
              <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
                <span className="grid h-6 w-6 place-items-center rounded-lg bg-secondary">01</span>{" "}
                Público da régua
              </div>
              <CardTitle className="text-lg">Quem deve receber atenção?</CardTitle>
              <CardDescription>
                {groupFromUrl
                  ? "Integrantes do grupo (resultado TRUE) foram pré-selecionados. Você pode ajustar antes de executar."
                  : "Escolha níveis de risco, limite e, se quiser, alunos específicos da lista prioritária."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <label className="text-xs font-semibold" htmlFor="campaign">
                  Nome da campanha
                </label>
                <Input
                  id="campaign"
                  placeholder="Ex.: Semana 42 — críticos finanças"
                  value={campaign}
                  onChange={(e) => setCampaign(e.target.value)}
                />
              </div>

              <fieldset>
                <legend className="mb-3 text-xs font-semibold">Níveis de risco</legend>
                <div className="grid gap-2 sm:grid-cols-3">
                  {levelOptions.map((option) => {
                    const selected = levels.includes(option.value);
                    return (
                      <button
                        key={option.value}
                        type="button"
                        aria-pressed={selected}
                        disabled={selectedIds.length > 0}
                        onClick={() => toggleLevel(option.value)}
                        className={`relative flex min-h-[82px] items-start gap-3 rounded-xl border p-3.5 text-left transition ${
                          selected
                            ? "border-primary/35 bg-secondary/70 shadow-[0_0_0_2px_rgba(64,80,205,0.08)]"
                            : "border-border bg-white hover:bg-muted/40"
                        } ${selectedIds.length > 0 ? "opacity-50" : ""}`}
                      >
                        <span
                          className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border"
                          style={
                            selected
                              ? { borderColor: option.color, backgroundColor: option.color, color: "white" }
                              : undefined
                          }
                        >
                          {selected && <Check className="h-3 w-3" />}
                        </span>
                        <span>
                          <span className="block text-xs font-semibold">{option.title}</span>
                          <span className="mt-1 block text-[10px] leading-relaxed text-muted-foreground">
                            {selectedIds.length > 0
                              ? "Ignorado enquanto houver alunos selecionados"
                              : option.detail}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </fieldset>

              <div className="grid gap-5 border-t border-border pt-5 sm:grid-cols-2 sm:items-end">
                <label className="block space-y-2">
                  <span className="text-xs font-semibold">Limite de alunos</span>
                  <input
                    type="number"
                    min={1}
                    max={500}
                    value={limit}
                    onChange={(event) =>
                      setLimit(Math.min(500, Math.max(1, Number(event.target.value) || 1)))
                    }
                    className="h-11 w-full rounded-xl border border-input bg-white px-3.5 text-sm tabular-nums outline-none focus:ring-2 focus:ring-primary/25"
                  />
                </label>
                <label className="flex cursor-pointer items-start gap-2 rounded-xl bg-muted/35 p-3 text-[11px] leading-relaxed text-muted-foreground">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={dryRun}
                    onChange={(e) => setDryRun(e.target.checked)}
                  />
                  <span>
                    <span className="font-semibold text-foreground">Dry-run (simulação)</span>
                    <br />
                    Recomendado quando o público veio de um grupo. Nenhuma mensagem real é enviada.
                  </span>
                </label>
              </div>

              <p className="flex items-start gap-2 rounded-xl bg-muted/35 p-3 text-[11px] leading-relaxed text-muted-foreground">
                <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                Anti-spam e opt-out permanecem ativos em toda execução.
              </p>

              {selectedIds.length > 0 && (
                <div className="border-t border-border pt-5">
                  <p className="mb-2 text-xs font-semibold">
                    Alunos no público ({selectedIds.length.toLocaleString("pt-BR")})
                  </p>
                  <p className="mb-3 text-[11px] text-muted-foreground">
                    Origem: {groupFromUrl ? "grupo virtual" : "seleção manual"}. Desmarque para
                    remover do público desta execução.
                  </p>
                  <ul className="max-h-48 space-y-1 overflow-y-auto rounded-xl border border-border p-2">
                    {selectedIds.slice(0, 80).map((id) => {
                      const fromCritical = students.find((s) => s.id === id);
                      return (
                        <li key={id}>
                          <label className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-muted/40">
                            <input
                              type="checkbox"
                              checked
                              onChange={() => toggleStudent(id)}
                            />
                            <span className="font-medium">
                              {fromCritical?.nome || id.slice(0, 8) + "…"}
                            </span>
                            {fromCritical?.matricula ? (
                              <span className="text-muted-foreground">{fromCritical.matricula}</span>
                            ) : null}
                          </label>
                        </li>
                      );
                    })}
                    {selectedIds.length > 80 ? (
                      <li className="px-2 py-1 text-[11px] text-muted-foreground">
                        + {(selectedIds.length - 80).toLocaleString("pt-BR")} não listados na prévia
                      </li>
                    ) : null}
                  </ul>
                </div>
              )}

              {!groupFromUrl && students.length > 0 && (
                <div className="border-t border-border pt-5">
                  <p className="mb-2 text-xs font-semibold">
                    Selecionar alunos prioritários (opcional)
                  </p>
                  <p className="mb-3 text-[11px] text-muted-foreground">
                    Se nenhum for marcado, a régua usa os níveis e o limite acima.
                  </p>
                  <ul className="max-h-48 space-y-1 overflow-y-auto rounded-xl border border-border p-2">
                    {students.map((s) => (
                      <li key={s.id}>
                        <label className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-muted/40">
                          <input
                            type="checkbox"
                            checked={selectedIds.includes(s.id)}
                            onChange={() => toggleStudent(s.id)}
                          />
                          <span className="font-medium">{s.nome}</span>
                          <span className="text-muted-foreground">{s.matricula}</span>
                          <span className="ml-auto text-[10px] uppercase text-muted-foreground">
                            {s.risk_level}
                          </span>
                        </label>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>

          <aside className="space-y-4">
            <Card className="bg-[var(--brand-midnight)] text-white shadow-none">
              <CardHeader className="pb-3">
                <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-white/60">
                  <span className="grid h-6 w-6 place-items-center rounded-lg bg-white/10 text-[var(--brand-coral)]">
                    02
                  </span>
                  Canais
                </div>
                <CardTitle className="text-base text-white">
                  {dryRun ? "Simular régua" : "Executar régua"}
                </CardTitle>
                <CardDescription className="text-white/60">
                  WhatsApp, e-mail e SMS conforme a configuração da instituição.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2 rounded-xl border border-white/10 px-3.5 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/45">
                    Canais configurados
                  </p>
                  {channelItems.map(({ key, label, icon: Icon }) => (
                    <div key={key} className="flex items-center justify-between text-xs">
                      <span className="flex items-center gap-2 text-white/75">
                        <Icon className="h-3.5 w-3.5 text-[var(--brand-coral)]" />
                        {label}
                      </span>
                      <span className="rounded-md bg-white/10 px-2 py-1 text-[10px] font-medium text-white/75">
                        {status.data?.providers[key] ?? (status.isLoading ? "…" : "—")}
                      </span>
                    </div>
                  ))}
                </div>
                <Button
                  onClick={run}
                  disabled={loading || (!selectedIds.length && levels.length === 0)}
                  className="w-full bg-[var(--brand-coral)] text-[var(--brand-midnight)] hover:bg-[#ff8a7c]"
                >
                  {loading ? <Activity className="h-4 w-4 animate-pulse" /> : <Play className="h-4 w-4" />}
                  {loading
                    ? "Executando…"
                    : dryRun
                      ? "Simular agora (dry-run)"
                      : "Executar régua agora"}
                </Button>
              </CardContent>
            </Card>
            <div className="flex items-start gap-2.5 rounded-xl border border-[#f4d4ce] bg-[#fff4f1] p-3.5 text-xs leading-relaxed text-[#963b32]">
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                Confira o público antes de executar. A régua respeita opt-out e intervalos de
                contato.
              </span>
            </div>
          </aside>
        </div>

        {result && (
          <Card className="overflow-hidden">
            <div className="h-1 bg-primary" />
            <CardHeader className="flex-row items-start justify-between gap-4">
              <div>
                <CardTitle>Resultado da campanha</CardTitle>
                <CardDescription className="mt-1">
                  {result.campaign_id ? `Campanha · ${result.campaign_id}` : "Execução finalizada"}
                </CardDescription>
              </div>
              <span className="rounded-full bg-secondary px-3 py-1 text-[10px] font-semibold text-primary">
                {resultTotal.toLocaleString("pt-BR")} registros
              </span>
            </CardHeader>
            <CardContent className="space-y-5">
              {humanSummary && (
                <p className="rounded-xl bg-muted/40 p-4 text-sm leading-relaxed">{humanSummary}</p>
              )}
              <div className="grid grid-cols-2 gap-3 xl:grid-cols-3">
                {resultItems.map((item) => (
                  <div key={item.label} className="rounded-xl border border-border/80 p-4">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
                      {item.label}
                    </p>
                    <p className="mt-2 text-2xl font-semibold tabular-nums" style={{ color: item.color }}>
                      {item.value.toLocaleString("pt-BR")}
                    </p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </>
  );
}

export default function RetencaoPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-10">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-64 w-full rounded-xl" />
        </main>
      }
    >
      <RetencaoContent />
    </Suspense>
  );
}
