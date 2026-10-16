import { loadAuthConfig } from "../src";

const BASE = { API_BASE_URL: "http://gateway:80/" };

describe("loadAuthConfig", () => {
  it("applies secure defaults", () => {
    expect(loadAuthConfig(BASE)).toEqual({
      apiBaseUrl: "http://gateway:80",
      jwksUrl: "http://gateway:80/api/v1/auth/.well-known/jwks.json",
      issuer: "ecommerce-auth",
      audience: "ecommerce-api",
      secureCookies: true,
      accessCookieName: "ecommerce_access",
      refreshCookieName: "ecommerce_refresh",
      refreshCookieMaxAgeSeconds: 604800,
      requestTimeoutMs: 5000,
    });
  });

  it("requires the API base URL", () => {
    expect(() => loadAuthConfig({})).toThrow("API_BASE_URL is required");
    expect(() => loadAuthConfig({ API_BASE_URL: "  " })).toThrow("API_BASE_URL is required");
  });

  it("allows insecure cookies only when explicitly disabled", () => {
    expect(loadAuthConfig({ ...BASE, AUTH_COOKIE_SECURE: "false" }).secureCookies).toBe(false);
    expect(loadAuthConfig({ ...BASE, AUTH_COOKIE_SECURE: "TRUE" }).secureCookies).toBe(true);
    expect(loadAuthConfig({ ...BASE, AUTH_COOKIE_SECURE: "" }).secureCookies).toBe(true);
  });

  it("rejects an ambiguous secure flag instead of guessing", () => {
    expect(() => loadAuthConfig({ ...BASE, AUTH_COOKIE_SECURE: "0" })).toThrow('must be "true" or "false"');
  });

  it("reads overrides", () => {
    const config = loadAuthConfig({
      ...BASE,
      AUTH_JWKS_URL: "http://auth:8000/jwks",
      JWT_ISSUER: "issuer",
      JWT_AUDIENCE: "audience",
      AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS: "60",
      AUTH_REQUEST_TIMEOUT_MS: "250",
    });

    expect(config).toMatchObject({
      jwksUrl: "http://auth:8000/jwks",
      issuer: "issuer",
      audience: "audience",
      refreshCookieMaxAgeSeconds: 60,
      requestTimeoutMs: 250,
    });
  });

  it.each(["0", "-5", "1.5", "abc"])("rejects %p as a number of seconds", (value) => {
    expect(() => loadAuthConfig({ ...BASE, AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS: value })).toThrow(
      "positive integer",
    );
  });
});
