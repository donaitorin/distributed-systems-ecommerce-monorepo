# Distributed Systems E-commerce

Event-driven e-commerce built as microservices (auth, accounts, catalog, cart, orders, payments) with a Next.js storefront and backoffice. Work in progress: the base environment, the auth, accounts and catalog services and the frontend foundations (design system, session handling, storefront and backoffice shells) are in place.

## Requirements

- Docker with Compose v2
- GNU Make

To work on the code (not needed to run the stack): Python 3.13 with [uv](https://docs.astral.sh/uv/) for the backend, and the Node.js version in `frontend/.nvmrc` with Corepack for the frontend.

## Quick start

```bash
cp .env.example .env
make up
make ps
```

When the stack is healthy, <http://127.0.0.1:8000/> is the store and <http://127.0.0.1:8000/admin> the backoffice (it redirects to its login page until an admin session exists). Both are built from `frontend/` and start without any backend.

`.env.example` holds demo values for local development only. Change them if the stack is reachable from anywhere other than your machine.

## Local infrastructure

All ports are bound to `127.0.0.1` and can be changed in `.env`.

| Component | Container | Host port |
| --- | --- | --- |
| Gateway (Traefik) | `gateway` | 8000 |
| Gateway dashboard | `gateway` | 8001 |
| PostgreSQL | `postgres` | 15432 |
| Redis for carts (AOF, `noeviction`) | `redis-cart` | 16379 |
| Redis for cache (`allkeys-lru`, no persistence) | `redis-cache` | 16380 |
| Kafka (KRaft) | `kafka` | 29092 |
| Kafka UI | `kafka-ui` | 8088 |
| Object storage S3 API (SeaweedFS) | `object-storage` | 19000 |

The store and backoffice (`store`, `backoffice`) publish no host port: they are reached through the gateway on a separate `frontend` network (`10.250.10.0/28`) that holds only the gateway and the two apps, whose fixed addresses are the only ones the gateway trusts for forwarded headers.

One-shot jobs `kafka-init`, `object-storage-init`, `auth-migrate` and `catalog-migrate` create the topics and buckets and apply database migrations, then exit. `auth-migrate` also seeds the initial admin. `auth-worker` and `catalog-worker` relay outbox events to Kafka.

## Services

| Service | Container | Reachable through the gateway |
| --- | --- | --- |
| Auth | `auth` | `/api/v1/auth/*`, and `/auth/docs`, `/auth/health`, `/auth/ready` |
| Accounts | `accounts`, `accounts-worker` | `/api/v1/accounts/*`, and `/accounts/docs`, `/accounts/health`, `/accounts/ready` |
| Cart | `cart`, `cart-worker` | `/api/v1/cart/*`, and `/cart-service/docs`, `/cart-service/health`, `/cart-service/ready` |
| Payments | `payments`, `payments-worker` | `/api/v1/payments/*`, and `/payments-service/docs`, `/payments-service/health`, `/payments-service/ready` |
| Orders | `orders`, `orders-worker` | `/api/v1/orders/*`, `/api/v1/admin/orders/*`, and `/orders-service/docs`, `/orders-service/health`, `/orders-service/ready` |
| Catalog | `catalog` | `/api/v1/products`, `/api/v1/categories`, and `/catalog/docs`, `/catalog/health`, `/catalog/ready` |
| Backoffice | `backoffice` | `/admin` and `/admin/*` |
| Store | `store` | Everything else (lowest priority), including `/login`, `/register` and `/account` |

The auth service generates its RSA signing key into a Docker volume on first start, and catalog (and every other service) validates tokens against its JWKS. Nothing secret is stored in the repository.

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

Access tokens are RS256 JWTs that live 15 minutes; any service validates them locally against the JWKS. Refresh tokens are opaque, live 7 days (30 days at most per session) and are stored only as a SHA-256 hash. Tokens are returned in the JSON body: the frontend keeps them in `httpOnly` cookies. Passwords are hashed with Argon2id and must have 10 to 128 characters and not be a common password; there are no composition rules. Emails are trimmed and lowercased. The initial admin comes from `AUTH_ADMIN_EMAIL` and `AUTH_ADMIN_PASSWORD` in `.env`. Reusing a rotated refresh token is rejected; after a 10 second grace window it revokes the whole session. `POST /register` publishes `user.registered` and a role change publishes `user.role_changed` on the `auth.events` topic (key: user id) through the transactional outbox; the `auth-worker` container relays them to Kafka, so registration works while Kafka is down and the events leave when it is back. The gateway limits `POST /login` to 10 requests per minute and `POST /register` to 5 per minute per client address (`429`, with a burst equal to the rate). The design, the signing key rotation procedure and the trade-offs are in [ADR 0005](docs/adr/0005-auth-tokens-and-signing-keys.md).

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
- **Ordering rule.** The role carries the time it was written (`role_updated_at`), and a write changes the role only if its time is strictly newer: `registered_at` for `user.registered`, `changed_at` for `user.role_changed`, and the token `iat` for the lazy path (the token role was read from the database at that moment). When a profile has no role time, because the token had no `iat`, any event wins. The reasoning and its limits are in [ADR 0006](docs/adr/0006-accounts-profile-consistency.md).

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
- **Projection.** The `cart-worker` container consumes `catalog.events` in the group `cart-catalog-events` and keeps `product:{sku}` (price, stock, name, version, deleted) in Redis, applying an event only if its version is newer than the stored one, with a Lua script. Replays and out of order delivery change nothing, so there is no processed-events table ([ADR 0011](docs/adr/0011-consumers-that-skip-the-claim.md), [ADR 0012](docs/adr/0012-cart-service.md)). Entries exist only for products that were added to some cart and expire 30 days after their last use, so importing 200,000 products cannot fill `redis-cart`.
- **Lifetime.** A cart expires 30 days after its last change. Reading does not renew it.
- **Catalog outage.** The catalog call has a 2 s timeout, one jittered retry for connection errors and `502/503/504`, and a circuit breaker (5 consecutive failures open it for 10 s, then one probe decides; `CART_CATALOG_BREAKER_*` and `CART_CATALOG_RETRY_ATTEMPTS` in `.env`). While it is open, adding a new product answers `503` Problem Details (`code: catalog_unavailable`) with `Retry-After` at once, and viewing the cart, changing a quantity, removing and clearing keep working from Redis and the projection. See [ADR 0018](docs/adr/0018-http-resilience.md), which also lists every synchronous HTTP call with its timeout and retry policy.
- **Independence.** `/ready` checks Redis only. The service starts without catalog, Kafka or auth; catalog is called only when a product is added or a price is accepted.

## Orders API

Orders orchestrates the checkout saga over Kafka ([ADR 0014](docs/adr/0014-orders-saga-and-idempotency.md)): it creates the order as `PENDING` with `order.created`, catalog reserves the stock (`stock.reserved` or `stock.reservation_failed`, [ADR 0013](docs/adr/0013-stock-reservations.md)), orders asks for the payment (`order.payment_requested`) and confirms or cancels. Every state change is a row in `order_status_history`. The docs live under `/orders-service/...` because `/orders` belongs to the storefront.

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

Payments consumes `order.payment_requested` from `orders.events` and answers on `payments.events` with `payment.succeeded`, `payment.failed` or, after a late success for a cancelled order, `payment.refunded`. It is idempotent per order (`payments.order_id` is unique) and calls a `PaymentProvider` port with the order id as the idempotency key; the only adapter is a simulation, replaceable by a real one ([ADR 0015](docs/adr/0015-payments-provider-port-and-stripe.md), which also explains how Stripe would plug in). The docs live under `/payments-service/...`.

| Card ending | Behaviour |
| --- | --- |
| `1111` (and any other ending) | Approved at once: order `CONFIRMED` |
| `0000` | Declined: `payment.failed`, order `CANCELLED` (`payment_failed`) and the stock comes back |
| `9999` | The provider never answers: the payment stays `PENDING` and the saga timeout cancels the order and releases the stock |
| `2222` | Approved after `PAYMENT_LATE_APPROVAL_DELAY_SECONDS` (90, longer than the 60 s saga timeout): the order is already `CANCELLED`, so the payment is refunded (`payment.refunded`) and the order history gets `payment refunded` |

`GET /api/v1/payments/{order_id}` is for the order's owner or an admin (`404` for anyone else) and returns the status, amount, `card_last4` and failure reason; the full number is never stored. A total of `0.00` skips payments: the order is confirmed right after the stock is reserved. After `order.confirmed` the `cart-worker` removes the purchased lines from the customer's cart ([ADR 0012](docs/adr/0012-cart-service.md)). `backend/tests/e2e` runs the whole saga (catalog, orders, payments and cart workers against real Postgres, Kafka and Redis) for each card above and for a total of zero, with short delays.

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

The response is `{"items", "next_cursor", "prev_cursor", "total", "total_exact"}`. A cursor is opaque and only valid with the same `q`, `category`, price, `in_stock` and `sort` it was issued for (`422` with `cursor_mismatch` otherwise); `limit` may change between pages. `total` is exact for small result sets and a planner estimate otherwise (`total_exact` is `false`). The design is recorded in [ADR 0002](docs/adr/0002-catalog-search-and-keyset-pagination.md).

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

The response has `image_url` (1200 px) and `thumbnail_url` (400 px), both WebP, served through the gateway under `/media/` with a one-year immutable cache header. Open `image_url` in the browser to see the result. Only JPEG, PNG and WebP are accepted, checked by content and not by file name, up to 5 MB and 25 megapixels (`413`, `415` and `422` otherwise). EXIF, GPS and ICC color profiles are removed. If object storage is down, only these two endpoints fail (`503` with `Retry-After`); catalog stays ready. The design is in [ADR 0003](docs/adr/0003-product-images.md).

### CSV import rules

`data/sample-products.csv` (downloaded Thursday 15 October 2026) is committed on purpose: it is seeded with edge cases and the tests run the whole file. The parsing and validation core is pure code in `catalog.domain.csv_import` (no I/O); the upload, confirmation and worker flow is built on top of it (see below).

Required columns are `name`, `sku`, `price` and `stock`; `description`, `category` and `weight_kg` are optional. Column names ignore case and spaces, order does not matter, and unknown or repeated columns reject the file. Row numbers are spreadsheet rows: the header is row 1, and a quoted cell with line breaks is still one row.

| Case in the file | Rule |
| --- | --- |
| Rows with every field empty | Ignored, counted in the report, never an error |
| Empty or whitespace-only name | Error |
| `$29.99` | Read as `29.99`, with a warning. Other formats (`1,299.99`, `29,99`, `12$`, `1e3`) are errors |
| Non-numeric price (`free`), negative price, more than 2 decimals | Error. `0.00` is valid |
| Negative or non-integer stock | Error. `0` and `99999` are valid |
| Empty weight / empty category | Valid, stored as `null` |
| Category that does not exist | Error, never created automatically. Matching ignores case and extra spaces; the report groups unknown names with how many rows they affect and suggests the closest existing one |
| Same SKU in several rows | The last row wins. Every earlier row with different data gets a warning ("replaced by row N"); an earlier row identical to the winner is skipped silently. If the last row is invalid the SKU is not imported |
| Same name, different SKU | Valid: the SKU is the identity |
| HTML or SQL-looking names, commas, quotes, `—`, `™` | Stored literally (real `csv` parser, UTF-8 with BOM detection) |
| Not UTF-8, binary, empty, header only, malformed quoting, missing columns | The whole file is rejected and every document-level problem is reported at once |

Every problem carries the row, the column, the received value and the reason, separated into errors and warnings. The sample file produces:

| Row | Column | Severity | Received | Reason |
| --- | --- | --- | --- | --- |
| 2 | sku | warning | `RS-001` | replaced by row 36, the last row with this SKU |
| 4 | price | warning | `$29.99` | currency symbol removed, read as 29.99 |
| 7 | price | error | `free` | price must be a plain number such as 29.99 |
| 16 | stock | error | `-5` | stock must not be negative |
| 25 | name | error | (empty) | name must not be empty |
| 41 | name | error | (spaces) | name must not be empty |
| 56 | sku | warning | `BS-021` | replaced by row 89, the last row with this SKU |

97 rows = 2 blank + 4 with errors + 3 skipped (rows 2 and 56 replaced by later rows, row 11 identical to the winning row 89) + 88 importable products.

### Product events

Every catalog write publishes an event on the `catalog.events` topic (key: SKU) through the transactional outbox, in the same transaction as the write; the `catalog-worker` relays them. Creating, replacing, changing or removing the image of a product, and every product that a CSV import creates, updates or restores, publish `product.updated` with `sku`, `name`, `price`, `stock`, `image_key` (an object key, never a URL), `version` and `occurred_at`. Soft deleting publishes `product.deleted` with `sku`, `version` and `occurred_at`. Rows of an import that change nothing publish nothing. The version grows with every change of a product, so a consumer applies an event only if its version is newer than the one it holds, which makes redelivery and reordering harmless. The payloads live in `backend/libs/contracts` with stored examples. A large import writes one outbox row per changed product: measured on a laptop with Testcontainers (Postgres and Kafka, relay batch of 100), a 100,000 row import that created every product took 39 s including the outbox rows, and the relay then needed 36 s (about 2,800 events per second) to publish the 100,000 events. Publishing takes roughly 4 s per 10,000 changed products after the import finishes; no optimization was needed.

### Importing a CSV

Nothing is written to the catalog until an admin confirms. The file is validated in the background by the `catalog-worker` container, which talks to Kafka; the API itself only needs Postgres and the object store.

```bash
TOKEN=$(make -s dev-token)
curl -s -X POST localhost:8000/api/v1/imports -H "Authorization: Bearer $TOKEN" \
  -F "file=@data/sample-products.csv"                         # 202, status "uploaded"
curl -s localhost:8000/api/v1/imports/<id> -H "Authorization: Bearer $TOKEN"
                                                               # wait for status "validated": counts + first problems
curl -s localhost:8000/api/v1/imports/<id>/problems.csv -H "Authorization: Bearer $TOKEN"
curl -s -X POST localhost:8000/api/v1/imports/<id>/revalidate -H "Authorization: Bearer $TOKEN"
                                                               # 202, status "uploaded" again: same file, current categories
curl -s -X POST localhost:8000/api/v1/imports/<id>/confirm -H "Authorization: Bearer $TOKEN"
                                                               # 202, status "queued" -> "processing" -> "completed"
curl -s 'localhost:8000/api/v1/products?q=yoga+block'
```

| Status | Meaning |
| --- | --- |
| `uploaded`, `validating` | Stored and hashed; the worker is checking every row |
| `validated` | The report is ready; the admin can fix the file and upload it again, or confirm to import only the valid rows |
| `rejected` | The whole file is unusable (not UTF-8 text, missing columns, ...); every document problem is listed |
| `queued`, `processing` | Confirmed; the worker upserts in batches of 1000 and `progress` grows |
| `completed` | `progress` has the created, updated, restored and unchanged counts |
| `failed` | A worker error survived its retries (the message is in the dead letter topic); `failure_reason` says why |

Uploading the same file twice returns the existing import (`200`), also when it was rejected or has errors. To fix the cause without re-uploading, for example after creating a category the file refers to, `POST /imports/{id}/revalidate` validates the stored file again. It is allowed from `validated` and `rejected` only (`409` once the import is confirmed), discards the previous report, problems and category snapshot in the same transaction that moves the status back to `uploaded` and queues a new `import.validation_requested`, and repeating it while it is pending is harmless (no second event). Rows are upserted by SKU: existing products are updated (and their version bumped only if something changed), soft-deleted ones are restored, and images are never touched. Files are limited by `IMPORT_MAX_BYTES` (50 MB by default). The design, including the reusable messaging library, is in [ADR 0004](docs/adr/0004-csv-import-and-messaging-core.md).

Stock reservations for the checkout saga live in catalog: on `order.created` (topic `orders.events`) the `catalog-worker` takes the stock of the whole order in one transaction (an atomic `UPDATE ... WHERE stock >= :qty` per line, in SKU order) and answers `stock.reserved` or `stock.reservation_failed` on `inventory.events`; on `order.cancelled` it gives the stock back and answers `stock.released`. Both are safe to replay, a cancellation that arrives before its order leaves a tombstone, and every change of stock emits `product.updated` so carts see it. See [ADR 0013](docs/adr/0013-stock-reservations.md).

## Frontend

`frontend/` is a pnpm and Turborepo workspace with two Next.js apps joined with [Multi-Zones](docs/adr/0007-frontend-zones-session-and-csp.md): `apps/store` at `/` and `apps/backoffice` at `/admin`. Shared code is in `packages/`: `config` (ESLint, tsconfig, Jest preset, the Tailwind theme and the Next.js configuration), `ui` (components with Storybook), `api-client` (types generated from the services' OpenAPI documents and a small typed fetch wrapper that understands `application/problem+json`), `auth` (server-side session handling) and `web-core` (logic and hooks both apps share: URL search parsers, failure handling and the navigation context; no visual components).

```bash
nvm install && nvm use         # in frontend/, installs the version in .nvmrc
corepack enable                # uses the pnpm version pinned in package.json
make install-frontend
make storybook                 # http://localhost:6006
make test-frontend             # Jest with an 85% coverage threshold per package
make test-storybook            # builds Storybook and runs axe on every story
make lint                      # backend and frontend linters and typechecks
```

If `pnpm -v` does not print the version pinned in `frontend/package.json`, another pnpm (for example a Homebrew one) comes first in your `PATH`; the make targets run `corepack pnpm` from inside `frontend/`, where Corepack reads the pinned `packageManager` (Corepack looks at the package.json of the current directory, not at `--dir`), so they use the pinned version on a machine that has never run Corepack.

- **Styling.** Tailwind v4 is the only styling approach. `packages/config/styles/theme.css` is the single source of design tokens (warm palette, Inter and Playfair Display self-hosted through Fontsource, radii, breakpoints). A test checks every text and control colour pair for WCAG 2.2 AA contrast, and another one fails on removed or misused tokens in component sources.
- **API types.** `backend/tools/dump_openapi.py` writes each service's OpenAPI document to `frontend/packages/api-client/openapi/` and openapi-typescript generates the types. `make openapi` regenerates both; `make check-openapi` (a CI job and a backend test) fails when they are stale.
- **Sessions.** Tokens live in `httpOnly`, `SameSite=Lax` cookies, never in `localStorage`. The Next.js servers call login, register and refresh through the gateway and forward the visitor's address, so the gateway rate limits stay per client. The design, what is proven and what is not are in [ADR 0008](docs/adr/0008-gateway-forwarded-headers-and-rate-limits.md); `make check-rate-limit` runs the proof.
- **Security headers.** Strict, nonce-based Content Security Policy (fonts only from `'self'`), `X-Content-Type-Options`, `Referrer-Policy`, frame and permissions headers. Because a nonce is per response, every page is rendered dynamically; the trade-offs, the refresh deduplication that only works inside one Next.js process, and the deprecated Storybook test runner we keep on purpose are in [ADR 0007](docs/adr/0007-frontend-zones-session-and-csp.md).
- **Routes.** `make check-routes` proves against the running stack that `/` (a temporary redirect to `/products`), `/products`, a product page, `/login` and `/account` reach the store, `/admin` reaches the backoffice, and that no zone route shadows `/api/v1`, `/media`, `/auth`, `/catalog` or `/accounts`.
- **Images.** Both apps build from `frontend/` with multi-stage Dockerfiles (Next.js standalone output, non-root user, pinned base image) and copy only the packages they use, so `make up` twice in a row recreates nothing, and editing one zone rebuilds only that zone.

### Backoffice

`/admin` signs administrators in (`/admin/login`; customers and anonymous visitors are sent back to it) and manages the catalog. It covers sign in and out, the product list, creating, editing, deleting and adding images to products, categories and the users page; the CSV import flow.

- **Everything goes through the Next.js server.** The browser never calls the API: server components read, server actions write, and image uploads stream through a route handler to the gateway without being buffered (limit enforced by `Content-Length` and by counting bytes). The reasoning, including why those routes bypass `proxy.ts`, is in [ADR 0009](docs/adr/0009-backoffice-data-access-and-uploads.md).
- **Navigation.** The shell links to the sections that exist (Products, Categories and Users). CSV import is not a separate section: the products page has an "Import CSV" button that opens `/admin/products/import`.
- **Products list.** Search, category, price range, availability, sort, page size and cursor live in the URL (`nuqs` + Zod): invalid values are ignored, defaults are not written, the cursor is cleared when a filter changes, and back and forward restore each state. The result count is announced with a status region and shown as approximate when the backend estimates it. On narrow screens the table becomes cards.
- **Categories.** The list and a create form (the API has no update or delete). A duplicate name, or one with the same slug, is shown on the field; names are validated like the backend does (whitespace collapsed, at most 100 characters, at least one letter or digit).
- **Users.** Email prefix, role and page size live in the URL like the product filters. The accounts API is forward-only, so there is "Next" and "First page" but no previous page and no total. A role change asks for confirmation and goes to the auth service; the API refuses an administrator changing their own role (`409`) and the dialog shows that. The accounts copy of the role is updated by an event, so the list shows the new role immediately and the server catches up a moment later; the user's current session keeps its old role until it refreshes (at most 15 minutes).
- **CSV import (`/admin/products/import`).** Linked from the products page, not from the navigation. The file goes through a guarded route handler (`/admin/api/stream/imports`) that streams it to the catalog API like the image upload does: it is never buffered, `IMPORT_MAX_BYTES` (50 MB by default, the same variable the backend reads) is enforced by `Content-Length` and by counting bytes, and the browser refuses a bigger file before sending it. The page then follows the import with TanStack Query: it polls with a growing delay, stops when the import is validated, rejected, completed or failed, and announces each status change in a polite live region. The report shows the counts (to create, update, restore, unchanged, errors, warnings), unknown categories grouped with the suggested existing name and a "Create category" button each (the Part B category creation), the problems with a severity filter and cursor pagination, and a `problems.csv` download. Confirming needs a validated import with importable rows and an explicit dialog; after creating a category, "Validate again" calls `POST /imports/{id}/revalidate`. The import id lives in the URL (`?import=<id>`), so a reload or a pasted link opens the same import.
- **Product form.** React Hook Form with a Zod schema that mirrors the backend rules, focus on the first invalid field, backend Problem Details shown on the fields. Edit sends `If-Match`; a `412` opens a dialog that shows the differing fields and lets the administrator choose between the latest version and their own input.
- **Testing deviation.** The project specification mentions MSW for mocking the API. Because every API call is made by the Next.js server, the tests mock `fetch` at that boundary instead and the project avoids one dependency.

Keyboard and screen reader walkthrough of the purchase flow (VoiceOver or NVDA) is added with the checkout in a later stage.

### Store

`/` redirects (307, query string kept) to `/products`, the product search, and `/products/{sku}` is the product page. Both are server components, so the first response already has the results; they are public, and the visitor's address is forwarded like in the backoffice. The decisions are in [ADR 0010](docs/adr/0010-store-catalog-search-and-product-pages.md).

- **Search state lives in the URL.** `q`, `category` (slug), `min_price`, `max_price`, `in_stock`, `sort`, `limit` and `cursor` are parsed with the `web-core` parsers (the ones the backoffice uses): an invalid value is ignored and defaults are never written. Every filter change is a history entry (`router.push` through nuqs), so back and forward walk the filters; the search text is applied 300 ms after the last keystroke; any filter change drops the cursor. Previous and Next carry the cursor in the URL, so a pasted link opens the same page. A total that is only an estimate reads "About 1,200 results".
- **Filters.** A sidebar from the `lg` breakpoint and a drawer below it (Radix Dialog: focus trapped, Escape closes, focus returns to the button that opened it). Active filters are removable chips with a "Clear all filters" button. The grid has 1, 2, 3 and 4 columns from the `sm`, `lg` and `xl` breakpoints. The total is announced through the pagination live region.
- **Product page.** The SKU is case-insensitive: another case redirects to the canonical address. Unknown and retired products are a real 404 with a page that links back to the catalog, and a temporary catalog failure shows an alert with a retry link instead. Out of stock products stay visible with their badge and a notice, and show no purchase action. `add-to-cart-slot.tsx` marks where the cart stage puts the add to cart form.
- **Images.** Cards use the 400 px thumbnail and the product page the 1200 px image; a product without an image, or whose image fails to load (also before hydration), shows the placeholder. `MEDIA_PUBLIC_BASE_URL` is relative, so the URLs are same-origin and the CSP needs nothing extra.
- **Customer accounts.** `/register` creates the account and signs in with the same credentials; `/login` signs in. Both are server actions over `packages/auth`, so the tokens only ever live in the `httpOnly` cookies. An email that is taken is shown on the email field (with a link to sign in), password rules from the API (too short, too common, same as the email) are explained in plain language on the password field, and a rate limit says when to retry. `next` is only accepted as an internal path (`nextPath` in `web-core`, the same helper and open-redirect table the backoffice uses); anything else, and the login and register pages themselves, fall back to `/products`. The header shows Sign in to a visitor and Account and Sign out to a customer. `/account` reads the profile from `GET /api/v1/accounts/me` and edits name and phone with `PATCH` (a blank phone clears it); field errors are linked to their inputs and focus goes to the first invalid one. Saved addresses come with checkout.
- **Cart.** The product page has the add to cart action in its slot: a quantity (1 to 99, never above the stock) and a button that is disabled, with the reason, when the product is out of stock. A visitor who adds goes to `/login?next=/products/{sku}`. Signed in customers see a Cart link with the number of units in the header; a polite live region announces the new count when it changes. `/cart` (protected like `/account`; the cart service documentation is under `/cart-service`) lists each line with image, name, quantity control, line total and Remove, a subtotal, an empty state and Clear cart behind a confirmation dialog. Every call goes through the store server with the session cookie. A price change shows as "The price changed from $X to $Y" with Accept new price (it sends `accepted_price`; on a `409` the page shows the price the server reported and the next click accepts that one), a retired product as "No longer available" and low stock as "Only N left" or "Out of stock". The cart limits (100 different products, 1 to 99 per product) and an unreachable cart are shown as plain messages, the latter with Try again. Changes are announced in `role="status"` regions and focus returns to the page heading when the cart empties. See [ADR 0010](docs/adr/0010-store-catalog-search-and-product-pages.md).

## Resilience

Each pattern below has a test that proves it; the last column says how to see it work.

| Pattern | Where it lives | See it work |
| --- | --- | --- |
| Transactional outbox, at least once | `libs/messaging` (`OutboxWriter`, `OutboxRelay`), one table per service | Stop Kafka, place an order: it is accepted and waits as `PENDING` (`make check-failure-scenarios SCENARIO=kafka`) |
| Idempotent consumers | `processed_events` claims, or naturally idempotent handlers ([ADR 0011](docs/adr/0011-consumers-that-skip-the-claim.md)) | The outbox may publish an event twice after a restart; the effect (stock, payment, profile) happens once |
| Retries with backoff, dead letter topics | `EventConsumer`: 3 attempts, then `<topic>.dlq`, the partition keeps moving | `make check-dead-letters` |
| `Idempotency-Key` on `POST /orders` | orders service ([ADR 0014](docs/adr/0014-orders-saga-and-idempotency.md)) | Repeat the same request: same order, header `Idempotent-Replay: true` |
| Saga timeout | the orders worker cancels `PENDING` and `STOCK_RESERVED` orders after `ORDERS_SAGA_TIMEOUT_SECONDS` (60) and the stock is released | Stop payments, place an order (`make check-failure-scenarios SCENARIO=payments`) |
| Timeouts, read retries, circuit breaker on synchronous HTTP | `libs/resilience`, cart to catalog, `packages/api-client` ([ADR 0018](docs/adr/0018-http-resilience.md)) | Stop catalog and add a product to the cart |

**Timeouts, retries and the breaker.** Every synchronous call has a timeout, and only idempotent reads are retried (once, with jittered backoff, never after a read timeout or a `503` with `Retry-After`). [ADR 0018](docs/adr/0018-http-resilience.md) lists every call with its timeout and policy. Only cart to catalog has a circuit breaker (5 consecutive failures open it for 10 s, then one probe). The breaker lives in each cart process, so two cart replicas open independently. While it is open, adding a new product answers `503` Problem Details with `Retry-After` immediately.

**What keeps working with catalog down.** Viewing the cart, removing a line, clearing it and changing the quantity of a line that is already in the cart never call catalog: they use Redis and the projection fed by `catalog.events`. Changing a quantity does not recheck the price, on purpose: the price is checked atomically when the stock is reserved (`UPDATE ... WHERE price = :expected AND stock >= :qty`, [ADR 0013](docs/adr/0013-stock-reservations.md)), so an order at a price that changed is cancelled with `price_changed` and nothing is charged. The store search shows "not available right now" with a Try again link, and the product page and the other pages that need catalog show their own message.

**Dead letters.** Malformed messages, unsupported versions and handlers that keep failing go to `<topic>.dlq` with a safe error summary (never payload values). `make dlq-inspect` and `make dlq-replay` look at them and publish them again to the original topic, once per original message even when several consumer groups dead-lettered it. See [Dead letters](#dead-letters).

### Failure scenarios and how to run them

Both exist as integration tests (Testcontainers, part of `make test-backend`) and as a script against the running stack.

| Scenario | Expected result | Test | Script |
| --- | --- | --- | --- |
| Payments stopped during a purchase | The order is accepted, the stock is reserved and the order waits. After the saga timeout it is `CANCELLED` with `saga_timeout` and the stock is back. When payments returns, the queued charge is made and refunded at once (one payment row, one `payment.succeeded`, one `payment.refunded`), the order stays cancelled and new orders are confirmed | `backend/tests/e2e/test_payments_outage.py` | `make check-failure-scenarios SCENARIO=payments` |
| Kafka stopped and started | Orders and registrations are accepted (HTTP writes only need their own database), their events wait in the outbox, the order stays `PENDING`. After the restart the relays publish, the saga completes and every effect happens once. A repeated idempotency key still buys once | `backend/tests/e2e/test_kafka_outage.py` | `make check-failure-scenarios SCENARIO=kafka` |
| A malformed message in any topic | It lands in that topic's `.dlq` and the partition is not blocked | `backend/tests/test_malformed_messages_per_topic.py` | `make check-dead-letters` |
| Catalog stopped | Adding to the cart fails fast with `503` once the breaker is open; the cart page still loads | `backend/services/cart/tests/integration/test_catalog_outage.py` | stop catalog and `PUT /api/v1/cart/items/{sku}` |

`make check-failure-scenarios` runs both scenarios (about 4 minutes, it stops and starts `payments`, `payments-worker` and `kafka` and restarts them when it ends, deleting nothing). Use `SCENARIO=payments` or `SCENARIO=kafka` for one. It creates a product `SCEN-<timestamp>-...` for each run and a user `scenario-<timestamp>@example.com`. Keep a Kafka outage shorter than `ORDERS_SAGA_TIMEOUT_SECONDS`: the sweeper cancels orders that stayed `PENDING` longer than that, whatever the cause (`KAFKA_OUTAGE_SECONDS`, 15 by default, sets how long the script waits).

The integration tests wait with bounded polling only and were run three times in a row with the CPUs saturated. After a Kafka restart the services reconnect by themselves; consumers continue from their committed offsets.

### Guards that keep this honest

- `make test-backend` fails when any lib or service is below 85% (`scripts/check_package_coverage.py`, on top of the global 85%). Frontend packages inherit the 85% Jest threshold from `@ecommerce/config`.
- `make check-not-found-csp` fetches an unknown store URL through the running gateway and fails on any `<style>` or inline `<script>` without the nonce of the Content-Security-Policy.
- The frontend Make targets stop with a clear message when the active Node major differs from `frontend/.nvmrc`.
- The frontend Docker images prepare the pinned pnpm in its own layer with up to 5 attempts, and retry `pnpm install` up to 3 times.

## Dead letters

A message that cannot be processed goes to `<topic>.dlq` and the partition keeps moving. That covers anything that is not a valid event envelope, an unsupported event version, a payload that does not match its contract, and a handler that still fails after its retries (3 attempts with exponential backoff). The original key and value are kept so the message can be replayed.

Logs and dead letter headers never carry payload values. A log line has the event id and type (when the envelope could be read), the error type, the topic, partition and offset. The `x-error` header is a safe summary: for a contract violation it lists the field paths and error codes (`2 validation errors: payload.email: string_type; event_version: int_parsing`), and for any other exception only its type. The other headers are `x-error-type`, `x-attempts`, `x-original-topic`, `x-original-partition`, `x-original-offset` and `x-consumer-group`.

| Command | What it does |
| --- | --- |
| `make dlq-inspect TOPIC=orders.events.dlq` | One JSON object per dead letter: partition, offset, key, event id and type, origin, group, error type, safe summary, attempts. Add `SHOW_PAYLOAD=1` to include the raw value (base64), which may hold personal data |
| `make dlq-replay TOPIC=orders.events.dlq OFFSETS="0:12 3:4"` | Publish those dead letters (`PARTITION:OFFSET`, as printed by inspect) again to the original topic |
| `make dlq-replay TOPIC=orders.events.dlq ALL=1` | Replay every dead letter of the topic. `DRY_RUN=1` shows what would be replayed without publishing |
| `make check-dead-letters` | Produce one malformed message into every topic and wait until each `.dlq` has it (needs the stack running) |

A message that several consumer groups could not process (a malformed message on `orders.events` is dead-lettered by catalog, payments and cart separately) has one dead letter per group. Replay deduplicates by `(x-original-topic, x-original-partition, x-original-offset)`, publishes each original message once, and prints the count (`6 dead letters, 4 duplicates skipped`) and, for every message, the groups that failed it.

Replaying is safe to repeat: the replayed message keeps its event id, so every consumer skips what it already applied, and the original dead letter stays in the topic (Kafka does not delete). A replay is all or nothing: if one selected message has no usable `x-original-topic` header, or names a topic other than the one its dead letter topic belongs to, nothing is published. A message that is still malformed simply lands in the dead letter topic again, so fix the cause (a deploy, a missing row) before replaying. The commands run the `ecommerce_messaging.dlq_cli` module inside the `orders-worker` image, so they use the stack's Kafka and need no local Python setup.

## Commands

| Command | Description |
| --- | --- |
| `make up` | Start the stack and wait until it is healthy |
| `make down` | Stop the stack |
| `make logs SERVICE=kafka` | Follow logs, optionally for one service |
| `make ps` | List containers and their health |
| `make seed COUNT=200000` | Load synthetic products into the catalog (idempotent) |
| `make dev-token` | Log in through the gateway and print an access token (`ROLE=customer` for a customer) |
| `make test-backend` | Backend tests with coverage (integration tests need Docker) |
| `make test-backend-unit` | Backend tests without Docker |
| `make lint-backend` | Ruff, format check and mypy |
| `make check-comments` | Fail if backend Python or frontend TypeScript code contains comments or docstrings (tool pragmas are allowed). Needs `make install-frontend` first |
| `make test-scripts` | Tests of the comment checker, including the real TypeScript cases |
| `make install-frontend` | `pnpm install --frozen-lockfile` |
| `make lint-frontend`, `make lint` | ESLint and typecheck of the frontend, or of both stacks |
| `make test-frontend`, `make test` | Frontend tests with coverage, or backend and frontend |
| `make storybook`, `make test-storybook` | Run Storybook; build it and run axe on every story |
| `make openapi`, `make check-openapi` | Regenerate the OpenAPI documents and API types, or fail when they are stale |
| `make check-routes` | Prove the gateway routes against the running stack |
| `make check-failure-scenarios [SCENARIO=payments\|kafka]`, `make check-not-found-csp` | Prove the payments and Kafka outage scenarios against the running stack, and the store 404 page against the CSP nonce (see Resilience) |
| `make dlq-inspect`, `make dlq-replay`, `make check-dead-letters` | Inspect and replay dead letters, and prove every topic has a working dead letter path (see Dead letters) |
| `make check-rate-limit` | Prove the rate limit buckets and the forwarded header trust (isolated stack, needs Docker) |

## Repository layout

```text
backend/    Python monorepo (uv workspaces): services, libs
frontend/   Next.js monorepo (pnpm and Turborepo): apps, packages
infra/      Gateway, database init, Kafka and object storage bootstrap
docs/       Architecture decision records and diagrams
```

## Assumptions and decisions

To be completed. Architecture decisions are recorded in [`docs/adr`](docs/adr).
