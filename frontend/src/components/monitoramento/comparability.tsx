"use client";

import type { RiskHistoryAssessment, RiskMovement } from "@/types/api";
import { cn } from "@/lib/utils";

export function formatModelLabel(parts: {
  model_version?: string | null;
  model_scope?: string | null;
  score_semantics_version?: string | null;
}) {
  const version = parts.model_version?.trim() || "versão n/d";
  const scope = parts.model_scope?.trim();
  const semantics = parts.score_semantics_version?.trim();
  const bits = [scope ? scope + " · v" + version : "v" + version];
  if (semantics) bits.push(semantics);
  return bits.join(" · ");
}

export function comparabilityLabel(change: RiskMovement["change_type"]): {
  label: string;
  detail: string;
  tone: "ok" | "warn" | "muted" | "model";
} {
  if (change === "mudanca_modelo") {
    return {
      label: "Modelo mudou",
      detail: "Versão ou semântica incompatível — delta não é comparável",
      tone: "model",
    };
  }
  if (change === "sem_historico_comparavel") {
    return {
      label: "Sem histórico",
      detail: "Não há avaliação anterior comparável no período",
      tone: "muted",
    };
  }
  if (change === "sem_mudanca_relevante") {
    return {
      label: "Comparável",
      detail: "Mesma família de modelo/semântica; variação irrelevante",
      tone: "ok",
    };
  }
  return {
    label: "Comparável",
    detail: "Mesma família de modelo/semântica",
    tone: "ok",
  };
}

export function ComparabilityBadge({
  change,
  className,
}: {
  change: RiskMovement["change_type"];
  className?: string;
}) {
  const info = comparabilityLabel(change);
  return (
    <span
      title={info.detail}
      className={cn(
        "inline-flex rounded-full px-2 py-0.5 text-[length:var(--type-overline)] font-semibold",
        info.tone === "ok" && "bg-[var(--color-source-ecfdf3)] text-[var(--color-source-027a48)]",
        info.tone === "model" && "bg-[var(--color-legacy-f4f3ff)] text-[var(--color-legacy-5925dc)]",
        info.tone === "muted" && "bg-[var(--color-legacy-f2f4f7)] text-[var(--color-legacy-475467)]",
        info.tone === "warn" && "bg-[var(--color-source-fffaeb)] text-[var(--color-source-b54708)]",
        className
      )}
    >
      {info.label}
    </span>
  );
}

export function ModelVersionCell({
  current,
  previous,
}: {
  current?: string | null;
  previous?: string | null;
  semantics?: string | null;
  previousSemantics?: string | null;
}) {
  return (
    <div className="text-[length:var(--type-caption)] leading-snug text-[var(--color-legacy-475467)]">
      <p className="font-medium text-[var(--color-legacy-344054)]">
        {current?.trim() ? "v" + current.trim() : "versão n/d"}
      </p>
      {previous?.trim() && previous !== current ? (
        <p className="mt-0.5 text-[length:var(--type-overline)] text-[var(--color-legacy-98a2b3)]">antes: v{previous.trim()}</p>
      ) : null}
    </div>
  );
}

export function AssessmentModelLine({ a }: { a: RiskHistoryAssessment }) {
  return (
    <p className="mt-1 text-[length:var(--type-overline)] leading-relaxed text-[var(--color-legacy-667085)]">
      {formatModelLabel({
        model_version: a.model_version,
        model_scope: a.model_scope,
        score_semantics_version: a.score_semantics_version,
      })}
      {a.score_basis ? ` · base ${a.score_basis}` : ""}
    </p>
  );
}
