import Link from "next/link";
import { Activity, ArrowRight, CircleAlert, Clock3, Mail, MessageCircle, Smartphone } from "@/components/ui/icons";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { InterventionLog } from "@/types/api";

const statusLabels: Record<string, string> = {
  dry_run: "Simulado",
  sent: "Envio registrado",
  sending: "Enviando",
  submitted: "Submetido",
  queued: "Na fila",
  delivered: "Entregue",
  read: "Lido",
  unknown: "Status incerto",
  skipped: "Ignorado",
  failed: "Falhou",
  bounced: "Devolvido",
  rejected: "Rejeitado",
};

function statusTone(status: string) {
  if (["delivered", "read"].includes(status)) return "bg-[#ECFDF3] text-[#027A48]";
  if (status === "sent" || status === "dry_run") return "bg-[#EFF6FF] text-[#2563EB]";
  if (["failed", "bounced", "rejected", "unknown"].includes(status))
    return "bg-[#FEF3F2] text-[#B42318]";
  if (["sending", "submitted", "queued"].includes(status)) return "bg-[#FFFAEB] text-[#B54708]";
  return "bg-[#F8FAFC] text-[#667085]";
}

function formatDate(value?: string | null) {
  if (!value) return "Data indisponível";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Data indisponível";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function channelDetails(channel?: string | null) {
  if (channel === "whatsapp") return { label: "WhatsApp", Icon: MessageCircle };
  if (channel === "email") return { label: "E-mail", Icon: Mail };
  if (channel === "sms") return { label: "SMS", Icon: Smartphone };
  return { label: "Sem canal", Icon: Activity };
}

export function RecentActivity({
  logs,
  loading,
  error,
  onRetry,
}: {
  logs?: InterventionLog[];
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
}) {
  return (
    <Card className="h-full overflow-hidden border-[#E5E7EB] shadow-none">
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0 border-b border-[#E5E7EB] pb-4">
        <div className="min-w-0">
          <CardTitle className="text-[15px] tracking-[-0.02em] text-[#111827]">
            Atividade recente
          </CardTitle>
          <CardDescription className="mt-1 text-[12px] text-[#667085]">
            Últimos registros da régua de retenção. Status de mensagem não confirma retenção.
          </CardDescription>
        </div>
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#EFF6FF] text-[#2563EB]">
          <Activity className="h-4 w-4" />
        </span>
      </CardHeader>
      <CardContent className="space-y-1 pt-2">
        {loading &&
          Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="flex items-center gap-3 py-3">
              <Skeleton className="h-9 w-9 rounded-lg" />
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className="h-3 w-28" />
                <Skeleton className="h-2.5 w-36" />
              </div>
              <Skeleton className="h-5 w-14 rounded-full" />
            </div>
          ))}

        {error && !loading && (
          <div role="alert" className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] px-4 py-5 text-center">
            <CircleAlert className="mx-auto h-5 w-5 text-[#B42318]" />
            <p className="mt-2 text-xs font-semibold text-[#B42318]">
              Não foi possível carregar a atividade.
            </p>
            <button
              type="button"
              onClick={onRetry}
              className="mt-2 text-xs font-semibold text-[#B42318] underline underline-offset-4"
            >
              Tentar novamente
            </button>
          </div>
        )}

        {!loading && !error && (!logs || logs.length === 0) && (
          <div className="flex flex-col items-center px-4 py-9 text-center">
            <span className="grid h-10 w-10 place-items-center rounded-lg bg-[#F8FAFC] text-[#98A2B3]">
              <Clock3 className="h-4 w-4" />
            </span>
            <p className="mt-3 text-xs font-semibold text-[#111827]">Nenhum contato registrado</p>
            <p className="mt-1 max-w-[230px] text-[11px] leading-relaxed text-[#667085]">
              Quando a régua for executada, o histórico aparecerá aqui.
            </p>
          </div>
        )}

        {!loading &&
          !error &&
          logs?.slice(0, 6).map((log) => {
            const channel = channelDetails(log.channel);
            const ChannelIcon = channel.Icon;
            const visibleStatus = log.status === "dry_run" ? "dry_run" : log.delivery_status || log.status;
            const label = statusLabels[visibleStatus] || visibleStatus;
            return (
              <div
                key={log.id}
                className="flex items-center gap-3 border-b border-[#E5E7EB] py-3 last:border-0"
              >
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#F8FAFC] text-[#667085]">
                  <ChannelIcon className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] font-semibold text-[#111827]">
                    {log.matricula ? `Matrícula ${log.matricula}` : "Registro de retenção"}
                  </p>
                  <p className="mt-1 truncate text-[10px] text-[#98A2B3]">
                    {channel.label}
                    {log.risk_level ? ` · Risco ${log.risk_level}` : ""} · {formatDate(log.created_at)}
                  </p>
                  {log.skip_reason && log.status === "skipped" && (
                    <p className="mt-1 truncate text-[10px] text-[#667085]">{log.skip_reason}</p>
                  )}
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-1 text-[9px] font-semibold ${statusTone(visibleStatus)}`}
                >
                  {label}
                </span>
              </div>
            );
          })}

        <div className="border-t border-[#E5E7EB] pt-3">
          <Link
            href="/retencao/logs"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#2563EB] transition hover:text-[#1D4ED8]"
          >
            Ver histórico completo <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
