# 0015. Payments: a provider port, late results, refunds and how Stripe would plug in

Status: accepted (2026-10-17)

## Context

The challenge asks for a simulated payment, not a real one. The design must still make the saga independent of how a provider answers: a real provider may answer at once, decline, or take a long time and call back (a Stripe webhook). Orders must not know which provider is used, and nothing in the system may charge twice or lose a refund when messages repeat or arrive late.

## Decision

### The port

`payments.application.ports.PaymentProvider` has three calls and nothing else:

- `charge(ChargeRequest) -> ChargeOutcome`: `order_id`, `amount`, `currency`, a payment method reference (`card_last4` in the simulation) and an **idempotency key equal to the order id**.
- `status_of(ChargeRequest) -> ChargeOutcome`: asks the provider again about the same charge.
- `refund(RefundRequest) -> None`, with the idempotency key `refund-<order id>`.

A `ChargeOutcome` is `Succeeded`, `Declined(reason)` or `Processing(check_after)`. `Processing` is the case that makes the design honest: the result will arrive later, either because the payments worker asks again after `check_after` (`status_of`) or because the provider calls back. Both paths end in the same function, `PaymentProcessor.apply(order_id, outcome)`, which is a compare-and-set from `PENDING`. The saga never sees the difference: orders only ever receives `payment.succeeded`, `payment.failed` or `payment.refunded`.

### The simulated adapter

`SimulatedPaymentProvider` decides by the last four digits: `0000` is declined (`card_declined`), `9999` is `Processing` forever (no `check_after`, so it is never asked again and stays `PENDING`), `2222` is `Processing` until `PAYMENT_LATE_APPROVAL_DELAY_SECONDS` (default 90, longer than the 60 second saga timeout) and then approves, and every other ending, `1111` included, approves. The delay and the interval at which the worker asks again (`PAYMENTS_SETTLE_INTERVAL_SECONDS`) are configurable so tests use seconds.

### Idempotency and ordering

- `payments.order_id` is unique. `order.payment_requested` inserts with `ON CONFLICT DO NOTHING` and only the delivery that finds the payment not yet submitted calls the provider; if the worker dies between saving and charging, the redelivery charges again with the same idempotency key, which a real provider treats as the same charge.
- Every change is a conditional update from the status that was read, and the event is written in the same transaction (outbox). Repeated deliveries, repeated settlement passes and races between them produce one `payment.succeeded`, one `payment.failed` or one `payment.refunded`.
- The provider is never called inside a database transaction.

### Late success after cancellation

Payments also reads `order.cancelled` and keeps a flag on the payment. If the result arrives while the flag is set, or the cancellation arrives when the payment already succeeded, the payment is refunded: the provider is asked (idempotent), the payment moves `SUCCEEDED → REFUNDED` and `payment.refunded` is published. A periodic pass also looks for `SUCCEEDED` payments of cancelled orders, so a refund that failed (provider down) is retried until it works. Orders ignores the late `payment.succeeded` (its order is final), records `payment refunded` in the order history once and shows `refunded_at` in the detail (ADR 0014). A cancelled order whose payment never succeeded (`FAILED`, or `PENDING` forever) is not refunded because nothing was taken.

### Reading

`GET /api/v1/payments/{order_id}` serves the owner or an admin (`404` for anyone else, so existence is not leaked) and exposes only the status, amount, currency, `card_last4`, the failure reason and the timestamps. Payments has no public write endpoint.

## How a Stripe adapter would plug in

Only an adapter and a webhook route are new; the saga, the events and the tables stay.

- **Charge.** `charge` creates a PaymentIntent with `amount`, `currency`, the payment method id and `Idempotency-Key: <order id>` (Stripe keeps the response for 24 hours, and the order id is unique, so a retry after a crash returns the same intent). `succeeded` maps to `Succeeded`, a card error to `Declined`, `processing` or `requires_action` to `Processing(None)`.
- **Webhook.** A `POST /api/v1/payments/webhooks/stripe` route verifies the signature with the endpoint secret and maps `payment_intent.succeeded` and `payment_intent.payment_failed` to `apply(order_id, Succeeded | Declined)`, with the order id read from the intent's metadata. Stripe delivers webhooks at least once and out of order; `apply` is already a compare-and-set, so that is safe. `status_of` (retrieving the intent) remains the reconciliation path for missed webhooks.
- **Refund.** `refund` creates a Refund on the intent with the key `refund-<order id>`.
- **Card data and PCI scope.** The browser collects the card with Stripe Elements, which sends it straight to Stripe and returns a payment method id (`pm_...`). The checkout request would carry that id instead of `payment.card_number`, so the card number never touches the store server, orders, payments, Kafka or the logs and the system stays at the lightest PCI level (SAQ A). `order.payment_requested` would carry the payment method id (an optional field, added in a backward compatible way) next to `card_last4` for display.
- **Why the simulation sends the card number.** The challenge asks for a fake that is decided by the card, so the request carries a number from which only the last four digits are kept. That is a conscious simplification: a real system must not receive a card number at all. The safeguards in place are that the number is a `SecretStr`, it is reduced to four digits in the request model, the database refuses anything but four digits, and a test fails if the number appears in a table, an outbox row, a response or a log.

## Consequences and limits

- The simulation has no webhook; the worker's periodic `status_of` plays that role, which is why a real adapter fits without changing the saga.
- A provider that is down makes the charge fail inside the consumer: the event is retried with backoff and dead-lettered afterwards, and the saga timeout cancels the order. A charge that did go through at the provider but whose answer was lost is found again by the idempotency key on redelivery.
- Partial refunds, disputes and multiple payment attempts per order are out of scope: there is exactly one payment per order.
