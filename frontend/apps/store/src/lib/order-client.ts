import { timeoutSignal } from "@ecommerce/web-core";
import type { Order } from "./orders";
import { ORDERS_API_PATH } from "./paths";

export type OrderFetcher = (orderId: string, signal?: AbortSignal) => Promise<Order>;

export class OrderRequestError extends Error {
  readonly status: number | null;

  constructor(status: number | null) {
    super(status === null ? "The server could not be reached" : `Request failed with status ${status}`);
    this.name = "OrderRequestError";
    this.status = status;
  }
}

export const SESSION_EXPIRED = 401;
export const ORDER_REQUEST_TIMEOUT_MS = 10_000;

export function isTerminalRequestError(error: unknown): boolean {
  return error instanceof OrderRequestError && (error.status === SESSION_EXPIRED || error.status === 404);
}

export const fetchOrder: OrderFetcher = async (orderId, signal) => {
  let response: Response;
  try {
    response = await fetch(`${ORDERS_API_PATH}/${encodeURIComponent(orderId)}`, {
      credentials: "same-origin",
      redirect: "manual",
      headers: { accept: "application/json" },
      signal: timeoutSignal(ORDER_REQUEST_TIMEOUT_MS, signal),
    });
  } catch {
    throw new OrderRequestError(null);
  }
  if (response.type === "opaqueredirect") {
    throw new OrderRequestError(SESSION_EXPIRED);
  }
  if (!response.ok) {
    throw new OrderRequestError(response.status);
  }
  return (await response.json()) as Order;
};
