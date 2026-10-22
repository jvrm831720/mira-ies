"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ExternalLink,
  Mail,
  MessageCircle,
  Phone,
  X,
} from "lucide-react";
import Link from "next/link";
import { RiskBadge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatScore } from "@/lib/utils";

export function StudentDrawer({
  studentId,
  onClose,
}: {
  studentId: string | null;
  onClose: () => void;
}) {
  const open = Boolean(studentId);
  const detail = useQuery({
    queryKey: ["student-risk", studentId],
    queryFn: () => api.studentRisk(studentId!),
    enabled: open && Boolean(studentId),
  });

  const s = detail.data as Record<string, unknown> | undefined;
  const nome = String(s?.nome || "Aluno");
  const matricula = s?.matricula ? String(s.matricula) : "—";
  const curso = s?.curso ? String(s.curso) : "Curso não informado";
  const riskLevel = s?.risk_level ? String(s.risk_level) : undefined;
  const score = typeof s?.risk_score === "number" ? s.risk_score : Number(s?.risk_score);
  const phone = s?.telefone || s?.phone || s?.phone_e164;
  const email = s?.email;
  const shap = s?.shap_summary || s?.explanation;
  const factors = Array.isArray(s?.top_factors) ? (s!.top_factors as Array<Record<string, unknown>>) : [];

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-black/25 backdrop-blur-[1px] transition-opacity ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
        aria-hidden={!open}
      />

      {/* Panel */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Detalhes do aluno"
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-[440px] flex-col border-l border-border bg-white shadow-[-24px_0_60px_rgba(16,13,80,0.12)] transition-transform duration-300 ease-out ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
              Ficha rápida
            </p>
            {detail.isLoading ? (
              <Skeleton className="mt-2 h-6 w-48" />
            ) : (
              <h2 className="mt-1 truncate text-lg font-semibold tracking-tight">{nome}</h2>
            )}
            <p className="mt-0.5 text-xs text-muted-foreground">
              Matrícula {matricula} · {curso}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-border hover:bg-muted"
            aria-label="Fechar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-5">
          {detail.isLoading && (
            <div className="space-y-3">
              <Skeleton className="h-24 w-full rounded-2xl" />
              <Skeleton className="h-32 w-full rounded-2xl" />
            </div>
          )}

          {detail.isError && (
            <p className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              Não foi possível carregar os detalhes deste aluno.
            </p>
          )}

          {!detail.isLoading && !detail.isError && s && (
            <div className="space-y-5">
              <div className="rounded-2xl border border-border bg-muted/30 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-medium text-muted-foreground">Nível de risco</p>
                    <div className="mt-1.5">
                      <RiskBadge level={riskLevel} />
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-[11px] font-medium text-muted-foreground">Score</p>
                    <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight">
                      {formatScore(Number.isFinite(score) ? score : undefined)}
                    </p>
                  </div>
                </div>
                {shap ? (
                  <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{String(shap)}</p>
                ) : null}
              </div>

              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  Contato
                </p>
                <div className="space-y-2 rounded-2xl border border-border p-3">
                  <div className="flex items-center gap-2 text-sm">
                    <Phone className="h-4 w-4 text-muted-foreground" />
                    <span>{phone ? String(phone) : "Telefone não informado"}</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <Mail className="h-4 w-4 text-muted-foreground" />
                    <span className="truncate">{email ? String(email) : "E-mail não informado"}</span>
                  </div>
                </div>
              </div>

              {factors.length > 0 && (
                <div className="space-y-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                    Principais de risco
                  </p>
                  <ul className="space-y-2">
                    {factors.slice(0, 5).map((f, i) => (
                      <li
                        key={i}
                        className="rounded-xl border border-border bg-white px-3 py-2 text-sm"
                      >
                        <span className="font-medium">
                          {String(f.label || f.feature || f.name || `Fator ${i + 1}`)}
                        </span>
                        {f.impact != null && (
                          <span className="ml-2 text-xs text-muted-foreground">
                            {String(f.impact)}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="border-t border-border p-4">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Link
              href={studentId ? `/alunos/${studentId}` : "#"}
              onClick={(event) => {
                if (!studentId) {
                  event.preventDefault();
                  return;
                }
                onClose();
              }}
              aria-disabled={!studentId}
              tabIndex={studentId ? undefined : -1}
              className={buttonVariants({
                className: `flex-1 rounded-full ${!studentId ? "pointer-events-none opacity-50" : ""}`,
              })}
            >
              <ExternalLink className="h-4 w-4" />
              Abrir ficha completa
            </Link>
            <Link
              href="/retencao"
              onClick={(event) => {
                if (!studentId) {
                  event.preventDefault();
                  return;
                }
                onClose();
              }}
              aria-disabled={!studentId}
              tabIndex={studentId ? undefined : -1}
              className={buttonVariants({
                variant: "outline",
                className: `flex-1 rounded-full ${!studentId ? "pointer-events-none opacity-50" : ""}`,
              })}
            >
              <MessageCircle className="h-4 w-4" />
              Retenção
            </Link>
          </div>
        </div>
      </aside>
    </>
  );
}
