/**
 * @jest-environment node
 */
import { fetchOrder, isTerminalRequestError, ORDER_REQUEST_TIMEOUT_MS, OrderRequestError } from "../src/lib/order-client";
import { json, problem } from "./support/api";
import { ORDER_ID, order } from "./support/orders";

describe("fetchOrder", () => {
  it("reads the order from the store server with the session cookie, never following a redirect", async () => {
    const send = jest.fn(() => Promise.resolve(json(order())));
    global.fetch = send;

    expect(await fetchOrder(ORDER_ID)).toEqual(order());

    expect(send).toHaveBeenCalledWith(`/api/orders/${ORDER_ID}`, expect.objectContaining({ credentials: "same-origin", redirect: "manual" }));
  });

  it("aborts the request when the caller aborts", async () => {
    const send = jest.fn(() => Promise.resolve(json(order())));
    global.fetch = send;
    const controller = new AbortController();

    await fetchOrder(ORDER_ID, controller.signal);
    const sent = (send.mock.calls[0] as unknown as [string, RequestInit])[1].signal as AbortSignal;

    expect(sent.aborted).toBe(false);
    controller.abort();
    expect(sent.aborted).toBe(true);
  });

  it("gives every request a timeout, with or without a caller signal", async () => {
    const send = jest.fn(() => Promise.resolve(json(order())));
    global.fetch = send;
    const timeout = jest.spyOn(AbortSignal, "timeout");

    await fetchOrder(ORDER_ID);
    await fetchOrder(ORDER_ID, new AbortController().signal);

    expect(timeout).toHaveBeenNthCalledWith(1, ORDER_REQUEST_TIMEOUT_MS);
    expect(timeout).toHaveBeenNthCalledWith(2, ORDER_REQUEST_TIMEOUT_MS);
    timeout.mockRestore();
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
