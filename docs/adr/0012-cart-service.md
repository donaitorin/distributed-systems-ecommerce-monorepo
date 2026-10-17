# 0012. Cart service: Redis storage, a bounded product projection and accepted prices

Status: accepted (2026-10-16)

## Context

The cart is volatile, written often and owned by one user. It lives in its own service on `redis-cart` (AOF with `appendfsync everysec`, `noeviction`). It saves a snapshot of each product (price and name) to show the customer, and it must tell the customer when the catalog no longer agrees with the snapshot, without becoming a second source of truth: checkout revalidates against catalog.

## Decision

### Storage

- `cart:{user_id}` is a hash, one field per SKU, whose value is JSON with `name`, `price` (string), `quantity`, `image_key` and `added_at`. The user is the `sub` claim of the token. Lines are listed in the order they were added.
- Every write goes through a Lua script that also sets the TTL (30 days), so the TTL is renewed on every change and never forgotten. Reading does not renew the cart. A script also enforces the limit of 100 different products, because a check followed by a write would let two requests exceed it. Quantity is 1 to 99 per line.
- The image is stored as an object key. The response builds the URL with `build_public_url(MEDIA_PUBLIC_BASE_URL, thumbnail_key(key))`. Catalog's `GET /products/{sku}` only exposes URLs, so the key is recovered from `image_url` with the inverse of the same helper (`image_key_from_full_url`); the rendition suffixes and that helper moved to `libs/storage` so both services share them. If catalog and the cart are configured with different public base URLs the key cannot be recovered and the line shows no image: they must share `MEDIA_PUBLIC_BASE_URL`, as compose does.

### Product projection

- `product:{sku}` is a hash with `version`, `name`, `price`, `stock`, `image_key` and `deleted`, written by the `cart-worker` from `product.updated` and `product.deleted` and by the API when a product is added.
- Writes use one Lua script: apply only if the entry exists and the event version is greater than the stored one. That is the whole idempotency story (ADR 0011): replays, duplicates and reordering are no-ops, and a deletion keeps the last known values so a later update with a higher version restores the product.
- **Bounded by use.** The worker never creates an entry. An entry exists only if a customer added that product to a cart, and it expires 30 days after its last use (a read of a cart renews the entries of its lines, without creating any). Importing 200,000 products therefore produces 200,000 events that find no entry and change nothing, while memory in `redis-cart`, which cannot evict, only grows with the products customers actually put in carts. The alternative, a TTL on entries created for every event, would still let an import write 200,000 keys. The tests publish thousands of events for products in no cart and assert that the key count does not move.
- **Closing the race between the first read and the events.** Adding a product runs `reserve(sku)` first (a placeholder with version 0 and a five minute TTL), then reads catalog, then applies the answer with the same compare-and-set. An event that arrives between the HTTP read and the write finds the placeholder and is kept if it is newer; an older HTTP answer then loses against it. Without the placeholder that event would be dropped as "no entry" and the projection would stay behind with nothing left to correct it. A placeholder alone is not a product: readers ignore it.
- The worker retries 8 times with a backoff of up to 8 seconds (about 30 seconds in total) before dead-lettering, so a restart of Redis does not send events to `catalog.events.dlq`. The group starts at the earliest offset, which is cheap: events for products without an entry are no-ops.

### Flags and accepted prices

- `GET /cart` compares each line with the projection and adds flags, never changing the line: `price_changed` (`old_price`, `new_price`), `unavailable` and `insufficient_stock` (`available`, 0 included). A line without a usable projection has no flags. Subtotal and line totals use the saved prices.
- A change of quantity keeps the snapshot, so it never accepts a new price by accident. The customer accepts explicitly with `PUT /cart/items/{sku}` and `accepted_price` equal to the `new_price` they saw. The service then reads catalog (the authority, not the projection), and if the current price differs it answers `409` with `code: price_changed` and `current_price`; otherwise the line takes the current price, name and image. It is the same optimistic-concurrency idea as `If-Match` on products, expressed in the body because the price is what the customer agreed to.

### Failure behaviour

- Adding a product needs catalog (2 s timeout). If it cannot answer the request fails with `503` and `Retry-After`; the circuit breaker comes in E14. Changing the quantity of a line already in the cart, reading and removing never call catalog.
- A Redis failure is a `503` Problem Details with `Retry-After`. `/ready` checks Redis only; the service does not depend on catalog, Kafka or auth to start.
- The documentation and health routes are published at `/cart-service/...`. A gateway route at `/cart` would shadow the storefront page of the same name (the same trap ADR 0007 notes for `/auth`).

## Known limitations

- **The image key is recovered from a URL.** Catalog's `GET /products/{sku}` only returns image URLs, so the cart derives the key from `image_url` (`image_key_from_full_url`, the inverse of `build_public_url` plus the `-1200.webp` suffix). Both services must therefore be configured with the same `MEDIA_PUBLIC_BASE_URL`; compose does it. If they differ the cart still works but its lines show the placeholder image instead of the photo. Events do not have the problem, they carry the key. Exposing `image_key` in catalog's response would remove the limitation, at the price of a change to catalog's API and its generated clients.

## Consequences

- A product added before the projection existed, or after its entry expired, is seeded from catalog on the next add; lines of carts untouched for 30 days expire together with their entries.
- Subtotals are advisory. A customer can see a stale price for as long as it takes an event to arrive (usually well under a second); checkout (E12) revalidates price and stock.
- E12's stock reservations must emit `product.updated`, or `insufficient_stock` will lag.
