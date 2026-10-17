import type { OrdersComponents } from "@ecommerce/api-client";

export type Order = OrdersComponents["schemas"]["OrderDetailOut"];
export type OrderLine = OrdersComponents["schemas"]["OrderLineOut"];
export type OrderStatus = OrdersComponents["schemas"]["OrderStatus"];
export type HistoryEntry = OrdersComponents["schemas"]["HistoryEntryOut"];

export type StatusTone = "progress" | "success" | "failure";

export type StatusView = { label: string; description: string; tone: StatusTone };

const POLL_START_MS = 1000;
const POLL_FACTOR = 1.5;
const POLL_MAX_MS = 8000;

export const REFUND_WATCH_MS = 180_000;

export function isFinalStatus(status: OrderStatus): boolean {
  return status === "CONFIRMED" || status === "CANCELLED";
}

export function awaitsRefund(order: Pick<Order, "status" | "cancel_reason" | "refunded_at">): boolean {
  return order.status === "CANCELLED" && order.cancel_reason === "saga_timeout" && order.refunded_at === null;
}

export function mayStillBeRefunded(order: Pick<Order, "status" | "cancel_reason" | "refunded_at" | "updated_at">, now: number): boolean {
  return awaitsRefund(order) && now - Date.parse(order.updated_at) < REFUND_WATCH_MS;
}

export function shouldKeepPolling(order: Pick<Order, "status" | "cancel_reason" | "refunded_at" | "updated_at">, now: number): boolean {
  return !isFinalStatus(order.status) || mayStillBeRefunded(order, now);
}

export function pollDelay(updates: number): number {
  return Math.min(Math.round(POLL_START_MS * POLL_FACTOR ** updates), POLL_MAX_MS);
}

export function cancelReasonText(reason: string | null): string {
  switch (reason) {
    case "insufficient_stock":
    case "product_unavailable":
      return "One or more items are out of stock.";
    case "price_changed":
      return "The price of an item changed while we were processing your order.";
    case "payment_failed":
      return "Your payment was declined.";
    case "saga_timeout":
      return "The payment did not answer in time.";
    default:
      return "The order could not be completed.";
  }
}

export function statusView(order: Pick<Order, "status" | "cancel_reason" | "refunded_at">): StatusView {
  switch (order.status) {
    case "PENDING":
      return { label: "Reserving stock", description: "We are checking that every item is available.", tone: "progress" };
    case "STOCK_RESERVED":
      return { label: "Payment in progress", description: "Your items are reserved. We are waiting for the payment.", tone: "progress" };
    case "PAID":
      return { label: "Payment received", description: "We are finishing your order.", tone: "progress" };
    case "CONFIRMED":
      return { label: "Order confirmed", description: "Thank you. Your payment was accepted and your order is confirmed.", tone: "success" };
    case "CANCELLED":
      return {
        label: "Order cancelled",
        description: order.refunded_at
          ? `${cancelReasonText(order.cancel_reason)} Your payment arrived late and was refunded.`
          : order.cancel_reason === "saga_timeout"
            ? `${cancelReasonText(order.cancel_reason)} You were not charged. If a late payment still arrives, it is refunded automatically.`
            : `${cancelReasonText(order.cancel_reason)} You were not charged.`,
        tone: "failure",
      };
  }
}

export function announcement(order: Pick<Order, "status" | "cancel_reason" | "refunded_at">): string {
  const view = statusView(order);
  return `${view.label}. ${view.description}`;
}

export function historyLabel(entry: HistoryEntry): string {
  if (entry.reason === "payment refunded") {
    return "Payment refunded";
  }
  switch (entry.to_status) {
    case "PENDING":
      return "Order placed";
    case "STOCK_RESERVED":
      return "Stock reserved";
    case "PAID":
      return "Payment received";
    case "CONFIRMED":
      return "Order confirmed";
    case "CANCELLED":
      return `Order cancelled: ${cancelReasonText(entry.reason)}`;
  }
}

const DATE_TIME = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "medium", timeZone: "UTC" });

export function formatDateTime(iso: string): string {
  return `${DATE_TIME.format(new Date(iso))} UTC`;
}

export type OrderFailureKind = "not_found" | "unavailable";
export type OrderFailure = { ok: false; kind: OrderFailureKind; retryAfterSeconds?: number };
