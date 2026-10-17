import { nextPath } from "@ecommerce/web-core";

export const LOGIN_PATH = "/login";
export const REGISTER_PATH = "/register";
export const ACCOUNT_PATH = "/account";
export const PRODUCTS_PATH = "/products";
export const CART_PATH = "/cart";
export const CHECKOUT_PATH = "/checkout";
export const ORDERS_PATH = "/orders";
export const ORDERS_API_PATH = "/api/orders";
export const PROTECTED_PREFIXES = [ACCOUNT_PATH, CART_PATH, CHECKOUT_PATH, ORDERS_PATH, ORDERS_API_PATH] as const;

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export function productHref(sku: string): string {
  return `${PRODUCTS_PATH}/${encodeURIComponent(sku)}`;
}

export function orderHref(orderId: string): string {
  return `${ORDERS_PATH}/${encodeURIComponent(orderId)}`;
}

export function categoryHref(slug: string): string {
  return `${PRODUCTS_PATH}?category=${encodeURIComponent(slug)}`;
}

export function storeNextPath(candidate: string | null | undefined): string {
  return nextPath(candidate, { fallback: PRODUCTS_PATH, loopPaths: [LOGIN_PATH, REGISTER_PATH] });
}

export function authPageHref(path: typeof LOGIN_PATH | typeof REGISTER_PATH, next: string): string {
  return next === PRODUCTS_PATH ? path : `${path}?next=${encodeURIComponent(next)}`;
}
