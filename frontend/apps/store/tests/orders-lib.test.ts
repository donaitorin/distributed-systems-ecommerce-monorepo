import {
  announcement,
  cancelReasonText,
  formatDateTime,
  historyLabel,
  isFinalStatus,
  mayStillBeRefunded,
  pollDelay,
  shouldKeepPolling,
  statusView,
} from "../src/lib/orders";
import { historyEntry } from "./support/orders";

describe("isFinalStatus", () => {
  it.each([
    ["CONFIRMED", true],
    ["CANCELLED", true],
    ["PENDING", false],
    ["STOCK_RESERVED", false],
    ["PAID", false],
  ] as const)("%s is final: %s", (status, expected) => {
    expect(isFinalStatus(status)).toBe(expected);
  });
});

describe("watching for a refund", () => {
  const cancelled = { status: "CANCELLED", cancel_reason: "saga_timeout", refunded_at: null, updated_at: "2026-10-17T10:00:00Z" } as const;
  const at = (seconds: number) => Date.parse(cancelled.updated_at) + seconds * 1000;

  it("watches a payment timeout for three minutes after the cancellation", () => {
    expect(mayStillBeRefunded(cancelled, at(0))).toBe(true);
    expect(mayStillBeRefunded(cancelled, at(179))).toBe(true);
    expect(mayStillBeRefunded(cancelled, at(180))).toBe(false);
  });

  it.each([
    ["a refunded order", { ...cancelled, refunded_at: "2026-10-17T10:01:30Z" }],
    ["a declined payment", { ...cancelled, cancel_reason: "payment_failed" }],
    ["an out of stock cancellation", { ...cancelled, cancel_reason: "insufficient_stock" }],
    ["a confirmed order", { ...cancelled, status: "CONFIRMED" }],
  ] as const)("does not watch %s", (_label, order) => {
    expect(mayStillBeRefunded(order, at(10))).toBe(false);
    expect(shouldKeepPolling(order, at(10))).toBe(false);
  });

  it("keeps polling open orders and watched cancellations", () => {
    expect(shouldKeepPolling({ ...cancelled, status: "PENDING" }, at(1000))).toBe(true);
    expect(shouldKeepPolling(cancelled, at(10))).toBe(true);
    expect(shouldKeepPolling(cancelled, at(500))).toBe(false);
  });
});

describe("pollDelay", () => {
  it("backs off from one second and stops growing at eight", () => {
    expect([0, 1, 2, 3, 4, 5, 10].map(pollDelay)).toEqual([1000, 1500, 2250, 3375, 5063, 7594, 8000]);
  });
});

describe("cancelReasonText", () => {
  it.each([
    ["insufficient_stock", "out of stock"],
    ["product_unavailable", "out of stock"],
    ["price_changed", "price"],
    ["payment_failed", "declined"],
    ["saga_timeout", "did not answer in time"],
    ["something_new", "could not be completed"],
    [null, "could not be completed"],
  ])("explains %s", (reason, expected) => {
    expect(cancelReasonText(reason)).toContain(expected);
  });
});

describe("statusView", () => {
  it.each([
    ["PENDING", "Reserving stock", "progress"],
    ["STOCK_RESERVED", "Payment in progress", "progress"],
    ["PAID", "Payment received", "progress"],
    ["CONFIRMED", "Order confirmed", "success"],
    ["CANCELLED", "Order cancelled", "failure"],
  ] as const)("shows %s as %s", (status, label, tone) => {
    expect(statusView({ status, cancel_reason: null, refunded_at: null })).toMatchObject({ label, tone });
  });

  it("gives the reason of a cancellation and says the customer was not charged", () => {
    const view = statusView({ status: "CANCELLED", cancel_reason: "payment_failed", refunded_at: null });

    expect(view.description).toBe("Your payment was declined. You were not charged.");
  });

  it("says a late payment was refunded", () => {
    const view = statusView({ status: "CANCELLED", cancel_reason: "saga_timeout", refunded_at: "2026-10-17T10:02:00Z" });

    expect(view.description).toBe("The payment did not answer in time. Your payment arrived late and was refunded.");
  });

  it("builds one announcement from the label and the description", () => {
    expect(announcement({ status: "PENDING", cancel_reason: null, refunded_at: null })).toBe(
      "Reserving stock. We are checking that every item is available.",
    );
  });
});

describe("historyLabel", () => {
  it.each([
    [historyEntry({ to_status: "PENDING" }), "Order placed"],
    [historyEntry({ from_status: "PENDING", to_status: "STOCK_RESERVED" }), "Stock reserved"],
    [historyEntry({ from_status: "STOCK_RESERVED", to_status: "PAID" }), "Payment received"],
    [historyEntry({ from_status: "PAID", to_status: "CONFIRMED" }), "Order confirmed"],
    [historyEntry({ from_status: "PENDING", to_status: "CANCELLED", reason: "insufficient_stock" }), "Order cancelled: One or more items are out of stock."],
    [historyEntry({ from_status: "CANCELLED", to_status: "CANCELLED", reason: "payment refunded" }), "Payment refunded"],
  ])("labels %j", (entry, expected) => {
    expect(historyLabel(entry)).toBe(expected);
  });
});

describe("formatDateTime", () => {
  it("prints a fixed time zone so the server and the browser agree", () => {
    expect(formatDateTime("2026-10-17T10:05:09Z")).toBe("17 Oct 2026, 10:05:09 UTC");
  });
});
