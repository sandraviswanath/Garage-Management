import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {mkdirSync, copyFileSync} from 'node:fs';

const root = fileURLToPath(new URL('../', import.meta.url));
const result = spawnSync(process.execPath, [
  root + 'node_modules/expo/bin/cli', 'export', '--platform', 'web',
  '--max-workers', '2',
  '--output-dir', '../portal/public/mobile-app',
], {
  cwd: root,
  env: {...process.env, EXPO_NO_TELEMETRY: '1', EXPO_OFFLINE: '1'},
  stdio: 'inherit',
});
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status || 1);
// Keep the original technician preview URL working for existing bookmarks.
mkdirSync(root + '../portal/public/technician-app', {recursive: true});
copyFileSync(root + '../portal/public/mobile-app/index.html', root + '../portal/public/technician-app/index.html');
console.log('Customer and technician app: http://localhost:3001/mobile-app/index.html');
