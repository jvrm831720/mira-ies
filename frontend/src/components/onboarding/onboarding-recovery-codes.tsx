"use client";

import { useState } from "react";
import { Check, CheckCircle2, Copy, LockKeyhole, ShieldCheck } from "@/components/ui/icons";

export function OnboardingRecoveryCodes({
  codes,
  onContinue,
}: {
  codes: string[];
  onContinue: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);

  async function copyAll() {
    try {
      await navigator.clipboard.writeText(codes.join("\n"));
      setCopied(true);
      setCopyError(false);
    } catch {
      setCopied(false);
      setCopyError(true);
    }
  }

  return (
    <div className="mira-flow-recovery-guide">
      <div className="mira-flow-recovery-intro">
        <p className="mira-flow-eyebrow">Proteção ativada</p>
        <span className="mira-flow-recovery-success-icon" aria-hidden="true">
          <ShieldCheck size={22} />
        </span>
        <h1>Códigos de recuperação</h1>
        <p>
          Seu autenticador está configurado. Guarde estes códigos para recuperar
          o acesso caso perca seu celular ou o aplicativo autenticador.
        </p>
      </div>

      <section className="mira-flow-recovery-panel" aria-labelledby="mira-recovery-list-title">
        <div className="mira-flow-recovery-panel-header">
          <div className="mira-flow-recovery-panel-heading">
            <h2 id="mira-recovery-list-title">Seus códigos de segurança</h2>
            <p>{codes.length} códigos de uso único · Exibidos apenas agora</p>
          </div>
          <button
            type="button"
            className="mira-flow-recovery-copy"
            onClick={() => void copyAll()}
            aria-label="Copiar todos os códigos de recuperação"
          >
            {copied ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
            {copied ? "Copiados" : "Copiar todos"}
          </button>
        </div>
        <ol className="mira-flow-recovery-codes" aria-label="Códigos de recuperação de uso único">
          {codes.map((code, index) => (
            <li key={index} className="mira-flow-recovery-code">
              <span className="mira-flow-recovery-code-index" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <code>{code}</code>
            </li>
          ))}
        </ol>
        <p className="mira-flow-recovery-copy-feedback" role="status" aria-live="polite">
          {copyError
            ? "Não foi possível copiar. Selecione os códigos e salve-os manualmente."
            : copied
              ? "Códigos copiados. Guarde-os em um local privado, como seu gerenciador de senhas."
              : "Sugestão: salve os códigos em um gerenciador de senhas."}
        </p>
      </section>

      <div className="mira-flow-recovery-footer">
        <div className="mira-flow-recovery-alert">
          <LockKeyhole size={16} aria-hidden="true" />
          <p>Esta lista não será exibida novamente. Não compartilhe os códigos nem guarde todos no mesmo dispositivo do autenticador.</p>
        </div>
        <label className="mira-flow-recovery-acknowledge">
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={event => setAcknowledged(event.target.checked)}
          />
          <span>Salvei meus códigos em um local seguro.</span>
        </label>
        <button
          type="button"
          className="mira-flow-primary mira-flow-recovery-continue"
          onClick={onContinue}
          disabled={!acknowledged}
        >
          <CheckCircle2 size={16} aria-hidden="true" />
          Continuar para as integrações
        </button>
      </div>
    </div>
  );
}
