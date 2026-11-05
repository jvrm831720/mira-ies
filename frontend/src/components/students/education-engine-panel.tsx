"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle, BookOpenCheck, CheckCircle2, Database, GraduationCap,
  RefreshCw, Wallet,
} from "@/components/ui/icons";
import { api } from "@/lib/api";
import {
  educationEngine, type EducationEngineResource, type EducationEngineRow,
} from "@/lib/education-engine-api";

const resources: { id: EducationEngineResource; label: string; icon: typeof GraduationCap }[] = [
  { id: "enrollments", label: "Matrículas", icon: GraduationCap },
  { id: "attendance", label: "Frequência", icon: BookOpenCheck },
  { id: "grades", label: "Notas", icon: CheckCircle2 },
  { id: "fees", label: "Mensalidades", icon: Wallet },
];

function textValue(raw: unknown): string {
  if (raw == null || raw === "") return "Não informado";
  if (typeof raw === "boolean") return raw ? "Sim" : "Não";
  return String(raw);
}

function recordLabel(record: EducationEngineRow, resource: EducationEngineResource): string {
  if (resource === "attendance") return textValue(record.date);
  if (resource === "grades") return textValue(record.course || record.assessment_plan);
  if (resource === "enrollments") return textValue(record.program);
  return textValue(record.name);
}

function recordDetails(record: EducationEngineRow, resource: EducationEngineResource): string {
  if (resource === "attendance") return "Presença: " + textValue(record.status);
  if (resource === "grades") return "Nota: " + textValue(record.total_score) + " · Conceito: " + textValue(record.grade);
  if (resource === "enrollments") {
    return "Ano: " + textValue(record.academic_year) + " · Período: " + textValue(record.academic_term);
  }
  const currency = typeof record.currency === "string" ? record.currency : "";
  const amount = record.outstanding_amount;
  let visible = textValue(amount);
  if (amount != null && Number.isFinite(Number(amount)) && /^[A-Z]{3}$/.test(currency)) {
    try {
      visible = new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(Number(amount));
    } catch {
      visible = textValue(amount) + " " + currency;
    }
  }
  return "Saldo informado na origem: " + visible + " · Vencimento: " + textValue(record.due_date);
}

export function EducationEngineStudentPanel({ studentId }: { studentId: string }) {
  const [opened, setOpened] = useState(false);
  const [active, setActive] = useState<EducationEngineResource>("enrollments");
  const [offset, setOffset] = useState(0);

  // The academic/finance source is more sensitive than the MIRA risk summary.
  // Never initiate calls for viewers or custom roles lacking explicit permission.
  const identity = useQuery({
    queryKey: ["org-me"], queryFn: () => api.me(), retry: false, staleTime: 60_000,
  });
  const isInstitution = identity.data?.operation_profile === "institution";
  const allowed = identity.data?.permissions
    ? identity.data.permissions.includes("students.sensitive.view")
    : ["admin", "coordinator"].includes(identity.data?.role ?? "");

  const profile = useQuery({
    queryKey: ["education-engine", "student", studentId, "profile"],
    queryFn: () => educationEngine.studentProfile(studentId),
    enabled: opened && isInstitution && allowed,
    retry: false,
    staleTime: 30_000,
  });
  const data = useQuery({
    queryKey: ["education-engine", "student", studentId, active, offset],
    queryFn: () => educationEngine.studentRecords(studentId, active, offset),
    enabled: opened && isInstitution && allowed && profile.isSuccess,
    retry: false,
    staleTime: 30_000,
  });

  if (identity.isLoading || !isInstitution || !allowed) return null;

  return (
    <section className="scroll-mt-24 overflow-hidden rounded-[10px] border border-[#E4E7EC] bg-white" aria-label="Dados do motor acadêmico MIRA">
      <div className="flex flex-wrap items-center justify-between gap-3 p-5">
        <div className="flex items-start gap-3">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[#E4E7EC] bg-[#F9FAFB] text-[#266DF0]">
            <Database className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-[15px] font-semibold text-[#111827]">Registros da instituição</h2>
            <p className="mt-1 text-[12px] leading-5 text-[#667085]">
              Dados operacionais do motor acadêmico próprio, vinculados a esta ficha.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpened((current) => !current)}
          aria-expanded={opened}
          className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#D0D5DD] bg-white px-3 text-[12px] font-semibold text-[#344054] hover:bg-[#F9FAFB] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#266DF0]"
        >
          {opened ? "Ocultar registros" : "Consultar origem"}
        </button>
      </div>

      {opened && (
        <div className="border-t border-[#E4E7EC] p-5">
          {profile.isLoading && (
            <p className="text-[12px] text-[#667085]">Verificando o vínculo com o sistema acadêmico…</p>
          )}
          {profile.isError && (
            <div role="status" className="flex gap-2.5 rounded-lg border border-[#EAECF0] bg-[#F9FAFB] p-4">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#667085]" />
              <div>
                <p className="text-[13px] font-semibold text-[#344054]">Registros indisponíveis</p>
                <p className="mt-1 text-[12px] leading-5 text-[#667085]">
                  A conexão pode estar desativada, indisponível ou este aluno ainda não ter sido vinculado.
                  A MIRA não preenche dados ausentes por estimativa.
                </p>
                <Link href="/conectores/education-engine" className="mt-2 inline-block text-[12px] font-semibold text-[#266DF0] hover:underline">
                  Ver integração
                </Link>
              </div>
            </div>
          )}
          {profile.data && (
            <>
              <div className="mb-5 flex flex-wrap items-center gap-3 rounded-lg border border-[#D1FADF] bg-[#F6FEF9] px-4 py-3">
                <CheckCircle2 className="h-4 w-4 text-[#079455]" />
                <p className="text-[12px] font-medium text-[#067647]">
                  Vínculo confirmado: {textValue(profile.data.profile.student_name || profile.data.profile.name)}
                </p>
                <span className="ml-auto text-[11px] font-medium text-[#667085]">Origem: MIRA Education Engine</span>
              </div>
              <div role="tablist" aria-label="Dados institucionais" className="flex flex-wrap gap-1 border-b border-[#E4E7EC]">
                {resources.map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    type="button"
                    role="tab"
                    aria-selected={active === id}
                    onClick={() => { setActive(id); setOffset(0); }}
                    className={
                      "inline-flex h-10 items-center gap-2 border-b-2 px-3 text-[12px] font-medium transition " +
                      (active === id
                        ? "border-[#266DF0] text-[#266DF0]"
                        : "border-transparent text-[#667085] hover:text-[#344054]")
                    }
                  >
                    <Icon className="h-3.5 w-3.5" /> {label}
                  </button>
                ))}
              </div>
              {active === "fees" && (
                <p className="mt-4 rounded-lg border border-[#FEDF89] bg-[#FFFAEB] px-3 py-2.5 text-[11px] leading-5 text-[#93370D]">
                  Valores são snapshots não conciliados do sistema de origem.
                  Não representam confirmação de pagamento, cobrança autorizada ou quitação.
                </p>
              )}
              <div className="mt-4">
                {data.isLoading && <p className="py-5 text-[12px] text-[#667085]">Buscando registros autorizados…</p>}
                {data.isError && (
                  <div className="flex flex-wrap items-center gap-2 rounded-lg bg-[#F9FAFB] p-4">
                    <p className="flex-1 text-[12px] text-[#667085]">Não foi possível consultar esta categoria agora.</p>
                    <button type="button" onClick={() => void data.refetch()} className="inline-flex items-center gap-1 text-[12px] font-semibold text-[#266DF0]">
                      <RefreshCw className="h-3.5 w-3.5" /> Tentar novamente
                    </button>
                  </div>
                )}
                {data.isSuccess && data.data.items.length === 0 && (
                  <p className="rounded-lg bg-[#F9FAFB] p-5 text-[12px] text-[#667085]">
                    Nenhum registro encontrado nesta categoria para o aluno.
                  </p>
                )}
                {data.isSuccess && data.data.items.length > 0 && (
                  <ul className="divide-y divide-[#EAECF0] rounded-lg border border-[#EAECF0]">
                    {data.data.items.map((row, index) => (
                      <li key={String(row.name ?? "") + "-" + index} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
                        <span className="min-w-0 text-[12px] font-semibold text-[#344054]">{recordLabel(row, active)}</span>
                        <span className="text-[12px] text-[#667085]">{recordDetails(row, active)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {data.isSuccess && (offset > 0 || data.data.has_more) && (
                <div className="mt-4 flex items-center justify-between gap-3">
                  <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}
                    className="text-[12px] font-medium text-[#266DF0] disabled:opacity-30">Anterior</button>
                  <span className="text-[11px] text-[#667085]">Registros {offset + 1}–{offset + data.data.items.length}</span>
                  <button type="button" disabled={!data.data.has_more} onClick={() => setOffset(offset + 30)}
                    className="text-[12px] font-medium text-[#266DF0] disabled:opacity-30">Próximo</button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
