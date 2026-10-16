import { safeRedirectPath } from "@ecommerce/auth/redirect";

export type NextPathOptions = {
  fallback: string;
  loopPaths: readonly string[];
  zonePath?: string;
};

function startsWithPath(path: string, base: string): boolean {
  return path === base || [`${base}?`, `${base}/`, `${base}#`].some((prefix) => path.startsWith(prefix));
}

function insideZone(path: string, zonePath: string, fallback: string): string {
  const stripped = startsWithPath(path, zonePath) ? path.slice(zonePath.length) : path;
  if (stripped === "") {
    return fallback;
  }
  return stripped.startsWith("/") ? stripped : `/${stripped}`;
}

export function nextPath(candidate: string | null | undefined, options: NextPathOptions): string {
  const { fallback, loopPaths, zonePath } = options;
  const safe = safeRedirectPath(candidate, fallback);
  const local = zonePath === undefined ? safe : safeRedirectPath(insideZone(safe, zonePath, fallback), fallback);
  return loopPaths.some((path) => startsWithPath(local, path)) ? fallback : local;
}
