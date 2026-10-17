# 0011. Consumers that skip the claim

Status: accepted (2026-10-16)

## Context

`EventConsumer` (ADR 0004) makes every handler safe against redelivery by claiming the event id in a `processed_events` table of the service's own PostgreSQL database. A claim is either taken in the same transaction as the handler's effect (`transactional_handler`) or recorded after a standalone effect (`standalone_handler`). Both need a database session.

The cart service has no PostgreSQL. Its only store is `redis-cart`, and the handler that consumes `catalog.events` updates a Redis hash. Adding a Postgres database just to remember event ids would break the rule that a service starts with only its own infrastructure, and a claim kept in Redis would have to be written atomically with the effect, which brings a second kind of claim store for one consumer.

## Decision

- `ClaimMode.NONE` and `idempotent_handler(event_type, version, payload, callback)` register a handler that runs without a claim. `EventConsumer` takes `session_factory` and `processed_events` as optional arguments; constructing a consumer with a handler that needs a claim and no claim storage raises `ValueError`, so a mistake shows at startup and not on the first message.
- Everything else stays as it was: routing by `(event_type, event_version)`, unknown types skipped, unsupported versions and invalid payloads dead-lettered, retries with backoff, the dead letter topic, offsets committed after the outcome. The existing modes behave exactly as before.
- **A handler may skip the claim only if applying the same event any number of times, in any order relative to other events of the same key, leaves the same state.** In practice that means the event carries a version (or another total order) and the handler applies it with an atomic compare-and-set, "write only if newer than what is stored". A handler that increments, appends, sends or charges is not allowed to skip the claim.
- An event delivered twice is run twice. The second run is a no-op because its version is not newer. This also covers out-of-order delivery and replays from the start of the topic, which a processed-events table does not: an older event that was never seen before would be applied by a claim-based consumer, and would overwrite newer state.

## Why the cart can

`product.updated` and `product.deleted` carry the product `version`, which grows with every change in catalog. The cart keeps a projection per SKU and applies an event with a Lua script that compares the version and writes in one step (ADR 0012). The script is the idempotency mechanism, so a claim would be redundant and could even be wrong: a claim recorded for an event that was only partly applied would hide it forever.

## Consequences

- A handler that skips the claim has to be tested for replay and for reordering, not only for the happy path. The cart has integration tests that do both against real Redis and Kafka.
- If the handler keeps failing (Redis down) the event is retried and then dead-lettered, like any other. Consumers of this kind should use a patient `RetryPolicy` so a short restart of their store does not send events to the dead letter topic.
- Services with PostgreSQL keep using the claim modes. Skipping the claim is a property of the handler, not a shortcut for convenience.
