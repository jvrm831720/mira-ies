"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Header } from "@/components/layout/header";
import { dispatchApi, type DispatchTemplate } from "@/lib/dispatch-api";

type Purpose = DispatchTemplate["purpose"];
type Channel = DispatchTemplate["channel"];
export default function MessageTemplatesPage() {
  const [templates, setTemplates] = useState<DispatchTemplate[]>([]);
  const [code, setCode] = useState("");
  const [purpose, setPurpose] = useState<Purpose>("retention");
  const [channel, setChannel] = useState<Channel>("email");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [evidence, setEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try { setTemplates((await dispatchApi.templates()).items); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Não foi possível carregar modelos."); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  async function submit() {
    setBusy(true);
    try {
      await dispatchApi.createTemplate({ code, purpose, channel, subject, body });
      toast.success("Modelo criado para revisão.");
      setCode(""); setSubject(""); setBody(""); await refresh();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Falha ao criar modelo."); }
    finally { setBusy(false); }
  }
  async function approve(id: string) {
    if (evidence.trim().length < 8) { toast.error("Informe referência de aprovação."); return; }
    setBusy(true);
    try {
      await dispatchApi.approveTemplate(id, evidence.trim());
      toast.success("Modelo aprovado. Pode ser usado em intervenções individuais.");
      setEvidence(""); await refresh();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Aprovação não permitida."); }
    finally { setBusy(false); }
  }

  return <>
    <Header title="Modelos de comunicação" subtitle="Aprovação reutilizável para contatos individuais e campanhas" />
    <main className="mx-auto max-w-5xl space-y-5 px-4 py-6 md:px-8">
      <Link href="/disparos" className="text-sm text-[var(--color-legacy-2563eb)]">Voltar a Disparos</Link>
      <p className="text-sm text-[var(--color-legacy-85858b)]">Um segundo usuário com permissão deve aprovar o modelo. A autorização do destinatário continua obrigatória a cada envio.</p>
      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm">{error}</p>}
      <section className="space-y-4 rounded-xl border border-[var(--color-legacy-e7e7e9)] bg-white p-5">
        <h2 className="font-semibold">Novo modelo</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-xs">Identificador
            <input value={code} onChange={e=>setCode(e.target.value)} placeholder="retencao-primeiro-contato" className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm" />
          </label>
          <label className="text-xs">Finalidade
            <select value={purpose} onChange={e=>{ setPurpose(e.target.value as Purpose); if (e.target.value==="collections" && channel==="whatsapp") setChannel("email"); }}
              className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm">
              <option value="retention">Permanência</option><option value="academic">Acadêmica</option>
              <option value="service">Atendimento</option><option value="collections">Cobrança</option>
            </select>
          </label>
          <label className="text-xs">Canal
            <select value={channel} onChange={e=>setChannel(e.target.value as Channel)} className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm">
              <option value="email">E-mail</option><option value="sms">SMS</option>
              {purpose !== "collections" && <option value="whatsapp">WhatsApp (simulado)</option>}
            </select>
          </label>
        </div>
        <label className="block text-xs">Assunto ou referência
          <input value={subject} onChange={e=>setSubject(e.target.value)} className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm" />
        </label>
        <label className="block text-xs">Conteúdo (campo permitido: {"{nome}"})
          <textarea value={body} onChange={e=>setBody(e.target.value)} rows={4} className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm" />
        </label>
        <button type="button" disabled={busy || code.trim().length<2 || !subject.trim() || !body.trim()}
          onClick={()=>void submit()} className="rounded-lg bg-[var(--color-legacy-202124)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Criar para aprovação</button>
      </section>
      <section className="space-y-3 rounded-xl border border-[var(--color-legacy-e7e7e9)] bg-white p-5">
        <h2 className="font-semibold">Modelos registrados</h2>
        <label className="block max-w-md text-xs">Referência da aprovação institucional
          <input value={evidence} onChange={e=>setEvidence(e.target.value)}
            placeholder="Ex.: termo-institucional-2026" className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm" />
        </label>
        {templates.length===0 && <p className="text-sm text-[var(--color-legacy-85858b)]">Nenhum modelo cadastrado.</p>}
        {templates.map(t=><div key={t.id} className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-legacy-e7e7e9)] py-3">
          <div>
            <p className="text-sm font-medium">{t.subject}</p>
            <p className="text-xs text-[var(--color-legacy-85858b)]">{t.code} · v{t.version} · {t.purpose} · {t.channel} · {t.status==="approved" ? "Aprovado" : "Aguardando revisão"}</p>
            <p className="mt-2 max-w-xl whitespace-pre-wrap text-xs leading-relaxed text-[var(--color-legacy-55555c)]">{t.body}</p>
          </div>
          {t.status==="draft" && <button type="button" disabled={busy || evidence.length<8}
            onClick={()=>void approve(t.id)} className="rounded-lg border border-[var(--color-legacy-dadadd)] px-3 py-2 text-xs font-medium disabled:opacity-50">
            Aprovar com outro usuário
          </button>}
        </div>)}
      </section>
    </main>
  </>;
}
