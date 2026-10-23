"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, Building2, CheckCircle2, CircleAlert, ClipboardList, Fingerprint, LoaderCircle, LogOut, RefreshCw, ShieldCheck, Users, Wifi, WifiOff } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "mira_control_center_token";
const ROLE_KEY = "mira_control_center_role";

type Tab = "overview" | "organizations" | "members" | "channels" | "audit" | "billing";
type Admin = { id: string; email: string; display_name: string; role: string };
type Channel = { id: string; name: string; configured: boolean; providers: string[]; note: string };
type Event = { id: string; actor_email?: string | null; action: string; result: string; reason?: string | null; created_at?: string | null; target_type?: string | null; target_id?: string | null; request_id?: string | null };
type Overview = { metrics: { organizations_total: number; organizations_active: number; members_total: number; members_active: number; admins_total: number }; channels: Channel[] };
type Organization = { id: string; name: string; slug: string; segment?: string | null; is_active: boolean; members_count: number; created_at?: string | null; model_ready: boolean };
type Member = { id: string; name: string; email: string; role: string; is_active: boolean; organization: string; created_at?: string | null };
type BillingRecord = { id: string; tenant_id: string; organization_name: string; plan_name: string; plan_price_brl: number; billing_cycle: "monthly" | "yearly"; payment_link?: string | null; due_at: string; plan_status: "active" | "paused" | "cancelled"; payment_status: "pending" | "paid"; is_overdue: boolean; days_until_due: number; notes?: string | null };
type BillingSummary = { total: number; overdue: number; due_soon: number; pending: number };

const roleLabels: Record<string, string> = { super_admin: "Super administrador", operations: "Operações", finance: "Financeiro", support: "Suporte", auditor: "Auditoria" };
const tabLabels: Record<Tab, string> = { overview: "Visão geral", organizations: "Instituições", members: "Membros", channels: "Canais", audit: "Auditoria", billing: "Financeiro" };

async function apiGet<T>(path: string, token: string): Promise<T> {
  const response = await fetch(`${API_BASE}/api/v1/admin/control-center/${path}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({})) as { detail?: string };
  if (!response.ok) {
    if (response.status === 401) throw new Error("SESSION_EXPIRED");
    if (response.status === 403) throw new Error("PERMISSION_DENIED");
    throw new Error(payload.detail || "Não foi possível carregar os dados administrativos.");
  }
  return payload as T;
}

function dateLabel(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function Metric({ label, value, note, icon: Icon }: { label: string; value: number; note: string; icon: typeof Building2 }) {
  return <article className="rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm">
    <div className="flex items-center justify-between gap-3"><span className="text-sm text-neutral-500">{label}</span><span className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-50 text-indigo-700"><Icon size={19} /></span></div>
    <p className="mt-4 text-3xl font-semibold tracking-tight text-neutral-950">{value.toLocaleString("pt-BR")}</p>
    <p className="mt-1 text-xs text-neutral-500">{note}</p>
  </article>;
}

export default function ControlCenterPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [admin, setAdmin] = useState<Admin | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [billingRecords, setBillingRecords] = useState<BillingRecord[]>([]);
  const [billingSummary, setBillingSummary] = useState<BillingSummary>({ total: 0, overdue: 0, due_soon: 0, pending: 0 });
  const [billingForm, setBillingForm] = useState({ tenant_id: "", plan_name: "MIRA Growth", plan_price_brl: "497", billing_cycle: "monthly" as "monthly" | "yearly", due_date: "", payment_link: "", notes: "" });
  const [savingBilling, setSavingBilling] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  const permissions = useMemo(() => {
    const role = admin?.role || "";
    return {
      organizations: ["super_admin", "operations", "finance", "support", "auditor"].includes(role),
      members: ["super_admin", "support"].includes(role),
      channels: ["super_admin", "operations", "support"].includes(role),
      audit: ["super_admin", "auditor"].includes(role),
      billing: ["super_admin", "finance", "auditor"].includes(role),
    };
  }, [admin?.role]);

  const signOut = useCallback(() => {
    window.sessionStorage.removeItem(TOKEN_KEY);
    window.sessionStorage.removeItem(ROLE_KEY);
    router.replace("/control-center/login");
  }, [router]);

  const loadTab = useCallback(async (currentToken: string, currentTab: Tab) => {
    setError("");
    if (currentTab === "overview") setOverview(await apiGet<Overview>("overview", currentToken));
    if (currentTab === "organizations") setOrganizations((await apiGet<{ organizations: Organization[] }>("organizations?limit=200", currentToken)).organizations);
    if (currentTab === "members") setMembers((await apiGet<{ members: Member[] }>("members?limit=200", currentToken)).members);
    if (currentTab === "audit") setEvents((await apiGet<{ events: Event[] }>("audit?limit=200", currentToken)).events);
    if (currentTab === "billing") {
      const data = await apiGet<{ records: BillingRecord[]; summary: BillingSummary }>("billing-records?limit=500", currentToken);
      setBillingRecords(data.records);
      setBillingSummary(data.summary);
      setOrganizations((await apiGet<{ organizations: Organization[] }>("organizations?limit=200", currentToken)).organizations);
    }
    if (currentTab === "channels") setOverview(await apiGet<Overview>("overview", currentToken));
  }, []);

  useEffect(() => {
    const saved = window.sessionStorage.getItem(TOKEN_KEY);
    if (!saved) { router.replace("/control-center/login"); return; }
    setToken(saved);
    apiGet<Admin>("auth/me", saved).then((me) => {
      setAdmin(me);
      const cachedRole = window.sessionStorage.getItem(ROLE_KEY);
      if (cachedRole !== me.role) window.sessionStorage.setItem(ROLE_KEY, me.role);
      setLoading(false);
    }).catch(() => signOut());
  }, [router, signOut]);

  useEffect(() => {
    if (!token || loading) return;
    void loadTab(token, tab).catch((err: unknown) => {
      if (err instanceof Error && err.message === "SESSION_EXPIRED") { signOut(); return; }
      setError(err instanceof Error && err.message === "PERMISSION_DENIED" ? "Seu perfil não tem permissão para consultar esta seção." : err instanceof Error ? err.message : "Erro ao consultar a API.");
    });
  }, [token, tab, loading, loadTab, signOut]);

  const refresh = async () => {
    if (!token) return;
    setRefreshing(true);
    try { await loadTab(token, tab); }
    catch (err) {
      if (err instanceof Error && err.message === "SESSION_EXPIRED") signOut();
      else setError(err instanceof Error ? err.message : "Não foi possível atualizar.");
    } finally { setRefreshing(false); }
  };


  async function toggleOrganization(org: Organization) {
    if (!token || admin?.role !== "super_admin") return;
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/v1/admin/control-center/organizations/${org.id}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ is_active: !org.is_active }),
      });
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "Não foi possível atualizar a instituição.");
      await loadTab(token, "organizations");
      await loadTab(token, "overview");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar instituição.");
    }
  }

  async function toggleMember(member: Member) {
    if (!token || admin?.role !== "super_admin") return;
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/v1/admin/control-center/members/${member.id}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ is_active: !member.is_active }),
      });
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "Não foi possível atualizar o membro.");
      await loadTab(token, "members");
      await loadTab(token, "overview");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar membro.");
    }
  }

  async function createBillingRecord(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !billingForm.tenant_id || !billingForm.due_date) {
      setError("Selecione a instituição e informe o vencimento.");
      return;
    }
    setSavingBilling(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/v1/admin/control-center/billing-records`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          tenant_id: billingForm.tenant_id,
          plan_name: billingForm.plan_name,
          plan_price_brl: Number(billingForm.plan_price_brl),
          billing_cycle: billingForm.billing_cycle,
          due_at: new Date(`${billingForm.due_date}T23:59:59-03:00`).toISOString(),
          payment_link: billingForm.payment_link.trim() || null,
          notes: billingForm.notes.trim() || null,
        }),
      });
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "Não foi possível salvar o registro financeiro.");
      setBillingForm((current) => ({ ...current, tenant_id: "", due_date: "", payment_link: "", notes: "" }));
      await loadTab(token, "billing");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar registro financeiro.");
    } finally {
      setSavingBilling(false);
    }
  }

  async function setPaymentStatus(record: BillingRecord, payment_status: "paid" | "pending") {
    if (!token) return;
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/v1/admin/control-center/billing-records/${record.id}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ payment_status }),
      });
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "Não foi possível atualizar o pagamento.");
      await loadTab(token, "billing");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar pagamento.");
    }
  }

  const visibleOrgs = organizations.filter((item) => [item.name, item.slug, item.segment || ""].some((value) => value.toLowerCase().includes(search.toLowerCase())));
  const visibleMembers = members.filter((item) => [item.name, item.email, item.organization, item.role].some((value) => value.toLowerCase().includes(search.toLowerCase())));
  const visibleEvents = events.filter((item) => [item.actor_email || "", item.action, item.result, item.reason || ""].some((value) => value.toLowerCase().includes(search.toLowerCase())));

  const availableTabs: Tab[] = ["overview", ...(permissions.organizations ? ["organizations" as const] : []), ...(permissions.members ? ["members" as const] : []), ...(permissions.channels ? ["channels" as const] : []), ...(permissions.audit ? ["audit" as const] : []), ...(permissions.billing ? ["billing" as const] : [])];

  if (loading || !admin) return <main className="grid min-h-screen place-items-center bg-[#f7f6f2]"><div className="flex items-center gap-3 text-sm text-neutral-600"><LoaderCircle className="animate-spin" size={18} /> Validando sessão administrativa…</div></main>;

  return <main className="min-h-screen bg-[#f7f6f2] px-4 py-6 text-neutral-900 sm:px-6 lg:px-10 lg:py-9">
    <div className="mx-auto max-w-[1500px]">
      <header className="flex flex-col gap-5 border-b border-neutral-200 pb-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-[#17191d] text-white"><Fingerprint size={24} /></div>
          <div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-700">MIRA · Interno</p><h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">Control Center</h1><p className="mt-1 text-sm text-neutral-500">Monitoramento operacional e administração da plataforma</p></div>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden text-right sm:block"><p className="text-sm font-semibold">{admin.display_name}</p><p className="text-xs text-neutral-500">{roleLabels[admin.role] || admin.role} · {admin.email}</p></div>
          <button onClick={() => void refresh()} disabled={refreshing} className="inline-flex h-10 items-center gap-2 rounded-xl border border-neutral-200 bg-white px-3 text-sm font-medium hover:bg-neutral-50 disabled:opacity-50"><RefreshCw size={15} className={refreshing ? "animate-spin" : ""} /> Atualizar</button>
          <button onClick={signOut} className="inline-flex h-10 items-center gap-2 rounded-xl bg-[#17191d] px-3 text-sm font-medium text-white hover:bg-neutral-700"><LogOut size={15} /> Sair</button>
        </div>
      </header>

      <nav aria-label="Seções administrativas" className="mt-6 flex gap-2 overflow-x-auto pb-1">
        {availableTabs.map((item) => <button key={item} onClick={() => { setSearch(""); setTab(item); }} className={`shrink-0 rounded-xl px-4 py-2.5 text-sm font-semibold transition ${tab === item ? "bg-[#4050cd] text-white shadow-sm" : "border border-neutral-200 bg-white text-neutral-600 hover:bg-neutral-100"}`}>{tabLabels[item]}</button>)}
      </nav>

      {error && <div role="alert" className="mt-5 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><CircleAlert size={18} className="mt-0.5 shrink-0" />{error}</div>}

      {tab === "overview" && <section className="mt-6 space-y-6">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Instituições" value={overview?.metrics.organizations_total ?? 0} note={`${overview?.metrics.organizations_active ?? 0} ativas`} icon={Building2} />
          <Metric label="Membros" value={overview?.metrics.members_total ?? 0} note={`${overview?.metrics.members_active ?? 0} ativos`} icon={Users} />
          <Metric label="Administradores internos" value={overview?.metrics.admins_total ?? 0} note="Contas do Control Center" icon={ShieldCheck} />
          <Metric label="Canais configurados" value={overview?.channels.filter((channel) => channel.configured).length ?? 0} note="Credenciais presentes; não é teste de conectividade" icon={Activity} />
        </div>
        <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
          <section className="rounded-2xl border border-neutral-200 bg-white p-5"><div className="flex items-center gap-2"><ClipboardList size={18} className="text-indigo-700" /><h2 className="font-semibold">Trilha de auditoria</h2></div><p className="mt-4 text-sm leading-6 text-neutral-500">{permissions.audit ? "Consulte os eventos administrativos na seção de auditoria, com acesso controlado por perfil." : "A trilha de auditoria é restrita aos perfis autorizados."}</p>{permissions.audit && <button onClick={() => setTab("audit")} className="mt-4 rounded-xl border border-neutral-200 px-3 py-2 text-sm font-semibold hover:bg-neutral-50">Abrir auditoria</button>}</section>
          <section className="rounded-2xl border border-neutral-200 bg-white p-5"><div className="flex items-center gap-2"><Wifi size={18} className="text-indigo-700" /><h2 className="font-semibold">Estado de configuração dos canais</h2></div>
            <div className="mt-4 space-y-3">{overview?.channels.map((channel) => <div key={channel.id} className="rounded-xl border border-neutral-100 p-4"><div className="flex items-center justify-between gap-3"><p className="font-medium">{channel.name}</p><span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${channel.configured ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}>{channel.configured ? <CheckCircle2 size={13} /> : <WifiOff size={13} />}{channel.configured ? "Configurado" : "Pendente"}</span></div><p className="mt-1 text-xs text-neutral-500">{channel.providers.length ? channel.providers.join(", ") : "Nenhum provedor configurado"} · {channel.note}</p></div>)}</div>
          </section>
        </div>
      </section>}

      {tab === "organizations" && <section className="mt-6 rounded-2xl border border-neutral-200 bg-white">
        <div className="flex flex-col gap-3 border-b border-neutral-100 p-5 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="font-semibold">Instituições</h2><p className="mt-1 text-sm text-neutral-500">Visão de leitura dos tenants cadastrados.</p></div><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar instituição…" className="h-10 rounded-xl border border-neutral-200 px-3 text-sm outline-none focus:border-indigo-500 sm:w-72" /></div>
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500"><tr><th className="px-5 py-3">Instituição</th><th className="px-5 py-3">Segmento</th><th className="px-5 py-3">Membros</th><th className="px-5 py-3">Modelo</th><th className="px-5 py-3">Status</th>{admin.role === "super_admin" && <th className="px-5 py-3">Ação</th>}</tr></thead><tbody className="divide-y divide-neutral-100">{visibleOrgs.map((org) => <tr key={org.id}><td className="px-5 py-4"><p className="font-semibold">{org.name}</p><p className="mt-1 text-xs text-neutral-500">{org.slug}</p></td><td className="px-5 py-4">{org.segment || "—"}</td><td className="px-5 py-4">{org.members_count}</td><td className="px-5 py-4">{org.model_ready ? "Pronto" : "Não configurado"}</td><td className="px-5 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${org.is_active ? "bg-emerald-50 text-emerald-700" : "bg-neutral-100 text-neutral-500"}`}>{org.is_active ? "Ativa" : "Inativa"}</span></td>{admin.role === "super_admin" && <td className="px-5 py-4"><button onClick={() => void toggleOrganization(org)} className="whitespace-nowrap rounded-lg border border-neutral-200 px-3 py-2 text-xs font-semibold hover:bg-neutral-50">{org.is_active ? "Desativar" : "Reativar"}</button></td>}</tr>)}</tbody></table></div>
        {visibleOrgs.length === 0 && <p className="p-6 text-sm text-neutral-500">Nenhuma instituição encontrada.</p>}
      </section>}

      {tab === "members" && <section className="mt-6 rounded-2xl border border-neutral-200 bg-white">
        <div className="flex flex-col gap-3 border-b border-neutral-100 p-5 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="font-semibold">Membros</h2><p className="mt-1 text-sm text-neutral-500">Contas de usuários das instituições.</p></div><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar membro…" className="h-10 rounded-xl border border-neutral-200 px-3 text-sm outline-none focus:border-indigo-500 sm:w-72" /></div>
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500"><tr><th className="px-5 py-3">Pessoa</th><th className="px-5 py-3">Instituição</th><th className="px-5 py-3">Perfil</th><th className="px-5 py-3">Status</th><th className="px-5 py-3">Criado em</th>{admin.role === "super_admin" && <th className="px-5 py-3">Ação</th>}</tr></thead><tbody className="divide-y divide-neutral-100">{visibleMembers.map((member) => <tr key={member.id}><td className="px-5 py-4"><p className="font-semibold">{member.name}</p><p className="mt-1 text-xs text-neutral-500">{member.email}</p></td><td className="px-5 py-4">{member.organization}</td><td className="px-5 py-4 capitalize">{member.role}</td><td className="px-5 py-4">{member.is_active ? "Ativo" : "Inativo"}</td><td className="px-5 py-4">{dateLabel(member.created_at)}</td>{admin.role === "super_admin" && <td className="px-5 py-4"><button onClick={() => void toggleMember(member)} className="whitespace-nowrap rounded-lg border border-neutral-200 px-3 py-2 text-xs font-semibold hover:bg-neutral-50">{member.is_active ? "Desativar" : "Reativar"}</button></td>}</tr>)}</tbody></table></div>
        {visibleMembers.length === 0 && <p className="p-6 text-sm text-neutral-500">Nenhum membro encontrado.</p>}
      </section>}

      {tab === "channels" && <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(overview?.channels || []).map((channel) => <article key={channel.id} className="rounded-2xl border border-neutral-200 bg-white p-5"><div className="flex items-center gap-3"><span className="grid h-11 w-11 place-items-center rounded-xl bg-indigo-50 text-indigo-700"><Activity size={20} /></span><div><h2 className="font-semibold">{channel.name}</h2><p className="text-xs text-neutral-500">{channel.id.toUpperCase()}</p></div></div><div className="mt-5 flex items-center gap-2 text-sm">{channel.configured ? <CheckCircle2 className="text-emerald-600" size={17} /> : <CircleAlert className="text-amber-600" size={17} />}{channel.configured ? "Credenciais configuradas" : "Configuração incompleta"}</div><p className="mt-2 text-sm text-neutral-500">{channel.providers.join(", ") || "Nenhum provedor"}.</p><p className="mt-4 rounded-xl bg-neutral-50 p-3 text-xs leading-5 text-neutral-600">{channel.note}</p></article>)}
      </section>}


      {tab === "billing" && <section className="mt-6 space-y-5">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Contratos cadastrados" value={billingSummary.total} note="Controle manual por instituição" icon={ClipboardList} />
          <Metric label="Vencidos" value={billingSummary.overdue} note="Pendentes após a data de vencimento" icon={CircleAlert} />
          <Metric label="Vencem em 30 dias" value={billingSummary.due_soon} note="Planeje a cobrança com antecedência" icon={Activity} />
          <Metric label="Pagamentos pendentes" value={billingSummary.pending} note="Inclui vencidos e a vencer" icon={Building2} />
        </div>
        {permissions.billing && admin.role !== "auditor" && <form onSubmit={createBillingRecord} className="grid gap-4 rounded-2xl border border-neutral-200 bg-white p-5 md:grid-cols-2 xl:grid-cols-3">
          <div className="md:col-span-2 xl:col-span-3"><h2 className="font-semibold">Cadastrar acompanhamento financeiro</h2><p className="mt-1 text-sm text-neutral-500">Controle manual de plano, link externo e vencimento; nenhum pagamento é processado pelo MIRA.</p></div>
          <label className="space-y-1.5 text-sm"><span className="font-medium">Instituição</span><select required value={billingForm.tenant_id} onChange={(e) => setBillingForm({ ...billingForm, tenant_id: e.target.value })} className="h-11 w-full rounded-xl border border-neutral-200 bg-white px-3"><option value="">Selecione…</option>{organizations.map((org) => <option key={org.id} value={org.id}>{org.name}</option>)}</select></label>
          <label className="space-y-1.5 text-sm"><span className="font-medium">Plano</span><input required minLength={2} maxLength={120} value={billingForm.plan_name} onChange={(e) => setBillingForm({ ...billingForm, plan_name: e.target.value })} className="h-11 w-full rounded-xl border border-neutral-200 px-3" /></label>
          <label className="space-y-1.5 text-sm"><span className="font-medium">Valor (R$)</span><input required type="number" min="0" max="100000000" step="0.01" value={billingForm.plan_price_brl} onChange={(e) => setBillingForm({ ...billingForm, plan_price_brl: e.target.value })} className="h-11 w-full rounded-xl border border-neutral-200 px-3" /></label>
          <label className="space-y-1.5 text-sm"><span className="font-medium">Ciclo</span><select value={billingForm.billing_cycle} onChange={(e) => setBillingForm({ ...billingForm, billing_cycle: e.target.value as "monthly" | "yearly" })} className="h-11 w-full rounded-xl border border-neutral-200 bg-white px-3"><option value="monthly">Mensal</option><option value="yearly">Anual</option></select></label>
          <label className="space-y-1.5 text-sm"><span className="font-medium">Próximo vencimento</span><input required type="date" value={billingForm.due_date} onChange={(e) => setBillingForm({ ...billingForm, due_date: e.target.value })} className="h-11 w-full rounded-xl border border-neutral-200 px-3" /></label>
          <label className="space-y-1.5 text-sm"><span className="font-medium">Link externo de pagamento (HTTPS)</span><input type="url" value={billingForm.payment_link} onChange={(e) => setBillingForm({ ...billingForm, payment_link: e.target.value })} placeholder="https://..." className="h-11 w-full rounded-xl border border-neutral-200 px-3" /></label>
          <label className="space-y-1.5 text-sm md:col-span-2 xl:col-span-3"><span className="font-medium">Observações (opcional)</span><input maxLength={500} value={billingForm.notes} onChange={(e) => setBillingForm({ ...billingForm, notes: e.target.value })} className="h-11 w-full rounded-xl border border-neutral-200 px-3" /></label>
          <div className="md:col-span-2 xl:col-span-3"><button disabled={savingBilling} className="inline-flex h-11 items-center gap-2 rounded-xl bg-[#4050cd] px-4 text-sm font-semibold text-white disabled:opacity-50">{savingBilling ? <LoaderCircle size={15} className="animate-spin" /> : <CheckCircle2 size={15} />} Registrar acompanhamento</button></div>
        </form>}
        <section className="rounded-2xl border border-neutral-200 bg-white">
          <div className="border-b border-neutral-100 p-5"><h2 className="font-semibold">Planos e vencimentos</h2><p className="mt-1 text-sm text-neutral-500">Status financeiro manual; confirme pagamentos na fonte externa antes de marcar como pagos.</p></div>
          <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500"><tr><th className="px-5 py-3">Instituição / Plano</th><th className="px-5 py-3">Valor</th><th className="px-5 py-3">Vencimento</th><th className="px-5 py-3">Status</th><th className="px-5 py-3">Pagamento</th><th className="px-5 py-3">Ação</th></tr></thead><tbody className="divide-y divide-neutral-100">{billingRecords.map((record) => <tr key={record.id}><td className="px-5 py-4"><p className="font-semibold">{record.organization_name}</p><p className="mt-1 text-xs text-neutral-500">{record.plan_name} · {record.billing_cycle === "monthly" ? "Mensal" : "Anual"}</p>{record.payment_link && <a href={record.payment_link} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block text-xs font-medium text-indigo-700 underline">Abrir link de pagamento ↗</a>}</td><td className="whitespace-nowrap px-5 py-4">R$ {record.plan_price_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td><td className="whitespace-nowrap px-5 py-4"><p>{dateLabel(record.due_at)}</p>{record.is_overdue ? <p className="mt-1 text-xs font-semibold text-red-700">Vencido há {Math.abs(record.days_until_due)} dia(s)</p> : record.payment_status !== "paid" && record.days_until_due <= 30 ? <p className="mt-1 text-xs font-semibold text-amber-700">{record.days_until_due === 0 ? "Vence hoje" : `Vence em ${record.days_until_due} dia(s)`}</p> : null}</td><td className="px-5 py-4 capitalize">{record.plan_status === "active" ? "Ativo" : record.plan_status === "paused" ? "Pausado" : "Cancelado"}</td><td className="px-5 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${record.payment_status === "paid" ? "bg-emerald-50 text-emerald-700" : record.is_overdue ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-800"}`}>{record.payment_status === "paid" ? "Pago" : record.is_overdue ? "Em atraso" : "Pendente"}</span></td><td className="px-5 py-4">{permissions.billing && admin.role !== "auditor" && <button onClick={() => void setPaymentStatus(record, record.payment_status === "paid" ? "pending" : "paid")} className="whitespace-nowrap rounded-lg border border-neutral-200 px-3 py-2 text-xs font-semibold hover:bg-neutral-50">{record.payment_status === "paid" ? "Reabrir pendência" : "Marcar como pago"}</button>}</td></tr>)}</tbody></table></div>
          {billingRecords.length === 0 && <p className="p-6 text-sm text-neutral-500">Nenhum registro financeiro cadastrado.</p>}
        </section>
      </section>}

      {tab === "audit" && <section className="mt-6 rounded-2xl border border-neutral-200 bg-white">
        <div className="flex flex-col gap-3 border-b border-neutral-100 p-5 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="font-semibold">Trilha de auditoria</h2><p className="mt-1 text-sm text-neutral-500">Eventos administrativos recentes; dados sensíveis são omitidos.</p></div><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filtrar eventos…" className="h-10 rounded-xl border border-neutral-200 px-3 text-sm outline-none focus:border-indigo-500 sm:w-72" /></div>
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500"><tr><th className="px-5 py-3">Data</th><th className="px-5 py-3">Ator</th><th className="px-5 py-3">Ação</th><th className="px-5 py-3">Resultado</th><th className="px-5 py-3">Motivo</th></tr></thead><tbody className="divide-y divide-neutral-100">{visibleEvents.map((event) => <tr key={event.id}><td className="whitespace-nowrap px-5 py-4">{dateLabel(event.created_at)}</td><td className="px-5 py-4">{event.actor_email || "Sistema"}</td><td className="px-5 py-4 font-medium">{event.action}</td><td className="px-5 py-4">{event.result}</td><td className="max-w-xs px-5 py-4 text-neutral-500">{event.reason || "—"}</td></tr>)}</tbody></table></div>
        {visibleEvents.length === 0 && <p className="p-6 text-sm text-neutral-500">Nenhum evento encontrado.</p>}
      </section>}

      <footer className="mt-8 flex flex-col gap-2 border-t border-neutral-200 pt-5 text-xs leading-5 text-neutral-500 sm:flex-row sm:items-center sm:justify-between"><span>Área interna · permissões aplicadas no backend</span><span className="inline-flex items-center gap-1.5"><ShieldCheck size={13} /> Sessão administrativa com expiração curta</span></footer>
    </div>
  </main>;
}
