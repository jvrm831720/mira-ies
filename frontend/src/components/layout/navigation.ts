import type { LucideIcon } from "@/components/ui/icons";
import {
  Activity, BarChart3, BookOpenCheck, BriefcaseBusiness, CreditCard,
  Database, FileClock, FileUp, House, MessageCircle, Settings2,
  ShieldCheck, Users, Workflow,
} from "@/components/ui/icons";
import type { OrgMeResponse } from "@/lib/api";

/** Wave 0: only routes that already exist in the authenticated workspace.
 * Collections, contacts and agreements are intentionally absent until built. */
export type NavigationItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  keywords?: string;
  permission: string;
  profile?: "education" | "collection";
  module?: "workspace" | "permanence" | "billing" | "data" | "mira_plan" | "operations";
  feature?: "academic_catalog" | "academic_services" | "academic_operations";
};
export type NavigationGroup = {
  id: string;
  label: string;
  items: NavigationItem[];
};
const allGroups: NavigationGroup[] = [
  { id: "home", label: "Início", items: [
    { href: "/", label: "Visão geral", icon: House, permission: "dashboard.view", module: "workspace", keywords: "painel prioridades dashboard" },
  ] },
  { id: "people", label: "Alunos", items: [
    { href: "/alunos", label: "Alunos", icon: Users, profile: "education", permission: "students.view", module: "permanence", keywords: "estudantes ficha histórico" },
    { href: "/alunos/grupos", label: "Grupos e segmentos", icon: BookOpenCheck, profile: "education", permission: "students.view", module: "permanence", keywords: "listas classificação segmentos" },
  ] },
  { id: "intelligence", label: "Inteligência", items: [
    { href: "/monitoramento", label: "Monitoramento", icon: Activity, profile: "education", permission: "students.sensitive.view", module: "permanence", keywords: "risco sinais permanência" },
    { href: "/resultados", label: "Resultados", icon: BarChart3, profile: "education", permission: "students.sensitive.view", module: "permanence", keywords: "evasão rematrícula desempenho" },
  ] },
  { id: "operations", label: "Operação", items: [
    { href: "/trabalho", label: "Central de trabalho", icon: BriefcaseBusiness, permission: "access.operator", module: "workspace", keywords: "tarefas fila atividades aprovações" },
    { href: "/retencao", label: "Intervenções", icon: Workflow, profile: "education", permission: "campaigns.view", module: "operations", keywords: "retenção jornadas" },
    { href: "/workflows", label: "Workflows", icon: Workflow, permission: "campaigns.view", module: "operations", keywords: "automações processos fluxos histórico execução" },
    { href: "/campanhas", label: "Campanhas", icon: FileClock, permission: "campaigns.view", module: "operations", keywords: "revisão aprovação mensagens" },
    { href: "/disparos", label: "Disparos", icon: MessageCircle, permission: "campaigns.view", module: "operations", keywords: "envios canais execução" },
    { href: "/retencao/logs", label: "Histórico de contatos", icon: Activity, profile: "education", permission: "campaigns.view", module: "operations", keywords: "logs atividades" },
  ] },
  { id: "academic", label: "Acadêmico", items: [
    { href: "/academico", label: "Gestão acadêmica", icon: BookOpenCheck, profile: "education", permission: "students.sensitive.view", module: "permanence", feature: "academic_catalog", keywords: "cursos turmas disciplinas professores" },
    { href: "/academico/jornadas", label: "Jornadas", icon: Workflow, profile: "education", permission: "students.sensitive.view", module: "permanence", feature: "academic_operations", keywords: "matrícula rematrícula notas frequência currículo" },
    { href: "/academico/servicos", label: "Serviços acadêmicos", icon: FileClock, profile: "education", permission: "students.sensitive.view", module: "permanence", feature: "academic_services", keywords: "solicitações protocolos documentos" },
  ] },
  { id: "data", label: "Dados", items: [
    { href: "/conectores", label: "Integrações", icon: Database, permission: "data.view", module: "data", keywords: "fontes sistemas Composio" },
    { href: "/conectores/financeiro", label: "Fontes financeiras", icon: CreditCard, permission: "data.view", module: "data", keywords: "conciliação ERP financeiras" },
    { href: "/importar", label: "Importar dados", icon: FileUp, permission: "data.import", module: "data", keywords: "CSV XLSX upload" },
    { href: "/importacoes", label: "Importações", icon: FileClock, permission: "data.view", module: "data", keywords: "histórico arquivos sincronização" },
  ] },
  { id: "settings", label: "Configurações", items: [
    { href: "/config", label: "Workspace", icon: Settings2, permission: "settings.manage", module: "workspace", keywords: "preferências instituição segurança" },
    { href: "/membros", label: "Equipe", icon: Users, permission: "members.view", module: "workspace", keywords: "membros convites" },
    { href: "/membros/cargos", label: "Cargos e permissões", icon: ShieldCheck, permission: "permissions.manage", module: "workspace", keywords: "acesso papéis RBAC" },
    { href: "/fatura", label: "Plano MIRA", icon: CreditCard, permission: "settings.manage", module: "mira_plan", keywords: "assinatura da plataforma créditos" },
  ] },
];

const builtinPermissions: Record<string, string[]> = {
  viewer: ["access.viewer", "dashboard.view", "students.view"],
  operator: ["access.viewer", "access.operator", "dashboard.view", "students.view",
    "students.create", "students.edit", "campaigns.view", "campaigns.create",
    "campaigns.edit", "members.view", "data.view"],
  coordinator: ["access.viewer", "access.operator", "access.coordinator", "dashboard.view",
    "students.view", "students.sensitive.view", "students.create", "students.edit",
    "campaigns.view", "campaigns.create", "campaigns.edit", "campaigns.approve",
    "campaigns.execute", "members.view", "members.manage", "data.view", "data.import", "audit.view"],
};

/** Explicit effective permissions take precedence; unknown custom roles fail closed.
 * Legacy built-in roles are supported until org/me always returns effective grants. */
export function hasNavigationPermission(me: OrgMeResponse | null | undefined, permission: string): boolean {
  if (!me) return false;
  if (Array.isArray(me.permissions)) return me.permissions.includes(permission);
  if (me.custom_role_id) return false;
  if (me.role === "admin") return true;
  return (builtinPermissions[me.role || ""] || []).includes(permission);
}

export function getVisibleNavigation(me: OrgMeResponse | null | undefined): NavigationGroup[] {
  if (!me) return [];
  const profile = me.operation_profile === "institution" ? "education"
    : ["collection", "debt_collection", "billing", "cobranca"].includes(me.operation_profile || "") ? "collection" : "unknown";
  // Optional server entitlement contract. A missing list preserves existing legacy
  // routes; a supplied list can explicitly disable modules without a UI override.
  const enabled = me.enabled_modules;
  return allGroups.map(group => ({
    ...group,
    items: group.items.filter(item => {
      if (item.profile && item.profile !== profile) return false;
      if (!hasNavigationPermission(me, item.permission)) return false;
      if (item.feature && me.available_features?.[item.feature] !== true) return false;
      const moduleKey = item.module === "operations" ? (profile === "education" ? "permanence" : "billing") : item.module;
      if (Array.isArray(enabled) && moduleKey && !enabled.includes(moduleKey)) return false;
      return true;
    }),
  })).filter(group => group.items.length > 0);
}

export function activeNavigationHref(groups: NavigationGroup[], pathname: string): string | null {
  const items = groups.flatMap(group => group.items);
  const matches = items.filter(item => pathname === item.href ||
    (item.href !== "/" && pathname.startsWith(item.href + "/")));
  matches.sort((a, b) => b.href.length - a.href.length);
  return matches[0]?.href || null;
}

export function searchNavigation(groups: NavigationGroup[], query: string): Array<NavigationItem & { category: string }> {
  const normalized = query.trim().toLocaleLowerCase("pt-BR");
  return groups.flatMap(group => group.items
    .filter(item => !normalized || [item.label, item.keywords || "", group.label]
      .some(value => value.toLocaleLowerCase("pt-BR").includes(normalized)))
    .map(item => ({ ...item, category: group.label })));
}
