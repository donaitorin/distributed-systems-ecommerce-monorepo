/**
 * @jest-environment node
 */
import { addToCart, clearCart, loadCart, loadCartCount, removeItem, setQuantity } from "../src/server/cart";
import { json, mockFetch, problem } from "./support/api";
import { cart, line } from "./support/cart";

const authorizationHeaders = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({
  authRuntime: () => ({ config: { apiBaseUrl: "http://gateway.test" } }),
  authorizationHeaders: () => authorizationHeaders() as unknown,
}));

beforeEach(() => {
  authorizationHeaders.mockReset();
  authorizationHeaders.mockResolvedValue({ authorization: "Bearer t" });
});

jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));

const CART = { method: "GET", path: "/api/v1/cart" };
const ITEM = (method: string) => ({ method, path: /^\/api\/v1\/cart\/items\/RS-001$/i });
const body = (call: { init: RequestInit } | undefined): unknown => JSON.parse((call?.init.body as string | undefined) ?? "null");

describe("loadCart", () => {
  it("reads the cart with the bearer token", async () => {
    const api = mockFetch([{ ...CART, respond: () => json(cart()) }]);

    expect(await loadCart()).toEqual(cart());
    expect(new Headers(api.calls[0]?.init.headers).get("authorization")).toBe("Bearer t");
  });

  it("sends an expired session to the login page and back to where it was", async () => {
    mockFetch([{ ...CART, respond: () => problem(401, "Unauthorized") }]);

    await expect(loadCart()).rejects.toThrow("NEXT_REDIRECT /login?next=%2Fcart&reason=expired");
    await expect(loadCart("/products/RS-001")).rejects.toThrow(
      "NEXT_REDIRECT /login?next=%2Fproducts%2FRS-001&reason=expired",
    );
  });

  it("returns a retryable failure for an unreachable cart", async () => {
    mockFetch([{ ...CART, respond: () => problem(503, "Down") }]);
    expect(await loadCart()).toEqual({ ok: false, kind: "unavailable" });

    global.fetch = jest.fn(() => Promise.reject(new TypeError("fetch failed")));
    expect(await loadCart()).toEqual({ ok: false, kind: "unavailable" });
  });

  it("keeps the retry hint of the gateway", async () => {
    mockFetch([
      { ...CART, respond: () => new Response(JSON.stringify({ type: "x", title: "Busy", status: 503 }), { status: 503, headers: { "content-type": "application/problem+json", "retry-after": "2" } }) },
    ]);

    expect(await loadCart()).toEqual({ ok: false, kind: "unavailable", retryAfterSeconds: 2 });
  });

  it("lets unexpected errors surface", async () => {
    authorizationHeaders.mockRejectedValue(new RangeError("bug"));

    await expect(loadCart()).rejects.toThrow("bug");
  });
});

describe("loadCartCount", () => {
  it("returns the number of units", async () => {
    mockFetch([{ ...CART, respond: () => json(cart()) }]);

    expect(await loadCartCount()).toBe(3);
  });

  it.each([401, 503])("returns null instead of failing the page on %i", async (status) => {
    mockFetch([{ ...CART, respond: () => problem(status, "No") }]);

    expect(await loadCartCount()).toBeNull();
  });
});

describe("setQuantity", () => {
  it("sends the quantity and returns the cart", async () => {
    const api = mockFetch([{ ...ITEM("PUT"), respond: () => json(cart()) }]);

    expect(await setQuantity("RS-001", 3)).toEqual({ ok: true, cart: cart() });
    expect(body(api.calls[0])).toEqual({ quantity: 3 });
  });

  it("sends the accepted price when there is one", async () => {
    const api = mockFetch([{ ...ITEM("PUT"), respond: () => json(cart()) }]);

    await setQuantity("RS-001", 2, "64.50");

    expect(body(api.calls[0])).toEqual({ quantity: 2, accepted_price: "64.50" });
  });

  it.each([0, 100, 1.5, Number.NaN])("does not call the API for quantity %s", async (quantity) => {
    const api = mockFetch([]);

    expect(await setQuantity("RS-001", quantity)).toEqual({ ok: false, kind: "invalid" });
    expect(await setQuantity("", 1)).toEqual({ ok: false, kind: "invalid" });
    expect(api.calls).toHaveLength(0);
  });

  it("tells a full cart from a changed price using the problem code", async () => {
    mockFetch([{ ...ITEM("PUT"), respond: () => problem(409, "Cart is full", { code: "cart_full", limit: 100 }) }]);
    expect(await setQuantity("RS-001", 1)).toEqual({ ok: false, kind: "cart_full" });

    mockFetch([{ ...ITEM("PUT"), respond: () => problem(409, "Price has changed", { code: "price_changed", current_price: "66.00" }) }]);
    expect(await setQuantity("RS-001", 1, "64.50")).toEqual({ ok: false, kind: "price_changed", currentPrice: "66.00" });

    mockFetch([{ ...ITEM("PUT"), respond: () => problem(409, "Conflict") }]);
    expect(await setQuantity("RS-001", 1, "64.50")).toEqual({ ok: false, kind: "price_changed" });
  });

  it("maps the other statuses", async () => {
    mockFetch([{ ...ITEM("PUT"), respond: () => problem(404, "Product not found") }]);
    expect(await setQuantity("RS-001", 1)).toEqual({ ok: false, kind: "not_found" });

    mockFetch([{ ...ITEM("PUT"), respond: () => problem(422, "Request validation failed") }]);
    expect(await setQuantity("RS-001", 1)).toEqual({ ok: false, kind: "invalid" });

    mockFetch([{ ...ITEM("PUT"), respond: () => problem(401, "Unauthorized") }]);
    await expect(setQuantity("RS-001", 1)).rejects.toThrow("NEXT_REDIRECT /login?next=%2Fcart&reason=expired");
  });
});

describe("removeItem and clearCart", () => {
  it("removes a line and returns the remaining cart", async () => {
    mockFetch([{ ...ITEM("DELETE"), respond: () => json(cart([])) }]);

    expect(await removeItem("RS-001")).toEqual({ ok: true, cart: cart([]) });
    expect(await removeItem("")).toEqual({ ok: false, kind: "invalid" });
  });

  it("reports a failure to remove", async () => {
    mockFetch([{ ...ITEM("DELETE"), respond: () => problem(503, "Down") }]);

    expect(await removeItem("RS-001")).toEqual({ ok: false, kind: "unavailable" });
  });

  it("clears the cart", async () => {
    const api = mockFetch([{ method: "DELETE", path: "/api/v1/cart", respond: () => new Response(null, { status: 204 }) }]);

    expect(await clearCart()).toEqual({ ok: true });
    expect(api.calls[0]?.url.pathname).toBe("/api/v1/cart");
  });

  it("reports a failure to clear", async () => {
    mockFetch([{ method: "DELETE", path: "/api/v1/cart", respond: () => problem(503, "Down") }]);

    expect(await clearCart()).toEqual({ ok: false, kind: "unavailable" });
  });
});

describe("addToCart", () => {
  const read = (items = [line({ quantity: 2 })]) => ({ ...CART, respond: () => json(cart(items)) });

  it("adds to what the cart already holds", async () => {
    const api = mockFetch([read(), { ...ITEM("PUT"), respond: () => json(cart()) }]);

    expect(await addToCart("RS-001", 3, "/products/RS-001")).toEqual({ ok: true, quantity: 5, capped: false });
    expect(body(api.calls[1])).toEqual({ quantity: 5 });
  });

  it("starts a new line", async () => {
    const api = mockFetch([read([]), { ...ITEM("PUT"), respond: () => json(cart()) }]);

    expect(await addToCart("rs-001", 1, "/products/RS-001")).toEqual({ ok: true, quantity: 1, capped: false });
    expect(body(api.calls[1])).toEqual({ quantity: 1 });
  });

  it("stops at 99 and says so", async () => {
    const api = mockFetch([read([line({ quantity: 98 })]), { ...ITEM("PUT"), respond: () => json(cart()) }]);

    expect(await addToCart("RS-001", 5, "/products/RS-001")).toEqual({ ok: true, quantity: 99, capped: true });
    expect(body(api.calls[1])).toEqual({ quantity: 99 });
  });

  it("does not call the API for an invalid quantity", async () => {
    const api = mockFetch([]);

    expect(await addToCart("RS-001", 0, "/products/RS-001")).toEqual({ ok: false, kind: "invalid" });
    expect(await addToCart("", 1, "/products/RS-001")).toEqual({ ok: false, kind: "invalid" });
    expect(api.calls).toHaveLength(0);
  });

  it("reports the limit of 100 products and the retired product", async () => {
    mockFetch([read(), { ...ITEM("PUT"), respond: () => problem(409, "Cart is full", { code: "cart_full" }) }]);
    expect(await addToCart("RS-001", 1, "/products/RS-001")).toEqual({ ok: false, kind: "cart_full" });

    mockFetch([read(), { ...ITEM("PUT"), respond: () => problem(404, "Product not found") }]);
    expect(await addToCart("RS-001", 1, "/products/RS-001")).toEqual({ ok: false, kind: "not_found" });
  });

  it("returns to the product after signing in again when the session expired", async () => {
    mockFetch([{ ...CART, respond: () => problem(401, "Unauthorized") }]);

    await expect(addToCart("RS-001", 1, "/products/RS-001")).rejects.toThrow(
      "NEXT_REDIRECT /login?next=%2Fproducts%2FRS-001&reason=expired",
    );
  });
});
