export type User = {name: string; role: string};
export type Vehicle = {id: number; plate: string; model: string};
export type Quote = {
  id: number; name: string; total: number; currency: string; version: string;
  lines: {name: string; qty: number; total: number}[];
};
export type Invoice = {id: number; name: string; total: number; currency: string; payment_state: string};
export type Job = {
  id: number; name: string; state: string; vehicle: string; model: string; concern: string;
  technician: string; date?: string; quote?: Quote | null; pending_quotes?: Quote[];
  invoices?: Invoice[];
  tasks?: {id: number; description: string; state: string; notes: string}[];
  notes?: {id: number; content: string; kind: string; author: string; date: string}[];
  timers?: {id: number; activity: string; start: string; end: string; minutes: number}[];
  checks: {id: number; name: string; done: boolean}[];
  parts: {id: number; name: string; quantity: number; state: string}[];
  photos: {id: number; name: string}[];
};
export type Dashboard = {user: User; jobs: Job[]; vehicles: Vehicle[]};
export type ApiCall = <T>(path: string, params?: object) => Promise<T>;
