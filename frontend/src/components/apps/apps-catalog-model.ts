/** MIRA-owned display registry. Provider implementation is intentionally not part of user-facing copy.
 * This is discovery metadata, NOT an assertion that any account has been configured.
 */
export type AppCategory = "Comunicação" | "Acadêmico" | "Financeiro" | "Produtividade" | "IA" | "CRM" | "Documentos" | "Atendimento" | "Marketing";
export type AppStatus = "connected" | "configured" | "listed" | "request" | "unknown";
export type AppEntry = {
  id: string; name: string; description: string; category: AppCategory;
  status: AppStatus; kind: "native" | "app"; href?: string; providerSlug?: string;
};
export type LiveApp = { slug: string; name: string; description?: string | null; categories?: string[]; category?: string | null; enabled?: boolean };
export type AccountEvidence = { toolkit_slug: string; status: string; disconnected_at?: string | null };
export type NativeEntry = { id: string; name: string; category?: string; description?: string };

const groups: Array<[AppCategory, Array<[string, string, string]>]> = [
  ["Comunicação", [
    ["gmail","Gmail","E-mail institucional"],["outlook","Outlook","E-mail e calendário"],
    ["slack","Slack","Alertas e colaboração"],["microsoft_teams","Microsoft Teams","Mensagens e reuniões"],
    ["zoom","Zoom","Videoconferências"],["zoom_chat","Zoom Team Chat","Mensagens em equipe"],["aircall","Aircall","Telefonia"],
  ]],
  ["Acadêmico", [
    ["jacad","JACAD","Gestão acadêmica"],["sponte","Sponte","Gestão educacional"],
    ["sophia","SophiA","Vida acadêmica"],["moodle","Moodle","LMS e aprendizagem"],
    ["canvas","Canvas","Ensino e aprendizagem"],["gvcollege","GVcollege","Gestão acadêmica"],
    ["totvs_rm","TOTVS RM","Gestão e operações institucionais"],["gvdasa","GVDASA","Sistema educacional"],
    ["wpensar","WPensar","Gestão educacional"],
  ]],
  ["Financeiro", [
    ["asaas","Asaas","Cobrança e pagamentos"],["omie","Omie","Financeiro e faturamento"],
    ["xero","Xero","Contabilidade"],["zoho_books","Zoho Books","Contabilidade"],
    ["freshbooks","FreshBooks","Gestão financeira"],["netsuite","Oracle NetSuite","ERP financeiro"],
    ["sage_intacct","Sage Intacct","Finanças corporativas"],["odoo","Odoo","Gestão empresarial"],
    ["erpnext","ERPNext","Gestão empresarial"],["stripe","Stripe","Pagamentos"],
  ]],
  ["Produtividade", [
    ["asana","Asana","Projetos e tarefas"],["trello","Trello","Quadros e tarefas"],
    ["clickup","ClickUp","Trabalho em equipe"],["notion","Notion","Conhecimento e projetos"],
    ["googlecalendar","Google Calendar","Agenda e eventos"],["calendly","Calendly","Agendamentos"],
    ["cal","Cal.com","Agendamentos"],
  ]],
  ["Documentos", [
    ["googledrive","Google Drive","Arquivos e documentos"],["one_drive","OneDrive","Armazenamento de arquivos"],
    ["share_point","SharePoint","Documentos e equipes"],["dropbox","Dropbox","Arquivos compartilhados"],
    ["googlesheets","Google Sheets","Planilhas e análise"],["excel","Microsoft Excel","Planilhas"],
    ["airtable","Airtable","Bases estruturadas"],
  ]],
  ["CRM", [
    ["hubspot","HubSpot","CRM e relacionamento"],["salesforce","Salesforce","Gestão de clientes"],
    ["pipedrive","Pipedrive","Funil comercial"],["dynamics365","Dynamics 365","Gestão de relacionamento"],
  ]],
  ["Atendimento", [
    ["zendesk","Zendesk","Central de suporte"],["freshdesk","Freshdesk","Atendimento"],
    ["intercom","Intercom","Mensagens e suporte"],["zoho_desk","Zoho Desk","Tickets de atendimento"],
  ]],
  ["Marketing", [
    ["mailchimp","Mailchimp","E-mail marketing"],["brevo","Brevo","Comunicação multicanal"],
    ["active_campaign","ActiveCampaign","Automação de marketing"],["customerio","Customer.io","Engajamento"],
  ]],
  ["IA", [["openai","OpenAI","Inteligência artificial e automações"]]],
];
const nativeNames = new Set(["jacad","sponte","sophia","moodle","canvas","gvcollege","totvs_rm","gvdasa","wpensar","asaas","omie"]);
const priority = ["whatsapp","gmail","outlook","googlecalendar","googledrive","slack","jacad","sponte","sophia","moodle","canvas","omie","asaas","openai","googlesheets"];
export const categories: Array<"Todos" | AppCategory> = ["Todos","Comunicação","Acadêmico","Financeiro","Produtividade","IA","CRM","Documentos","Atendimento","Marketing"];
export const editorialCatalog: AppEntry[] = [
  {id:"whatsapp",name:"WhatsApp",description:"Atendimento e campanhas",category:"Comunicação",status:"request",kind:"native",href:"/disparos"} as AppEntry,
  ...groups.flatMap(([category, items]) => items.map(([id,name,description]):AppEntry=>({
    id,name,description,category,status:"request",kind:nativeNames.has(id)?"native":"app",
    href:nativeNames.has(id)?"/conectores":undefined,providerSlug:id
  }))),
].sort((a,b)=>{const ia=priority.indexOf(a.id), ib=priority.indexOf(b.id);
  return (ia<0?999:ia)-(ib<0?999:ib) || a.name.localeCompare(b.name,"pt-BR");});
const alias: Record<string,string> = {
  "google_drive":"googledrive","google_sheets":"googlesheets","google_calendar":"googlecalendar",
  "microsoft_outlook":"outlook","microsoft_teams":"microsoft_teams","zoho_books":"zoho_books",
  "sophia":"sophia","totvsrm":"totvs_rm",
};
const norm = (value:string) => value.toLowerCase().replace(/[^a-z0-9]/g,"");
function identifier(id:string) {return alias[id.toLowerCase()] || id.toLowerCase();}
function knownCategory(raw:string):AppCategory {
  const key=raw.toLowerCase();
  if (/academic|educa|lms|school/.test(key)) return "Acadêmico";
  if (/financ|account|billing|payment|erp/.test(key)) return "Financeiro";
  if (/commun|mail|messag|chat/.test(key)) return "Comunicação";
  if (/calendar|schedul|project|task|productiv/.test(key)) return "Produtividade";
  if (/document|file|drive|spreadsheet|data_analysis/.test(key)) return "Documentos";
  if (/market/.test(key)) return "Marketing";
  if (/support|helpdesk|service/.test(key)) return "Atendimento";
  if (/crm|sales/.test(key)) return "CRM";
  return "Produtividade";
}
export function isRemoteConnected(account: AccountEvidence) {
  return !account.disconnected_at && ["active","connected","authenticated"].includes(account.status.toLowerCase());
}
export function mergeAppCatalog(
  listed: LiveApp[] | undefined, native: NativeEntry[] | undefined, accounts: AccountEvidence[] | undefined,
  knownState: { jacad?: boolean | "connected"; sponte?: boolean | "connected" } = {},
): AppEntry[] {
  const entries=new Map(editorialCatalog.map(x=>[x.id,{...x}]));
  const ensure=(id:string,name:string,description:string,category:AppCategory,kind:AppEntry["kind"])=>{
    const found=[...entries.values()].find(x=>norm(x.id)===norm(id)||norm(x.name)===norm(name));
    if(found) return found;
    const row:AppEntry={id,name,description,category,status:"request",kind};
    entries.set(id,row);return row;
  };
  for(const source of (native||[])){
    if(!source.id || !source.name)continue;
    const item=ensure(identifier(source.id),source.name,source.description||"Integração com dados da instituição",knownCategory(source.category||""),"native");
    item.kind="native";item.href="/conectores";
    // A registered native connector is not proof that tenant credentials were configured.
  }
  for(const live of (listed||[])){
    if(!live.slug || !live.name)continue;
    const item=ensure(identifier(live.slug),live.name,live.description||"Integração com seu ambiente",knownCategory(live.category||live.categories?.join(" ")||""),"app");
    if(item.kind!=="native")item.status=live.enabled?"configured":"listed";
  }
  for(const [key,configured] of Object.entries(knownState)){
    const item=entries.get(key);
    if(item && configured)item.status=configured==="connected"?"connected":"configured";
  }
  for(const account of accounts||[]){
    if(!isRemoteConnected(account))continue;
    const key=identifier(account.toolkit_slug);
    const item=[...entries.values()].find(x=>norm(x.id)===norm(key));
    if(item && item.kind==="app") item.status="connected";
  }
  return [...entries.values()].sort((a,b)=>{
    const ia=priority.indexOf(a.id),ib=priority.indexOf(b.id);
    return (ia<0?999:ia)-(ib<0?999:ib)||a.name.localeCompare(b.name,"pt-BR");
  });
}
export function filterApps(items:AppEntry[],query:string,category:string,view:string):AppEntry[]{
 const q=query.trim().toLocaleLowerCase("pt-BR");
 const filtered=items.filter(item=>(category==="Todos"||item.category===category)
   && (!q||[item.name,item.description,item.category].some(x=>x.toLocaleLowerCase("pt-BR").includes(q)))
   && (view!=="connected"||item.status==="connected"));
 return view==="popular" ? filtered.slice(0,24):filtered;
}
