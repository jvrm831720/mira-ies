"use client";

import { Skeleton } from "@/components/ui/skeleton";

/** Uniform states: no partial dataset is mistaken for an authorized complete record. */
export function RecordLoadState({
  state, onRetry, domain = "registro",
}: {
  state: "loading" | "denied" | "error" | "missing";
  onRetry?: () => void;
  domain?: string;
}) {
  if (state === "loading") {
    return <div aria-label={"Carregando " + domain} role="status" className="space-y-3">
      <Skeleton className="h-16 w-full rounded-xl" />
      <Skeleton className="h-28 w-full rounded-xl" />
      <Skeleton className="h-24 w-full rounded-xl" />
    </div>;
  }
  const message = state === "denied" ? "Seu cargo ou workspace não tem acesso a este registro."
    : state === "missing" ? "Nenhum registro foi disponibilizado pela origem."
    : "Não foi possível consultar os detalhes deste registro.";
  return <div role="alert" className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-panel)] p-5 text-xs text-[var(--color-slate-600)]">
    <p>{message}</p>
    {state === "error" && onRetry && <button type="button" onClick={onRetry}
      className="mt-3 font-semibold text-[var(--color-blue)] hover:underline">Tentar novamente</button>}
  </div>;
}
