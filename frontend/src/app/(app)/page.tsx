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
      <Header title="Visão geral" subtitle="Comece por quem precisa de atenção hoje." />
      <main className="mx-auto w-full max-w-[1240px] space-y-8 px-4 pb-12 pt-6 md:px-10 md:pt-8">
        <form onSubmit={onSearchSubmit} className="relative max-w-2xl">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-[var(--brand-indigo)]" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Busque aluno por nome, matrícula ou curso"
            className="h-14 w-full rounded-2xl border border-black/[0.08] bg-white pl-12 pr-4 text-sm text-neutral-900 shadow-[0_12px_32px_rgba(31,33,42,0.05)] outline-none transition placeholder:text-neutral-400 focus:border-[var(--brand-indigo)] focus:ring-4 focus:ring-[rgba(64,80,205,0.12)]"
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
              className="group flex min-h-[112px] flex-col items-start justify-between rounded-2xl border border-black/[0.07] bg-white px-4 py-4 text-left transition duration-200 hover:-translate-y-0.5 hover:border-black/15 hover:shadow-[0_14px_32px_rgba(31,33,42,0.08)]"
            >
              <span className="grid h-9 w-9 place-items-center rounded-xl bg-[rgba(64,80,205,0.1)] text-[var(--brand-indigo)] transition group-hover:bg-[var(--brand-indigo)] group-hover:text-white">
                <Icon className="h-[18px] w-[18px]" />
              </span>
              <span><span className="block text-[13px] font-semibold text-neutral-900">{label}</span><span className="mt-0.5 block text-[10px] text-neutral-400">{href === "/importar" ? "Atualize sua base" : href === "/retencao" ? "Aja sobre o risco" : "Explorar agora"}</span></span>
            </Link>
          ))}
        </div>

        <section className="relative overflow-hidden rounded-[24px] bg-[var(--brand-midnight)] px-5 py-5 text-white shadow-[0_18px_50px_rgba(23,25,29,0.14)] sm:px-7 sm:py-6">
          <div className="pointer-events-none absolute -right-10 -top-24 h-64 w-64 rounded-full border-[28px] border-[rgba(64,80,205,0.5)]" />
          <div className="relative min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-white/45">MIRA · painel de decisão</p>
            <p className="mt-2 max-w-xl text-[20px] font-semibold leading-tight tracking-[-0.04em] text-white sm:text-[24px]">
              {isEmpty
                ? "Importe a base para transformar dados em próximos passos."
                : `${criticalCount.toLocaleString("pt-BR")} alunos pedem atenção crítica · ${priorityRate}% da base`}
            </p>
          </div>
          <div className="relative mt-5 flex shrink-0 flex-wrap gap-2 sm:absolute sm:bottom-6 sm:right-7 sm:mt-0">
            <Link
              href="/importar"
              className="inline-flex h-10 items-center gap-1.5 rounded-xl bg-white px-4 text-[12px] font-semibold text-[var(--brand-midnight)] hover:bg-white/90"
            >
              <Upload className="h-3.5 w-3.5" /> Importar
            </Link>
            <Link
              href="/retencao"
              className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-white/15 bg-white/10 px-4 text-[12px] font-semibold text-white hover:bg-white/15"
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
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-neutral-400">Leitura rápida</p>
              <h2 className="mt-1 text-[19px] font-semibold tracking-[-0.04em] text-neutral-950">
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
