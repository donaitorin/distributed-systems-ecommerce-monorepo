# 0020. Operational notes and known limitations

Status: accepted (2026-10-17)

## Context

Delivering a project means saying what it does not do and which local quirks a person running it will meet. These items are known, accepted and, where a mitigation exists, written down here. They are grouped by where they bite. The README links this record from its "Known limitations" section.

## Running it

- **`BUILDX_NO_DEFAULT_ATTESTATIONS=1`.** BuildKit adds provenance and SBOM attestations by default, which change the manifest of every build, so the image id changes even when nothing changed and `docker compose up` recreates every container on every run. Compose 2.38 has no `build.provenance` or `build.sbom` key, so the switch is the environment variable, exported by the Makefile and present in `.env.example` (Compose forwards `.env` to the builder). Without it everything still works; containers are only recreated needlessly. A newer Compose may accept `provenance: false` and `sbom: false` in the file: re-test and drop the variable if it validates.
- **The `frontend` network and its subnet.** The network has the fixed subnet `10.250.10.0/28`, the store at `.2`, the backoffice at `.3` and an `ip_range` (`10.250.10.8/29`) for containers without a fixed address (ADR 0008). A stack created before the `ip_range` existed must be recreated once with `docker compose down` (never `-v`, the volumes keep the data) because Docker cannot change the ranges of an existing network.
- **VPN collisions.** Some VPNs and other Docker networks use `10.250.x.x`. If `make up` fails with a pool overlap, pick another `/28` and change the three files that name it together: `docker-compose.yml` (the `subnet`, the `ip_range` and the `ipv4_address` of the store and the backoffice), `infra/gateway/traefik.yml` (`trustedIPs`) and `infra/gateway/dynamic/auth.yml` (the `ClientIP` rules and the `excludedIPs`). One command does it, for example for `10.250.40.0/28` (on macOS use `sed -i ''`): `sed -i 's/10\.250\.10\./10.250.40./g' docker-compose.yml infra/gateway/traefik.yml infra/gateway/dynamic/auth.yml`. The same fixed subnet means two stacks cannot run side by side, so a disposable stack needs this change in its own copy of the repository, plus `COMPOSE_PROJECT_NAME`, a `.env` with other ports (the project name alone does not separate host ports) and, for the checks that start their own stack, nothing else: `make check-rate-limit` uses its own project name.
- **Node, Corepack and pnpm.** The frontend needs the Node version in `.nvmrc`. There is one at the root and one in `frontend/`, and the Node guard (`scripts/check_node_version.py`, run by the frontend Make targets) fails if they differ or if the active Node major differs from them. pnpm is pinned by `packageManager` in `frontend/package.json` and started by Corepack; the Corepack of an older Node cannot run that pnpm and fails with "Cannot find module pnpm.cjs", which is what the guard replaces with a message. The Docker images prepare the pinned pnpm in its own layer with retries.
- **Users without a registration event.** Accounts created before the outbox existed (the first admin and the `ada@example.com` account of the early examples) have no `user.registered` event on `auth.events`. This only affects databases created at that point: accounts creates a missing profile on the first authenticated `/me` request (ADR 0006), and the admin seeded by a fresh stack publishes its event.

## Behaviour under failure

- **A Kafka outage longer than the saga timeout cancels pending orders.** Orders and registrations are accepted while Kafka is down and their events wait in the outbox, but the sweeper cancels every order that stayed `PENDING` or `STOCK_RESERVED` longer than `ORDERS_SAGA_TIMEOUT_SECONDS` (60), whatever the cause (ADR 0014, 0019). Raising the timeout or pausing the sweeper while the outbox is backed up are possible changes, neither built.
- **After a payments outage a cancelled order is charged, then refunded.** The queued `order.payment_requested` is consumed when payments returns, the simulated provider approves, and `order.cancelled`, which follows on the same partition, triggers the refund. The result is one payment row, one `payment.succeeded` and one `payment.refunded`, and the order stays cancelled. The alternative is an `expires_at` on `order.payment_requested` so payments never charges a stale request (ADR 0015). Not built: the refund path is proven, and the field belongs to a contract used by three services.
- **The circuit breaker is per cart instance.** Two cart replicas open and close independently (ADR 0018). A shared state in Redis would add a dependency to every catalog call.
- **Adding to the cart is read-then-write.** The store's server action reads the quantity in the cart and sets the new total, and the service reads the line and then writes it. The 100-line limit is enforced atomically in a Lua script, but two simultaneous adds of the same product can lose one, and a removal between the read and the write can bring the line back. Closing it needs an atomic increment in the cart script. The interface disables the button while a request is in flight, which covers the double click.
- **Image keys are recovered from URLs.** Catalog's product endpoint returns URLs, so the cart derives the object key from `image_url`; catalog and cart must be configured with the same `MEDIA_PUBLIC_BASE_URL` (ADR 0012). Events carry the key and are not affected.
- **Rate limits are per gateway instance**, and Docker Desktop makes every local client look like one address (ADR 0008).
- **No retention jobs** for processed events, imports and their source files, orphaned product images and expired refresh tokens (ADR 0003, 0004, 0005, 0013).

## Frontend

- **The CSP nonce makes every page dynamic.** A nonce is unique per response, so no page can be prerendered or cached as HTML (ADR 0007).
- **The refresh-token deduplication is per Next.js process.** With several replicas of a zone two requests of one session can still race and sign the session out; a shared store for the rotated pair is the fix (ADR 0007).
- **The Storybook test runner is deprecated** and kept on purpose because it runs axe on every story. The migration path is the Storybook Vitest addon with the accessibility addon in browser mode: stories and `play` functions stay, only the runner and its axe configuration change (ADR 0007).
- **MSW is not used.** The specification names it, but every API call is made by a Next.js server, so the tests mock `fetch` at that boundary and the project avoids one dependency (ADR 0009).
- **Accessibility is only checked by tools** (axe in tests and stories, a contrast test, Radix keyboard behaviour). A manual screen-reader pass over the purchase flow was not performed.

## Not built

OpenTelemetry (the build stage was skipped; logs are JSON with a request id and a correlation id), dashboards, a shared breaker, a real Stripe adapter, the `expires_at` guard, publishing images to GitHub Container Registry, Kubernetes manifests, Terraform, a Lambda, Playwright tests, a load test. The README lists them as future work.

## Consequences

- None of these items changes the guarantees the project claims; each is either a documented limit of a mitigation that exists or a feature outside the scope of the delivery.
- A reader who hits one of the operational items has the exact files and commands to change.
