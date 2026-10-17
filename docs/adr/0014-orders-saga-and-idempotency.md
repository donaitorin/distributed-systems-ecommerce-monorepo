# 0014. Orders: the saga state machine, idempotency keys and the timeout sweeper

Status: accepted (2026-10-17)

## Context

Orders is the orchestrator of the checkout saga (reserve stock in catalog, charge in payments, confirm or compensate). Every step is a Kafka message written through the outbox and consumed idempotently. The client must be able to retry `POST /orders` safely, and the full card number must never be stored, logged or published.

## Decision

### State machine

```text
PENDING ─► STOCK_RESERVED ─► PAID ─► CONFIRMED
   │             │  └──────────────────► CONFIRMED   (total 0.00: nothing to pay)
   └──► CANCELLED ◄┘
```

- The table of allowed transitions lives in `orders.domain.status` and is checked before every change. `CONFIRMED` and `CANCELLED` are final.
- A transition is a row lock plus a conditional `UPDATE ... WHERE status = <the status that was read>`, with the `order_status_history` row (`from`, `to`, `reason`, `at`) in the same transaction. A redelivered or late event finds another status and does nothing: no history row, no event.
- `payment.succeeded` writes two history rows in one transaction (`STOCK_RESERVED → PAID`, `PAID → CONFIRMED`) and one `order.confirmed`. `stock.reserved` with a positive total emits `order.payment_requested`; with a zero total it confirms at once.
- A payment that succeeds for an order that is already `CANCELLED` changes nothing. Payments refunds it and publishes `payment.refunded`; orders records `CANCELLED → CANCELLED` with the reason `payment refunded` and sets `refunded_at`, once (`UPDATE ... WHERE refunded_at IS NULL AND status = 'CANCELLED'`). The order detail shows both.
- Every event of an order carries the same `correlation_id` (the request id of the `POST`), stored on the order, so one order can be followed across `orders.events`, `inventory.events` and `payments.events`.

### Consumers without a claim

The five handlers (`stock.reserved`, `stock.reservation_failed`, `payment.succeeded`, `payment.failed`, `payment.refunded`) use `idempotent_handler`, so orders has no `processed_events` table. The conditions of ADR 0011 hold: each handler's effect is a compare-and-set on the order's status (or on `refunded_at`), applying the same event any number of times, in any order relative to the other events of the same order, ends in the same state, and the side effects (history, outbox) are written only by the transition that wins. Tests replay every event, deliver them out of order, and race a payment against the timeout.

### Idempotency-Key

- Required header, 8 to 128 characters of letters, digits, `-`, `_`, `:` and `.`. Scoped to the customer: two customers can use the same key.
- `idempotency_keys(user_id, key)` holds a fingerprint of the request, the order id and the response (`202 {id, status: PENDING}`). The claim is one `INSERT ... ON CONFLICT (user_id, key) DO UPDATE ... WHERE expires_at <= now`: a concurrent duplicate waits on the unique index until the first transaction ends and then reads its row, so 20 simultaneous requests create one order. The claim and the order are in the same transaction; if the order fails the key is not consumed.
- Same key and same fingerprint: the stored response again (`202`, the original `Location`, `Idempotent-Replay: true`), even if the order has moved on. Same key and a different fingerprint: `422` with `code: idempotency_key_reused`. Keys live 24 hours; the first claim after that replaces the row, and the sweeper deletes expired rows.
- The fingerprint is a SHA-256 of the normalized request: lines sorted by SKU, prices as two-decimal strings, the address fields and the last four digits of the card. Formatting differences (line order, `12.5` against `12.50`, spaces in the card number) do not matter.
- **Limit.** The fingerprint holds only the last four digits of the card, so two requests that differ only in the other digits of the number are the same request. This is the price of never storing anything derived from the full number: a hash of it would be easy to brute force.

### The card number

The body carries `payment.card_number` (a `SecretStr`, 12 to 19 digits after removing spaces and hyphens). The API reduces it to `card_last4` in the request model; only that string reaches the application layer, the order row (`CHECK card_last4 ~ '^[0-9]{4}$'`, so the database itself refuses more), the idempotency fingerprint and the events. Validation errors list the field and the rule, never the value. The simulation sends the number because the challenge asks for a card based fake; a real provider flow tokenizes in the browser and only a payment method id reaches the backend (the Stripe design is in the payments ADR).

### Saga timeout

`SagaTimeouts.sweep` runs in every `orders-worker` every `ORDERS_SAGA_SWEEP_INTERVAL_SECONDS` (default 5). In one transaction it selects the ids of orders in `PENDING` or `STOCK_RESERVED` created more than `ORDERS_SAGA_TIMEOUT_SECONDS` ago (default 60) with `FOR UPDATE SKIP LOCKED`, cancels them with the reason `saga_timeout` and writes `order.cancelled`. Two sweepers never take the same row, and the conditional transition makes a collision with a late event harmless: whichever commits first wins and the loser is a no-op. A partial index on the open statuses keeps the query cheap. The timeout is measured from `created_at`, so it bounds the whole saga and not one step.

`order.cancelled` makes catalog release the stock (ADR 0013), which also covers the cancellation that arrives before the reservation.

## Consequences and limits

- A message lost to the dead letter topic leaves its order waiting for the timeout, which compensates. Dead letters are logged without payloads.
- Names of lines are filled when `stock.reserved` arrives, so a pending order shows SKUs only.
- The relay is single active per database (advisory lock) while sweepers are active in every worker; the deployment can scale the worker without changing the guarantees.
- Orders keep an `updated_at` and no version; there is no endpoint that edits an order.
- No retention yet for orders, history or outbox rows beyond the relay's own purge.
