# Distributed Systems E-commerce

Event-driven e-commerce built as microservices (auth, accounts, catalog, cart, orders, payments) with a Next.js storefront and backoffice. Work in progress: the repository currently contains the base environment only.

## Requirements

- Docker with Compose v2
- GNU Make

## Quick start

```bash
cp .env.example .env
make up
make ps
```

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

One-shot jobs `kafka-init`, `object-storage-init`, `auth-migrate` and `catalog-migrate` create the topics and buckets and apply database migrations, then exit. `auth-migrate` also seeds the initial admin. `auth-worker` and `catalog-worker` relay outbox events to Kafka.

## Services

| Service | Container | Reachable through the gateway |
| --- | --- | --- |
| Auth | `auth` | `/api/v1/auth/*`, and `/auth/docs`, `/auth/health`, `/auth/ready` |
| Catalog | `catalog` | `/api/v1/products`, `/api/v1/categories`, and `/catalog/docs`, `/catalog/health`, `/catalog/ready` |

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

### Importing a CSV

Nothing is written to the catalog until an admin confirms. The file is validated in the background by the `catalog-worker` container, which talks to Kafka; the API itself only needs Postgres and the object store.

```bash
TOKEN=$(make -s dev-token)
curl -s -X POST localhost:8000/api/v1/imports -H "Authorization: Bearer $TOKEN" \
  -F "file=@data/sample-products.csv"                         # 202, status "uploaded"
curl -s localhost:8000/api/v1/imports/<id> -H "Authorization: Bearer $TOKEN"
                                                               # wait for status "validated": counts + first problems
curl -s localhost:8000/api/v1/imports/<id>/problems.csv -H "Authorization: Bearer $TOKEN"
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

Uploading the same file twice returns the existing import (`200`). Rows are upserted by SKU: existing products are updated (and their version bumped only if something changed), soft-deleted ones are restored, and images are never touched. Files are limited by `IMPORT_MAX_BYTES` (50 MB by default). The design, including the reusable messaging library, is in [ADR 0004](docs/adr/0004-csv-import-and-messaging-core.md).

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

## Repository layout

```text
backend/    Python monorepo (uv workspaces): services, libs
frontend/   Next.js monorepo (pnpm and Turborepo): apps, packages
infra/      Gateway, database init, Kafka and object storage bootstrap
docs/       Architecture decision records and diagrams
```

## Assumptions and decisions

To be completed. Architecture decisions are recorded in [`docs/adr`](docs/adr).
