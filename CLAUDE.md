# CLAUDE.md

E-commerce code challenge built as event-driven microservices. The working specification and the build stages are local planning notes in `.planning/spec.md` and `.planning/stages.md` (not versioned); read the relevant section before starting a stage. Final decisions are recorded in `docs/adr/` and the README.

## How we work

- Work on one stage at a time, only what that stage's scope describes. Never start the next stage on your own.
- If a stage is too large for one pass, propose a split before writing code.
- Do not run `git commit`, `git push` or create branches. The developer commits manually.
- When a stage is done, stop and report: what was built, how to verify it (exact commands), and a suggested split of the changes into commits using Conventional Commits.
- When a decision is not covered by the spec, ask instead of assuming. If you must assume, say so in your report.
- Prefer the simplest solution that satisfies the spec. Do not add dependencies the spec does not mention without asking.

## Repository layout

```
backend/    Python monorepo (uv workspaces): services/*, libs/*
frontend/   Next.js monorepo (pnpm + Turborepo): apps/store, apps/backoffice, packages/*
infra/      gateway (Traefik), postgres init, k8s and terraform (extras)
docs/       spec, stages, ADRs, diagrams
```

## Architecture rules

- Services: auth, accounts, catalog, cart, orders, payments. Each owns its data.
- Each service has its own PostgreSQL database and user. Never read or write another service's database.
- Cross-service workflows go through Kafka. Synchronous HTTP between services is limited to cart -> catalog, always with timeout and circuit breaker.
- A service must start and pass `/ready` with only its own infrastructure up (its database, Kafka, Redis). Never depend on another service being up.
- Events use the shared envelope in `libs/contracts`, are published through the transactional outbox, and are consumed idempotently.
- Event changes are backward compatible: add optional fields only. Breaking changes ship as a new versioned event.
- `libs/` holds technical infrastructure only (messaging, auth validation, storage, observability, contracts). No business logic in libs.
- Files go through the `ObjectStorage` port (SeaweedFS locally, S3 compatible). Store object keys in the database, never full URLs.

## Code rules

- English everywhere: code, identifiers, README, commit messages.
- No code comments or docstrings. Make the code self-explanatory through naming and small functions. Tool pragmas such as `# noqa` or `# type: ignore` are allowed only when unavoidable.
- Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, aiokafka. Full type hints; mypy strict must pass.
- Layers per service: `api`, `application`, `domain`, `infra`. `domain` has no framework imports.
- Money is `Decimal` in Python and `NUMERIC(12,2)` in PostgreSQL. Never float.
- Queries are always parameterized. Never build SQL with string formatting.
- Errors follow RFC 9457 Problem Details. Lists use cursor pagination.
- Frontend: TypeScript strict, App Router, Tailwind, Radix UI for interactive primitives, TanStack Query, React Hook Form with Zod.
- Search and filter state lives in URL query params (`nuqs`), so back and forward navigation restore it.
- Mobile first, WCAG 2.2 AA: semantic HTML, keyboard support, visible focus, labeled inputs, sufficient contrast, status never conveyed by color alone.

## Testing rules

- Every change ships with unit tests in the same stage.
- Backend: pytest with pytest-cov, coverage threshold 85%. Integration tests use Testcontainers.
- Frontend: Jest with React Testing Library and jest-axe. Every visual component has a Storybook story covering its states (default, loading, empty, error, disabled when relevant).
- Never weaken or delete a test to make it pass. If a test is wrong, explain why before changing it.

## Commands

Available once the corresponding stage is done.

```
make up                 start the full stack with docker compose
make down               stop the stack
make test               run backend and frontend tests with coverage
make test-backend       backend tests with coverage report
make test-frontend      frontend tests with coverage report
make lint               ruff, mypy, eslint and typecheck
make storybook          run Storybook
make check-comments     fail if code comments are present
```
