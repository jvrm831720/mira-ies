"use client";

import { type FormEvent, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle2,
  KeyRound,
  Mail,
  MessageCircle,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import { copy } from "@/lib/copy";

type LoginMode = "password" | "whatsapp" | "forgot";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<LoginMode>("password");
  const [whatsappStep, setWhatsappStep] = useState<"phone" | "code">("phone");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function changeMode(nextMode: LoginMode) {
    setMode(nextMode);
    setWhatsappStep("phone");
    setError(null);
    setNotice(null);
  }

  function backToLogin() {
    changeMode("password");
  }

  async function onPasswordSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const response = await api.loginPassword({ email: email.trim(), password });
      setAccessToken(response.access_token);
      router.replace("/");
    } catch {
      setError("Não foi possível entrar. Verifique seu e-mail e sua senha.");
    } finally {
      setLoading(false);
    }
  }

  async function onWhatsappSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      if (whatsappStep === "phone") {
        await api.requestWhatsappCode(phone.trim());
        setWhatsappStep("code");
        setNotice("Se o número estiver cadastrado, enviaremos um código de uso único pelo WhatsApp.");
      } else {
        const response = await api.verifyWhatsappCode(phone.trim(), code.trim());
        setAccessToken(response.access_token);
        router.replace("/");
      }
    } catch {
      setError(
        whatsappStep === "phone"
          ? "Não foi possível enviar o código. Confira o telefone e tente novamente."
          : "Código inválido ou expirado. Solicite um novo código."
      );
    } finally {
      setLoading(false);
    }
  }

  async function onForgotSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.forgotPassword(email.trim());
      setNotice(
        "Se existir uma conta com esse e-mail, enviaremos instruções para recuperar sua senha."
      );
    } catch {
      setError("Não foi possível solicitar a recuperação agora. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }

  const title = mode === "forgot" ? "Recupere sua senha" : copy.loginTitle;
  const description =
    mode === "forgot"
      ? "Informe seu e-mail institucional e enviaremos um link de recuperação."
      : copy.loginSubtitle;

  return (
    <main className="min-h-screen bg-[#f2f3fb] p-3 sm:p-5 md:p-8">
      <div className="mx-auto grid min-h-[calc(100vh-1.5rem)] w-full max-w-6xl overflow-hidden rounded-3xl border border-border/80 bg-white shadow-[0_24px_80px_rgba(16,13,80,0.12)] md:min-h-[calc(100vh-4rem)] md:grid-cols-[1.05fr_0.95fr]">
        <section className="relative hidden flex-col justify-between overflow-hidden bg-[var(--brand-midnight)] p-8 text-white md:flex lg:p-12">
          <div className="absolute -right-32 -top-32 h-80 w-80 rounded-full bg-[#4050cd]/25 blur-3xl" />
          <div className="absolute -bottom-36 -left-28 h-80 w-80 rounded-full bg-[#f47769]/10 blur-3xl" />
          <div className="relative space-y-14">
            <Image src="/mira-logo.svg" alt="Mira" width={144} height={32} className="h-auto w-36" />
            <div className="space-y-5">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-medium text-slate-200">
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                Acesso seguro para sua instituição
              </div>
              <h1 className="max-w-md text-3xl font-semibold tracking-tight lg:text-4xl">
                Decisões mais claras para cuidar da permanência.
              </h1>
              <p className="max-w-md text-sm leading-6 text-slate-300">{copy.productTagline}</p>
            </div>
          </div>
          <ul className="relative space-y-3 text-sm text-white/70">
            <li className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-[var(--brand-coral)]" aria-hidden="true" />Identifique alunos em risco em segundos</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-[var(--brand-coral)]" aria-hidden="true" />Entenda os fatores com linguagem clara</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-[var(--brand-coral)]" aria-hidden="true" />Aja com segurança e acompanhamento humano</li>
          </ul>
        </section>

        <section className="flex items-center p-5 sm:p-8 lg:p-12">
          <div className="mx-auto w-full max-w-md">
            <div className="mb-8 md:hidden">
              <div className="mb-6 inline-flex rounded-xl bg-[var(--brand-midnight)] px-4 py-3 shadow-sm">
                <Image src="/mira-logo.svg" alt="Mira" width={112} height={25} className="h-auto w-28" />
              </div>
              <p className="text-sm text-muted-foreground">{copy.productTagline}</p>
            </div>

            <Card className="border-0 shadow-none sm:border sm:border-border/80 sm:shadow-sm">
              <CardHeader className="px-0 sm:px-6">
                <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
                  {mode === "whatsapp" ? (
                    <MessageCircle className="h-5 w-5" aria-hidden="true" />
                  ) : mode === "forgot" ? (
                    <KeyRound className="h-5 w-5" aria-hidden="true" />
                  ) : (
                    <Mail className="h-5 w-5" aria-hidden="true" />
                  )}
                </div>
                <CardTitle>{title}</CardTitle>
                <CardDescription>{description}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 px-0 sm:px-6">
                {error ? (
                  <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {error}
                  </p>
                ) : null}
                {notice ? (
                  <p role="status" className="flex gap-2 rounded-lg bg-primary/10 px-3 py-2 text-sm text-primary">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                    <span>{notice}</span>
                  </p>
                ) : null}

                {mode === "password" ? (
                  <form onSubmit={onPasswordSubmit} className="space-y-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium" htmlFor="email">
                        E-mail institucional
                      </label>
                      <Input
                        id="email"
                        type="email"
                        autoComplete="email"
                        placeholder={copy.loginPlaceholder}
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        required
                      />
                    </div>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between gap-3">
                        <label className="text-sm font-medium" htmlFor="password">
                          Senha
                        </label>
                        <button
                          type="button"
                          onClick={() => changeMode("forgot")}
                          className="text-xs font-medium text-primary underline-offset-4 hover:underline"
                        >
                          Esqueci minha senha
                        </button>
                      </div>
                      <Input
                        id="password"
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        required
                      />
                    </div>
                    <Button type="submit" className="w-full" disabled={loading}>
                      {loading ? "Entrando..." : copy.loginCta}
                    </Button>
                  </form>
                ) : null}

                {mode === "whatsapp" ? (
                  <form onSubmit={onWhatsappSubmit} className="space-y-4">
                    {whatsappStep === "phone" ? (
                      <div className="space-y-2">
                        <label className="text-sm font-medium" htmlFor="phone">
                          Telefone com WhatsApp
                        </label>
                        <Input
                          id="phone"
                          type="tel"
                          autoComplete="tel"
                          placeholder="+55 (11) 99999-9999"
                          value={phone}
                          onChange={(event) => setPhone(event.target.value)}
                          required
                        />
                        <p className="text-xs text-muted-foreground">
                          Use o número cadastrado pela sua instituição.
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <label className="text-sm font-medium" htmlFor="code">
                          Código de uso único
                        </label>
                        <Input
                          id="code"
                          inputMode="numeric"
                          autoComplete="one-time-code"
                          maxLength={6}
                          placeholder="000000"
                          value={code}
                          onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                          required
                        />
                        <p className="text-xs text-muted-foreground">
                          Digite o código recebido no WhatsApp de {phone}.
                        </p>
                      </div>
                    )}
                    <Button type="submit" className="w-full" disabled={loading}>
                      {loading
                        ? whatsappStep === "phone"
                          ? "Enviando código..."
                          : "Validando código..."
                        : whatsappStep === "phone"
                          ? "Enviar código"
                          : "Entrar com código"}
                    </Button>
                    {whatsappStep === "code" ? (
                      <button
                        type="button"
                        onClick={() => {
                          setWhatsappStep("phone");
                          setCode("");
                          setNotice(null);
                          setError(null);
                        }}
                        className="flex w-full items-center justify-center gap-2 text-sm text-muted-foreground hover:text-foreground"
                      >
                        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                        Trocar telefone
                      </button>
                    ) : null}
                  </form>
                ) : null}

                {mode === "forgot" ? (
                  <form onSubmit={onForgotSubmit} className="space-y-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium" htmlFor="recovery-email">
                        E-mail institucional
                      </label>
                      <Input
                        id="recovery-email"
                        type="email"
                        autoComplete="email"
                        placeholder={copy.loginPlaceholder}
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        required
                      />
                    </div>
                    <Button type="submit" className="w-full" disabled={loading}>
                      {loading ? "Enviando..." : "Enviar instruções"}
                    </Button>
                  </form>
                ) : null}

                <div className="border-t border-border pt-4 text-center">
                  {mode === "password" ? (
                    <button
                      type="button"
                      onClick={() => changeMode("whatsapp")}
                      className="inline-flex items-center gap-2 text-sm font-medium text-primary underline-offset-4 hover:underline"
                    >
                      <MessageCircle className="h-4 w-4" aria-hidden="true" />
                      Entrar com WhatsApp
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={backToLogin}
                      className="inline-flex items-center gap-2 text-sm font-medium text-primary underline-offset-4 hover:underline"
                    >
                      <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                      Voltar para o login
                    </button>
                  )}
                </div>
              </CardContent>
            </Card>
            <p className="mt-5 text-center text-xs text-muted-foreground">{copy.loginHelp}</p>
          </div>
        </section>
      </div>
    </main>
  );
}
