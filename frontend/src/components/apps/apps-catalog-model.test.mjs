import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";
import ts from "typescript";

const current=dirname(fileURLToPath(import.meta.url));
const load=(name)=>readFileSync(resolve(current,name),"utf8");
const outputs={};
vm.runInNewContext(ts.transpileModule(load("apps-catalog-model.ts"),{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
}).outputText,{exports:outputs});
const {unifyAppsCatalog,filterAppsCatalog,normalizeAppKey}=outputs;

test("unifies native and external entries without duplicates",()=>{
 const native=[{id:"jacad",name:"JACAD",category:"academic"},{id:"moodle",name:"Moodle",category:"lms"}];
 const remote=[{slug:"jacad",name:"JACAD remote",category:"education"},{slug:"gmail",name:"Gmail",category:"communication"}];
 const rows=unifyAppsCatalog(native,remote,[]);
 assert.equal(rows.length,3);
 assert.equal(rows.find(x=>x.id==="jacad").native,true);
 assert.equal(rows.find(x=>x.id==="jacad").external,true);
 assert.equal(rows.find(x=>x.id==="gmail").status,"available");
 assert.equal(rows.find(x=>x.id==="moodle").status,"available");
});

test("local account is registered, never automatically presented as verified connected",()=>{
 const apps=unifyAppsCatalog([], [{slug:"gmail",name:"Gmail"}],[{toolkit_slug:"gmail",status:"active",display_name:"equipe@exemplo.edu.br"}]);
 assert.equal(apps[0].status,"configured");
 assert.equal(apps[0].statusText,"Conta registrada");
 assert.equal(apps[0].connectedAccountName,"equipe@exemplo.edu.br");
});

test("native status requires evidence and respects inactive and error",()=>{
 const item=[{id:"jacad",name:"JACAD"}];
 assert.equal(unifyAppsCatalog(item,[],[])[0].status,"available");
 assert.equal(unifyAppsCatalog(item,[],[],{jacad:{configured:true}})[0].status,"configured");
 assert.equal(unifyAppsCatalog(item,[],[],{jacad:{configured:true,status:"connected"}})[0].status,"connected");
 assert.equal(unifyAppsCatalog(item,[],[],{jacad:{configured:true,enabled:false}})[0].status,"inactive");
 assert.equal(unifyAppsCatalog(item,[],[],{jacad:{configured:true,status:"error"}})[0].status,"error");
});

test("filters by category, connection status, and normalized case",()=>{
 const rows=unifyAppsCatalog([{id:"jacad",name:"JACAD"},{id:"moodle",name:"Moodle"}],[],[],{jacad:{configured:true}});
 assert.equal(filterAppsCatalog(rows,"","Acadêmico","Conectados").length,1);
 assert.equal(filterAppsCatalog(rows,"JACAD","Todos","Descobrir").length,1);
 assert.equal(filterAppsCatalog(rows,"xzy","Todos","Descobrir").length,0);
 assert.equal(normalizeAppKey("Google Drive"),"googledrive");
});

test("view keeps provider technical terms out of visible copy and protects permissions",()=>{
 const view=load("apps-catalog-experience.tsx");
 const navigation=load("../layout/navigation.ts");
 const sidebar=load("../layout/sidebar.tsx");
 assert.doesNotMatch(view,/>\s*Composio\s*</i);
 assert.doesNotMatch(view,/statusText:\s*"Conectado"\s*,\s*native:\s*false/);
 assert.match(view,/hasNavigationPermission\(me\.data,\s*"data\.view"\)/);
 assert.match(view,/hasNavigationPermission\(me\.data,\s*"settings\.manage"\)/);
 assert.match(navigation,/href: "\/apps".*permission: "data\.view".*module: "data"/);
 assert.match(sidebar,/paths: \["\/apps", "\/dados"/);
 assert.match(view,/O pedido não será enviado automaticamente/);
});
