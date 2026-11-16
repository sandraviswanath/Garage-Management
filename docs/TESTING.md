# Validation and test commands

## Current architecture and verification

Odoo 18 owns the REST API at http://localhost:8070/workshop/rest/. Next.js on
port 3001 is the frontend and HTTP forwarding layer. The former Next.js API
route and mock backend have been removed. React Native calls Odoo directly;
its browser preview uses the website forwarding rule.

- **26 Odoo integration tests pass** against the isolated `workshop_test` database.
- The suite covers customer/technician permissions, ownership, bookings, estimates,
  additional-work approval, repair completion, timers, stock issuance and the shop.
- Shop checks include Odoo cookie/native bearer login, session expiry/logout,
  origin checks, private products, persistent customer carts, server pricing,
  invalid quantities, stale-price review, insufficient stock, idempotent checkout,
  cancellation and stock reservation release.
- Direct Odoo live checks pass for staff/customer/technician login and role access.
- The real-API website smoke suite passes authentication, shop endpoints, origin
  rejection, session logout and 48 original/new customer/staff page requests.
- Both TypeScript checks, Next.js production build, React Native browser preview
  and Android Hermes bundle export pass. The Next.js build contains no API route.
- 21 standalone Python policy/input tests and frontend architecture tests pass.

## Run checks

```bash
python3 -m unittest discover -s tests -v
npm --prefix apps/portal test
npm --prefix apps/portal run build
npm --prefix apps/mobile run typecheck
npm --prefix apps/mobile run web
python3 scripts/local_dev.py test
```

Native bundling, from `apps/mobile`:

```bash
EXPO_NO_TELEMETRY=1 EXPO_OFFLINE=1 npx expo export --platform android --max-workers 2 --output-dir ../../.runtime/android-export
```

The local stack must be running for live checks:

```bash
python3 scripts/local_dev.py start
python3 tests/live-smoke.py
WORKSHOP_API_URL=http://127.0.0.1:3001/api python3 tests/live-smoke.py
node tests/run-smoke.mjs
```

The first live check calls Odoo directly; the second verifies the forwarding
path. The runner starts a separate production frontend on port 3100 while using
the real Odoo backend. Set `SMOKE_PORT` to override that frontend test port.
Database tests use a separate database and port 8071. They can run without
changing the demonstration customer's orders or stock.

## Manual acceptance

Use the customer website at http://localhost:3001/shop and **Parts shop** in
http://localhost:3001/mobile-app/index.html. Check search/category filters,
quantities, totals, pickup details, order history and eligibility to cancel.
A single labelled development product is available; no online payment is taken.
Verify the shared cart in the website and mobile app under the same account.
Configure published real products, warehouse stock, currency, taxes and pricelists
in Odoo before using the shop outside the local demonstration.

Company accounting, actual posted invoices/payments/refunds, PDF/email delivery,
physical-device camera/SecureStore/PDF sharing, production TLS, concurrency under
load and multi-company deployment require acceptance testing in their intended
environment. Android export is a JavaScript bundle, not a signed APK/device test.
The default shopping fulfilment is pickup and payment at the workshop. No courier
integration or online card payment provider has been configured.
