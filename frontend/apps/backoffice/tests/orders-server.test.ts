/**
 * @jest-environment node
 */
import { loadOrder, loadOrderPage } from "../src/server/orders";
import { json, mockFetch, ORDER_ID, orderDetail, orderRow, payment, problem } from "./support/api";

jest.mock("@ecommerce/auth/next", () => ({
  authRuntime: () => ({ config: { apiBaseUrl: "http://gateway.test" } }),
  authorizationHeaders: () => Promise.resolve({ authorization: "Bearer t" }),
}));
jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));

const LIST = { method: "GET", path: "/api/v1/admin/orders" };
const DETAIL = { method: "GET", path: `/api/v1/admin/orders/${ORDER_ID}` };
const PAYMENT = { method: "GET", path: `/api/v1/payments/${ORDER_ID}` };
const STATE = { status: null, from: null, to: null, limit: 25, cursor: null } as const;

describe("loadOrderPage", () => {
  it("sends the filters as query parameters, with the days as a UTC range", async () => {
    const api = mockFetch([{ ...LIST, respond: () => json({ items: [orderRow()], next_cursor: "n" }) }]);

    const result = await loadOrderPage({ status: "CANCELLED", from: "2026-10-01", to: "2026-10-17", limit: 50, cursor: "c" });

    expect(result).toEqual({ items: [orderRow()], next_cursor: "n" });
    expect(Object.fromEntries(api.calls[0]?.url.searchParams ?? [])).toEqual({
      status: "CANCELLED",
      created_from: "2026-10-01T00:00:00Z",
      created_to: "2026-10-18T00:00:00Z",
      limit: "50",
      cursor: "c",
    });
    expect(new Headers(api.calls[0]?.init.headers).get("authorization")).toBe("Bearer t");
  });

  it("returns a rejected cursor as a failure with its field", async () => {
    mockFetch([
      {
        ...LIST,
        respond: () => problem(422, "Invalid", { errors: [{ location: "query.cursor", message: "bad", type: "value_error" }] }),
      },
    ]);

    expect(await loadOrderPage({ ...STATE, cursor: "old" })).toMatchObject({ ok: false, status: 422, fieldErrors: { cursor: "bad" } });
  });

  it("sends an expired session to the login page and a customer session back to it with a reason", async () => {
    mockFetch([{ ...LIST, respond: () => problem(401, "Unauthorized") }]);
    await expect(loadOrderPage(STATE)).rejects.toThrow("NEXT_REDIRECT /login?reason=expired");

    mockFetch([{ ...LIST, respond: () => problem(403, "Forbidden") }]);
    await expect(loadOrderPage(STATE)).rejects.toThrow("NEXT_REDIRECT /login?reason=forbidden");
  });
});

describe("loadOrder", () => {
  it("reads the order and its payment", async () => {
    mockFetch([
      { ...DETAIL, respond: () => json(orderDetail()) },
      { ...PAYMENT, respond: () => json(payment()) },
    ]);

    expect(await loadOrder(ORDER_ID)).toEqual({ order: orderDetail(), payment: { payment: payment() } });
  });

  it("says there is no payment when the payments service has none", async () => {
    mockFetch([
      { ...DETAIL, respond: () => json(orderDetail({ status: "CANCELLED", cancel_reason: "insufficient_stock" })) },
      { ...PAYMENT, respond: () => problem(404, "Not found") },
    ]);

    expect(await loadOrder(ORDER_ID)).toMatchObject({ payment: { payment: null, unavailable: false } });
  });

  it("still shows the order when the payment cannot be read", async () => {
    mockFetch([
      { ...DETAIL, respond: () => json(orderDetail()) },
      { ...PAYMENT, respond: () => problem(503, "Down") },
    ]);

    expect(await loadOrder(ORDER_ID)).toMatchObject({ order: orderDetail(), payment: { payment: null, unavailable: true } });
  });

  it("does not ask for a payment when the order is missing", async () => {
    const api = mockFetch([{ ...DETAIL, respond: () => problem(404, "Not found") }]);

    expect(await loadOrder(ORDER_ID)).toMatchObject({ ok: false, status: 404 });
    expect(api.calls).toHaveLength(1);
  });

  it("does not call anything for an id that is not a UUID", async () => {
    const api = mockFetch([]);

    expect(await loadOrder("../users")).toMatchObject({ ok: false, status: 404 });
    expect(api.calls).toHaveLength(0);
  });

  it("returns an unavailable orders service as a failure", async () => {
    mockFetch([{ ...DETAIL, respond: () => problem(503, "Down") }]);

    expect(await loadOrder(ORDER_ID)).toMatchObject({ ok: false, status: 503 });
  });
});
