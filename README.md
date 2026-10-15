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

One-shot jobs `kafka-init`, `object-storage-init` and `catalog-migrate` create the topics and buckets and apply database migrations, then exit.

## Services

| Service | Container | Reachable through the gateway |
| --- | --- | --- |
| Catalog | `catalog` | `/api/v1/products`, `/api/v1/categories`, and `/catalog/docs`, `/catalog/health`, `/catalog/ready` |
| Dev auth (temporary, removed when the auth service lands) | `dev-auth` | Internal only: serves the public JWKS that catalog trusts |

`dev-auth` generates an RSA key pair into a Docker volume on first start. Nothing secret is stored in the repository.

## Catalog API

Reads are public. Creating, replacing and deleting products and creating categories need an admin token. Until the auth service exists, `make dev-token` prints one signed by the `dev-auth` container (`ROLE=customer make dev-token` prints a customer token).

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

## Commands

| Command | Description |
| --- | --- |
| `make up` | Start the stack and wait until it is healthy |
| `make down` | Stop the stack |
| `make logs SERVICE=kafka` | Follow logs, optionally for one service |
| `make ps` | List containers and their health |
| `make seed COUNT=200000` | Load synthetic products into the catalog (idempotent) |
| `make dev-token` | Print an admin JWT for the catalog API (temporary, until the auth service) |
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
