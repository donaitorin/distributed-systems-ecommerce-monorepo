# API reference

Per-service behaviour of the REST APIs, as served through the gateway on `http://127.0.0.1:8000`. Every service also publishes interactive OpenAPI docs (see the table below). The main [README](../README.md) has the overview, the quick start and the design decisions.

| Service | Interactive docs |
| --- | --- |
| Auth | `/auth/docs` |
| Accounts | `/accounts/docs` |
| Catalog | `/catalog/docs` |
| Cart | `/cart-service/docs` |
| Orders | `/orders-service/docs` |
| Payments | `/payments-service/docs` |

## Auth API

| Endpoint | Description |
| --- | --- |
| `POST /api/v1/auth/register` | Creates a `customer` account and returns `{id, email, role}` (no tokens). `409` if the email exists, `422` for an invalid email or password |
| `POST /api/v1/auth/login` | Returns `{access_token, refresh_token, token_type, expires_in}`. Unknown email and wrong password give the same `401` |
| `POST /api/v1/auth/refresh` | Body `{refresh_token}`. Rotates the pair; the old refresh token stops working |
| `POST /api/v1/auth/logout` | Body `{refresh_token}`. Revokes the whole session; always `204` |
| `GET /api/v1/auth/.well-known/jwks.json` | Public signing keys (cached for 5 minutes) |
| `PATCH /api/v1/auth/users/{id}/role` | Admin only. Body `{role}` (`customer` or `admin`). `409` when an admin changes their own role, `404` for an unknown user, `200` without an event when the role is already that value |

```bash
curl -s -X POST localhost:8000/api/v1/auth/register -H "Content-Type: application/json" \
  -d '{"email": "ada@example.com", "password": "correct horse battery"}'
curl -s -X POST localhost:8000/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"email": "ada@example.com", "password": "correct horse battery"}'
```

Access tokens are RS256 JWTs that live 15 minutes; any service validates them locally against the JWKS. Refresh tokens are opaque, live 7 days (30 days at most per session) and are stored only as a SHA-256 hash. Tokens are returned in the JSON body: the frontend keeps them in `httpOnly` cookies. Passwords are hashed with Argon2id and must have 10 to 128 characters and not be a common password; there are no composition rules. Emails are trimmed and lowercased. The initial admin comes from `AUTH_ADMIN_EMAIL` and `AUTH_ADMIN_PASSWORD` in `.env`. Reusing a rotated refresh token is rejected; after a 10 second grace window it revokes the whole session. `POST /register` publishes `user.registered` and a role change publishes `user.role_changed` on the `auth.events` topic (key: user id) through the transactional outbox; the `auth-worker` container relays them to Kafka, so registration works while Kafka is down and the events leave when it is back. The gateway limits `POST /login` to 10 requests per minute and `POST /register` to 5 per minute per client address (`429`, with a burst equal to the rate). The design, the signing key rotation procedure and the trade-offs are in [ADR 0005](adr/0005-auth-tokens-and-signing-keys.md).

## Accounts API

| Endpoint | Description |
| --- | --- |
| `GET /api/v1/accounts/me` | The profile of the token's user: `user_id`, `email`, `role`, `name`, `phone`, `created_at`, `updated_at` |
| `PATCH /api/v1/accounts/me` | Body `{name?, phone?}`. `name` is 1 to 100 characters after trimming and cannot be `null`; `phone` is optional, `+` and 8 to 15 digits (spaces, dashes, dots and parentheses are stripped), and `null` or blank clears it. Omitted fields stay as they are |
| `GET /api/v1/accounts/me/addresses` | `{items}` in creation order |
| `POST /api/v1/accounts/me/addresses` | `recipient_name`, `line1`, `city`, `postal_code`, `country` (ISO 3166-1 alpha-2, uppercased) and optional `line2`, `region`, `phone`. `409` after 10 addresses, `422` with field locations |
| `DELETE /api/v1/accounts/me/addresses/{id}` | Hard delete, `204`. `404` for an unknown address or one owned by someone else (orders will snapshot the address they ship to) |
| `GET /api/v1/accounts` | Admin only. `{items, next_cursor}`, newest first. Filters `email` (case-insensitive prefix) and `role`; `limit` 25, 50 or 100; opaque `cursor` bound to the filters (`422` `invalid_cursor` or `cursor_mismatch` on `query.cursor`) |

```bash
TOKEN=$(make -s dev-token)
curl -s localhost:8000/api/v1/accounts/me -H "Authorization: Bearer $TOKEN"
curl -s "localhost:8000/api/v1/accounts?role=admin&limit=25" -H "Authorization: Bearer $TOKEN"
```

Accounts owns the profile; auth owns identity and roles. Authorization always uses the role in the token, never the local copy, which exists to display and filter users in the backoffice. The admin list is forward-only (no previous page, no total).

How a profile comes to exist and stays current:

- **Events.** The `accounts-worker` container consumes `auth.events` in the group `accounts-auth-events`, starting from the earliest offset, so users registered before accounts existed get a profile the first time it runs. `user.registered` creates the profile or, if it already exists, fills a missing email; it never touches the name, phone or addresses. `user.role_changed` updates the role and creates the profile when the registration has not arrived yet. Every event is claimed in `processed_events` in the same transaction as its effect, so a redelivered or republished event does nothing. Messages that are not valid events, or have an unsupported version, go to `auth.events.dlq` with `x-error` headers and the worker keeps consuming.
- **Lazy creation.** Any authenticated `/me` request inserts the profile from the token claims (`sub`, `email`, `role`, `iat`) with `INSERT ... ON CONFLICT DO NOTHING`, and never updates an existing row. This covers the seeded admin, which has no registration event, and users whose event has not been consumed yet. Access tokens issued before the `email` claim existed have none, so the email stays empty until the registration event fills it.
- **Ordering rule.** The role carries the time it was written (`role_updated_at`), and a write changes the role only if its time is strictly newer: `registered_at` for `user.registered`, `changed_at` for `user.role_changed`, and the token `iat` for the lazy path (the token role was read from the database at that moment). When a profile has no role time, because the token had no `iat`, any event wins. The reasoning and its limits are in [ADR 0006](adr/0006-accounts-profile-consistency.md).

The accounts API needs only its own database: `/ready` checks Postgres, the API does not start Kafka, and it fetches the signing keys lazily like catalog. Only the worker needs Kafka.

## Cart API

The cart service keeps one cart per user in `redis-cart` (AOF with `appendfsync everysec`, `noeviction`), so a restart of Redis does not lose carts. Every endpoint needs a customer or admin token and answers `Cache-Control: no-store`. The docs live under `/cart-service/...` because `/cart` is the storefront page.

| Request | What it does |
| --- | --- |
| `GET /api/v1/cart` | `{items, item_count, subtotal}`. Each item has `sku`, `name`, `quantity`, `price` (saved when the line was added or last accepted), `line_total`, `thumbnail_url` and `flags` |
| `PUT /api/v1/cart/items/{sku}` | Body `{quantity, accepted_price?}`, quantity 1 to 99. Creates the line or replaces its quantity and returns the cart. A new line reads the product from catalog (timeout 2 s) and saves its price and name. `404` for an unknown or retired product, `409` when the cart already has 100 different products (`code: cart_full`), `503` with `Retry-After` when catalog or Redis cannot answer |
| `DELETE /api/v1/cart/items/{sku}` | Removes the line (not an error if it is not there) and returns the cart |
| `DELETE /api/v1/cart` | Empties the cart, `204` |

```bash
TOKEN=$(ROLE=customer make -s dev-token)
curl -s -X PUT localhost:8000/api/v1/cart/items/RS-001 -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"quantity": 2}'
curl -s localhost:8000/api/v1/cart -H "Authorization: Bearer $TOKEN"
```

- **Flags.** `GET` compares every line with the cart's projection of catalog and reports, without changing the line: `price_changed` (`old_price`, `new_price`), `unavailable` (the product was retired) and `insufficient_stock` (`available`, which can be 0). The saved price is never the source of truth: checkout revalidates against catalog.
- **Accepting a new price.** `PUT` with `accepted_price` set to the `new_price` the customer saw. The line takes the current price and name and keeps its quantity. If catalog's price is no longer that value the answer is `409` (`code: price_changed`, `current_price`), the same optimistic idea as `If-Match` on products.
- **Projection.** The `cart-worker` container consumes `catalog.events` in the group `cart-catalog-events` and keeps `product:{sku}` (price, stock, name, version, deleted) in Redis, applying an event only if its version is newer than the stored one, with a Lua script. Replays and out of order delivery change nothing, so there is no processed-events table ([ADR 0011](adr/0011-consumers-that-skip-the-claim.md), [ADR 0012](adr/0012-cart-service.md)). Entries exist only for products that were added to some cart and expire 30 days after their last use, so importing 200,000 products cannot fill `redis-cart`.
- **Lifetime.** A cart expires 30 days after its last change. Reading does not renew it.
- **Catalog outage.** The catalog call has a 2 s timeout, one jittered retry for connection errors and `502/503/504`, and a circuit breaker (5 consecutive failures open it for 10 s, then one probe decides; `CART_CATALOG_BREAKER_*` and `CART_CATALOG_RETRY_ATTEMPTS` in `.env`). While it is open, adding a new product answers `503` Problem Details (`code: catalog_unavailable`) with `Retry-After` at once, and viewing the cart, changing a quantity, removing and clearing keep working from Redis and the projection. See [ADR 0018](adr/0018-http-resilience.md), which also lists every synchronous HTTP call with its timeout and retry policy.
- **Independence.** `/ready` checks Redis only. The service starts without catalog, Kafka or auth; catalog is called only when a product is added or a price is accepted.

## Orders API

Orders orchestrates the checkout saga over Kafka ([ADR 0014](adr/0014-orders-saga-and-idempotency.md)): it creates the order as `PENDING` with `order.created`, catalog reserves the stock (`stock.reserved` or `stock.reservation_failed`, [ADR 0013](adr/0013-stock-reservations.md)), orders asks for the payment (`order.payment_requested`) and confirms or cancels. Every state change is a row in `order_status_history`. The docs live under `/orders-service/...` because `/orders` belongs to the storefront.

| Endpoint | Behaviour |
| --- | --- |
| `POST /api/v1/orders` | Customer. Body `{lines: [{sku, quantity, unit_price}], shipping_address, payment: {card_number}}`; the header `Idempotency-Key` is required. `202 {id, status: "PENDING"}`. The same key with the same body returns the same response for 24 hours (`Idempotent-Replay: true`); the same key with a different body is `422` with `code: idempotency_key_reused`; a missing or malformed key is `400`. `unit_price` is the price the customer saw: catalog refuses the order if it changed (`price_changed`) |
| `GET /api/v1/orders` | The customer's own orders, newest first, `limit` 25/50/100, opaque `cursor`, optional `status` |
| `GET /api/v1/orders/{id}` | Owner only (`404` otherwise): lines, totals, `card_last4`, address snapshot, `cancel_reason`, `refunded_at` and the status history |
| `GET /api/v1/admin/orders`, `/{id}` | Admin. Filters `status`, `created_from` (inclusive) and `created_to` (exclusive), both with a time zone |

Statuses: `PENDING`, `STOCK_RESERVED`, `PAID`, `CONFIRMED`, `CANCELLED`. The card number is used only to keep its last four digits: it is not stored, logged or published (a test fails if it appears in the tables, the outbox or the logs). The timeout is `ORDERS_SAGA_TIMEOUT_SECONDS` (60) checked every `ORDERS_SAGA_SWEEP_INTERVAL_SECONDS` (5) by every `orders-worker`, safely in parallel.

```bash
TOKEN=$(ROLE=customer make -s dev-token)
curl -s -X POST localhost:8000/api/v1/orders -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -H "Idempotency-Key: demo-0001" -d '{
    "lines": [{"sku": "RS-001", "quantity": 1, "unit_price": "39.90"}],
    "shipping_address": {"recipient_name": "Ada", "line1": "1 St", "city": "London", "postal_code": "N1", "country": "GB"},
    "payment": {"card_number": "4111 1111 1111 1111"}}'
```

## Payments API

Payments consumes `order.payment_requested` from `orders.events` and answers on `payments.events` with `payment.succeeded`, `payment.failed` or, after a late success for a cancelled order, `payment.refunded`. It is idempotent per order (`payments.order_id` is unique) and calls a `PaymentProvider` port with the order id as the idempotency key; the only adapter is a simulation, replaceable by a real one ([ADR 0015](adr/0015-payments-provider-port-and-stripe.md), which also explains how Stripe would plug in). The docs live under `/payments-service/...`.

| Card ending | Behaviour |
| --- | --- |
| `1111` (and any other ending) | Approved at once: order `CONFIRMED` |
| `0000` | Declined: `payment.failed`, order `CANCELLED` (`payment_failed`) and the stock comes back |
| `9999` | The provider never answers: the payment stays `PENDING` and the saga timeout cancels the order and releases the stock |
| `2222` | Approved after `PAYMENT_LATE_APPROVAL_DELAY_SECONDS` (90, longer than the 60 s saga timeout): the order is already `CANCELLED`, so the payment is refunded (`payment.refunded`) and the order history gets `payment refunded` |

`GET /api/v1/payments/{order_id}` is for the order's owner or an admin (`404` for anyone else) and returns the status, amount, `card_last4` and failure reason; the full number is never stored. A total of `0.00` skips payments: the order is confirmed right after the stock is reserved. After `order.confirmed` the `cart-worker` removes the purchased lines from the customer's cart ([ADR 0012](adr/0012-cart-service.md)). `backend/tests/e2e` runs the whole saga (catalog, orders, payments and cart workers against real Postgres, Kafka and Redis) for each card above and for a total of zero, with short delays.

## Catalog API

Reads are public. Creating, replacing and deleting products and creating categories need an admin token. `make dev-token` logs in as the seeded admin and prints the access token (`ROLE=customer make dev-token` logs in as a dev customer, registering `dev-customer@example.com` the first time).

```bash
TOKEN=$(make -s dev-token)
curl -s localhost:8000/api/v1/products
curl -s -X POST localhost:8000/api/v1/products \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"sku": "DEMO-1", "name": "Demo", "price": "19.90", "stock": 5}'
curl -s -i localhost:8000/api/v1/products/DEMO-1      # note the ETag header
curl -s -X PUT localhost:8000/api/v1/products/DEMO-1 \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H 'If-Match: "1"' -d '{"name": "Demo", "price": "21.00", "stock": 4}'
```

Products carry a `version`, returned as the `ETag`. `PUT` and `DELETE` require it in `If-Match` (`428` when missing, `412` when stale), so two editors can never silently overwrite each other's stock. Prices and weights are JSON strings to keep their precision. The interactive docs are at `/catalog/docs`.

### Search, filters and pagination

`GET /api/v1/products` is a keyset-paginated search. All parameters are optional.

| Parameter | Values | Default |
| --- | --- | --- |
| `q` | Free text, up to 100 characters. Typos are tolerated | No text filter |
| `category` | Category slug. An unknown slug returns an empty page | All |
| `min_price`, `max_price` | Decimals with at most 2 places, inclusive | No limit |
| `in_stock` | `true` hides sold-out products. `false` is the same as omitting it | Includes sold out |
| `sort` | `relevance`, `price_asc`, `price_desc`, `newest` | `relevance` with `q`, otherwise `newest` |
| `limit` | `12`, `24`, `48` | `24` |
| `cursor` | The `next_cursor` or `prev_cursor` of a previous response | First page |

```bash
curl -s 'localhost:8000/api/v1/products?q=runing+shoes&limit=12'
curl -s 'localhost:8000/api/v1/products?category=footwear&min_price=20&max_price=150&in_stock=true&sort=price_asc'
curl -s 'localhost:8000/api/v1/products?q=running+shoes&limit=12&cursor=<next_cursor>'
```

The response is `{"items", "next_cursor", "prev_cursor", "total", "total_exact"}`. A cursor is opaque and only valid with the same `q`, `category`, price, `in_stock` and `sort` it was issued for (`422` with `cursor_mismatch` otherwise); `limit` may change between pages. `total` is exact for small result sets and a planner estimate otherwise (`total_exact` is `false`). The design is recorded in [ADR 0002](adr/0002-catalog-search-and-keyset-pagination.md).

A search that exceeds `CATALOG_SEARCH_TIMEOUT_MS` (2000 by default) is cancelled and answers `503` Problem Details with `Retry-After: 1`.

`make seed` loads synthetic products (`COUNT=200000` by default) so search and pagination can be tried at volume. It is safe to run twice: existing `SEED-` SKUs are skipped, and a larger `COUNT` only adds the missing ones.

### Product images

Admins attach one image per product. Changing it changes the product, so both calls need an admin token and `If-Match`, and both return the product with its new `ETag`.

```bash
TOKEN=$(make -s dev-token)
curl -s -X PUT localhost:8000/api/v1/products/DEMO-1/image \
  -H "Authorization: Bearer $TOKEN" -H 'If-Match: "1"' -F "file=@photo.jpg"
curl -s -X DELETE localhost:8000/api/v1/products/DEMO-1/image \
  -H "Authorization: Bearer $TOKEN" -H 'If-Match: "2"'
```

The response has `image_url` (1200 px) and `thumbnail_url` (400 px), both WebP, served through the gateway under `/media/` with a one-year immutable cache header. Open `image_url` in the browser to see the result. Only JPEG, PNG and WebP are accepted, checked by content and not by file name, up to 5 MB and 25 megapixels (`413`, `415` and `422` otherwise). EXIF, GPS and ICC color profiles are removed. If object storage is down, only these two endpoints fail (`503` with `Retry-After`); catalog stays ready. The design is in [ADR 0003](adr/0003-product-images.md).

### CSV import

The import endpoints (`/api/v1/imports`, confirm, revalidate, `problems.csv`), the validation rules and the report of the sample file are in [csv-import.md](csv-import.md).

### Product events

Every catalog write publishes an event on the `catalog.events` topic (key: SKU) through the transactional outbox, in the same transaction as the write; the `catalog-worker` relays them. Creating, replacing, changing or removing the image of a product, and every product that a CSV import creates, updates or restores, publish `product.updated` with `sku`, `name`, `price`, `stock`, `image_key` (an object key, never a URL), `version` and `occurred_at`. Soft deleting publishes `product.deleted` with `sku`, `version` and `occurred_at`. Rows of an import that change nothing publish nothing. The version grows with every change of a product, so a consumer applies an event only if its version is newer than the one it holds, which makes redelivery and reordering harmless. The payloads live in `backend/libs/contracts` with stored examples. A large import writes one outbox row per changed product: measured on a laptop with Testcontainers (Postgres and Kafka, relay batch of 100), a 100,000 row import that created every product took 39 s including the outbox rows, and the relay then needed 36 s (about 2,800 events per second) to publish the 100,000 events. Publishing takes roughly 4 s per 10,000 changed products after the import finishes; no optimization was needed.

### Stock reservations

Stock reservations for the checkout saga live in catalog: on `order.created` (topic `orders.events`) the `catalog-worker` takes the stock of the whole order in one transaction (an atomic `UPDATE ... WHERE stock >= :qty` per line, in SKU order) and answers `stock.reserved` or `stock.reservation_failed` on `inventory.events`; on `order.cancelled` it gives the stock back and answers `stock.released`. Both are safe to replay, a cancellation that arrives before its order leaves a tombstone, and every change of stock emits `product.updated` so carts see it. See [ADR 0013](adr/0013-stock-reservations.md).
