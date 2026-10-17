import { redirect } from "next/navigation";
import { ApiError, ApiNetworkError, createApiClient, type CartPaths } from "@ecommerce/api-client";
import { authorizationHeaders, authRuntime } from "@ecommerce/auth/next";
import {
  isValidQuantity,
  MAX_QUANTITY,
  type AddResult,
  type Cart,
  type CartFailure,
  type CartResult,
  type ClearResult,
} from "../lib/cart";
import { CART_PATH, LOGIN_PATH } from "../lib/paths";

const UNAUTHORIZED = 401;
const NOT_FOUND = 404;
const CONFLICT = 409;
const UNPROCESSABLE = 422;

export function cartApi() {
  return createApiClient<CartPaths>({
    baseUrl: authRuntime().config.apiBaseUrl,
    headers: authorizationHeaders,
  });
}

function expiredSession(returnTo: string): never {
  return redirect(`${LOGIN_PATH}?next=${encodeURIComponent(returnTo)}&reason=expired`);
}

function failureOf(error: ApiError): CartFailure {
  switch (error.status) {
    case NOT_FOUND:
      return { ok: false, kind: "not_found" };
    case UNPROCESSABLE:
      return { ok: false, kind: "invalid" };
    case CONFLICT:
      return error.problem.code === "cart_full"
        ? { ok: false, kind: "cart_full" }
        : {
            ok: false,
            kind: "price_changed",
            ...(typeof error.problem.current_price === "string" ? { currentPrice: error.problem.current_price } : {}),
          };
    default:
      return {
        ok: false,
        kind: "unavailable",
        ...(error.retryAfterSeconds !== undefined ? { retryAfterSeconds: error.retryAfterSeconds } : {}),
      };
  }
}

async function guarded<Value>(returnTo: string, work: () => Promise<Value>): Promise<Value | CartFailure> {
  try {
    return await work();
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === UNAUTHORIZED) {
        expiredSession(returnTo);
      }
      return failureOf(error);
    }
    if (error instanceof ApiNetworkError) {
      return { ok: false, kind: "unavailable" };
    }
    throw error;
  }
}

export function loadCart(returnTo: string = CART_PATH): Promise<Cart | CartFailure> {
  return guarded(returnTo, async () => (await cartApi().get("/api/v1/cart")).data);
}

export async function loadCartCount(): Promise<number | null> {
  try {
    return (await cartApi().get("/api/v1/cart")).data.item_count;
  } catch {
    return null;
  }
}

export async function setQuantity(sku: string, quantity: number, acceptedPrice?: string): Promise<CartResult> {
  if (!sku || !isValidQuantity(quantity)) {
    return { ok: false, kind: "invalid" };
  }
  const result = await guarded(CART_PATH, async () => {
    const body = acceptedPrice ? { quantity, accepted_price: acceptedPrice } : { quantity };
    return (await cartApi().put("/api/v1/cart/items/{sku}", { params: { sku }, body })).data;
  });
  return "ok" in result ? result : { ok: true, cart: result };
}

export async function removeItem(sku: string): Promise<CartResult> {
  if (!sku) {
    return { ok: false, kind: "invalid" };
  }
  const result = await guarded(CART_PATH, async () => (await cartApi().delete("/api/v1/cart/items/{sku}", { params: { sku } })).data);
  return "ok" in result ? result : { ok: true, cart: result };
}

export async function clearCart(): Promise<ClearResult> {
  const result = await guarded(CART_PATH, async () => {
    await cartApi().delete("/api/v1/cart");
    return { ok: true } as const;
  });
  return result;
}

export async function addToCart(sku: string, quantity: number, returnTo: string): Promise<AddResult> {
  if (!sku || !isValidQuantity(quantity)) {
    return { ok: false, kind: "invalid" };
  }
  const result = await guarded(returnTo, async () => {
    const api = cartApi();
    const current = (await api.get("/api/v1/cart")).data;
    const already = current.items.find((line) => line.sku === sku.toUpperCase())?.quantity ?? 0;
    const wanted = Math.min(already + quantity, MAX_QUANTITY);
    await api.put("/api/v1/cart/items/{sku}", { params: { sku }, body: { quantity: wanted } });
    return { ok: true, quantity: wanted, capped: already + quantity > MAX_QUANTITY } as const;
  });
  return result;
}
