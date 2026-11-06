import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import vm from "node:vm";

const folder=dirname(fileURLToPath(import.meta.url));
const source=readFileSync(resolve(folder,"apps-catalog-model.ts"),"utf8");
const output=ts.transpileModule(source,{compilerOptions:{
  module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,
}}).outputText;
const exp={};
vm.runInNewContext(output,{exports:exp});
const {editorialCatalog,mergeAppCatalog,filterApps,isRemoteConnected}=exp;

test("editorial discovery covers native academic, finance and productivity apps without claiming connections",()=>{
 assert.ok(editorialCatalog.length>=45);
 for(const id of ["jacad","sponte","sophia","moodle","canvas","asaas","omie","whatsapp","gmail","googlecalendar"]){
  const app=editorialCatalog.find(x=>x.id===id);
  assert.ok(app,id+" missing");
  assert.equal(app.status,"request","false connected state for "+id);
 }
});
test("connected status requires active matching tenant account, not merely appearance in catalog",()=>{
 const rows=mergeAppCatalog([{slug:"gmail",name:"Gmail",enabled:false}],[],
   [{toolkit_slug:"gmail",status:"revoked",disconnected_at:"2026-11-01T00:00:00Z"}]);
 assert.equal(rows.find(x=>x.id==="gmail").status,"listed");
 const active=mergeAppCatalog([{slug:"gmail",name:"Gmail",enabled:true}],[],
   [{toolkit_slug:"gmail",status:"ACTIVE"}]);
 assert.equal(active.find(x=>x.id==="gmail").status,"connected");
 assert.equal(isRemoteConnected({toolkit_slug:"gmail",status:"ERROR"}),false);
});
test("native connector discovery never means tenant connection is active",()=>{
 const rows=mergeAppCatalog(undefined,[{id:"jacad",name:"JACAD"},{id:"custom_i",name:"Custom Institution"}],undefined);
 assert.equal(rows.find(x=>x.id==="jacad").status,"request");
 assert.equal(rows.find(x=>x.id==="custom_i").status,"request");
 const configured=mergeAppCatalog(undefined,[],undefined,{jacad:true,sponte:false});
 assert.equal(configured.find(x=>x.id==="jacad").status,"configured");
 assert.equal(configured.find(x=>x.id==="sponte").status,"request");
});
test("filtering works across all, category, connected and search",()=>{
 const rows=mergeAppCatalog([{slug:"gmail",name:"Gmail",enabled:true}],[],
  [{toolkit_slug:"gmail",status:"connected"}]);
 assert.ok(filterApps(rows,"","Todos","discover").length>24);
 assert.equal(filterApps(rows,"gmail","Comunicação","discover").length,1);
 assert.equal(filterApps(rows,"gmail","Financeiro","discover").length,0);
 assert.equal(filterApps(rows,"gmail","Todos","connected").length,1);
 assert.equal(filterApps(rows,"asana","Todos","connected").length,0);
 assert.ok(filterApps(rows,"","Todos","popular").length<=24);
});
test("presentation uses MIRA-only language, permission gating and real integration APIs",()=>{
 const ui=readFileSync(resolve(folder,"apps-catalog.tsx"),"utf8");
 const nav=readFileSync(resolve(folder,"../layout/navigation.ts"),"utf8");
 assert.match(ui,/hasNavigationPermission\(me\.data,"data\.view"\)/);
 assert.match(ui,/api\.listConnectors\(\)/);
 assert.match(ui,/api\.composioCatalog\(\)/);
 assert.match(ui,/api\.composioConnections\(\)/);
 assert.match(nav,/href: "\/apps".*permission: "data\.view"/);
 assert.doesNotMatch(ui,/Conectado"\s*:\s*true/);
 assert.ok(!ui.includes("Conta Composio"));
});
