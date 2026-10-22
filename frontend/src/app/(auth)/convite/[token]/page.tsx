"use client";

import { FormEvent, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { LoaderCircle, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";

export default function AcceptInvitePage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const token = params.token;

  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [phone, setPhone] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(false);

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
      if (res.access_token) {
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
        </CardContent>
      </Card>
    </div>
  );
}
