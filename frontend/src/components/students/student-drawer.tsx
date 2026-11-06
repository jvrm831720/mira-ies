"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Mail, MessageCircle, ShieldCheck, Smartphone } from "@/components/ui/icons";
import { RiskBadge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { getVisibleNavigation, hasNavigationPermission } from "@/components/layout/navigation";
import { RecordDrawer } from "@/components/record/record-drawer";
import { RecordProperties } from "@/components/record/record-properties";
import { RecordRelations } from "@/components/record/record-relations";
import { RecordSections } from "@/components/record/record-sections";
import { StudentRecordActivity } from "@/components/record/student-record-activity";
import { StudentRiskTrend } from "./risk-trend";
import { StudentCampaignsPanel } from "./student-campaigns-panel";
import { StudentRiskFactors } from "./student-risk-factors";
import { studentPropertyGroups, studentRecordIdentity, studentRelations } from "@/components/record/student-record-data";
import type { CommunicationChannel, CommunicationPreferences, CommunicationTopic,
  CommunicationPreferenceUpdate, ConsentAuditEvent } from "@/types/api";

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

export function StudentDrawer({ studentId, onClose }: {studentId: string|null;onClose:()=>void}) {
  const open=Boolean(studentId);
  const me=useQuery({queryKey:["org-me"],queryFn:api.me,retry:false,staleTime:60_000});
  const canRead=getVisibleNavigation(me.data).some(group=>group.items.some(item=>item.href==="/alunos"));
  const canSensitive=hasNavigationPermission(me.data,"students.sensitive.view");
  const canCampaigns=hasNavigationPermission(me.data,"campaigns.view");
  const q=useQuery({
    queryKey:["student-risk",studentId],queryFn:()=>api.studentRisk(studentId!),
    enabled:open&&canRead&&Boolean(studentId),retry:false,staleTime:30_000,
  });
  // Stable record ID ensures Query cache reuse between drawer and full page.
  const record=studentId?studentRecordIdentity(studentId,q.data):null;
  const groups=q.data?studentPropertyGroups(q.data,canSensitive):[];
  const sections=[
    {id:"summary",label:"Resumo da IA",content:me.isLoading||q.isLoading?<div role="status" className="space-y-3"><Skeleton className="h-20 w-full"/><Skeleton className="h-28 w-full"/></div>
      : me.isError||!canRead?<p role="alert" className="text-xs text-[var(--color-red)]">Este perfil não tem acesso à ficha do aluno.</p>
      : q.isError?<div role="alert" className="space-y-3 text-xs text-[var(--color-slate-600)]">Não foi possível abrir o aluno.
          <button type="button" onClick={()=>void q.refetch()} className="ml-2 text-[var(--color-blue)]">Tentar novamente</button></div>
      : q.data?<div className="space-y-4">
        {canSensitive&&<div className="flex flex-wrap items-center gap-3 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-3">
          <RiskBadge level={q.data.risk_level}/>
          <p className="text-[length:var(--type-caption)] text-[var(--color-slate-600)]">Score: <span className="font-semibold tabular-nums text-[var(--color-ink)]">
            {typeof q.data.risk_score==="number"&&Number.isFinite(q.data.risk_score)?Math.round(q.data.risk_score):"Não calculado"}
          </span></p>
          {q.data.risk_score==null&&<p className="text-[length:var(--type-caption)] text-[var(--color-muted)]">Sem score não significa baixo risco.</p>}
          {studentId&&<StudentRiskTrend studentId={studentId}/>}
        </div>}
        {canSensitive&&<StudentRiskFactors student={q.data}/>}
        <RecordProperties groups={groups.filter(group=>group.id==="identification"||(canSensitive&&group.id==="risk"))} compact />
        <RecordRelations relations={studentRelations(q.data)}/>
      </div>:null},
    {id:"academic",label:"Acadêmico e financeiro",content:canSensitive&&q.data
      ?<RecordProperties groups={groups.filter(group=>group.id==="academic"||group.id==="finance")} compact />
      :<p className="rounded-[var(--radius-md)] bg-[var(--color-panel)] p-4 text-xs text-[var(--color-muted)]">Indicadores restritos ou indisponíveis.</p>},
    {id:"activity",label:"Timeline de contatos",content:studentId?<StudentRecordActivity studentId={studentId} canView={canSensitive&&canRead}/>:null},
    {id:"campaigns",label:"Campanhas",content:studentId?<StudentCampaignsPanel studentId={studentId} canView={canRead&&canCampaigns&&canSensitive}/>:null},
    {id:"contact",label:"Contato",content:q.data&&canRead?<div className="space-y-4">
      <RecordProperties compact groups={[{id:"contact",title:"Contato cadastrado",properties:[
        {key:"phone",label:"Telefone",value:q.data.telefone},{key:"email",label:"E-mail",value:q.data.email},
        {key:"opt-out",label:"Bloqueio global",value:q.data.communication_opt_out,type:"boolean"},
      ]}]}/>
      {q.data.communication_preferences&&typeof q.data.communication_opt_out==="boolean"
        ?<ConsentPreferencesPanel key={studentId} studentId={studentId!}
            globalOptOut={q.data.communication_opt_out} preferences={q.data.communication_preferences}/>
        :<p role="status" className="text-xs text-[var(--color-muted)]">Preferências de comunicação não disponibilizadas pela origem. Nenhum canal é presumido como permitido.</p>}
    </div>:<p className="text-xs text-[var(--color-muted)]">Sem acesso aos dados de contato.</p>},
  ];
  return <RecordDrawer record={record} onClose={onClose}
    fullPageHref={canRead&&studentId?"/alunos/"+encodeURIComponent(studentId):undefined}
    status={canSensitive&&q.data?<RiskBadge level={q.data.risk_level}/>:undefined}>
    <RecordSections key={studentId||""} sections={sections}/>
  </RecordDrawer>;
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
    queryKey: ["org-me"],
    queryFn: () => api.me(),
    enabled: Boolean(studentId),
    retry: false,
  });
  const canEdit = hasNavigationPermission(me.data, "students.edit");
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
    <section className="overflow-hidden rounded-xl border border-[var(--color-border)]">
      <div className="flex items-start gap-3 border-b border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-3.5">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--color-blue-tint)] text-[var(--color-blue)]">
          <ShieldCheck className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-[var(--color-ink)]">Preferências de comunicação</h3>
          <p className="mt-1 text-[length:var(--type-caption)] leading-relaxed text-[var(--color-slate-600)]">
            Defina quais canais e finalidades são permitidos para este aluno.
          </p>
        </div>
      </div>
      <div className="space-y-4 p-4">
        {!me.isLoading && !canEdit && (
          <p
            role="status"
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2 text-[length:var(--type-overline)] leading-relaxed text-[var(--color-slate-600)]"
          >
            Perfil somente leitura: é possível consultar preferências, mas não alterá-las.
          </p>
        )}
        <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-[var(--color-red-tint-border)] bg-[var(--color-peach-tint)] p-3">
          <input
            type="checkbox"
            checked={globalOptOut}
            disabled={update.isPending || !canEdit}
            onChange={(event) => update.mutate({ opt_out: event.target.checked })}
            className="mt-0.5 h-4 w-4 accent-[var(--color-red)]"
          />
          <span>
            <span className="block text-xs font-semibold text-[var(--color-red)]">
              Bloqueio global de contato
            </span>
            <span className="mt-1 block text-[length:var(--type-overline)] leading-relaxed text-[var(--color-red)]/80">
              Quando ativado, bloqueia todos os canais mesmo que estejam permitidos
              individualmente.
            </span>
          </span>
        </label>
        <div className="space-y-2">
          <p className="text-[length:var(--type-caption)] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]">
            Canais
          </p>
          {CHANNEL_OPTIONS.map(({ key, label, detail, icon: Icon }) => (
            <label
              key={key}
              className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-[var(--color-border)] p-3"
            >
              <input
                type="checkbox"
                checked={Boolean(preferences.channels?.[key])}
                disabled={update.isPending || !canEdit || globalOptOut}
                onChange={(event) =>
                  update.mutate({ channels: { [key]: event.target.checked } })
                }
                className="mt-0.5 h-4 w-4 accent-[var(--color-blue)]"
              />
              <span className="flex min-w-0 items-start gap-2">
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-slate-600)]" />
                <span>
                  <span className="block text-xs font-semibold text-[var(--color-ink)]">{label}</span>
                  <span className="mt-0.5 block text-[length:var(--type-overline)] text-[var(--color-slate-600)]">{detail}</span>
                </span>
              </span>
            </label>
          ))}
        </div>
        <div className="space-y-2">
          <p className="text-[length:var(--type-caption)] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]">
            Finalidades
          </p>
          {TOPIC_OPTIONS.map(({ key, label, detail }) => (
            <label
              key={key}
              className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-[var(--color-border)] p-3"
            >
              <input
                type="checkbox"
                checked={Boolean(preferences.topics?.[key])}
                disabled={update.isPending || !canEdit || globalOptOut}
                onChange={(event) =>
                  update.mutate({ topics: { [key]: event.target.checked } })
                }
                className="mt-0.5 h-4 w-4 accent-[var(--color-blue)]"
              />
              <span>
                <span className="block text-xs font-semibold text-[var(--color-ink)]">{label}</span>
                <span className="mt-0.5 block text-[length:var(--type-overline)] text-[var(--color-slate-600)]">{detail}</span>
              </span>
            </label>
          ))}
        </div>
        {audit.isLoading && <Skeleton className="h-16 w-full rounded-lg" />}
        {audit.data && audit.data.events.length > 0 && (
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] p-3">
            <p className="text-[length:var(--type-caption)] font-semibold text-[var(--color-slate-600)]">Auditoria recente</p>
            <ul className="mt-2 space-y-1.5">
              {audit.data.events.slice(0, 4).map((ev) => (
                <li key={ev.id} className="text-[length:var(--type-overline)] leading-relaxed text-[var(--color-slate-600)]">
                  <span className="font-medium text-[var(--color-slate-600)]">
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
