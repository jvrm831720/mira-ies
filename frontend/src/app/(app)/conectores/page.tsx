"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { LoaderCircle, Plug, UploadCloud } from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

export default function ConectoresPage() {
  const catalog = useQuery({
    queryKey: ["connectors"],
    queryFn: () => api.listConnectors(),
    retry: false,
  });
  const [selected, setSelected] = useState<string>("generic");
  const [payload, setPayload] = useState("{\n  \"students\": []\n}");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  async function onIngest() {
    setLoading(true);
    setResult(null);
    try {
      const json = JSON.parse(payload);
      const res = await api.ingestConnector(selected, json, true);
      setResult(JSON.stringify(res, null, 2));
      toast.success("Dados recebidos pelo conector");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Falha na ingestão");
    } finally {
      setLoading(false);
    }
  }

  const items = catalog.data?.connectors ?? [];

  return (
    <>
      <Header
        title="Conectores"
        subtitle="Integre ERP e LMS ou envie um payload JSON canônico."
      />
      <main className="mx-auto w-full max-w-5xl space-y-6 px-4 pb-10 pt-5 md:px-9 md:pt-7">
        <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Fontes disponíveis</CardTitle>
              <CardDescription>Escolha o conector da instituição.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {catalog.isLoading && <p className="text-xs text-muted-foreground">Carregando…</p>}
              {items.length === 0 && !catalog.isLoading && (
                <p className="text-xs text-muted-foreground">
                  Catálogo indisponível. Você ainda pode usar o conector genérico abaixo.
                </p>
              )}
              {(items.length
                ? items
                : [{ id: "generic", name: "Genérico", category: "generic", description: "JSON canônico" }]
              ).map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setSelected(c.id)}
                  className={`flex w-full items-start gap-2 rounded-xl border px-3 py-2.5 text-left text-sm transition ${
                    selected === c.id
                      ? "border-primary/40 bg-secondary"
                      : "border-border hover:bg-muted/40"
                  }`}
                >
                  <Plug className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span>
                    <span className="block font-semibold">{c.name}</span>
                    <span className="mt-0.5 block text-[11px] text-muted-foreground">
                      {c.category || "—"} · {c.description || c.id}
                    </span>
                  </span>
                </button>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Enviar payload · {selected}</CardTitle>
              <CardDescription>
                Cole o JSON do ERP/LMS. Telefone e e-mail são mapeados automaticamente pelos
                conectores (JACAD, Sponte, SophiA, GVcollege, WPensar, Moodle, Canvas).
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <textarea
                value={payload}
                onChange={(e) => setPayload(e.target.value)}
                rows={14}
                className="w-full rounded-xl border border-input bg-background p-3 font-mono text-xs outline-none focus:ring-2 focus:ring-primary/25"
              />
              <Button onClick={onIngest} disabled={loading}>
                {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
                {loading ? "Processando…" : "Ingerir e pontuar"}
              </Button>
              {result && (
                <pre className="overflow-x-auto rounded-xl bg-muted/40 p-3 text-[11px]">{result}</pre>
              )}
            </CardContent>
          </Card>
        </div>
      </main>
    </>
  );
}
