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
      if ("onboarding_required" in response && response.onboarding_required) {\n        router.replace(`/onboarding?email=${encodeURIComponent(response.email)}`);\n        return;\n      }\n      if ("mfa_enrollment_required" in response && response.mfa_enrollment_required) {
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
      if (mode === "mfa-enroll" && "recovery_codes" in response) {
        setRecoveryCodes(response.recovery_codes);
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
    <main className="min-h-screen bg-white text-neutral-900">
      <div className="grid min-h-screen w-full md:grid-cols-2">
        <section className="flex min-h-screen min-w-0 flex-col px-7 py-8 sm:px-12 lg:px-[10%]">
          <div className="shrink-0">
            <Image src="/mira-logo.svg" alt="MIRA" width={112} height={29} priority className="h-auto w-[104px] brightness-0" />
          </div>

          <div className="mx-auto flex w-full max-w-[390px] flex-1 flex-col justify-center py-14">
            <h1 className="text-[18px] font-semibold leading-6 tracking-[-0.045em] text-neutral-950">
              {isEmailStep ? "Vamos começar." : isCodeStep ? "Verifique seu e-mail." : mode === "mfa-enroll" ? "Configure seu autenticador." : "Verificação em duas etapas."}
            </h1>
            <p className="mt-3 text-[14px] leading-5 text-neutral-500">
              {isEmailStep
                ? "Acesse a MIRA para acompanhar indicadores, identificar alunos em risco e orientar ações de permanência estudantil."
                : isCodeStep
                  ? <>Se este e-mail estiver associado a uma conta ativa, enviaremos um código para <span className="font-medium text-neutral-800">{email}</span>. Digite os seis dígitos abaixo para continuar.</>
                  : mode === "mfa-enroll"
                    ? "A segurança da MIRA exige autenticação multifator para sua conta."
                    : "Informe o código do aplicativo autenticador para concluir o acesso."}
            </p>

            <div className="mt-8 space-y-4">
              {error && <p role="alert" aria-live="assertive" className="rounded-lg bg-red-50 px-3 py-2.5 text-sm leading-5 text-red-700">{error}</p>}

              {isEmailStep && (
                <form onSubmit={requestCode} className="space-y-4">
                  <div className="space-y-2">
                    <label htmlFor="email" className="text-[13px] font-medium text-neutral-700">E-mail de trabalho</label>
                    <Input id="email" type="email" autoComplete="email" placeholder="Digite seu e-mail de trabalho" value={email} onChange={(event) => setEmail(event.target.value)} required className="h-12 rounded-lg border-neutral-200 px-4 text-[14px]" />
                  </div>
                  <Button type="submit" disabled={loading} className="h-12 w-full rounded-lg bg-neutral-950 text-[14px] font-medium text-white hover:bg-neutral-800">
                    {loading ? "Enviando…" : "Continuar com e-mail"}
                  </Button>
                  <p className="text-center text-[11px] leading-5 text-neutral-400">
                    Ao continuar, você concorda com os termos de uso e a política de privacidade da MIRA.
                  </p>
                </form>
              )}

              {isCodeStep && (
                <form onSubmit={verifyCode} className="space-y-5">
                  <div className="space-y-2">
                    <label htmlFor="email-code" className="text-[13px] font-medium text-neutral-700">Código de verificação</label>
                    <Input id="email-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="000000" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} required className="h-12 rounded-lg border-neutral-200 px-4 text-center text-xl tracking-[0.45em]" />
                  </div>
                  <div className="flex items-center justify-between text-[13px]">
                    <span className="text-neutral-500">Não recebeu o código?</span>
                    <button type="button" onClick={() => void requestCode()} disabled={loading || resendSeconds > 0} className="font-medium text-neutral-900 disabled:cursor-not-allowed disabled:text-neutral-400">
                      {resendSeconds > 0 ? `Reenviar em ${String(Math.floor(resendSeconds / 60)).padStart(2, "0")}:${String(resendSeconds % 60).padStart(2, "0")}` : "Reenviar código"}
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <Button type="button" variant="outline" onClick={() => { setMode("email"); setCode(""); setError(null); }} className="h-12 rounded-lg border-neutral-200 bg-white text-neutral-800 hover:bg-neutral-50">
                      <ArrowLeft className="mr-2 h-4 w-4" /> Voltar
                    </Button>
                    <Button type="submit" disabled={loading || code.length !== 6} className="h-12 rounded-lg bg-neutral-950 text-white hover:bg-neutral-800">
                      {loading ? "Verificando…" : "Confirmar"}
                    </Button>
                  </div>
                </form>
              )}

              {(mode === "mfa" || mode === "mfa-enroll") && (
                <form onSubmit={confirmMfa} className="space-y-4">
                  {mfaEnrollment && mode === "mfa-enroll" && (
                    <div className="space-y-3 rounded-lg border border-neutral-200 p-4">
                      <p className="text-sm font-medium">Escaneie o QR Code no aplicativo autenticador.</p>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={mfaEnrollment.qr_code} alt="QR Code para configurar o autenticador da MIRA" className="mx-auto h-44 w-44" />
                      <p className="break-all rounded bg-neutral-50 p-2 font-mono text-xs">{mfaEnrollment.secret}</p>
                    </div>
                  )}
                  {recoveryCodes ? (
                    <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-4">
                      <p className="text-sm font-semibold text-amber-900">Guarde seus códigos de recuperação.</p>
                      <div className="grid grid-cols-2 gap-2">{recoveryCodes.map((item) => <code key={item} className="rounded bg-white p-2 text-center text-xs">{item}</code>)}</div>
                      <Button type="button" variant="outline" onClick={() => navigator.clipboard.writeText(recoveryCodes.join("\n"))}>Copiar códigos</Button>
                      <Button type="button" className="w-full" onClick={() => router.replace("/")}>Já guardei — entrar</Button>
                    </div>
                  ) : (
                    <>
                      <Input id="mfa-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="Código de 6 dígitos" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} required className="h-12 rounded-lg border-neutral-200 px-4 text-center text-xl tracking-[0.45em]" />
                      <Button type="submit" disabled={loading || code.length !== 6} className="h-12 w-full rounded-lg bg-neutral-950 text-white hover:bg-neutral-800">{loading ? "Confirmando…" : "Confirmar e entrar"}</Button>
                    </>
                  )}
                </form>
              )}
            </div>
          </div>

          <p className="shrink-0 text-center text-[11px] text-neutral-400">Acesso protegido e vinculado à sua instituição.</p>
        </section>

        <aside className="relative hidden min-h-screen overflow-hidden bg-[#17191d] md:block">
          <Image src="/login-art.svg" alt="" fill priority className="object-cover opacity-90" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/65 via-black/15 to-black/10" />
          <div className="absolute bottom-[10%] left-[10%] right-[10%]">
            <p className="max-w-[440px] text-[18px] font-medium leading-[1.45] tracking-[-0.025em] text-white">
              “A permanência estudantil começa com decisões mais claras, ações no momento certo e acompanhamento contínuo.”
            </p>
            <div className="mt-6 space-y-1">
              <p className="text-[13px] font-semibold text-white">MIRA</p>
              <p className="text-[13px] text-white/70">Inteligência para permanência estudantil</p>
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}
