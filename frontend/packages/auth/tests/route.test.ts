/**
 * @jest-environment node
 */
import { createAuthRuntime } from "../src";
import { applyCookies, guardRoute } from "../src/next";
import { CONFIG, createTestKeys, jsonResponse, tokensBody } from "./support/tokens";

async function runtimeWith(handler: () => Promise<Response> = () => Promise.reject(new Error("unused"))) {
  const keys = await createTestKeys();
  const fetchMock = jest.fn(handler);
  const runtime = createAuthRuntime(CONFIG, { fetch: fetchMock as unknown as typeof fetch, keySet: keys.keySet });
  return { keys, fetchMock, runtime };
}

function requestWith(cookie: string | undefined, headers: Record<string, string> = {}): Request {
  return new Request("http://backoffice.test/admin/api/stream/x", {
    method: "PUT",
    headers: { ...(cookie ? { cookie } : {}), ...headers },
  });
}

describe("guardRoute", () => {
  it("accepts a valid admin token and exposes it for the upstream call", async () => {
    const { keys, runtime } = await runtimeWith();
    const token = await keys.sign({ role: "admin" });

    const result = await guardRoute(requestWith(`other=1; ecommerce_access=${token}`, { "x-forwarded-for": "203.0.113.9" }), {
      runtime,
      requiredRole: "admin",
    });

    expect(result).toMatchObject({
      ok: true,
      access: { accessToken: token, clientIp: "203.0.113.9", cookies: [], session: { role: "admin" } },
    });
  });

  it("refreshes an expired session and hands back the new token and cookies", async () => {
    const { keys, runtime, fetchMock } = await runtimeWith();
    const expired = await keys.sign({ role: "admin" }, { expiresIn: "-1m" });
    const fresh = await keys.sign({ role: "admin" });
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(tokensBody(fresh, "r2"))));

    const result = await guardRoute(requestWith(`ecommerce_access=${expired}; ecommerce_refresh=r1`), { runtime });

    expect(result).toMatchObject({ ok: true, access: { accessToken: fresh } });
    expect(result.ok && result.access.cookies.map((cookie) => cookie.name)).toEqual([
      "ecommerce_access",
      "ecommerce_refresh",
    ]);
  });

  it("answers 401 without a session and clears nothing it never had", async () => {
    const { runtime } = await runtimeWith();

    const result = await guardRoute(requestWith(undefined), { runtime });

    expect(result.ok).toBe(false);
    expect(!result.ok && result.response.status).toBe(401);
    expect(!result.ok && result.response.headers.get("content-type")).toBe("application/problem+json");
  });

  it("answers 401 and clears cookies for a bad token", async () => {
    const { runtime } = await runtimeWith();

    const result = await guardRoute(requestWith("ecommerce_access=garbage"), { runtime });

    expect(!result.ok && result.response.status).toBe(401);
    expect(!result.ok && result.response.headers.get("set-cookie")).toContain("ecommerce_access=;");
  });

  it("answers 403 for the wrong role", async () => {
    const { keys, runtime } = await runtimeWith();
    const token = await keys.sign({ role: "customer" });

    const result = await guardRoute(requestWith(`ecommerce_access=${token}`), { runtime, requiredRole: "admin" });

    expect(!result.ok && result.response.status).toBe(403);
  });

  it("refuses cross-site requests before looking at the session", async () => {
    const { keys, runtime } = await runtimeWith();
    const token = await keys.sign({ role: "admin" });

    const result = await guardRoute(requestWith(`ecommerce_access=${token}`, { "sec-fetch-site": "cross-site" }), {
      runtime,
    });

    expect(!result.ok && result.response.status).toBe(403);
  });

  it("answers 503 with Retry-After when the keys cannot be fetched", async () => {
    const keys = await createTestKeys();
    const runtime = createAuthRuntime(CONFIG, {
      fetch: jest.fn() as unknown as typeof fetch,
      keySet: () => Promise.reject(new TypeError("offline")),
    });

    const result = await guardRoute(requestWith(`ecommerce_access=${await keys.sign()}`), { runtime });

    expect(!result.ok && result.response.status).toBe(503);
    expect(!result.ok && result.response.headers.get("retry-after")).toBe("5");
  });

  it("rethrows unexpected failures", async () => {
    const { runtime } = await runtimeWith();
    const broken = { ...runtime, resolve: () => Promise.reject(new Error("bug")) };

    await expect(guardRoute(requestWith("ecommerce_access=x"), { runtime: broken })).rejects.toThrow("bug");
  });
});

describe("applyCookies", () => {
  it("writes the cookie specs onto the response", async () => {
    const { keys, runtime } = await runtimeWith();
    const token = await keys.sign({ role: "admin" });
    const result = await guardRoute(requestWith("ecommerce_access=garbage"), { runtime });
    expect(result.ok).toBe(false);

    const response = applyCookies(new (await import("next/server")).NextResponse(null), [
      { name: "a", value: token, options: { httpOnly: true, secure: false, sameSite: "lax", path: "/", maxAge: 5 } },
    ]);

    expect(response.headers.get("set-cookie")).toContain("a=");
  });
});
