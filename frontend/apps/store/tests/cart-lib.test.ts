import {
  describeFlag,
  failureMessage,
  isCartFailure,
  isValidQuantity,
  money,
  parseQuantity,
  pluralItems,
  type CartFailureKind,
} from "../src/lib/cart";
import { cart } from "./support/cart";

describe("parseQuantity", () => {
  it.each([
    ["1", 1],
    ["99", 99],
    [" 7 ", 7],
    ["007", 7],
  ])("accepts %j", (text, expected) => {
    expect(parseQuantity(text)).toBe(expected);
  });

  it.each(["", "0", "100", "-1", "1.5", "1e2", "abc", "٣", "1234"])("refuses %j", (text) => {
    expect(parseQuantity(text)).toBeNull();
  });
});

describe("isValidQuantity", () => {
  it("only accepts whole numbers from 1 to 99", () => {
    expect([1, 50, 99].every(isValidQuantity)).toBe(true);
    expect([0, 100, 1.5, NaN, "2", null, undefined].some(isValidQuantity)).toBe(false);
  });
});

describe("money and pluralItems", () => {
  it("formats decimal strings as dollars and keeps unreadable values", () => {
    expect(money("59.00")).toBe("$59.00");
    expect(money("1234.5")).toBe("$1,234.50");
    expect(money("free")).toBe("$free");
  });

  it("counts items in the singular and the plural", () => {
    expect([pluralItems(0), pluralItems(1), pluralItems(3)]).toEqual(["0 items", "1 item", "3 items"]);
  });
});

describe("failureMessage", () => {
  const kinds: CartFailureKind[] = ["cart_full", "not_found", "invalid", "price_changed", "unavailable"];

  it.each(kinds)("explains %s in plain language without status codes", (kind) => {
    const message = failureMessage({ ok: false, kind });

    expect(message.length).toBeGreaterThan(20);
    expect(message).not.toMatch(/\b(40\d|50\d)\b/);
  });

  it("names the limits and the new price", () => {
    expect(failureMessage({ ok: false, kind: "cart_full" })).toContain("100 different products");
    expect(failureMessage({ ok: false, kind: "invalid" })).toContain("1 to 99");
    expect(failureMessage({ ok: false, kind: "price_changed", currentPrice: "64.50" })).toContain("$64.50");
  });

  it("tells the customer that nothing changed when the cart is unreachable", () => {
    expect(failureMessage({ ok: false, kind: "unavailable" })).toContain("Nothing was changed");
  });
});

describe("describeFlag", () => {
  it("shows both prices and offers the new one for acceptance", () => {
    expect(describeFlag({ type: "price_changed", old_price: "59.00", new_price: "64.50" })).toEqual({
      label: "Price changed",
      text: "The price changed from $59.00 to $64.50.",
      acceptablePrice: "64.50",
    });
  });

  it("prefers the price learned from a conflict", () => {
    const notice = describeFlag({ type: "price_changed", old_price: "59.00", new_price: "64.50" }, "66.00");

    expect(notice.text).toBe("The price changed from $59.00 to $66.00.");
    expect(notice.acceptablePrice).toBe("66.00");
  });

  it("says a retired product is no longer available, with nothing to accept", () => {
    const notice = describeFlag({ type: "unavailable" });

    expect(notice.label).toBe("No longer available");
    expect(notice.acceptablePrice).toBeUndefined();
  });

  it("distinguishes few left from out of stock", () => {
    expect(describeFlag({ type: "insufficient_stock", available: 3 })).toMatchObject({
      label: "Low stock",
      text: expect.stringContaining("Only 3 left") as string,
    });
    expect(describeFlag({ type: "insufficient_stock", available: 0 }).label).toBe("Out of stock");
    expect(describeFlag({ type: "insufficient_stock" }).label).toBe("Out of stock");
  });
});

describe("isCartFailure", () => {
  it("tells a failure from a cart", () => {
    expect(isCartFailure({ ok: false, kind: "unavailable" })).toBe(true);
    expect(isCartFailure(cart())).toBe(false);
  });
});
