import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatScore(score?: number | null) {
  if (score === null || score === undefined || Number.isNaN(score)) return "—";
  return Math.round(score).toString();
}

export function riskLabel(level?: string | null) {
  switch (level) {
    case "critico":
      return "Crítico";
    case "medio":
      return "Médio";
    case "baixo":
      return "Baixo";
    default:
      return "Sem score";
  }
}
