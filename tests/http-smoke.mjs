// Read-only checks through Next.js transport against real Odoo.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const portal=process.env.SMOKE_BASE_URL||'http://127.0.0.1:3100';
const env=Object.fromEntries((await fs.readFile(new URL('../.env',import.meta.url),'utf8')).split('\n').filter(line=>line&&!line.startsWith('#')).map(line=>{const i=line.indexOf('=');return [line.slice(0,i),line.slice(i+1)];}));
const post=(path,params={},cookie='',headers={})=>fetch(portal+'/api/'+path,{method:'POST',headers:{'Content-Type':'application/json',...(cookie?{Cookie:cookie}:{}),...headers},body:JSON.stringify(params)});
assert.equal((await post('dashboard')).status,401);
assert.equal((await post('auth/login',{login:env.DEMO_CUSTOMER_EMAIL,password:'incorrect-password'})).status,401);
let response=await post('auth/login',{login:env.DEMO_CUSTOMER_EMAIL,password:env.DEMO_CUSTOMER_PASSWORD});
assert.equal(response.status,200);const cookie=response.headers.get('set-cookie').split(';')[0];
assert.match(cookie,/workshop_session=/);assert.match(response.headers.get('set-cookie'),/HttpOnly/);
for(const path of ['dashboard','shop/catalog','shop/cart','shop/orders'])assert.equal((await post(path,{},cookie)).status,200,path);
assert.equal((await post('shop/cart',{},cookie,{Origin:'https://attacker.example'})).status,403);
assert.equal((await post('res.users/write',{},cookie)).status,404);
assert.equal((await post('staff',{action:'list',payload:{entity:'users'}},cookie)).status,403);
response=await post('auth/logout',{},cookie);assert.equal(response.status,200);assert.match(response.headers.get('set-cookie'),/Max-Age=0/);
assert.equal((await post('dashboard',{},cookie)).status,401);
response=await post('mobile/login',{login:env.DEMO_CUSTOMER_EMAIL,password:env.DEMO_CUSTOMER_PASSWORD});assert.equal(response.status,200);
const native=await response.json();assert.equal(native.user.role,'customer');
assert.equal((await post('shop/catalog',{},'',{Authorization:`Bearer ${native.session_id}`})).status,200);
await post('auth/logout',{},'',{Authorization:`Bearer ${native.session_id}`});
const routes=JSON.parse(await fs.readFile(new URL('../docs/original-route-audit.json',import.meta.url),'utf8'));
for(const item of [...routes,{route:'/shop'},{route:'/'}]){const route=item.route.replace('/.','/').replaceAll('[id]','1');const page=await fetch(portal+route+(route.endsWith('addservice')?'?id=1':''));assert.equal(page.status,200,route);}
console.log('PASS: real Odoo authentication, shopping API, permissions, logout and 48 website routes through Next.js transport.');
