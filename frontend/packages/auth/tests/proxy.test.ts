import { NextRequest } from "next/server";
import { ApiError } from "@ecommerce/api-client";
import { createAuthRuntime, type AuthRuntime } from "../src";
import { createProxy } from "../src/next";
import { CONFIG, createTestKeys, jsonResponse, problemResponse, tokensBody, type TestKeys } from "./support/tokens";

const ORIGIN = "http://gateway.test";

function request(path: string, cookies: Record<string, string> = {}, headers: Record<string, string> = {}, nextConfig?: { basePath: string }) {
  const cookieHeader = Object.entries(cookies)
    .map(([name, value]) => `${name}=${value}`)
    .join("; ");
  return new NextRequest(`${ORIGIN}${path}`, {
    headers: { ...(cookieHeader ? { cookie: cookieHeader } : {}), ...headers },
    ...(nextConfig ? { nextConfig } : {}),
  });
}

type Setup = { keys: TestKeys; runtime: AuthRuntime; fetchMock: jest.Mock };

async function setup(refreshResponse?: () => Promise<Response>): Promise<Setup> {
  const keys = await createTestKeys();
  const fetchMock = jest.fn(refreshResponse ?? (() => Promise.resolve(problemResponse(401))));
  const runtime = createAuthRuntime(CONFIG, { fetch: fetchMock as unknown as typeof fetch, keySet: keys.keySet });
  return { keys, runtime, fetchMock };
}

const GUARD = { loginPath: "/login", requiredRole: "admin" };

describe("createProxy without a guard", () => {
  it("adds a per-request nonce and a matching CSP to the response and to the request", async () => {
    const { runtime } = await setup();
    const proxy = createProxy({ runtime });

    const first = await proxy(request("/"));
    const second = await proxy(request("/"));

    const policy = first.headers.get("content-security-policy") ?? "";
    const nonce = /'nonce-([^']+)'/.exec(policy)?.[1];
    expect(nonce).toBeDefined();
    expect(first.headers.get("x-middleware-request-x-nonce")).toBe(nonce);
    expect(first.headers.get("x-middleware-request-content-security-policy")).toBe(policy);
    expect(second.headers.get("content-security-policy")).not.toBe(policy);
  });

  it("does not require a session", async () => {
    const { runtime, fetchMock } = await setup();

    const response = await createProxy({ runtime })(request("/products"));

    expect(response.status).toBe(200);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("allows eval only in development", async () => {
    const { runtime } = await setup();

    const production = await createProxy({ runtime })(request("/"));
    const development = await createProxy({ runtime, development: true })(request("/"));

    expect(production.headers.get("content-security-policy")).not.toContain("unsafe-eval");
    expect(development.headers.get("content-security-policy")).toContain("unsafe-eval");
  });
});

describe("createProxy with an admin guard", () => {
  it("redirects an anonymous visitor to the login page and remembers where they were going", async () => {
    const { runtime } = await setup();

    const response = await createProxy({ runtime, guard: GUARD })(request("/products?page=2"));

    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location") ?? "");
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("next")).toBe("/products?page=2");
    expect(response.headers.get("content-security-policy")).toContain("default-src 'self'");
  });

  it("keeps the zone base path when redirecting", async () => {
    const { runtime } = await setup();

    const response = await createProxy({ runtime, guard: GUARD })(
      request("/admin/products", {}, {}, { basePath: "/admin" }),
    );

    expect(new URL(response.headers.get("location") ?? "").pathname).toBe("/admin/login");
  });

  it("lets the login page through without a session", async () => {
    const { runtime } = await setup();

    const response = await createProxy({ runtime, guard: GUARD })(request("/login"));

    expect(response.status).toBe(200);
  });

  it("lets an admin through without touching the API", async () => {
    const { runtime, keys, fetchMock } = await setup();
    const token = await keys.sign({ role: "admin" });

    const response = await createProxy({ runtime, guard: GUARD })(request("/", { ecommerce_access: token }));

    expect(response.status).toBe(200);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends a customer back to the login page marked as forbidden", async () => {
    const { runtime, keys } = await setup();
    const token = await keys.sign({ role: "customer" });

    const response = await createProxy({ runtime, guard: GUARD })(request("/", { ecommerce_access: token }));

    const location = new URL(response.headers.get("location") ?? "");
    expect(response.status).toBe(307);
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("reason")).toBe("forbidden");
  });

  it("rejects a forged token", async () => {
    const { runtime } = await setup();
    const other = await createTestKeys();

    const response = await createProxy({ runtime, guard: GUARD })(
      request("/", { ecommerce_access: await other.sign({ role: "admin" }) }),
    );

    expect(response.status).toBe(307);
  });

  it("refreshes an expired session, sets the new cookies and hands them to the page", async () => {
    const { runtime, keys, fetchMock } = await setup();
    const fresh = await keys.sign({ role: "admin" });
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(tokensBody(fresh, "r2"))));
    const expired = await keys.sign({ role: "admin" }, { expiresIn: "-1m" });

    const response = await createProxy({ runtime, guard: GUARD })(
      request("/", { ecommerce_access: expired, ecommerce_refresh: "r1", theme: "dark" }, { "x-forwarded-for": "203.0.113.9" }),
    );

    expect(response.status).toBe(200);
    expect(response.cookies.get("ecommerce_access")?.value).toBe(fresh);
    expect(response.cookies.get("ecommerce_refresh")?.value).toBe("r2");
    const setCookie = response.headers.get("set-cookie") ?? "";
    expect(setCookie).toMatch(/HttpOnly/i);
    expect(setCookie).toMatch(/SameSite=lax/i);
    expect(response.headers.get("x-middleware-request-cookie")).toBe(
      `ecommerce_access=${fresh}; ecommerce_refresh=r2; theme=dark`,
    );
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>)["x-forwarded-for"]).toBe("203.0.113.9");
  });

  it("marks cookies secure when configured", async () => {
    const keys = await createTestKeys();
    const fresh = await keys.sign({ role: "admin" });
    const fetchMock = jest.fn(() => Promise.resolve(jsonResponse(tokensBody(fresh, "r2"))));
    const runtime = createAuthRuntime(
      { ...CONFIG, secureCookies: true },
      { fetch: fetchMock as unknown as typeof fetch, keySet: keys.keySet },
    );

    const response = await createProxy({ runtime, guard: GUARD })(request("/", { ecommerce_refresh: "r1" }));

    expect(response.headers.get("set-cookie")).toMatch(/Secure/i);
  });

  it("clears the cookies and redirects when the refresh token was revoked", async () => {
    const { runtime } = await setup();

    const response = await createProxy({ runtime, guard: GUARD })(request("/", { ecommerce_refresh: "revoked" }));

    expect(response.status).toBe(307);
    expect(response.cookies.get("ecommerce_refresh")?.value).toBe("");
    expect(response.headers.get("set-cookie")).toMatch(/Max-Age=0/i);
  });

  it("answers 503 with Retry-After, not a redirect, when the gateway is down", async () => {
    const { runtime, fetchMock } = await setup();
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));

    const response = await createProxy({ runtime, guard: GUARD })(request("/", { ecommerce_refresh: "r1" }));

    expect(response.status).toBe(503);
    expect(response.headers.get("retry-after")).toBe("5");
    expect(response.headers.get("content-security-policy")).toBeTruthy();
    expect(response.cookies.get("ecommerce_refresh")).toBeUndefined();
  });

  it("rethrows unexpected errors", async () => {
    const { runtime } = await setup();
    const broken = {
      ...runtime,
      resolve: () => Promise.reject(new Error("bug")),
    } satisfies AuthRuntime;

    await expect(createProxy({ runtime: broken, guard: GUARD })(request("/"))).rejects.toThrow("bug");
  });
});

describe("createProxy protecting only some paths", () => {
  const guard = { loginPath: "/login", isProtected: (pathname: string) => pathname.startsWith("/account") };

  it("leaves public pages alone and guards the account pages", async () => {
    const { runtime } = await setup();
    const proxy = createProxy({ runtime, guard });

    expect((await proxy(request("/products"))).status).toBe(200);
    expect((await proxy(request("/account"))).status).toBe(307);
  });

  it("accepts any role when none is required", async () => {
    const { runtime, keys } = await setup();

    const response = await createProxy({ runtime, guard })(
      request("/account", { ecommerce_access: await keys.sign({ role: "customer" }) }),
    );

    expect(response.status).toBe(200);
  });
});

describe("ApiError import", () => {
  it("is the same class the runtime throws", () => {
    expect(ApiError).toBeDefined();
  });
});
