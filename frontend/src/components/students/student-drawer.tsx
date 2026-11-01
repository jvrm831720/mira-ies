"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  BookOpen,
  ExternalLink,
  History,
  Mail,
  MessageCircle,
  Phone,
  ShieldCheck,
  Smartphone,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { RiskBadge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type {
  CommunicationChannel,
  CommunicationPreferences,
  CommunicationTopic,
  CommunicationPreferenceUpdate,
  ConsentAuditEvent,
} from "@/types/api";
import { formatScore } from "@/lib/utils";
import { StudentWorkTimeline } from "@/components/students/student-work-timeline";

const DEFAULT_PREFERENCES: CommunicationPreferences = {
  channels: { whatsapp: true, email: true, sms: true },
  topics: { academic: true, retention: true, promotional: false },
};

const CHANNEL_OPTIONS: Array<{ key: CommunicationChannel; label: string; detail: string; icon: typeof MessageCircle }> = [
  { key: "whatsapp", label: "WhatsApp", detail: "Mensagens no WhatsApp", icon: MessageCircle },
  { key: "email", label: "E-mail", detail: "Mensagens por e-mail", icon: Mail },
  { key: "sms", label: "SMS", detail: "Mensagens de texto", icon: Smartphone },
];

const TOPIC_OPTIONS: Array<{ key: CommunicationTopic; label: string; detail: string }> = [
  { key: "academic", label: "Comunicados acadêmicos", detail: "Avisos e informações acadêmicas" },
  { key: "retention", label: "Acompanhamento de permanência", detail: "Apoio acadêmico e ações de retenção" },
  { key: "promotional", label: "Promoções e marketing", detail: "Ofertas e campanhas promocionais" },
];

function formatAuditDate(value?: string | null) {
  if (!value) return "Data não informada";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Data não informada";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function auditDescription(event: ConsentAuditEvent) {
  if (event.event_type === "global_opt_out_enabled") return "Todos os canais foram bloqueados.";
  if (event.event_type === "global_opt_out_disabled") return "O bloqueio global foi removido; as preferências por canal e finalidade continuam valendo.";
  const state = event.new_value === true ? "permitido" : "bloqueado";
  if (event.channel) {
    const name = CHANNEL_OPTIONS.find((option) => option.key === event.channel)?.label || event.channel;
    return `${name}: ${state}.`;
  }
  if (event.topic) {
    const name = TOPIC_OPTIONS.find((option) => option.key === event.topic)?.label || event.topic;
    return `${name}: ${state}.`;
  }
  return "Preferência atualizada.";
}

export function StudentDrawer({
  studentId,
  onClose,
}: {
  studentId: string | null;
  onClose: () => void;
}) {
  const open = Boolean(studentId);
  const [activeTab, setActiveTab] = useState<"resumo" | "comunicacao" | "contexto" | "historico">("resumo");
  useEffect(() => {
    if (open) setActiveTab("resumo");
  }, [studentId, open]);
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
  const factors = Array.isArray(s?.top_factors)
    ? (s!.top_factors as Array<Record<string, unknown>>)
    : Array.isArray((s as { shap_top_factors?: { top_3?: unknown } })?.shap_top_factors?.top_3)
      ? (((s as { shap_top_factors: { top_3: Array<Record<string, unknown>> } }).shap_top_factors.top_3) as Array<Record<string, unknown>>)
      : [];
  const preferences =
    (s?.communication_preferences as CommunicationPreferences | undefined) || DEFAULT_PREFERENCES;
  const globalOptOut = Boolean(s?.communication_opt_out);

  return (
    <>
      <div
        className={`fixed inset-0 z-40 bg-[#111827]/30 transition-opacity ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
        aria-hidden={!open}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Detalhes do aluno"
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-[440px] flex-col border-l border-[#E5E7EB] bg-white shadow-[-16px_0_40px_rgba(16,24,40,0.12)] transition-transform duration-300 ease-out ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-start justify-between gap-3 border-b border-[#E5E7EB] px-5 py-4">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#2563EB]">
              Ficha rápida
            </p>
            {detail.isLoading ? (
              <Skeleton className="mt-2 h-6 w-48" />
            ) : (
              <h2 className="mt-1 truncate text-[18px] font-semibold tracking-[-0.02em] text-[#111827]">
                {nome}
              </h2>
            )}
            <p className="mt-0.5 text-xs text-[#667085]">
              Matrícula {matricula} · {curso}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[#E5E7EB] text-[#667085] hover:bg-[#F8FAFC] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
            aria-label="Fechar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="border-b border-[#E5E7EB] px-4 py-3">
          <div
            role="tablist"
            aria-label="Seções da ficha do aluno"
            className="grid grid-cols-4 gap-1 rounded-xl bg-[#F8FAFC] p-1"
          >
            {(
              [
                { id: "resumo", label: "Resumo", icon: UserRound },
                { id: "comunicacao", label: "Contato", icon: ShieldCheck },
                { id: "contexto", label: "Contexto", icon: BookOpen },
                { id: "historico", label: "Histórico", icon: History },
              ] as const
            ).map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={activeTab === id}
                onClick={() => setActiveTab(id)}
                className={`flex min-w-0 items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-[11px] font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB] ${
                  activeTab === id
                    ? "bg-white text-[#111827] shadow-sm"
                    : "text-[#667085] hover:text-[#111827]"
                }`}
              >
                <Icon className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          {detail.isLoading && (
            <div className="space-y-3">
              <Skeleton className="h-24 w-full rounded-xl" />
              <Skeleton className="h-32 w-full rounded-xl" />
            </div>
          )}
          {detail.isError && (
            <div
              role="alert"
              className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] px-3 py-3 text-sm text-[#B42318]"
            >
              <p>Não foi possível carregar os detalhes deste aluno.</p>
              <button
                type="button"
                onClick={() => void detail.refetch()}
                className="mt-2 font-semibold underline underline-offset-2"
              >
                Tentar novamente
              </button>
            </div>
          )}

          {!detail.isLoading && !detail.isError && s && activeTab === "resumo" && (
            <>
              <div className="rounded-xl border border-[#E5E7EB] bg-[#F8FAFC] p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-medium text-[#667085]">Nível de risco</p>
                    <div className="mt-1.5">
                      <RiskBadge level={riskLevel} />
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-[11px] font-medium text-[#667085]">Score</p>
                    <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight text-[#111827]">
                      {Number.isFinite(score) ? formatScore(score) : "Sem score"}
                    </p>
                  </div>
                </div>
                {shap && !/\/api\/|GET\s+\/|SHAP sob demanda/i.test(String(shap)) ? (
                  <p className="mt-3 text-xs leading-relaxed text-[#667085]">{String(shap)}</p>
                ) : !Number.isFinite(score) ? (
                  <p className="mt-3 text-xs leading-relaxed text-[#98A2B3]">
                    Ausência de score não significa baixo risco.
                  </p>
                ) : null}
              </div>

              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">
                  Contato
                </p>
                <div className="space-y-2 rounded-xl border border-[#E5E7EB] p-3">
                  <div className="flex items-center gap-2 text-sm text-[#344054]">
                    <Phone className="h-4 w-4 text-[#667085]" />
                    <span>{phone ? String(phone) : "Telefone não informado"}</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm text-[#344054]">
                    <Mail className="h-4 w-4 text-[#667085]" />
                    <span className="truncate">{email ? String(email) : "E-mail não informado"}</span>
                  </div>
                </div>
              </div>

              {factors.length > 0 && (
                <div className="space-y-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">
                    Principais fatores
                  </p>
                  <ul className="space-y-2">
                    {factors.slice(0, 5).map((factor, index) => {
                      const label = String(
                        factor.label || factor.feature || factor.name || `Fator ${index + 1}`
                      );
                      if (/\/api\/|SHAP sob demanda/i.test(label)) return null;
                      return (
                        <li
                          key={index}
                          className="rounded-xl border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#111827]"
                        >
                          <span className="font-medium">{label}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </>
          )}

          {!detail.isLoading && !detail.isError && s && activeTab === "comunicacao" && (
            <section className="space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-[#111827]">Contato e permissões</h3>
                <p className="mt-1 text-xs leading-relaxed text-[#667085]">
                  Confira os dados cadastrados e respeite as preferências de comunicação.
                </p>
              </div>
              <div className="space-y-2 rounded-xl border border-[#E5E7EB] p-3">
                <div className="flex items-center gap-2 text-sm">
                  <Phone className="h-4 w-4 text-[#667085]" />
                  <span className="break-all">{phone ? String(phone) : "Telefone não informado"}</span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Mail className="h-4 w-4 text-[#667085]" />
                  <span className="break-all">{email ? String(email) : "E-mail não informado"}</span>
                </div>
              </div>
              <ConsentPreferencesPanel
                key={studentId}
                studentId={studentId!}
                globalOptOut={globalOptOut}
                preferences={preferences}
              />
            </section>
          )}

          {!detail.isLoading && !detail.isError && s && activeTab === "contexto" && (
            <section className="space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-[#111827]">Contexto do aluno</h3>
                <p className="mt-1 text-xs leading-relaxed text-[#667085]">
                  Abra a ficha completa para editar propriedades comportamentais.
                </p>
              </div>
              <Link
                href={studentId ? `/alunos/${studentId}` : "#"}
                onClick={onClose}
                className={buttonVariants({ className: "w-full rounded-lg" })}
              >
                Abrir ficha completa
              </Link>
            </section>
          )}

          {!detail.isLoading && !detail.isError && s && activeTab === "historico" && studentId && (
            <StudentWorkTimeline studentId={studentId} compact className="border-0 shadow-none" />
          )}
        </div>

        <div className="border-t border-[#E5E7EB] p-4">
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
                className: `flex-1 rounded-lg bg-[#2563EB] hover:bg-[#1D4ED8] ${!studentId ? "pointer-events-none opacity-50" : ""}`,
              })}
            >
              <ExternalLink className="h-4 w-4" /> Abrir ficha completa
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
                className: `flex-1 rounded-lg border-[#E5E7EB] ${!studentId ? "pointer-events-none opacity-50" : ""}`,
              })}
            >
              <MessageCircle className="h-4 w-4" /> Retenção
            </Link>
          </div>
        </div>
      </aside>
    </>
  );
}

function ConsentPreferencesPanel({
  studentId,
  globalOptOut,
  preferences,
}: {
  studentId: string;
  globalOptOut: boolean;
  preferences: CommunicationPreferences;
}) {
  const queryClient = useQueryClient();
  const me = useQuery({
    queryKey: ["current-user"],
    queryFn: () => api.me(),
    enabled: Boolean(studentId),
    retry: false,
  });
  const canEdit = ["admin", "coordinator", "operator"].includes(me.data?.role || "");
  const audit = useQuery({
    queryKey: ["consent-audit", studentId],
    queryFn: () => api.consentAudit(studentId, 6),
    enabled: Boolean(studentId),
  });

  const update = useMutation({
    mutationFn: (body: CommunicationPreferenceUpdate) =>
      api.updateCommunicationPreferences(studentId, body),
    onSuccess: async () => {
      toast.success("Preferência atualizada e alteração registrada na auditoria.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["student-risk", studentId] }),
        queryClient.invalidateQueries({ queryKey: ["consent-audit", studentId] }),
      ]);
    },
    onError: (error) => {
      toast.error(
        error instanceof Error ? error.message : "Não foi possível atualizar a preferência."
      );
    },
  });

  return (
    <section className="overflow-hidden rounded-xl border border-[#E5E7EB]">
      <div className="flex items-start gap-3 border-b border-[#E5E7EB] bg-[#F8FAFC] px-4 py-3.5">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#EFF6FF] text-[#2563EB]">
          <ShieldCheck className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-[#111827]">Preferências de comunicação</h3>
          <p className="mt-1 text-[11px] leading-relaxed text-[#667085]">
            Defina quais canais e finalidades são permitidos para este aluno.
          </p>
        </div>
      </div>
      <div className="space-y-4 p-4">
        {!me.isLoading && !canEdit && (
          <p
            role="status"
            className="rounded-lg border border-[#E5E7EB] bg-[#F8FAFC] px-3 py-2 text-[10px] leading-relaxed text-[#667085]"
          >
            Perfil somente leitura: é possível consultar preferências, mas não alterá-las.
          </p>
        )}
        <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-3">
          <input
            type="checkbox"
            checked={globalOptOut}
            disabled={update.isPending || !canEdit}
            onChange={(event) => update.mutate({ opt_out: event.target.checked })}
            className="mt-0.5 h-4 w-4 accent-[#B42318]"
          />
          <span>
            <span className="block text-xs font-semibold text-[#B42318]">
              Bloqueio global de contato
            </span>
            <span className="mt-1 block text-[10px] leading-relaxed text-[#B42318]/80">
              Quando ativado, bloqueia todos os canais mesmo que estejam permitidos
              individualmente.
            </span>
          </span>
        </label>
        <div className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">
            Canais
          </p>
          {CHANNEL_OPTIONS.map(({ key, label, detail, icon: Icon }) => (
            <label
              key={key}
              className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-[#E5E7EB] p-3"
            >
              <input
                type="checkbox"
                checked={Boolean(preferences.channels?.[key])}
                disabled={update.isPending || !canEdit || globalOptOut}
                onChange={(event) =>
                  update.mutate({ channels: { [key]: event.target.checked } })
                }
                className="mt-0.5 h-4 w-4 accent-[#2563EB]"
              />
              <span className="flex min-w-0 items-start gap-2">
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-[#667085]" />
                <span>
                  <span className="block text-xs font-semibold text-[#111827]">{label}</span>
                  <span className="mt-0.5 block text-[10px] text-[#667085]">{detail}</span>
                </span>
              </span>
            </label>
          ))}
        </div>
        <div className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">
            Finalidades
          </p>
          {TOPIC_OPTIONS.map(({ key, label, detail }) => (
            <label
              key={key}
              className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-[#E5E7EB] p-3"
            >
              <input
                type="checkbox"
                checked={Boolean(preferences.topics?.[key])}
                disabled={update.isPending || !canEdit || globalOptOut}
                onChange={(event) =>
                  update.mutate({ topics: { [key]: event.target.checked } })
                }
                className="mt-0.5 h-4 w-4 accent-[#2563EB]"
              />
              <span>
                <span className="block text-xs font-semibold text-[#111827]">{label}</span>
                <span className="mt-0.5 block text-[10px] text-[#667085]">{detail}</span>
              </span>
            </label>
          ))}
        </div>
        {audit.isLoading && <Skeleton className="h-16 w-full rounded-lg" />}
        {audit.data && audit.data.events.length > 0 && (
          <div className="rounded-xl border border-[#E5E7EB] bg-[#F8FAFC] p-3">
            <p className="text-[11px] font-semibold text-[#344054]">Auditoria recente</p>
            <ul className="mt-2 space-y-1.5">
              {audit.data.events.slice(0, 4).map((ev) => (
                <li key={ev.id} className="text-[10px] leading-relaxed text-[#667085]">
                  <span className="font-medium text-[#344054]">
                    {formatAuditDate(ev.occurred_at)}
                  </span>
                  {" — "}
                  {auditDescription(ev)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
