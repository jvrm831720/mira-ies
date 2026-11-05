"use client";

import { FormEvent, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { LoaderCircle, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { getAccessToken, setAccessToken } from "@/lib/auth";

export default function AcceptInvitePage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const token = params.token;

  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [phone, setPhone] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(false);
  const [mfaSetupTicket, setMfaSetupTicket] = useState("");
  const [mfaEnrollment, setMfaEnrollment] = useState<{secret:string; qr_code:string} | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (password.length < 8) {
      toast.error("A senha deve ter pelo menos 8 caracteres");
      return;
    }
    if (password !== password2) {
      toast.error("As senhas não coincidem");
      return;
    }
    if (!phone.trim()) {
      toast.error("Informe um telefone para contato");
      return;
    }
    setLoading(true);
    try {
      const res = await api.acceptInvite({
        token,
        password,
        phone: phone.trim(),
        display_name: displayName.trim() || undefined,
      });
      if ("mfa_enrollment_required" in res && res.mfa_enrollment_required) {
        setMfaSetupTicket(res.challenge_token);
        const enrollment = await api.beginRequiredMfaEnrollment(res.challenge_token);
        setMfaEnrollment(enrollment);
        toast.message("A instituição exige MFA. Configure seu aplicativo autenticador para concluir o acesso.");
        return;
      }
      if ("access_token" in res && res.access_token) {
        setAccessToken(res.access_token);
      }
      toast.success("Conta criada. Bem-vindo à organização!");
      router.replace("/");
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Não foi possível concluir o convite. Verifique o link ou peça um novo.";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  async function acceptWithExistingAccount() {
    if (!getAccessToken()) {
      router.push(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      return;
    }
    setLoading(true);
    try {
      const result = await api.acceptExistingInvite({ token });
      setAccessToken(result.access_token);
      toast.success("Convite aceito. Você já está no workspace da instituição.");
      router.replace("/");
    } catch (err) {
      toast.error(
        err instanceof ApiError
          ? err.message
          : "Não foi possível aceitar o convite com esta conta."
      );
    } finally {
      setLoading(false);
    }
  }

  async function confirmRequiredMfa() {
    setLoading(true);
    try {
      const result = await api.confirmRequiredMfaEnrollment(mfaSetupTicket, mfaCode);
      setAccessToken(result.access_token);
      setRecoveryCodes(result.recovery_codes);
      setMfaEnrollment(null);
      setMfaCode("");
      toast.success("MFA ativado. Guarde os códigos de recuperação.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível concluir a configuração do MFA.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_#eef0ff,_#f8f9fc_55%)] p-4">
      <Card className="w-full max-w-md border-border/80 shadow-soft">
        <CardHeader>
          <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-secondary px-3 py-1 text-[11px] font-medium text-primary">
            <ShieldCheck className="h-3.5 w-3.5" /> Convite Mira
          </div>
          <CardTitle>Ative seu acesso</CardTitle>
          <CardDescription>
            Defina sua senha e telefone para entrar na organização convidada.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {recoveryCodes ? (
            <div className="space-y-4">
              <p className="text-sm font-semibold text-amber-900">Guarde seus códigos de recuperação</p>
              <p className="text-xs text-amber-800">Cada código pode ser usado uma única vez. Eles não serão exibidos novamente.</p>
              <div className="grid grid-cols-2 gap-2">{recoveryCodes.map((item) => <code key={item} className="rounded bg-amber-50 p-2 text-center text-xs">{item}</code>)}</div>
              <Button type="button" variant="outline" onClick={() => navigator.clipboard.writeText(recoveryCodes.join("\\n"))}>Copiar códigos</Button>
              <Button type="button" className="w-full" onClick={() => router.replace("/")}>Já guardei — entrar</Button>
            </div>
          ) : mfaEnrollment ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">Esta instituição exige autenticação multifator. Escaneie o QR Code no Google Authenticator, Microsoft Authenticator ou 1Password.</p>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={mfaEnrollment.qr_code} alt="QR Code para configurar MIRA no aplicativo autenticador" className="mx-auto h-48 w-48" />
              <p className="break-all rounded-lg bg-muted p-2 font-mono text-xs">{mfaEnrollment.secret}</p>
              <Input value={mfaCode} onChange={(e) => setMfaCode(e.target.value.replace(/\\D/g, "").slice(0,6))} inputMode="numeric" placeholder="Código de 6 dígitos" maxLength={6} />
              <Button type="button" className="w-full" onClick={confirmRequiredMfa} disabled={loading || mfaCode.length !== 6}>
                {loading ? "Confirmando…" : "Ativar MFA e concluir acesso"}
              </Button>
            </div>
          ) : (
          <div className="space-y-4">
          <Button type="button" variant="outline" className="w-full" onClick={acceptWithExistingAccount} disabled={loading}>
            {getAccessToken() ? "Aceitar com minha conta existente" : "Já tenho conta — entrar e aceitar"}
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            Ou crie um novo acesso para este convite:
          </p>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="name">
                Nome (opcional)
              </label>
              <Input
                id="name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Como prefere ser chamado"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="phone">
                Telefone
              </label>
              <Input
                id="phone"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="(11) 99999-9999"
                autoComplete="tel"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="password">
                Nova senha
              </label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="password2">
                Confirmar senha
              </label>
              <Input
                id="password2"
                type="password"
                value={password2}
                onChange={(e) => setPassword2(e.target.value)}
                autoComplete="new-password"
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : null}
              {loading ? "Ativando…" : "Criar acesso e entrar"}
            </Button>
          </form>
          </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
