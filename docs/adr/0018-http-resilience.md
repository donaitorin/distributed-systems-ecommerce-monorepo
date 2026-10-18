# 0018. Synchronous HTTP resilience: timeouts, read retries and the catalog circuit breaker

Status: accepted (2026-10-17)

## Context

Almost everything between services goes through Kafka (ADR 0004, 0014). The synchronous HTTP that remains is small: the cart asks catalog for a product (ADR 0012), every service fetches the signing keys of auth, and the two Next servers talk to the gateway. The spec asks for timeouts and a circuit breaker on these calls, with tenacity. A catalog that is down or hanging must not make the cart slow, and a cart that already exists must keep working.

## Decision

### Rules

1. Every call has a timeout. A call without one is a bug.
2. Only idempotent reads are retried: at most one retry, with exponential backoff and jitter, and only for failures that are likely to disappear on their own (a refused or reset connection, a connect timeout, `502`, `503`, `504`). A read timeout is not retried, because it would double the wait of the caller. A `503` that carries `Retry-After` is not retried either: the server already said when to come back. Writes (`POST`, `PUT`, `PATCH`, `DELETE`) are never retried; the retry helpers only exist for reads.
3. The cart to catalog call also has a circuit breaker. Other calls have a natural fallback (cached signing keys) or are user-initiated writes, so a breaker would add state without adding safety.

### The breaker (`libs/resilience`)

`CircuitBreaker` is a small state machine, one instance per client, no framework imports:

```text
closed ──(failure_threshold consecutive failures)──► open
open ──(open_seconds elapsed)──► half-open
half-open ──(half_open_probes probes succeed)──► closed
half-open ──(any probe fails)──► open (a full new open period)
```

- Configurable per client: `failure_threshold` (default 5), `open_seconds` (10), `half_open_probes` (1). Half-open lets at most `half_open_probes` calls through at the same time; the others are rejected like in open.
- A rejected call raises `CircuitOpenError` with the time left, without touching the network.
- The caller decides what counts as a failure. For the cart: transport errors, `5xx`, `429` and a body that is not a product. A `404` (no such product) and other `4xx` are healthy answers of a healthy service and reset the count. A cancelled call frees its half-open slot and counts as nothing.
- `BreakerListener` has two hooks, `state_changed(name, previous, current)` and `call_finished(name, outcome)` with `success`, `failure` or `rejected`. The cart installs `LoggingListener`, which logs transitions. E15 can implement the same protocol to export counters and a state gauge without touching the breaker.
- Time comes from an injectable monotonic clock, so every transition is unit tested without sleeping.

One logical call is one count: the retry runs inside the breaker, so a call that used its retry and failed counts once.

### Cart to catalog

- `HttpCatalogGateway.get` is `breaker.call(retry(GET))`. Per attempt timeout `CATALOG_TIMEOUT_SECONDS` (2 s). Settings: `CATALOG_BREAKER_FAILURE_THRESHOLD`, `CATALOG_BREAKER_OPEN_SECONDS`, `CATALOG_BREAKER_HALF_OPEN_PROBES`, `CATALOG_RETRY_ATTEMPTS` (2), `CATALOG_RETRY_INITIAL_DELAY_SECONDS` (0.1), `CATALOG_RETRY_MAX_DELAY_SECONDS` (0.5). Invalid values stop the service at startup.
- While the circuit is open the API answers `503` Problem Details with `code: "catalog_unavailable"` and `Retry-After` set to the seconds left, immediately. A failure before it opens gives the same problem with `Retry-After: 2`.
- Reading the cart, changing the quantity of a line that is already in the cart, removing a line and clearing never call catalog (they use Redis and the projection fed by `catalog.events`), so they keep working. Only adding a product that is not in the cart, and accepting a new price, need catalog.
- `/ready` still depends only on Redis (the architecture rule): an open circuit does not make the cart unready.

### Next servers to the gateway (`packages/api-client`)

- Reads (`GET`) have a 5 s timeout and writes 10 s by default; callers can override them (`timeoutMs`).
- `GET` is retried once after a network error (but not a timeout), `502`, `503` or `504` without `Retry-After`, with a delay of half to all of `min(500 ms, 100 ms * 2^n)`. The policy is a client option (`readRetry`); methods other than `GET` always make one attempt.
- The browser to Next calls that had no timeout now have one (see the table).
- The store search shows "The product search is not available right now" for a network error, `502`, `503` or `504` (the gateway answers `502` with a plain text body when catalog is down) and offers a Try again link to the same search.

## Audit of synchronous HTTP calls

| Caller | Callee | Timeout | Retry | Breaker |
| --- | --- | --- | --- | --- |
| cart | catalog `GET /api/v1/products/{sku}` | 2 s per attempt | 1 retry (connect errors, 502/503/504), jittered 0.1 to 0.5 s | Yes: 5 failures, 10 s open, 1 probe |
| every service | auth `GET` JWKS | `JwtSettings.request_timeout_seconds`, 3 s | None; keys are cached for 5 min and kept when a refresh fails, and a refresh is attempted at most once per cooldown | No (the cache and the cooldown play that role) |
| catalog | object storage (S3 API) | connect 3 s, read 15 s | botocore standard mode, 2 attempts in total | No |
| payments | payment provider | The provider is simulated and makes no network call; a real adapter must add a timeout and no retry on charges (idempotent by `order_id`) | n/a | n/a |
| store server | gateway, through `api-client` | reads 5 s, writes 10 s | `GET` once, jittered; writes never | No |
| backoffice server | gateway, through `api-client` | reads 5 s, writes 10 s | `GET` once, jittered; writes never | No |
| `packages/auth` (both apps) | gateway `/auth/*` (`POST`) | `AUTH_REQUEST_TIMEOUT_MS`, 5 s | None (writes) | No |
| `packages/auth` (both apps) | gateway JWKS (jose) | `AUTH_REQUEST_TIMEOUT_MS`, 5 s | Cached 10 min, 30 s cooldown | No |
| backoffice server | gateway image upload (streamed) | 60 s | None (write) | No |
| backoffice server | gateway CSV import upload (streamed) | 15 min | None (write) | No |
| backoffice server | gateway `problems.csv` (`downloadProblemsCsv`, raw `fetch`) | 60 s (had none) | None | No |
| store browser | store server `/api/orders/{id}` (`order-client.ts`) | 10 s (had none) | None; the order page polls again | No |
| backoffice browser | backoffice server import reads (`import-client.ts`) | 15 s (had none) | None; the page polls again | No |
| backoffice browser | backoffice server import upload | 15 min (had none) | None (write) | No |
| backoffice browser | backoffice server image upload (`upload-client.ts`) | 90 s (had none) | None (write) | No |

Kafka clients have their own settings (publish timeout 15 s, outbox and consumer backoff, ADR 0004) and are not HTTP.

## Consequences

- Catalog down: the first failures cost at most one retry (a refused connection fails in milliseconds), then adding answers instantly for the open period, and the store keeps showing existing carts. When catalog returns, the first add after the open period closes the circuit.
- The breaker lives in each cart instance, so two replicas open independently. That is acceptable at this scale; sharing the state in Redis would add a dependency to every call.
- A product that exists only in catalog (never viewed through the projection) cannot be added during an outage. That is the cost of not caching reads of products that were never requested.
- The retry and breaker code is generic and lives in a lib, but it holds no business rule: what counts as a failure is decided by the caller.
