#!/usr/bin/env python3
"""Run a private Linux development stack without Docker or system services."""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
LOGS = RUNTIME / 'logs'
CONFIG = RUNTIME / 'odoo.conf'
PYTHON = RUNTIME / 'venv/bin/python'
ODOO = RUNTIME / 'odoo18/odoo-bin'
STATE = RUNTIME / 'services.json'


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], cwd=ROOT, check=True, **kwargs)


def environment():
    env = os.environ.copy()
    for line in (ROOT / '.env').read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            env[key] = value.strip()
    return env


def configure():
    LOGS.mkdir(parents=True, exist_ok=True)
    path = ROOT / '.env'
    if not path.exists():
        values = {'POSTGRES_PASSWORD': secrets.token_urlsafe(24),
                  'WORKSHOP_ADMIN_PASSWORD': secrets.token_urlsafe(18),
                  'DEMO_CUSTOMER_EMAIL': 'customer@example.com',
                  'DEMO_CUSTOMER_PASSWORD': secrets.token_urlsafe(18),
                  'DEMO_TECHNICIAN_EMAIL': 'technician@example.com',
                  'DEMO_TECHNICIAN_PASSWORD': secrets.token_urlsafe(18)}
        path.write_text(''.join(f'{key}={value}\n' for key, value in values.items()))
        path.chmod(0o600)
    if not CONFIG.exists():
        CONFIG.write_text(
            f'[options]\naddons_path = {RUNTIME}/odoo18/addons,{ROOT}/odoo/addons\n'
            f'data_dir = {RUNTIME}/odoo-data\ndb_host = /tmp\ndb_port = 5433\n'
            f'db_user = {getpass.getuser()}\ndb_name = workshop\ndbfilter = ^workshop$\n'
            'list_db = False\nhttp_interface = 127.0.0.1\nhttp_port = 8070\n'
            f'max_cron_threads = 0\nlimit_time_real = 300\nadmin_passwd = {secrets.token_urlsafe(32)}\n')
        CONFIG.chmod(0o600)
    for relative, content in {
        'apps/portal/.env.local': 'ODOO_URL=http://127.0.0.1:8070\nODOO_DB=workshop\n',
        'apps/mobile/.env': 'EXPO_PUBLIC_API_URL=http://10.0.2.2:8070\n',
    }.items():
        target = ROOT / relative
        if not target.exists():
            target.write_text(content)


def postgres(start=True):
    bindir = Path(subprocess.check_output(['pg_config', '--bindir'], text=True).strip())
    cluster = RUNTIME / 'postgres'
    if start:
        if not (cluster / 'PG_VERSION').exists():
            run([bindir / 'initdb', '-D', cluster, '--auth-local=trust',
                 '--auth-host=scram-sha-256', f'--username={getpass.getuser()}',
                 '--encoding=UTF8', '--locale=C.UTF-8'])
        status = subprocess.run([bindir / 'pg_ctl', '-D', cluster, 'status'], capture_output=True)
        if status.returncode:
            run([bindir / 'pg_ctl', '-D', cluster, '-l', LOGS / 'postgres.log',
                 '-o', '-h 127.0.0.1 -p 5433 -k /tmp', 'start'])
    elif (cluster / 'postmaster.pid').exists():
        run([bindir / 'pg_ctl', '-D', cluster, '-m', 'fast', 'stop'])


def wait_http(url, process):
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError(f'Service exited with {process.returncode}; see {LOGS}.')
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    time.sleep(0.3)
                    if process.poll() is not None:
                        raise RuntimeError('Service exited during startup; inspect its log.')
                    return
        except (OSError, TimeoutError):
            pass
        time.sleep(1)
    raise RuntimeError(f'Timed out waiting for {url}; see {LOGS}.')


def process_identity(pid):
    return Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()[19]


def owned_process(info):
    try:
        return info['identity'] == process_identity(info['pid'])
    except (OSError, KeyError):
        return False


def state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def launch(name, args, cwd, env, url):
    services = state()
    if name in services and owned_process(services[name]):
        print(f'{name} already running (PID {services[name]["pid"]}).')
        return
    # Refuse occupied ports rather than accidentally accepting another app's health response.
    from urllib.parse import urlparse
    port = urlparse(url).port
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(('0.0.0.0', port))
    with (LOGS / f'{name}.log').open('a') as log:
        process = subprocess.Popen([str(arg) for arg in args], cwd=cwd, env=env,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   start_new_session=True)
    services[name] = {'pid': process.pid, 'identity': process_identity(process.pid)}
    STATE.write_text(json.dumps(services, indent=2))
    wait_http(url, process)
    print(f'{name}: {url}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['setup', 'upgrade', 'start', 'stop', 'status', 'test'])
    parser.add_argument('--mobile', action='store_true', help='Also start Expo on port 8081.')
    args = parser.parse_args()
    configure()
    if args.command == 'status':
        for name, info in state().items():
            print(f'{name}: {"running" if owned_process(info) else "stopped"} (PID {info["pid"]})')
        return
    if args.command == 'stop':
        for name, info in reversed(list(state().items())):
            if owned_process(info):
                os.killpg(info['pid'], signal.SIGTERM)
                print(f'Stopped {name}.')
        time.sleep(2)
        postgres(False)
        STATE.write_text('{}\n')
        return
    if not ODOO.exists() or not PYTHON.exists():
        raise RuntimeError('Install the local Odoo 18 runtime first; see docs/LOCAL_DEVELOPMENT.md.')
    env = environment()
    postgres()
    odoo = [PYTHON, ODOO, '-c', CONFIG]
    if args.command == 'upgrade':
        if any(owned_process(info) for info in state().values()):
            raise RuntimeError('Stop the local stack before upgrading the Odoo addon.')
        run(odoo + ['-u', 'workshop_hub', '--no-http', '--stop-after-init'], env=env)
        print('Odoo addon upgraded. Start the stack with: python3 scripts/local_dev.py start')
    elif args.command == 'setup':
        if any(owned_process(info) for info in state().values()):
            raise RuntimeError('Stop the local stack before running setup.')
        run(odoo + ['-i', 'workshop_hub', '--without-demo=all', '--stop-after-init'], env=env)
        marker = RUNTIME / 'seeded'
        if not marker.exists():
            with (ROOT / 'scripts/seed_demo.py').open() as seed:
                run([PYTHON, ODOO, 'shell', '-c', CONFIG, '--no-http'], env=env, stdin=seed)
            marker.touch()
        print('Setup complete. Credentials are in .env. Run: python3 scripts/local_dev.py start --mobile')
    elif args.command == 'test':
        run(odoo + ['-d', 'workshop_test', '--db-filter=^workshop_test$', '-i', 'workshop_hub',
                    '--http-port=8071',
                    '--without-demo=all', '--test-enable', '--test-tags=/workshop_hub',
                    '--stop-after-init'], env=env)
    else:
        launch('odoo', odoo, ROOT, env, 'http://127.0.0.1:8070/web/login')
        node = shutil.which('node')
        launch('portal', [node, ROOT / 'apps/portal/node_modules/next/dist/bin/next',
                          'dev', '--hostname', '0.0.0.0', '--port', '3001'],
               ROOT / 'apps/portal', env, 'http://localhost:3001/login')
        if args.mobile:
            env.update(EXPO_NO_TELEMETRY='1', EXPO_OFFLINE='1', CI='1')
            launch('expo', [node, ROOT / 'apps/mobile/node_modules/expo/bin/cli',
                            'start', '--lan', '--port', '8081'],
                   ROOT / 'apps/mobile', env, 'http://localhost:8081/status')


if __name__ == '__main__':
    main()
