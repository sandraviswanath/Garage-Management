export type Job = {
  id:number; name:string; state:string; vehicle:string; model:string; concern:string; date:string; technician:string;
  quote:null | {id:number; name:string; total:number; currency:string; version:string; lines:{name:string; qty:number; total:number}[]};
  pending_quotes?:{id:number;name:string;total:number;currency:string;version:string;lines:{name:string;qty:number;total:number}[]}[];
  checks:{id:number;name:string;done:boolean}[];
  parts:{id:number;name:string;quantity:number;state:string}[];
  photos:{id:number;name:string}[];
  invoices:{id:number;name:string;total:number;currency:string;payment_state:string}[];
};
export type Dashboard = {user:{name:string;role:string};jobs:Job[];vehicles:{id:number;plate:string;model:string}[]};
