import type { HistoryEntry, Order } from "../../src/lib/orders";

export const ORDER_ID = "6f1c2f64-3f0e-4c1a-9d52-7a1b8c9d0e21";

export function historyEntry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return { from_status: null, to_status: "PENDING", reason: "order created", at: "2026-10-17T10:00:00Z", ...overrides };
}

export function order(overrides: Partial<Order> = {}): Order {
  return {
    id: ORDER_ID,
    customer_id: "0f6c1f0e-7a52-4f33-9c2a-5d9c3b1e7a10",
    status: "PENDING",
    total: "137.50",
    currency: "USD",
    card_last4: "1111",
    shipping_address: {
      recipient_name: "Ada Lovelace",
      line1: "12 Analytical St",
      line2: null,
      city: "London",
      region: null,
      postal_code: "N1 9GU",
      country: "GB",
      phone: null,
    },
    cancel_reason: null,
    refunded_at: null,
    created_at: "2026-10-17T10:00:00Z",
    updated_at: "2026-10-17T10:00:00Z",
    lines: [
      { sku: "RS-001", name: "Running shoes", quantity: 2, unit_price: "59.00", line_total: "118.00" },
      { sku: "TY-002", name: null, quantity: 1, unit_price: "19.50", line_total: "19.50" },
    ],
    history: [historyEntry()],
    ...overrides,
  };
}
