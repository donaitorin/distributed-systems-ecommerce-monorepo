/**
 * @jest-environment node
 */
import { fetchOrder, isTerminalRequestError, OrderRequestError } from "../src/lib/order-client";
import { json, problem } from "./support/api";
import { ORDER_ID, order } from "./support/orders";

describe("fetchOrder", () => {
  it("reads the order from the store server with the session cookie, never following a redirect", async () => {
    const send = jest.fn(() => Promise.resolve(json(order())));
    global.fetch = send;

    expect(await fetchOrder(ORDER_ID)).toEqual(order());

    expect(send).toHaveBeenCalledWith(`/api/orders/${ORDER_ID}`, expect.objectContaining({ credentials: "same-origin", redirect: "manual" }));
  });

  it("passes the abort signal on", async () => {
    const send = jest.fn(() => Promise.resolve(json(order())));
    global.fetch = send;
    const controller = new AbortController();

    await fetchOrder(ORDER_ID, controller.signal);

    expect(send).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ signal: controller.signal }));
  });

  it("reports a redirect to the login page as an expired session", async () => {
    global.fetch = jest.fn(() => Promise.resolve({ type: "opaqueredirect", ok: false, status: 0 } as unknown as Response));

    await expect(fetchOrder(ORDER_ID)).rejects.toMatchObject({ status: 401 });
  });

  it("reports a failed response with its status", async () => {
    global.fetch = jest.fn(() => Promise.resolve(problem(503, "Down")));

    await expect(fetchOrder(ORDER_ID)).rejects.toMatchObject({ name: "OrderRequestError", status: 503 });
  });

  it("reports a network failure without a status", async () => {
    global.fetch = jest.fn(() => Promise.reject(new TypeError("fetch failed")));

    const error = await fetchOrder(ORDER_ID).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(OrderRequestError);
    expect(error).toMatchObject({ status: null, message: "The server could not be reached" });
  });
});

describe("isTerminalRequestError", () => {
  it.each([
    [new OrderRequestError(401), true],
    [new OrderRequestError(404), true],
    [new OrderRequestError(503), false],
    [new OrderRequestError(null), false],
    [new Error("x"), false],
    [null, false],
  ])("%s is terminal: %s", (error, expected) => {
    expect(isTerminalRequestError(error)).toBe(expected);
  });
});
