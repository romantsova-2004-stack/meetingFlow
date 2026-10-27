export type Person={id:number;name:string}
export type Status='new'|'in_progress'|'done'
export type Task={id:number;description:string;decision_id:number;responsible_id:number;responsible:Person;deadline:string;status:Status;is_overdue:boolean;decision:{id:number;text:string;meeting_id:number};meeting:{id:number;title:string;date:string}}
export type Decision={id:number;meeting_id:number;text:string;tasks:Task[]}
export type Meeting={id:number;title:string;date:string;participants:Person[];decisions:Decision[]}
export type Dashboard={meetings:number;tasks:number;incomplete:number;overdue:number;upcoming_tasks:Task[];recent_meetings:Meeting[];today:string}
export class ApiError extends Error { constructor(message:string,public fields:Record<string,string>={}){super(message)} }
export async function api<T>(path:string,method='GET',body?:unknown):Promise<T>{
 let res:Response
 try {res=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)})} catch {throw new ApiError('Нет связи с сервером. Проверьте подключение и повторите попытку.')}
 let data
 try {data=await res.json()} catch {throw new ApiError('Сервер вернул некорректный ответ. Повторите попытку.')}
 if(!res.ok) throw new ApiError(typeof data.detail==='string'?data.detail:'Не удалось сохранить данные',Object.fromEntries((data.errors||[]).map((e:{field:string;message:string})=>[e.field,e.message])))
 return data
}
export const statuses:Record<Status,string>={new:'Новая',in_progress:'В работе',done:'Выполнено'}
export const dateLabel=(s:string)=>new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short',year:'numeric'}).format(new Date(s+'T12:00:00'))
export const localDate=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
