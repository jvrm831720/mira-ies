"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Fingerprint, KeyRound, LoaderCircle, LockKeyhole, Mail, ShieldCheck } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const SESSION_KEY = "mira_control_center_token";
const SESSION_ROLE_KEY = "mira_control_center_role";

type LoginResponse = { message?: string; expires_in?: number };
type SessionResponse = { access_token: string; token_type: string; expires_in: number; role: string };

async function post<T>(path: string, body: Record<string, string>): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/admin/control-center/auth/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new Error("Não foi possível conectar à API. Confira a URL do backend e tente novamente.");
  }

  const payload = (await response.json().catch(() => ({}))) as {
    detail?: string | Array<{ msg?: string }>;
    message?: string;
  };
  if (!response.ok) {
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((item) => item.msg || "Dados inválidos").join(". ")
      : payload.detail;
    throw new Error(detail || payload.message || "Não foi possível concluir a solicitação.");
  }
  return payload as T;
}


export default function ControlCenterLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"credentials" | "mfa">("credentials");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function submitCredentials(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    setLoading(true);
    try {
      const result = await post<LoginResponse>("login", {
        email: email.trim().toLowerCase(),
        password,
      });
      setPassword("");
      setStep("mfa");
      setNotice(result.message || "Se as credenciais forem válidas, enviaremos um código de acesso.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível iniciar o login.");
    } finally {
      setLoading(false);
    }
  }

  async function submitCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    setLoading(true);
    try {
      const result = await post<SessionResponse>("verify", {
        email: email.trim().toLowerCase(),
        code: code.trim(),
      });
      // Admin session is deliberately isolated from the regular MIRA user/API-key session.
      // sessionStorage limits persistence to this browser tab; do not store credentials or OTPs.
      window.sessionStorage.setItem(SESSION_KEY, result.access_token);
      window.sessionStorage.setItem(SESSION_ROLE_KEY, result.role);
      setCode("");
      router.replace("/control-center");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Código inválido ou expirado.");
    } finally {
      setLoading(false);
    }
  }

  function restart() {
    setError("");
    setNotice("");
    setCode("");
    setPassword("");
    setStep("credentials");
  }


  return (
    <main className="min-h-screen px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-6xl items-center justify-center">
        <div className="grid w-full overflow-hidden rounded-[2rem] border border-black/5 bg-white shadow-[0_28px_100px_rgba(27,31,48,0.12)] lg:min-h-[640px] lg:grid-cols-[0.95fr_1.05fr]">
          <aside className="relative hidden flex-col justify-between overflow-hidden bg-[#17191d] p-10 text-white lg:flex xl:p-14">
            <div className="absolute -right-24 -top-20 h-80 w-80 rounded-full bg-[#4050cd]/40 blur-3xl" />
            <div className="absolute -bottom-32 -left-20 h-80 w-80 rounded-full bg-[#f47769]/20 blur-3xl" />
            <div className="relative">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-[#4050cd]">
                  <Fingerprint size={24} strokeWidth={2.3} />
                </div>
                <div>
                  <p className="text-lg font-semibold tracking-tight">MIRA</p>
                  <p className="text-xs uppercase tracking-[0.22em] text-white/55">Control Center</p>
                </div>
              </div>
              <div className="mt-24 max-w-md">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[#aeb7ff]">Acesso interno</p>
                <h1 className="mt-5 text-4xl font-semibold leading-[1.12] tracking-tight xl:text-5xl">
                  Controle operacional. Segurança em cada acesso.
                </h1>
                <p className="mt-6 max-w-sm text-base leading-7 text-white/65">
                  Um ambiente reservado para administrar operações, instituições e configurações da plataforma MIRA.
                </p>
              </div>
            </div>
            <div className="relative flex items-center gap-2 text-sm text-white/55">
              <LockKeyhole size={16} />
              <span>Autenticação em duas etapas obrigatória</span>
            </div>
          </aside>

          <section className="flex items-center justify-center p-6 sm:p-10 lg:p-12 xl:p-16">
            <div className="w-full max-w-md">
              <div className="mb-10 flex items-center gap-3 lg:hidden">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#4050cd] text-white">
                  <Fingerprint size={24} />
                </div>
                <div>
                  <p className="font-semibold tracking-tight">MIRA</p>
                  <p className="text-xs uppercase tracking-[0.2em] text-neutral-500">Control Center</p>
                </div>
              </div>

                            <>
                  <div className="mb-8 flex h-12 w-12 items-center justify-center rounded-2xl bg-[#eef0ff] text-[#4050cd]">
                    {step === "credentials" ? <KeyRound size={23} /> : <ShieldCheck size={23} />}
                  </div>
                  <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[#4050cd]">
                    {step === "credentials" ? "Área restrita" : "Verificação de segurança"}
                  </p>
                  <h2 className="mt-3 text-3xl font-semibold tracking-tight text-neutral-950">
                    {step === "credentials" ? "Entre no Control Center" : "Confirme sua identidade"}
                  </h2>
                  <p className="mt-3 leading-6 text-neutral-600">
                    {step === "credentials"
                      ? "Use sua conta administrativa. Depois da senha, enviaremos um código de uso único para seu e-mail."
                      : <>Informe o código de seis dígitos enviado para <span className="font-medium text-neutral-900">{email}</span>.</>}
                  </p>

                  {error && (
                    <div role="alert" className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-5 text-red-800">
                      {error}
                    </div>
                  )}
                  {notice && (
                    <div role="status" className="mt-6 rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm leading-5 text-blue-900">
                      {notice}
                    </div>
                  )}

                  {step === "credentials" ? (
                    <form className="mt-7 space-y-5" onSubmit={submitCredentials}>
                      <div>
                        <label htmlFor="admin-email" className="mb-2 block text-sm font-medium text-neutral-800">E-mail administrativo</label>
                        <div className="relative">
                          <Mail size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-neutral-400" />
                          <input id="admin-email" type="email" autoComplete="username" required maxLength={255} value={email} onChange={(event) => setEmail(event.target.value)} placeholder="voce@empresa.com.br" className="h-12 w-full rounded-xl border border-neutral-200 bg-white pl-11 pr-4 text-sm outline-none transition placeholder:text-neutral-400 focus:border-[#4050cd] focus:ring-4 focus:ring-[#4050cd]/10" />
                        </div>
                      </div>
                      <div>
                        <label htmlFor="admin-password" className="mb-2 block text-sm font-medium text-neutral-800">Senha</label>
                        <div className="relative">
                          <LockKeyhole size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-neutral-400" />
                          <input id="admin-password" type="password" autoComplete="current-password" required maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} className="h-12 w-full rounded-xl border border-neutral-200 bg-white pl-11 pr-4 text-sm outline-none transition focus:border-[#4050cd] focus:ring-4 focus:ring-[#4050cd]/10" />
                        </div>
                      </div>
                      <button type="submit" disabled={loading} className="flex h-12 w-full items-center justify-center gap-2 rounded-full bg-[#4050cd] px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#3442b5] disabled:cursor-not-allowed disabled:opacity-60">
                        {loading ? <><LoaderCircle size={17} className="animate-spin" /> Validando...</> : <>Continuar com segurança <ArrowLeft size={17} className="rotate-180" /></>}
                      </button>
                    </form>
                  ) : (
                    <form className="mt-7 space-y-5" onSubmit={submitCode}>
                      <div>
                        <label htmlFor="mfa-code" className="mb-2 block text-sm font-medium text-neutral-800">Código de verificação</label>
                        <input id="mfa-code" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required autoFocus value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="000000" aria-describedby="mfa-hint" className="h-14 w-full rounded-xl border border-neutral-200 bg-white px-4 text-center font-mono text-2xl tracking-[0.45em] outline-none transition placeholder:text-neutral-300 focus:border-[#4050cd] focus:ring-4 focus:ring-[#4050cd]/10" />
                        <p id="mfa-hint" className="mt-2 text-xs leading-5 text-neutral-500">O código expira em 5 minutos e só pode ser usado uma vez.</p>
                      </div>
                      <button type="submit" disabled={loading || code.length !== 6} className="flex h-12 w-full items-center justify-center gap-2 rounded-full bg-[#4050cd] px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#3442b5] disabled:cursor-not-allowed disabled:opacity-60">
                        {loading ? <><LoaderCircle size={17} className="animate-spin" /> Verificando...</> : <><ShieldCheck size={17} /> Verificar código</>}
                      </button>
                      <button type="button" disabled={loading} onClick={restart} className="w-full rounded-full px-4 py-3 text-sm font-medium text-neutral-600 transition hover:bg-neutral-100 hover:text-neutral-900">
                        Voltar e informar outra conta
                      </button>
                    </form>
                  )}

                  <div className="mt-8 border-t border-neutral-100 pt-5">
                    <p className="text-center text-xs leading-5 text-neutral-500">
                      Acesso exclusivo para equipe autorizada. Nunca compartilhe sua senha ou código de verificação.
                    </p>
                  </div>
              </>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
