import { OrderStatusBadge } from "@ecommerce/ui";
import { formatDateTime } from "@ecommerce/web-core";
import { cancelReasonLabel, paymentStatusLabel } from "../../lib/order-format";
import { ORDERS_PATH, ZONE_PATH } from "../../lib/paths";
import type { OrderDetail } from "../../lib/types";
import type { PaymentLookup } from "../../server/orders";

export type OrderDetailViewProps = {
  order: OrderDetail;
  payment: PaymentLookup;
};

const MONEY = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

function money(value: string): string {
  return MONEY.format(Number(value));
}

function Term({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-sm text-secondary">{label}</dt>
      <dd className="text-base break-words">{children}</dd>
    </div>
  );
}

function PaymentSection({ order, payment }: OrderDetailViewProps) {
  if (payment.payment === null) {
    return (
      <p className="text-base">
        {payment.unavailable
          ? "The payment could not be loaded right now. Reload the page to try again."
          : "No payment was recorded for this order."}
      </p>
    );
  }
  const record = payment.payment;
  return (
    <dl className="grid gap-4 sm:grid-cols-2">
      <Term label="Payment status">{paymentStatusLabel(record.status)}</Term>
      <Term label="Card">Ending in {record.card_last4}</Term>
      <Term label="Amount">{money(record.amount)}</Term>
      {record.failure_reason ? <Term label="Failure reason">{record.failure_reason}</Term> : null}
      {record.refunded_at ? <Term label="Refunded">{formatDateTime(record.refunded_at)}</Term> : null}
      {order.refunded_at && !record.refunded_at ? <Term label="Refunded">{formatDateTime(order.refunded_at)}</Term> : null}
    </dl>
  );
}

export function OrderDetailView({ order, payment }: OrderDetailViewProps) {
  return (
    <div className="flex flex-col gap-8">
      <p>
        <a href={`${ZONE_PATH}${ORDERS_PATH}`} className="text-accent-strong underline">
          Back to orders
        </a>
      </p>
      <section aria-labelledby="summary-heading" className="flex flex-col gap-4">
        <h2 id="summary-heading" className="text-xl font-semibold">
          Summary
        </h2>
        <dl className="grid gap-4 sm:grid-cols-2">
          <Term label="Status">
            <OrderStatusBadge status={order.status} />
          </Term>
          <Term label="Order total">{money(order.total)}</Term>
          <Term label="Placed">{formatDateTime(order.created_at)}</Term>
          <Term label="Last update">{formatDateTime(order.updated_at)}</Term>
          {order.status === "CANCELLED" ? <Term label="Cancel reason">{cancelReasonLabel(order.cancel_reason)}</Term> : null}
          {order.refunded_at ? <Term label="Refunded">{formatDateTime(order.refunded_at)}</Term> : null}
          <Term label="Order id">{order.id}</Term>
        </dl>
      </section>
      <section aria-labelledby="customer-heading" className="flex flex-col gap-4">
        <h2 id="customer-heading" className="text-xl font-semibold">
          Customer
        </h2>
        <dl className="grid gap-4 sm:grid-cols-2">
          <Term label="Email">{order.customer_email ?? "Not recorded for this order"}</Term>
          <Term label="Customer id">{order.customer_id}</Term>
        </dl>
      </section>
      <section aria-labelledby="lines-heading" className="flex flex-col gap-4">
        <h2 id="lines-heading" className="text-xl font-semibold">
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
      </section>
      <section aria-labelledby="address-heading" className="flex flex-col gap-3">
        <h2 id="address-heading" className="text-xl font-semibold">
          Shipping address
        </h2>
        <address className="flex flex-col text-base not-italic">
          <span className="font-semibold">{order.shipping_address.recipient_name}</span>
          <span>{order.shipping_address.line1}</span>
          {order.shipping_address.line2 ? <span>{order.shipping_address.line2}</span> : null}
          <span>
            {[order.shipping_address.city, order.shipping_address.region, order.shipping_address.postal_code]
              .filter(Boolean)
              .join(", ")}
          </span>
          <span>{order.shipping_address.country}</span>
          {order.shipping_address.phone ? <span>{order.shipping_address.phone}</span> : null}
        </address>
      </section>
      <section aria-labelledby="payment-heading" className="flex flex-col gap-4">
        <h2 id="payment-heading" className="text-xl font-semibold">
          Payment
        </h2>
        <p className="text-base">Card ending in {order.card_last4}</p>
        <PaymentSection order={order} payment={payment} />
      </section>
      <section aria-labelledby="history-heading" className="flex flex-col gap-3">
        <h2 id="history-heading" className="text-xl font-semibold">
          Status history
        </h2>
        <ol aria-label="Status history" className="flex flex-col gap-2">
          {order.history.map((entry) => (
            <li key={`${entry.at}-${entry.to_status}-${entry.reason ?? ""}`} className="flex flex-col gap-0.5 border-l-4 border-border-strong pl-3">
              <span className="text-base font-medium">
                {entry.from_status ? `${entry.from_status} to ${entry.to_status}` : `Created as ${entry.to_status}`}
                {entry.reason ? `: ${entry.reason}` : ""}
              </span>
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
