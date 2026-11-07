export type AppsCategory = "Comunicação" | "CRM e relacionamento" | "Documentos e arquivos" | "Dados e análise" | "Atendimento e suporte" | "Agenda e agendamento" | "Marketing institucional" | "Acadêmico" | "Financeiro" | "Produtividade" | "IA" | "Outros";
export type AppsStatus = "connected" | "configured" | "available" | "inactive" | "error";
export type CatalogApp = {
  id: string;
  slug: string;
  name: string;
  description: string;
  category: AppsCategory;
  status: AppsStatus;
  statusText: string;
  native: boolean;
  external: boolean;
  route: string;
  initials: string;
  color: string;
  connectedAccountName?: string;
  logoUrl?: string;
  website?: string;
};
export type NativeApp = { id: string; name: string; description?: string; category?: string };
export type RemoteApp = { slug: string; name: string; description?: string | null; logo?: string | null; app_url?: string | null; categories?: string[]; category?: string | null; mira_category?: string | null; mira_category_label?: string | null; enabled?: boolean };
export type RemoteAccount = { toolkit_slug: string; status: string; display_name?: string | null };
export type NativeEvidence = { configured: boolean; enabled?: boolean; status?: string | null; last_sync_status?: string | null };
const editorial: Record<string, { name: string; description: string; category: AppsCategory; initials: string; color: string; rank: number }> = {
  whatsapp: { name: "WhatsApp", description: "Atendimento e campanhas", category: "Comunicação", initials: "W", color: "green", rank: 1 },
  gmail: { name: "Gmail", description: "E-mail institucional", category: "Comunicação", initials: "M", color: "red", rank: 2 },
  outlook: { name: "Outlook", description: "E-mail e calendário", category: "Comunicação", initials: "O", color: "blue", rank: 3 },
  googlecalendar: { name: "Google Calendar", description: "Agenda e eventos", category: "Produtividade", initials: "31", color: "blue", rank: 4 },
  googledrive: { name: "Google Drive", description: "Arquivos e documentos", category: "Produtividade", initials: "D", color: "green", rank: 5 },
  slack: { name: "Slack", description: "Alertas e colaboração", category: "Comunicação", initials: "S", color: "purple", rank: 6 },
  jacad: { name: "JACAD", description: "Dados acadêmicos", category: "Acadêmico", initials: "J", color: "blue", rank: 7 },
  sponte: { name: "Sponte", description: "Gestão educacional", category: "Acadêmico", initials: "S", color: "blue", rank: 8 },
  sophia: { name: "SophiA", description: "Vida acadêmica", category: "Acadêmico", initials: "S", color: "blue", rank: 9 },
  moodle: { name: "Moodle", description: "Aprendizagem e engajamento", category: "Acadêmico", initials: "m", color: "orange", rank: 10 },
  canvas: { name: "Canvas", description: "Ensino e aprendizagem", category: "Acadêmico", initials: "C", color: "red", rank: 11 },
  omie: { name: "Omie", description: "Financeiro e faturamento", category: "Financeiro", initials: "O", color: "cyan", rank: 12 },
  asaas: { name: "Asaas", description: "Cobrança e pagamentos", category: "Financeiro", initials: "A", color: "blue", rank: 13 },
  openai: { name: "OpenAI", description: "Assistentes e automações", category: "IA", initials: "AI", color: "gray", rank: 14 },
  googlesheets: { name: "Google Sheets", description: "Planilhas e análise", category: "Produtividade", initials: "▤", color: "green", rank: 15 },
};
export function normalizeAppKey(value: string): string {
  const clean = value.toLocaleLowerCase("en-US").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]/g, "");
  const aliases: Record<string, string> = { microsoftoutlook:"outlook", outlook365:"outlook", sophiaapi:"sophia" };
  return aliases[clean] || clean;
}
function categoryOf(value?: string | null): AppsCategory {
  const key = (value || "").toLowerCase();
  if (/academic|educa|lms|learning|school|student|ensino/.test(key)) return "Acadêmico";
  if (/crm|relationship/.test(key)) return "CRM e relacionamento";
  if (/support|suporte|atendimento|helpdesk|customer_service/.test(key)) return "Atendimento e suporte";
  if (/marketing|campaign/.test(key)) return "Marketing institucional";
  if (/calendar|schedul|appointment|agenda|agendamento/.test(key)) return "Agenda e agendamento";
  if (/document|arquivo|storage|file|drive|sharepoint/.test(key)) return "Documentos e arquivos";
  if (/spreadsheet|planilha|analise|análise|analysis|analytics|database/.test(key)) return "Dados e análise";
  if (/finan|billing|payment|erp|accounting|bank/.test(key)) return "Financeiro";
  if (/communicat|messag|email|mail|collaborat|social|crm|support|marketing|telephony/.test(key)) return "Comunicação";
  if (/ai|artificial|llm|machine_learning/.test(key)) return "IA";
  if (/document|calendar|productiv|produtiv|file|spreadsheet|task|project|storage|data|schedule/.test(key)) return "Produtividade";
  return "Outros";
}
function nameInitials(name: string) {
  return name.trim().split(/\s+/).slice(0,2).map(word=>word[0]||"").join("").toUpperCase().slice(0,2);
}
function nativeStatus(evidence?: NativeEvidence): { status: AppsStatus; statusText: string } {
  if (!evidence || !evidence.configured) return { status:"available", statusText:"Configuração necessária" };
  if (evidence.enabled === false) return {status:"inactive",statusText:"Desativado"};
  if (["error","failed"].includes((evidence.last_sync_status || evidence.status || "").toLowerCase())) return {status:"error",statusText:"Requer atenção"};
  if (["authenticated","connected"].includes((evidence.status||"").toLowerCase())) return { status:"connected", statusText:"Conectado" };
  return {status:"configured",statusText:"Configurado"};
}
export function unifyAppsCatalog(
  natives: NativeApp[], remotes: RemoteApp[], accounts: RemoteAccount[],
  evidence: Partial<Record<"jacad"|"sponte", NativeEvidence | undefined>> = {},
): CatalogApp[] {
  const apps = new Map<string,CatalogApp>();
  for (const source of natives) {
    const key=normalizeAppKey(source.id);
    const info=editorial[key];
    const connection=nativeStatus(key==="jacad"||key==="sponte" ? evidence[key] : undefined);
    apps.set(key,{
      id:key,slug:source.id,name:info?.name||source.name,description:info?.description||source.description||"Integração de dados da organização",
      category:info?.category||categoryOf(source.category),
      initials:info?.initials||nameInitials(source.name),color:info?.color||"gray",
      status:connection.status,statusText:connection.statusText,
      native:true,external:false,route:"/conectores",
    });
  }
  for(const source of remotes){
    const key=normalizeAppKey(source.slug);
    // The infrastructure vendor is never a customer-facing catalog app.
    if (key === "composio") continue;
    const info=editorial[key];
    const active=accounts.find(account=>normalizeAppKey(account.toolkit_slug)===key && account.status==="active");
    const existing=apps.get(key);
    // A locally active OAuth record does not prove that tools can execute.
    const state=active ? {status:"configured" as const,statusText:"Conta registrada"} : {status:"available" as const,statusText:"Disponível"};
    const base:CatalogApp={
      id:key,slug:source.slug,name:info?.name||source.name,
      description:info?.description||(source.description?.replace(/\bcomposio\b/gi, "MIRA").replace(/\btoolkits?\b/gi,"aplicativos") || "Conexão com o seu workspace"),
      category:info?.category||(source.mira_category_label || source.mira_category || source.category || source.categories?.[0] ? categoryOf(source.mira_category_label || source.mira_category || source.category || source.categories?.[0]) : existing?.category || "Outros"),
      initials:info?.initials||nameInitials(source.name),color:info?.color||"gray",
      status:state.status,statusText:state.statusText,
      native:false,external:true,route:"/dados",
      connectedAccountName:active?.display_name||undefined,
      logoUrl:source.logo||undefined,website:source.app_url||undefined,
    };
    apps.set(key,existing ? {
      ...base,...existing,external:true,native:true,
      status:existing.status==="available" ? state.status : existing.status,
      statusText:existing.status==="available" ? state.statusText : existing.statusText,
      connectedAccountName:base.connectedAccountName,
    }:base);
  }
  return [...apps.values()].sort((a,b)=>{
    const rankA=editorial[a.id]?.rank??10000,rankB=editorial[b.id]?.rank??10000;
    return rankA-rankB || a.name.localeCompare(b.name,"pt-BR");
  });
}
export function filterAppsCatalog(rows: CatalogApp[], query: string, category: string, tab: string): CatalogApp[] {
 const search=query.trim().toLocaleLowerCase("pt-BR");
 return rows.filter(item=>
  (!category || category==="Todos"||item.category===category) &&
  (tab!=="Conectados" || ["connected","configured"].includes(item.status)) &&
  (!search || [item.name,item.description,item.category].some(s=>s.toLocaleLowerCase("pt-BR").includes(search)))
 ).sort((a,b)=>tab==="Conectados" ? a.name.localeCompare(b.name,"pt-BR") : 0);
}
