import { formatDateTime } from "@ecommerce/web-core";
import { money } from "../../lib/cart";
import { historyLabel, type Order } from "../../lib/orders";
import { AddressText } from "../account/address-text";

export type OrderDetailsProps = { order: Order };

export function OrderDetails({ order }: OrderDetailsProps) {
  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="order-items-heading" className="flex flex-col gap-4">
        <h2 id="order-items-heading" className="text-xl font-semibold">
          Items
        </h2>
        <ul aria-label="Items in this order" className="flex flex-col gap-3">
          {order.lines.map((line) => (
            <li key={line.sku} className="flex items-start justify-between gap-4 rounded-lg border border-border bg-surface p-3">
              <div className="flex min-w-0 flex-col gap-1">
                <p className="text-base font-semibold break-words">{line.name ?? line.sku}</p>
                <p className="text-sm text-secondary">
                  SKU {line.sku} · {line.quantity} × {money(line.unit_price)}
                </p>
              </div>
              <p className="text-base font-semibold">
                <span className="sr-only">Line total: </span>
                {money(line.line_total)}
              </p>
            </li>
          ))}
        </ul>
        <dl className="flex max-w-md items-baseline justify-between gap-4 border-t border-border pt-4">
          <dt className="text-base font-medium">Order total</dt>
          <dd className="text-xl font-semibold">{money(order.total)}</dd>
        </dl>
      </section>
      <section aria-labelledby="order-address-heading" className="flex flex-col gap-3">
        <h2 id="order-address-heading" className="text-xl font-semibold">
          Shipping address
        </h2>
        <AddressText address={order.shipping_address} />
      </section>
      <section aria-labelledby="order-payment-heading" className="flex flex-col gap-2">
        <h2 id="order-payment-heading" className="text-xl font-semibold">
          Payment
        </h2>
        <p className="text-base">Card ending in {order.card_last4}</p>
        {order.refunded_at ? <p className="text-base">Refunded on {formatDateTime(order.refunded_at)}.</p> : null}
      </section>
      <section aria-labelledby="order-history-heading" className="flex flex-col gap-3">
        <h2 id="order-history-heading" className="text-xl font-semibold">
          Status history
        </h2>
        <ol aria-label="Status history" className="flex flex-col gap-2">
          {order.history.map((entry) => (
            <li key={`${entry.at}-${entry.to_status}-${entry.reason ?? ""}`} className="flex flex-col gap-0.5 border-l-4 border-border-strong pl-3">
              <span className="text-base font-medium">{historyLabel(entry)}</span>
              <time dateTime={entry.at} className="text-sm text-secondary">
                {formatDateTime(entry.at)}
              </time>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
