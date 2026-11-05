"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import { Copy, GraduationCap, LockKeyhole, ShieldCheck } from "@/components/ui/icons";

type EngineStatus = {
  native_academic_enabled: boolean;
  student_portal_enabled: boolean;
  backend: string;
};
type RecordRow = {
  id: string; kind: string; title: string; status?: string | null;
  academic_period?: string | null; source: string;
};
type Invite = { one_time_token: string; expires_at: string; delivery: string };

async function staffRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getAccessToken();
  if (!token) throw new Error("Sessão institucional necessária.");
  const res = await fetch("/api/v1/native-academic" + path, {
    ...init,
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!res.ok) throw new Error(res.status === 503
    ? "O módulo acadêmico ainda está em homologação."
    : "Não foi possível consultar ou atualizar o portal.");
  return res.json() as Promise<T>;
}
const kindLabels: Record<string, string> = {
  enrollment: "Matrícula", attendance: "Frequência",
  assessment: "Avaliação", fee: "Mensalidade",
};

export function NativeAcademicPanel({ studentId }: { studentId: string }) {
  const identity = useQuery({ queryKey: ["org-me"], queryFn: api.me, staleTime: 60_000, retry: false });
  const canView = identity.data?.permissions
    ? identity.data.permissions.includes("students.sensitive.view")
    : ["admin", "coordinator"].includes(identity.data?.role || "");
  const canManage = identity.data?.permissions
    ? identity.data.permissions.includes("settings.manage")
    : identity.data?.role === "admin";

  const status = useQuery({
    queryKey: ["native-academic", "status"],
    queryFn: () => staffRequest<EngineStatus>("/status"),
    enabled: !!canView,
    retry: false,
  });
  const records = useQuery({
    queryKey: ["native-academic", "records", studentId],
    queryFn: () => staffRequest<{ items: RecordRow[] }>(
      "/students/" + encodeURIComponent(studentId) + "/records"
    ),
    enabled: !!canView && status.data?.native_academic_enabled === true,
    retry: false,
  });
  const [invite, setInvite] = useState<Invite | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState(false);

  if (identity.isLoading || !canView) return null;

  async function generateInvite() {
    setCreating(true); setInviteError(null); setInvite(null); setCopied(false);
    try {
      const data = await staffRequest<Invite>(
        "/students/" + encodeURIComponent(studentId) + "/portal-invites",
        { method: "POST" }
      );
      setInvite(data);
    } catch (error) {
      setInviteError(error instanceof Error ? error.message : "Não foi possível emitir o convite.");
    } finally { setCreating(false); }
  }

  return (
    <section className="space-y-4 rounded-[10px] border border-[#E4E7EC] bg-white p-5" aria-label="Motor acadêmico MIRA e Portal do Aluno">
      <div className="flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#F5F8FF] text-[#2563EB]">
          <GraduationCap className="h-4 w-4" />
        </span>
        <div className="flex-1">
          <h2 className="text-[15px] font-semibold text-[#111827]">Registros acadêmicos MIRA</h2>
          <p className="mt-1 text-[12px] leading-5 text-[#667085]">
            Histórico nativo no PostgreSQL, independente de serviços Frappe.
            Somente registros com origem identificada são exibidos.
          </p>
        </div>
      </div>
      {status.isLoading && <p className="text-[12px] text-[#667085]">Verificando disponibilidade do módulo…</p>}
      {status.isError && <p className="text-[12px] text-[#667085]">O módulo acadêmico ainda não está disponível nesta instalação.</p>}
      {status.data && !status.data.native_academic_enabled && (
        <div className="rounded-lg bg-[#F9FAFB] px-4 py-3 text-[12px] text-[#667085]">
          Migração e testes de isolamento pendentes. Nenhuma consulta nativa está habilitada em produção.
        </div>
      )}
      {records.isLoading && <p className="text-[12px] text-[#667085]">Carregando registros…</p>}
      {records.data && records.data.items.length === 0 && (
        <p className="rounded-lg bg-[#F9FAFB] px-4 py-3 text-[12px] text-[#667085]">Nenhum registro acadêmico nativo para este aluno.</p>
      )}
      {records.isError && <p className="text-[12px] text-[#667085]">Registros indisponíveis nesta instalação.</p>}
      {records.data && records.data.items.length > 0 && (
        <ul className="divide-y divide-[#E4E7EC] rounded-lg border border-[#E4E7EC]">
          {records.data.items.slice(0, 10).map(row => (
            <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div>
                <p className="text-[12px] font-semibold text-[#344054]">{row.title}</p>
                <p className="mt-1 text-[11px] text-[#98A2B3]">
                  {kindLabels[row.kind] || "Registro"} · Fonte: {row.source}
                  {row.academic_period ? " · " + row.academic_period : ""}
                </p>
              </div>
              <span className="rounded bg-[#F2F4F7] px-2 py-1 text-[11px] text-[#667085]">{row.status || "Não informado"}</span>
            </li>
          ))}
        </ul>
      )}
      {canManage && (
        <div className="mt-4 border-t border-[#E4E7EC] pt-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-2.5">
              <LockKeyhole className="mt-0.5 h-4 w-4 text-[#2563EB]" />
              <div>
                <h3 className="text-[13px] font-semibold text-[#344054]">Acesso ao Portal do Aluno</h3>
                <p className="mt-1 max-w-[440px] text-[11px] leading-5 text-[#667085]">
                  Convite individual de uso único, com validade de 15 minutos.
                  O envio é manual e exige verificar a identidade do destinatário.
                </p>
              </div>
            </div>
            <button type="button"
              disabled={!status.data?.student_portal_enabled || creating}
              onClick={() => void generateInvite()}
              className="rounded-lg bg-[#101828] px-3 py-2 text-[11px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">
              {creating ? "Emitindo…" : "Gerar convite"}
            </button>
          </div>
          {!status.data?.student_portal_enabled && <p className="mt-3 text-[11px] text-[#98A2B3]">
            Portal desabilitado por segurança até homologar autenticação, migração e isolamento por tenant.
          </p>}
          {inviteError && <p role="alert" className="mt-3 text-[11px] text-[#B42318]">{inviteError}</p>}
          {invite && (
            <div className="mt-4 rounded-lg border border-[#D6E4FF] bg-[#F5F8FF] p-4">
              <div className="flex items-center gap-2 text-[12px] font-semibold text-[#344054]">
                <ShieldCheck className="h-4 w-4 text-[#2563EB]" /> Código emitido uma única vez
              </div>
              <p className="mt-2 text-[11px] leading-5 text-[#667085]">
                Entregue somente ao aluno após confirmar sua identidade. Nunca publique o código em grupos.
                O aluno deve acessar a rota /portal.
              </p>
              <p className="mt-3 break-all rounded border border-[#DCE8FF] bg-white p-3 font-mono text-[11px] text-[#344054]">{invite.one_time_token}</p>
              <button type="button" onClick={() => {
                void navigator.clipboard.writeText(invite.one_time_token).then(() => setCopied(true)).catch(() => setInviteError("Copie manualmente o código acima."));
              }} className="mt-3 inline-flex items-center gap-2 rounded-lg border border-[#C7D7FE] bg-white px-3 py-2 text-[11px] font-semibold text-[#2563EB]">
                <Copy className="h-3.5 w-3.5" /> {copied ? "Copiado" : "Copiar código"}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
