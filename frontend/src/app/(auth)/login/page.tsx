"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Radio, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { setApiKey } from "@/lib/auth";
import { copy } from "@/lib/copy";

export default function LoginPage() {
  const router = useRouter();
  const [key, setKey] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!key.trim()) {
      toast.error("Informe a API key");
      return;
    }
    setLoading(true);
    try {
      await api.validateKey(key.trim());
      setApiKey(key.trim());
      toast.success("Acesso liberado");
      router.replace("/");
    } catch {
      toast.error("API key inválida ou backend indisponível");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="grid w-full max-w-4xl gap-8 md:grid-cols-2 md:items-center">
        <div className="space-y-4 px-2">
          <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
            <ShieldCheck className="h-3.5 w-3.5" />
            Multi-tenant · LGPD-aware
          </div>
          <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
            {copy.productName}
          </h1>
          <p className="max-w-md text-muted-foreground">{copy.productTagline}</p>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li>• Identifique alunos em risco em segundos</li>
            <li>• Entenda os fatores com linguagem clara</li>
            <li>• Simule contatos de retenção com segurança</li>
          </ul>
        </div>

        <Card className="border-border/80">
          <CardHeader>
            <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <Radio className="h-5 w-5" />
            </div>
            <CardTitle>{copy.loginTitle}</CardTitle>
            <CardDescription>{copy.loginSubtitle}</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="apiKey">
                  API key
                </label>
                <Input
                  id="apiKey"
                  type="password"
                  autoComplete="off"
                  placeholder={copy.loginPlaceholder}
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">{copy.loginHelp}</p>
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Validando..." : copy.loginCta}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
