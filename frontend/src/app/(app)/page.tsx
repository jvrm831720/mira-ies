"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  GraduationCap,
  Info,
  MessageSquareHeart,
  Plug,
  Search,
  Upload,
  Users,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { KpiCards } from "@/components/risk/kpi-cards";
import { CriticalList } from "@/components/risk/critical-list";
import { RiskDistribution } from "@/components/risk/risk-distribution";
import { StudentDrawer } from "@/components/students/student-drawer";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import { copy } from "@/lib/copy";

const quickActions = [
  { href: "/importar", label: "Importar dados", icon: Upload },
  { href: "/alunos", label: "Alunos", icon: Users },
  { href: "/retencao", label: "Retenção", icon: MessageSquareHeart },
  { href: "/conectores", label: "Conectores", icon: Plug },
];

export default function CommandCenterPage() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const summary = useQuery({ queryKey: ["risk-summary"], queryFn: () => api.riskSummary() });
  const critical = useQuery({ queryKey: ["risk-critical"], queryFn: () => api.riskCritical(10) });
  const model = useQuery({ queryKey: ["model-info"], queryFn: () => api.modelInfo(), retry: false });
  const students = useQuery({
    queryKey: ["students-home"],
    queryFn: () => api.students({ limit: 80 }),
    retry: false,
  });

  const total =
    summary.data?.total_scored ??
    (summary.data?.summary
      ? summary.data.summary.baixo + summary.data.summary.medio + summary.data.summary.critico
      : 0);
  const criticalCount = summary.data?.summary.critico ?? 0;
  const priorityRate = total ? Math.round((criticalCount / total) * 100) : 0;
  const isEmpty = !summary.isLoading && !summary.isError && total === 0;

  const searchHits = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (term.length < 2) return [];
    return (students.data?.students ?? [])
      .filter(
        (s) =>
          s.nome?.toLowerCase().includes(term) ||
          s.matricula?.toLowerCase().includes(term) ||
          s.curso?.toLowerCase().includes(term)
      )
      .slice(0, 6);
  }, [q, students.data]);

  function onSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    const term = q.trim();
    if (!term) return;
    if (searchHits.length === 1) {
      setSelectedId(searchHits[0].id);
      return;
    }
    router.push(`/alunos?q=${encodeURIComponent(term)}`);
  }

  return (
    <>
      <Header title="Página inicial" subtitle="Priorize risco e acompanhe a permanência estudantil." />
      <main className="mx-auto w-full max-w-[1100px] space-y-6 px-4 pb-10 pt-5 md:px-9 md:pt-6">
        <form onSubmit={onSearchSubmit} className="relative">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Busque aluno por nome, matrícula ou curso"
            className="h-12 w-full rounded-full border border-neutral-200 bg-white pl-11 pr-4 text-sm text-neutral-900 shadow-sm outline-none transition placeholder:text-neutral-400 focus:border-neutral-300 focus:ring-2 focus:ring-neutral-900/10"
          />
          {searchHits.length > 0 && (
            <ul className="absolute left-0 right-0 top-[calc(100%+6px)] z-10 overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-xl">
              {searchHits.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-sm hover:bg-neutral-50"
                    onClick={() => {
                      setSelectedId(s.id);
                      setQ("");
                    }}
                  >
                    <span className="font-medium text-neutral-900">{s.nome}</span>
                    <span className="text-xs text-neutral-500">
                      {s.matricula}
                      {s.risk_level ? ` · ${s.risk_level}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </form>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {quickActions.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className="flex flex-col items-center justify-center gap-2 rounded-[20px] border border-neutral-200 bg-white px-3 py-4 text-center transition hover:border-neutral-300 hover:shadow-sm"
            >
              <span className="grid h-10 w-10 place-items-center rounded-full bg-neutral-100 text-neutral-900">
                <Icon className="h-[18px] w-[18px]" />
              </span>
              <span className="text-[12px] font-semibold text-neutral-800">{label}</span>
            </Link>
          ))}
        </div>

        <section className="flex flex-col gap-4 rounded-[20px] border border-neutral-200 bg-white px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="min-w-0">
            <p className="text-[11px] font-medium tracking-wide text-neutral-400">
              Mira · permanência estudantil
            </p>
            <p className="mt-1 text-[15px] font-semibold leading-snug tracking-[-0.02em] text-neutral-900 sm:text-base">
              {isEmpty
                ? "Importe a base para ver quem precisa de atenção."
                : `${criticalCount.toLocaleString("pt-BR")} alunos em risco crítico · ${priorityRate}% da base`}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Link
              href="/importar"
              className="inline-flex h-9 items-center gap-1.5 rounded-full bg-neutral-950 px-3.5 text-[12px] font-medium text-white hover:bg-neutral-800"
            >
              <Upload className="h-3.5 w-3.5" /> Importar
            </Link>
            <Link
              href="/retencao"
              className="inline-flex h-9 items-center gap-1.5 rounded-full border border-neutral-200 bg-white px-3.5 text-[12px] font-medium text-neutral-800 hover:bg-neutral-50"
            >
              Retenção
            </Link>
          </div>
        </section>

        {summary.isError && (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-medium">Não foi possível carregar o resumo agora.</p>
              <p className="mt-0.5 text-xs text-red-700/80">Confira o backend e atualize a página.</p>
            </div>
          </div>
        )}

        {isEmpty && (
          <section className="rounded-[20px] border border-dashed border-neutral-200 bg-white px-5 py-10 text-center">
            <GraduationCap className="mx-auto h-8 w-8 text-neutral-300" />
            <p className="mt-3 text-sm font-semibold text-neutral-900">Ainda não há alunos pontuados</p>
            <p className="mx-auto mt-1 max-w-md text-xs text-neutral-500">
              Importe uma planilha ou sincronize um conector para montar o painel de risco.
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-3">
              <Link href="/importar" className="text-sm font-semibold text-neutral-900 underline-offset-4 hover:underline">
                Importar agora
              </Link>
              <Link href="/conectores" className="text-sm font-semibold text-neutral-900 underline-offset-4 hover:underline">
                Abrir conectores
              </Link>
            </div>
          </section>
        )}

        <section aria-label="Indicadores de risco" className="space-y-3">
          <div className="flex items-end justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-neutral-400">
                Sua base
              </p>
              <h2 className="mt-1 text-base font-semibold tracking-[-0.02em] text-neutral-900">
                Indicadores de risco
              </h2>
            </div>
            <Link
              href="/alunos"
              className="hidden items-center gap-1 text-xs font-medium text-neutral-600 hover:text-neutral-900 sm:flex"
            >
              Ver alunos <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          <KpiCards data={summary.data} loading={summary.isLoading} />
        </section>

        {!isEmpty && (
          <section className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
            <RiskDistribution data={summary.data} loading={summary.isLoading} />
            <CriticalList
              students={critical.data?.students}
              loading={critical.isLoading}
              onSelect={(id) => setSelectedId(id)}
            />
          </section>
        )}

        {(model.data?.disclaimer || model.data?.training_data === "synthetic") && (
          <Card className="border-neutral-200 bg-neutral-50 shadow-none">
            <CardContent className="flex items-start gap-3 p-4 text-xs text-neutral-600">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-neutral-400" />
              <div>
                <p className="font-semibold text-neutral-900">Apoio à decisão da coordenação</p>
                <p className="mt-1 leading-relaxed">
                  {model.data?.disclaimer || copy.modelDisclaimerFallback}
                </p>
              </div>
            </CardContent>
          </Card>
        )}
      </main>

      <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
    </>
  );
}
