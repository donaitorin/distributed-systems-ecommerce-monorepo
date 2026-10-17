# 0013. Stock reservations: all or nothing, replay safe and cancellation safe

Status: accepted (2026-10-17)

## Context

The checkout saga (orders orchestrates it over Kafka) needs catalog to take stock for a whole order or for nothing, to give it back when the order is cancelled, and to survive everything Kafka does: duplicates, replays and, because orders and catalog are separate consumers of separate topics, a cancellation that is processed before the order it cancels. Two orders racing for the last unit must sell it once, and stock must never go negative.

## Decision

### Storage

- `stock_reservations(order_id PRIMARY KEY, status, failure_reason, created_at, updated_at)` with `status` in `RESERVED`, `FAILED`, `RELEASED`, and `stock_reservation_lines(order_id, sku, quantity)` for what was taken. The primary key is the "order_id unique" rule: one row per order, forever.
- Every successful change of stock bumps `products.version` and emits `product.updated` (or `product.deleted` when a release returns stock to a retired product, so carts do not resurrect it) in the same transaction, through the outbox. Carts therefore see the new stock with the normal version rule.

### Reserve (`order.created`)

1. `INSERT INTO stock_reservations ... ON CONFLICT (order_id) DO NOTHING`. If nothing was inserted the order was already handled (replay, concurrent duplicate, or a cancellation that arrived first): do nothing and emit nothing. A concurrent duplicate waits on the unique index until the first transaction ends, then finds the row.
2. For each line, sorted by SKU: `UPDATE products SET stock = stock - :qty, version = version + 1 WHERE sku = :sku AND deleted_at IS NULL AND price = :expected AND stock >= :qty RETURNING ...`. There is no read before the write; the statement is the check. The price is compared as `Decimal` quantized to two places, inside the same statement, so a price change racing the reservation cannot slip through. Locking rows in SKU order means two orders that list the same products in opposite order cannot deadlock.
3. The lines run in a savepoint. If one updates no row, the savepoint is rolled back (earlier lines come back), a read says why (`price_changed` with the current price, `product_unavailable` for unknown or retired, otherwise `insufficient_stock` with the available quantity), the row becomes `FAILED` and `stock.reservation_failed` is written. Otherwise the lines are stored and `stock.reserved` carries the authoritative name and unit price of each line.

A failed order stays failed: a replay finds the row and does not retry, even if the product was restocked meanwhile. Orders has already cancelled it.

### Release (`order.cancelled`)

- `INSERT ... ON CONFLICT DO NOTHING` of a `RELEASED` row. If it inserted, the cancellation arrived before the order: that row is a tombstone, no stock moves and any later `order.created` finds it and does nothing.
- Otherwise a conditional `UPDATE ... WHERE status = 'RESERVED'` moves the reservation to `RELEASED`; only the transition that wins gives the stock back (`stock = stock + qty`, version bump, `product.updated`) and emits `stock.released`. `FAILED`, `RELEASED` and tombstones are no-ops, so a second cancellation changes nothing.

### Consumer and claims

The handlers are registered with `idempotent_handler` (no `processed_events` claim, ADR 0011). This follows the condition of that ADR and not a shortcut: the `stock_reservations` row is the compare-and-set. Applying the same event any number of times, in any order relative to the other event of the same order, leaves the same state, and the claim would not add anything. A claim recorded for an event whose effect was only partly applied would be worse than none. ADR 0011 says services with PostgreSQL keep claiming by default; this is a handler that meets the stated exception. The worker runs a second consumer group, `catalog-orders`, on `orders.events`; `order.confirmed` and `order.payment_requested` on the same topic are skipped as unknown types.

## Consequences and limits

- Reserved stock is not marked as sold when the order is confirmed. Only `order.cancelled` releases, and orders never cancels a confirmed order; the payment refund path leaves the order cancelled, so that release has already happened.
- A dead-lettered `order.created` leaves the order waiting for the saga timeout in orders, which cancels it and publishes `order.cancelled`; catalog then writes a tombstone.
- The reservation tables grow with orders. They are small (a row per order plus its lines) and a retention job belongs with the other retention work (`processed_events`, imports).
- Event payloads have no `occurred_at` based ordering between `order.created` and `order.cancelled`; the tombstone is what makes the order irrelevant.
- Verified with 20 concurrent orders for the last unit (exactly one is sold), 20 concurrent orders for 7 units of 2, concurrent multi-product orders (all or nothing, no deadlock) and a cancellation delivered before its order, on Postgres.
