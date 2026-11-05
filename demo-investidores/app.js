/* MIRA investor demo — standalone Cloudflare Pages prototype.
 * Data is 100% synthetic and is never sent to a server. All actions are local.
 * This file deliberately has no API credentials, fetch(), cookies or storage.
 */
"use strict";

const students = [
  {id:"NV-1001",name:"Marina Oliveira",course:"Administração",semester:5,risk:"critico",riskScore:92,signal:"Atraso financeiro",secondary:"Queda de frequência",attendance:57,fees:2,grade:6.1},
  {id:"NV-1002",name:"Rafael Monteiro",course:"Direito",semester:3,risk:"critico",riskScore:89,signal:"Queda de frequência",secondary:"Queda de rendimento",attendance:51,fees:0,grade:5.3},
  {id:"NV-1003",name:"Gabriela Costa",course:"Enfermagem",semester:6,risk:"alto",riskScore:77,signal:"Queda de rendimento",secondary:"Atraso financeiro",attendance:73,fees:1,grade:5.7},
  {id:"NV-1004",name:"Pedro Santos",course:"Ciência da Computação",semester:4,risk:"alto",riskScore:74,signal:"Atraso financeiro",secondary:"Baixa participação",attendance:78,fees:2,grade:7.1},
  {id:"NV-1005",name:"Isabela Lima",course:"Psicologia",semester:2,risk:"alto",riskScore:71,signal:"Queda de frequência",secondary:"Baixa participação",attendance:69,fees:0,grade:6.8},
  {id:"NV-1006",name:"Lucas Ferreira",course:"Administração",semester:1,risk:"moderado",riskScore:56,signal:"Atraso financeiro",secondary:"Dados incompletos",attendance:84,fees:1,grade:7.6},
  {id:"NV-1007",name:"Beatriz Almeida",course:"Pedagogia",semester:7,risk:"moderado",riskScore:49,signal:"Queda de frequência",secondary:"Dados incompletos",attendance:81,fees:0,grade:7.9},
  {id:"NV-1008",name:"André Ribeiro",course:"Engenharia Civil",semester:3,risk:"moderado",riskScore:44,signal:"Queda de rendimento",secondary:"Baixa participação",attendance:87,fees:0,grade:6.9},
  {id:"NV-1009",name:"Camila Martins",course:"Direito",semester:5,risk:"moderado",riskScore:38,signal:"Atraso financeiro",secondary:"Dados incompletos",attendance:90,fees:1,grade:8.1},
  {id:"NV-1010",name:"Felipe Barbosa",course:"Psicologia",semester:6,risk:"baixo",riskScore:21,signal:"Sem sinal prioritário",secondary:"—",attendance:93,fees:0,grade:8.7},
  {id:"NV-1011",name:"Júlia Rodrigues",course:"Enfermagem",semester:4,risk:"baixo",riskScore:17,signal:"Sem sinal prioritário",secondary:"—",attendance:96,fees:0,grade:8.9},
  {id:"NV-1012",name:"Thiago Pereira",course:"Pedagogia",semester:2,risk:"baixo",riskScore:13,signal:"Sem sinal prioritário",secondary:"—",attendance:94,fees:0,grade:9.1}
];
let interventions = [
  {id:1,student:"NV-1001",title:"Acolhimento financeiro e acadêmico",note:"Revisar possibilidades de apoio com o responsável institucional, sem iniciar cobrança automática.",owner:"Ana Duarte",status:"Em acompanhamento"},
  {id:2,student:"NV-1002",title:"Revisar histórico de frequência",note:"Validar evidências e convidar a coordenação a analisar o caso individualmente.",owner:"Caio Menezes",status:"Pendente de revisão"},
  {id:3,student:"NV-1003",title:"Encaminhamento pedagógico",note:"Analisar avaliações recentes antes de definir uma ação de orientação.",owner:"Ana Duarte",status:"Planejada"}
];
let filterRisk="todos";
let currentStudent=null;
let toastTimer=null;
let tourIndex=0;
const titles={"visao-geral":"Visão geral","alunos":"Alunos","trabalho":"Central de trabalho","intervencoes":"Intervenções","resultados":"Resultados","integracoes":"Dados e integrações"};
const levels={critico:"Crítico",alto:"Alto",moderado:"Moderado",baixo:"Baixo"};

function initials(name){return name.trim().split(/\s+/).slice(0,2).map(x=>x[0]).join("").toUpperCase()}
function el(tag,cls,text){const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=String(text);return node}
function studentById(id){return students.find(s=>s.id===id)}
function riskTag(risk){const span=el("span","risk-tag "+risk,levels[risk]);return span}
function showToast(message){
  const node=document.getElementById("toast");
  node.replaceChildren(el("span","",message));
  node.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{node.hidden=true},4800);
}
function navigate(view){
  if(!titles[view])return;
  document.querySelectorAll(".view").forEach(n=>n.classList.toggle("active",n.id==="view-"+view));
  document.querySelectorAll(".nav-button").forEach(n=>{
    const active=n.dataset.view===view;n.classList.toggle("active",active);
    if(active)n.setAttribute("aria-current","page");else n.removeAttribute("aria-current");
  });
  document.getElementById("breadcrumb-current").textContent=titles[view];
  document.getElementById("sidebar").classList.remove("open");
  if(location.hash!=="#"+view)history.replaceState(null,"","#"+view);
  window.scrollTo({top:0,behavior:"instant"});
}
function priorityRow(student){
  const row=el("div","priority-person");
  row.setAttribute("role","button");row.tabIndex=0;
  row.append(el("div","person-avatar",initials(student.name)));
  const detail=el("div","person-detail");
  detail.append(el("strong","",student.name),el("small","",student.signal+" · "+student.course));
  row.append(detail,riskTag(student.risk),el("span","chevron","›"));
  row.addEventListener("click",()=>openStudent(student.id));
  row.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();openStudent(student.id)}});
  return row
}
function renderDashboard(){
  const list=document.getElementById("priority-list");
  list.replaceChildren(...students.filter(s=>["critico","alto"].includes(s.risk)).slice(0,5).map(priorityRow));
  document.getElementById("signals-panel").replaceChildren(...[
    ["Atraso financeiro",5,83],["Queda de frequência",4,67],["Queda de rendimento",3,50],["Baixa participação",3,50]
  ].map(([name,count,percent])=>{
    const row=el("div","signal-row"),track=el("div","signal-track"),bar=el("div","signal-fill");
    bar.style.width=percent+"%";track.append(bar);row.append(el("span","",name),track,el("strong","",count));return row
  }));
  const preview=document.getElementById("work-preview");
  preview.replaceChildren(...interventions.slice(0,4).map(item=>{
    const row=el("div","work-row");const left=el("div");
    left.append(el("div","work-title",item.title),el("div","work-description",studentById(item.student)?.name+" · "+item.owner));
    row.append(left,el("span","work-label",item.status));return row
  }));
  document.getElementById("active-interventions-count").textContent=String(interventions.length)
}
function renderStudents(){
  const query=document.getElementById("student-search").value.trim().toLocaleLowerCase("pt-BR");
  const found=students.filter(s=>(filterRisk==="todos"||s.risk===filterRisk)&&
    [s.name,s.id,s.course].some(value=>value.toLocaleLowerCase("pt-BR").includes(query)));
  const tbody=document.getElementById("students-table");tbody.replaceChildren();
  if(!found.length){const tr=el("tr");const td=el("td","empty-search","Nenhum aluno fictício corresponde aos filtros.");td.colSpan=6;tr.append(td);tbody.append(tr);return}
  for(const student of found){
    const tr=el("tr","row-link");tr.tabIndex=0;tr.setAttribute("aria-label","Abrir ficha de "+student.name);
    const first=el("td");const flex=el("div","student-name-cell");const name=el("div");name.append(el("strong","",student.name),el("small","",student.id));
    flex.append(el("div","person-avatar",initials(student.name)),name);first.append(flex);
    tr.append(first,el("td","",student.course),el("td","",student.semester+"º"),el("td"),el("td","",student.signal),el("td","chevron","›"));
    tr.children[3].append(riskTag(student.risk));
    tr.addEventListener("click",()=>openStudent(student.id));
    tr.addEventListener("keydown",event=>{if(event.key==="Enter"){openStudent(student.id)}});
    tbody.append(tr)
  }
}
function field(label,value){const wrapper=el("div","drawer-field");wrapper.append(el("span","",label),el("strong","",value));return wrapper}
function openStudent(id){
  const student=studentById(id);if(!student)return;currentStudent=student.id;
  document.getElementById("drawer-name").textContent=student.name;
  document.getElementById("drawer-course").textContent=student.course+" · "+student.semester+"º semestre · "+student.id;
  const content=document.getElementById("drawer-content");content.replaceChildren();
  const section1=el("section","drawer-section");section1.append(el("h3","","Visão do acompanhamento"));
  const fields=el("div","drawer-field-grid");
  const risk=el("div","drawer-field");risk.append(el("span","","Risco ilustrativo"),riskTag(student.risk));
  fields.append(risk,field("Índice simulado",student.riskScore+" / 100"),field("Média acadêmica (exemplo)",student.grade.toFixed(1).replace(".",",")),field("Frequência (exemplo)",student.attendance+"%"));
  section1.append(fields);
  const section2=el("section","drawer-section");section2.append(el("h3","","Sinais de atenção"));
  section2.append(el("div","drawer-signal","Sinal principal · "+student.signal));
  if(student.secondary!=="—")section2.append(el("div","drawer-signal","Sinal complementar · "+student.secondary));
  section2.append(el("p","drawer-note","Os sinais acima são inventados para demonstrar como a MIRA apresentaria a evidência de um caso. Não são cálculos de modelo ou dados institucionais."));
  const section3=el("section","drawer-section");section3.append(el("h3","","Contexto acadêmico e financeiro"));
  const values=el("div","drawer-field-grid");
  values.append(field("Matrícula",student.id),field("Semestre",student.semester+"º"),field("Mensalidades vencidas (exemplo)",String(student.fees)),field("Situação","Acompanhamento sintético"));
  section3.append(values);
  const btn=el("button","button primary drawer-cta","+ Planejar intervenção fictícia");
  btn.addEventListener("click",()=>{closeDrawer();createIntervention(student.id)});
  const section4=el("section","drawer-section");section4.append(el("h3","","Próximo passo"),el("p","drawer-note","Na operação real, uma equipe autorizada pode revisar evidências, registrar decisão e acompanhar o resultado. Este botão altera apenas o estado temporário da demonstração."),btn);
  content.append(section1,section2,section3,section4);
  document.getElementById("modal-backdrop").hidden=false;
  const drawer=document.getElementById("student-drawer");drawer.classList.add("open");drawer.setAttribute("aria-hidden","false");
  document.getElementById("drawer-close").focus()
}
function closeDrawer(){const drawer=document.getElementById("student-drawer");drawer.classList.remove("open");drawer.setAttribute("aria-hidden","true");document.getElementById("modal-backdrop").hidden=true;currentStudent=null}
function renderWork(){
  const target=document.getElementById("work-table");target.replaceChildren();
  document.getElementById("work-count").textContent=interventions.length+" atividades";
  interventions.forEach(intervention=>{
    const student=studentById(intervention.student);
    const row=el("div","work-line");const ico=el("div","work-icon","◎");const middle=el("div");
    middle.append(el("strong","",intervention.title),el("p","",(student?.name||"Aluno fictício")+" · Responsável: "+intervention.owner+" · "+intervention.note));
    row.append(ico,middle,el("span","work-label",intervention.status));target.append(row)
  })
}
function renderInterventions(){
  const target=document.getElementById("intervention-list");target.replaceChildren();
  for(const item of interventions){
    const student=studentById(item.student);const card=el("article","panel intervention-card");
    card.append(el("span","pill neutral",item.status),el("h3","",item.title),el("p","",item.note));
    const meta=el("div","intervention-meta");const owner=el("div","intervention-avatars");
    owner.append(el("span","mini-avatar",initials(item.owner)),el("span","",item.owner));
    meta.append(owner,el("span","",student?student.name:"Aluno fictício"));card.append(meta);target.append(card)
  }
}
function createIntervention(studentId){
  const id=studentId||"NV-1001";const student=studentById(id);
  interventions.unshift({id:Date.now(),student:id,title:"Análise individual planejada",note:"Revisar sinais fictícios, reunir contexto e registrar orientação humana. Nenhum contato enviado.",owner:"Equipe de demonstração",status:"Planejada"});
  renderDashboard();renderWork();renderInterventions();navigate("intervencoes");
  showToast("Intervenção fictícia planejada para "+student.name+". Nenhum dado foi salvo ou enviado.")
}
function startTour(){
  const order=["visao-geral","alunos","intervencoes","resultados","integracoes"];
  const tips=[
    "1/5 · Comece pela distribuição de risco e pelas prioridades.",
    "2/5 · Abra a ficha de Marina Oliveira e mostre a explicação do risco.",
    "3/5 · Demonstre o planejamento de uma intervenção sem disparos reais.",
    "4/5 · Mostre como um resultado precisa ser verificado.",
    "5/5 · Mostre a arquitetura preparada para diferentes fontes de dados."
  ];
  navigate(order[tourIndex]);showToast(tips[tourIndex]);tourIndex=(tourIndex+1)%order.length
}
document.getElementById("primary-nav").addEventListener("click",event=>{
  const btn=event.target.closest("[data-view]");if(btn)navigate(btn.dataset.view)
});
document.querySelectorAll("[data-navigate]").forEach(btn=>btn.addEventListener("click",()=>navigate(btn.dataset.navigate)));
document.querySelectorAll("[data-risk]").forEach(btn=>btn.addEventListener("click",()=>{
  filterRisk=btn.dataset.risk;document.querySelectorAll("[data-risk]").forEach(n=>n.classList.toggle("active",n===btn));renderStudents()
}));
document.getElementById("student-search").addEventListener("input",renderStudents);
document.getElementById("drawer-close").addEventListener("click",closeDrawer);
document.getElementById("modal-backdrop").addEventListener("click",closeDrawer);
document.addEventListener("keydown",event=>{if(event.key==="Escape")closeDrawer()});
document.getElementById("tour-button").addEventListener("click",startTour);
document.getElementById("new-intervention-btn").addEventListener("click",()=>createIntervention("NV-1001"));
document.getElementById("create-work-btn").addEventListener("click",()=>createIntervention("NV-1001"));
document.getElementById("mobile-menu").addEventListener("click",()=>document.getElementById("sidebar").classList.toggle("open"));
window.addEventListener("hashchange",()=>{const hash=location.hash.slice(1);if(titles[hash])navigate(hash)});
renderDashboard();renderStudents();renderInterventions();renderWork();
navigate(titles[location.hash.slice(1)]?location.hash.slice(1):"visao-geral");
