import { act, render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { OrderTracker } from "../src/components/orders/order-tracker";
import { OrderRequestError } from "../src/lib/order-client";
import type { Order } from "../src/lib/orders";
import { historyEntry, order } from "./support/orders";

async function advance(milliseconds: number) {
  await act(async () => {
    await jest.advanceTimersByTimeAsync(milliseconds);
  });
}

async function advanceUntil(done: () => boolean, limitMs = 60_000) {
  for (let elapsed = 0; elapsed < limitMs && !done(); elapsed += 250) {
    await advance(250);
  }
  expect(done()).toBe(true);
}

const onSessionExpired = jest.fn();

function setup(initial: Order, responses: (Order | Error)[] = [], onConfirmed?: jest.Mock) {
  const queue = [...responses];
  const fetchOrder = jest.fn(() => {
    const next = queue.length > 1 ? queue.shift() : queue[0];
    if (next === undefined) {
      return Promise.resolve(initial);
    }
    return next instanceof Error ? Promise.reject(next) : Promise.resolve(next);
  });
  const view = render(<OrderTracker initial={initial} fetchOrder={fetchOrder} onSessionExpired={onSessionExpired} {...(onConfirmed ? { onConfirmed } : {})} />);
  return { fetchOrder, ...view };
}

const status = () => screen.getByRole("status");

const NOW = new Date("2026-10-17T12:00:00Z");

beforeEach(() => {
  jest.useFakeTimers({ now: NOW });
  jest.clearAllMocks();
});

afterEach(() => {
  jest.useRealTimers();
});

describe("OrderTracker", () => {
  it("shows the order with its lines, totals, address, card and history, under one h1, with no accessibility violations", async () => {
    jest.useRealTimers();
    const { container } = setup(
      order({ status: "CONFIRMED", history: [historyEntry(), historyEntry({ from_status: "PENDING", to_status: "CONFIRMED", reason: "order confirmed", at: "2026-10-17T10:00:09Z" })] }),
    );

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Order 6F1C2F64" })).toBeInTheDocument();
    const lines = within(screen.getByRole("list", { name: "Items in this order" })).getAllByRole("listitem");
    expect(lines[0]).toHaveTextContent("Running shoes");
    expect(lines[0]).toHaveTextContent("2 × $59.00");
    expect(lines[0]).toHaveTextContent("$118.00");
    expect(lines[1]).toHaveTextContent("TY-002");
    expect(screen.getByText("Order total").nextSibling).toHaveTextContent("$137.50");
    expect(screen.getByText("12 Analytical St")).toBeInTheDocument();
    expect(screen.getByText("Card ending in 1111")).toBeInTheDocument();
    const history = within(screen.getByRole("list", { name: "Status history" })).getAllByRole("listitem");
    expect(history.map((item) => item.textContent)).toEqual([
      "Order placed17 Oct 2026, 10:00:00 UTC",
      "Order confirmed17 Oct 2026, 10:00:09 UTC",
    ]);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("announces each status change in one live region and polls with growing delays until the order is confirmed", async () => {
    const times: number[] = [];
    const sequence = [order(), order({ status: "STOCK_RESERVED" }), order({ status: "PAID" }), order({ status: "CONFIRMED" })];
    const fetchOrder = jest.fn(() => {
      times.push(Date.now());
      return Promise.resolve(sequence[Math.min(times.length - 1, sequence.length - 1)] as Order);
    });
    render(<OrderTracker initial={order()} fetchOrder={fetchOrder} onSessionExpired={onSessionExpired} />);

    expect(status()).toHaveAttribute("aria-live", "polite");
    expect(status()).toHaveTextContent("Reserving stock");

    await advanceUntil(() => /Payment in progress/.test(status().textContent ?? ""));
    await advanceUntil(() => /Payment received/.test(status().textContent ?? ""));
    await advanceUntil(() => /Order confirmed/.test(status().textContent ?? ""));
    expect(status()).toHaveTextContent("Thank you");

    const gaps = times.slice(1).map((time, index) => time - (times[index] as number));
    expect(gaps.length).toBeGreaterThanOrEqual(3);
    expect(gaps[1] as number).toBeGreaterThan(gaps[0] as number);
    expect(gaps[2] as number).toBeGreaterThan(gaps[1] as number);
    expect(Math.max(...gaps)).toBeLessThanOrEqual(8000);

    const calls = fetchOrder.mock.calls.length;
    await advance(120_000);
    expect(fetchOrder).toHaveBeenCalledTimes(calls);
  });

  it("stops polling when the order is cancelled and says why", async () => {
    const { fetchOrder } = setup(order({ status: "STOCK_RESERVED" }), [
      order({ status: "STOCK_RESERVED" }),
      order({ status: "CANCELLED", cancel_reason: "payment_failed" }),
    ]);

    await advanceUntil(() => /Order cancelled/.test(status().textContent ?? ""));

    expect(status()).toHaveTextContent("Your payment was declined. You were not charged.");
    const calls = fetchOrder.mock.calls.length;
    await advance(120_000);
    expect(fetchOrder).toHaveBeenCalledTimes(calls);
  });

  it.each([
    ["insufficient_stock", null, "One or more items are out of stock."],
    ["price_changed", null, "The price of an item changed"],
    ["payment_failed", null, "Your payment was declined."],
    ["saga_timeout", null, "The payment did not answer in time. You were not charged. If a late payment still arrives"],
    ["saga_timeout", "2026-10-17T10:02:00Z", "Your payment arrived late and was refunded."],
  ])("explains a cancellation for %s (refunded at %s)", (reason, refundedAt, expected) => {
    setup(order({ status: "CANCELLED", cancel_reason: reason, refunded_at: refundedAt }));

    expect(status()).toHaveTextContent("Order cancelled");
    expect(status()).toHaveTextContent(expected);
    if (refundedAt) {
      expect(screen.getByText(/Refunded on 17 Oct 2026, 10:02:00 UTC/)).toBeInTheDocument();
    }
  });

  it("keeps watching a payment timeout for a refund, announces it when it arrives, then stops", async () => {
    const cancelled = order({ status: "CANCELLED", cancel_reason: "saga_timeout", updated_at: new Date(NOW.getTime() - 30_000).toISOString() });
    const refunded = { ...cancelled, refunded_at: new Date(NOW.getTime() + 20_000).toISOString() };
    const { fetchOrder } = setup(cancelled, [cancelled, cancelled, refunded]);

    expect(status()).toHaveTextContent("If a late payment still arrives, it is refunded automatically.");
    await advanceUntil(() => /was refunded/.test(status().textContent ?? ""));
    expect(screen.getByText(/Refunded on/)).toBeInTheDocument();

    const calls = fetchOrder.mock.calls.length;
    expect(calls).toBeGreaterThanOrEqual(3);
    await advance(300_000);
    expect(fetchOrder).toHaveBeenCalledTimes(calls);
  });

  it("stops watching for a refund three minutes after the cancellation", async () => {
    const cancelled = order({ status: "CANCELLED", cancel_reason: "saga_timeout", updated_at: new Date(NOW.getTime() - 150_000).toISOString() });
    const { fetchOrder } = setup(cancelled, [cancelled]);

    await advance(60_000);
    const calls = fetchOrder.mock.calls.length;
    expect(calls).toBeGreaterThan(1);
    await advance(300_000);
    expect(fetchOrder.mock.calls.length).toBeLessThan(calls + 2);
  });

  it("does not poll an order that is already final", async () => {
    const { fetchOrder } = setup(order({ status: "CONFIRMED" }));

    await advance(30_000);

    expect(fetchOrder.mock.calls.length).toBeLessThanOrEqual(1);
  });

  it("refreshes the header cart count on confirmation, and again a little later while the cart worker catches up", async () => {
    const onConfirmed = jest.fn();
    setup(order({ status: "STOCK_RESERVED" }), [order({ status: "STOCK_RESERVED" }), order({ status: "CONFIRMED" })], onConfirmed);

    await advance(500);
    expect(onConfirmed).not.toHaveBeenCalled();
    await advanceUntil(() => onConfirmed.mock.calls.length === 1);
    await advanceUntil(() => onConfirmed.mock.calls.length === 2, 3000);
    await advanceUntil(() => onConfirmed.mock.calls.length === 3, 6000);
    await advance(60_000);
    expect(onConfirmed).toHaveBeenCalledTimes(3);
  });

  it("keeps showing the last status and says it may be out of date when the refresh fails, then recovers", async () => {
    setup(order(), [order(), new OrderRequestError(null), new OrderRequestError(null), new OrderRequestError(null), order({ status: "STOCK_RESERVED" })]);

    await advanceUntil(() => screen.queryByText(/cannot refresh the status right now/) !== null);
    expect(status()).toHaveTextContent("Reserving stock");

    await advanceUntil(() => /Payment in progress/.test(status().textContent ?? ""));
    expect(screen.queryByText(/cannot refresh the status right now/)).not.toBeInTheDocument();
  });

  it("sends an expired session to the login page and back to the order, and stops polling", async () => {
    const { fetchOrder } = setup(order(), [order(), new OrderRequestError(401)]);

    await advanceUntil(() => onSessionExpired.mock.calls.length > 0);

    expect(onSessionExpired).toHaveBeenCalledTimes(1);
    const calls = fetchOrder.mock.calls.length;
    await advance(120_000);
    expect(fetchOrder).toHaveBeenCalledTimes(calls);
  });

  it("stops polling when the order has disappeared", async () => {
    const { fetchOrder } = setup(order(), [order(), new OrderRequestError(404)]);

    await advanceUntil(() => fetchOrder.mock.calls.length >= 2);
    await advance(1000);
    const calls = fetchOrder.mock.calls.length;
    await advance(120_000);

    expect(fetchOrder).toHaveBeenCalledTimes(calls);
  });
});
