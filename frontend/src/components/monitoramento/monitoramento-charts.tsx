"use client";

import Link from "next/link";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Info,
  TrendingUp,
  Users,
} from "lucide-react";
import { RiskBadge } from "@/components/ui/badge";
import type { RiskHistoryAssessment, RiskHistoryResponse, RiskMovement } from "@/types/api";
import { cn } from "@/lib/utils";

export type Period = "30" | "90" | "180" | "365";

export const CHANGE_LABEL: Record<RiskMovement["change_type"], string> = {
  risco_aumentou: "Risco aumentou",
  risco_diminuiu: "Risco diminuiu",
  sem_mudanca_relevante: "Sem mudança",
  sem_historico_comparavel: "Sem histórico comparável",
  mudanca_modelo: "Mudança de modelo",
};

export function dateLabel(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

export function dateTimeLabel(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function scoreLabel(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
}

export function movementTone(change: RiskMovement["change_type"]) {
  if (change === "risco_aumentou") return "bg-[#FEF3F2] text-[#B42318]";
  if (change === "risco_diminuiu") return "bg-[#ECFDF3] text-[#027A48]";
  if (change === "mudanca_modelo") return "bg-[#F4F3FF] text-[#5925DC]";
  return "bg-[#F2F4F7] text-[#475467]";
}

export function ScoreTimeline({ data }: { data: RiskHistoryResponse["timeline"] }) {
  const buckets = [...new Set(data.map((p) => p.bucket))].sort();
  const series = [
    ...new Set(
      data.map(
        (p) => p.model_scope + " · " + p.model_version + " · " + p.score_semantics_version
      )
    ),
  ];
  if (!data.length || !buckets.length) {
    return (
      <div className="grid min-h-[220px] place-items-center rounded-lg bg-[#F8FAFC] px-5 text-center text-[13px] text-[#667085]">
        Ainda não há avaliações históricas suficientes. Novas avaliações aparecerão aqui depois de
        executadas.
      </div>
    );
  }
  const x = (bucket: string) =>
    54 + (buckets.length <= 1 ? 0 : (buckets.indexOf(bucket) * 790) / (buckets.length - 1));
  const y = (score: number) => 210 - Math.max(0, Math.min(100, score)) * 1.75;
  const colors = ["#2563EB", "#7F56D9", "#039855", "#D92D20"];
  return (
    <div>
      <div className="overflow-x-auto">
        <svg
          viewBox="0 0 900 250"
          role="img"
          aria-label="Evolução da média dos scores por semana e versão do modelo"
          className="min-w-[640px] w-full"
        >
          {[0, 25, 50, 75, 100].map((tick) => (
            <g key={tick}>
              <line x1="54" x2="844" y1={y(tick)} y2={y(tick)} stroke="#EAECF0" strokeDasharray="3 4" />
              <text x="42" y={y(tick) + 4} fontSize="11" textAnchor="end" fill="#667085">
                {tick}
              </text>
            </g>
          ))}
          {buckets.map((bucket) => (
            <text key={bucket} x={x(bucket)} y="236" fontSize="10" textAnchor="middle" fill="#667085">
              {dateLabel(bucket)}
            </text>
          ))}
          {series.map((key, index) => {
            const points = data
              .filter(
                (p) =>
                  p.model_scope + " · " + p.model_version + " · " + p.score_semantics_version === key
              )
              .sort((a, b) => a.bucket.localeCompare(b.bucket));
            const color = colors[index % colors.length];
            return (
              <g key={key}>
                {points.slice(1).map((point, i) => {
                  const prev = points[i];
                  if (new Date(point.bucket).getTime() - new Date(prev.bucket).getTime() > 8 * 86400000)
                    return null;
                  return (
                    <line
                      key={prev.bucket + point.bucket}
                      x1={x(prev.bucket)}
                      y1={y(prev.average_score)}
                      x2={x(point.bucket)}
                      y2={y(point.average_score)}
                      stroke={color}
                      strokeWidth="2.5"
                      strokeLinecap="round"
                    />
                  );
                })}
                {points.map((point) => (
                  <circle key={point.bucket} cx={x(point.bucket)} cy={y(point.average_score)} r="4" fill={color}>
                    <title>
                      {dateLabel(point.bucket) +
                        " · média " +
                        scoreLabel(point.average_score) +
                        " · " +
                        point.students_count +
                        " alunos · " +
                        point.model_scope +
                        " v" +
                        point.model_version +
                        " · " +
                        point.score_semantics_version}
                    </title>
                  </circle>
                ))}
              </g>
            );
          })}
        </svg>
      </div>
      <div className="mt-2 flex flex-wrap gap-3">
        {series.map((key, i) => (
          <span key={key} className="inline-flex items-center gap-2 text-[11px] text-[#475467]">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: colors[i % colors.length] }} />
            {key}
          </span>
        ))}
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-[#667085]">
        Cada ponto representa a média do score da última avaliação de cada aluno naquela semana,
        agrupada por escopo, versão e semântica do score. Séries incompatíveis ficam separadas;
        lacunas superiores a uma semana não são conectadas. Ausência de pontos não implica
        estabilidade do risco.
      </p>
    </div>
  );
}

export function DistributionTimeline({ data }: { data: RiskHistoryResponse["timeline"] }) {
  const rows = [...data]
    .sort(
      (a, b) =>
        a.bucket.localeCompare(b.bucket) ||
        a.model_scope.localeCompare(b.model_scope) ||
        a.model_version.localeCompare(b.model_version) ||
        a.score_semantics_version.localeCompare(b.score_semantics_version)
    )
    .slice(-12);
  if (!rows.length) {
    return (
      <p className="rounded-lg bg-[#F8FAFC] p-4 text-[13px] text-[#667085]">
        A distribuição histórica será exibida quando houver avaliações no período.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {rows.map((point) => {
        const distribution = point.risk_distribution;
        const total = distribution.baixo + distribution.medio + distribution.critico;
        const label = dateLabel(point.bucket) + " · " + point.model_scope + " v" + point.model_version;
        return (
          <div key={point.bucket + point.model_scope + point.model_version + point.score_semantics_version}>
            <div className="mb-1.5 flex items-center justify-between gap-2 text-[10px] text-[#667085]">
              <span>{label}</span>
              <span>{point.students_count} alunos</span>
            </div>
            <div
              className="flex h-3 overflow-hidden rounded-full bg-[#F2F4F7]"
              title={distribution.critico + " críticos, " + distribution.medio + " médios, " + distribution.baixo + " baixos"}
            >
              {total > 0 && (
                <>
                  <div className="bg-[#12B76A]" style={{ width: (distribution.baixo / total) * 100 + "%" }} />
                  <div className="bg-[#F79009]" style={{ width: (distribution.medio / total) * 100 + "%" }} />
                  <div className="bg-[#F04438]" style={{ width: (distribution.critico / total) * 100 + "%" }} />
                </>
              )}
            </div>
            <p className="mt-1 text-[9px] text-[#98A2B3]">{point.score_semantics_version}</p>
          </div>
        );
      })}
    </div>
  );
}

export function CurrentRiskDistribution({
  summary,
  totalStudents,
  totalScored,
}: {
  summary: { baixo: number; medio: number; critico: number; sem_score: number };
  totalStudents?: number;
  totalScored?: number;
}) {
  const scored = summary.baixo + summary.medio + summary.critico;
  const total =
    typeof totalStudents === "number" && totalStudents > 0 ? totalStudents : scored + summary.sem_score;
  const pct = (n: number) => (total > 0 ? ((n / total) * 100).toFixed(1).replace(".", ",") : "0");
  const rows = [
    { key: "critico", label: "Crítico", value: summary.critico, color: "bg-[#F04438]", href: "/alunos?risk_level=critico" },
    { key: "medio", label: "Moderado", value: summary.medio, color: "bg-[#F79009]", href: "/alunos?risk_level=medio" },
    { key: "baixo", label: "Baixo", value: summary.baixo, color: "bg-[#12B76A]", href: "/alunos?risk_level=baixo" },
    { key: "sem_score", label: "Sem score", value: summary.sem_score, color: "bg-[#98A2B3]", href: "/alunos" },
  ];
  return (
    <div className="space-y-4">
      <div className="flex h-3 overflow-hidden rounded-full bg-[#F2F4F7]">
        {rows.map((row) =>
          total > 0 && row.value > 0 ? (
            <div key={row.key} className={row.color} style={{ width: (row.value / total) * 100 + "%" }} title={row.label + ": " + row.value} />
          ) : null
        )}
      </div>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.key} className="flex items-center justify-between gap-3 text-[12px]">
            <span className="inline-flex items-center gap-2 text-[#344054]">
              <span className={cn("h-2.5 w-2.5 rounded-full", row.color)} />
              {row.label}
            </span>
            <span className="tabular-nums text-[#101828]">
              <strong>{row.value.toLocaleString("pt-BR")}</strong>
              <span className="ml-2 text-[11px] text-[#667085]">{pct(row.value)}%</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="text-[11px] leading-relaxed text-[#667085]">
        Fonte: snapshot atual de GET /api/v1/risk/summary.
        {typeof totalScored === "number" ? ` Avaliados com score: ${totalScored.toLocaleString("pt-BR")}.` : ""}{" "}
        <strong className="font-medium text-[#475467]">Sem score não é classificado como baixo risco.</strong>
      </p>
      <div className="flex flex-wrap gap-2">
        {rows.slice(0, 3).map((row) => (
          <Link
            key={row.key}
            href={row.href}
            className="inline-flex items-center gap-1 rounded-lg border border-[#D0D5DD] px-2.5 py-1.5 text-[11px] font-medium text-[#344054] hover:bg-[#F9FAFB]"
          >
            Ver {row.label.toLowerCase()}
            <ArrowRight className="h-3 w-3" />
          </Link>
        ))}
      </div>
    </div>
  );
}

export function StudentAssessmentTimeline({ assessments }: { assessments: RiskHistoryAssessment[] }) {
  const points = [...assessments].sort((a, b) => a.evaluated_at.localeCompare(b.evaluated_at));
  if (!points.length) return null;
  const width = 820,
    height = 190,
    left = 42,
    right = 18,
    top = 14,
    bottom = 32;
  const x = (index: number) =>
    left + (points.length <= 1 ? (width - left - right) / 2 : (index * (width - left - right)) / (points.length - 1));
  const y = (score: number) => top + ((100 - score) * (height - top - bottom)) / 100;
  return (
    <div className="mb-5 rounded-lg border border-[#EAECF0] p-3">
      <h3 className="mb-2 text-[12px] font-semibold text-[#344054]">Trajetória temporal do score</h3>
      <div className="overflow-x-auto">
        <svg viewBox={"0 0 " + width + " " + height} role="img" aria-label="Trajetória individual do score de risco" className="min-w-[600px] w-full">
          {[0, 25, 50, 75, 100].map((tick) => (
            <g key={tick}>
              <line x1={left} x2={width - right} y1={y(tick)} y2={y(tick)} stroke="#EAECF0" strokeDasharray="3 4" />
              <text x={left - 8} y={y(tick) + 4} fontSize="10" textAnchor="end" fill="#667085">{tick}</text>
            </g>
          ))}
          {points.map((point, index) => {
            const previous = points[index - 1];
            const compatible = Boolean(
              previous &&
                point.model_version &&
                previous.model_version &&
                point.model_version === previous.model_version &&
                point.model_scope === previous.model_scope &&
                point.score_semantics_version === previous.score_semantics_version &&
                point.score_basis === previous.score_basis
            );
            const gap = previous
              ? new Date(point.evaluated_at).getTime() - new Date(previous.evaluated_at).getTime()
              : 0;
            const connect = compatible && gap <= 45 * 86400000;
            return (
              <g key={point.id}>
                {connect && previous && (
                  <line x1={x(index - 1)} y1={y(previous.score)} x2={x(index)} y2={y(point.score)} stroke="#2563EB" strokeWidth="2.5" />
                )}
                <circle cx={x(index)} cy={y(point.score)} r="4" fill="#FFFFFF" stroke="#2563EB" strokeWidth="2">
                  <title>
                    {dateTimeLabel(point.evaluated_at) +
                      " · score " +
                      scoreLabel(point.score) +
                      " · " +
                      point.risk_level +
                      " · " +
                      (point.model_version || "versão não identificada")}
                  </title>
                </circle>
                <text x={x(index)} y={height - 10} fontSize="9" textAnchor="middle" fill="#667085">
                  {dateLabel(point.evaluated_at)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <p className="mt-1 text-[10px] text-[#667085]">
        A linha é interrompida entre modelos/semânticas incompatíveis ou lacunas superiores a 45 dias.
      </p>
    </div>
  );
}

export function Metric({
  label,
  value,
  hint,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: number;
  hint: string;
  icon: React.ReactNode;
  tone?: "neutral" | "danger" | "success";
}) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-white p-4",
        tone === "danger" && "border-[#FECDCA]",
        tone === "success" && "border-[#A6F4C5]",
        tone === "neutral" && "border-[#E5E7EB]"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-medium text-[#667085]">{label}</p>
        <span className="text-[#98A2B3]">{icon}</span>
      </div>
      <p className="mt-3 text-[25px] font-semibold tracking-[-0.04em] text-[#101828]">
        {value.toLocaleString("pt-BR")}
      </p>
      <p className="mt-1 text-[10px] leading-relaxed text-[#667085]">{hint}</p>
    </div>
  );
}
