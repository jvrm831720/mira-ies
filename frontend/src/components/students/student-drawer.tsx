"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertCircle,
  ExternalLink,
  History,
  Mail,
  MessageCircle,
  Phone,
  ShieldCheck,
  Smartphone,
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

const AUDIT_LABELS: Record<string, string> = {
  global_opt_out_enabled: "Bloqueio global ativado",
  global_opt_out_disabled: "Bloqueio global desativado",
  channel_preference_changed: "Preferência de canal alterada",
  topic_preference_changed: "Preferência de finalidade alterada",
};

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
  const preferences = (s?.communication_preferences as CommunicationPreferences | undefined) || DEFAULT_PREFERENCES;
  const globalOptOut = Boolean(s?.communication_opt_out);

  return (
    <>
      <div
        className={`fixed inset-0 z-40 bg-black/25 backdrop-blur-[1px] transition-opacity ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={onClose}
        aria-hidden={!open}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Detalhes do aluno"
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-[440px] flex-col border-l border-border bg-white shadow-[-24px_0_60px_rgba(16,13,80,0.12)] transition-transform duration-300 ease-out ${open ? "translate-x-0" : "translate-x-full"}`}
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">Ficha rápida</p>
            {detail.isLoading ? <Skeleton className="mt-2 h-6 w-48" /> : <h2 className="mt-1 truncate text-lg font-semibold tracking-tight">{nome}</h2>}
            <p className="mt-0.5 text-xs text-muted-foreground">Matrícula {matricula} · {curso}</p>
          </div>
          <button type="button" onClick={onClose} className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-border hover:bg-muted" aria-label="Fechar">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          {detail.isLoading && <div className="space-y-3"><Skeleton className="h-24 w-full rounded-2xl" /><Skeleton className="h-32 w-full rounded-2xl" /></div>}
          {detail.isError && <p className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">Não foi possível carregar os detalhes deste aluno.</p>}

          {!detail.isLoading && !detail.isError && s && (
            <>
              <div className="rounded-2xl border border-border bg-muted/30 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-medium text-muted-foreground">Nível de risco</p>
                    <div className="mt-1.5"><RiskBadge level={riskLevel} /></div>
                  </div>
                  <div className="text-right">
                    <p className="text-[11px] font-medium text-muted-foreground">Score</p>
                    <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight">{formatScore(Number.isFinite(score) ? score : undefined)}</p>
                  </div>
                </div>
                {shap ? <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{String(shap)}</p> : null}
              </div>

              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Contato</p>
                <div className="space-y-2 rounded-2xl border border-border p-3">
                  <div className="flex items-center gap-2 text-sm"><Phone className="h-4 w-4 text-muted-foreground" /><span>{phone ? String(phone) : "Telefone não informado"}</span></div>
                  <div className="flex items-center gap-2 text-sm"><Mail className="h-4 w-4 text-muted-foreground" /><span className="truncate">{email ? String(email) : "E-mail não informado"}</span></div>
                </div>
              </div>

              <ConsentPreferencesPanel
                key={studentId}
                studentId={studentId!}
                globalOptOut={globalOptOut}
                preferences={preferences}
              />

              {factors.length > 0 && (
                <div className="space-y-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Principais fatores de risco</p>
                  <ul className="space-y-2">
                    {factors.slice(0, 5).map((factor, index) => (
                      <li key={index} className="rounded-xl border border-border bg-white px-3 py-2 text-sm">
                        <span className="font-medium">{String(factor.label || factor.feature || factor.name || `Fator ${index + 1}`)}</span>
                        {factor.impact != null && <span className="ml-2 text-xs text-muted-foreground">{String(factor.impact)}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>

        <div className="border-t border-border p-4">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Link
              href={studentId ? `/alunos/${studentId}` : "#"}
              onClick={(event) => { if (!studentId) { event.preventDefault(); return; } onClose(); }}
              aria-disabled={!studentId}
              tabIndex={studentId ? undefined : -1}
              className={buttonVariants({ className: `flex-1 rounded-full ${!studentId ? "pointer-events-none opacity-50" : ""}` })}
            >
              <ExternalLink className="h-4 w-4" /> Abrir ficha completa
            </Link>
            <Link
              href="/retencao"
              onClick={(event) => { if (!studentId) { event.preventDefault(); return; } onClose(); }}
              aria-disabled={!studentId}
              tabIndex={studentId ? undefined : -1}
              className={buttonVariants({ variant: "outline", className: `flex-1 rounded-full ${!studentId ? "pointer-events-none opacity-50" : ""}` })}
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
  const audit = useQuery({
    queryKey: ["consent-audit", studentId],
    queryFn: () => api.consentAudit(studentId, 6),
    enabled: Boolean(studentId),
  });

  const update = useMutation({
    mutationFn: (body: CommunicationPreferenceUpdate) => api.updateCommunicationPreferences(studentId, body),
    onSuccess: async () => {
      toast.success("Preferência atualizada e alteração registrada na auditoria.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["student-risk", studentId] }),
        queryClient.invalidateQueries({ queryKey: ["consent-audit", studentId] }),
      ]);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Não foi possível atualizar a preferência.");
    },
  });

  return (
    <section className="overflow-hidden rounded-2xl border border-border">
      <div className="flex items-start gap-3 border-b border-border bg-muted/25 px-4 py-3.5">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[rgba(64,80,205,0.09)] text-primary"><ShieldCheck className="h-4 w-4" /></span>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-neutral-900">Preferências de comunicação</h3>
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">Defina quais canais e finalidades são permitidos para este aluno.</p>
        </div>
      </div>
      <div className="space-y-4 p-4">
        <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-[#f2d5d1] bg-[#fff6f4] p-3">
          <input
            type="checkbox"
            checked={globalOptOut}
            disabled={update.isPending}
            onChange={(event) => update.mutate({ opt_out: event.target.checked })}
            className="mt-0.5 h-4 w-4 accent-[#b84336]"
          />
          <span>
            <span className="block text-xs font-semibold text-[#9c3c32]">Bloqueio global de contato</span>
            <span className="mt-1 block text-[10px] leading-relaxed text-[#9c3c32]/80">Quando ativado, bloqueia todos os canais mesmo que estejam permitidos individualmente.</span>
          </span>
        </label>

        <div className="space-y-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-neutral-500">Canais</p>
          {CHANNEL_OPTIONS.map(({ key, label, detail, icon: Icon }) => (
            <label key={key} className="flex cursor-pointer items-center gap-3 rounded-xl border border-border px-3 py-2.5 transition hover:bg-muted/20">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-muted text-neutral-600"><Icon className="h-4 w-4" /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-xs font-semibold text-neutral-800">{label}</span>
                <span className="mt-0.5 block text-[10px] text-neutral-500">{detail}</span>
              </span>
              <input
                type="checkbox"
                checked={preferences.channels[key]}
                disabled={update.isPending}
                onChange={(event) => update.mutate({ channels: { [key]: event.target.checked } })}
                aria-label={`${label} permitido`}
                className="h-4 w-4 accent-[#4050cd]"
              />
            </label>
          ))}
        </div>

        <div className="space-y-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-neutral-500">Finalidades</p>
          {TOPIC_OPTIONS.map(({ key, label, detail }) => (
            <label key={key} className="flex cursor-pointer items-start gap-3 rounded-xl border border-border px-3 py-2.5 transition hover:bg-muted/20">
              <input
                type="checkbox"
                checked={preferences.topics[key]}
                disabled={update.isPending}
                onChange={(event) => update.mutate({ topics: { [key]: event.target.checked } })}
                aria-label={`${label} permitido`}
                className="mt-0.5 h-4 w-4 accent-[#4050cd]"
              />
              <span className="min-w-0">
                <span className="block text-xs font-semibold text-neutral-800">{label}</span>
                <span className="mt-0.5 block text-[10px] leading-relaxed text-neutral-500">{detail}</span>
              </span>
            </label>
          ))}
        </div>

        {globalOptOut && (
          <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] leading-relaxed text-amber-900">
            O bloqueio global está ativo. As preferências individuais ficam salvas, mas nenhum canal poderá ser usado até o bloqueio ser removido.
          </p>
        )}

        <div className="border-t border-border pt-3">
          <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-neutral-500"><History className="h-3.5 w-3.5" /> Histórico de alterações</p>
          {audit.isLoading ? (
            <div className="mt-3 space-y-2"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
          ) : audit.isError ? (
            <p className="mt-2 text-[10px] text-neutral-500">Não foi possível carregar o histórico neste momento.</p>
          ) : !audit.data?.events.length ? (
            <p className="mt-2 text-[10px] leading-relaxed text-neutral-500">Ainda não há alterações registradas. Mudanças futuras serão auditadas com origem, método e data.</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {audit.data.events.map((event) => (
                <li key={event.id} className="rounded-lg bg-muted/25 px-3 py-2">
                  <p className="text-[10px] font-semibold text-neutral-800">{AUDIT_LABELS[event.event_type] || event.event_type}</p>
                  <p className="mt-1 text-[10px] text-neutral-600">{auditDescription(event)}</p>
                  <p className="mt-1 text-[9px] leading-relaxed text-neutral-400">{formatAuditDate(event.occurred_at)} · {event.source} / {event.method} · {event.location}</p>
                  {event.source_reference && <p className="mt-0.5 break-all text-[9px] text-neutral-400">Referência: {event.source_reference}</p>}
                </li>
              ))}
            </ul>
          )}
        </div>
        {update.isPending && <p className="text-[10px] text-muted-foreground">Salvando preferência…</p>}
        {update.isError && <p role="alert" className="flex items-center gap-1.5 text-[10px] text-red-700"><AlertCircle className="h-3.5 w-3.5" /> A alteração não foi salva.</p>}
      </div>
    </section>
  );
}
