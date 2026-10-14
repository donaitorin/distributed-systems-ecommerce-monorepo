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

## Commands

| Command | Description |
| --- | --- |
| `make up` | Start the stack and wait until it is healthy |
| `make down` | Stop the stack |
| `make logs SERVICE=kafka` | Follow logs, optionally for one service |
| `make ps` | List containers and their health |

## Repository layout

```text
backend/    Python monorepo (uv workspaces): services, libs
frontend/   Next.js monorepo (pnpm and Turborepo): apps, packages
infra/      Gateway, database init, Kafka and object storage bootstrap
docs/       Architecture decision records and diagrams
```

## Assumptions and decisions

To be completed. Architecture decisions are recorded in [`docs/adr`](docs/adr).
