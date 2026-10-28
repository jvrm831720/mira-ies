"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, ArrowDownRight, ArrowRight, ArrowUpRight, CalendarDays, RefreshCw, TrendingUp, Users, Info } from "lucide-react";
import { Header } from "@/components/layout/header";
import { Skeleton } from "@/components/ui/skeleton";
import { RiskBadge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import type { RiskHistoryAssessment, RiskHistoryResponse, RiskMovement } from "@/types/api";
import { cn } from "@/lib/utils";

type Period = "30" | "90" | "180" | "365";
const CHANGE_LABEL: Record<RiskMovement["change_type"], string> = {
  risco_aumentou: "Risco aumentou", risco_diminuiu: "Risco diminuiu",
  sem_mudanca_relevante: "Sem mudança", sem_historico_comparavel: "Sem histórico comparável",
  mudanca_modelo: "Mudança de modelo",
};

function ScoreTimeline({ data }: { data: RiskHistoryResponse["timeline"] }) {
  const buckets = [...new Set(data.map((p) => p.bucket))].sort();
  const series = [...new Set(data.map((p) => p.model_scope + " · " + p.model_version + " · " + p.score_semantics_version))];
  if (!data.length || !buckets.length) return <div className="grid min-h-[220px] place-items-center rounded-lg bg-[#F8FAFC] px-5 text-center text-[13px] text-[#667085]">Ainda não há avaliações históricas suficientes. Novas avaliações aparecerão aqui depois de executadas.</div>;
  const x = (bucket: string) => 54 + (buckets.length <= 1 ? 0 : buckets.indexOf(bucket) * 790 / (buckets.length - 1));
  const y = (score: number) => 210 - (Math.max(0, Math.min(100, score)) * 1.75);
  const colors = ["#2563EB", "#7F56D9", "#039855", "#D92D20"];
  return <div>
    <div className="overflow-x-auto"><svg viewBox="0 0 900 250" role="img" aria-label="Evolução da média dos scores por semana e versão do modelo" className="min-w-[640px] w-full">
      {[0,25,50,75,100].map((tick) => <g key={tick}><line x1="54" x2="844" y1={y(tick)} y2={y(tick)} stroke="#EAECF0" strokeDasharray="3 4" /><text x="42" y={y(tick)+4} fontSize="11" textAnchor="end" fill="#667085">{tick}</text></g>)}
      {buckets.map((bucket) => <text key={bucket} x={x(bucket)} y="236" fontSize="10" textAnchor="middle" fill="#667085">{dateLabel(bucket)}</text>)}
      {series.map((key, index) => { const points = data.filter((p) => p.model_scope + " · " + p.model_version + " · " + p.score_semantics_version === key).sort((a,b) => a.bucket.localeCompare(b.bucket)); const color = colors[index % colors.length]; return <g key={key}>
        {points.slice(1).map((point, i) => { const prev = points[i]; if (new Date(point.bucket).getTime() - new Date(prev.bucket).getTime() > 8 * 86400000) return null; return <line key={prev.bucket + point.bucket} x1={x(prev.bucket)} y1={y(prev.average_score)} x2={x(point.bucket)} y2={y(point.average_score)} stroke={color} strokeWidth="2.5" strokeLinecap="round" />; })}
        {points.map((point) => <circle key={point.bucket} cx={x(point.bucket)} cy={y(point.average_score)} r="4" fill={color}><title>{dateLabel(point.bucket) + " · média " + scoreLabel(point.average_score) + " · " + point.students_count + " alunos · " + point.model_scope + " v" + point.model_version + " · " + point.score_semantics_version}</title></circle>)}
      </g>; })}
    </svg></div>
    <div className="mt-2 flex flex-wrap gap-3">{series.map((key,i) => <span key={key} className="inline-flex items-center gap-2 text-[11px] text-[#475467]"><span className="h-2.5 w-2.5 rounded-full" style={{backgroundColor:colors[i % colors.length]}} />{key}</span>)}</div>
    <p className="mt-3 text-[11px] leading-relaxed text-[#667085]">Cada ponto representa a média do score da última avaliação de cada aluno naquela semana, agrupada por escopo, versão e semântica do score. Séries incompatíveis ficam separadas; lacunas superiores a uma semana não são conectadas.</p>
  </div>;
}

function DistributionTimeline({ data }: { data: RiskHistoryResponse["timeline"] }) {
  const rows = [...data].sort((a, b) =>
    a.bucket.localeCompare(b.bucket)
    || a.model_scope.localeCompare(b.model_scope)
    || a.model_version.localeCompare(b.model_version)
    || a.score_semantics_version.localeCompare(b.score_semantics_version)
  ).slice(-12);
  if (!rows.length) return <p className="rounded-lg bg-[#F8FAFC] p-4 text-[13px] text-[#667085]">A distribuição histórica será exibida quando houver avaliações no período.</p>;
  return <div className="space-y-3">{rows.map((point) => {
    const distribution = point.risk_distribution;
    const total = distribution.baixo + distribution.medio + distribution.critico;
    const label = dateLabel(point.bucket) + " · " + point.model_scope + " v" + point.model_version;
    return <div key={point.bucket + point.model_scope + point.model_version + point.score_semantics_version}>
      <div className="mb-1.5 flex items-center justify-between gap-2 text-[10px] text-[#667085]"><span>{label}</span><span>{point.students_count} alunos</span></div>
      <div className="flex h-3 overflow-hidden rounded-full bg-[#F2F4F7]" title={distribution.critico + " críticos, " + distribution.medio + " médios, " + distribution.baixo + " baixos"}>
        {total > 0 && <><div className="bg-[#12B76A]" style={{width:(distribution.baixo/total*100)+"%"}}/><div className="bg-[#F79009]" style={{width:(distribution.medio/total*100)+"%"}}/><div className="bg-[#F04438]" style={{width:(distribution.critico/total*100)+"%"}}/></>}
      </div>
      <p className="mt-1 text-[9px] text-[#98A2B3]">{point.score_semantics_version}</p>
    </div>;
  })}</div>;
}

function StudentAssessmentTimeline({ assessments }: { assessments: RiskHistoryAssessment[] }) {
  const points = [...assessments].sort((a, b) => a.evaluated_at.localeCompare(b.evaluated_at));
  if (!points.length) return null;
  const width = 820, height = 190, left = 42, right = 18, top = 14, bottom = 32;
  const x = (index: number) => left + (points.length <= 1 ? (width-left-right)/2 : index*(width-left-right)/(points.length-1));
  const y = (score: number) => top + (100-score)*(height-top-bottom)/100;
  return <div className="mb-5 rounded-lg border border-[#EAECF0] p-3">
    <h3 className="mb-2 text-[12px] font-semibold text-[#344054]">Trajetória temporal do score</h3>
    <div className="overflow-x-auto"><svg viewBox={"0 0 "+width+" "+height} role="img" aria-label="Trajetória individual do score de risco" className="min-w-[600px] w-full">
      {[0,25,50,75,100].map(tick=><g key={tick}><line x1={left} x2={width-right} y1={y(tick)} y2={y(tick)} stroke="#EAECF0" strokeDasharray="3 4"/><text x={left-8} y={y(tick)+4} fontSize="10" textAnchor="end" fill="#667085">{tick}</text></g>)}
      {points.map((point,index)=>{
        const previous=points[index-1];
        const compatible=Boolean(previous && point.model_version && previous.model_version
          && point.model_version===previous.model_version
          && point.model_scope===previous.model_scope
          && point.score_semantics_version===previous.score_semantics_version
          && point.score_basis===previous.score_basis);
        const gap=previous ? new Date(point.evaluated_at).getTime()-new Date(previous.evaluated_at).getTime() : 0;
        const connect=compatible && gap<=45*86400000;
        return <g key={point.id}>
          {connect&&previous&&<line x1={x(index-1)} y1={y(previous.score)} x2={x(index)} y2={y(point.score)} stroke="#2563EB" strokeWidth="2.5"/>}
          <circle cx={x(index)} cy={y(point.score)} r="4" fill="#FFFFFF" stroke="#2563EB" strokeWidth="2"><title>{dateTimeLabel(point.evaluated_at)+" · score "+scoreLabel(point.score)+" · "+point.risk_level+" · "+(point.model_version||"versão não identificada")}</title></circle>
          <text x={x(index)} y={height-10} fontSize="9" textAnchor="middle" fill="#667085">{dateLabel(point.evaluated_at)}</text>
        </g>;
      })}
    </svg></div>
    <p className="mt-1 text-[10px] text-[#667085]">A linha é interrompida entre modelos/semânticas incompatíveis ou lacunas superiores a 45 dias. Avaliações legadas usam score ajustado sem ajuste dinâmico.</p>
  </div>;
}

export default function MonitoramentoPage() {
  const [period,setPeriod] = useState<Period>("90");
  const [course,setCourse] = useState("");
  const [riskLevel,setRiskLevel] = useState("");
  const [selectedStudentId,setSelectedStudentId] = useState<string|null>(null);
  const [to,setTo] = useState(()=>new Date().toISOString());
  const from = useMemo(()=>new Date(new Date(to).getTime()-Number(period)*86400000).toISOString(),[period,to]);
  const historyQuery = useQuery({queryKey:["risk-history",period,course,riskLevel,from,to],queryFn:()=>api.riskHistory({from,to,course:course||undefined,risk_level:riskLevel||undefined,page:1,page_size:50}),retry:false});
  const selectedHistoryQuery = useQuery({queryKey:["student-risk-history",selectedStudentId,from,to],queryFn:()=>api.studentRiskHistory(selectedStudentId!,{from,to,page:1,page_size:200}),enabled:Boolean(selectedStudentId),retry:false});
  const data = historyQuery.data;
  const courseOptions = data?.courses ?? [];
  const refresh = ()=>setTo(new Date().toISOString());
  const counts = data?.comparison_counts;
  const movements = data?.movements ?? [];

  return <>
    <Header title="Monitoramento de risco" compact />
    <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 pb-10 pt-5 md:px-8 md:pt-6 xl:px-10">
      <section className="flex flex-col gap-4 border-b border-[#E5E7EB] pb-5 lg:flex-row lg:items-end lg:justify-between"><div><div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#2563EB]"><Activity className="h-3.5 w-3.5"/>Inteligência temporal</div><h1 className="text-[24px] font-semibold tracking-[-0.035em] text-[#101828]">Monitoramento de risco</h1><p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-[#667085]">Veja o que mudou entre avaliações reais, quanto o score variou e quais movimentações merecem revisão.</p></div>
        <div className="flex flex-wrap items-center gap-2"><label className="sr-only" htmlFor="risk-period">Período</label><select id="risk-period" value={period} onChange={(e)=>setPeriod(e.target.value as Period)} className="h-10 rounded-lg border border-[#D0D5DD] bg-white px-3 text-[12px] font-medium text-[#344054]"><option value="30">Últimos 30 dias</option><option value="90">Últimos 90 dias</option><option value="180">Últimos 180 dias</option><option value="365">Últimos 365 dias</option></select><button type="button" onClick={refresh} disabled={historyQuery.isFetching} className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#D0D5DD] bg-white px-3 text-[12px] font-medium text-[#344054] hover:bg-[#F9FAFB] disabled:opacity-60"><RefreshCw className={cn("h-3.5 w-3.5",historyQuery.isFetching&&"animate-spin")}/>Atualizar</button><Link href="/alunos" className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#2563EB] px-3.5 text-[12px] font-semibold text-white hover:bg-[#1D4ED8]">Lista de alunos<ArrowRight className="h-3.5 w-3.5"/></Link></div>
      </section>
      <section className="flex flex-wrap items-end gap-3 rounded-xl border border-[#E5E7EB] bg-white p-4"><label className="flex min-w-[180px] flex-1 flex-col gap-1.5 text-[11px] font-medium text-[#475467]">Curso<select value={course} onChange={(e)=>setCourse(e.target.value)} className="h-9 rounded-lg border border-[#D0D5DD] bg-white px-2.5 text-[12px] text-[#344054]"><option value="">Todos os cursos</option>{courseOptions.map(v=><option key={v} value={v}>{v}</option>)}</select></label><label className="flex min-w-[180px] flex-1 flex-col gap-1.5 text-[11px] font-medium text-[#475467]">Classificação<select value={riskLevel} onChange={(e)=>setRiskLevel(e.target.value)} className="h-9 rounded-lg border border-[#D0D5DD] bg-white px-2.5 text-[12px] text-[#344054]"><option value="">Todos os níveis</option><option value="critico">Crítico</option><option value="medio">Moderado</option><option value="baixo">Baixo</option></select></label><div className="flex items-center gap-2 pb-2 text-[11px] text-[#667085]"><CalendarDays className="h-3.5 w-3.5"/>{data?dateLabel(data.period.from)+" – "+dateLabel(data.period.to):"Últimos "+period+" dias"} · avaliações reais</div></section>
      {historyQuery.isError&&<div role="alert" className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-5"><p className="text-[13px] font-semibold text-[#B42318]">Não foi possível carregar o histórico de risco.</p><p className="mt-1 text-[12px] text-[#667085]">A API pode ainda não estar implantada. Tente novamente após a atualização do backend.</p><button onClick={refresh} className="mt-3 text-[12px] font-semibold text-[#B42318] underline">Tentar novamente</button></div>}
      {historyQuery.isLoading?<div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[1,2,3,4].map(n=><Skeleton key={n} className="h-28 rounded-xl"/>)}</div>:data&&<>
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5"><Metric label="Avaliações registradas" value={data.total_assessments} hint="Eventos no período; um aluno pode ter vários" icon={<Activity className="h-4 w-4"/>}/><Metric label="Risco aumentou" value={counts?.increased??0} hint="Delta positivo, mesma versão e escopo" icon={<ArrowUpRight className="h-4 w-4"/>} tone="danger"/><Metric label="Risco diminuiu" value={counts?.decreased??0} hint="Delta negativo, mesma versão e escopo" icon={<ArrowDownRight className="h-4 w-4"/>} tone="success"/><Metric label="Mudança de classificação" value={counts?.classification_changed??0} hint="Transição confirmada entre níveis, modelo comparável" icon={<TrendingUp className="h-4 w-4"/>}/><Metric label="Sem histórico comparável" value={(counts?.no_comparable_history??0)+(counts?.model_changed??0)} hint="Sem avaliação anterior ou versão incompatível" icon={<Users className="h-4 w-4"/>}/></section>
        {data.temporal_data_truncated&&<p className="rounded-lg border border-[#FEDF89] bg-[#FFFAEB] p-3 text-[12px] text-[#B54708]">Série temporal limitada aos 5.000 registros mais recentes. O total é completo, mas gráfico e movimentações podem estar parciais.</p>}
        <section className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.85fr)]"><div className="rounded-xl border border-[#E5E7EB] bg-white p-5"><div className="mb-4 flex items-start justify-between gap-3"><div><h2 className="text-[14px] font-semibold text-[#101828]">Evolução dos scores</h2><p className="mt-1 text-[11px] text-[#667085]">Média semanal das últimas avaliações por aluno, separada por versão do modelo</p></div><TrendingUp className="h-4 w-4 text-[#2563EB]"/></div><ScoreTimeline data={data.timeline}/></div><div className="rounded-xl border border-[#E5E7EB] bg-white p-5"><div className="mb-4"><h2 className="text-[14px] font-semibold text-[#101828]">Distribuição histórica</h2><p className="mt-1 text-[11px] text-[#667085]">Uma avaliação representativa por aluno em cada semana</p></div><div className="mb-3 flex flex-wrap gap-3 text-[10px] text-[#667085]"><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-[#12B76A]"/>Baixo</span><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-[#F79009]"/>Moderado</span><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-[#F04438]"/>Crítico</span></div><DistributionTimeline data={data.timeline}/></div></section>
        <section className="overflow-hidden rounded-xl border border-[#E5E7EB] bg-white"><div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#EAECF0] p-5"><div><h2 className="text-[14px] font-semibold text-[#101828]">Movimentações de risco</h2><p className="mt-1 text-[11px] text-[#667085]">Última avaliação no período comparada à última anterior. Aumento não prova evasão nem causalidade.</p></div><span className="rounded-full bg-[#F2F4F7] px-2.5 py-1 text-[10px] font-medium text-[#475467]">{movements.length} casos</span></div>
          {movements.length===0?<div className="p-10 text-center"><div className="mx-auto grid h-10 w-10 place-items-center rounded-xl bg-[#F8FAFC] text-[#667085]"><Info className="h-5 w-5"/></div><p className="mt-3 text-[13px] font-semibold text-[#344054]">Nenhuma movimentação para este período</p><p className="mt-1 text-[12px] text-[#667085]">Pode não haver avaliações históricas. Isso não significa que o risco ficou estável.</p></div>:<div className="overflow-x-auto"><table className="w-full min-w-[860px] text-left"><thead className="bg-[#F9FAFB] text-[10px] font-semibold uppercase tracking-[0.05em] text-[#667085]"><tr><th className="px-5 py-3">Aluno</th><th className="px-3 py-3">Anterior</th><th className="px-3 py-3">Atual</th><th className="px-3 py-3">Variação</th><th className="px-3 py-3">Movimento</th><th className="px-5 py-3">Última avaliação</th></tr></thead><tbody className="divide-y divide-[#EAECF0]">{movements.map(m=><tr key={m.student_id} className="hover:bg-[#F9FAFB]"><td className="px-5 py-3.5"><button onClick={()=>setSelectedStudentId(m.student_id)} className="text-left text-[12px] font-semibold text-[#175CD3] hover:underline">{m.student_name||m.matricula||"Aluno"}</button><p className="mt-0.5 text-[10px] text-[#667085]">{m.course||"Curso não informado"} · {m.matricula||"—"}</p></td><td className="px-3 py-3.5 text-[12px] text-[#475467]">{scoreLabel(m.previous_score)}{m.previous_risk_level&&<div className="mt-1"><RiskBadge level={m.previous_risk_level}/></div>}</td><td className="px-3 py-3.5 text-[12px] font-semibold text-[#101828]">{scoreLabel(m.current_score)}<div className="mt-1"><RiskBadge level={m.current_risk_level}/></div></td><td className="px-3 py-3.5 text-[12px] font-semibold">{m.delta==null?"—":(m.delta>0?"+":"")+scoreLabel(m.delta)}</td><td className="px-3 py-3.5"><span className={cn("inline-flex rounded-full px-2 py-1 text-[10px] font-medium",movementTone(m.change_type))}>{CHANGE_LABEL[m.change_type]}</span></td><td className="px-5 py-3.5 text-[11px] text-[#667085]">{dateTimeLabel(m.current_evaluated_at)}<div className="mt-1 text-[10px]">Modelo {m.model_version||"não identificado"}</div><Link href={"/alunos/"+m.student_id} className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold text-[#175CD3]">Ficha do aluno<ArrowRight className="h-3 w-3"/></Link></td></tr>)}</tbody></table></div>}
          {data.movements_truncated&&<p className="border-t border-[#EAECF0] px-5 py-3 text-[11px] text-[#B54708]">Exibindo os 500 primeiros casos por prioridade; refine os filtros.</p>}
        </section>
        {selectedStudentId&&<section className="rounded-xl border border-[#B2CCFF] bg-white p-5"><div className="flex items-start justify-between gap-3"><div><h2 className="text-[14px] font-semibold text-[#101828]">Trajetória individual</h2><p className="mt-1 text-[11px] text-[#667085]">{selectedHistoryQuery.data?.student.name||"Carregando aluno"} · avaliações e intervenções registradas</p></div><button onClick={()=>setSelectedStudentId(null)} className="text-[11px] font-semibold text-[#475467] underline">Fechar</button></div>
          {selectedHistoryQuery.isLoading?<Skeleton className="mt-4 h-20 rounded-lg"/>:selectedHistoryQuery.isError?<p className="mt-4 text-[12px] text-[#B42318]">Não foi possível consultar esta trajetória.</p>:selectedHistoryQuery.data&&<><StudentAssessmentTimeline assessments={selectedHistoryQuery.data.assessments}/><div className="mt-4 grid gap-4 lg:grid-cols-2"><div><h3 className="mb-2 text-[12px] font-semibold text-[#344054]">Avaliações preservadas</h3>{selectedHistoryQuery.data.assessments.length?<div className="space-y-2">{selectedHistoryQuery.data.assessments.map(a=><div key={a.id} className="rounded-lg border border-[#EAECF0] p-3"><div className="flex items-center justify-between gap-3"><span className="text-[11px] text-[#667085]">{dateTimeLabel(a.evaluated_at)}</span><span className="text-[13px] font-semibold text-[#101828]">{scoreLabel(a.score)}</span></div><div className="mt-1 flex flex-wrap items-center gap-2"><RiskBadge level={a.risk_level}/><span className="text-[10px] text-[#667085]">Modelo {a.model_version||"não identificado"} · {a.model_scope} · {a.score_semantics_version}</span>{a.score_basis==="legacy_adjusted"&&<span className="text-[9px] text-[#B54708]">Score histórico sem ajuste dinâmico</span>}</div>{a.explanation_available&&a.explanation?.top_factors?.length?<ul className="mt-2 list-disc pl-4 text-[11px] text-[#475467]">{a.explanation.top_factors.map((f,i)=><li key={a.id+"-"+i}>{f.label||f.feature||"Fator"}{f.value!=null?": "+f.value:""}</li>)}</ul>:<p className="mt-2 text-[10px] text-[#667085]">Fatores explicativos não foram preservados nesta avaliação.</p>}</div>)}</div>:<p className="rounded-lg bg-[#F8FAFC] p-3 text-[12px] text-[#667085]">Nenhuma avaliação histórica no período. A consulta não gera novos scores.</p>}</div>
            <div><h3 className="mb-2 text-[12px] font-semibold text-[#344054]">Intervenções e desfechos registrados</h3>{selectedHistoryQuery.data.interventions.length?<div className="space-y-2">{selectedHistoryQuery.data.interventions.map(i=><div key={i.id} className="rounded-lg border border-[#EAECF0] p-3"><div className="flex items-center justify-between gap-2"><span className="text-[11px] font-medium text-[#344054]">{i.channel||"Canal não informado"} · {i.status}</span><span className="text-[10px] text-[#667085]">{dateTimeLabel(i.created_at)}</span></div><p className="mt-1 text-[11px] text-[#667085]">{i.decision_reason||"Sem justificativa registrada"}</p><p className="mt-1 text-[10px] text-[#475467]">Desfecho: {i.outcome||"Ainda não registrado"}{i.outcome_at?" · "+dateTimeLabel(i.outcome_at):""}</p></div>)}</div>:<p className="rounded-lg bg-[#F8FAFC] p-3 text-[12px] text-[#667085]">Nenhuma intervenção registrada neste período.</p>}<p className="mt-3 text-[10px] leading-relaxed text-[#667085]">Proximidade temporal não demonstra causalidade. Permanência, evasão e recuperação financeira dependem dos desfechos próprios.</p></div>
          </div></>}</section>
        <p className="text-[10px] leading-relaxed text-[#667085]">Base: avaliações registradas entre {dateTimeLabel(data.period.from)} e {dateTimeLabel(data.period.to)}. Ausência de histórico não equivale a score zero. {data.definition}</p>
      </>}
    </main>
  </>;
}

function Metric({label,value,hint,icon,tone="neutral"}:{label:string;value:number;hint:string;icon:React.ReactNode;tone?:"neutral"|"danger"|"success"}) {
  const toneClass=tone==="danger"?"text-[#B42318] bg-[#FEF3F2]":tone==="success"?"text-[#027A48] bg-[#ECFDF3]":"text-[#344054] bg-[#F2F4F7]";
  return <div className="rounded-xl border border-[#E5E7EB] bg-white p-4"><div className="flex items-center justify-between gap-3"><span className="text-[11px] font-medium text-[#667085]">{label}</span><span className={cn("grid h-8 w-8 place-items-center rounded-lg",toneClass)}>{icon}</span></div><p className="mt-3 text-[25px] font-semibold tracking-[-0.04em] text-[#101828]">{value.toLocaleString("pt-BR")}</p><p className="mt-1 text-[10px] leading-relaxed text-[#667085]">{hint}</p></div>;
}
