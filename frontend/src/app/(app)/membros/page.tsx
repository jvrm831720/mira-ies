"use client";

import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { LoaderCircle, Mail, Shield, UserPlus, Users } from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import type { MemberRole, OrgMember, OrgInvite } from "@/types/api";

const ROLE_LABEL: Record<MemberRole, string> = {
  admin: "Administrador",
  coordinator: "Coordenação",
  operator: "Operação",
  viewer: "Somente leitura",
};

const ROLE_HELP: Record<MemberRole, string> = {
  admin: "Gerencia membros, configurações e toda a operação.",
  coordinator: "Vê riscos, importa dados e conduz retenção.",
  operator: "Acompanha alunos e executa contatos de retenção.",
  viewer: "Consulta painéis e listas, sem alterar dados.",
};

export default function MembersPage() {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<MemberRole>("coordinator");

  const members = useQuery({
    queryKey: ["org-members"],
    queryFn: () => api.listMembers(),
    retry: false,
  });

  const invites = useQuery({
    queryKey: ["org-invites"],
    queryFn: () => api.listInvites(),
    retry: false,
  });

  const inviteMutation = useMutation({
    mutationFn: () => api.inviteMember({ email: email.trim().toLowerCase(), role }),
    onSuccess: (data) => {
      toast.success(data.message || "Convite enviado");
      setEmail("");
      qc.invalidateQueries({ queryKey: ["org-invites"] });
      qc.invalidateQueries({ queryKey: ["org-members"] });
      if (data.invite_url) {
        toast.message("Link do convite (dev)", { description: data.invite_url });
      }
    },
    onError: (err) => {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Não foi possível enviar o convite. O backend de membros pode ainda não estar ativo.";
      toast.error(msg);
    },
  });

  const backendMissing =
    (members.isError && members.error instanceof ApiError && members.error.status === 404) ||
    (invites.isError && invites.error instanceof ApiError && invites.error.status === 404);

  const memberList: OrgMember[] = members.data?.members ?? [];
  const inviteList: OrgInvite[] = invites.data?.invites ?? [];

  const pendingCount = useMemo(
    () => inviteList.filter((i) => i.status === "pending").length,
    [inviteList]
  );

  function onInvite(e: FormEvent) {
    e.preventDefault();
    if (!email.trim() || !email.includes("@")) {
      toast.error("Informe um e-mail válido");
      return;
    }
    inviteMutation.mutate();
  }

  return (
    <>
      <Header
        title="Membros"
        subtitle="Organize quem acessa a instituição e com qual permissão."
      />
      <main className="mx-auto w-full max-w-5xl space-y-6 px-4 pb-10 pt-5 md:px-9 md:pt-7">
        {backendMissing && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            A API de membros ainda não respondeu (404). A interface já está pronta — o convite
            passará a funcionar quando o endpoint de organização estiver no ar.
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Card>
            <CardHeader>
              <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
                <UserPlus className="h-3.5 w-3.5" /> Convidar
              </div>
              <CardTitle>Adicionar membro</CardTitle>
              <CardDescription>
                Informe só o e-mail e o tipo de acesso. A pessoa recebe um link para criar senha e
                telefone e entrar na organização.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={onInvite} className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="invite-email">
                    E-mail
                  </label>
                  <Input
                    id="invite-email"
                    type="email"
                    placeholder="nome@instituicao.edu.br"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="invite-role">
                    Tipo de acesso
                  </label>
                  <select
                    id="invite-role"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    value={role}
                    onChange={(e) => setRole(e.target.value as MemberRole)}
                  >
                    {(Object.keys(ROLE_LABEL) as MemberRole[]).map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABEL[r]}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-foreground">{ROLE_HELP[role]}</p>
                </div>
                <Button type="submit" disabled={inviteMutation.isPending} className="w-full sm:w-auto">
                  {inviteMutation.isPending ? (
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                  ) : (
                    <Mail className="h-4 w-4" />
                  )}
                  Enviar convite
                </Button>
              </form>
            </CardContent>
          </Card>

          <aside className="space-y-4">
            <Card className="bg-[var(--brand-midnight)] text-white shadow-none">
              <CardHeader>
                <span className="grid h-9 w-9 place-items-center rounded-xl bg-white/10 text-[var(--brand-coral)]">
                  <Shield className="h-4 w-4" />
                </span>
                <CardTitle className="pt-1 text-[15px] text-white">Como funciona</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-xs leading-relaxed text-white/75">
                <p>1. Você convida com e-mail + perfil de acesso.</p>
                <p>2. A pessoa abre o link seguro do convite.</p>
                <p>3. Define senha e telefone e entra na organização.</p>
                <p className="text-white/55">Convites pendentes expiram conforme a política da instituição.</p>
              </CardContent>
            </Card>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-border bg-white p-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Ativos
                </p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">
                  {members.isLoading ? "—" : memberList.length}
                </p>
              </div>
              <div className="rounded-xl border border-border bg-white p-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Convites
                </p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">
                  {invites.isLoading ? "—" : pendingCount}
                </p>
              </div>
            </div>
          </aside>
        </div>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-primary" />
              <CardTitle>Membros da organização</CardTitle>
            </div>
            <CardDescription>Pessoas com acesso ativo a esta instituição.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/40 text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">Nome / e-mail</th>
                    <th className="px-4 py-3 font-medium">Acesso</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {members.isLoading &&
                    Array.from({ length: 3 }).map((_, i) => (
                      <tr key={i}>
                        <td className="px-4 py-3" colSpan={3}>
                          <Skeleton className="h-5 w-full" />
                        </td>
                      </tr>
                    ))}
                  {!members.isLoading && memberList.length === 0 && (
                    <tr>
                      <td colSpan={3} className="px-4 py-10 text-center text-muted-foreground">
                        Nenhum membro listado ainda. Envie o primeiro convite.
                      </td>
                    </tr>
                  )}
                  {memberList.map((m) => (
                    <tr key={m.id} className="border-b border-border/70">
                      <td className="px-4 py-3">
                        <p className="font-medium">{m.display_name || m.email}</p>
                        <p className="text-xs text-muted-foreground">{m.email}</p>
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-medium">
                          {ROLE_LABEL[m.role] || m.role}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {m.status === "active" ? "Ativo" : m.status}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Convites pendentes</CardTitle>
            <CardDescription>Aguardando aceite do convidado.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/40 text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">E-mail</th>
                    <th className="px-4 py-3 font-medium">Acesso</th>
                    <th className="px-4 py-3 font-medium">Enviado</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {invites.isLoading &&
                    Array.from({ length: 2 }).map((_, i) => (
                      <tr key={i}>
                        <td className="px-4 py-3" colSpan={4}>
                          <Skeleton className="h-5 w-full" />
                        </td>
                      </tr>
                    ))}
                  {!invites.isLoading && inviteList.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                        Nenhum convite pendente.
                      </td>
                    </tr>
                  )}
                  {inviteList.map((inv) => (
                    <tr key={inv.id} className="border-b border-border/70">
                      <td className="px-4 py-3 font-medium">{inv.email}</td>
                      <td className="px-4 py-3 text-xs">{ROLE_LABEL[inv.role] || inv.role}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {inv.created_at
                          ? new Date(inv.created_at).toLocaleString("pt-BR")
                          : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">
                          {inv.status}
                        </span>
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
