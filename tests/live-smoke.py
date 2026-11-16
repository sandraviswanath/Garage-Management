"""Live authentication and cart-refresh checks against Odoo or Next.js forwarding."""
import http.cookiejar
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
ENV = dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
           if line.strip() and not line.lstrip().startswith('#'))
BASE = os.environ.get('WORKSHOP_API_URL', 'http://127.0.0.1:8070/workshop/rest').rstrip('/') + '/'


def client():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(opener, path, params=None, headers=None, expected=200):
    request = urllib.request.Request(BASE + path, json.dumps(params or {}).encode(),
        {'Content-Type': 'application/json', **(headers or {})})
    try:
        response = opener.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = json.load(response)
        assert response.status == expected, (path, response.status, body)
        return body


call(client(), 'dashboard', expected=401)
for login, secret, role in [
    ('admin', 'WORKSHOP_ADMIN_PASSWORD', 'admin'),
    (ENV['DEMO_CUSTOMER_EMAIL'], 'DEMO_CUSTOMER_PASSWORD', 'customer'),
    (ENV['DEMO_TECHNICIAN_EMAIL'], 'DEMO_TECHNICIAN_PASSWORD', 'technician'),
]:
    session = client()
    result = call(session, 'auth/login', {'login': login, 'password': ENV[secret]})
    assert result['user']['role'] == role, result
    if role == 'admin':
        for action, payload in [('dashboard', {}), ('lookups', {})] + [
            ('list', {'entity': entity}) for entity in [
                'customers', 'vehicles', 'jobs', 'estimates', 'inventory',
                'invoices', 'payments', 'users', 'transactions', 'purchases']
        ]:
            call(session, 'staff', {'action': action, 'payload': payload})
    else:
        dashboard = call(session, 'dashboard')
        assert dashboard['user']['role'] == role and isinstance(dashboard['jobs'], list)
        call(session, 'staff', {'action': 'list', 'payload': {'entity': 'users'}}, expected=403)
    call(session, 'dashboard', headers={'Origin': 'https://attacker.example'}, expected=403)
    call(session, 'auth/logout')
    call(session, 'dashboard', expected=401)
    print(f'PASS: {role} login, read access, origin protection and logout')

for prefix, role in [('DEMO_CUSTOMER', 'customer'), ('DEMO_TECHNICIAN', 'technician')]:
    native = client()
    result = call(native, 'mobile/login', {
        'login': ENV[prefix + '_EMAIL'], 'password': ENV[prefix + '_PASSWORD']})
    headers = {'Authorization': 'Bearer ' + result['session_id']}
    dashboard = call(native, 'dashboard', headers=headers)
    assert dashboard['user']['role'] == role
    if role == 'customer':
        for endpoint in ['shop/catalog', 'shop/cart', 'shop/orders']:
            call(native, endpoint, headers=headers)
        # A website and phone can refresh the same persistent cart together.
        # Each client needs its own HTTP opener, while sharing the Odoo session.
        with ThreadPoolExecutor(max_workers=4) as pool:
            carts = list(pool.map(lambda _: call(client(), 'shop/cart', headers=headers), range(8)))
        assert len({cart['id'] for cart in carts}) == 1
        print('PASS: simultaneous customer cart refreshes share one cart and recover from database conflicts')
    else:
        call(native, 'shop/cart', headers=headers, expected=403)
    call(native, 'parts', headers=headers, expected=200 if role == 'technician' else 403)
    call(native, 'staff', {'action': 'list', 'payload': {'entity': 'users'}}, headers=headers, expected=403)
    call(native, 'auth/logout', headers=headers)
    call(native, 'dashboard', headers=headers, expected=401)
    print(f'PASS: {role} native bearer session, scoped data, role restrictions and logout')
call(client(), 'mobile/login', {'login': 'admin', 'password': ENV['WORKSHOP_ADMIN_PASSWORD']}, expected=403)
print('PASS: administrator denied a native mobile session')
