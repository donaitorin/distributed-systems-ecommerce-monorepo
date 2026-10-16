import type { CookieSpec } from "../cookies";

export function withCookies(header: string | null, specs: readonly CookieSpec[]): string {
  const entries = new Map<string, string>();
  for (const part of (header ?? "").split(";")) {
    const pair = part.trim();
    const separator = pair.indexOf("=");
    if (separator > 0) {
      entries.set(pair.slice(0, separator), pair.slice(separator + 1));
    }
  }
  for (const { name, value } of specs) {
    if (value === "") {
      entries.delete(name);
    } else {
      entries.set(name, value);
    }
  }
  return [...entries].map(([name, value]) => `${name}=${value}`).join("; ");
}
