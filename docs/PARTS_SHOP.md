# Customer parts shop and Odoo API

## Architecture

- Odoo owns all REST endpoints, authentication/session lifecycle, permissions,
  customer carts, prices, taxes, orders, stock reservations and cancellation.
- The API is `http://localhost:8070/workshop/rest/<endpoint>` in the local runtime.
- Next.js is the staff/customer frontend. Its `/api/:path*` rewrite only forwards
  HTTP requests to Odoo. There are no Next.js API route handlers or database calls.
- Native React Native calls Odoo directly. `EXPO_PUBLIC_API_URL` is the Odoo base
  URL (Android emulator: `http://10.0.2.2:8070`), rather than the Next.js server.
- The browser preview uses the same forwarding rule as the website. Browsers use
  an Odoo-issued HttpOnly `workshop_session` cookie. Native apps use an Odoo-issued
  bearer session stored in SecureStore. REST sessions expire after eight hours.

## Customer entry points

- Customer website: http://localhost:3001 — sign in, then choose **Parts shop**.
- Direct shop website: http://localhost:3001/shop — includes customer sign-in.
- Mobile/browser preview: http://localhost:3001/mobile-app/index.html — customer
  sign-in, then **Parts shop**. Technician workspaces do not expose purchasing.

## Publish products and fulfil orders

1. In Odoo, open **Workshop Hub → Shop Products** and select an inventory-tracked,
   saleable product. Enable **Sell in customer parts shop**. Add its SKU,
   description, image and vehicle compatibility information.
2. Configure actual prices, customer pricelists, sales taxes and warehouse stock
   in Odoo. Products are private by default; publishing is explicit.
3. Customers search/filter the catalogue, add quantities to their persistent cart,
   review Odoo's subtotal/tax/total, and enter a collection contact and phone.
4. **Place pickup order** confirms an Odoo sales order and reserves its stock.
   Payment is due at the workshop. Nothing is marked paid by checkout.
5. Open **Workshop Hub → Parts Orders** in Odoo. Process the existing delivery
   when goods are handed over, create/post the invoice, and register actual payment.
6. Customers see order status and posted invoice balances/PDFs in **My parts orders**.
   They can cancel an unfulfilled, uninvoiced order; Odoo releases its reservation.

The first checkout supports pickup and payment at the workshop. Delivery, shipping
rates and online card charging require their own configuration/integration and
are not offered as functioning checkout options.

## REST endpoints

All accept JSON POST requests and return ordinary JSON, with an HTTP error status
and `{ "error": "message" }` on failure. Customer authentication is required.

| Endpoint | Parameters | Result |
|---|---|---|
| `shop/catalog` | `search`, `category`, `offset` | Published products, prices, compatibility, availability; 24/page |
| `shop/cart` | none | Current customer's persistent cart and total/version |
| `shop/cart/update` | `product_id`, absolute `quantity` (0 removes) | Updated server-priced cart |
| `shop/checkout` | `order_id`, `version`, `contact_name`, `contact_phone`, optional `vehicle_id`, `note` | Confirmed pickup sales order |
| `shop/orders` | `offset` | Own parts-order history; 20/page |
| `shop/order` | `order_id` | Own cart/order details |
| `shop/cancel` | `order_id` | Cancel eligible order and release stock |
| `shop/invoice` | `order_id`, `invoice_id` | Own posted invoice's base64 PDF |

An order ID is the checkout idempotency key: retrying an already checked-out cart
returns the same order. Checkout validates current prices and available stock;
clients cannot set prices, customer IDs, company IDs, paid status or stock moves.
Changed totals require another customer review. Odoo row locks serialize checkout,
and stock reservation failures roll back the order confirmation.

## Local update and verification

```bash
python3 scripts/local_dev.py stop
python3 scripts/local_dev.py upgrade
python3 scripts/local_dev.py start
npm --prefix apps/mobile run web
python3 tests/live-smoke.py
python3 scripts/local_dev.py test
```

The isolated Odoo tests cover cookie/bearer authentication, logout, expired
sessions, origin rejection, product publication, server pricing, cart persistence,
customer isolation, stale prices, shortages, idempotent checkout, cancellation and
reservation release, alongside the existing repair workflow tests.
The live smoke check also refreshes the same cart concurrently from separate
clients, checking that Odoo retries database conflicts and returns one shared cart.

One clearly labelled `SHOP-DEMO-FILTER` product with development stock is installed
in this local demo. `scripts/seed_shop_demo.py` creates it only once and refuses a
database without the seeded demo customer. It does not change existing stock or
create payment records. Do not run development fixtures against real business data.

For a deployed frontend, set Odoo's `WORKSHOP_ALLOWED_ORIGINS` to its exact HTTPS
origin(s), separated by commas. Set `WORKSHOP_COOKIE_SECURE=1` and configure Odoo's
trusted proxy/TLS. The local server binds loopback; a physical phone requires a
reachable, appropriately secured Odoo endpoint.
