"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CreditCard,
  Mail,
  MessageCircle,
  MessageSquare,
  Plus,
  Receipt,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
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

  return (
    <>
      <Header
        title="Fatura e créditos"
        subtitle="Plano da instituição, consumo e créditos por canal de mensagem."
      />
      <main className="mx-auto w-full max-w-[1100px] space-y-6 px-4 pb-12 pt-5 md:px-9">
        {/* Plan strip */}
        <section className="overflow-hidden rounded-[24px] border border-border bg-white shadow-[0_16px_50px_rgba(16,13,80,0.06)]">
          <div className="grid gap-0 lg:grid-cols-[1.2fr_0.8fr]">
            <div className="space-y-4 p-6 md:p-8">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--brand-midnight)] px-3 py-1 text-[11px] font-semibold text-white">
                  <Sparkles className="h-3.5 w-3.5 text-[var(--brand-coral)]" />
                  Plano atual
                </span>
                <StatusBadge status={data?.plan_status === "active" ? "success" : "pending"} />
              </div>
              <div>
                <h2 className="text-2xl font-semibold tracking-tight">
                  {data?.plan_name || "Mira Growth"}
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Renovação em{" "}
                  <strong className="font-semibold text-foreground">
                    {data?.renews_at
                      ? new Date(data.renews_at).toLocaleDateString("pt-BR")
                      : "—"}
                  </strong>
                  {" · "}
                  {data?.billing_cycle === "yearly" ? "Ciclo anual" : "Ciclo mensal"}
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <Metric
                  label="Valor do plano"
                  value={formatBRL(data?.plan_price_brl ?? 497)}
                />
                <Metric
                  label="Gasto no período"
                  value={formatBRL(data?.period_spend_brl ?? 0)}
                />
                <Metric
                  label="Disparos no período"
                  value={String(data?.period_messages ?? 0)}
                />
              </div>
            </div>
            <div className="border-t border-border bg-[var(--brand-midnight)] p-6 text-white md:p-8 lg:border-l lg:border-t-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/45">
                Próxima fatura
              </p>
              <p className="mt-3 text-3xl font-semibold tracking-tight">
                {formatBRL(data?.next_invoice_brl ?? data?.plan_price_brl ?? 497)}
              </p>
              <p className="mt-2 text-sm text-white/60">
                Inclui plano base. Créditos extras de canal são cobrados à parte.
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                <Button className="rounded-full bg-white text-[var(--brand-midnight)] hover:bg-white/90">
                  <Receipt className="h-4 w-4" />
                  Baixar última fatura
                </Button>
                <Button
                  variant="outline"
                  className="rounded-full border-white/20 bg-transparent text-white hover:bg-white/10"
                >
                  <CreditCard className="h-4 w-4" />
                  Método de pagamento
                </Button>
              </div>
            </div>
          </div>
        </section>

        {/* Credits by channel */}
        <section className="space-y-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
              Créditos de disparo
            </p>
            <h3 className="mt-1 text-base font-semibold">Saldo por canal</h3>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Cada canal consome créditos próprios ao enviar mensagens reais.
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

        {/* Buy credits */}
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
                Cada mensagem enviada de verdade (fora do dry-run) consome 1 crédito do canal
                correspondente.
              </p>
              <ul className="space-y-2">
                <li className="flex gap-2">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--brand-coral)]" />
                  WhatsApp, e-mail e SMS têm saldos separados.
                </li>
                <li className="flex gap-2">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--brand-coral)]" />
                  Campanhas em dry-run não descontam créditos.
                </li>
                <li className="flex gap-2">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--brand-coral)]" />
                  Quando o saldo acaba, o canal pausa até a reposição.
                </li>
              </ul>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/40">
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
            Não foi possível carregar a fatura da API. Exibindo valores padrão de demonstração.
          </p>
        )}
      </main>
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border bg-muted/30 px-4 py-3">
      <p className="text-[11px] font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tracking-tight">{value}</p>
    </div>
  );
}

function formatBRL(value: number) {
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
