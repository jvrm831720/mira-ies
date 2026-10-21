"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

export default function RetentionLogsPage() {
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["retention-logs", channel, status],
    queryFn: () =>
      api.retentionLogs({
        limit: 100,
        channel: channel || undefined,
        status: status || undefined,
      }),
  });

  return (
    <>
      <Header title="Logs de retenção" subtitle="Envio imediato e entrega assíncrona por provider" />
      <main className="space-y-4 p-4 md:p-8">
        <div className="flex flex-wrap gap-3">
          <select
            className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
          >
            <option value="">Todos os canais</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="email">E-mail</option>
            <option value="sms">SMS</option>
          </select>
          <select
            className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">Todos os status</option>
            <option value="dry_run">dry_run</option>
            <option value="sent">sent</option>
            <option value="sending">sending</option>
            <option value="unknown">unknown</option>
            <option value="skipped">skipped</option>
            <option value="failed">failed</option>
            <option value="planned">planned</option>
          </select>
        </div>

        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/40 text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3">Quando</th>
                    <th className="px-4 py-3">Matrícula</th>
                    <th className="px-4 py-3">Canal</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Entrega</th>
                    <th className="px-4 py-3">Preview</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading &&
                    Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i}>
                        <td className="px-4 py-3" colSpan={6}>
                          <Skeleton className="h-5 w-full" />
                        </td>
                      </tr>
                    ))}
                  {!isLoading && (data?.logs?.length ?? 0) === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                        Nenhum log ainda. Rode uma simulação em Retenção.
                      </td>
                    </tr>
                  )}
                  {!isLoading &&
                    data?.logs?.map((log) => (
                      <tr key={log.id} className="border-b border-border/70">
                        <td className="px-4 py-3 text-xs text-muted-foreground">
                          {log.created_at
                            ? new Date(log.created_at).toLocaleString("pt-BR")
                            : "—"}
                        </td>
                        <td className="px-4 py-3 font-medium">{log.matricula || "—"}</td>
                        <td className="px-4 py-3">{log.channel || "—"}</td>
                        <td className="px-4 py-3">
                          <span className="rounded-full bg-muted px-2 py-0.5 text-xs">{log.status}</span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="rounded-full bg-muted px-2 py-0.5 text-xs">
                            {log.delivery_status || "—"}
                          </span>
                        </td>
                        <td className="max-w-xs truncate px-4 py-3 text-xs text-muted-foreground">
                          {log.message_preview || log.skip_reason || log.error || "—"}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </main>
    </>
  );
}
