import {spawn} from 'node:child_process';
import {setTimeout} from 'node:timers/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const port=process.env.SMOKE_PORT||'3100';
const base=`http://127.0.0.1:${port}`;
const next=spawn(process.execPath,['node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',port],{cwd:root+'apps/portal',env:process.env,stdio:'inherit'});
try{
 let ready=false;
 for(let attempt=0;attempt<80;attempt++){
   if(next.exitCode!==null)throw new Error('A smoke-test server exited before becoming ready. Check that the test ports are free.');
   try{if((await fetch(base)).ok){ready=true;break;}}catch{}
   await setTimeout(500);
 }
 if(!ready)throw new Error('Next.js did not start.');
 const script='tests/http-smoke.mjs';
 const child=spawn(process.execPath,[script],{cwd:root,stdio:'inherit',env:{...process.env,SMOKE_BASE_URL:base}});
 const code=await new Promise(resolve=>child.on('exit',resolve));
 if(code!==0)process.exitCode=1;
}finally{next.kill('SIGTERM');}
