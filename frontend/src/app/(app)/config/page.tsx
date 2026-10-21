"use client";

import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { clearAuth } from "@/lib/auth";
import { copy } from "@/lib/copy";

export default function ConfigPage() {
  const router = useRouter();
  const status = useQuery({ queryKey: ["agents-status"], queryFn: () => api.agentsStatus() });
  const model = useQuery({
    queryKey: ["model-info"],
    queryFn: () => api.modelInfo(),
    retry: false,
  });

  function logout() {
    clearAuth();
    toast.message("Sessão encerrada neste dispositivo");
    router.replace("/login");
  }

  return (
    <>
      <Header title="Configurações" subtitle="Canais, modelo e sessão" />
      <main className="mx-auto max-w-3xl space-y-6 p-4 md:p-8">
        <Card>
          <CardHeader>
            <CardTitle>Agentes de retenção</CardTitle>
            <CardDescription>Estado dos providers (sem expor secrets)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>
              Dry-run padrão:{" "}
              <strong>{status.data?.dry_run_default ? "sim" : status.isLoading ? "..." : "não"}</strong>
            </p>
            <p>
              Anti-spam: {status.data?.anti_spam.min_hours_between_contact ?? "—"}h entre contatos · máx.{" "}
              {status.data?.anti_spam.max_contacts_per_week ?? "—"}/semana
            </p>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              <li>WhatsApp: {status.data?.providers.whatsapp ?? "—"}</li>
              <li>E-mail: {status.data?.providers.email ?? "—"}</li>
              <li>SMS: {status.data?.providers.sms ?? "—"}</li>
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Modelo preditivo</CardTitle>
            <CardDescription>Transparência para a coordenação</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Status: {model.data?.status ?? "indisponível"}</p>
            <p>Escopo: {model.data?.model_scope ?? "—"}</p>
            <p>Dados de treino: {model.data?.training_data ?? "—"}</p>
            <p className="rounded-lg bg-muted/50 p-3 text-foreground">
              {model.data?.disclaimer || copy.modelDisclaimerFallback}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Sessão</CardTitle>
            <CardDescription>Token de acesso armazenado apenas neste navegador</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" onClick={logout}>
              Sair e limpar sessão
            </Button>
          </CardContent>
        </Card>
      </main>
    </>
  );
}
