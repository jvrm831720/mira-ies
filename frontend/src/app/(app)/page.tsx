"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Header } from "@/components/layout/header";
import { KpiCards } from "@/components/risk/kpi-cards";
import { CriticalList } from "@/components/risk/critical-list";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import { copy } from "@/lib/copy";
import { Upload, MessageSquareHeart, Info } from "lucide-react";

const btnPrimary =
  "inline-flex h-10 items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground shadow-sm transition hover:bg-primary/90";
const btnOutline =
  "inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border bg-background px-4 text-sm font-medium transition hover:bg-muted";

export default function CommandCenterPage() {
  const summary = useQuery({ queryKey: ["risk-summary"], queryFn: () => api.riskSummary() });
  const critical = useQuery({
    queryKey: ["risk-critical"],
    queryFn: () => api.riskCritical(10),
  });
  const model = useQuery({
    queryKey: ["model-info"],
    queryFn: () => api.modelInfo(),
    retry: false,
  });

  return (
    <>
      <Header title={copy.commandTitle} subtitle={copy.commandSubtitle} />
      <main className="space-y-6 p-4 md:p-8">
        <div className="flex flex-wrap gap-3">
          <Link href="/importar" className={btnPrimary}>
            <Upload className="h-4 w-4" />
            {copy.importCta}
          </Link>
          <Link href="/retencao" className={btnOutline}>
            <MessageSquareHeart className="h-4 w-4" />
            {copy.retentionCta}
          </Link>
        </div>

        <KpiCards data={summary.data} loading={summary.isLoading} />

        {(model.data?.disclaimer || model.data?.training_data === "synthetic") && (
          <Card className="border-amber-200 bg-amber-50/60">
            <CardContent className="flex items-start gap-3 p-4 text-sm text-amber-900">
              <Info className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-medium">Sobre o modelo</p>
                <p className="text-amber-800/90">
                  {model.data?.disclaimer || copy.modelDisclaimerFallback}
                  {model.data?.model_scope ? ` · Escopo: ${model.data.model_scope}` : ""}
                  {model.data?.training_data ? ` · Dados: ${model.data.training_data}` : ""}
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        <CriticalList students={critical.data?.students} loading={critical.isLoading} />
      </main>
    </>
  );
}
