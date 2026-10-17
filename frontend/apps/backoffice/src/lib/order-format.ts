import type { OrderRow } from "./types";

export function cancelReasonLabel(reason: string | null): string {
  switch (reason) {
    case "insufficient_stock":
      return "Insufficient stock";
    case "product_unavailable":
      return "Product unavailable";
    case "price_changed":
      return "Price changed";
    case "payment_failed":
      return "Payment declined";
    case "saga_timeout":
      return "Payment timed out";
    case null:
      return "No reason recorded";
    default:
      return reason;
  }
}

export function paymentStatusLabel(status: string): string {
  switch (status) {
    case "PENDING":
      return "Pending";
    case "SUCCEEDED":
      return "Succeeded";
    case "FAILED":
      return "Failed";
    case "REFUNDED":
      return "Refunded";
    default:
      return status;
  }
}

export function shortOrderId(id: string): string {
  return id.slice(0, 8).toUpperCase();
}

export function customerLabel(order: Pick<OrderRow, "customer_email" | "customer_id">): string {
  return order.customer_email ?? `Customer ${order.customer_id.slice(0, 8)}`;
}
