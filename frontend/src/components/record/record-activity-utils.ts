import type { WorkTimelineItem } from "@/types/work";
import type { RecordActivityEvent } from "./record-types";

/** Only event metadata from the actual institutional timeline, never notes/payloads. */
export function fromStudentWorkTimeline(items: WorkTimelineItem[]):RecordActivityEvent[] {
  const kinds:Record<string,RecordActivityEvent["kind"]>={
    risk_assessment:"risk", intervention_log:"intervention",
    work_activity:"activity", engagement_event:"contact",
  };
  const labels:Record<string,string>={
    risk_assessment:"Avaliação de risco registrada",
    intervention_log:"Intervenção registrada",
    work_activity:"Atividade operacional registrada",
    engagement_event:"Engajamento registrado",
  };
  return items.filter(item=>Object.hasOwn(kinds,item.source)&&Boolean(item.id))
    .map(item=>{
      const refs=item.refs||{};
      const status=typeof refs.status==="string"?refs.status:null;
      const channel=typeof refs.channel==="string"?refs.channel:null;
      const actor=typeof refs.assignee_display_name==="string"?refs.assignee_display_name:null;
      return {
        id:item.source+":"+item.id,kind:kinds[item.source],at:item.at||null,
        title:labels[item.source],origin:item.source.replaceAll("_"," "),
        status,actor,
        description:channel?"Canal: "+channel:null,
      };
    }).sort((a,b)=>(b.at||"").localeCompare(a.at||""));
}
