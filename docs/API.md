# API contract

## Odoo REST API (local port 8070)

All backend and API handling is implemented in Odoo under `/workshop/rest/<endpoint>`.
Send JSON POST requests; responses are ordinary JSON rather than JSON-RPC envelopes.
Failures return `{ "error": "message" }` with the appropriate HTTP status.
The Next.js website forwards `/api/<endpoint>` to this Odoo URL through a transport-only
rewrite. Its previous API route handler has been removed. Native mobile clients call
Odoo directly. Odoo authenticates users and issues browser cookies/native bearer sessions.
See [parts-shop API and setup](PARTS_SHOP.md) for the catalogue/cart/order endpoints.

| Endpoint | Parameters | Role / result |
|---|---|---|
| `auth/login` | `login`, `password` | Own Odoo credentials; HttpOnly cookie |
| `mobile/login` | `login`, `password` | Customer or technician; `{user, session_id}` |
| `auth/logout` | none | Revokes session where possible; clears web cookie |
| `me` | none | `{uid, name, role}` |
| `dashboard` | none | `{user, jobs, vehicles}` scoped to caller |
| `vehicle` | `plate`, `make_model` | Customer; creates owned vehicle |
| `request` | `vehicle_id`, `concern`, `appointment_date` | Customer; creates job and CRM opportunity |
| `job` | `job_id` | Visible job details |
| `approve` | `job_id`, `version` | Customer; confirms current linked quotation |
| `status` | `job_id`, `state`, optional `note` | Assigned technician |
| `check` | `job_id`, `check_id`, boolean `done` | Assigned technician |
| `photo` | `job_id`, base64 `image`, `name` | Assigned technician; JPEG/PNG, max 5 MB |
| `photo-get` | `job_id`, `photo_id` | Visible job; `{image,mimetype}` |
| `parts` | none | Technician; `[{id,name}]` |
| `part-request` | `job_id`, `product_id`, `quantity`, optional `note` | Assigned technician |
| `invoice` | `job_id`, `invoice_id` | Customer; posted invoice `{content,name}` as base64 PDF |

Native requests include `Authorization: Bearer <session_id>`. The browser uses
the gateway cookie automatically. Do not persist a session in browser localStorage.
There is no service-account credential and no API to specify another partner,
technician, company, price, or generic model method.

## Odoo controllers

`/workshop/api/<endpoint>` uses `type='json'`, `auth='user'` on **Odoo 18**.
It receives the normal JSON-RPC envelope with `params`. The standard
`/web/session/authenticate` endpoint handles passwords; the custom controller
never implements password hashing. No wildcard CORS is enabled.

## Job transitions

| Actor | From | To |
|---|---|---|
| Customer | — | requested |
| Manager | requested | awaiting_approval |
| Customer | awaiting_approval | approved |
| Technician | approved | in_progress |
| Technician | in_progress | waiting_parts |
| Technician | waiting_parts | in_progress |
| Technician | in_progress | completed |

Completion requires all inspection checks and no pending parts. Quotation
approval submits the exact snapshot version returned to the client; changed
quotations must be refreshed and reviewed. Issuing parts locks the request and
job, validates the linked sales delivery once, and checks allocation quantities.


# Staff workspace API (version 2)

All staff screens POST `/api/staff` with:

```json
{"action":"list","payload":{"entity":"jobs","search":"WS/","offset":0}}
```

The website forwards transport to Odoo's `/workshop/rest/staff`; Odoo authenticates
the session and dispatches the staff operation. `staff_policy.py` defines the action/role and resource-read
allowlists. This is not an arbitrary Odoo model/method endpoint. Every read or
write scopes records to the active company; technician job operations additionally
require assignment. Customer accounts cannot use this endpoint.

| Group | Actions |
|---|---|
| Read | dashboard, lookups, list, detail, report, document |
| Customers | customer.save, customer.archive, customer.portal |
| Vehicles | vehicle.save, vehicle.archive |
| Job/work | job.save, job.state, job.archive, job.review, check.update |
| Labour | task.save, task.delete, task.update |
| Notes/timers | note.add, timer.start, timer.stop |
| Photos | photo.save, photo.edit, photo.delete |
| Parts | part.request, part.issue, part.reject, part.use |
| Estimates | estimate.save/send/approve/reject/duplicate/delete |
| Inventory | inventory.save, inventory.stock, inventory.archive |
| Invoices | invoice.create/save/post/cancel/email/remind |
| Payments | payment.create, payment.cancel, payment.refund |
| Staff | user.save, user.archive |
| Purchasing | purchase.create, purchase.confirm, purchase.receive |

`list` returns `{rows,total,offset,limit,metrics,currency}`. The page limit is 50.
Supported entity values are customers, vehicles, jobs, work, estimates, inventory,
transactions, invoices, payments, users and purchases. `detail` requires entity
and id. The report endpoint returns all matching rows for its selected report.

Payload forms and concrete action calls are in `lib/staff.ts`, `StaffApp.tsx`,
`JobDetail.tsx`, `EstimateEditor.tsx` and `Reports.tsx`. Server field allowlists and
validation are in `controllers/staff_api.py`; client field names do not grant
extra write privileges.

Main/additional quotation approval accepts `job_id`, `version` and optional
`order_id`. Only a linked quotation on the customer's own job can be approved.
Additional quotations preserve the ongoing job state; pending quotes prevent
completion. Job states additionally include assigned and paused.
