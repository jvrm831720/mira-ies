"use client";
import { useMemo, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, Check, ChevronRight, LockKeyhole, ShieldCheck } from "@/components/ui/icons";
import type { CampaignDraft, DispatchCampaign, DispatchSource, DispatchTemplate } from "@/lib/dispatch-api";
import type { CampaignBuilderState } from "./dispatch-types";
import { CHANNEL_LABEL, PURPOSE_LABEL } from "./dispatch-types";
import { eligibleSources, matchingTemplates, permittedPurposes, sourceKey, validChannel, validateCampaignDraft } from "./dispatch-utils";

const STEPS = [
  "Objetivo", "Público e origem", "Canais e mensagem", "Regras", "Revisão",
] as const;
const fieldClass = "mt-1.5 h-9 w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-3 text-xs outline-none focus:border-[var(--color-blue)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]/15";
const labelClass = "block text-[length:var(--type-caption)] font-medium text-[var(--color-slate-600)]";
const buttonClass = "inline-flex h-9 items-center justify-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-3 text-xs font-medium text-[var(--color-ink)] hover:bg-[var(--color-panel)] disabled:opacity-40";
function Notice({children}:{children:ReactNode}) {
  return <div role="note" className="flex items-start gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-3 text-[length:var(--type-caption)] leading-relaxed text-[var(--color-slate-600)]"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />{children}</div>;
}

export function CampaignBuilder({
  sources, templates, profile, busy, onCreate, onCancel,
}: {
  sources: DispatchSource[];
  templates: DispatchTemplate[];
  profile?: string | null;
  busy: boolean;
  onCreate: (payload: CampaignDraft) => Promise<DispatchCampaign>;
  onCancel: () => void;
}) {
  const purposes = useMemo(() => permittedPurposes(profile), [profile]);
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<CampaignBuilderState>({
    name: "", purpose: purposes[0] || "service", mode: "targeted",
    sourceKey: "", channel: "email", templateId: "", perMinute: 10,
  });
  const [tool, setTool] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const availableSources = useMemo(() => eligibleSources(sources), [sources]);
  const source = availableSources.find(item => sourceKey(item) === draft.sourceKey);
  const selectedTemplate = templates.find(item => item.id === draft.templateId);
  const matched = matchingTemplates(templates, draft.purpose, draft.channel);
  const warnings = validateCampaignDraft(draft, sources, templates, profile);
  const sourceTools = source?.kind === "composio" ? source.tools : [];
  const canAdvance = step === 0 ? draft.name.trim().length >= 3 && purposes.includes(draft.purpose)
    : step === 1 ? !!source && (source.kind !== "composio" || !!tool)
    : step === 2 ? !!selectedTemplate && matched.some(item => item.id === selectedTemplate.id)
    : step === 3 ? Number.isInteger(draft.perMinute) && draft.perMinute >= 1 && draft.perMinute <= 120 : true;
  function update(patch: Partial<CampaignBuilderState>) {
    setDraft(current => ({ ...current, ...patch }));
    setConfirmed(false); setError("");
  }
  function next() { if (canAdvance) setStep(i => Math.min(i + 1, STEPS.length - 1)); }
  async function createDraft() {
    if (warnings.length || !confirmed || !source || !selectedTemplate || busy || (source.kind === "composio" && !tool)) return;
    setError("");
    try {
      await onCreate({
        name: draft.name.trim(), purpose: draft.purpose, delivery_mode: draft.mode,
        source_kind: source.kind, source_ref: source.reference,
        source_tool_slug: source.kind === "composio" ? tool : null,
        channel: draft.channel, template_ref: selectedTemplate.id,
        template_body: selectedTemplate.body, per_minute_limit: draft.perMinute,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível criar o rascunho.");
    }
  }
  return <section aria-labelledby="builder-heading" className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white">
    <div className="flex flex-wrap items-start justify-between gap-2 border-b border-[var(--color-border)] px-5 py-4">
      <div><p className="text-[length:var(--type-overline)] font-semibold uppercase tracking-wider text-[var(--color-muted)]">MIRA Operação / Construtor</p>
        <h2 id="builder-heading" className="mt-1 text-[length:var(--type-body-comfort)] font-semibold">Nova campanha operacional</h2>
        <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-slate-600)]">Criação de rascunho. Público, autorização e execução são etapas independentes.</p>
      </div>
      <button type="button" className={buttonClass} onClick={onCancel}>Fechar</button>
    </div>
    <nav aria-label="Etapas da campanha" className="flex overflow-x-auto border-b border-[var(--color-border)] bg-[var(--color-panel)]">
      {STEPS.map((title, index) => <button key={title} type="button"
        disabled={index > step}
        aria-current={step === index ? "step" : undefined}
        className={"flex shrink-0 items-center gap-1.5 border-b-2 px-4 py-3 text-[length:var(--type-caption)] font-medium " +
          (index === step ? "border-[var(--color-blue)] text-[var(--color-blue)]" : "border-transparent text-[var(--color-slate-600)] disabled:opacity-50")}
        onClick={() => setStep(index)}>
        {index < step ? <Check className="h-3.5 w-3.5" /> : <span className="tabular-nums">{index + 1}</span>}{title}
      </button>)}
    </nav>
    <div className="mx-auto max-w-[760px] space-y-5 p-5 md:p-7">
      {step === 0 && <div className="space-y-4">
        <h3 className="text-[length:var(--type-body-compact)] font-semibold">Qual é a finalidade da comunicação?</h3>
        <Notice>As finalidades disponíveis dependem do tipo de workspace. A autorização da finalidade é verificada novamente pelo backend.</Notice>
        <label className={labelClass}>Nome da operação
          <input className={fieldClass} value={draft.name} maxLength={160}
            placeholder="Ex.: Orientação sobre rematrícula — período 2026.2"
            onChange={e => update({ name: e.target.value })} /></label>
        <fieldset><legend className={labelClass}>Finalidade</legend><div className="mt-2 grid gap-2 sm:grid-cols-2">
          {purposes.map(purpose => <label key={purpose} className={"flex cursor-pointer items-center gap-2 rounded-[var(--radius-md)] border px-3 py-3 text-xs " + (draft.purpose === purpose ? "border-[var(--color-blue)] bg-[var(--color-blue-tint)]" : "border-[var(--color-border)]")}>
            <input type="radio" checked={draft.purpose === purpose} onChange={() => update({ purpose, channel: "email", templateId: "" })} />
            {PURPOSE_LABEL[purpose]}
          </label>)}
        </div></fieldset>
        {!purposes.length && <p role="alert" className="text-xs text-[var(--color-red)]">Perfil do workspace indisponível. Não é possível criar a campanha.</p>}
        <fieldset><legend className={labelClass}>Modalidade</legend><div className="mt-2 flex flex-wrap gap-3">
          {(["targeted","bulk"] as const).map(mode => <label key={mode} className="inline-flex items-center gap-2 text-xs">
            <input type="radio" checked={draft.mode===mode} onChange={() => update({ mode })} />
            {mode === "targeted" ? "Segmentada" : "Em escala"}
          </label>)}
        </div></fieldset>
      </div>}
      {step === 1 && <div className="space-y-4">
        <h3 className="text-[length:var(--type-body-compact)] font-semibold">Escolha uma origem autorizada</h3>
        <Notice>O vínculo não importa destinatários nem concede consentimento. A consulta real de elegibilidade acontece no motor após a criação e a associação autorizada dos registros.</Notice>
        {availableSources.length ? <div className="space-y-2">
          {availableSources.map(s => <label key={sourceKey(s)} className={"flex cursor-pointer items-start gap-3 rounded-[var(--radius-md)] border p-3 " + (draft.sourceKey === sourceKey(s) ? "border-[var(--color-blue)] bg-[var(--color-blue-tint)]" : "border-[var(--color-border)]")}>
            <input type="radio" name="dispatch-source" className="mt-1" checked={draft.sourceKey === sourceKey(s)} onChange={() => { update({ sourceKey: sourceKey(s) }); setTool(""); }} />
            <span><span className="block text-xs font-medium">{s.name}</span>
              <span className="mt-0.5 block text-[length:var(--type-caption)] text-[var(--color-muted)]">{s.kind === "manual" ? "Base interna" : s.kind === "native" ? "Conector nativo" : "Conexão Composio"} · {s.note}</span>
            </span>
          </label>)}
        </div> : <p role="alert" className="text-xs text-[var(--color-red)]">Não há origens conectadas e elegíveis para preparar a campanha. Conecte uma origem na área Dados.</p>}
        {source?.kind === "composio" && <label className={labelClass}>Ferramenta autorizada para esta origem
          <select className={fieldClass} value={tool} onChange={e => setTool(e.target.value)}>
            <option value="">Selecione uma ferramenta disponível</option>
            {sourceTools.map(key => <option value={key} key={key}>{key}</option>)}
          </select></label>}
        <div className="grid grid-cols-2 gap-3 text-[length:var(--type-caption)] text-[var(--color-slate-600)]">
          {["Identificados","Elegíveis","Bloqueados","Sem dados suficientes"].map(label =>
            <div key={label} className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-3 py-2">
              {label}<p className="mt-1 font-medium text-[var(--color-ink)]">A verificar</p>
            </div>)}
        </div>
      </div>}
      {step === 2 && <div className="space-y-4">
        <h3 className="text-[length:var(--type-body-compact)] font-semibold">Canal e mensagem aprovada</h3>
        <Notice>Somente modelos já aprovados aparecem abaixo. Selecionar um canal não significa que o provedor foi homologado ou que o disparo está autorizado.</Notice>
        <fieldset><legend className={labelClass}>Canal desejado</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {(["email","sms","whatsapp"] as const).filter(channel => validChannel(draft.purpose, channel)).map(channel =>
              <button type="button" key={channel} onClick={() => update({ channel, templateId: "" })}
                aria-pressed={draft.channel===channel}
                className={"rounded-[var(--radius-md)] border px-3 py-2 text-xs " + (draft.channel===channel ? "border-[var(--color-blue)] bg-[var(--color-blue-tint)]" : "border-[var(--color-border)]")}>{CHANNEL_LABEL[channel]}</button>)}
          </div></fieldset>
        <label className={labelClass}>Modelo aprovado
          <select className={fieldClass} value={draft.templateId} onChange={e => update({ templateId: e.target.value })}>
            <option value="">Selecione um modelo validado</option>
            {matched.map(item => <option value={item.id} key={item.id}>{item.code} · v{item.version}</option>)}
          </select></label>
        {!matched.length && <p role="note" className="text-xs text-[var(--color-muted)]">Não há modelos aprovados para a combinação. Use a Biblioteca de Modelos e o fluxo de aprovação existente.</p>}
        {selectedTemplate && <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-panel)] p-4">
          <p className="text-[length:var(--type-caption)] font-semibold">Prévia do modelo — variáveis não substituídas</p>
          {selectedTemplate.subject && <p className="mt-2 text-xs font-medium">{selectedTemplate.subject}</p>}
          <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-relaxed text-[var(--color-slate-600)]">{selectedTemplate.body}</p>
        </div>}
      </div>}
      {step === 3 && <div className="space-y-4">
        <h3 className="text-[length:var(--type-body-compact)] font-semibold">Restrições operacionais</h3>
        <Notice>O servidor aplica janelas locais, limites de contato, autorização vigente, supressões e idempotência. Estes parâmetros não substituem nenhuma política.</Notice>
        <label className={labelClass}>Teto de processamento por minuto
          <input className={fieldClass} type="number" min={1} max={120} step={1} value={draft.perMinute}
            onChange={e => update({ perMinute: Number(e.target.value) })} /></label>
        <div className="space-y-2 rounded-[var(--radius-card)] border border-[var(--color-border)] p-4 text-xs">
          <p><LockKeyhole className="mr-1.5 inline h-3.5 w-3.5" /> Autorização individual obrigatória</p>
          <p>Revisão por segundo usuário e MFA: conferidos pelo backend conforme operação.</p>
          <p>Execução real: indisponível neste construtor, mesmo com campanha aprovada.</p>
        </div>
      </div>}
      {step === 4 && <div className="space-y-4">
        <h3 className="text-[length:var(--type-body-compact)] font-semibold">Revisar antes de criar o rascunho</h3>
        <dl className="grid gap-3 rounded-[var(--radius-card)] border border-[var(--color-border)] p-4 sm:grid-cols-2">
          {([
            ["Nome", draft.name], ["Finalidade", PURPOSE_LABEL[draft.purpose]],
            ["Público", source?.name || "Não selecionado"], ["Canal", CHANNEL_LABEL[draft.channel]],
            ["Modelo", selectedTemplate?.code || "Não selecionado"],
            ["Limite/minuto", String(draft.perMinute)],
            ["Estado após salvar", "Rascunho — sem disparo"],
          ] as Array<[string,string]>).map(([name,value]) => <div key={name}><dt className="text-[length:var(--type-overline)] text-[var(--color-muted)]">{name}</dt><dd className="mt-0.5 break-words text-xs font-medium">{value}</dd></div>)}
        </dl>
        <p className="text-[length:var(--type-caption)] text-[var(--color-muted)]">Elegibilidade global e provedores: não verificados nesta etapa. O próximo fluxo exigirá dados e autorizações do motor.</p>
        {warnings.map((warning,i) => <p className="text-[length:var(--type-caption)] text-[var(--color-red)]" key={i}>• {warning}</p>)}
        <label className="flex items-start gap-2 text-xs">
          <input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} className="mt-0.5" />
          Confirmo a criação de um rascunho. Não estou autorizando envio, agendamento nem aprovação.
        </label>
        {error && <p role="alert" className="text-xs text-[var(--color-red)]">{error}</p>}
      </div>}
    </div>
    <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] px-5 py-4 md:px-7">
      <span className="text-[length:var(--type-caption)] tabular-nums text-[var(--color-muted)]">Etapa {step + 1} de {STEPS.length}</span>
      <div className="flex gap-2">
        {step > 0 && <button type="button" className={buttonClass} onClick={() => setStep(x => x - 1)}><ArrowLeft className="h-3.5 w-3.5" /> Voltar</button>}
        {step < 4 ? <button type="button" disabled={!canAdvance} onClick={next} className={buttonClass}>
          Continuar <ArrowRight className="h-3.5 w-3.5" /></button>
        : <button type="button" disabled={busy || !!warnings.length || !confirmed || (source?.kind === "composio" && !tool)}
            onClick={() => void createDraft()} className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--color-ink)] px-4 text-xs font-medium text-white disabled:opacity-40">
          {busy ? "Salvando…" : "Criar apenas rascunho"} <ChevronRight className="h-3.5 w-3.5" />
        </button>}
      </div>
    </footer>
  </section>;
}
