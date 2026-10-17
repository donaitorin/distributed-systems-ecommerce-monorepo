# 0017. Order views: the customer email snapshot, the order history and the backoffice orders

Status: accepted (2026-10-17)

## Context

The order list of an administrator needs to say who ordered, and the orders service only knows the customer id. Looking the email up in accounts for each row would be a request per order (or a join across two databases, which the architecture forbids). Customers also need to find their past orders.

## Decision

### Customer email on the order

- `orders.customer_email` is a nullable `VARCHAR(320)` (migration `0002`). `POST /orders` copies it from the `email` claim of the access token, trimmed. A missing, blank or longer than 320 characters claim becomes `NULL` and never fails the order: the order matters more than its label.
- It is a snapshot taken when the order is placed. A later change of the customer's email does not rewrite old orders, and an idempotent replay keeps the email of the first request. Orders placed before the migration have `NULL`; the backoffice then shows `Customer 0f6c1f0e`, the start of the customer id, in the list and "Not recorded for this order" next to the full id in the detail.
- Only the admin responses carry it (`AdminOrderSummaryOut`, `AdminOrderDetailOut`, `AdminOrderPageOut`, which extend the customer ones). A customer's own responses are unchanged, so nothing new is exposed to them and the two contracts can evolve apart. The OpenAPI document and the generated client include the admin types.
- The email is personal data kept next to an order that already holds the shipping address. It is not in any event: the events of ADR 0014 are unchanged.

### Store: order history

- `/orders` lists the customer's orders newest first, 25 at a time. The API pages forward only, so the page has Next page and First page links, and the cursor lives in the address: the browser's Back button returns to the previous page and a page can be bookmarked. A cursor the API refuses is explained with a link to the first page.
- Each row links to `/orders/{id}` and shows the status as text and an icon (`OrderStatusBadge` in `packages/ui`, used by both apps), the date, the number of items and the total. The header offers Orders to signed in customers, the account page and the order page link to it.

### Backoffice: orders

- `/admin/orders` follows the users and products lists: filters (status, a first and a last day, page size) and the cursor are URL state read with `nuqs` and Zod, invalid values are ignored, a change of filter clears the cursor and adds a history entry, defaults are not written. The two days are inclusive days in UTC: the first becomes `created_from` at 00:00:00Z and the last becomes `created_to` at 00:00:00Z of the next day, because the API range is half open. An end before the start is explained on the field and the API is not called.
- On small screens each order is a card; the table is hidden, not removed, by CSS. Pagination is forward only, like the users list.
- `/admin/orders/{id}` is read only: summary, customer, lines, shipping address, card last four digits, payment and the full status history. The payment comes from `GET /api/v1/payments/{order_id}`, which allows an administrator to read any payment (`PaymentQueries.of_order` and its API test). A payment that does not exist (an order cancelled before a charge) says so, and one that cannot be read does not hide the order. Cancel reasons and payment statuses are shown as words, and the raw status history is shown as recorded.
- A route-level `not-found` replaces Next's default 404 page, whose inline `<style>` is blocked by the nonce CSP of ADR 0007 and logged a violation.

## Consequences

- The email is only as fresh as the order. If the customer must be reachable for an old order, the accounts service is the place to ask.
- The admin list reads one more column and no other table, so its indexes (ADR 0014) are unchanged.
- `Table` in `packages/ui` no longer puts `role="alert"` on a list item (axe rejects it); the error is a paragraph inside the item.
