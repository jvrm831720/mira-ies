"use client";

import { type FormEvent, useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";

type LoginMode = "email" | "email-code" | "mfa" | "mfa-enroll";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<LoginMode>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [mfaTicket, setMfaTicket] = useState("");
  const [mfaEnrollment, setMfaEnrollment] = useState<{ secret: string; qr_code: string } | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [resendSeconds, setResendSeconds] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (resendSeconds <= 0) return;
    const timer = window.setTimeout(() => setResendSeconds((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [resendSeconds]);

  function humanError(err: unknown, fallback: string) {
    if (err instanceof ApiError) {
      if (err.status === 0 || /failed to fetch|network/i.test(err.message)) {
        return "Não foi possível conectar à MIRA. Verifique sua conexão e tente novamente.";
      }
      if (err.status === 429) return "Muitas tentativas em pouco tempo. Aguarde antes de solicitar outro código.";
      if (err.status >= 500) return "O serviço está temporariamente indisponível. Tente novamente em instantes.";
    }
    if (err instanceof TypeError) return "Não foi possível conectar à MIRA. Verifique sua conexão e tente novamente.";
    return fallback;
  }

  async function requestCode(event?: FormEvent) {
    event?.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.requestEmailCode(email.trim());
      setCode("");
      setResendSeconds(60);
      setMode("email-code");
    } catch (err) {
      setError(humanError(err, "Não foi possível enviar o código. Confira o e-mail e tente novamente."));
    } finally {
      setLoading(false);
    }
  }

  async function verifyCode(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const response = await api.verifyEmailCode(email.trim(), code);
      if ("onboarding_required" in response && response.onboarding_required) {
        router.replace(`/onboarding?email=${encodeURIComponent(response.email)}`);
        return;
      }
      if ("mfa_enrollment_required" in response && response.mfa_enrollment_required) {
        setMfaTicket(response.challenge_token);
        const enrollment = await api.beginRequiredMfaEnrollment(response.challenge_token);
        setMfaEnrollment(enrollment);
        setRecoveryCodes(null);
        setCode("");
        setMode("mfa-enroll");
      } else if ("mfa_required" in response && response.mfa_required) {
        setMfaTicket(response.challenge_token);
        setCode("");
        setMode("mfa");
      } else if ("access_token" in response) {
        setAccessToken(response.access_token);
        router.replace("/");
      }
    } catch (err) {
      setError(humanError(err, "Código inválido ou expirado. Confira os seis dígitos e tente novamente."));
    } finally {
      setLoading(false);
    }
  }

  async function confirmMfa(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const response = mode === "mfa-enroll"
        ? await api.confirmRequiredMfaEnrollment(mfaTicket, code)
        : await api.verifyMfaLogin(mfaTicket, code);
      setAccessToken(response.access_token);
      if (mode === "mfa-enroll" && "recovery_codes" in response && Array.isArray(response.recovery_codes)) {
        setRecoveryCodes(response.recovery_codes.filter((item): item is string => typeof item === "string"));
        setCode("");
      } else {
        router.replace("/");
      }
    } catch (err) {
      setError(humanError(err, "Código inválido ou expirado."));
    } finally {
      setLoading(false);
    }
  }

  const isEmailStep = mode === "email";
  const isCodeStep = mode === "email-code";

  return (
    <main className="auth-login-page">
      <div className="auth-login-frame">
        <header className="auth-login-brand">
          <Image src="/mira-logo.svg" alt="MIRA" width={112} height={29} priority className="auth-login-logo" />
        </header>

        <div className="auth-login-card">
          <section className="auth-login-form-panel" aria-label="Acesso à MIRA">
            <div className="auth-login-content">
              <h1 className="auth-login-heading">
                {isEmailStep ? "Vamos começar." : isCodeStep ? "Verifique seu e-mail." : mode === "mfa-enroll" ? "Configure seu autenticador." : "Verificação em duas etapas."}
              </h1>
              <p className="auth-login-description">
                {isEmailStep
                  ? "Acesse a MIRA para acompanhar indicadores, identificar alunos em risco e orientar ações de permanência estudantil."
                  : isCodeStep
                    ? <>Se este e-mail estiver associado a uma conta ativa, enviaremos um código para <span className="font-medium text-neutral-800">{email}</span>. Digite os seis dígitos abaixo para continuar.</>
                    : mode === "mfa-enroll"
                      ? "A segurança da MIRA exige autenticação multifator para sua conta."
                      : "Informe o código do aplicativo autenticador para concluir o acesso."}
              </p>

              <div className="auth-login-form-stack">
                {error && <p role="alert" aria-live="assertive" className="auth-login-error">{error}</p>}

                {isEmailStep && (
                  <form onSubmit={requestCode} className="space-y-4">
                    <div className="space-y-2">
                      <label htmlFor="email" className="auth-login-label">E-mail de trabalho</label>
                      <Input id="email" type="email" autoComplete="email" placeholder="Digite seu e-mail de trabalho" value={email} onChange={(event) => setEmail(event.target.value)} required className="auth-login-input h-12 rounded-lg px-4 text-[14px]" />
                    </div>
                    <Button type="submit" disabled={loading} className="auth-login-primary h-12 w-full rounded-lg text-[14px] font-medium">
                      {loading ? "Enviando…" : "Continuar com e-mail"}
                    </Button>
                    <p className="auth-login-terms">
                      Ao continuar, você concorda com os termos de uso e a política de privacidade da MIRA.
                    </p>
                  </form>
                )}

                {isCodeStep && (
                  <form onSubmit={verifyCode} className="space-y-5">
                    <div className="space-y-2">
                      <label htmlFor="email-code" className="auth-login-label">Código de verificação</label>
                      <Input id="email-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="000000" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} required className="auth-login-input h-12 rounded-lg px-4 text-center text-xl tracking-[0.45em]" />
                    </div>
                    <div className="flex items-center justify-between gap-3 text-[13px]">
                      <span className="auth-login-muted">Não recebeu o código?</span>
                      <button type="button" onClick={() => void requestCode()} disabled={loading || resendSeconds > 0} className="auth-login-text-button">
                        {resendSeconds > 0 ? `Reenviar em ${String(Math.floor(resendSeconds / 60)).padStart(2, "0")}:${String(resendSeconds % 60).padStart(2, "0")}` : "Reenviar código"}
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <Button type="button" variant="outline" onClick={() => { setMode("email"); setCode(""); setError(null); }} className="auth-login-secondary h-12 rounded-lg">
                        <ArrowLeft className="mr-2 h-4 w-4" /> Voltar
                      </Button>
                      <Button type="submit" disabled={loading || code.length !== 6} className="auth-login-primary h-12 rounded-lg">
                        {loading ? "Verificando…" : "Confirmar"}
                      </Button>
                    </div>
                  </form>
                )}

                {(mode === "mfa" || mode === "mfa-enroll") && (
                  <form onSubmit={confirmMfa} className="space-y-4">
                    {mfaEnrollment && mode === "mfa-enroll" && (
                      <div className="auth-login-enrollment-card space-y-3 rounded-lg p-4">
                        <p className="text-sm font-medium">Escaneie o QR Code no aplicativo autenticador.</p>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={mfaEnrollment.qr_code} alt="QR Code para configurar o autenticador da MIRA" className="mx-auto h-44 w-44 rounded-md bg-white p-2" />
                        <p className="auth-login-secret break-all rounded p-2 font-mono text-xs">{mfaEnrollment.secret}</p>
                      </div>
                    )}
                    {recoveryCodes ? (
                      <div className="auth-login-recovery-card space-y-3 rounded-lg p-4">
                        <p className="text-sm font-semibold">Guarde seus códigos de recuperação.</p>
                        <div className="grid grid-cols-2 gap-2">{recoveryCodes.map((item) => <code key={item} className="auth-login-recovery-code rounded p-2 text-center text-xs">{item}</code>)}</div>
                        <Button type="button" variant="outline" className="auth-login-secondary w-full" onClick={() => navigator.clipboard.writeText(recoveryCodes.join("\n"))}>Copiar códigos</Button>
                        <Button type="button" className="auth-login-primary w-full" onClick={() => router.replace("/")}>Já guardei — entrar</Button>
                      </div>
                    ) : (
                      <>
                        <Input id="mfa-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="Código de 6 dígitos" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} required className="auth-login-input h-12 rounded-lg px-4 text-center text-xl tracking-[0.45em]" />
                        <Button type="submit" disabled={loading || code.length !== 6} className="auth-login-primary h-12 w-full rounded-lg">{loading ? "Confirmando…" : "Confirmar e entrar"}</Button>
                      </>
                    )}
                  </form>
                )}
              </div>
            </div>

            <p className="auth-login-footer">Acesso protegido e vinculado à sua instituição.</p>
          </section>

          <aside className="auth-login-testimonial" aria-label="Depoimento da MIRA">
            <div className="auth-login-testimonial-content">
              <blockquote className="auth-login-quote">
                “A permanência estudantil começa com decisões mais claras, ações no momento certo e acompanhamento contínuo.”
              </blockquote>
              <div className="auth-login-attribution">
                <p className="auth-login-attribution-name">MIRA</p>
                <p className="auth-login-attribution-description">Inteligência para permanência estudantil</p>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </main>
  );
}
