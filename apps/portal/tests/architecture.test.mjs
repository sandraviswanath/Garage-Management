import test from 'node:test';
import assert from 'node:assert/strict';
import {access,readFile} from 'node:fs/promises';
import config from '../next.config.mjs';
test('Next.js forwards transport to the Odoo REST backend',async()=>{
  const routes=await config.rewrites();assert.equal(routes[0].source,'/api/:path*');
  assert.ok(routes[0].destination.endsWith('/workshop/rest/:path*'));
});
test('the former Next.js API server is removed',async()=>{
  await assert.rejects(access(new URL('../app/api/[...path]/route.ts',import.meta.url)),{code:'ENOENT'});
  await assert.rejects(access(new URL('../lib/gateway.mjs',import.meta.url)),{code:'ENOENT'});
});
test('native clients address Odoo directly',async()=>{
  const source=await readFile(new URL('../../mobile/App.tsx',import.meta.url),'utf8');
  assert.ok(source.includes("'/workshop/rest/'"));
});
