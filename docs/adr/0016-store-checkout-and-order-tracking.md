# 0016. Store: checkout, retried attempts and order tracking

Status: accepted (2026-10-17)

## Context

Checkout is the one place where a customer's retry, a double click and a slow saga all meet. The orders API already makes a repeated `POST` safe (ADR 0014); the store has to use that, keep the card number out of every place it could leak, and show an order whose status changes while the page is open.

## Decision

### Routes

- `/checkout`, `/orders/{id}` and the polling route `/api/orders/{id}` are store routes and are in the proxy's protected list, so a visitor goes to `/login?next=...` and comes back. The gateway only sends `/api/v1/orders`, `/api/v1/admin/orders` and `/orders-service/*` to the orders service, so none of them collides; `make check-routes` proves it with and without a session (a store 404 page with "Order not found" instead of an API problem, the login redirect for a visitor, the documentation routes still reaching their services).
- `/orders/{id}` answers a real `404` for an order that is not the customer's (the API returns 404 for other people's orders, so existence is not leaked) and has no `loading.tsx` above it, for the same reason as the product page (ADR 0010).

### The order is built on the server

The browser sends the attempt key, the chosen address id, the card number and a fingerprint of the cart it showed. The server action reads the cart and the addresses again with the customer's token and builds the body itself: lines and prices come from the cart service and the shipping address is the saved address, copied as a snapshot. It refuses when the cart is empty, any line has a flag (the flags of ADR 0012 block checkout, so the page's own check is a convenience, not the guard), the cart no longer matches the fingerprint (`cart_changed`, so the customer never buys something other than what they saw) or the address id is not one of theirs. A customer cannot choose prices or someone else's address by editing the request.

### Attempts and the Idempotency-Key

- The checkout page generates a UUID on the server for each render and passes it to the form. The form binds it to a signature of the attempt: the cart fingerprint, the address id and the last four digits of the card (the same things the orders API fingerprints, ADR 0014).
- Submitting again with the same signature reuses the key, so a double click, a double Enter or a retry after a network error is one order. If the signature changed (other lines, address or card) the form asks the server for a new key first (`newAttemptKeyAction`), because the API answers `422 idempotency_key_reused` for the same key with a different body. If the API says so anyway, the form takes a fresh key and asks the customer to check and submit again.
- The submit handler ignores a second call while one is in flight (a ref, because two clicks can arrive before React re-renders) and stays disabled once the order is accepted, until the page changes.
- The key lives in component memory only. It is never in a URL, a cookie or storage.

### The card number

- The field is a text input with `inputmode="numeric"`, `autocomplete="cc-number"` and digits grouped by four as they are typed. The form has `method="post"` so a submit before hydration cannot put the number in the URL.
- The number goes browser to the Next server action (a POST body) to the orders API. It is validated, sent, and never logged or put in an error or a Problem Details message by the store; the API's own validation errors name the field, not the value. The form clears the field after every submit, success or failure, so a retry means typing it again: the cost of not keeping it in memory.
- The page says visibly that payments are simulated and lists the four test cards. As ADR 0015 explains, a real provider would tokenize in the browser and the number would never reach the store at all.
- Known limit, inherited from ADR 0014: two attempts that differ only in the digits other than the last four have the same fingerprint, so they share a key and the second returns the first order.

### Order status page

- The server renders the order, so the first paint has the status. A client component then polls `GET /api/orders/{id}`, a store route handler that reads the order with the session token (the token never reaches the browser, as with the cart), with TanStack Query: the delay starts at about 1.5 seconds and grows by half each time to 8 seconds, stops at `CONFIRMED` or `CANCELLED`, with one exception below, and stops at once on 404 or an expired session (which sends the customer to the login page and back). Failures are retried twice with a backoff; while refreshing fails the page keeps the last status and says it may be out of date. Polling pauses in a background tab (Query's default).
- The status is one `role="status"` / `aria-live="polite"` region with the label and its explanation, so each change is announced once: reserving stock, payment in progress, payment received, confirmed, or cancelled with the reason in plain language (out of stock, price changed, payment declined, payment timed out) and, when `refunded_at` is set, that a late payment was refunded. The status always has text and an icon, never colour alone. A cancellation caused by the payment timeout (`saga_timeout`) may still be followed by a refund, when the provider approves late (ADR 0015), and the refund only shows up later in the order. So the page keeps polling such an order, at the slowest rate, until `refunded_at` is set or three minutes after the cancellation, and the status text says that a late payment is refunded automatically; without this the page would show the cancellation and never the refund. Other cancellations have nothing more to come and stop at once. The order's cancel reason is mapped from the codes the saga uses (`insufficient_stock`, `product_unavailable`, `price_changed`, `payment_failed`, `saga_timeout`); an unknown code becomes a generic sentence instead of leaking the raw text.
- The page shows lines (SKU while the name is not yet known, ADR 0014), totals, the address snapshot, the last four digits, the refund date and the status history. Dates are printed in UTC with the zone, so the server and the browser render the same text.
- On `CONFIRMED` the page calls a server action that revalidates the layout, so the header cart count is read again; the cart worker removes the purchased lines asynchronously (ADR 0012), so it is called again after 2 and 6 seconds.

### Addresses

- `/account` lists, adds and deletes addresses (a confirmation dialog for delete, focus returned to the Add button, a status line). The same `AddressForm` is used inline at checkout; a saved address is selected and focused. The form validates with the API's rules (required fields, two-letter country, phone with country code, lengths) and shows the API's field errors on the fields. The address limit (10) is explained in plain language.

## Consequences

- The order is placed in two API calls from the store (cart and addresses) plus the order itself, all with the customer's token; the extra reads are the price of not trusting the browser.
- A customer who goes back to `/checkout` after an accepted order gets a new attempt: the cart worker may not have removed the lines yet, and a second order is then a deliberate act.
- `/api/orders` is a second kind of route in the store (the other is page routes); it is protected like the pages, and a redirect to login is understood by the client as an expired session.
