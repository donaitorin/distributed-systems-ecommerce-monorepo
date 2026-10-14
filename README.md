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

## Commands

| Command | Description |
| --- | --- |
| `make up` | Start the stack and wait until it is healthy |
| `make down` | Stop the stack |
| `make logs SERVICE=kafka` | Follow logs, optionally for one service |
| `make ps` | List containers and their health |
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
