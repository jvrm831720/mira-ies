"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { api } from "@/lib/api";

function CompleteOAuth() {
  const params = useSearchParams();
  const [message, setMessage] = useState("Verificando a autorização com segurança…");
  const [done, setDone] = useState(false);
  const email = typeof window === "undefined" ? "" : window.sessionStorage.getItem("mira_onboarding_connect_email") || "";
  const home = email ? "/onboarding?email=" + encodeURIComponent(email) : "/apps";
  useEffect(() => {
    const state = params.get("state") || "";
    const account = params.get("connected_account_id") || params.get("connectedAccountId") || "";
    if (params.has("error") || params.get("status") === "failed") {
      setMessage("A autorização foi cancelada ou recusada pelo provedor.");
      setDone(true);
      return;
    }
    if (!state || !account) {
      setMessage("O provedor não retornou os identificadores necessários. A conexão não foi confirmada.");
      setDone(true);
      return;
    }
    let cancelled = false;
    void api.completeComposioOnboardingConnection({ state, connected_account_id: account })
      .then(() => {
        if (cancelled) return;
        setMessage("Conta autorizada e verificada. Voltando para o onboarding…");
        setDone(true);
        window.location.replace(home);
      })
      .catch(reason => {
        if (cancelled) return;
        setMessage(reason instanceof Error ? reason.message : "Não foi possível confirmar a conexão.");
        setDone(true);
      });
    return () => { cancelled = true; };
  }, [params, home]);
  return <main className="mira-flow-page">
    <div className="mira-flow-expired" role="status">
      <h1>Conexão com a MIRA</h1>
      <p>{message}</p>
      {done && <Link href={home} className="mira-flow-primary">Voltar para a MIRA</Link>}
    </div>
  </main>;
}

export default function ComposioCallbackPage() {
  return <Suspense fallback={<main className="mira-flow-page"><p role="status">Confirmando integração…</p></main>}><CompleteOAuth /></Suspense>;
}
