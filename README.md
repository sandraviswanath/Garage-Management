# Workshop Hub — complete workshop workflow, version 2

## Run on this machine

The project now has a private Odoo 18/PostgreSQL runtime without Docker.
Start all three applications from the project root:

```bash
python3 scripts/local_dev.py start --mobile
```

Staff: http://localhost:3001/login · Customer: http://localhost:3001 ·
Odoo: http://localhost:8070 · Expo: port 8081.
Login credentials are in the root `.env` file. See
[local development](docs/LOCAL_DEVELOPMENT.md) for stop/restart commands,
mobile connectivity, runtime installation and database integration tests.

This version adds the **staff-facing Next.js workshop application** that was
missing from the first package. It implements the workshop features identified
in your original upload, with Odoo as the backend, while retaining the customer
portal and Expo customer/technician app.

**Start staff work at http://localhost:3001/login with the local runtime**
(port 3000 with the Docker instructions below). Daily workshop operations
are now available in Next.js; you do not have to use Odoo's interface in place
of the admin, receptionist, manager, accountant, or technician screens.

The interface is a new responsive design following the original workshop flow.
It is not an exact copy of the original Bootstrap theme. The original code is
preserved under `reference/`; working features are implemented under
`apps/portal/components/staff/` and the custom Odoo addon, not just stored there
as reference. See **docs/FEATURE_PARITY.md** for the feature-by-feature map and
**docs/original-route-audit.json** for all 46 original screen paths.

## Parts shop and backend ownership

Customers can now buy parts through the Next.js website at
http://localhost:3001/shop or **Parts shop** in the customer mobile app.
Catalogue, persistent cart, Odoo-calculated prices/taxes, checkout, real stock
reservation, order history, cancellation and posted invoice access are implemented.
Checkout currently uses **pickup and payment at the workshop**.

**The backend and REST API are entirely in Odoo** at
`http://localhost:8070/workshop/rest/`. Next.js has no API route handlers;
its `/api/*` path is a forwarding configuration. Native apps call Odoo directly.
See [parts-shop setup, API and fulfilment](docs/PARTS_SHOP.md).

## Applications and entry points

| Application | Entry | Users |
|---|---|---|
| Next.js staff workspace | `/login` | Administrator, manager, receptionist, accountant, technician |
| Next.js customer portal | `/` | Customers |
| React Native / Expo | `apps/mobile` | Customers and technicians; workspace selected after login |
| Odoo 18 backend | localhost:8070 locally; 8069 with Docker | Initial accounting/warehouse setup and optional ERP administration |

## Included workshop features

- Separate role dashboards showing real job, customer, billing and work metrics.
- Customer creation/editing, optional vehicle entry, customer status, service
  history, financial summaries, and customer portal-account provisioning.
- Vehicles with owner, registration, type, make/model/year, VIN/chassis,
  engine number, odometer, status, and service history.
- Job-card creation/editing, job type, priority, expected completion,
  diagnosis, special instructions, technician assignment and lifecycle actions.
- Labour tasks, hours/rates, task status/notes, inspection checks and progress.
- Spare-part requests, manager issuance from the approved sales delivery,
  rejection and used/not-used tracking.
- Before/during/after/issue photos, photo descriptions, view/edit/delete,
  technician notes and persistent server-side start/stop work timers.
- Estimates with labour/part lines, quantity, price, percentage and order
  discounts, sales-tax selection, validity, notes, send/request approval,
  recorded customer approval, rejection, duplication, deletion and PDF output.
- Additional-work quotations for an active job, separately approved through
  the customer portal or recorded by management; approved extras are included
  in stock issuance and invoicing.
- Inventory records, SKU, category, supplier, cost/retail price, min/max levels,
  storage bin, add-stock adjustments, stock transactions and stock-level filters.
- Supplier purchase orders, confirmation and receipt, integrated with stock.
- Invoices from completed jobs, draft issue/due date and discount editing,
  posting, totals/balance/payment state, PDF, email and reminder actions.
- Partial payment recording, cash/bank/card/cheque metadata, transaction/reference
  details, receipt PDFs, cancellation of eligible erroneous recordings and
  partial/full recorded refunds with credit notes and outbound payment records.
- Staff users, passwords, roles, specialization, edit and archive.
- Job, technician-performance and revenue reports; date/status/type/technician,
  efficiency/quality/specialization and payment filters; Excel/PDF/print exports.
- Original workshop routes, searching, filters and pagination. Managers and
  accountants also have role-specific navigation to their relevant screens.

## Requirements

- Docker Engine/Desktop and Docker Compose v2.
- Node.js 22.13+ or Node 24 LTS, and npm.
- Expo Go compatible with SDK 58 or an Expo development build, for native use.
- Internet for first-time package and image downloads.

## Fresh setup with Docker

From this folder:

```bash
cp .env.example .env
```

Edit `.env`. Replace every example password with your own password of at least
12 characters. The setup script refuses unchanged placeholder passwords.

```bash
bash scripts/setup.sh
```

This initializes PostgreSQL, creates the `workshop` Odoo database, installs the
addon, sets the admin password, and seeds one customer, technician, vehicle and
quotation-ready job. It does not create artificial payments, stock quantities,
company tax rules or accounting configuration.

Before invoicing/payments, open http://localhost:8069 as `admin` with
`WORKSHOP_ADMIN_PASSWORD` and configure your company's currency, fiscal
localization/chart of accounts, journals, taxes and product accounts. Configure
cash/bank journals with suitable manual payment methods/outstanding accounts.
Configure outgoing email if you will send quotations, invoices or reminders.
These business settings are specific to your workshop and are not guessed.

Start the Next.js application:

```bash
cd apps/portal
cp .env.example .env.local
npm ci
npm run dev
```

- Staff login: **http://localhost:3000/login**.
- Initial administrator username: **admin**; password from root `.env`.
- Customer portal: **http://localhost:3000**; customer credentials from `.env`.
- From Admin → Staff users, create receptionist, manager and accountant accounts.
- From a customer's detail page, Admin/Manager can configure portal access using
  the customer's email and an initial password. Share credentials securely.

`ODOO_URL` in `apps/portal/.env.local` configures transport forwarding to Odoo.
The browser does not contain a shared Odoo administrator key or password.

## Upgrade from the first generated package

Back up your development database/filestore before upgrading. Replace the source
with this version, retain your private `.env` files and Docker volumes, then:

```bash
bash scripts/upgrade.sh
cd apps/portal
npm ci
npm run dev
```

The upgrade installs added fields/groups/models and backfills job-to-quotation
links from version 1. It does **not** import data from the original external REST
backend, because that database was not part of your uploaded frontend archive.
Do not rerun the sample-user seeder on a real business database.

## Customer and technician mobile app

To test the React Native application without Expo Go or an emulator, build its
browser preview and open http://localhost:3001/mobile-app/index.html:

```bash
python3 scripts/local_dev.py start
npm --prefix apps/mobile run web
```

Use the customer or technician credentials from `.env`. This renders the same app with React
Native Web and uses the existing Next.js/Odoo API. Re-run the web command after
editing mobile source. Camera/device security behaviour still needs native testing.

```bash
cd apps/mobile
cp .env.example .env
npm ci
npx expo start
```

Set `EXPO_PUBLIC_API_URL` to the Odoo server (local port 8070, Docker port 8069):

| Device | URL example |
|---|---|
| Android emulator | `http://10.0.2.2:8070` |
| iOS simulator on the same Mac | `http://localhost:8070` |
| Physical phone on the same Wi-Fi | `http://YOUR_COMPUTER_LAN_IP:8070` |
| Hosted build | Your HTTPS portal domain |

Restart Expo after changing its environment file. Sign in with the seeded
customer or technician credentials. Native sessions use Expo SecureStore.
Customer accounts open their own workspace with vehicles, service booking,
repair progress, initial/additional quotation approval, repair photos, posted
invoices and recorded payment status. Invoice PDFs can be downloaded in the
browser or shared/saved through the device's share sheet. Online payment
collection is not included. Technician accounts retain assigned jobs,
task/check completion, status, parts requests, photos, notes and timers.
Android/iOS are targeted; a browser preview is also available as described above.
The original `/technician-app/index.html` preview URL remains an alias.

For an APK, configure your own Expo/EAS account and app identifiers, then use
`eas build --platform android --profile preview`. No signed APK is included.

## Complete workshop demonstration

1. Reception: add the customer and vehicle, then create a job card and assign a
   technician. Record concerns, priority and expected completion.
2. Open the job: add labour tasks and expected spare parts.
3. Prepare the estimate: review prices, taxes, discounts, notes and validity.
4. Request customer approval. The customer approves in the portal, or a manager
   records how approval was received. No approval is silently fabricated.
5. Technician: start work, run the timer, update tasks/checks, add notes and
   before/during/after photos. Pause/resume as needed.
6. Receive purchased stock if needed. Management issues the linked quoted sales
   delivery once; the technician marks issued parts used.
7. If extra work is discovered, prepare an additional estimate on the active job,
   request approval and issue any additional approved parts. Existing approved
   prices are not silently rewritten.
8. Complete the checks and labour tasks. Resolve pending quotes and parts, then
   complete the job. Active timers stop and completion time is recorded.
9. Accounts: create the invoice, review dates/discount, post it and record partial
   or full payments. Print/download the invoice and receipts.
10. Customer: see repair progress, photos, posted invoices and payment status.
11. Management: filter/export job, technician and revenue reports.

## Deliberate business controls

- Deleting customers, vehicles, staff users or closed jobs archives them, retaining
  history. Draft quotations can be deleted. Posted financial records are not
  erased with a generic delete button.
- Paid/unpaid is derived from real invoice/payment balances; it is not a cosmetic
  checkbox. Eligible erroneous payments can be cancelled; matched payments need
  accountant review. Refunds create accounting records and do not transfer money
  through a card processor. Stock returns are a separate operation.
- Emails are queued in Odoo. Delivery requires a working outgoing mail server.
- Add stock is an inventory adjustment; supplier purchases/receipts have their
  own workflow. Tracked lots/serials require Odoo receipt review.
- Parts must be approved on a quotation before their sales delivery is issued.
  The issue action validates the whole linked delivery, including its other
  reserved products. It does not create a duplicate stock deduction.
- The interface reports actual Odoo states; original mock statuses have been
  mapped to real job, quotation and accounting states.

## Validation and limits

See **docs/TESTING.md**. The Next.js production build, both TypeScript checks,
Expo Android bundle, standalone tests and HTTP/route checks passed. The route
checks cover all 46 original paths but are not proof of browser interaction or
Odoo database behavior.

**Live local validation is now complete for the core repair workflow**: the addon
installs on Odoo 18 with PostgreSQL 16, and all 26 database integration tests pass,
including customer approval, technician completion, role isolation, timers and
stock issuance without double deduction. Real staff/customer/native login and
staff list/lookup/dashboard requests pass through Next.js transport forwarding to Odoo. Browser
sign-in, dashboard, job list and job detail were verified against real Odoo.
The production build and Android bundle pass. Company-specific accounting,
PDF/email delivery and physical-device camera/SecureStore behavior still require
the included acceptance checks. No native device was available.

Target backend: **Odoo 18**. Do not install this addon unchanged on Odoo 19/20.
List pages paginate at 50 records; lookup pickers currently cap at 1,000 records
and customer/native summaries at 100 jobs. Add lookup pagination for larger
workshops. No online card charging, public registration/password reset, push
notifications, offline sync or automatic historical-data import is included;
these were not implemented workshop features in the original frontend.

## Source layout

```text
apps/portal/app/                         Customer portal and staff frontend routes
apps/portal/components/staff/            Connected staff screens and shared forms
apps/mobile/                            Expo customer and technician app
odoo/addons/workshop_hub/                Odoo models, controllers, ACL/rules and tests
scripts/                                Fresh setup, upgrade and development seeding
tests/                                  Standalone policy and HTTP/route checks
docs/FEATURE_PARITY.md                   Original features → implemented screens/actions
docs/original-route-audit.json           Inventory of all 46 original screen paths
reference/legacy-workshop-source.zip     Original code reference, excluding media/build files
```

The original full upload remains separate. The reference ZIP excludes public
media and generated/dependency directories and is not a standalone runnable
copy of the original theme.

Custom project code is MIT licensed; the Odoo addon declares LGPL-3. Third-party
and original uploaded reference code retain their own licenses.
