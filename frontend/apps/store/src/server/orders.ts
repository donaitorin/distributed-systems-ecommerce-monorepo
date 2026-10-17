import { redirect } from "next/navigation";
import { ApiError, ApiNetworkError, createApiClient, type OrdersPaths } from "@ecommerce/api-client";
import { authorizationHeaders, authRuntime } from "@ecommerce/auth/next";
import { isCartFailure, type Cart } from "../lib/cart";
import {
  blockedLines,
  cartFingerprint,
  isAttemptKey,
  isValidCardNumber,
  type PlaceOrderFailure,
  type PlaceOrderInput,
  type PlaceOrderResult,
} from "../lib/checkout";
import type { Address } from "../lib/addresses";
import { ORDER_PAGE_SIZE, type Order, type OrderFailure, type OrderListFailure, type OrderPage } from "../lib/orders";
import { CHECKOUT_PATH, LOGIN_PATH, ORDERS_PATH, orderHref } from "../lib/paths";
import { loadAddresses } from "./addresses";
import { loadCart } from "./cart";

const UNAUTHORIZED = 401;
const NOT_FOUND = 404;
const TOO_MANY_REQUESTS = 429;
const UNPROCESSABLE = 422;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const NO_STORE = { "cache-control": "no-store" };

export function isOrderId(value: string): boolean {
  return UUID.test(value);
}

export function ordersApi() {
  return createApiClient<OrdersPaths>({
    baseUrl: authRuntime().config.apiBaseUrl,
    headers: authorizationHeaders,
  });
}

function expiredSession(returnTo: string): never {
  return redirect(`${LOGIN_PATH}?next=${encodeURIComponent(returnTo)}&reason=expired`);
}

function failure(kind: PlaceOrderFailure["kind"], extra: Partial<PlaceOrderFailure> = {}): PlaceOrderFailure {
  return { ok: false, kind, ...extra };
}

function locationsOf(error: ApiError): string[] {
  return (error.problem.errors ?? []).map((item) => item.location);
}

function placementFailure(error: ApiError): PlaceOrderFailure {
  if (error.status === UNPROCESSABLE) {
    if (error.problem.code === "idempotency_key_reused") {
      return failure("attempt_changed");
    }
    const locations = locationsOf(error);
    if (locations.some((location) => location.startsWith("body.payment"))) {
      return failure("invalid_card");
    }
    if (locations.some((location) => location.startsWith("body.shipping_address"))) {
      return failure("invalid_address");
    }
    return failure("invalid");
  }
  if (error.status === TOO_MANY_REQUESTS) {
    return failure("rate_limited", error.retryAfterSeconds !== undefined ? { retryAfterSeconds: error.retryAfterSeconds } : {});
  }
  return failure(
    "unavailable",
    error.retryAfterSeconds !== undefined ? { retryAfterSeconds: error.retryAfterSeconds } : {},
  );
}

function orderBody(cart: Cart, address: Address, cardNumber: string) {
  return {
    lines: cart.items.map((line) => ({ sku: line.sku, quantity: line.quantity, unit_price: line.price })),
    shipping_address: {
      recipient_name: address.recipient_name,
      line1: address.line1,
      line2: address.line2,
      city: address.city,
      region: address.region,
      postal_code: address.postal_code,
      country: address.country,
      phone: address.phone,
    },
    payment: { card_number: cardNumber.replace(/[\s-]/g, "") },
  };
}

function inputProblem(input: PlaceOrderInput): PlaceOrderFailure | undefined {
  if (!isAttemptKey(input.attemptKey) || !UUID.test(input.addressId)) {
    return failure("invalid");
  }
  return isValidCardNumber(input.cardNumber) ? undefined : failure("invalid_card");
}

export async function placeOrder(input: PlaceOrderInput): Promise<PlaceOrderResult> {
  const problem = inputProblem(input);
  if (problem) {
    return problem;
  }
  const [cart, addresses] = await Promise.all([loadCart(CHECKOUT_PATH), loadAddresses(CHECKOUT_PATH)]);
  if (isCartFailure(cart) || !Array.isArray(addresses)) {
    return failure("unavailable");
  }
  if (cart.items.length === 0) {
    return failure("empty_cart");
  }
  if (blockedLines(cart).length > 0) {
    return failure("cart_flagged");
  }
  if (cartFingerprint(cart) !== input.cartFingerprint) {
    return failure("cart_changed");
  }
  const address = addresses.find((candidate) => candidate.id === input.addressId);
  if (!address) {
    return failure("address_missing");
  }
  try {
    const { data } = await ordersApi().post("/api/v1/orders", {
      body: orderBody(cart, address, input.cardNumber),
      headers: { "Idempotency-Key": input.attemptKey },
    });
    return { ok: true, orderId: data.id };
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === UNAUTHORIZED) {
        expiredSession(CHECKOUT_PATH);
      }
      return placementFailure(error);
    }
    if (error instanceof ApiNetworkError) {
      return failure("unavailable");
    }
    throw error;
  }
}

export async function loadOrder(orderId: string, returnTo: string = orderHref(orderId)): Promise<Order | OrderFailure> {
  if (!isOrderId(orderId)) {
    return { ok: false, kind: "not_found" };
  }
  try {
    const { data } = await ordersApi().get("/api/v1/orders/{order_id}", { params: { order_id: orderId } });
    return data;
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === UNAUTHORIZED) {
        expiredSession(returnTo);
      }
      return error.status === NOT_FOUND || error.status === UNPROCESSABLE
        ? { ok: false, kind: "not_found" }
        : {
            ok: false,
            kind: "unavailable",
            ...(error.retryAfterSeconds !== undefined ? { retryAfterSeconds: error.retryAfterSeconds } : {}),
          };
    }
    if (error instanceof ApiNetworkError) {
      return { ok: false, kind: "unavailable" };
    }
    throw error;
  }
}

export async function loadOrderPage(cursor: string | null): Promise<OrderPage | OrderListFailure> {
  try {
    const { data } = await ordersApi().get("/api/v1/orders", {
      query: { limit: ORDER_PAGE_SIZE, ...(cursor ? { cursor } : {}) },
    });
    return data;
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === UNAUTHORIZED) {
        expiredSession(cursor ? `${ORDERS_PATH}?cursor=${cursor}` : ORDERS_PATH);
      }
      if (error.status === UNPROCESSABLE) {
        return { ok: false, kind: "invalid_cursor" };
      }
      return {
        ok: false,
        kind: "unavailable",
        ...(error.retryAfterSeconds !== undefined ? { retryAfterSeconds: error.retryAfterSeconds } : {}),
      };
    }
    if (error instanceof ApiNetworkError) {
      return { ok: false, kind: "unavailable" };
    }
    throw error;
  }
}

function problemResponse(status: number, title: string, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify({ type: "about:blank", title, status }), {
    status,
    headers: { "content-type": "application/problem+json", ...NO_STORE, ...headers },
  });
}

export async function readOrderResponse(orderId: string): Promise<Response> {
  const order = await loadOrder(orderId);
  if ("kind" in order) {
    return order.kind === "not_found"
      ? problemResponse(NOT_FOUND, "Order not found")
      : problemResponse(
          503,
          "Order status unavailable",
          order.retryAfterSeconds !== undefined ? { "retry-after": String(order.retryAfterSeconds) } : {},
        );
  }
  return Response.json(order, { headers: NO_STORE });
}
