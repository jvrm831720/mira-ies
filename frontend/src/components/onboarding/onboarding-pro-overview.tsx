"use client";

import {
  BarChart3, BrainCircuit, CheckCircle2, Database, Sparkles,
  TrendingUp, Workflow,
} from "@/components/ui/icons";

const proCapabilities = [
  { title: "Antecipe riscos", detail: "Monitoramento preditivo", Icon: TrendingUp },
  { title: "Entenda cada aluno", detail: "Sinais e contexto com IA", Icon: BrainCircuit },
  { title: "Transforme análise em ação", detail: "Campanhas e intervenções", Icon: Workflow },
  { title: "Coordene sua equipe", detail: "Central de trabalho", Icon: Database },
  { title: "Acompanhe o impacto", detail: "Resultados da operação", Icon: BarChart3 },
] as const;

export function OnboardingProOverview({
  workspaceName,
  responsibleName,
}: {
  workspaceName: string;
  responsibleName: string;
}) {
  return (
    <div className="mira-flow-ready-stack">
      <section className="mira-flow-ready-summary" aria-labelledby="mira-ready-title">
        <div className="mira-flow-ready-intro">
          <span className="mira-flow-ready-check" aria-hidden="true"><CheckCircle2 size={18} /></span>
          <div>
            <h2 id="mira-ready-title">Tudo pronto para começar</h2>
            <p>Seus dados estão confirmados.</p>
          </div>
        </div>
        <dl className="mira-flow-ready-facts">
          <div>
            <dt>Workspace</dt>
            <dd>{workspaceName}</dd>
          </div>
          <div>
            <dt>Responsável inicial</dt>
            <dd>{responsibleName}</dd>
          </div>
          <div>
            <dt>Integrações</dt>
            <dd>Conectar na próxima etapa</dd>
          </div>
        </dl>
      </section>

      <section className="mira-flow-pro-showcase" aria-labelledby="mira-pro-title">
        <div className="mira-flow-pro-glow" aria-hidden="true" />
        <div className="mira-flow-pro-topline">
          <span className="mira-flow-pro-eyebrow"><Sparkles size={13} aria-hidden="true" /> Conheça a experiência</span>
          <span className="mira-flow-pro-badge">PRO</span>
        </div>
        <div className="mira-flow-pro-heading">
          <p className="mira-flow-pro-brand">MIRA <strong>Pro</strong></p>
          <h2 id="mira-pro-title">Da previsão à ação. Tudo conectado.</h2>
          <p>Uma experiência completa para acompanhar a permanência estudantil com inteligência, contexto e execução.</p>
        </div>
        <p className="mira-flow-pro-includes">O que você encontra no Pro</p>
        <ul className="mira-flow-pro-benefits">
          {proCapabilities.map(({ title, detail, Icon }) => (
            <li key={title}>
              <span className="mira-flow-pro-feature-icon" aria-hidden="true"><Icon size={16} /></span>
              <span>
                <strong>{title}</strong>
                <small>{detail}</small>
              </span>
            </li>
          ))}
        </ul>
        <div className="mira-flow-pro-footnote">
          <CheckCircle2 size={15} aria-hidden="true" />
          <span>Os recursos disponíveis dependem do plano habilitado no workspace.</span>
        </div>
      </section>
      <p className="mira-flow-ready-next">Próximo passo: proteger seu acesso e conectar suas ferramentas.</p>
    </div>
  );
}
