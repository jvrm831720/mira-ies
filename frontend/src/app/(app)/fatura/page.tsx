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
  X,
} from "lucide-react";
import { toast } from "sonner";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

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

export default function FaturaPage() {
  const qc = useQueryClient();
  const [channel, setChannel] = useState<"whatsapp" | "email" | "sms">("whatsapp");
  const [packId, setPackId] = useState<(typeof PACKS)[number]["id"]>("growth");
  const [invoicesOpen, setInvoicesOpen] = useState(false);

  const billing = useQuery({
    queryKey: ["billing-summary"],
    queryFn: () => api.billingSummary(),
    retry: false,
  });

  const purchase = useMutation({
    mutationFn: () =>
      api.purchaseCredits({
        channel,
        pack_id: packId,
        credits: PACKS.find((p) => p.id === packId)!.credits,
      }),
    onSuccess: (data) => {
      toast.success(`${data.added} créditos de ${data.channel} adicionados.`);
      qc.invalidateQueries({ queryKey: ["billing-summary"] });
    },
    onError: (err: Error) => toast.error(err.message || "Não foi possível concluir a compra."),
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
        {/* Plan */}
        <section className="overflow-hidden rounded-[24px] border border-white/10 bg-[#0f0e1c] text-white shadow-[0_24px_80px_rgba(0,0,0,0.18)]">
          <div className="grid gap-0 lg:grid-cols-[1.2fr_0.8fr]">
            <div className="space-y-5 p-6 md:p-8">
              <div className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold text-white/80">
                <Sparkles className="h-3.5 w-3.5 text-[var(--brand-coral)]" />
                Plano atual
              </div>
              <div>
                <h2 className="text-2xl font-semibold tracking-tight">
                  {data?.plan_name || "Plano da instituição"}
                </h2>
                <p className="mt-1 text-sm text-white/55">
                  Renovação em{" "}
                  <strong className="font-semibold text-white/85">
                    {data?.renews_at
                      ? new Date(data.renews_at).toLocaleDateString("pt-BR")
                      : "—"}
                  </strong>
                  {" · "}
                  {data?.billing_cycle === "yearly" ? "Ciclo anual" : "Ciclo mensal"}
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <MetricDark label="Valor do plano" value={formatBRL(data?.plan_price_brl ?? 0)} />
                <MetricDark label="Gasto no período" value={formatBRL(data?.period_spend_brl ?? 0)} />
                <MetricDark
                  label="Disparos no período"
                  value={String(data?.period_messages ?? 0)}
                />
              </div>
            </div>

            <div className="border-t border-white/10 bg-black/25 p-6 md:p-8 lg:border-l lg:border-t-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/40">
                Próxima cobrança
              </p>
              <p className="mt-3 text-3xl font-semibold tracking-tight">
                {formatBRL(data?.next_invoice_brl ?? data?.plan_price_brl ?? 0)}
              </p>
              <p className="mt-2 text-sm text-white/50">
                Valor do plano desta instituição. Créditos extras de canal são cobrados à parte.
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                <Button
                  type="button"
                  onClick={() => setInvoicesOpen(true)}
                  className="rounded-full bg-white text-[#0f0e1c] hover:bg-white/90"
                >
                  <Receipt className="h-4 w-4" />
                  Baixar faturas
                </Button>
                {data?.payment_link ? (
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
                      toast.message("Link de pagamento ainda não configurado para esta instituição.")
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

        {/* Credits */}
        <section className="space-y-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
              Créditos de disparo
            </p>
            <h3 className="mt-1 text-base font-semibold">Saldo por canal</h3>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Cada canal consome créditos próprios ao enviar mensagens.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {CHANNELS.map(({ key, label, icon: Icon, tint }) => {
              const balance = data?.credits?.[key] ?? 0;
              const used = data?.used_period?.[key] ?? 0;
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

        {/* Buy */}
        <section className="grid gap-4 lg:grid-cols-[1fr_0.9fr]">
          <Card className="border-border/80 shadow-[0_10px_30px_rgba(16,13,80,0.04)]">
            <CardHeader>
              <CardTitle className="text-base">Comprar créditos</CardTitle>
              <p className="text-sm text-muted-foreground">
                Escolha o canal e o pacote. Os créditos ficam disponíveis na hora.
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
                onClick={() => purchase.mutate()}
              >
                <Plus className="h-4 w-4" />
                {purchase.isPending
                  ? "Processando…"
                  : `Comprar ${selectedPack.credits.toLocaleString("pt-BR")} créditos de ${CHANNELS.find((c) => c.key === channel)?.label}`}
              </Button>
            </CardContent>
          </Card>

          <Card className="border-border/80 bg-[#0c0b1d] text-white shadow-[0_10px_30px_rgba(16,13,80,0.12)]">
            <CardHeader>
              <CardTitle className="text-base text-white">Como os créditos funcionam</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-white/70">
              <p>
                Cada mensagem enviada consome 1 crédito do canal correspondente (WhatsApp, e-mail ou
                SMS).
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

        {billing.isError && (
          <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Não foi possível carregar a fatura da API. Verifique o backend e tente novamente.
          </p>
        )}
      </main>

      {/* Invoices modal */}
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
                    <a
                      href={inv.download_url || "#"}
                      target={inv.download_url ? "_blank" : undefined}
                      rel="noopener noreferrer"
                      className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-border px-3 text-xs font-semibold transition hover:bg-muted"
                      onClick={(e) => {
                        if (!inv.download_url) {
                          e.preventDefault();
                          toast.message("PDF ainda não disponível para esta fatura.");
                        }
                      }}
                    >
                      <Download className="h-3.5 w-3.5" />
                      Baixar
                    </a>
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
