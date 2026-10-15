const FALLBACK = "/";

export function safeRedirectPath(candidate: string | null | undefined, fallback = FALLBACK): string {
  if (!candidate || !candidate.startsWith("/") || candidate.startsWith("//")) {
    return fallback;
  }
  if (candidate.includes("\\") || [...candidate].some((character) => character.charCodeAt(0) < 32)) {
    return fallback;
  }
  return candidate;
}
