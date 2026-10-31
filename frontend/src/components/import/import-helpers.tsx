"use client";

import type { ImportField } from "@/types/api";

export const IMPORT_FIELDS: ImportField[] = [
  "matricula",
  "nome",
  "curso",
  "campus",
  "status_aluno",
  "turma",
  "semestre",
  "forma_ingresso",
  "dias_atraso_boleto",
  "recorrencia_atrasos",
  "saldo_devedor",
  "status_financeiro",
  "dias_sem_login",
  "presenca_percentual",
  "nota_media",
  "reprovacoes",
  "telefone",
  "email",
  "communication_opt_out",
];

export const TEMPLATE_CSV = [
  "matricula,nome,email,telefone,curso,turma,semestre,forma_ingresso,dias_atraso_boleto,recorrencia_atrasos,dias_sem_login,presenca_percentual,nota_media,reprovacoes,communication_opt_out",
  "2024001,Ana Souza,ana@example.edu.br,11999990001,Enfermagem,A,2,Transferência,0,0,1,96,8.7,0,false",
  "2024002,Bruno Lima,bruno@example.edu.br,11999990002,Administração,B,4,Ingresso regular,18,2,12,78,6.4,1,false",
].join("\n");

export const FIELD_LABELS: Record<ImportField, string> = {
  matricula: "Matrícula",
  nome: "Nome completo",
  curso: "Curso",
  campus: "Unidade / Campus",
  status_aluno: "Status do aluno",
  turma: "Turma",
  semestre: "Semestre",
  forma_ingresso: "Forma de ingresso",
  dias_atraso_boleto: "Dias de atraso financeiro",
  recorrencia_atrasos: "Parcelas vencidas / recorrência",
  saldo_devedor: "Saldo devedor (R$)",
  status_financeiro: "Status financeiro",
  dias_sem_login: "Dias sem login",
  presenca_percentual: "Presença (%)",
  nota_media: "Nota média",
  reprovacoes: "Reprovações",
  telefone: "Telefone",
  email: "E-mail",
  communication_opt_out: "Não contatar",
};

export const IMPORT_STEPS = [
  { id: "upload", label: "Enviar" },
  { id: "analyze", label: "Analisar" },
  { id: "map", label: "Mapear" },
  { id: "quality", label: "Qualidade" },
  { id: "confirm", label: "Confirmar" },
  { id: "result", label: "Resultado" },
];

export function formatCount(value?: number | null) {
  return (value ?? 0).toLocaleString("pt-BR");
}

export function downloadImportTemplate() {
  const csv = "\uFEFF" + TEMPLATE_CSV + "\n";
  const url = `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
  const link = document.createElement("a");
  link.href = url;
  link.download = "modelo-importacao-mira.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export function isSupportedImportFile(file: File) {
  return ["csv", "xlsx", "xls"].includes(file.name.split(".").pop()?.toLowerCase() || "");
}

export function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ImportStat({ label, value }: { label: string; value?: number | null }) {
  return (
    <div className="rounded-xl border border-border bg-white p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tracking-tight tabular-nums">
        {value == null ? "—" : formatCount(value)}
      </p>
    </div>
  );
}

export function ImportNotice({
  tone,
  title,
  text,
}: {
  tone: "error" | "warning" | "info";
  title: string;
  text: string;
}) {
  const styles = {
    error: "border-red-200 bg-red-50 text-red-900",
    warning: "border-amber-200 bg-amber-50 text-amber-950",
    info: "border-blue-200 bg-blue-50 text-blue-950",
  };
  return (
    <div className={`rounded-xl border px-3.5 py-3 ${styles[tone]}`}>
      <p className="text-sm font-semibold">{title}</p>
      <p className="mt-1 text-xs leading-relaxed opacity-80">{text}</p>
    </div>
  );
}
