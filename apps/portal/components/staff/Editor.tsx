'use client';
import {FormEvent,useState} from 'react';
import {defaults,normalize,type Field,type Row} from '../../lib/staff';
export default function Editor({fields,record={},onSave,busy,title='Save'}:{fields:Field[];record?:Row;onSave:(values:Row)=>void;busy:boolean;title?:string}){
 const [values,setValues]=useState(()=>defaults(fields,record));
 function submit(event:FormEvent){event.preventDefault();onSave(normalize(values,fields));}
 return <form className="staff-form" onSubmit={submit}><div className="field-grid">{fields.map(field=>{
  let options=field.options||[];
  if(field.key==='vehicle_id'&&values.partner_id)options=options.filter(option=>!record._vehicles||record._vehicles.some((v:Row)=>v.id===option.id&&Number(v.partner_id)===Number(values.partner_id)));
  return <label key={field.key}>{field.label}{field.required?' *':''}{field.type==='textarea'?<textarea rows={3} value={values[field.key]} onChange={e=>setValues({...values,[field.key]:e.target.value})} required={field.required}/>:field.type==='select'?<select value={values[field.key]} required={field.required} onChange={e=>setValues({...values,[field.key]:e.target.value,...(field.key==='partner_id'?{vehicle_id:''}:{})})}><option value="">Select…</option>{options.map(option=><option value={option.id} key={option.id}>{option.name}</option>)}</select>:<input type={field.type||'text'} value={values[field.key]} required={field.required} min={field.min??(field.type==='number'?0:undefined)} max={field.max} step={field.type==='number'?'any':undefined} minLength={field.type==='password'&&field.required?12:undefined} autoComplete={field.type==='password'?'new-password':undefined} onChange={e=>setValues({...values,[field.key]:e.target.value})}/>}</label>;
 })}</div><button className="primary" disabled={busy}>{busy?'Saving…':title}</button></form>;
}
