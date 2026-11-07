"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, Check, LockKeyhole, Mail, ShieldCheck } from "@/components/ui/icons";

type Mode = "identify" | "register" | "code" | "profile";
type Profile = {
  authenticated: boolean;
  email: string;
  whatsapp: string;
  identity_verified: boolean;
  requires_identity_verification: boolean;
  debts_available: boolean;
};
const common = "h-12 w-full rounded-xl border border-slate-200 bg-white px-4 text-base outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100";

async function requestApi<T>(path: string, method: "GET" | "POST" = "GET", body?: unknown): Promise<T> {
  const response = await fetch("/api/v1/global-portal" + path, {
    method, credentials: "same-origin", cache: "no-store",
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(method === "POST" ? { "X-Mira-Global-Portal-Action": "1" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    const message = response.status === 429 ? "Muitas tentativas. Tente novamente mais tarde."
      : response.status === 503 ? "Acesso temporariamente indisponível."
      : response.status === 401 ? "Código inválido ou expirado."
      : "Não foi possível concluir esta etapa. Confira os dados e tente novamente.";
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export default function GlobalStudentAccessPage() {
  const [step, setStep] = useState<Mode>("identify");
  const [cpf, setCpf] = useState("");
  const [email, setEmail] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [code, setCode] = useState("");
  const [purpose, setPurpose] = useState<"login" | "register">("login");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    void requestApi<Profile>("/auth/me").then(value => {
      if (active && value.authenticated) { setProfile(value); setStep("profile"); }
    }).catch(() => {}).finally(() => {});
    return () => { active = false; };
  }, []);

  const validCpf = cpf.replace(/\D/g, "").length === 11;
  function back() { setError(""); setNotice(""); setCode(""); setStep(step === "code" ? (purpose === "register" ? "register" : "identify") : "identify"); }
  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!validCpf || working) return;
    setError(""); setNotice(""); setWorking(true);
    try {
      if (step === "register") {
        await requestApi("/auth/register/request", "POST", { cpf, email, whatsapp });
        setPurpose("register");
      } else {
        await requestApi("/auth/login/request", "POST", { cpf });
        setPurpose("login");
      }
      setNotice("Se os dados estiverem corretos, enviaremos um código para o e-mail cadastrado.");
      setStep("code");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível continuar.");
    } finally { setWorking(false); }
  }
  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!/^\d{6}$/.test(code) || working) return;
    setWorking(true); setError("");
    try {
      await requestApi("/auth/verify", "POST", { cpf, code });
      const next = await requestApi<Profile>("/auth/me");
      setProfile(next); setStep("profile"); setCode("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível validar o código.");
    } finally { setWorking(false); }
  }
  async function logout() {
    setWorking(true); setError("");
    try { await requestApi("/auth/logout", "POST"); } catch { /* Session may already have expired. */ }
    setProfile(null); setCpf(""); setEmail(""); setWhatsapp(""); setCode(""); setStep("identify"); setWorking(false);
  }
  const isRegister = step === "register";
  const isCode = step === "code";
  const isProfile = step === "profile";

  return (
    <main className="min-h-dvh bg-slate-50 text-slate-900">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-6 sm:px-8">
        <a href="/portal/acesso" className="text-3xl font-semibold tracking-[-0.09em]">mira<span className="text-blue-600">.</span></a>
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600">
          <ShieldCheck size={15} /> Ambiente protegido
        </span>
      </header>

      <section className="mx-auto grid max-w-6xl gap-12 px-5 pb-24 pt-8 sm:px-8 md:grid-cols-[1fr_450px] md:items-center md:pt-24">
        <div className="max-w-lg">
          <span className="text-xs font-semibold uppercase tracking-[0.15em] text-blue-600">Portal MIRA</span>
          <h1 className="mt-5 text-4xl font-semibold leading-[1.13] tracking-[-0.055em] sm:text-5xl">
            Sua vida financeira estudantil, em um só lugar.
          </h1>
          <p className="mt-5 text-base leading-7 text-slate-600">
            Um único acesso para acompanhar negociações com instituições participantes.
            Seus dados permanecem protegidos em cada etapa.
          </p>
          <div className="mt-9 grid gap-4 text-sm text-slate-600">
            <div className="flex items-center gap-3"><Check className="text-emerald-600" size={17}/> Um acesso para instituições participantes</div>
            <div className="flex items-center gap-3"><Check className="text-emerald-600" size={17}/> Confirmação de e-mail e verificação de identidade</div>
            <div className="flex items-center gap-3"><Check className="text-emerald-600" size={17}/> Nenhuma dívida exibida antes da autorização</div>
          </div>
        </div>
        <section className="rounded-[24px] border border-slate-200 bg-white p-6 shadow-[0_24px_60px_rgba(15,23,42,0.06)] sm:p-9" aria-label="Acesso ao Portal MIRA">
          {!isProfile && (
            <>
              {step !== "identify" && (
                <button type="button" onClick={back} disabled={working}
                  className="mb-6 inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900">
                  <ArrowLeft size={16}/> Voltar
                </button>
              )}
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-blue-50 text-blue-600">
                {isCode ? <Mail size={23}/> : <LockKeyhole size={23}/>}
              </span>
              <h2 className="mt-6 text-2xl font-semibold leading-tight tracking-[-0.04em]">
                {isCode ? "Confirme seu e-mail" : isRegister ? "Crie sua conta" : "Acesse o Portal MIRA"}
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                {isCode ? "Digite o código de seis dígitos enviado ao e-mail informado ou cadastrado."
                  : isRegister ? "Informe seus dados de contato para solicitar a validação por e-mail."
                  : "Informe seu CPF para entrar ou criar uma conta."}
              </p>
            </>
          )}

          {(step === "identify" || isRegister) && (
            <form className="mt-7 space-y-4" onSubmit={start}>
              <div><label htmlFor="global-cpf" className="mb-2 block text-sm font-medium">CPF</label>
                <input id="global-cpf" autoComplete="off" inputMode="numeric" required maxLength={14}
                  value={cpf} onChange={event => setCpf(event.target.value)} placeholder="000.000.000-00" className={common}/>
              </div>
              {isRegister && (<>
                <div><label htmlFor="global-email" className="mb-2 block text-sm font-medium">E-mail</label>
                  <input id="global-email" type="email" autoComplete="email" required maxLength={255}
                    value={email} onChange={event => setEmail(event.target.value)} placeholder="voce@exemplo.com" className={common}/>
                </div>
                <div><label htmlFor="global-whatsapp" className="mb-2 block text-sm font-medium">WhatsApp com DDD</label>
                  <input id="global-whatsapp" type="tel" autoComplete="tel" required placeholder="55 21 99999-9999"
                    value={whatsapp} onChange={event => setWhatsapp(event.target.value)} className={common}/>
                </div>
              </>)}
              {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
              <button className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
                disabled={!validCpf || working} type="submit">
                {working ? "Continuando…" : isRegister ? "Criar conta" : "Receber código"} <ArrowRight size={16}/>
              </button>
              {step === "identify" && <button type="button" onClick={() => {setError("");setStep("register");}}
                className="h-11 w-full rounded-xl border border-slate-200 text-sm font-semibold text-slate-700 hover:bg-slate-50">
                Ainda não tenho cadastro
              </button>}
              {isRegister && <p className="text-xs leading-5 text-slate-500">Validar o e-mail não comprova a titularidade do CPF. Uma verificação adicional será necessária para acessar informações financeiras.</p>}
            </form>
          )}
          {isCode && (
            <form className="mt-7 space-y-5" onSubmit={verify}>
              {notice && <p role="status" className="rounded-xl bg-blue-50 p-3 text-xs leading-5 text-blue-800">{notice}</p>}
              <div><label htmlFor="global-code" className="mb-2 block text-sm font-medium">Código recebido por e-mail</label>
                <input id="global-code" autoComplete="one-time-code" inputMode="numeric" required
                  maxLength={6} pattern="[0-9]{6}" value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ""))}
                  placeholder="000000" className={common + " text-center text-xl tracking-[0.35em]"}/>
              </div>
              {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
              <button disabled={code.length !== 6 || working} type="submit"
                className="h-12 w-full rounded-xl bg-blue-600 font-semibold text-white hover:bg-blue-700 disabled:opacity-50">
                {working ? "Validando…" : "Validar código"}
              </button>
              <p className="text-center text-xs text-slate-500">O código é válido por cinco minutos e só pode ser usado uma vez.</p>
            </form>
          )}
          {isProfile && profile && (
            <div className="mt-1 space-y-5">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-50 text-emerald-700"><Check size={24}/></span>
              <h2 className="text-2xl font-semibold tracking-[-0.04em]">Seu acesso está ativo</h2>
              <p className="text-sm text-slate-600">{profile.email}</p>
              {profile.identity_verified ? (
                <p className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
                  Identidade confirmada. A consulta às instituições será disponibilizada em uma próxima etapa.
                </p>
              ) : (
                <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
                  E-mail confirmado. A verificação independente de titularidade do CPF ainda está pendente.
                  Nenhuma dívida ou acordo ficará disponível antes dessa verificação.
                </p>
              )}
              <p className="text-xs leading-5 text-slate-500">As consultas e negociações com instituições participantes serão disponibilizadas nas próximas etapas do Portal MIRA.</p>
              <button type="button" onClick={() => void logout()} disabled={working}
                className="h-12 w-full rounded-xl border border-slate-200 text-sm font-semibold hover:bg-slate-50">
                Sair da conta
              </button>
            </div>
          )}
          <div className="mt-7 flex items-start gap-2 border-t border-slate-100 pt-5 text-xs leading-5 text-slate-500">
            <ShieldCheck size={15} className="mt-0.5 shrink-0"/> A MIRA não solicita pagamento para confirmar seu cadastro.
          </div>
        </section>
      </section>
    </main>
  );
}
