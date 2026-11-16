# Local development without Docker (Linux)

The working local runtime lives in `.runtime/`, including Odoo **18**, its own
Python virtual environment, PostgreSQL cluster, filestore, logs and Android
bundle. It does not use or modify the machine's Odoo 19 installation or the
system PostgreSQL cluster. PostgreSQL uses port **5433**.

From the project root:

```bash
python3 scripts/local_dev.py start --mobile
python3 scripts/local_dev.py status
python3 scripts/local_dev.py stop
```

Open staff access at http://localhost:3001/login, customer access at
http://localhost:3001 and Odoo at http://localhost:8070.

Passwords were generated during setup and are stored in the private root
`.env` file. Use `admin` with `WORKSHOP_ADMIN_PASSWORD`,
`DEMO_CUSTOMER_EMAIL` with `DEMO_CUSTOMER_PASSWORD`, or
`DEMO_TECHNICIAN_EMAIL` with `DEMO_TECHNICIAN_PASSWORD`. Keep this file private.

Expo serves the native application on port **8081**. Open a terminal in
`apps/mobile` and run `npm start` instead if you want Expo's interactive QR code
and emulator shortcuts (stop the managed Expo process first). Set
`EXPO_PUBLIC_API_URL` in `apps/mobile/.env` to the Odoo server's reachable address for a
physical phone; `http://10.0.2.2:8070` is the Android emulator default. The phone
and computer must share a network. Restart Expo after changing this setting.
An Android or iOS device/emulator is required to exercise native camera and
SecureStore behavior. The bundle in `.runtime/android-export` is not an APK.

Logs: `.runtime/logs/odoo.log`, `portal.log`, `expo.log`, `postgres.log`.
To follow them: `tail -f .runtime/logs/odoo.log .runtime/logs/portal.log`.

## Test the customer and technician app without a phone

```bash
python3 scripts/local_dev.py start
npm --prefix apps/mobile run web
```

Open http://localhost:3001/mobile-app/index.html and use the customer or technician
credentials from `.env`. The appropriate workspace opens after login. The old
`/technician-app/index.html` URL continues to work. This is the React Native app rendered with React Native Web. The
browser uses the portal's HttpOnly session cookie, while native builds continue
to store their token in SecureStore. The browser storage contains only a sign-in
marker. Sign-in shares the website's browser session, so use a private window if
you want to keep a customer, technician or administrator signed in separately.

Customers can add vehicles, request a service date, track their jobs, approve
initial/additional estimates, inspect photos and view posted invoices/payment
status. A customer cannot edit technician work or see other customers' records.
Reception provisions customer accounts; public registration is not included.

Technicians can test assigned jobs, refresh, checklists, tasks, progress, timers,
notes, image selection and part requests on an approved job. Use browser developer tools
to view a phone-sized viewport. This validates the shared app UI and backend
workflow; it does not validate Android/iOS permissions, SecureStore or native
camera behaviour. The preview does not require Metro to run. Rebuild with the
same npm command after editing app source, then refresh the browser.

## Re-create the runtime on another Linux machine

Install Node.js 22.13+ or 24, Python 3.12 with venv/dev headers, PostgreSQL 16
with development headers, C compiler, LDAP/SASL development libraries and
wkhtmltopdf (for Odoo PDF reports). Then, from the project root:

```bash
mkdir -p .runtime/odoo18
curl -fL https://codeload.github.com/odoo/odoo/tar.gz/refs/heads/18.0 -o /tmp/workshop-odoo18.tar.gz
tar -xzf /tmp/workshop-odoo18.tar.gz -C .runtime/odoo18 --strip-components=1
python3 -m venv .runtime/venv
.runtime/venv/bin/pip install -r .runtime/odoo18/requirements.txt
npm --prefix apps/portal ci
npm --prefix apps/mobile ci
python3 scripts/local_dev.py setup
python3 scripts/local_dev.py start --mobile
```

Setup creates configuration only when absent. The demo seeder runs once per
runtime; restarting services never resets passwords or job data. Stop the local
stack before running setup or tests. The development cluster trusts local Unix
socket connections and requires password authentication for TCP connections;
it is intended for a single-user development machine.

## Checks

```bash
python3 -m unittest discover -s tests -v
npm --prefix apps/portal test
npm --prefix apps/portal run typecheck
npm --prefix apps/portal run build
npm --prefix apps/mobile run typecheck
# Against the running real backend (read-only; credentials from .env):
python3 tests/live-smoke.py
# From apps/mobile:
EXPO_NO_TELEMETRY=1 EXPO_OFFLINE=1 npx expo export --platform android --output-dir ../../.runtime/android-export
```

Run database integration tests in the separate `workshop_test` database:

```bash
python3 scripts/local_dev.py stop
python3 scripts/local_dev.py test
python3 scripts/local_dev.py start --mobile
```

The local runtime uses ports 3001/8070 to avoid the existing applications on
3000/8069. The original Docker deployment remains available through `docker-compose.yml`.
Before real invoicing, configure your company currency, chart of accounts,
taxes, bank/cash journals and outgoing email in Odoo. Those business settings
must match your workshop; local setup does not invent them.

## Parts shopping and Odoo-owned API

The customer website includes http://localhost:3001/shop, and the mobile customer
workspace includes **Parts shop**. All API handling and shop business rules live
in Odoo. Next.js forwards `/api/*` to `/workshop/rest/*`; native clients address
Odoo directly on port 8070. See [shop setup and API](PARTS_SHOP.md).

When upgrading this version, stop the stack, run `python3 scripts/local_dev.py upgrade`,
then start it and rebuild the browser preview. Configure the exact frontend
origin in Odoo's `WORKSHOP_ALLOWED_ORIGINS` for hosts beyond local development.
