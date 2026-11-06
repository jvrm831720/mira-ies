import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import ts from "typescript";
const dir=path.dirname(fileURLToPath(import.meta.url));
function load(file) {
  const source=readFileSync(path.join(dir,file),"utf8");
  const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
  const exports={};
  vm.runInNewContext(compiled,{exports});
  return exports;
}
const {studentPropertyGroups,studentRecordIdentity,studentRelations,STUDENT_RECORD_EDITABLE_FIELDS}=load("student-record-data.ts");
const {fromStudentWorkTimeline}=load("record-activity-utils.ts");

test("viewer never receives financial, risk or assessment properties",()=>{
 const student={id:"a",nome:"Ana",matricula:"00123",curso:"Engenharia",saldo_devedor:240,
   risk_score:77,status_financeiro:"VENCIDO",nota_media:8.5};
 const visible=studentPropertyGroups(student,false);
 assert.deepEqual(JSON.parse(JSON.stringify(visible.map(group=>group.id))),["identification"]);
 assert.equal(JSON.stringify(visible).includes("240"),false);
 assert.equal(JSON.stringify(visible).includes("77"),false);
 const privileged=studentPropertyGroups(student,true);
 assert.deepEqual(JSON.parse(JSON.stringify(privileged.map(group=>group.id))),["identification","academic","risk","finance"]);
 assert.deepEqual(Array.from(STUDENT_RECORD_EDITABLE_FIELDS),[]);
});

test("record identity remains canonical across list, drawer and full page",()=>{
 const student={id:"a",nome:"Ana Souza",matricula:"00042",curso:"Direito",campus:"Centro"};
 const r=studentRecordIdentity("a",student);
 assert.equal(r.kind,"student");
 assert.equal(r.id,"a");
 assert.equal(r.title,"Ana Souza");
 assert.equal(r.subtitle,"Matrícula 00042 · Direito · Centro");
 assert.equal(studentRelations(student).length,2);
});

test("missing score remains missing, not classified as low risk",()=>{
 const props=studentPropertyGroups({id:"a",risk_level:null,risk_score:null},true);
 const risk=props.find(group=>group.id==="risk");
 assert.equal(risk.properties.find(p=>p.key==="risk-level").value,"Sem classificação");
 assert.equal(risk.properties.find(p=>p.key==="risk-score").value,null);
});

test("timeline only includes documented sources; never surfaces internal payloads",()=>{
 const events=fromStudentWorkTimeline([
   {source:"work_activity",id:"e2",at:"2026-11-05T11:00:00Z",summary:"Internal",refs:{status:"completed",payload:{note:"nota interna restrita"}}},
   {source:"intervention_log",id:"e1",at:"2026-11-06T10:00:00Z",summary:"Message",refs:{status:"sent",channel:"email",payload:{message:"sigilo"}}},
   {source:"unknown_internal",id:"x",summary:"private",refs:{hidden:"yes"}},
 ]);
 assert.equal(events.length,2);
 assert.equal(events[0].id,"intervention_log:e1");
 assert.equal(events[0].status,"sent");
 assert.equal(events[0].description,"Canal: email");
 assert.equal(JSON.stringify(events).includes("nota interna"),false);
 assert.equal(JSON.stringify(events).includes("sigilo"),false);
});
