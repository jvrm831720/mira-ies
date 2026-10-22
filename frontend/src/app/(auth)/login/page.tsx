"use client";

import { type FormEvent, useMemo, useRef, useState, useEffect } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { ArrowLeft, Check, ChevronDown, KeyRound, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

type LoginMode = "password" | "whatsapp" | "email-code" | "forgot";

const COUNTRIES = [
  { iso: "br", code: "BR", name: "Brasil", dial: "+55" },
  { iso: "pt", code: "PT", name: "Portugal", dial: "+351" },
  { iso: "us", code: "US", name: "Estados Unidos", dial: "+1" },
  { iso: "ar", code: "AR", name: "Argentina", dial: "+54" },
  { iso: "cl", code: "CL", name: "Chile", dial: "+56" },
  { iso: "co", code: "CO", name: "Colômbia", dial: "+57" },
  { iso: "mx", code: "MX", name: "México", dial: "+52" },
  { iso: "es", code: "ES", name: "Espanha", dial: "+34" },
] as const;

function Flag({ iso, className }: { iso: string; className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`https://flagcdn.com/w40/${iso}.png`}
      srcSet={`https://flagcdn.com/w80/${iso}.png 2x`}
      alt=""
      width={20}
      height={15}
      className={cn(
        "h-[15px] w-5 shrink-0 rounded-[2px] object-cover shadow-sm ring-1 ring-black/10",
        className
      )}
      loading="lazy"
    />
  );
}

function WhatsAppMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#25D366"
        d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.435 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"
      />
    </svg>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<LoginMode>("password");
  const [whatsappStep, setWhatsappStep] = useState<"phone" | "code">("phone");
  const [emailStep, setEmailStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [localPhone, setLocalPhone] = useState("");
  const [country, setCountry] = useState<(typeof COUNTRIES)[number]>(COUNTRIES[0]);
  const [countryOpen, setCountryOpen] = useState(false);
  const countryRef = useRef<HTMLDivElement>(null);
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const fullPhone = useMemo(() => {
    const digits = localPhone.replace(/\D/g, "");
    return `${country.dial}${digits}`;
  }, [country.dial, localPhone]);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!countryRef.current?.contains(e.target as Node)) setCountryOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function changeMode(next: LoginMode) {
    setMode(next);
    setWhatsappStep("phone");
    setEmailStep("email");
    setCode("");
    setError(null);
    setNotice(null);
  }

  function humanError(err: unknown, fallback: string) {
    if (err instanceof ApiError) {
      if (err.status === 0 || /failed to fetch|network/i.test(err.message)) {
        return "Não foi possível falar com o servidor. Confira sua conexão e tente novamente.";
      }
      return err.message || fallback;
    }
    if (err instanceof TypeError) {
      return "Não foi possível falar com o servidor. Confira sua conexão e tente novamente.";
    }
    return fallback;
  }

  async function onPasswordSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const response = await api.loginPassword({ email: email.trim(), password });
      setAccessToken(response.access_token);
      router.replace("/");
    } catch (err) {
      setError(
        humanError(
          err,
          "Não foi possível entrar. Em desenvolvimento use admin@mira.local / MiraAdmin123!"
        )
      );
    } finally {
      setLoading(false);
    }
  }

  async function onWhatsappSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      if (whatsappStep === "phone") {
        await api.requestWhatsappCode(fullPhone);
        setWhatsappStep("code");
        setNotice("Se o número estiver cadastrado, enviaremos um código pelo WhatsApp.");
      } else {
        const response = await api.verifyWhatsappCode(fullPhone, code.trim());
        setAccessToken(response.access_token);
        router.replace("/");
      }
    } catch (err) {
      setError(
        humanError(
          err,
          whatsappStep === "phone"
            ? "Não foi possível enviar o código. Confira o telefone."
            : "Código inválido ou expirado."
        )
      );
    } finally {
      setLoading(false);
    }
  }

  async function onEmailCodeSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      if (emailStep === "email") {
        await api.requestEmailCode(email.trim());
        setEmailStep("code");
        setNotice("Se o e-mail estiver cadastrado, enviaremos um código de acesso.");
      } else {
        const response = await api.verifyEmailCode(email.trim(), code.trim());
        setAccessToken(response.access_token);
        router.replace("/");
      }
    } catch (err) {
      setError(
        humanError(
          err,
          emailStep === "email"
            ? "Não foi possível enviar o código. Confira o e-mail."
            : "Código inválido ou expirado."
        )
      );
    } finally {
      setLoading(false);
    }
  }

  async function onForgotSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.forgotPassword(email.trim());
      setNotice("Se existir uma conta com esse e-mail, enviaremos as instruções.");
    } catch (err) {
      setError(humanError(err, "Não foi possível solicitar a recuperação agora."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#1a1a1a]">
      <div className="pointer-events-none absolute inset-0">
        <Image src="/login-art.svg" alt="" fill priority className="object-cover opacity-90" />
        <div className="absolute inset-0 bg-gradient-to-br from-black/35 via-black/20 to-black/45" />
      </div>

      <div className="relative z-10 flex min-h-screen items-center justify-center p-4 sm:p-6">
        <div className="grid w-full max-w-[980px] overflow-hidden rounded-[28px] border border-white/20 bg-white shadow-[0_40px_120px_rgba(0,0,0,0.45)] md:grid-cols-[minmax(0,1fr)_minmax(0,0.95fr)]">
          <section className="flex flex-col justify-center px-7 py-10 sm:px-10 lg:px-12">
            <div className="mb-8">
              <Image
                src="/mira-logo.svg"
                alt="Mira"
                width={112}
                height={26}
                className="h-auto w-[104px] brightness-0"
              />
            </div>

            <h1 className="text-[28px] font-semibold tracking-[-0.04em] text-neutral-900">
              {mode === "forgot"
                ? "Recuperar senha"
                : mode === "whatsapp"
                  ? whatsappStep === "code"
                    ? "Confirme o código"
                    : "Entrar com WhatsApp"
                  : mode === "email-code"
                    ? emailStep === "code"
                      ? "Confirme o código"
                      : "Entrar com código no e-mail"
                  : "Entrar"}
            </h1>
            <p className="mt-1.5 text-sm text-neutral-500">
              {mode === "forgot"
                ? "Enviaremos um link para o e-mail da conta."
                : mode === "whatsapp"
                  ? whatsappStep === "code"
                    ? `Código enviado para ${fullPhone}`
                    : "Informe o número cadastrado na instituição."
                  : mode === "email-code"
                    ? emailStep === "code"
                      ? `Código enviado para ${email}`
                      : "Informe o e-mail cadastrado na instituição."
                  : "Continue para o painel da sua instituição."}
            </p>

            <div className="mt-7 space-y-4">
              {error && (
                <p role="alert" className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">
                  {error}
                </p>
              )}
              {notice && (
                <p role="status" className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                  {notice}
                </p>
              )}

              {mode === "password" && (
                <>
                  <button
                    type="button"
                    onClick={() => changeMode("email-code")}
                    className="flex h-11 w-full items-center justify-center gap-2.5 rounded-full border border-neutral-200 bg-white text-sm font-medium text-neutral-800 transition hover:bg-neutral-50"
                  >
                    <Mail className="h-4 w-4" />
                    Entrar com código no e-mail
                  </button>
                  <button
                    type="button"
                    onClick={() => changeMode("whatsapp")}
                    className="flex h-11 w-full items-center justify-center gap-2.5 rounded-full border border-neutral-200 bg-white text-sm font-medium text-neutral-800 transition hover:bg-neutral-50"
                  >
                    <WhatsAppMark className="h-5 w-5" />
                    Entrar com WhatsApp
                  </button>

                  <div className="relative py-1 text-center text-[11px] font-medium uppercase tracking-[0.16em] text-neutral-400">
                    <span className="absolute inset-x-0 top-1/2 h-px bg-neutral-200" />
                    <span className="relative bg-white px-3">ou</span>
                  </div>

                  <form onSubmit={onPasswordSubmit} className="space-y-3.5">
                    <div className="space-y-1.5">
                      <label className="text-[13px] font-medium text-neutral-700" htmlFor="email">
                        E-mail
                      </label>
                      <Input
                        id="email"
                        type="email"
                        autoComplete="email"
                        placeholder="voce@instituicao.edu.br"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                        className="h-11 rounded-full border-neutral-200 px-4"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label className="text-[13px] font-medium text-neutral-700" htmlFor="password">
                          Senha
                        </label>
                        <button
                          type="button"
                          onClick={() => changeMode("forgot")}
                          className="text-xs font-medium text-neutral-500 hover:text-neutral-900"
                        >
                          Esqueci a senha
                        </button>
                      </div>
                      <Input
                        id="password"
                        type="password"
                        autoComplete="current-password"
                        placeholder="••••••••"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        className="h-11 rounded-full border-neutral-200 px-4"
                      />
                    </div>
                    <Button
                      type="submit"
                      disabled={loading}
                      className="h-11 w-full rounded-full bg-neutral-950 text-white hover:bg-neutral-800"
                    >
                      {loading ? "Entrando…" : "Entrar"}
                    </Button>
                  </form>

                  <p className="rounded-xl bg-neutral-50 px-3 py-2 text-[11px] leading-relaxed text-neutral-500">
                    <strong className="font-semibold text-neutral-700">Dev local:</strong>{" "}
                    <code className="rounded bg-white px-1 py-0.5 text-[10px]">admin@mira.local</code>{" "}
                    /{" "}
                    <code className="rounded bg-white px-1 py-0.5 text-[10px]">MiraAdmin123!</code>
                  </p>
                </>
              )}

              {mode === "email-code" && (
                <form onSubmit={onEmailCodeSubmit} className="space-y-4">
                  {emailStep === "email" ? (
                    <div className="space-y-1.5">
                      <label className="text-[13px] font-medium text-neutral-700" htmlFor="email-otp">
                        E-mail institucional
                      </label>
                      <Input
                        id="email-otp"
                        type="email"
                        autoComplete="email"
                        placeholder="voce@instituicao.edu.br"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                        className="h-11 rounded-full border-neutral-200 px-4"
                      />
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      <label className="text-[13px] font-medium text-neutral-700" htmlFor="email-otp-code">
                        Código de 6 dígitos
                      </label>
                      <Input
                        id="email-otp-code"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={6}
                        placeholder="000000"
                        value={code}
                        onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                        required
                        className="h-12 rounded-full border-neutral-200 px-4 text-center text-lg tracking-[0.35em]"
                      />
                    </div>
                  )}
                  <Button
                    type="submit"
                    disabled={loading}
                    className="h-11 w-full rounded-full bg-neutral-950 text-white hover:bg-neutral-800"
                  >
                    <Mail className="h-4 w-4" />
                    {loading
                      ? emailStep === "email" ? "Enviando…" : "Validando…"
                      : emailStep === "email" ? "Enviar código por e-mail" : "Confirmar e entrar"}
                  </Button>
                  <button
                    type="button"
                    onClick={() => {
                      if (emailStep === "code") {
                        setEmailStep("email");
                        setCode("");
                        setNotice(null);
                        setError(null);
                      } else {
                        changeMode("password");
                      }
                    }}
                    className="flex w-full items-center justify-center gap-2 text-sm text-neutral-500 hover:text-neutral-900"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    {emailStep === "code" ? "Trocar e-mail" : "Voltar"}
                  </button>
                </form>
              )}

              {mode === "whatsapp" && (
                <form onSubmit={onWhatsappSubmit} className="space-y-4">
                  {whatsappStep === "phone" ? (
                    <div className="space-y-1.5">
                      <label className="text-[13px] font-medium text-neutral-700">
                        Número com WhatsApp
                      </label>
                      <div className="flex gap-2">
                        <div className="relative" ref={countryRef}>
                          <button
                            type="button"
                            onClick={() => setCountryOpen((v) => !v)}
                            className="flex h-11 min-w-[148px] items-center gap-2 rounded-full border border-neutral-200 bg-white px-3 text-left text-sm transition hover:bg-neutral-50"
                            aria-expanded={countryOpen}
                          >
                            <Flag iso={country.iso} />
                            <span className="truncate text-[12px] font-medium text-neutral-800">
                              {country.name}
                            </span>
                            <ChevronDown className="ml-auto h-3.5 w-3.5 shrink-0 text-neutral-400" />
                          </button>
                          {countryOpen && (
                            <ul className="absolute left-0 top-[calc(100%+6px)] z-20 max-h-56 w-[240px] overflow-y-auto rounded-2xl border border-neutral-200 bg-neutral-950 p-1.5 text-white shadow-2xl">
                              {COUNTRIES.map((c) => (
                                <li key={c.code}>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setCountry(c);
                                      setCountryOpen(false);
                                    }}
                                    className={cn(
                                      "flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-[13px] hover:bg-white/10",
                                      c.code === country.code && "bg-white/10"
                                    )}
                                  >
                                    <Flag iso={c.iso} className="ring-white/20" />
                                    <span className="min-w-0 flex-1 truncate">{c.name}</span>
                                    <span className="text-[11px] text-white/50">{c.dial}</span>
                                    {c.code === country.code && (
                                      <Check className="h-3.5 w-3.5 text-emerald-400" />
                                    )}
                                  </button>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                        <div className="relative min-w-0 flex-1">
                          <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-sm font-medium text-neutral-400">
                            {country.dial}
                          </span>
                          <Input
                            type="tel"
                            inputMode="tel"
                            autoComplete="tel-national"
                            placeholder="11 99999-9999"
                            value={localPhone}
                            onChange={(e) => setLocalPhone(e.target.value)}
                            required
                            className="h-11 rounded-full border-neutral-200 pl-14 pr-4"
                          />
                        </div>
                      </div>
                      <p className="text-[11px] text-neutral-400">
                        Selecione o país e digite o DDD + número.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      <label className="text-[13px] font-medium text-neutral-700" htmlFor="otp">
                        Código de 6 dígitos
                      </label>
                      <Input
                        id="otp"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={6}
                        placeholder="000000"
                        value={code}
                        onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                        required
                        className="h-12 rounded-full border-neutral-200 px-4 text-center text-lg tracking-[0.35em]"
                      />
                    </div>
                  )}

                  <Button
                    type="submit"
                    disabled={loading}
                    className="h-11 w-full rounded-full bg-[#25D366] text-white hover:bg-[#1ebe57]"
                  >
                    <WhatsAppMark className="h-4 w-4 brightness-0 invert" />
                    {loading
                      ? whatsappStep === "phone"
                        ? "Enviando…"
                        : "Validando…"
                      : whatsappStep === "phone"
                        ? "Enviar código no WhatsApp"
                        : "Confirmar e entrar"}
                  </Button>

                  <button
                    type="button"
                    onClick={() => {
                      if (whatsappStep === "code") {
                        setWhatsappStep("phone");
                        setCode("");
                        setNotice(null);
                        setError(null);
                      } else {
                        changeMode("password");
                      }
                    }}
                    className="flex w-full items-center justify-center gap-2 text-sm text-neutral-500 hover:text-neutral-900"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    {whatsappStep === "code" ? "Trocar número" : "Voltar"}
                  </button>
                </form>
              )}

              {mode === "forgot" && (
                <form onSubmit={onForgotSubmit} className="space-y-3.5">
                  <div className="space-y-1.5">
                    <label className="text-[13px] font-medium text-neutral-700" htmlFor="recovery">
                      E-mail institucional
                    </label>
                    <Input
                      id="recovery"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      className="h-11 rounded-full border-neutral-200 px-4"
                      placeholder="voce@instituicao.edu.br"
                    />
                  </div>
                  <Button
                    type="submit"
                    disabled={loading}
                    className="h-11 w-full rounded-full bg-neutral-950 text-white hover:bg-neutral-800"
                  >
                    <KeyRound className="h-4 w-4" />
                    {loading ? "Enviando…" : "Enviar instruções"}
                  </Button>
                  <button
                    type="button"
                    onClick={() => changeMode("password")}
                    className="flex w-full items-center justify-center gap-2 text-sm text-neutral-500 hover:text-neutral-900"
                  >
                    <ArrowLeft className="h-4 w-4" /> Voltar ao login
                  </button>
                </form>
              )}
            </div>

            <p className="mt-8 text-center text-[11px] text-neutral-400">
              Acesso protegido e vinculado à sua instituição.
            </p>
          </section>

          <section className="relative hidden min-h-[560px] md:block">
            <Image src="/login-art.svg" alt="" fill className="object-cover" priority />
            <div className="absolute inset-0 bg-gradient-to-t from-black/30 via-transparent to-white/10" />
            <div className="absolute bottom-8 left-8 right-8">
              <p className="max-w-xs text-sm font-medium leading-relaxed text-neutral-900/80">
                Clareza para agir. Presença para cuidar da permanência estudantil.
              </p>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
