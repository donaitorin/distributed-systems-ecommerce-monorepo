# 0019. Failure scenarios and the quality gates that protect them

Status: accepted (2026-10-17)

## Context

E14 adds retries, dead letters and a circuit breaker (ADR 0004, 0018). Each of them is only worth something if the failures they answer are reproduced end to end and if a later change cannot quietly weaken the checks. This record fixes what the scenarios assert and which gates run in CI.

## Decision

### Scenarios

Two outages are proven end to end with the real workers, relays, outbox tables and a real Kafka broker (Testcontainers), and again as a script against the running stack.

- **Payments stopped.** The order is accepted (HTTP does not depend on payments), the stock is reserved, and the order waits in `STOCK_RESERVED`. The saga sweeper cancels it with `saga_timeout` and the stock returns. When payments starts again it consumes the queued `order.payment_requested`, charges and then, because `order.cancelled` follows on the same partition, refunds. The assertion is "one payment row, one `payment.succeeded`, one `payment.refunded`, the order stays cancelled, no `CONFIRMED` in its history", which is what "not charged twice" means for an at least once pipeline. New orders are confirmed.
- **Kafka stopped.** The broker container is stopped and started again (same data, same port), so committed offsets survive. Orders and registrations are accepted and their events wait in the outbox. After the restart the saga completes and every effect (stock taken, payment row, status history) happens once, even though the relay may publish an event twice. The published copies are not asserted to be one: the guarantee is at least once delivery plus idempotent consumers.
- The Kafka scenario uses a saga timeout longer than the outage. The sweeper cancels `PENDING` orders older than the timeout whatever the cause, so an outage longer than `ORDERS_SAGA_TIMEOUT_SECONDS` (60 s) cancels the orders that were waiting. That is intended: an order that could not progress in a minute should not hang for ever.

Tests wait with bounded polling only (`eventually`, `asyncio.timeout`, `for` loops with a limit) and are run repeatedly under CPU load before a change is accepted.

### Gates

- **Coverage per lib and service.** `pytest-cov` enforces 85% over the whole backend; `scripts/check_package_coverage.py` reads `coverage.xml` and fails when any lib or service is below 85%, using the same statements plus branches formula as coverage.py. It runs inside `make test-backend`, so CI and local runs agree. Frontend packages inherit the 85% threshold from the shared Jest preset.
- **Testcontainers in CI.** The backend job runs the plain `pytest` (the `-m "not integration"` filter exists only in `make test-backend-unit`), checks that Docker answers before the tests, and no test is skipped for lack of Docker: a missing Docker makes the integration suites fail.
- **Node version.** Frontend Make targets run `scripts/check_node_version.py` first: when the active Node major differs from `frontend/.nvmrc` they stop with a message instead of the corepack error of a pnpm that cannot start.
- **Docker builds.** The pinned pnpm is prepared in its own layer, up to five attempts, then `pnpm install` is retried up to three times with the fetch retries of pnpm raised. The pinned version is unchanged.
- **CSP on 404.** The store has a root `not-found` page like the backoffice (ADR 0017), because Next's default page carries an inline `<style>` the nonce policy blocks. `make check-not-found-csp` checks the running gateway.

## Consequences

- The e2e modules start their own Kafka, Postgres databases and Redis, so each costs about 15 seconds of set-up; they add roughly 90 seconds to `make test-backend`.
- The scripted scenarios stop and start `payments`, `payments-worker` and `kafka` of the local stack and leave test data (`SCEN-*` products, a `scenario-*` user). They are for a developer machine, not for CI.
- The per-package check depends on how coverage.py names files (`<dir>/src/ecommerce_<lib>/...` for libs); its unit tests cover that mapping.
