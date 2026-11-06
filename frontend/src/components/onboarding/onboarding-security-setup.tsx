"use client";

import { useState, type FormEvent } from "react";
import { Check, Copy, KeyRound, LockKeyhole, ShieldCheck, Smartphone } from "@/components/ui/icons";

export type MfaEnrollment = { qr_code: string; secret: string };

export function MfaCodeInput({
  code, onCodeChange, disabled = false, id = "mira-flow-mfa",
}: {
  code: string;
  onCodeChange: (value: string) => void;
  disabled?: boolean;
  id?: string;
}) {
  return (
    <div className="mira-flow-otp-field">
      <label htmlFor={id}>Código de verificação</label>
      <div className="mira-flow-otp-control">
        <input
          id={id}
          name="totp_code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]{6}"
          maxLength={6}
          required
          aria-describedby={id + "-help"}
          aria-label="Código de seis dígitos do aplicativo autenticador"
          disabled={disabled}
          value={code}
          onChange={event => onCodeChange(event.target.value.replace(/\D/g, "").slice(0, 6))}
          onPaste={event => {
            const pastedCode = event.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
            if (pastedCode) {
              event.preventDefault();
              onCodeChange(pastedCode);
            }
          }}
          className="mira-flow-otp-native"
        />
        <div className="mira-flow-otp-slots" aria-hidden="true">
          {Array.from({ length: 6 }, (_, index) => (
            <span
              key={index}
              className={"mira-flow-otp-slot" + (index === code.length && code.length < 6 ? " active" : "")}
            >
              {code[index] || ""}
            </span>
          ))}
        </div>
      </div>
      <p id={id + "-help"} className="mira-flow-security-hint">
        O código muda automaticamente a cada 30 segundos. Você também pode colar os seis dígitos.
      </p>
    </div>
  );
}

export function OnboardingSecuritySetup({
  mode, enrollment, code, onCodeChange, onConfirm, onRetry, busy, error,
}: {
  mode: "enroll" | "verify";
  enrollment: MfaEnrollment | null;
  code: string;
  onCodeChange: (value: string) => void;
  onConfirm: (event: FormEvent<HTMLFormElement>) => void;
  onRetry: () => void;
  busy: boolean;
  error: string;
}) {
  const [showManual, setShowManual] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const isEnrollment = mode === "enroll";
  const canConfirm = code.length === 6 && !busy && (!isEnrollment || !!enrollment);

  async function copySecret() {
    if (!enrollment?.secret) return;
    try {
      await navigator.clipboard.writeText(enrollment.secret);
      setCopied(true);
      setCopyError(false);
    } catch {
      setCopied(false);
      setCopyError(true);
    }
  }

  return (
    <div className="mira-flow-security-guide">
      <div className="mira-flow-security-intro">
        <p className="mira-flow-eyebrow">Última etapa · Segurança</p>
        <span className="mira-flow-security-emblem" aria-hidden="true"><ShieldCheck size={23} /></span>
        <h1>{isEnrollment ? "Proteja seu acesso" : "Confirme seu acesso"}</h1>
        <p>
          {isEnrollment
            ? "Ative a autenticação em duas etapas para proteger sua conta e continuar a configuração do workspace."
            : "Sua conta já utiliza autenticação em duas etapas. Confirme o código do aplicativo para continuar."}
        </p>
      </div>

      <form onSubmit={onConfirm} className="mira-flow-security-card">
        <div className="mira-flow-security-card-title">
          <LockKeyhole size={15} aria-hidden="true" />
          <strong>{isEnrollment ? "Configuração do autenticador" : "Verificação de segurança"}</strong>
          <span>{isEnrollment ? "3 passos" : "1 passo"}</span>
        </div>
        <ol className="mira-flow-security-steps">
          {isEnrollment && (
            <>
              <li className="mira-flow-security-step">
                <span className="mira-flow-security-number" aria-hidden="true">1</span>
                <div className="mira-flow-security-step-body">
                  <h2>Abra um aplicativo autenticador</h2>
                  <p>Use Google Authenticator, Microsoft Authenticator, 1Password ou outro aplicativo compatível.</p>
                  <span className="mira-flow-security-app-note"><Smartphone size={13} aria-hidden="true" /> Já tem um instalado? Siga para o próximo passo.</span>
                </div>
              </li>
              <li className="mira-flow-security-step">
                <span className="mira-flow-security-number" aria-hidden="true">2</span>
                <div className="mira-flow-security-step-body">
                  <h2>Escaneie o QR Code</h2>
                  <p>Abra o aplicativo, escolha adicionar conta e aponte a câmera para o código abaixo.</p>
                  {enrollment ? (
                    <div className="mira-flow-security-qr-area">
                      <div className="mira-flow-security-qr-frame">
                        {/* O QR é gerado pela API MFA da MIRA; nunca usar uma imagem de exemplo. */}
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={enrollment.qr_code}
                          width={180}
                          height={180}
                          alt="QR Code exclusivo para configurar o autenticador da sua conta MIRA"
                        />
                      </div>
                      <p className="mira-flow-security-qr-caption">Este QR Code é individual. Não o compartilhe.</p>
                    </div>
                  ) : (
                    <div className="mira-flow-security-qr-pending" role="status">
                      <p>{busy ? "Preparando seu QR Code…" : "Não foi possível exibir o QR Code."}</p>
                      {!busy && (
                        <button type="button" className="mira-flow-secondary" onClick={onRetry}>
                          Tentar carregar novamente
                        </button>
                      )}
                    </div>
                  )}

                  {enrollment && (
                    <div className="mira-flow-security-manual">
                      <button
                        className="mira-flow-security-manual-trigger"
                        type="button"
                        aria-expanded={showManual}
                        onClick={() => { setShowManual(open => !open); setCopied(false); setCopyError(false); }}
                      >
                        <KeyRound size={14} aria-hidden="true" />
                        Não consegue escanear? Usar chave manual
                      </button>
                      {showManual && (
                        <div id="mira-flow-security-manual-panel" className="mira-flow-security-manual-panel">
                          <p>No aplicativo, escolha inserir chave de configuração e digite o valor abaixo.</p>
                          <div className="mira-flow-security-manual-secret">
                            <code>{enrollment.secret}</code>
                            <button type="button" onClick={() => void copySecret()} aria-label="Copiar chave de configuração do autenticador">
                              {copied ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
                              <span aria-live="polite">{copied ? "Copiada" : "Copiar"}</span>
                            </button>
                          </div>
                          {copyError && (
                            <p className="mira-flow-security-copy-error" role="alert">
                              Não foi possível copiar. Selecione a chave e copie manualmente.
                            </p>
                          )}
                          <p className="mira-flow-security-qr-caption">Mantenha a chave em segurança. Ela permite gerar os códigos de acesso.</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </li>
            </>
          )}
          <li className="mira-flow-security-step last">
            <span className="mira-flow-security-number" aria-hidden="true">{isEnrollment ? "3" : "1"}</span>
            <div className="mira-flow-security-step-body">
              <h2>{isEnrollment ? "Digite o código gerado" : "Abra seu autenticador"}</h2>
              <p>
                {isEnrollment
                  ? "Para finalizar, informe o código de seis dígitos exibido no aplicativo."
                  : "Informe o código de seis dígitos exibido na sua conta MIRA no aplicativo."}
              </p>
              <MfaCodeInput code={code} onCodeChange={onCodeChange} disabled={busy || (isEnrollment && !enrollment)} />
            </div>
          </li>
        </ol>
        {error && <p className="mira-flow-error" role="alert">{error}</p>}
        <div className="mira-flow-security-card-actions">
          <button className="mira-flow-primary" type="submit" disabled={!canConfirm}>
            {busy ? "Verificando…" : isEnrollment ? "Ativar proteção e continuar" : "Confirmar e continuar"}
          </button>
          <p>Os códigos do autenticador são solicitados para proteger o seu acesso.</p>
        </div>
      </form>
    </div>
  );
}
