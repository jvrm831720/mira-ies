"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowRight, MessageSquareText, Users } from "@/components/ui/icons";
import { api } from "@/lib/api";

/**
 * CTA operacional: usa o grupo como público de retenção.
 * - Link principal: /retencao?group={id}&dry_run=1 (pré-preenche a tela)
 * - Ação secundária: dry-run imediato com até 100 membros da 1ª página
 */
export function GroupRetentionCta({
  groupId,
  groupName,
  memberCount,
}: {
  groupId: string;
  groupName: string;
  memberCount?: number;
}) {
  const [running, setRunning] = useState(false);

  const dryRun = useMutation({
    mutationFn: async () => {
      const page = await api.studentGroupMembers(groupId, { limit: 100 });
      const ids = page.members.map((m) => m.student_id);
      if (ids.length === 0) {
        throw new Error("Nenhum integrante TRUE retornado para este grupo.");
      }
      const key =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `group-dry-${groupId}-${Date.now()}`;
      return api.enqueueRetention(
        {
          dry_run: true,
          student_ids: ids,
          limit: ids.length,
          campaign_name: `Grupo · ${groupName}`,
        },
        key
      );
    },
    onSuccess: () => {
      toast.success("Dry-run enfileirado com os integrantes retornados do grupo.");
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Falha ao enfileirar dry-run.");
    },
    onSettled: () => setRunning(false),
  });

  const retentionHref =
    "/retencao?group=" +
    encodeURIComponent(groupId) +
    "&dry_run=1&campaign=" +
    encodeURIComponent(`Grupo · ${groupName}`);

  const listHref = "/alunos?group=" + encodeURIComponent(groupId);

  return (
    <section className="rounded-xl border border-[#BFDBFE] bg-[#F8FAFC] p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <MessageSquareText className="h-4 w-4 text-[#2563EB]" />
            <h2 className="text-[15px] font-semibold text-[#111827]">Usar como público</h2>
          </div>
          <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-[#667085]">
            Abra a retenção com este grupo pré-selecionado. A primeira execução parte em{" "}
            <strong className="font-semibold text-[#344054]">dry-run</strong> (simulação). Opt-out e
            anti-spam continuam valendo.
            {typeof memberCount === "number"
              ? ` · ${memberCount.toLocaleString("pt-BR")} alunos no grupo (métrica da avaliação).`
              : ""}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Link
            href={listHref}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#E5E7EB] bg-white px-3.5 text-[13px] font-medium text-[#344054] transition hover:bg-white"
          >
            <Users className="h-3.5 w-3.5" />
            Ver na lista de alunos
          </Link>
          <button
            type="button"
            disabled={running}
            onClick={() => {
              setRunning(true);
              dryRun.mutate();
            }}
            className="inline-flex h-10 items-center rounded-lg border border-[#E5E7EB] bg-white px-3.5 text-[13px] font-medium text-[#344054] transition hover:bg-[#F8FAFC] disabled:opacity-60"
          >
            {running ? "Enfileirando…" : "Dry-run rápido (até 100)"}
          </button>
          <Link
            href={retentionHref}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#2563EB] px-4 text-[13px] font-semibold text-white transition hover:bg-[#1D4ED8]"
          >
            Usar na retenção
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </section>
  );
}
