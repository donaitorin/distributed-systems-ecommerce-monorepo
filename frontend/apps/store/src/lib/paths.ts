export const LOGIN_PATH = "/login";
export const PRODUCTS_PATH = "/products";
export const PROTECTED_PREFIXES = ["/account", "/checkout", "/orders"] as const;

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export function productHref(sku: string): string {
  return `${PRODUCTS_PATH}/${encodeURIComponent(sku)}`;
}

export function categoryHref(slug: string): string {
  return `${PRODUCTS_PATH}?category=${encodeURIComponent(slug)}`;
}
