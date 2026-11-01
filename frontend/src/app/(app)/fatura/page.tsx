"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CreditCard,
  Download,
  ExternalLink,
  Mail,
  MessageCircle,
  MessageSquare,
  Plus,
  Receipt,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { BillingSummary } from "@/types/api";

/** Pacotes exibidos na UI — preço e quantidade são revalidados no servidor. */
const PACKS = [
  { id: "starter", label: "Starter", credits: 500, price: 89 },
  { id: "growth", label: "Growth", credits: 2000, price: 279, popular: true },
  { id: "scale", label: "Scale", credits: 8000, price: 890 },
] as const;

const CHANNELS = [
  { key: "whatsapp" as const, label: "WhatsApp", icon: MessageCircle, tint: "text-[#25D366]" },
  { key: "email" as const, label: "E-mail", icon: Mail, tint: "text-sky-600" },
  { key: "sms" as const, label: "SMS", icon: MessageSquare, tint: "text-violet-600" },
];

function planStatusVariant(
  status?: BillingSummary["plan_status"]
): "success" | "pending" | "failed" {
  if (status === "active") return "success";
  if (status === "trialing") return "pending";
  if (status === "past_due") return "failed";
  return "pending";
}

function planStatusLabel(status?: BillingSummary["plan_status"]): string {
  if (status === "active") return "Ativo";
  if (status === "trialing") return "Período de avaliação";
  if (status === "past_due") return "Pagamento em atraso";
  return "Status não informado";
}

export default function FaturaPage() {
  const qc = useQueryClient();
  const [channel, setChannel] = useState<"whatsapp" | "email" | "sms">("whatsapp");
  const [packId, setPackId] = useState<(typeof PACKS)[number]["id"]>("growth");
  const [invoicesOpen, setInvoicesOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const billing = useQuery({
    queryKey: ["billing-summary"],
    queryFn: () => api.billingSummary(),
    retry: false,
  });

  const purchase = useMutation({
    mutationFn: () => {
      const pack = PACKS.find((p) => p.id === packId)!;
      return api.purchaseCredits({
        channel,
        pack_id: packId,
        credits: pack.credits,
      });
    },
    onSuccess: (data) => {
      setConfirmOpen(false);
      toast.success(
        `${data.added.toLocaleString("pt-BR")} créditos de ${channelLabel(data.channel)} adicionados ao saldo.`
      );
      void qc.invalidateQueries({ queryKey: ["billing-summary"] });
    },
    onError: (err: Error) => {
      toast.error(err.message || "Não foi possível concluir a compra.");
    },
  });

  const data = billing.data;
  const selectedPack = useMemo(() => PACKS.find((p) => p.id === packId)!, [packId]);
  const invoices = data?.invoices ?? [];

  return (
    <>
      <Header
        title="Fatura e créditos"
        subtitle="Plano da instituição, consumo e créditos por canal de mensagem."
      />
      <main className="mx-auto w-full max-w-[1100px] space-y-6 px-4 pb-12 pt-5 md:px-9">
        {billing.isLoading && (
          <div className="space-y-4" role="status" aria-label="Carregando fatura">
            <Skeleton className="h-48 w-full rounded-[24px]" />
            <div className="grid gap-3 md:grid-cols-3">
              <Skeleton className="h-36 rounded-xl" />
              <Skeleton className="h-36 rounded-xl" />
              <Skeleton className="h-36 rounded-xl" />
            </div>
            <Skeleton className="h-64 w-full rounded-xl" />
          </div>
        )}

        {billing.isError && (
          <div
            role="alert"
            className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] px-4 py-4 text-sm text-[#B42318]"
          >
            <div className="flex items-start gap-2">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-semibold">Não foi possível carregar a fatura</p>
                <p className="mt-1 text-[13px] leading-relaxed text-[#B42318]/90">
                  A consulta ao resumo financeiro falhou. Nenhum valor de demonstração é
                  exibido. Tente novamente ou contate o suporte da MIRA.
                </p>
                <button
                  type="button"
                  onClick={() => void billing.refetch()}
                  className="mt-3 text-[13px] font-semibold underline underline-offset-2"
                >
                  Tentar novamente
                </button>
              </div>
            </div>
          </div>
        )}

        {!billing.isLoading && !billing.isError && data && (
          <>
            <section className="overflow-hidden rounded-[24px] border border-white/10 bg-[#0f0e1c] text-white shadow-[0_24px_80px_rgba(0,0,0,0.18)]">
              <div className="grid gap-0 lg:grid-cols-[1.2fr_0.8fr]">
                <div className="space-y-5 p-6 md:p-8">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold text-white/80">
                      <Sparkles className="h-3.5 w-3.5 text-[var(--brand-coral)]" />
                      Plano atual
                    </div>
                    <StatusBadge
                      status={planStatusVariant(data.plan_status)}
                      label={planStatusLabel(data.plan_status)}
                      className="border-white/15 bg-white/10 text-white"
                    />
                  </div>
                  <div>
                    <h2 className="text-2xl font-semibold tracking-tight">
                      {data.plan_name || "Plano não informado"}
                    </h2>
                    <p className="mt-1 text-sm text-white/55">
                      Renovação em{" "}
                      <strong className="font-semibold text-white/85">
                        {data.renews_at
                          ? new Date(data.renews_at).toLocaleDateString("pt-BR")
                          : "—"}
                      </strong>
                      {" · "}
                      {data.billing_cycle === "yearly" ? "Ciclo anual" : "Ciclo mensal"}
                    </p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <MetricDark label="Valor do plano" value={formatBRL(data.plan_price_brl)} />
                    <MetricDark label="Gasto no período" value={formatBRL(data.period_spend_brl)} />
                    <MetricDark
                      label="Mensagens no período"
                      value={String(data.period_messages ?? 0)}
                    />
                  </div>
                </div>

                <div className="border-t border-white/10 bg-black/25 p-6 md:p-8 lg:border-l lg:border-t-0">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/40">
                    Próxima cobrança
                  </p>
                  <p className="mt-3 text-3xl font-semibold tracking-tight">
                    {formatBRL(
                      data.next_invoice_brl != null
                        ? data.next_invoice_brl
                        : data.plan_price_brl
                    )}
                  </p>
                  <p className="mt-2 text-sm text-white/50">
                    Valor do plano desta instituição. Créditos extras de canal são cobrados à
                    parte.
                  </p>
                  <div className="mt-6 flex flex-wrap gap-2">
                    <Button
                      type="button"
                      onClick={() => setInvoicesOpen(true)}
                      className="rounded-full bg-white text-[#0f0e1c] hover:bg-white/90"
                    >
                      <Receipt className="h-4 w-4" />
                      Ver faturas
                    </Button>
                    {data.payment_link ? (
                      <a
                        href={data.payment_link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex h-10 items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 text-sm font-medium text-white transition hover:bg-white/10"
                      >
                        <ExternalLink className="h-4 w-4" />
                        Pagar / atualizar
                      </a>
                    ) : (
                      <Button
                        type="button"
                        variant="outline"
                        className="rounded-full border-white/15 bg-transparent text-white hover:bg-white/10"
                        onClick={() =>
                          toast.message(
                            "Link de pagamento ainda não configurado para esta instituição."
                          )
                        }
                      >
                        <CreditCard className="h-4 w-4" />
                        Método de pagamento
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </section>

            <section className="space-y-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
                  Créditos de disparo
                </p>
                <h3 className="mt-1 text-base font-semibold">Saldo por canal</h3>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  Cada canal consome créditos próprios ao enviar mensagens. Tentativas em
                  simulação (dry-run) não devem descontar saldo real.
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                {CHANNELS.map(({ key, label, icon: Icon, tint }) => {
                  const balance = data.credits?.[key] ?? 0;
                  const used = data.used_period?.[key] ?? 0;
                  const max = Math.max(balance + used, 1);
                  const pct = Math.min(100, Math.round((balance / max) * 100));
                  return (
                    <Card
                      key={key}
                      className="overflow-hidden border-border/80 shadow-[0_10px_30px_rgba(16,13,80,0.04)]"
                    >
                      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                          <Icon className={cn("h-4 w-4", tint)} />
                          {label}
                        </CardTitle>
                        <StatusBadge
                          status={balance < 50 ? "pending" : "success"}
                          label={balance < 50 ? "Baixo" : "OK"}
                        />
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <p className="text-3xl font-semibold tracking-tight">
                          {balance.toLocaleString("pt-BR")}
                          <span className="ml-1 text-sm font-medium text-muted-foreground">
                            créditos
                          </span>
                        </p>
                        <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full bg-[var(--brand-indigo)]"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {used.toLocaleString("pt-BR")} usados neste período
                        </p>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </section>

            <section className="grid gap-4 lg:grid-cols-[1fr_0.9fr]">
              <Card className="border-border/80 shadow-[0_10px_30px_rgba(16,13,80,0.04)]">
                <CardHeader>
                  <CardTitle className="text-base">Comprar créditos</CardTitle>
                  <p className="text-sm text-muted-foreground">
                    Escolha o canal e o pacote. A quantidade e o preço são validados no
                    servidor. A compra registra créditos no saldo da instituição; não
                    processa cartão neste fluxo.
                  </p>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div className="flex flex-wrap gap-2">
                    {CHANNELS.map(({ key, label, icon: Icon }) => (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setChannel(key)}
                        className={cn(
                          "inline-flex items-center gap-2 rounded-full border px-3.5 py-2 text-sm font-medium transition",
                          channel === key
                            ? "border-[var(--brand-midnight)] bg-[var(--brand-midnight)] text-white"
                            : "border-border bg-white text-foreground hover:bg-muted"
                        )}
                      >
                        <Icon className="h-4 w-4" />
                        {label}
                      </button>
                    ))}
                  </div>

                  <div className="grid gap-3 sm:grid-cols-3">
                    {PACKS.map((pack) => (
                      <button
                        key={pack.id}
                        type="button"
                        onClick={() => setPackId(pack.id)}
                        className={cn(
                          "relative rounded-2xl border p-4 text-left transition",
                          packId === pack.id
                            ? "border-[var(--brand-indigo)] bg-secondary shadow-sm"
                            : "border-border bg-white hover:border-primary/30"
                        )}
                      >
                        {"popular" in pack && pack.popular ? (
                          <span className="absolute -top-2 right-3 rounded-full bg-[var(--brand-coral)] px-2 py-0.5 text-[10px] font-bold text-[var(--brand-midnight)]">
                            Popular
                          </span>
                        ) : null}
                        <p className="text-sm font-semibold">{pack.label}</p>
                        <p className="mt-2 text-2xl font-semibold tracking-tight">
                          {pack.credits.toLocaleString("pt-BR")}
                        </p>
                        <p className="text-xs text-muted-foreground">créditos</p>
                        <p className="mt-3 text-sm font-medium">{formatBRL(pack.price)}</p>
                      </button>
                    ))}
                  </div>

                  <Button
                    className="h-11 w-full rounded-full"
                    disabled={purchase.isPending}
                    onClick={() => setConfirmOpen(true)}
                  >
                    <Plus className="h-4 w-4" />
                    Revisar compra · {selectedPack.credits.toLocaleString("pt-BR")} créditos de{" "}
                    {CHANNELS.find((c) => c.key === channel)?.label}
                  </Button>
                </CardContent>
              </Card>

              <Card className="border-border/80 bg-[#0c0b1d] text-white shadow-[0_10px_30px_rgba(16,13,80,0.12)]">
                <CardHeader>
                  <CardTitle className="text-base text-white">Como os créditos funcionam</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4 text-sm text-white/70">
                  <p>
                    Cada mensagem enviada de verdade consome 1 crédito do canal correspondente
                    (WhatsApp, e-mail ou SMS).
                  </p>
                  <ul className="space-y-2">
                    <li className="flex gap-2">
                      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--brand-coral)]" />
                      Os três canais têm saldos independentes.
                    </li>
                    <li className="flex gap-2">
                      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--brand-coral)]" />
                      Sem saldo, o canal fica pausado até a reposição.
                    </li>
                    <li className="flex gap-2">
                      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--brand-coral)]" />
                      O valor do plano e o link de pagamento são configurados por instituição.
                    </li>
                  </ul>
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/40">
                      Resumo da compra
                    </p>
                    <p className="mt-2 text-lg font-semibold text-white">
                      {CHANNELS.find((c) => c.key === channel)?.label} ·{" "}
                      {selectedPack.credits.toLocaleString("pt-BR")} créditos
                    </p>
                    <p className="mt-1 text-sm text-white/55">{formatBRL(selectedPack.price)}</p>
                  </div>
                </CardContent>
              </Card>
            </section>
          </>
        )}
      </main>

      {confirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
            aria-label="Fechar"
            onClick={() => !purchase.isPending && setConfirmOpen(false)}
          />
          <div
            role="dialog"
            aria-modal
            aria-labelledby="confirm-purchase-title"
            className="relative z-10 w-full max-w-md overflow-hidden rounded-[24px] border border-border bg-white shadow-2xl"
          >
            <div className="border-b border-border px-5 py-4">
              <h2 id="confirm-purchase-title" className="text-base font-semibold">
                Confirmar compra de créditos
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {CHANNELS.find((c) => c.key === channel)?.label} ·{" "}
                {selectedPack.credits.toLocaleString("pt-BR")} créditos ·{" "}
                {formatBRL(selectedPack.price)}
              </p>
            </div>
            <div className="space-y-3 px-5 py-4 text-sm text-muted-foreground">
              <p>
                Esta operação adiciona créditos ao saldo da sua instituição. Não processa
                pagamento com cartão nesta etapa — o lançamento financeiro depende do fluxo
                comercial configurado.
              </p>
            </div>
            <div className="flex justify-end gap-2 border-t border-border px-5 py-4">
              <Button
                type="button"
                variant="outline"
                disabled={purchase.isPending}
                onClick={() => setConfirmOpen(false)}
              >
                Cancelar
              </Button>
              <Button
                type="button"
                disabled={purchase.isPending}
                onClick={() => purchase.mutate()}
              >
                {purchase.isPending ? "Processando…" : "Confirmar compra"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {invoicesOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
            aria-label="Fechar"
            onClick={() => setInvoicesOpen(false)}
          />
          <div
            role="dialog"
            aria-modal
            aria-labelledby="invoices-title"
            className="relative z-10 w-full max-w-lg overflow-hidden rounded-[24px] border border-border bg-white shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <h2 id="invoices-title" className="text-base font-semibold">
                  Faturas
                </h2>
                <p className="text-xs text-muted-foreground">Histórico desta instituição</p>
              </div>
              <button
                type="button"
                onClick={() => setInvoicesOpen(false)}
                className="grid h-9 w-9 place-items-center rounded-full hover:bg-muted"
                aria-label="Fechar"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <ul className="max-h-[360px] overflow-y-auto">
              {invoices.length === 0 ? (
                <li className="px-5 py-8 text-center text-sm text-muted-foreground">
                  Nenhuma fatura disponível ainda.
                </li>
              ) : (
                invoices.map((inv) => (
                  <li
                    key={inv.id}
                    className="flex items-center justify-between gap-3 border-b border-border/70 px-5 py-3.5 last:border-0"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-semibold">
                        {new Date(inv.date).toLocaleDateString("pt-BR", {
                          day: "2-digit",
                          month: "long",
                          year: "numeric",
                        })}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {inv.label || "Fatura"} · {formatBRL(inv.amount_brl)}
                      </p>
                    </div>
                    {inv.download_url ? (
                      <a
                        href={inv.download_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-border px-3 text-xs font-semibold transition hover:bg-muted"
                      >
                        <Download className="h-3.5 w-3.5" />
                        Baixar
                      </a>
                    ) : (
                      <button
                        type="button"
                        className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-border px-3 text-xs font-semibold text-muted-foreground"
                        onClick={() =>
                          toast.message("PDF ainda não disponível para esta fatura.")
                        }
                      >
                        <Download className="h-3.5 w-3.5" />
                        Indisponível
                      </button>
                    )}
                  </li>
                ))
              )}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}

function channelLabel(channel: string) {
  return CHANNELS.find((c) => c.key === channel)?.label || channel;
}

function MetricDark({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3">
      <p className="text-[11px] font-medium text-white/45">{label}</p>
      <p className="mt-1 text-lg font-semibold tracking-tight text-white">{value}</p>
    </div>
  );
}

function formatBRL(value: number) {
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
