"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  Building2,
  Database,
  Sparkles,
  UploadCloud,
} from "@/components/ui/icons";
import { toast } from "sonner";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Stepper } from "@/components/ui/stepper";
import { api } from "@/lib/api";

const STEPS = [
  { id: "welcome", label: "Boas-vindas" },
  { id: "institution", label: "Instituição" },
  { id: "data", label: "Dados" },
  { id: "intelligence", label: "Inteligência" },
  { id: "finish", label: "Conclusão" },
];

export function InstitutionalOnboarding() {
  const qc = useQueryClient();
  const me = useQuery({
    queryKey: ["org-me"],
    queryFn: () => api.me(),
    retry: false,
    staleTime: 30_000,
  });

  const [step, setStep] = useState(0);
  const [dismissedSession, setDismissedSession] = useState(false);

  const open = useMemo(() => {
    if (dismissedSession) return false;
    if (me.isLoading || me.isError || !me.data) return false;
    // Only interactive users with a real user_id (password session)
    if (!me.data.user_id) return false;
    return me.data.onboarding_completed !== true;
  }, [me.data, me.isError, me.isLoading, dismissedSession]);

  const complete = useMutation({
    mutationFn: () => api.completeOnboarding(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org-me"] });
      toast.success("Onboarding concluído. Bem-vindo à MIRA.");
      setDismissedSession(true);
    },
    onError: (err: Error) => toast.error(err.message || "Não foi possível salvar o onboarding."),
  });

  const tenant = me.data?.tenant_name || "sua instituição";
  const role = me.data?.role || "membro";

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setDismissedSession(true);
      }}
      title="Bem-vindo à MIRA"
      description="Configure o essencial da operação institucional em poucos passos."
      dismissible
      className="max-w-xl"
    >
      <div className="space-y-5">
        <Stepper steps={STEPS} current={step} />

        {step === 0 && (
          <section className="space-y-3">
            <div className="flex items-center gap-2 text-[var(--brand-indigo)]">
              <Sparkles className="h-5 w-5" />
              <p className="text-sm font-semibold">Inteligência de permanência estudantil</p>
            </div>
            <p className="text-sm text-[var(--text-secondary)]">
              A MIRA centraliza risco, intervenções e resultados para equipes acadêmicas e de
              retenção. Você está entrando como <strong className="text-[var(--text-primary)]">{role}</strong>{" "}
              em <strong className="text-[var(--text-primary)]">{tenant}</strong>.
            </p>
          </section>
        )}

        {step === 1 && (
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-[var(--brand-indigo)]" />
              <p className="text-sm font-semibold">Instituição ativa</p>
            </div>
            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-4 py-3">
              <p className="text-sm font-semibold text-[var(--text-primary)]">{tenant}</p>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">
                Nome e isolamento por tenant já estão definidos no provisionamento. Ajuste membros e
                convites em Configurações quando precisar.
              </p>
            </div>
            <Link href="/membros" className="text-sm font-medium text-[var(--brand-indigo)] hover:underline">
              Gerenciar membros
            </Link>
          </section>
        )}

        {step === 2 && (
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <Database className="h-5 w-5 text-[var(--brand-indigo)]" />
              <p className="text-sm font-semibold">Dados e integrações</p>
            </div>
            <p className="text-sm text-[var(--text-secondary)]">
              Importe planilhas ou envie payloads de ERP/LMS. A gravação definitiva só ocorre após
              confirmação explícita no fluxo de importação.
            </p>
            <div className="flex flex-wrap gap-2">
              <Link href="/importar">
                <Button type="button" size="sm" variant="secondary">
                  <UploadCloud className="h-4 w-4" /> Importar dados
                </Button>
              </Link>
              <Link href="/conectores">
                <Button type="button" size="sm" variant="outline">
                  Dados e integrações
                </Button>
              </Link>
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-[var(--brand-indigo)]" />
              <p className="text-sm font-semibold">Scores e monitoramento</p>
            </div>
            <p className="text-sm text-[var(--text-secondary)]">
              Após a base ser pontuada, a Visão geral, o Monitoramento e a Central de trabalho usam
              scores e históricos reais — sem inventar tendências quando não houver avaliações.
            </p>
          </section>
        )}

        {step === 4 && (
          <section className="space-y-3">
            <p className="text-sm text-[var(--text-secondary)]">
              Você pode concluir agora. O status fica salvo no seu perfil na instituição e não
              depende apenas deste navegador.
            </p>
          </section>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--border-subtle)] pt-4">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setDismissedSession(true)}
          >
            Pular por agora
          </Button>
          <div className="flex gap-2">
            {step > 0 ? (
              <Button type="button" variant="outline" size="sm" onClick={() => setStep((s) => s - 1)}>
                Voltar
              </Button>
            ) : null}
            {step < STEPS.length - 1 ? (
              <Button type="button" size="sm" onClick={() => setStep((s) => s + 1)}>
                Continuar <ArrowRight className="h-4 w-4" />
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                disabled={complete.isPending}
                onClick={() => complete.mutate()}
              >
                {complete.isPending ? "Salvando…" : "Concluir onboarding"}
              </Button>
            )}
          </div>
        </div>
      </div>
    </Dialog>
  );
}
