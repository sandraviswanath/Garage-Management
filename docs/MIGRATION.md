# Migration from the uploaded workshop frontend

Version 1 of this generated package only added a customer portal/native app and
used Odoo's screens for staff work. **Version 2 adds the staff workflows in
Next.js**, corresponding to all 46 original page paths.

The interface has been reimplemented using shared responsive staff components;
it does not preserve the old theme pixel-for-pixel. Admin, receptionist, manager,
accountant and technician workflows use the same Odoo database and scoped API.
The original source remains under `reference/legacy-workshop-source.zip` for
comparison; those reference screens are not used to stand in for working features.

Read FEATURE_PARITY.md for each feature's actual destination. The mechanical
route/field/action inventory is original-route-audit.json.

## Main mappings

| Original REST feature | Odoo-backed implementation |
|---|---|
| customers | Tagged res.partner records and owned vehicle/history queries |
| vehicles | workshop.vehicle with original workshop metadata |
| jobcards | workshop.job plus task, note, photo and time records |
| work assignments | Job technician/state and real task progress |
| estimates | Linked sale.order records; main and additional-work quotations |
| inventory | product.product, stock.quant, stock.move and sales deliveries |
| invoices | Linked account.move invoices/credit notes |
| payments/history | account.payment, payment registration and reversal records |
| user management | Controlled res.users role groups and profile metadata |
| reports | Queries over jobs, work logs, ratings, invoices and payments |

The customer portal and native technician app remain in addition to these staff
screens. Staff go to /login; customers go to /. Setup/upgrade steps are in README.

## Existing data

The upload contains frontend code, not the external REST backend/database.
This package does not pretend to migrate external customer/stock/payment data.
A production data import would need real exports, identifiers, opening balances
and reconciliation. The included upgrade script only links records from version 1
of this generated Odoo project.

## Semantic changes

Records with history are archived, not destroyed. Posted invoices/payment
records use cancellation/credit-note controls. Paid/unpaid comes from balances.
Refunds are accounting recordings, not card-network transfers. Emails are queued.
Original sample widgets/arrays have been replaced with actual data sources; no
random/demo numbers are used by the application itself.

Live Odoo installation and browser/device acceptance are not yet verified in the
authoring environment. See TESTING.md for the exact checks that passed and those
that still need execution with Odoo.
