export const LOGIN_PATH = "/login";
export const PROTECTED_PREFIXES = ["/account", "/checkout", "/orders"] as const;

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}
