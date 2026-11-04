"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Copy, LoaderCircle, Save, Shield, Trash2 } from "lucide-react";
import Link from "next/link";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import type { TenantRole, TenantRolePayload } from "@/types/api";

const GROUPS: Array<{ label: string; keys: string[] }> = [
  { label: "Acesso e navegação", keys: ["access.viewer", "access.operator", "access.coordinator", "dashboard.view"] },
  { label: "Alunos", keys: ["students.view", "students.sensitive.view", "students.create", "students.edit", "students.delete"] },
  { label: "Campanhas", keys: ["campaigns.view", "campaigns.create", "campaigns.edit", "campaigns.approve", "campaigns.execute", "campaigns.delete"] },
  { label: "Equipe e administração", keys: ["members.view", "members.manage", "permissions.manage", "settings.manage", "audit.view"] },
  { label: "Dados e operações", keys: ["data.view", "data.import", "critical.manage"] },
];

const EMPTY: TenantRolePayload = { name: "", description: "", base_role: "viewer", permissions: ["access.viewer", "dashboard.view"] };
const BASE_RANK = { viewer: 1, operator: 2, coordinator: 3 } as const;
const PERMISSION_RANK: Record<string, number> = {
  "access.viewer": 1, "dashboard.view": 1, "students.view": 1,
  "access.operator": 2, "students.create": 2, "students.edit": 2,
  "campaigns.view": 2, "campaigns.create": 2, "campaigns.edit": 2,
  "members.view": 2, "data.view": 2,
  "access.coordinator": 3, "data.import": 3, "audit.view": 3,
  "students.sensitive.view": 3, "campaigns.approve": 3, "campaigns.execute": 3,
  "members.manage": 3, "permissions.manage": 3, "settings.manage": 3,
  "students.delete": 3, "campaigns.delete": 3, "critical.manage": 3,
};

export default function CustomRolesPage() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["org-me"], queryFn: () => api.me(), retry: false });
  const canManageRoles = me.data?.role === "admin" || me.data?.permissions?.includes("permissions.manage") === true;
  const canViewMembers = me.data?.role === "admin" || me.data?.permissions?.includes("members.view") === true;
  const roles = useQuery({ queryKey: ["tenant-roles"], queryFn: () => api.tenantRoles(), retry: false, enabled: me.data?.role === "admin" || me.data?.permissions?.includes("permissions.manage") === true });
  const catalog = useQuery({ queryKey: ["tenant-role-catalog"], queryFn: () => api.tenantRoleCatalog(), enabled: me.data?.role === "admin" || me.data?.permissions?.includes("permissions.manage") === true });
  const members = useQuery({ queryKey: ["org-members"], queryFn: () => api.listMembers(), retry: false, enabled: canManageRoles && canViewMembers });
  const audit = useQuery({ queryKey: ["tenant-role-audit"], queryFn: () => api.tenantRoleAudit(), retry: false, enabled: me.data?.role === "admin" || me.data?.permissions?.includes("permissions.manage") === true });
  const [form, setForm] = useState<TenantRolePayload>(EMPTY);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [stepUpCode, setStepUpCode] = useState("");
  const [selectedMember, setSelectedMember] = useState("");
  const [selectedRole, setSelectedRole] = useState("");
  const [viewingRoleId, setViewingRoleId] = useState<string | null>(null);
  const roleMembers = useQuery({
    queryKey: ["tenant-role-members", viewingRoleId],
    queryFn: () => api.tenantRoleMembers(viewingRoleId as string),
    enabled: canManageRoles && Boolean(viewingRoleId),
  });
  const memberPermissions = useQuery({
    queryKey: ["member-effective-permissions", selectedMember],
    queryFn: () => api.memberEffectivePermissions(selectedMember),
    enabled: canManageRoles && Boolean(selectedMember),
  });

  const roleList = roles.data?.roles ?? [];
  const memberList = members.data?.members ?? [];
  const labels = useMemo(() => new Map((catalog.data?.permissions ?? []).map((p) => [p.key, p.label])), [catalog.data]);

  async function elevate() {
    if (stepUpCode.length !== 6) throw new Error("Informe o código de seis dígitos do autenticador.");
    const result = await api.stepUpMfa(stepUpCode);
    setAccessToken(result.access_token);
    setStepUpCode("");
  }

  function resetForm() {
    setForm(EMPTY);
    setEditingId(null);
  }

  function beginEdit(role: TenantRole) {
    setEditingId(role.id);
    setForm({ name: role.name, description: role.description || "", base_role: role.base_role, permissions: role.permissions });
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      await elevate();
      return editingId ? api.updateTenantRole(editingId, form) : api.createTenantRole(form);
    },
    onSuccess: () => { toast.success(editingId ? "Cargo atualizado." : "Cargo criado."); resetForm(); qc.invalidateQueries({ queryKey: ["tenant-roles"] }); qc.invalidateQueries({ queryKey: ["tenant-role-audit"] }); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Não foi possível salvar o cargo."),
  });

  const duplicateMutation = useMutation({
    mutationFn: async (id: string) => { await elevate(); return api.duplicateTenantRole(id); },
    onSuccess: () => { toast.success("Cargo duplicado."); qc.invalidateQueries({ queryKey: ["tenant-roles"] }); qc.invalidateQueries({ queryKey: ["tenant-role-audit"] }); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Falha ao duplicar."),
  });

  const deactivateMutation = useMutation({
    mutationFn: async (id: string) => { await elevate(); return api.deactivateTenantRole(id); },
    onSuccess: () => { toast.success("Cargo desativado."); qc.invalidateQueries({ queryKey: ["tenant-roles"] }); qc.invalidateQueries({ queryKey: ["tenant-role-audit"] }); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Falha ao desativar."),
  });

  const assignMutation = useMutation({
    mutationFn: async () => { await elevate(); return api.assignTenantRole(selectedMember, selectedRole || null); },
    onSuccess: () => { toast.success("Cargo do membro atualizado. As sessões anteriores foram invalidadas."); qc.invalidateQueries({ queryKey: ["org-members"] }); qc.invalidateQueries({ queryKey: ["tenant-role-audit"] }); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Falha ao atribuir cargo."),
  });

  function togglePermission(key: string, checked: boolean) {
    setForm((current) => ({ ...current, permissions: checked ? [...current.permissions, key] : current.permissions.filter((p) => p !== key) }));
  }

  if (me.isLoading) return <main className="p-8 text-sm text-muted-foreground">Carregando permissões…</main>;
  if (!canManageRoles) return <main className="mx-auto max-w-3xl p-8"><Card><CardHeader><CardTitle>Acesso restrito</CardTitle><CardDescription>Você não tem permissão para configurar cargos nesta instituição.</CardDescription></CardHeader><CardContent><Link href="/membros"><Button variant="outline"><ArrowLeft className="mr-2 h-4 w-4" /> Voltar para membros</Button></Link></CardContent></Card></main>;

  return (
    <>
      <Header title="Cargos e permissões" subtitle="Configure o acesso da equipe por módulo, tela e operação." />
      <main className="mx-auto w-full max-w-6xl space-y-6 px-4 pb-12 pt-5 md:px-9 md:pt-7">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link href="/membros" className="text-sm text-muted-foreground hover:text-foreground">← Voltar para membros</Link>
          <div className="flex items-center gap-2">
            <label htmlFor="rbac-step-up" className="text-xs text-muted-foreground">Código MFA</label>
            <Input id="rbac-step-up" value={stepUpCode} onChange={(e) => setStepUpCode(e.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="000000" className="w-28" inputMode="numeric" />
          </div>
        </div>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2"><Shield className="h-4 w-4 text-primary" /><CardTitle>{editingId ? "Editar cargo" : "Criar cargo"}</CardTitle></div>
              <CardDescription>O cargo-base limita o nível máximo de privilégio. O papel administrador é reservado e não pode ser criado como cargo personalizado.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1"><label className="text-xs font-medium">Nome</label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ex.: Analista de permanência" maxLength={80} /></div>
                <div className="space-y-1"><label className="text-xs font-medium">Cargo-base (limite de privilégio)</label><select value={form.base_role} onChange={(e) => { const base_role = e.target.value as TenantRolePayload["base_role"]; setForm((current) => ({ ...current, base_role, permissions: current.permissions.filter((permission) => (PERMISSION_RANK[permission] ?? 99) <= BASE_RANK[base_role]) })); }} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"><option value="viewer">Consulta</option><option value="operator">Operação</option><option value="coordinator">Coordenação</option></select></div>
              </div>
              <div className="space-y-1"><label className="text-xs font-medium">Descrição</label><Input value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Responsabilidades deste cargo" maxLength={500} /></div>
              <div className="space-y-4">
                {GROUPS.map((group) => <section key={group.label} className="space-y-2"><h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{group.label}</h3><div className="grid gap-2 sm:grid-cols-2">{group.keys.map((key) => <label key={key} className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm"><input type="checkbox" checked={form.permissions.includes(key)} disabled={key === "access.viewer" || (PERMISSION_RANK[key] ?? 99) > BASE_RANK[form.base_role]} onChange={(e) => togglePermission(key, e.target.checked)} className="h-4 w-4 accent-primary" /><span>{labels.get(key) || key}</span></label>)}</div></section>)}
              </div>
              <div className="flex flex-wrap gap-2"><Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending || !form.name.trim() || !form.permissions.length}>{saveMutation.isPending ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}{editingId ? "Salvar alterações" : "Criar cargo"}</Button>{editingId && <Button variant="outline" onClick={resetForm}>Cancelar edição</Button>}</div>
            </CardContent>
          </Card>

          <div className="space-y-5">
            <Card>
              <CardHeader><CardTitle>Cargos da instituição</CardTitle><CardDescription>{roleList.length} cargo(s) personalizado(s). Cargos com membros ativos não podem ser desativados.</CardDescription></CardHeader>
              <CardContent className="space-y-3">
                {roles.isLoading && <p className="text-sm text-muted-foreground">Carregando cargos…</p>}
                {roleList.map((role) => <div key={role.id} className="rounded-xl border border-border p-3"><div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="font-medium">{role.name}</p><p className="text-xs text-muted-foreground">{role.description || "Sem descrição"} · {role.members_count} membro(s)</p><p className="mt-1 text-xs text-muted-foreground">{role.permissions.length} permissões · Base: {role.base_role}</p><span className={role.is_active ? "text-xs text-emerald-700" : "text-xs text-muted-foreground"}>{role.is_active ? "Ativo" : "Desativado"}</span></div><div className="flex shrink-0 gap-1"><Button size="sm" variant="outline" onClick={() => setViewingRoleId(role.id)}>Membros</Button><Button size="icon" variant="ghost" onClick={() => beginEdit(role)} disabled={!role.is_active} aria-label="Editar cargo"><Save className="h-4 w-4" /></Button><Button size="icon" variant="ghost" onClick={() => duplicateMutation.mutate(role.id)} aria-label="Duplicar cargo"><Copy className="h-4 w-4" /></Button><Button size="icon" variant="ghost" onClick={() => deactivateMutation.mutate(role.id)} disabled={!role.is_active || role.members_count > 0} aria-label="Desativar cargo"><Trash2 className="h-4 w-4" /></Button></div></div></div>)}
                {!roles.isLoading && !roleList.length && <p className="text-sm text-muted-foreground">Nenhum cargo personalizado criado.</p>}
              </CardContent>
            </Card>

            {viewingRoleId && (
              <Card>
                <CardHeader>
                  <CardTitle>Membros vinculados</CardTitle>
                  <CardDescription>Vínculos atuais do cargo selecionado.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  {(roleMembers.data?.members ?? []).map((member) => (
                    <div key={member.id} className="flex flex-wrap justify-between gap-2 border-b border-border py-2 text-sm">
                      <span>{member.display_name} · {member.email}</span>
                      <span className="text-xs text-muted-foreground">{member.status}</span>
                    </div>
                  ))}
                  {roleMembers.isLoading && <p className="text-sm text-muted-foreground">Carregando membros…</p>}
                  {!roleMembers.isLoading && !(roleMembers.data?.members.length) && <p className="text-sm text-muted-foreground">Nenhum membro vinculado.</p>}
                  <Button size="sm" variant="ghost" onClick={() => setViewingRoleId(null)}>Fechar</Button>
                </CardContent>
              </Card>
            )}

            {canViewMembers && (
              <Card>
                <CardHeader><CardTitle>Atribuir cargo a membro</CardTitle><CardDescription>Alterar o cargo invalida as sessões existentes. Administradores principais não podem ser rebaixados por esta tela.</CardDescription></CardHeader>
                <CardContent className="space-y-3">
                  <select value={selectedMember} onChange={(e) => setSelectedMember(e.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"><option value="">Selecione um membro</option>{memberList.filter((m) => m.role !== "admin").map((m) => <option key={m.id} value={m.id}>{m.display_name || m.email} · {m.email}</option>)}</select>
                  <select value={selectedRole} onChange={(e) => setSelectedRole(e.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"><option value="">Revogar cargo personalizado (papel padrão: consulta)</option>{roleList.filter((r) => r.is_active).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select>
                  {memberPermissions.data && (
                    <div className="rounded-lg border border-border p-3">
                      <p className="mb-2 text-xs font-semibold">Permissões efetivas do membro</p>
                      <p className="text-xs text-muted-foreground">{memberPermissions.data.custom_role?.name || memberPermissions.data.legacy_role}</p>
                      <div className="mt-2 flex flex-wrap gap-1">{memberPermissions.data.permissions.map((permission) => <span key={permission} className="rounded-md bg-muted px-2 py-1 text-[10px]">{permission}</span>)}</div>
                    </div>
                  )}
                  <Button variant="outline" className="w-full" onClick={() => assignMutation.mutate()} disabled={!selectedMember || assignMutation.isPending}>{assignMutation.isPending ? "Atualizando…" : "Atualizar acesso do membro"}</Button>
                </CardContent>
              </Card>

            )}
          </div>
        </div>

        <Card><CardHeader><CardTitle>Auditoria de cargos e permissões</CardTitle><CardDescription>Últimas 200 alterações registradas pelo backend.</CardDescription></CardHeader><CardContent className="space-y-2">{(audit.data?.events ?? []).map((event) => <div key={event.id} className="flex flex-wrap justify-between gap-2 border-b border-border py-2 text-xs"><span className="font-medium">{event.event_type}</span><span className="text-muted-foreground">{new Date(event.created_at).toLocaleString("pt-BR")}</span></div>)}{!audit.isLoading && !(audit.data?.events.length) && <p className="text-sm text-muted-foreground">Nenhuma alteração registrada.</p>}</CardContent></Card>
      </main>
    </>
  );
}
