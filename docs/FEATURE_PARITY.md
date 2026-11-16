# Original workshop feature map — version 2

This is an **implementation map**, not a claim that real Odoo or browser/device
acceptance has passed. Source for the original 46 pages was inspected. Features
below are implemented in the new Next.js staff workspace and scoped Odoo API.
The original theme's unrelated reusable demo widgets are not business features.

| Original workshop feature | New Next.js location | Backend / behavior |
|---|---|---|
| Staff login and role routing | `/login` | Own Odoo session; admin/manager/receptionist/accountant/technician |
| Admin dashboard | `/admin` | Job/customer/invoice/receipt metrics, status chart, recent jobs |
| Receptionist dashboard | `/receptionist` | Live company workshop overview and intake navigation |
| Manager dashboard | `/manager` | Live metrics and full operational navigation |
| Accountant dashboard | `/accountant` | Invoice/payment/report navigation and metrics |
| Technician dashboard | `/technician` | Assigned jobs only |
| Customer list/search/status/pagination | `/admin/customer` and reception equivalent | Tagged customer contacts and live job counts |
| Create customer + optional vehicle | `/admin/customer/add` | Contact and vehicle records in one request |
| Edit customer | Customer detail → Edit | Name/email/phone/address/tax number/status |
| Customer detail and service history | `/admin/customer/[id]` | Owned vehicles, service history, spending/open-job metrics |
| Delete customer | Customer detail → Archive | Preserves linked service/accounting history |
| Vehicle list/search/status | `/admin/vehicles` | Registration/model/owner/status search/filter |
| Add/edit vehicle | `/admin/vehicles/add`, detail → Edit | Owner/type/make/model/year/VIN/engine/KM/status |
| Vehicle service history | `/admin/vehicles/[id]` | Linked job cards |
| Delete vehicle | Vehicle detail → Archive | Preserves job links |
| Job-card list, status and type filters | `/admin/jobcards`, reception equivalent | Search registration/customer/job; status/type/technician filters |
| Job creation/editing | `/admin/jobcards/create` and reception equivalent | Customer-owned vehicle, issue, type, priority, instructions, expected date |
| Technician assignment | Job detail → Edit / assign | Valid workshop technician in the job company |
| Job status lifecycle | Job detail → actions | Approved/assigned/start/pause/wait/resume/complete/cancel |
| Job diagnosis and instructions | Job detail → Overview / Edit | Stored fields, not local-only state |
| Labour items and estimated costs | Job detail → Tasks | Description, hours, hourly rate, subtotal |
| Add service / remove labour or parts | `/admin/jobcards/addservice?id=...` | Tasks tab; request/reject parts; revise an unapproved estimate |
| Task status and notes | Job detail → Tasks | Pending/in-progress/completed plus per-task notes |
| Work assignment list | `/admin/work` | Job status/technician filtering and progress |
| Create work assignment | `/admin/work/create` | Creates an actual job/assignment rather than a disconnected mock |
| Work detail | `/admin/work/[id]` | Same connected job/tasks/parts/billing workflow |
| Technician assigned jobs and filters | `/technician/jobs` | Server-enforced assignment scope |
| Technician quick actions | Assigned job detail | Start/pause/resume/complete actions |
| Repair photos | Job detail → Photos | Actual private image uploads and viewing |
| Photo type, description, edit and delete | Job detail → Photos | Before/during/after/issue metadata, persisted changes |
| Technician notes | Job detail → Notes | Progress/issue/resolution, author/time retained |
| Work timers | Job detail → Time | Persisted start/stop, activity and server-calculated duration |
| Parts used toggle | Job detail → Parts | Available after inventory issue, persisted used/not-used state |
| Estimate list/search/status | `/admin/estimates` | Actual Odoo quotations |
| Estimate create with job/parts/labour | `/admin/estimates/create` | Editable lines, quantity/hour, price, discounts and configured taxes |
| Estimate validity and customer notes | Estimate editor | Date and note stored on sales order |
| Send estimate / request approval | Estimate detail | Portal approval state; optional queued email |
| Approve/reject estimate | Estimate detail | Management records approval evidence, or customer approves directly |
| Duplicate estimate | Estimate detail → Duplicate | Copy to a selected open job |
| Delete estimate | Estimate detail → Delete | Draft/cancelled estimates only |
| Estimate PDF/print | Estimate detail | Odoo quotation PDF / browser print |
| Inventory list and metrics | `/admin/inventory` | Actual available quantity/cost/value/low-stock metrics |
| Category and stock-level filters | Inventory list | In-stock / low-stock / out-of-stock, category and search |
| Part creation/edit | Inventory add/detail | SKU, description, category, supplier, cost/retail, min/max, bin |
| Add stock | Inventory detail → Add stock | Audited Odoo inventory adjustment |
| Stock transactions | `/admin/inventory/transactions` | Actual completed stock moves with from/to/reference/date |
| Remove part | Inventory detail → Archive | Product history retained |
| Invoice list and status | `/admin/invoices` | Actual invoice state, balance, payment status, overdue filter |
| Invoice from completed job | `/admin/invoices/create` | Approved quoted labour/parts and any approved additional orders |
| Invoice issue/due dates and discount | Draft invoice → Edit | Persisted dates and controlled discount line |
| Invoice taxes/totals | Quote → invoice | Odoo configured sales taxes and line discounts; no invented tax amount |
| Invoice PDF and print | Invoice detail | Odoo report PDF and print layout |
| Invoice email and reminders | Invoice detail | Queued Odoo email; outgoing server required |
| Delete invoice | Draft invoice → Cancel | Posted invoices retained; use credit-note/refund workflow |
| Paid/unpaid indicators | Job and invoice detail | Derived from accounting balances, not a fake checkbox |
| Invoice payment history | `/admin/payments/[invoice_id]` | Linked recorded payments and remaining balance |
| Add partial/full payment | Payment detail or `/admin/payments/add` | Odoo payment registration and reconciliation |
| Payment method/date/reference metadata | Payment form | Cash/bank/card/cheque/other, reference, transaction, last4, bank, notes |
| Payment list filters | `/admin/payments` | Status, method, date, search and pagination |
| Print receipt | Payment list/detail | Odoo payment-receipt PDF |
| Delete erroneous payment | Payment detail → Cancel recording | Eligible unbank-matched entries only; audit preserved |
| Refund | Payment list → Record refund | Partial/full credit note and outbound payment recording |
| Staff list/add/edit/detail/delete | `/admin/user` | Controlled roles/password/specialization and archive |
| Job report | `/admin/reports/jobs` | Date/status/technician/service-type filters and live job rows |
| Technician report | `/admin/reports/technician` | Completion/time/efficiency/rating/revenue, specialization filters |
| Revenue report | `/admin/reports/revenue` | Posted invoice/credit totals, receivables, recorded receipts, filters |
| Excel/PDF report exports | Report pages | Full filtered report rows; list-page exports export the displayed page |
| Pagination and search | Staff list pages | 50 rows/page, server-scoped data |

## Added alongside the original workshop flow

- Customer portal: own vehicles, service requests, quote/additional-work approval,
  repair progress, photos and posted invoice downloads.
- Customer/technician React Native app with service booking, estimates, repair tracking and parts shopping.
- Customer parts catalogue, persistent cart, pickup checkout, stock reservation, order history and cancellation through Odoo REST APIs.
- Purchase orders and goods receipts accessible from Next.js.
- Management can provision/reset a customer's portal account in Next.js.
- Separate customer approval for additional work rather than silently adding
  charges to an already-approved estimate.

## Behavioral changes that preserve real accounting/history

Archive replaces destructive delete for master records. A paid flag cannot be
changed independently of payment records. Refunds record credit notes/payments;
they do not call a card network. Stock issue uses existing sales deliveries.
Emails are queued, and cannot be reported as delivered without mail setup.

The original manager/accountant dashboards and several estimate/reception/
technician screens used theme widgets or hardcoded/local-only data. This version
provides actual model/controller implementations instead of retaining the mock
data and calling those workflows complete. Core Odoo workflow and shop integration checks now pass; see docs/TESTING.md for the remaining environment-specific acceptance work.
