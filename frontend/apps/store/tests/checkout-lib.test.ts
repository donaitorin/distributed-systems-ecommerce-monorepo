import {
  attemptSignature,
  blockedLines,
  cardDigits,
  cartFingerprint,
  checkoutFormSchema,
  groupCardNumber,
  isAttemptKey,
  isValidCardNumber,
  lastFour,
  nextAttempt,
  placeOrderFailureMessage,
  type PlaceOrderFailureKind,
} from "../src/lib/checkout";
import { cart, line } from "./support/cart";

describe("card number helpers", () => {
  it("keeps digits only, up to 19", () => {
    expect(cardDigits("4111 1111-1111 1111abc")).toBe("4111111111111111");
    expect(cardDigits("1".repeat(25))).toHaveLength(19);
  });

  it("groups the digits by four for display", () => {
    expect(groupCardNumber("4111111111111111")).toBe("4111 1111 1111 1111");
    expect(groupCardNumber("41111")).toBe("4111 1");
    expect(groupCardNumber("")).toBe("");
    expect(groupCardNumber("abc")).toBe("");
  });

  it("reads the last four digits", () => {
    expect(lastFour("4111111111111111")).toBe("1111");
    expect(lastFour("12")).toBe("12");
  });

  it.each([
    ["4111 1111 1111 1111", true],
    ["4111-1111-1111-1111", true],
    ["411111111111", true],
    ["4".repeat(19), true],
    ["41111111111", false],
    ["4".repeat(20), false],
    ["4111 1111 1111 111a", false],
    ["", false],
  ])("validates %j as %s", (text, expected) => {
    expect(isValidCardNumber(text)).toBe(expected);
    expect(checkoutFormSchema.safeParse({ card_number: text }).success).toBe(expected);
  });
});

describe("cart helpers", () => {
  it("fingerprints what the customer saw: sku, quantity and price of every line", () => {
    expect(cartFingerprint(cart())).toBe("RS-001:2:59.00,TY-002:1:19.50");
    expect(cartFingerprint(cart([]))).toBe("");
  });

  it("finds the lines that block checkout", () => {
    const flagged = line({ flags: [{ type: "unavailable" }] });

    expect(blockedLines(cart([flagged, line({ sku: "B" })]))).toEqual([flagged]);
    expect(blockedLines(cart())).toEqual([]);
  });
});

describe("isAttemptKey", () => {
  it.each(["6f1c2f64-3f0e-4c1a-9d52-7a1b8c9d0e21", "abc_DEF:12.3-4"])("accepts %s", (key) => {
    expect(isAttemptKey(key)).toBe(true);
  });

  it.each(["short", "has space in it", "x".repeat(129), "", 42, null])("rejects %j", (key) => {
    expect(isAttemptKey(key)).toBe(false);
  });
});

describe("attempts", () => {
  const signature = attemptSignature({ cartFingerprint: "A:1:1.00", addressId: "addr", cardDigits: "4111111111111111" });
  const newKey = jest.fn(() => Promise.resolve("new-key-0001"));

  beforeEach(() => {
    newKey.mockClear();
  });

  it("depends on the cart, the address and the last four digits of the card only", () => {
    expect(signature).toBe("A:1:1.00|addr|1111");
    expect(attemptSignature({ cartFingerprint: "A:1:1.00", addressId: "addr", cardDigits: "5500000000001111" })).toBe(signature);
  });

  it("binds the first submit to the key the server gave", async () => {
    expect(await nextAttempt({ key: "first-key-01", signature: null }, signature, newKey)).toEqual({ key: "first-key-01", signature });
    expect(newKey).not.toHaveBeenCalled();
  });

  it("reuses the key when the same attempt is repeated", async () => {
    const current = { key: "first-key-01", signature };

    expect(await nextAttempt(current, signature, newKey)).toBe(current);
    expect(newKey).not.toHaveBeenCalled();
  });

  it.each([
    ["cart", { cartFingerprint: "A:2:1.00", addressId: "addr", cardDigits: "4111111111111111" }],
    ["address", { cartFingerprint: "A:1:1.00", addressId: "other", cardDigits: "4111111111111111" }],
    ["card", { cartFingerprint: "A:1:1.00", addressId: "addr", cardDigits: "4111111111110000" }],
  ])("asks the server for a new key when the %s changes", async (_label, parts) => {
    const next = await nextAttempt({ key: "first-key-01", signature }, attemptSignature(parts), newKey);

    expect(next).toEqual({ key: "new-key-0001", signature: attemptSignature(parts) });
    expect(newKey).toHaveBeenCalledTimes(1);
  });
});

describe("placeOrderFailureMessage", () => {
  const kinds: PlaceOrderFailureKind[] = [
    "empty_cart",
    "cart_flagged",
    "cart_changed",
    "address_missing",
    "attempt_changed",
    "invalid_card",
    "invalid_address",
    "invalid",
    "rate_limited",
    "unavailable",
  ];

  it.each(kinds)("words %s in plain language", (kind) => {
    const message = placeOrderFailureMessage({ ok: false, kind });

    expect(message.length).toBeGreaterThan(20);
    expect(message).not.toMatch(/422|409|idempotency|undefined/i);
  });

  it("says how long to wait when the API said so", () => {
    expect(placeOrderFailureMessage({ ok: false, kind: "rate_limited", retryAfterSeconds: 30 })).toContain("30 seconds");
  });
});
