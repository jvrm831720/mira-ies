"use client";

import Link from "next/link";
import Image from "next/image";
import { Suspense, type FormEvent, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, KeyRound, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token")?.trim() || "";
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!token) {
      setError("O link de recuperação está incompleto ou inválido.");
      return;
    }
    if (password.length < 12) {
      setError("A nova senha deve ter pelo menos 12 caracteres.");
      return;
    }
    if (password !== confirmation) {
      setError("As senhas não conferem.");
      return;
    }

    setLoading(true);
    try {
      await api.resetPassword(token, password);
      setSuccess(true);
    } catch {
      setError("Não foi possível redefinir sua senha. Solicite um novo link e tente novamente.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4 md:p-8">
      <div className="w-full max-w-md">
        <div className="mb-8 flex justify-center">
          <div className="rounded-xl bg-slate-950 px-4 py-3">
            <Image src="/mira-logo.svg" alt="Mira" width={128} height={29} className="h-auto w-32" />
          </div>
        </div>
        <Card>
          <CardHeader>
            <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              {success ? (
                <CheckCircle2 className="h-5 w-5" aria-hidden="true" />
              ) : (
                <KeyRound className="h-5 w-5" aria-hidden="true" />
              )}
            </div>
            <CardTitle>{success ? "Senha atualizada" : "Crie uma nova senha"}</CardTitle>
            <CardDescription>
              {success
                ? "Sua senha foi redefinida com sucesso. Entre novamente para acessar a Mira."
                : "Escolha uma senha com pelo menos 12 caracteres para continuar."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {success ? (
              <Button type="button" className="w-full" onClick={() => router.replace("/login")}>
                Ir para o login
              </Button>
            ) : (
              <form onSubmit={onSubmit} className="space-y-4">
                {!token ? (
                  <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    O link de recuperação está incompleto ou inválido.
                  </p>
                ) : null}
                {error ? (
                  <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {error}
                  </p>
                ) : null}
                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="new-password">
                    Nova senha
                  </label>
                  <Input
                    id="new-password"
                    type="password"
                    autoComplete="new-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    minLength={12}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="password-confirmation">
                    Confirme a nova senha
                  </label>
                  <Input
                    id="password-confirmation"
                    type="password"
                    autoComplete="new-password"
                    value={confirmation}
                    onChange={(event) => setConfirmation(event.target.value)}
                    minLength={12}
                    required
                  />
                </div>
                <Button type="submit" className="w-full" disabled={loading || !token}>
                  {loading ? "Salvando..." : "Redefinir senha"}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
        <div className="mt-5 flex items-center justify-center gap-2 text-center text-xs text-muted-foreground">
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          <span>Se precisar, volte ao </span>
          <Link href="/login" className="font-medium text-primary underline-offset-4 hover:underline">
            login
          </Link>
        </div>
      </div>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center p-4 text-sm text-muted-foreground">
          Carregando recuperação...
        </main>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
