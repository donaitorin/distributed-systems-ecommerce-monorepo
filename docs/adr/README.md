# Architecture decision records

Each record has a context, the decision, the alternatives that were considered and the consequences. Where the text says "E8", "E14" and so on, those are the build stages of the project plan (E0 to E16, a local working note that is not in the repository); the records name them only to say when something was added. The [README](../../README.md) summarises the decisions and links the records.

| ADR | Decision |
| --- | --- |
| [0001](0001-object-storage-seaweedfs.md) | Object storage: SeaweedFS behind an S3 port |
| [0002](0002-catalog-search-and-keyset-pagination.md) | Catalog search: PostgreSQL full text with trigram fallback and keyset pagination |
| [0003](0003-product-images.md) | Product images: validated uploads, WebP renditions and storage that never blocks readiness |
| [0004](0004-csv-import-and-messaging-core.md) | CSV import: asynchronous validation, explicit confirmation and a reusable messaging core |
| [0005](0005-auth-tokens-and-signing-keys.md) | Auth: short-lived RS256 tokens, rotating refresh tokens and file-based signing keys |
| [0006](0006-accounts-profile-consistency.md) | Accounts: an eventually consistent profile ordered by timestamps |
| [0007](0007-frontend-zones-session-and-csp.md) | Frontend: Multi-Zones, cookie sessions and a strict nonce-based CSP |
| [0008](0008-gateway-forwarded-headers-and-rate-limits.md) | Gateway: trusted forwarded headers and per-client rate limits |
| [0009](0009-backoffice-data-access-and-uploads.md) | Backoffice: server-side data access, streaming uploads and URL state |
| [0010](0010-store-catalog-search-and-product-pages.md) | Store: catalog search, product pages and shared search logic |
| [0011](0011-consumers-that-skip-the-claim.md) | Consumers that skip the claim |
| [0012](0012-cart-service.md) | Cart service: Redis storage, a bounded product projection and accepted prices |
| [0013](0013-stock-reservations.md) | Stock reservations: all or nothing, replay safe and cancellation safe |
| [0014](0014-orders-saga-and-idempotency.md) | Orders: the saga state machine, idempotency keys and the timeout sweeper |
| [0015](0015-payments-provider-port-and-stripe.md) | Payments: a provider port, late results, refunds and how Stripe would plug in |
| [0016](0016-store-checkout-and-order-tracking.md) | Store: checkout, retried attempts and order tracking |
| [0017](0017-order-views-and-customer-email-snapshot.md) | Order views: the customer email snapshot, the order history and the backoffice orders |
| [0018](0018-http-resilience.md) | Synchronous HTTP resilience: timeouts, read retries and the catalog circuit breaker |
| [0019](0019-failure-scenarios-and-quality-gates.md) | Failure scenarios and the quality gates that protect them |
| [0020](0020-operational-notes-and-known-limitations.md) | Operational notes and known limitations |
