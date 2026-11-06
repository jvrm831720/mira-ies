import type { StudentRisk } from "@/types/api";
import type { RecordIdentity, RecordPropertyGroup, RecordRelation } from "./record-types";

/** Read-only fields from the existing GET /students/{id}/risk contract.
 * No inferred values, no financial data without the sensitive grant. */
export function studentRecordIdentity(id: string, student: StudentRisk | null | undefined): RecordIdentity {
  return {kind:"student",id,title:student?.nome||"Aluno",caption:"Registro do aluno",
    subtitle:[student?.matricula?"Matrícula "+student.matricula:null,student?.curso,student?.campus].filter(Boolean).join(" · ")||"Identificação não informada"};
}
export function studentPropertyGroups(student: StudentRisk, canSensitive:boolean):RecordPropertyGroup[] {
  const groups:RecordPropertyGroup[]=[{
    id:"identification",title:"Identificação",properties:[
      {key:"matricula",label:"Matrícula",value:student.matricula},
      {key:"curso",label:"Curso",value:student.curso},
      {key:"campus",label:"Campus",value:student.campus},
      {key:"turma",label:"Turma",value:student.turma},
      {key:"status",label:"Situação acadêmica",value:student.status_aluno,type:"status"},
      {key:"semestre",label:"Semestre",value:student.semestre,type:"number"},
    ],
  }];
  if(canSensitive){
    groups.push({id:"academic",title:"Indicadores acadêmicos",properties:[
      {key:"attendance",label:"Presença",value:student.presenca_percentual,type:"percentage"},
      {key:"grade",label:"Nota média",value:student.nota_media,type:"number"},
      {key:"failures",label:"Reprovações",value:student.reprovacoes,type:"number"},
    ]});
    groups.push({id:"risk",title:"Inteligência de permanência",properties:[
      {key:"risk-level",label:"Classificação",value:student.risk_level||"Sem classificação",type:"status"},
      {key:"risk-score",label:"Score",value:typeof student.risk_score==="number"&&Number.isFinite(student.risk_score)?student.risk_score:null,type:"number"},
      {key:"model-score",label:"Score do modelo",value:student.model_risk_score,type:"number"},
      {key:"login-days",label:"Dias sem login",value:student.dias_sem_login,type:"number"},
    ]});
    groups.push({id:"finance",title:"Situação financeira informada",properties:[
      {key:"financial-status",label:"Situação",value:student.status_financeiro,type:"status"},
      {key:"debt",label:"Saldo informado",value:student.saldo_devedor,type:"currency"},
      {key:"delay",label:"Dias de atraso informados",value:student.dias_atraso_boleto,type:"number"},
    ]});
  }
  return groups;
}
export function studentRelations(student:StudentRisk):RecordRelation[] {
  const relations: RecordRelation[] = [];
  if (student.curso) relations.push({id:"course",label:"Curso",value:student.curso,type:"course"});
  if (student.turma) relations.push({id:"class",label:"Turma",value:student.turma,type:"class"});
  if (student.campus) relations.push({id:"campus",label:"Campus",value:student.campus,type:"campus"});
  return relations;
}
/** No backend endpoint exists to edit official student attributes. */
export const STUDENT_RECORD_EDITABLE_FIELDS: ReadonlyArray<string> = Object.freeze([]);
