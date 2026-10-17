/**
 * @jest-environment node
 */
import { cartFingerprint, type PlaceOrderInput } from "../src/lib/checkout";
import { isOrderId, loadOrder, placeOrder, readOrderResponse } from "../src/server/orders";
import { json, mockFetch, problem } from "./support/api";
import { cart, line } from "./support/cart";
import { address, ADDRESS_ID } from "./support/addresses";
import { ORDER_ID, order } from "./support/orders";

const authorizationHeaders = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({
  authRuntime: () => ({ config: { apiBaseUrl: "http://gateway.test" } }),
  authorizationHeaders: () => authorizationHeaders() as unknown,
}));
jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));

beforeEach(() => {
  authorizationHeaders.mockReset();
  authorizationHeaders.mockReturnValue({ authorization: "Bearer t" });
});

const CART = { method: "GET", path: "/api/v1/cart", respond: () => json(cart()) };
const ADDRESSES = { method: "GET", path: "/api/v1/accounts/me/addresses", respond: () => json({ items: [address()] }) };
const ORDER_POST = (respond: () => Response) => ({ method: "POST", path: "/api/v1/orders", respond });
const ORDER_GET = (respond: () => Response) => ({ method: "GET", path: `/api/v1/orders/${ORDER_ID}`, respond });

const INPUT: PlaceOrderInput = {
  attemptKey: "6f1c2f64-3f0e-4c1a-9d52-7a1b8c9d0e21",
  addressId: ADDRESS_ID,
  cardNumber: "4111 1111 1111 1111",
  cartFingerprint: cartFingerprint(cart()),
};

const accepted = () => json({ id: ORDER_ID, status: "PENDING" }, 202);
const postBody = (api: ReturnType<typeof mockFetch>) =>
  JSON.parse(api.calls.find((call) => call.method === "POST")?.init.body as string) as Record<string, unknown>;

describe("placeOrder", () => {
  it("builds the order from the cart and the saved address, with the attempt key as Idempotency-Key", async () => {
    const api = mockFetch([CART, ADDRESSES, ORDER_POST(accepted)]);

    expect(await placeOrder(INPUT)).toEqual({ ok: true, orderId: ORDER_ID });

    const post = api.calls.find((call) => call.method === "POST");
    const headers = new Headers(post?.init.headers);
    expect(headers.get("idempotency-key")).toBe(INPUT.attemptKey);
    expect(headers.get("authorization")).toBe("Bearer t");
    expect(postBody(api)).toEqual({
      lines: [
        { sku: "RS-001", quantity: 2, unit_price: "59.00" },
        { sku: "TY-002", quantity: 1, unit_price: "19.50" },
      ],
      shipping_address: {
        recipient_name: "Ada Lovelace",
        line1: "12 Analytical St",
        line2: null,
        city: "London",
        region: null,
        postal_code: "N1 9GU",
        country: "GB",
        phone: "+442071234567",
      },
      payment: { card_number: "4111111111111111" },
    });
  });

  it("never puts the card number in the URL or in the headers", async () => {
    const api = mockFetch([CART, ADDRESSES, ORDER_POST(accepted)]);

    await placeOrder(INPUT);

    for (const call of api.calls) {
      expect(call.url.href).not.toContain("4111");
      expect(JSON.stringify(call.init.headers)).not.toContain("4111");
    }
  });

  it.each([
    ["a malformed attempt key", { attemptKey: "short" }, "invalid"],
    ["an address id that is not a UUID", { addressId: "../me" }, "invalid"],
    ["a card number that is too short", { cardNumber: "4111" }, "invalid_card"],
    ["a card number with letters", { cardNumber: "4111 1111 1111 abcd" }, "invalid_card"],
  ])("refuses %s without calling anything", async (_label, override, kind) => {
    const api = mockFetch([]);

    expect(await placeOrder({ ...INPUT, ...override })).toEqual({ ok: false, kind });
    expect(api.calls).toHaveLength(0);
  });

  it("does not order when the cart or the addresses cannot be read", async () => {
    mockFetch([{ ...CART, respond: () => problem(503, "Down") }, ADDRESSES]);
    expect(await placeOrder(INPUT)).toEqual({ ok: false, kind: "unavailable" });

    mockFetch([CART, { ...ADDRESSES, respond: () => problem(503, "Down") }]);
    expect(await placeOrder(INPUT)).toEqual({ ok: false, kind: "unavailable" });
  });

  it("does not order an empty cart", async () => {
    const api = mockFetch([{ ...CART, respond: () => json(cart([])) }, ADDRESSES]);

    expect(await placeOrder({ ...INPUT, cartFingerprint: "" })).toEqual({ ok: false, kind: "empty_cart" });
    expect(api.calls.some((call) => call.method === "POST")).toBe(false);
  });

  it("does not order while a line has a flag, even if the page showed it as fine", async () => {
    const flagged = cart([line({ flags: [{ type: "price_changed", old_price: "59.00", new_price: "64.50" }] })]);
    const api = mockFetch([{ ...CART, respond: () => json(flagged) }, ADDRESSES]);

    expect(await placeOrder({ ...INPUT, cartFingerprint: cartFingerprint(flagged) })).toEqual({ ok: false, kind: "cart_flagged" });
    expect(api.calls.some((call) => call.method === "POST")).toBe(false);
  });

  it("does not order a cart that differs from what the customer saw", async () => {
    const api = mockFetch([CART, ADDRESSES]);

    expect(await placeOrder({ ...INPUT, cartFingerprint: "RS-001:1:59.00" })).toEqual({ ok: false, kind: "cart_changed" });
    expect(api.calls.some((call) => call.method === "POST")).toBe(false);
  });

  it("does not order to an address that is not one of the customer's", async () => {
    mockFetch([CART, { ...ADDRESSES, respond: () => json({ items: [] }) }]);

    expect(await placeOrder(INPUT)).toEqual({ ok: false, kind: "address_missing" });
  });

  it("tells a reused key apart from other validation problems", async () => {
    mockFetch([CART, ADDRESSES, ORDER_POST(() => problem(422, "Idempotency key reused", { code: "idempotency_key_reused" }))]);

    expect(await placeOrder(INPUT)).toEqual({ ok: false, kind: "attempt_changed" });
  });

  it.each([
    ["body.payment.card_number", "invalid_card"],
    ["body.shipping_address.country", "invalid_address"],
    ["body.lines.0.unit_price", "invalid"],
  ])("maps a 422 on %s to %s without echoing any value", async (location, kind) => {
    mockFetch([CART, ADDRESSES, ORDER_POST(() => problem(422, "Validation failed", { errors: [{ location, message: "bad", type: "value_error" }] }))]);

    expect(await placeOrder(INPUT)).toEqual({ ok: false, kind });
  });

  it("keeps the retry hint of a rate limit and of an unavailable service", async () => {
    const limited = () =>
      new Response(JSON.stringify({ type: "x", title: "Slow down", status: 429 }), {
        status: 429,
        headers: { "content-type": "application/problem+json", "retry-after": "12" },
      });
    mockFetch([CART, ADDRESSES, ORDER_POST(limited)]);
    expect(await placeOrder(INPUT)).toEqual({ ok: false, kind: "rate_limited", retryAfterSeconds: 12 });

    const down = () =>
      new Response(JSON.stringify({ type: "x", title: "Down", status: 503 }), {
        status: 503,
        headers: { "content-type": "application/problem+json", "retry-after": "3" },
      });
    mockFetch([CART, ADDRESSES, ORDER_POST(down)]);
    expect(await placeOrder(INPUT)).toEqual({ ok: false, kind: "unavailable", retryAfterSeconds: 3 });
  });

  it("treats a rate limit without a hint and a plain 500 as retryable", async () => {
    mockFetch([CART, ADDRESSES, ORDER_POST(() => problem(429, "Slow down"))]);
    expect(await placeOrder(INPUT)).toEqual({ ok: false, kind: "rate_limited" });

    mockFetch([CART, ADDRESSES, ORDER_POST(() => problem(500, "Oops"))]);
    expect(await placeOrder(INPUT)).toEqual({ ok: false, kind: "unavailable" });
  });

  it("is unavailable when the network fails, so the same key can be sent again", async () => {
    const api = mockFetch([CART, ADDRESSES]);
    const original = api.implementation.getMockImplementation();
    api.implementation.mockImplementation((input, init) =>
      (init?.method ?? "GET") === "POST" ? Promise.reject(new TypeError("fetch failed")) : (original?.(input, init) as Promise<Response>),
    );

    expect(await placeOrder(INPUT)).toEqual({ ok: false, kind: "unavailable" });
  });

  it("sends an expired session to the login page and back to checkout", async () => {
    mockFetch([CART, ADDRESSES, ORDER_POST(() => problem(401, "Unauthorized"))]);

    await expect(placeOrder(INPUT)).rejects.toThrow("NEXT_REDIRECT /login?next=%2Fcheckout&reason=expired");
  });

  it("sends the same key and body again when the same attempt is repeated", async () => {
    const api = mockFetch([CART, ADDRESSES, ORDER_POST(accepted)]);

    await placeOrder(INPUT);
    await placeOrder(INPUT);

    const posts = api.calls.filter((call) => call.method === "POST");
    expect(posts).toHaveLength(2);
    expect(new Headers(posts[0]?.init.headers).get("idempotency-key")).toBe(new Headers(posts[1]?.init.headers).get("idempotency-key"));
    expect(posts[0]?.init.body).toBe(posts[1]?.init.body);
  });

  it("lets unexpected errors surface", async () => {
    mockFetch([CART, ADDRESSES, ORDER_POST(accepted)]);
    authorizationHeaders.mockRejectedValue(new RangeError("bug"));

    await expect(placeOrder(INPUT)).rejects.toThrow("bug");
  });
});

describe("isOrderId", () => {
  it("accepts UUIDs only", () => {
    expect(isOrderId(ORDER_ID)).toBe(true);
    expect(isOrderId("../admin")).toBe(false);
  });
});

describe("loadOrder", () => {
  it("reads the order of the customer", async () => {
    mockFetch([ORDER_GET(() => json(order()))]);

    expect(await loadOrder(ORDER_ID)).toEqual(order());
  });

  it("does not call the API for an id that is not a UUID", async () => {
    const api = mockFetch([]);

    expect(await loadOrder("nope")).toEqual({ ok: false, kind: "not_found" });
    expect(api.calls).toHaveLength(0);
  });

  it.each([404, 422])("reports %s as not found", async (status) => {
    mockFetch([ORDER_GET(() => problem(status, "Nope"))]);

    expect(await loadOrder(ORDER_ID)).toEqual({ ok: false, kind: "not_found" });
  });

  it("reports other failures as unavailable, with the retry hint", async () => {
    mockFetch([ORDER_GET(() => new Response(JSON.stringify({ type: "x", title: "Down", status: 503 }), { status: 503, headers: { "content-type": "application/problem+json", "retry-after": "4" } }))]);
    expect(await loadOrder(ORDER_ID)).toEqual({ ok: false, kind: "unavailable", retryAfterSeconds: 4 });

    mockFetch([ORDER_GET(() => problem(500, "Oops"))]);
    expect(await loadOrder(ORDER_ID)).toEqual({ ok: false, kind: "unavailable" });

    global.fetch = jest.fn(() => Promise.reject(new TypeError("fetch failed")));
    expect(await loadOrder(ORDER_ID)).toEqual({ ok: false, kind: "unavailable" });
  });

  it("sends an expired session to the login page and back to the order", async () => {
    mockFetch([ORDER_GET(() => problem(401, "Unauthorized"))]);

    await expect(loadOrder(ORDER_ID)).rejects.toThrow(`NEXT_REDIRECT /login?next=%2Forders%2F${ORDER_ID}&reason=expired`);
  });

  it("lets unexpected errors surface", async () => {
    mockFetch([ORDER_GET(() => json(order()))]);
    authorizationHeaders.mockRejectedValue(new RangeError("bug"));

    await expect(loadOrder(ORDER_ID)).rejects.toThrow("bug");
  });
});

describe("readOrderResponse", () => {
  it("serves the order without caching it", async () => {
    mockFetch([ORDER_GET(() => json(order()))]);

    const response = await readOrderResponse(ORDER_ID);

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual(order());
  });

  it("answers a problem for an order that does not exist", async () => {
    const response = await readOrderResponse("nope");

    expect(response.status).toBe(404);
    expect(response.headers.get("content-type")).toBe("application/problem+json");
  });

  it("answers 503 with the retry hint when the orders service is down", async () => {
    mockFetch([ORDER_GET(() => new Response(JSON.stringify({ type: "x", title: "Down", status: 503 }), { status: 503, headers: { "content-type": "application/problem+json", "retry-after": "4" } }))]);
    const hinted = await readOrderResponse(ORDER_ID);
    expect(hinted.status).toBe(503);
    expect(hinted.headers.get("retry-after")).toBe("4");

    mockFetch([ORDER_GET(() => problem(500, "Oops"))]);
    const plain = await readOrderResponse(ORDER_ID);
    expect(plain.status).toBe(503);
    expect(plain.headers.get("retry-after")).toBeNull();
  });
});
