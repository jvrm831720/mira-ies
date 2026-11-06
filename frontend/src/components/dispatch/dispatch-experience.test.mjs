import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const directory=path.dirname(fileURLToPath(import.meta.url));
function loadPureTypeScript(filename){
  const content=readFileSync(path.join(directory,filename),"utf8");
  const code=ts.transpileModule(content,{compilerOptions:{
    module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,
  }}).outputText;
  const exports={};
  vm.runInNewContext(code,{exports,Intl,Date,Number,String,Array,Set,Map,console});
  return exports;
}
const utils=loadPureTypeScript("dispatch-utils.ts");

test("collections cannot use WhatsApp, and unknown profiles are fail-closed",()=>{
  assert.equal(utils.validChannel("collections","whatsapp"),false);
  assert.equal(utils.validChannel("collections","sms"),true);
  assert.equal(utils.permittedPurposes(undefined).length,0);
  assert.deepEqual(Array.from(utils.permittedPurposes("institution")),["retention","academic","service"]);
  assert.deepEqual(Array.from(utils.permittedPurposes("billing")),["collections","service"]);
});

const src={kind:"manual",reference:"upload-1",name:"Importação",category:"workspace",connected:true,can_bind:true,tools:[],automatic_ingestion:false,note:""};
const template={id:"id-1",code:"AVISO-1",version:1,purpose:"retention",channel:"email",subject:"Orientação",body:"Olá {nome}.",status:"approved",created_by:"person",approved_by:"other",approved_at:"2026-11-06"};
const baseDraft={name:"Revisão institucional",purpose:"retention",mode:"targeted",sourceKey:"manual:upload-1:",channel:"email",templateId:"id-1",perMinute:10};

test("draft requires authorized source and approved purpose-specific template",()=>{
  assert.deepEqual(Array.from(utils.validateCampaignDraft(baseDraft,[src],[template],"institution")),[]);
  assert.ok(utils.validateCampaignDraft(baseDraft,[{...src,connected:false}],[template],"institution").length>0);
  assert.ok(utils.validateCampaignDraft(baseDraft,[src],[{...template,status:"draft"}],"institution").length>0);
  assert.ok(utils.validateCampaignDraft({...baseDraft,purpose:"collections"},[src],[template],"billing").length>0);
  assert.ok(utils.validateCampaignDraft({...baseDraft,perMinute:200},[src],[template],"institution").length>0);
});

test("preview counts never claim global totals",()=>{
  const entries=[
    {id:"a",status:"draft",problems:0},
    {id:"b",status:"running",problems:2},
    {id:"c",status:"paused",problems:0},
  ];
  const result=utils.countCampaignPreview(entries);
  assert.equal(result.rows,3);
  assert.equal(result.withProblems,1);
  assert.equal(result.running,1);
  assert.equal(result.paused,1);
});

test("provider acceptance never becomes delivery",()=>{
  assert.equal(utils.postSendLabel("sent"),"Aceito pelo provedor");
  assert.equal(utils.postSendLabel("delivered"),"Entregue (confirmado)");
  assert.equal(utils.postSendLabel("unknown"),"Resultado desconhecido");
  assert.equal(utils.readableDate(undefined),"Não registrado");
  assert.equal(utils.countItemStates([{status:"unknown"},{status:"unknown"},{status:"delivered"}]).unknown,2);
});

test("visual modules cannot trigger live operations through their own code",()=>{
  const folder=directory;
  for(const file of [
    "dispatch-overview.tsx","campaign-index.tsx","campaign-detail.tsx",
    "dispatch-control-center.tsx","dispatch-results.tsx",
  ]){
    const source=readFileSync(path.join(folder,file),"utf8");
    assert.doesNotMatch(source,/dispatchApi\.(approve|action|schedule|stage|intervene|activateProvider|verifyProvider)\s*\(/);
    assert.doesNotMatch(source,/DISPATCH_LIVE_ENABLED|DISPATCH_WORKER_ENABLED/);
  }
});
