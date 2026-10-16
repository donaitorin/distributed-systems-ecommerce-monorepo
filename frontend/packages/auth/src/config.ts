export type AuthConfig = {
  apiBaseUrl: string;
  jwksUrl: string;
  issuer: string;
  audience: string;
  secureCookies: boolean;
  accessCookieName: string;
  refreshCookieName: string;
  refreshCookieMaxAgeSeconds: number;
  requestTimeoutMs: number;
};

export type Environment = Record<string, string | undefined>;

const DEFAULT_ISSUER = "ecommerce-auth";
const DEFAULT_AUDIENCE = "ecommerce-api";
const DEFAULT_REFRESH_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60;
const DEFAULT_REQUEST_TIMEOUT_MS = 5_000;
const JWKS_PATH = "/api/v1/auth/.well-known/jwks.json";

function required(environment: Environment, name: string): string {
  const value = environment[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

function booleanFlag(environment: Environment, name: string, fallback: boolean): boolean {
  const value = environment[name]?.trim().toLowerCase();
  if (value === undefined || value === "") {
    return fallback;
  }
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  throw new Error(`${name} must be "true" or "false"`);
}

function positiveInteger(environment: Environment, name: string, fallback: number): number {
  const raw = environment[name]?.trim();
  if (!raw) {
    return fallback;
  }
  const value = Number(raw);
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`${name} must be a positive integer`);
  }
  return value;
}

export function loadAuthConfig(environment: Environment): AuthConfig {
  const apiBaseUrl = required(environment, "API_BASE_URL").replace(/\/+$/, "");
  return {
    apiBaseUrl,
    jwksUrl: environment.AUTH_JWKS_URL?.trim() || `${apiBaseUrl}${JWKS_PATH}`,
    issuer: environment.JWT_ISSUER?.trim() || DEFAULT_ISSUER,
    audience: environment.JWT_AUDIENCE?.trim() || DEFAULT_AUDIENCE,
    secureCookies: booleanFlag(environment, "AUTH_COOKIE_SECURE", true),
    accessCookieName: "ecommerce_access",
    refreshCookieName: "ecommerce_refresh",
    refreshCookieMaxAgeSeconds: positiveInteger(
      environment,
      "AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS",
      DEFAULT_REFRESH_COOKIE_MAX_AGE_SECONDS,
    ),
    requestTimeoutMs: positiveInteger(
      environment,
      "AUTH_REQUEST_TIMEOUT_MS",
      DEFAULT_REQUEST_TIMEOUT_MS,
    ),
  };
}
